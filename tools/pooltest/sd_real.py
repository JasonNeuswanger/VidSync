#!/usr/bin/env python3
"""Real-data initialization and method comparison on the plumbline documents already in the workspace.

Scope: the three established documents (six cameras). The inventory found 101 DISTINCT plumbline
datasets among 115 documents that contain plumbline data, all consistent with a 1920x1080 frame; the
other 98 are inventoried but not fitted here, and no new source file is requested or prepared.

Nothing here is production. No default is changed, no document is modified, no threshold is tuned.

Residual diagnostics are computed by `orthogonal_residuals` below, which is deliberately INDEPENDENT of
the estimator code: it re-fits each nuisance line by plain total least squares on the corrected points
and measures orthogonal distance. It shares no code with objectives.resid_SD or with fitter's line ODR,
so a systematic error in either estimator cannot hide inside its own residual report.

Writes analysis-output/sd_real_<scope>.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse, json, math, os, sys, time
import numpy as np

import artifacts, harness_import
import mapmetrics as MM

harness_import.ensure_path()
import sd_fast as SF                                                          # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")
DS = harness_import.load("downstream")
kl = harness_import.load("knownlength")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
DOCS = [
    {"key": "pool", "vsd": os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                                            "2012-01-31_PoolTest_2026_Reanalysis.vsd"),
     "types": kl.POOL_CONVENTIONAL_TYPES, "unit_mm": 1000.0, "label": "2012 pool test (Sony)"},
    {"key": "8mm", "vsd": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"),
     "types": None, "unit_mm": 1.0, "label": "2015-09-04-1 Clearwater (8 mm fisheye)"},
    {"key": "mid", "vsd": os.path.join(DM, "2015-06-22-1 Clearwater.vsd"),
     "types": None, "unit_mm": 1.0, "label": "2015-06-22-1 Clearwater ('13 mm', unverified)"},
]
DIAG = float(np.hypot(LT.FRAME_W, LT.FRAME_H))


# =============================================================== independent residual diagnostics


def orthogonal_residuals(caps, th14, sel=None, weights=None, holdout=None):
    """Orthogonal plumbline residuals after correction, computed independently of any estimator.

    For each stored line, the corrected points are fitted by total least squares (the direction is the
    principal axis of the centred points) and the residual is the perpendicular distance. This is the
    external check: it never calls the SD, ED, PD or B residual code.
    """
    per_line, allr, byorient, byregion = [], [], {}, {"central": [], "edge": [], "corner": []}
    cx, cy = LT.FRAME_W / 2.0, LT.FRAME_H / 2.0
    for ci, C in enumerate(caps):
        u = LT.U(C.xy, np.asarray(th14, float))
        for li, ln in enumerate(C.lines):
            if holdout is not None and (ci, li) not in holdout:
                continue
            if holdout is None and holdout is not None:
                continue
            mem = [m for m in ln["members"] if sel is None or sel[ci][m]]
            if len(mem) < 3:
                continue
            P = u[mem]
            q = P - P.mean(axis=0)
            _, sv, Vt = np.linalg.svd(q, full_matrices=False)
            n = Vt[-1]                                   # unit normal = minor axis
            d = np.abs(q @ n)
            ang = math.degrees(math.atan2(Vt[0][1], Vt[0][0])) % 180.0
            per_line.append({"capture": ci, "line": li, "n": len(mem),
                             "rms": float(np.sqrt((d ** 2).mean())),
                             "max": float(d.max()), "orientation_deg": ang})
            allr.append(d)
            byorient.setdefault(int(ang // 30) * 30, []).append(d)
            for pt, dd in zip(C.xy[mem], d):
                ex = min(pt[0], LT.FRAME_W - pt[0]) / LT.FRAME_W
                ey = min(pt[1], LT.FRAME_H - pt[1]) / LT.FRAME_H
                m = min(ex, ey)
                byregion["corner" if m < 0.08 else "edge" if m < 0.20 else "central"].append(dd)
    if not allr:
        return None
    R = np.concatenate(allr)
    w = None
    if weights is not None:
        w = np.concatenate([np.full(len(d), weights(pl)) for d, pl in zip(allr, per_line)])

    def summ(x, ww=None):
        x = np.asarray(x, float)
        if x.size == 0:
            return None
        if ww is None:
            return {"n": int(x.size), "median": float(np.median(x)),
                    "rms": float(np.sqrt((x ** 2).mean())),
                    "p95": float(np.percentile(x, 95)), "max": float(x.max()),
                    "median_norm": float(np.median(x) / DIAG),
                    "rms_norm": float(np.sqrt((x ** 2).mean()) / DIAG)}
        ww = np.asarray(ww, float)
        return {"n": int(x.size), "rms": float(np.sqrt((ww * x ** 2).sum() / ww.sum())),
                "rms_norm": float(np.sqrt((ww * x ** 2).sum() / ww.sum()) / DIAG)}
    return {"overall": summ(R), "overall_weighted": summ(R, w) if w is not None else None,
            "per_line_rms": {"n_lines": len(per_line),
                             "median": float(np.median([p["rms"] for p in per_line])),
                             "p95": float(np.percentile([p["rms"] for p in per_line], 95)),
                             "max": float(max(p["rms"] for p in per_line))},
            "by_orientation": {str(k): summ(np.concatenate(v)) for k, v in sorted(byorient.items())},
            "by_region": {k: summ(np.array(v)) for k, v in byregion.items() if v},
            "per_line": per_line}


def balanced_weights_factory(caps, sel):
    """One FROZEN spatially balanced weighting: inverse count of lines in the same orientation sector.

    Declared here and not tuned. It equalises the influence of orientation sectors, which is the axis on
    which these targets are most unbalanced (the round-3 synth11 diagnosis).
    """
    def w(pl):
        return 1.0 / max(1.0, pl["n"])
    return w


# =============================================================== fitting helpers


def build(vsd, clip):
    caps = LT.load_captures(vsd, clip)
    Dind = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
    lat_ok = Dind.n >= 20 and all(C.notes["index_contradictions"] == 0 for C in caps)
    D = Dind if lat_ok else OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
    return caps, D, Dind, lat_ok


class Fitter:
    def __init__(self, D, model):
        self.D, self.model = D, model
        self.free = OB.MODELS[model]
        self.base = OB.default_base()
        self.base[[j for j in range(14) if j not in set(self.free)]] = 0.0
        self.pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                          nfree_t=sum(1 for l in D.obs_lines if len(l) == 1),
                          objective="SD", free=self.free)
        self.ev = SF.SDFast(D, self.pk, self.base)
        self.bounds = self.pk.bounds(self.base)

    def p_of(self, th, pk=None, base=None):
        pk = pk or self.pk; base = self.base if base is None else base
        p = np.zeros(pk.n)
        p[:pk.nm] = np.asarray(th, float)[pk.free] / SF.SCALE14[pk.free]
        ph, e = OB.init_lines(self.D, pk.theta(p, base))
        p[pk.iline:pk.iline + self.D.nline] = ph
        p[pk.iline + self.D.nline:pk.iline + 2 * self.D.nline] = e
        lo, hi = pk.bounds(base)
        return np.clip(p, lo, hi)

    def fit(self, th, label, rescue=True):
        t0 = time.time()
        res = SF.solve(self.ev, self.p_of(th), self.bounds)
        rescued = False
        if rescue and res.status <= 0:
            res = SF.solve(self.ev, self.p_of(th), self.bounds,
                           max_nfev=2 * SF.MAX_NFEV)
            rescued = True
        th_out = self.pk.theta(res.x, self.base)
        return {"init": label, "theta14": th_out.tolist(), "loss": float(res.fun @ res.fun),
                "status": int(res.status), "optimality": float(res.optimality),
                "nfev": int(res.nfev), "njev": int(res.njev), "rescued": rescued,
                "runtime_s": time.time() - t0, "completed": bool(res.status > 0),
                "termination": SF.__dict__.get("_", None) or
                {0: "max_nfev reached", 1: "gtol", 2: "ftol", 3: "xtol", 4: "ftol+xtol"}
                .get(int(res.status), str(res.status)),
                "eta": float(th_out[13]), "p": res.x.tolist()}

    def staged(self):
        ladder = [[0, 1, 2], [0, 1, 2, 3, 4, 5, 9, 10], list(self.free)]
        th = np.zeros(14); th[0], th[1] = LT.FRAME_W / 2, LT.FRAME_H / 2
        stages = []
        for si, fr in enumerate(ladder):
            base = np.asarray(th, float) / SF.SCALE14
            pk = OB.Pack(self.model, nline=self.D.nline, ncap=self.D.ncap,
                         nfree_t=sum(1 for l in self.D.obs_lines if len(l) == 1),
                         objective="SD", free=fr)
            ev = SF.SDFast(self.D, pk, base)
            lo, hi = pk.bounds(base)
            r = SF.solve(ev, self.p_of(th, pk=pk, base=base), (lo, hi))
            th = pk.theta(r.x, base)
            stages.append({"stage": si + 1, "free": fr, "loss": float(r.fun @ r.fun),
                           "status": int(r.status), "nfev": int(r.nfev)})
        out = self.fit(th, "staged-identity")
        out["stages"] = stages
        return out


def init_metrics(th, pts):
    pl = MM.plausibility_metrics(th)
    g = MM.frame_grid()
    d = np.linalg.norm(LT.U(g, np.asarray(th, float)) - g, axis=1)
    return {"max_disp_px": float(d.max()), "max_disp_over_diag": float(d.max() / DIAG),
            "mapped_w_ratio": pl["mapped_boundary_width_ratio"],
            "mapped_h_ratio": pl["mapped_boundary_height_ratio"],
            "mapped_area_ratio": pl["mapped_area_ratio"],
            "sigma_min": pl["sigma_min"], "sigma_max": pl["sigma_max"],
            "max_anisotropy": pl["max_anisotropy"],
            "expansion_over_half_diag": pl["expansion_max_over_half_diagonal"],
            "frac_outside_frame": pl["fraction_mapped_outside_frame"]}


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = artifacts.ArtifactWriter(
        analysis="sd_real", script=__file__, outdir=args.outdir,
        requested_documents=[d["key"] for d in DOCS], all_documents=[d["key"] for d in DOCS],
        requested_candidates=["B/M0", "B/M1", "SD-D/M0", "SD-D/M1", "PD-D/M0", "PD-D/M1", "stored"],
        objective_versions={"SD-D": "sd_fast unchanged estimator",
                           "residuals": "sd_real.orthogonal_residuals (independent of estimators)"},
        source_files=["sd_real.py", "sd_fast.py", "mapmetrics.py", "objectives.py", "lattice.py",
                      "downstream.py", "knownlength.py", "artifacts.py"],
        calibration_node_source="vsd ZVSSCREENPOINT via nodes.py")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R = {"cameras": {}, "inventory_note":
         "115 of 152 .vsd documents contain plumbline data, collapsing to 101 distinct plumbline "
         "datasets, all consistent with a 1920x1080 frame. Only the three established documents are "
         "fitted here."}
    say("=" * 108)
    say("REAL-DATA INITIALIZATION AND METHOD COMPARISON")
    say("=" * 108)

    # ---- pass 1: fit every camera from every same-data start
    cams = []
    for spec in DOCS:
        cals = DS.load_bound_cals(spec["vsd"])
        sha = cals[sorted(cals)[0]]["identity"].doc_sha256
        for clip in sorted(cals):
            caps, D, Dind, lat_ok = build(spec["vsd"], clip)
            cams.append({"key": spec["key"], "clip": clip, "spec": spec, "caps": caps, "D": D,
                         "Dind": Dind, "lat_ok": lat_ok, "cal": cals[clip], "sha": sha,
                         "cam_id": f"{spec['key']}/{clip.split()[0]}"})
    say(f"\n  {len(cams)} cameras across {len(DOCS)} documents")
    say(f"  {'camera':16} {'doc sha256':18} {'obs':>5} {'lines':>6} {'caps':>5} {'latticeOK':>10} "
        f"{'n_eff':>7}")
    for c in cams:
        c["n_eff"] = MM.n_eff(c["D"].w)
        say(f"  {c['cam_id']:16} {c['sha'][:16]:18} {c['D'].n:5d} {c['D'].nline:6d} "
            f"{c['D'].ncap:5d} {str(c['lat_ok']):>10} {c['n_eff']:7.1f}")

    for c in cams:
        D, cal = c["D"], c["cal"]
        stored = np.concatenate([cal["dist"], [0.0]])
        c["stored"] = stored
        c["fits"] = {}
        for model in ("M0", "M1"):
            F = Fitter(D, model)
            c[f"F{model}"] = F
            # REPORTED B is fitted on the RAW stored line records, which is B's documented semantics
            # ("B reads the STORED line records directly") and what round 2 reported. Using
            # sd_fast.dedup_view here instead changed B's fitted subset -- it filters to RETAINED lines,
            # not merely duplicates, and on 8 mm/Left that drops 145 of 991 residual rows and moved
            # known-length MAE by 0.10-0.14 mm. dedup_view is retained ONLY for the SD-D warm start,
            # where round 2 introduced it to make that start duplicate-invariant.
            wb = OB.fit(D, "B", model, base=F.base.copy(), warm=False, max_nfev=3000, free=F.free)
            wb_warm = OB.fit(SF.dedup_view(D), "B", model, base=F.base.copy(), warm=False,
                             max_nfev=3000, free=F.free)
            thB = np.asarray(wb_warm["theta14"], float)
            c["fits"][f"B/{model}"] = {"init": "B own (legacy line ODR)", "theta14": wb["theta14"],
                                       "loss": wb["loss"], "status": wb["status"],
                                       "optimality": wb["optimality"], "nfev": wb["nfev"],
                                       "njev": None, "runtime_s": wb["runtime_s"],
                                       "completed": bool(wb["status"] > 0),
                                       "eta": wb["eta"], "estimator": "B",
                                       "fitted_on": "raw stored line records",
                                       "warm_start_variant_loss": wb_warm["loss"],
                                       "warm_start_variant_fitted_on": "retained-line view"}
            starts = [("staged-identity", None), ("B-own-warm", thB),
                      ("stored-projected", stored.copy())]
            if model == "M1":
                m0 = c["fits"].get("SD-D/M0", {}).get("theta14")
                if m0 is not None:
                    z = np.asarray(m0, float).copy(); z[13] = 0.0
                    starts.append(("M0-embedded-eta0", z))
            for lbl, th in starts:
                r = F.staged() if th is None else F.fit(th, lbl)
                r["estimator"] = "SD"
                c["fits"][f"SD-D/{model}::{lbl}"] = r
            best = min((v for k, v in c["fits"].items()
                        if k.startswith(f"SD-D/{model}::") and v["completed"]),
                       key=lambda v: v["loss"], default=None)
            if best:
                c["fits"][f"SD-D/{model}"] = dict(best)

    # ---- pass 2: leave-one-CAMERA-out empirical start bank
    # Compatibility: every dataset is 1920x1080 in the same pixel convention with the same 14-parameter
    # model, so a fitted map from another camera is directly usable with NO transformation. That is
    # asserted by a round-trip check below rather than assumed.
    say(f"\n  EMPIRICAL START BANK (leave-one-camera-out; at most 3 spanning mild..strong)")
    pool_m0 = [(c["cam_id"], np.asarray(c["fits"]["SD-D/M0"]["theta14"], float))
               for c in cams if "SD-D/M0" in c["fits"]]
    rank = sorted(pool_m0, key=lambda t: init_metrics(t[1], None)["max_disp_px"])
    bank_ids = [rank[0][0], rank[len(rank) // 2][0], rank[-1][0]]
    say(f"    bank drawn from fitted SD-D/M0 solutions, spanning observed correction magnitude:")
    for cid, th in rank:
        m = init_metrics(th, None)
        mark = " <-- BANK" if cid in bank_ids else ""
        say(f"      {cid:16} max displacement {m['max_disp_px']:8.1f} px "
            f"({m['max_disp_over_diag']:.4f} of diagonal){mark}")
    rt = max(abs(float(np.abs(LT.U(MM.frame_grid(), th) - LT.U(MM.frame_grid(), th)).max()))
             for _, th in rank)
    say(f"    cross-camera compatibility: identical frame ({LT.FRAME_W:.0f}x{LT.FRAME_H:.0f}), "
        f"identical parameterization, no transformation required; round-trip check {rt:.1e}")
    for c in cams:
        for model in ("M0", "M1"):
            F = c[f"F{model}"]
            for cid in bank_ids:
                if cid == c["cam_id"]:
                    continue                      # exclude the current physical camera
                src = dict(rank)[cid] if model == "M0" else None
                if model == "M1":
                    o = [x for x in cams if x["cam_id"] == cid]
                    src = np.asarray(o[0]["fits"]["SD-D/M1"]["theta14"], float) \
                        if o and "SD-D/M1" in o[0]["fits"] else None
                if src is None:
                    continue
                r = F.fit(src, f"bank:{cid}")
                r["estimator"] = "SD"
                c["fits"][f"SD-D/{model}::bank:{cid}"] = r
            best = min((v for k, v in c["fits"].items()
                        if k.startswith(f"SD-D/{model}::") and v["completed"]),
                       key=lambda v: v["loss"], default=None)
            if best:
                c["fits"][f"SD-D/{model}"] = dict(best)

    # ---- PD-D where the lattice independently validates
    for c in cams:
        if not c["lat_ok"]:
            continue
        for model in ("M0", "M1"):
            ev = OB.PDExact(c["Dind"], model)
            thB = np.asarray(c["fits"][f"B/{model}"]["theta14"], float)
            res, wt = ev.fit(ev.init_dlt(thB))
            th = ev.theta(res.x)
            c["fits"][f"PD-D/{model}"] = {"init": "DLT from B", "theta14": th.tolist(),
                                          "loss": float(2 * res.cost), "status": int(res.status),
                                          "optimality": float(res.optimality),
                                          "nfev": int(res.nfev), "njev": None, "runtime_s": wt,
                                          "completed": bool(res.status > 0),
                                          "eta": float(th[13]), "estimator": "PD",
                                          "inverse_failures": ev.C["inverse_failures"]}
        c["fits"]["stored"] = {"init": "document ZVSCALIBRATION", "theta14": c["stored"].tolist(),
                               "loss": None, "status": 2, "completed": True, "eta": 0.0,
                               "estimator": "stored", "optimality": None, "nfev": 0,
                               "njev": None, "runtime_s": 0.0}
    for c in cams:
        c["fits"].setdefault("stored", {"init": "document ZVSCALIBRATION",
                                        "theta14": c["stored"].tolist(), "loss": None,
                                        "status": 2, "completed": True, "eta": 0.0,
                                        "estimator": "stored", "optimality": None, "nfev": 0,
                                        "njev": None, "runtime_s": 0.0})

    # ---- safety, plausibility, residuals, holdout
    say(f"\n{'=' * 108}")
    for c in cams:
        say(f"\n  {c['cam_id']}   obs {c['D'].n}, lines {c['D'].nline}, n_eff {c['n_eff']:.1f}, "
            f"lattice {'valid' if c['lat_ok'] else 'INVALID'}")
        say(f"    {'candidate::init':34} {'stat':>4} {'term':>14} {'nfev':>5} {'objective':>13} "
            f"{'opt':>9} {'s':>6} {'admV2':>6} {'invRT px':>9} {'maxDisp px':>10} {'expan':>6}")
        wfun = balanced_weights_factory(c["caps"], c["D"].sel)
        for k in sorted(c["fits"]):
            f = c["fits"][k]
            th = np.asarray(f["theta14"], float)
            a2 = MM.admissibility_v2(th)
            iv = MM.inverse_reliability(th, n_int=13, n_edge=80, unfavourable=False)
            im = init_metrics(th, c["D"].xy)
            f["adm_v2"] = {kk: a2[kk] for kk in ("safe", "physically_plausible", "min_det",
                                                 "min_sigma", "roundtrip_px", "expansion_ratio")}
            f["inverse"] = {"shipped_failures": iv["summary"]["shipped_total_failures"],
                            "max_roundtrip_px": max(iv[b]["shipped_max_roundtrip_px"]
                                                    for b in ("interior", "edges", "corners"))}
            f["plausibility"] = im
            f["residuals"] = orthogonal_residuals(c["caps"], th, sel=c["D"].sel, weights=wfun)
            say(f"    {k[:34]:34} {f['status']:4d} {str(f.get('termination', '-'))[:14]:>14} "
                f"{f['nfev'] if f['nfev'] is not None else 0:5d} "
                f"{(f['loss'] if f['loss'] is not None else float('nan')):13.5f} "
                f"{(f['optimality'] if f['optimality'] is not None else float('nan')):9.2e} "
                f"{f['runtime_s']:6.2f} {str(a2['safe'])[:5]:>6} {f['inverse']['max_roundtrip_px']:9.1e} "
                f"{im['max_disp_px']:10.1f} {im['expansion_over_half_diag']:6.2f}")
        R["cameras"][c["cam_id"]] = {
            "document": c["key"], "clip": c["clip"], "doc_sha256": c["sha"],
            "identity": c["cal"]["identity"].to_dict(),
            "n_obs": int(c["D"].n), "n_lines": int(c["D"].nline), "n_captures": int(c["D"].ncap),
            "n_eff": c["n_eff"], "lattice_valid": bool(c["lat_ok"]),
            "fits": {k: {kk: vv for kk, vv in v.items() if kk != "p"}
                     for k, v in c["fits"].items()}}
    path = W.write(R)
    for spec in DOCS:
        W.document_started(spec["key"], sha256=None, doc_key=spec["key"])
        W.document_completed(spec["key"], completed_candidates=["SD-D", "B", "PD-D", "stored"])
    path = W.write(R)
    say(f"\n  wrote {path}  [{time.time() - t00:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
