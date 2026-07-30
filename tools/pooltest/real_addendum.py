#!/usr/bin/env python3
"""ADDENDUM 2026-07-29: completing the established-real-data method comparison after the lattice fix.

WHY THIS EXISTS. The earlier established-data study (`sd_real.py`, `xdoc_objectives.py`) reported
`2015-06-22-1 Clearwater` as lattice-invalid and therefore excluded PD-D on both of its cameras. That
exclusion was an artefact of a traversal-canonicalization defect in `lattice._recover_indices`, now
fixed: click direction was being allowed to decide edge direction while the index step was chosen by
orientation family, so one line clicked against its family-mates made every cycle through it contradict.
With the fix both cameras index completely and are PD-D eligible through the ordinary production path.

This script does NOT re-derive the study. The two established scripts were re-run UNCHANGED into
`analysis-output/addendum-2026-07-29/`, so the only difference from the historical artifacts is the
lattice fix, and this script reads their output and adds what they do not compute:

  * PD-D/M0 and PD-D/M1 with full optimization and empirical map diagnostics for all six cameras,
    including the M1-from-fitted-M0-at-eta-zero start alongside the established DLT-from-B start;
  * ONE common residual implementation applied to every map, on each method's NATIVE observations and
    on the COMMON indexed intersection, unweighted and under the frozen balanced weighting;
  * the FULL pairwise map-disagreement matrix per camera (raw and projectively aligned, hull, full
    frame, edge and corner), not each method's distance from a chosen reference;
  * the known-length table assembled from the re-run downstream artifact.

Nothing here changes production code, defaults, thresholds, documents or plumbline data, and no
additional document is opened: the six established cameras only.

Run with ~/.venvs/vidsync/bin/python. See ADDENDUM_2026-07-29_REAL_DATA.md for the commands.
"""

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

import artifacts
import harness_import
import mapmetrics as MM

harness_import.ensure_path()
import sd_real as SR                                                          # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")
DS = harness_import.load("downstream")
O1 = harness_import.load("obj_round1")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DIAG = SR.DIAG
GRID = MM.frame_grid()

# The region rule is the one already used by the residual diagnostics, applied to the frame grid so
# residual regions and map-disagreement regions mean the same thing.
_ex = np.minimum(GRID[:, 0], LT.FRAME_W - GRID[:, 0]) / LT.FRAME_W
_ey = np.minimum(GRID[:, 1], LT.FRAME_H - GRID[:, 1]) / LT.FRAME_H
_m = np.minimum(_ex, _ey)
REGION = {"corner": _m < 0.08, "edge": (_m >= 0.08) & (_m < 0.20), "central": _m >= 0.20}

METHODS = ["stored", "B/M0", "B/M1", "SD-D/M0", "SD-D/M1", "PD-D/M0", "PD-D/M1"]


# =============================================================== 1. frozen inputs


def plumbline_hash(caps):
    """A digest of the stored plumbline geometry that is INVARIANT to click direction and record order.

    Each line contributes its point coordinates rounded to 1e-6 px and sorted; the lines are then sorted
    and hashed. Two documents with the same physical digitization hash identically no matter which way
    the operator clicked, which is exactly the equivalence the lattice fix establishes, so this digest
    also demonstrates that the fix did not alter the input.
    """
    h = hashlib.sha256()
    for C in caps:
        rows = []
        for ln in C.lines:
            pts = sorted(tuple(np.round(C.xy[m], 6)) for m in ln["members"])
            rows.append(repr(pts))
        for r in sorted(rows):
            h.update(r.encode())
        h.update(b"|" + C.timecode.encode())
    return h.hexdigest()


def freeze(say):
    """Exact inputs, hashes, views and per-method observation sets for the six established cameras."""
    say("=" * 118)
    say("1. FROZEN INPUTS")
    say("=" * 118)
    cams, out = [], {}
    for spec in SR.DOCS:
        cals = DS.load_bound_cals(spec["vsd"])
        for clip in sorted(cals):
            caps, D, Dind, lat_ok = SR.build(spec["vsd"], clip)
            Draw = OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
            cid = f"{spec['key']}/{clip.split()[0]}"
            ident = cals[clip]["identity"]
            rec = {
                "camera": cid, "document": spec["key"], "label": spec["label"], "clip": clip,
                "vsd_path": spec["vsd"], "doc_sha256": ident.doc_sha256,
                "calibration_pk": ident.cal_pk, "clip_pk": getattr(ident, "clip_pk", None),
                "plumbline_sha256": plumbline_hash(caps),
                "frame": [LT.FRAME_W, LT.FRAME_H],
                "coordinate_convention": "stored screen pixels, origin top-left, y down, as digitized; "
                                         "no flip or normalization applied anywhere in this harness",
                "n_captures": int(D.ncap), "n_stored_incidences": int(sum(
                    len(ln["members"]) for C in caps for ln in C.lines)),
                "n_unique_observations": int(sum(C.n for C in caps)),
                "n_lines_stored": int(sum(len(C.lines) for C in caps)),
                "lattice_valid": bool(lat_ok),
                "index_contradictions": int(sum(C.notes["index_contradictions"] for C in caps)),
                "reliably_indexed": int(sum(C.notes["reliably_indexed"] for C in caps)),
                "traversal_canonicalized_lines": int(sum(
                    C.notes["n_traversal_canonicalized"] for C in caps)),
                "degenerate_direction_lines": int(sum(
                    len(C.notes.get("degenerate_direction_lines", [])) for C in caps)),
                "view_raw_records": {"n_obs": int(Draw.n), "n_lines": int(Draw.nline),
                                     "consumer": "B (legacy line ODR), reported fit"},
                "view_indexed": {"n_obs": int(Dind.n), "n_lines": int(Dind.nline),
                                 "consumer": "PD-D and SD-D (identical observations)"},
                "n_eff_indexed": MM.n_eff(Dind.w),
            }
            cams.append({"cid": cid, "spec": spec, "caps": caps, "D": D, "Dind": Dind,
                         "Draw": Draw, "cal": cals[clip], "lat_ok": lat_ok, "rec": rec,
                         "stored": np.concatenate([cals[clip]["dist"], [0.0]])})
            out[cid] = rec
    say(f"  {'camera':12} {'doc sha256':18} {'plumbline sha256':18} {'stored inc':>10} {'unique':>7} "
        f"{'lines':>6} {'indexed':>8} {'Dind.n':>7} {'n_eff':>8} {'latOK':>6} {'canon':>6}")
    for c in cams:
        r = c["rec"]
        say(f"  {r['camera']:12} {r['doc_sha256'][:16]:18} {r['plumbline_sha256'][:16]:18} "
            f"{r['n_stored_incidences']:10d} {r['n_unique_observations']:7d} {r['n_lines_stored']:6d} "
            f"{r['reliably_indexed']:8d} {r['view_indexed']['n_obs']:7d} {r['n_eff_indexed']:8.1f} "
            f"{str(r['lattice_valid']):>6} {r['traversal_canonicalized_lines']:6d}")
    say("")
    say("  DATA VIEWS, defined once and not adjusted for symmetry:")
    say("    V_raw     every stored line-point record. A corner shared by two lines appears in both.")
    say("              B's reported fit consumes V_raw; that is B's documented semantics.")
    say("    V_indexed unique observations (exact-coordinate match) that carry a consistent lattice")
    say("              index, with at least 2 line incidences and the established kappa=3.0 weighting.")
    say("              PD-D requires it. SD-D is given the SAME view whenever the lattice validates, so")
    say("              the two are compared on identical observations -- the established rule, now")
    say("              satisfied on all six cameras rather than four.")
    say("    NOTE      on `mid` the historical SD-D fits used the require_indexed=False view (365 and")
    say("              365 observations) BECAUSE the lattice was wrongly rejected. Those SD-D numbers")
    say("              are therefore not comparable to the ones here; the rule did not change, its")
    say("              precondition did.")
    return cams, out


# =============================================================== 2. PD-D fits


def pd_diagnostics(th, pts):
    a2 = MM.admissibility_v2(th)
    iv = MM.inverse_reliability(th, n_int=13, n_edge=80, unfavourable=False)
    cert = MM.certify_forward_injective(th, max_cells=800)
    pl = SR.init_metrics(th, pts)
    return {
        "admissibility_v2": {k: a2[k] for k in ("safe", "physically_plausible", "min_det",
                                                "min_sigma", "roundtrip_px", "expansion_ratio")},
        "forward_certificate": {"verdict": cert["verdict"], "cells": cert["cells_certified"]},
        "inverse": {"shipped_failures": iv["summary"]["shipped_total_failures"],
                    "max_roundtrip_px": max(iv[b]["shipped_max_roundtrip_px"]
                                            for b in ("interior", "edges", "corners"))},
        "displacement_boundary_jacobian": pl,
    }


def fit_pd(cams, say):
    """PD-D/M0 and PD-D/M1 on every eligible camera, with both initializations.

    The established policy is DLT-from-B per model, which is what the historical eligible cases used and
    what the re-run of `sd_real.py` reproduces. The brief also asks for M1 started from the FITTED M0 at
    eta = 0; that is run here for every eligible camera, not only the new ones, and reported beside the
    established start. Selection between them is by objective value only -- no downstream or
    known-length quantity is consulted.
    """
    say("")
    say("=" * 118)
    say("2. PD-D FITS THROUGH THE ORDINARY PRODUCTION PATH")
    say("=" * 118)
    say(f"  {'camera':12} {'candidate':26} {'stat':>4} {'nfev':>5} {'objective':>13} {'opt':>9} "
        f"{'eta':>11} {'s':>6} {'admV2':>6} {'fwd cert':>32} {'invRT px':>9}")
    out = {}
    for c in cams:
        if not c["lat_ok"]:
            say(f"  {c['cid']:12} INELIGIBLE (lattice did not validate)")
            continue
        Dind = c["Dind"]
        c["pd"] = {}
        for model in ("M0", "M1"):
            free = OB.MODELS[model]
            base = OB.default_base()
            base[[j for j in range(14) if j not in set(free)]] = 0.0
            wb = OB.fit(Dind, "B", model, base=base.copy(), warm=False, max_nfev=3000, free=free)
            starts = [("DLT-from-B (established)", np.asarray(wb["theta14"], float))]
            if model == "M1" and "PD-D/M0" in c["pd"]:
                z = np.asarray(c["pd"]["PD-D/M0"]["theta14"], float).copy()
                z[13] = 0.0
                starts.append(("fitted-PD-D/M0-at-eta0", z))
            variants = []
            for lbl, th0 in starts:
                ev = OB.PDExact(Dind, model)
                t0 = time.time()
                res, wt = ev.fit(ev.init_dlt(th0))
                th = ev.theta(res.x)
                rec = {
                    "camera": c["cid"], "candidate": f"PD-D/{model}", "init": lbl,
                    "theta14": th.tolist(), "eta": float(th[13]),
                    "loss": float(2 * res.cost), "status": int(res.status),
                    "termination": {0: "max_nfev reached", 1: "gtol", 2: "ftol", 3: "xtol",
                                    4: "ftol+xtol", -1: "improper input"}.get(int(res.status),
                                                                              str(res.status)),
                    "optimality": float(res.optimality), "nfev": int(res.nfev),
                    "runtime_s": float(wt if wt else time.time() - t0),
                    "converged": bool(res.status > 0),
                    "n_indexed_observations": int(Dind.n), "n_fitted_observations": int(Dind.n),
                    "n_lines": int(Dind.nline), "n_captures": int(Dind.ncap),
                    "pdexact_inverse_failures": ev.C["inverse_failures"],
                }
                rec.update(pd_diagnostics(th, Dind.xy))
                variants.append(rec)
                fc = rec["forward_certificate"]
                say(f"  {c['cid']:12} {('PD-D/' + model + ' ' + lbl)[:26]:26} {rec['status']:4d} "
                    f"{rec['nfev']:5d} {rec['loss']:13.5f} {rec['optimality']:9.2e} "
                    f"{rec['eta']:+11.7f} {rec['runtime_s']:6.2f} "
                    f"{str(rec['admissibility_v2']['safe'])[:5]:>6} "
                    f"{(fc['verdict'] + ' (' + str(fc['cells']) + ')')[:32]:>32} "
                    f"{rec['inverse']['max_roundtrip_px']:9.1e}")
            best = min((v for v in variants if v["converged"]),
                       key=lambda v: v["loss"], default=variants[0])
            c["pd"][f"PD-D/{model}"] = best
            out[f"{c['cid']}::PD-D/{model}"] = {"reported": best, "variants": variants,
                                                "selected_by": "lowest objective among converged "
                                                               "starts; no downstream quantity used"}
    return out


# =============================================================== 3. one common residual analysis


def residual_block(c, maps, say):
    """The SAME residual implementation for every map, on native and common observation sets."""
    caps = c["caps"]
    wfun = SR.balanced_weights_factory(caps, c["Dind"].sel)
    sets = {"native_B_raw_records": None, "common_indexed": c["Dind"].sel}
    out = {}
    for sname, sel in sets.items():
        for mname, th in maps.items():
            r = SR.orthogonal_residuals(caps, np.asarray(th, float), sel=sel, weights=wfun)
            if r is None:
                continue
            out[f"{sname}::{mname}"] = {
                "observation_set": sname, "map": mname,
                "n_points": r["overall"]["n"], "median_px": r["overall"]["median"],
                "rms_px": r["overall"]["rms"], "p95_px": r["overall"]["p95"],
                "max_px": r["overall"]["max"],
                "median_over_diag": r["overall"]["median_norm"],
                "rms_over_diag": r["overall"]["rms_norm"],
                "rms_px_balanced_weighted": (r["overall_weighted"] or {}).get("rms"),
                "rms_over_diag_balanced_weighted": (r["overall_weighted"] or {}).get("rms_norm"),
                "per_line_rms": r["per_line_rms"],
                "by_orientation": {k: {"n": v["n"], "median": v["median"], "rms": v["rms"]}
                                   for k, v in r["by_orientation"].items()},
                "by_region": {k: {"n": v["n"], "median": v["median"], "rms": v["rms"],
                                  "p95": v["p95"], "max": v["max"]}
                              for k, v in r["by_region"].items()},
            }
    # The established real-data zero-weight holdout: the lattice diagonal families. For PD the caveat is
    # real and stated -- the fitted homography already predicts every indexed corner, diagonals included.
    for mname, th in maps.items():
        try:
            dh = O1.diagonal_holdout(caps, np.asarray(th, float), sel=c["Dind"].sel)
            out[f"diagonal_holdout::{mname}"] = {
                "map": mname, "families": dh["families"], "points": dh["points"],
                "rms_px": dh["rms"], "max_px": dh["max"],
                "caveat": "not genuinely held out for PD-D: its homography is fitted to all indexed "
                          "corners, which include these" if mname.startswith("PD-D") else None}
        except Exception as e:                                             # noqa: BLE001
            out[f"diagonal_holdout::{mname}"] = {"map": mname, "error": repr(e)}
    return out


# =============================================================== 4. pairwise map disagreement


def pair_block(th_a, th_b, pts):
    d = MM.map_difference(th_a, th_b, grid=GRID, pts=pts)
    A = LT.U(GRID, np.asarray(th_a, float))
    B = LT.U(GRID, np.asarray(th_b, float))
    raw = np.linalg.norm(A - B, axis=1)
    H = np.asarray(d["homography"], float)
    al = np.linalg.norm(MM.apply_homography(H, A) - B, axis=1)
    reg = {}
    for rn, mask in REGION.items():
        reg[rn] = {"n": int(mask.sum()),
                   "raw_median": float(np.median(raw[mask])),
                   "aligned_median": float(np.median(al[mask])),
                   "aligned_p95": float(np.percentile(al[mask], 95)),
                   "aligned_max": float(al[mask].max())}
    return {
        "raw_full": d["raw_full"], "aligned_full": d["aligned_full"],
        "raw_hull": d.get("raw_hull"), "aligned_hull": d.get("aligned_hull"),
        "hull_coverage": d.get("hull_coverage"), "gauge_fraction": d["gauge_fraction"],
        "by_region": reg, "threshold_ladder": MM.threshold_ladder(d),
        "aligned_over_diag_hull": (d.get("aligned_hull") or {}).get("median", float("nan")) / DIAG,
    }


def pairwise(cams, all_maps, say):
    say("")
    say("=" * 118)
    say("4. FULL PAIRWISE MAP DISAGREEMENT (aligned = after removing the best planar homography)")
    say("=" * 118)
    out = {}
    for c in cams:
        maps = all_maps[c["cid"]]
        names = [m for m in METHODS if m in maps]
        M = {}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                M[f"{a} vs {b}"] = pair_block(maps[a], maps[b], c["Dind"].xy)
        out[c["cid"]] = M
        say("")
        say(f"  {c['cid']}   aligned median disagreement inside the observation hull, px "
            f"(hull coverage {list(M.values())[0]['hull_coverage']:.2f})")
        say("    " + " " * 10 + "".join(f"{n:>10}" for n in names))
        for a in names:
            row = ""
            for b in names:
                if a == b:
                    row += f"{'-':>10}"
                else:
                    k = f"{a} vs {b}" if f"{a} vs {b}" in M else f"{b} vs {a}"
                    row += f"{M[k]['aligned_hull']['median']:10.3f}"
            say(f"    {a:>10}{row}")
        say("    raw median / aligned median / aligned p95 / aligned corner median, px")
        for k, v in M.items():
            say(f"      {k:24} {v['raw_hull']['median']:9.3f} {v['aligned_hull']['median']:9.3f} "
                f"{v['aligned_hull']['p95']:9.3f} {v['by_region']['corner']['aligned_median']:9.3f}"
                f"   gaugeFrac {v['gauge_fraction']:+.3f}")
    return out


# =============================================================== 5. known length


def knownlength(xdoc_path, say):
    say("")
    say("=" * 118)
    say("5. KNOWN-LENGTH RESULTS (re-run downstream artifact; same measurements and treatment)")
    say("=" * 118)
    if not os.path.exists(xdoc_path):
        say(f"  MISSING {xdoc_path} -- not assumed")
        return {}
    d = json.load(open(xdoc_path))
    kl = d["results"].get("known_length", {})
    val = d["results"].get("validity", d["results"].get("fit_validity", {}))
    out = {"source_artifact": xdoc_path, "blocks": {}}
    for key, blk in kl.items():
        s = blk.get("summary", {})
        out["blocks"][key] = {"summary": s,
                              "reportable_candidates": blk.get("reportable_candidates"),
                              "invalid_candidates": blk.get("invalid_candidates"),
                              "contrasts": blk.get("contrasts")}
        say("")
        say(f"  {key}")
        say(f"    {'candidate':12} {'n':>5} {'MAE mm':>9} {'RMSE mm':>9} {'median mm':>10} "
            f"{'bias mm':>9} {'p95 mm':>9} {'max mm':>9} {'valid':>6}")
        for cand in METHODS:
            v = s.get(cand)
            if not isinstance(v, dict) or "mae" not in v:
                continue
            say(f"    {cand:12} {v['n']:5d} {v['mae']:9.4f} {v['rmse']:9.4f} {v['med']:10.4f} "
                f"{v['bias']:+9.4f} {v['p95']:9.4f} {v['max']:9.4f} {str(v.get('valid')):>6}")
        inval = blk.get("invalid_candidates") or []
        if inval:
            say(f"    EXCLUDED as invalid fits (fail-closed, not reported above): {inval}")
        miss = [m for m in METHODS
                if not (isinstance(s.get(m), dict) and "mae" in s.get(m, {})) and m not in inval]
        if miss:
            say(f"    absent from this block: {miss}")
        con = blk.get("contrasts") or {}
        if con:
            say("    clustered paired contrasts (replication unit = measurement timecode); negative "
                "means the FIRST candidate is more accurate")
            for ck, cv in con.items():
                if not isinstance(cv, dict) or not cv.get("available"):
                    say(f"      {ck:22} unavailable: {str(cv.get('reason', cv))[:80]}")
                    continue
                ci = cv.get("cluster_ci95") or [float("nan")] * 2
                say(f"      {ck:22} nMeas {cv.get('n_measurements', 0):4d} "
                    f"nClus {cv.get('n_clusters', 0):3d} "
                    f"mean d|err| {cv['mean_d_abs_err']:+8.4f} mm  clusterMean "
                    f"{cv['cluster_mean']:+8.4f}  95% CI [{ci[0]:+8.4f}, {ci[1]:+8.4f}]  "
                    f"{'SEPARATED' if (ci[0] > 0 or ci[1] < 0) else 'not separated from zero'}")
    return out


# =============================================================== plots


def plots(cams, pw, outdir, say):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                                 # noqa: BLE001
        say(f"  plots skipped: {e!r}")
        return []
    names = METHODS
    fig, axes = plt.subplots(2, 3, figsize=(16.5, 10.5))
    for ax, c in zip(axes.ravel(), cams):
        M = pw[c["cid"]]
        present = [n for n in names if any(n in k for k in M)]
        Z = np.full((len(present), len(present)), np.nan)
        for i, a in enumerate(present):
            for j, b in enumerate(present):
                if a == b:
                    continue
                k = f"{a} vs {b}" if f"{a} vs {b}" in M else f"{b} vs {a}"
                if k in M:
                    Z[i, j] = M[k]["aligned_hull"]["median"]
        im = ax.imshow(Z, cmap="viridis")
        ax.set_xticks(range(len(present))); ax.set_xticklabels(present, rotation=45, ha="right",
                                                              fontsize=8)
        ax.set_yticks(range(len(present))); ax.set_yticklabels(present, fontsize=8)
        for i in range(len(present)):
            for j in range(len(present)):
                if np.isfinite(Z[i, j]):
                    ax.text(j, i, f"{Z[i, j]:.2f}", ha="center", va="center", fontsize=7,
                            color="white" if Z[i, j] < np.nanmax(Z) * 0.6 else "black")
        ax.set_title(f"{c['cid']}  aligned median in-hull disagreement (px)", fontsize=9)
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("Pairwise projectively aligned map disagreement, six established cameras "
                 "(addendum 2026-07-29)", fontsize=11)
    fig.tight_layout()
    p1 = os.path.join(outdir, "real_addendum_pairwise_aligned.png")
    fig.savefig(p1, dpi=110); plt.close(fig)
    say(f"  wrote {p1}")
    return [p1]


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(OUT, "addendum-2026-07-29"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    sdreal = os.path.join(args.outdir, "sd_real_full.json")
    xdoc = os.path.join(args.outdir, "xdoc_objectives_full.json")

    W = artifacts.ArtifactWriter(
        analysis="real_addendum", script=__file__, outdir=args.outdir,
        requested_documents=[d["key"] for d in SR.DOCS],
        all_documents=[d["key"] for d in SR.DOCS],
        requested_candidates=METHODS,
        objective_versions={"residuals": "sd_real.orthogonal_residuals (one implementation for every "
                                         "map, independent of every estimator)",
                            "PD-D": "objectives.PDExact (exact projective lattice)",
                            "map difference": "mapmetrics.map_difference with geometric homography "
                                              "refinement"},
        source_files=["real_addendum.py", "sd_real.py", "xdoc_objectives.py", "lattice.py",
                      "objectives.py", "mapmetrics.py", "obj_round1.py", "downstream.py",
                      "knownlength.py", "artifacts.py"],
        calibration_node_source="vsd ZVSSCREENPOINT via nodes.py")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    say("ADDENDUM 2026-07-29 -- COMPLETING THE ESTABLISHED-REAL-DATA METHOD COMPARISON")
    say("  supersedes: 'mid lattice invalid' / 'PD-D not fitted for 2015-06-22-1 Clearwater'")
    say(f"  re-run established artifacts: {os.path.basename(sdreal)}, {os.path.basename(xdoc)}")
    say("")
    cams, frozen = freeze(say)
    pd = fit_pd(cams, say)

    prior = json.load(open(sdreal))["results"]["cameras"] if os.path.exists(sdreal) else {}
    all_maps, prov = {}, {}
    for c in cams:
        m = {"stored": c["stored"].tolist()}
        pc = prior.get(c["cid"], {}).get("fits", {})
        for k in ("B/M0", "B/M1", "SD-D/M0", "SD-D/M1"):
            if k in pc:
                m[k] = pc[k]["theta14"]
        for k, v in c.get("pd", {}).items():
            m[k] = v["theta14"]
        all_maps[c["cid"]] = m
        prov[c["cid"]] = {k: ("re-run sd_real.py (unchanged script)" if k in pc else
                              "this script" if k.startswith("PD-D") else "document")
                          for k in m}
        # cross-check: the re-run PD-D must agree with the PD-D refitted here
        for k in ("PD-D/M0", "PD-D/M1"):
            if k in pc and k in c.get("pd", {}):
                da = float(np.abs(np.asarray(pc[k]["theta14"], float)
                                  - np.asarray(c["pd"][k]["theta14"], float)).max())
                dl = abs(pc[k]["loss"] - c["pd"][k]["loss"])
                prov[c["cid"]][k] = (f"this script; re-run sd_real agrees to {da:.2e} in theta, "
                                     f"{dl:.2e} in loss")

    say("")
    say("=" * 118)
    say("3. ONE COMMON RESIDUAL IMPLEMENTATION, NATIVE AND COMMON OBSERVATION SETS")
    say("=" * 118)
    res = {}
    for c in cams:
        res[c["cid"]] = residual_block(c, all_maps[c["cid"]], say)
        say("")
        say(f"  {c['cid']}   orthogonal plumbline residual after correction, px")
        say(f"    {'set':22} {'map':10} {'n':>6} {'median':>8} {'rms':>8} {'p95':>8} {'max':>8} "
            f"{'rms/diag':>9} {'wRMS':>8} {'lineRMSmed':>11} {'central':>8} {'edge':>8} {'corner':>8}")
        for k in sorted(res[c["cid"]]):
            v = res[c["cid"]][k]
            if k.startswith("diagonal_holdout"):
                continue
            br = v["by_region"]
            say(f"    {v['observation_set']:22} {v['map']:10} {v['n_points']:6d} "
                f"{v['median_px']:8.4f} {v['rms_px']:8.4f} {v['p95_px']:8.4f} {v['max_px']:8.3f} "
                f"{v['rms_over_diag']:9.2e} {(v['rms_px_balanced_weighted'] or float('nan')):8.4f} "
                f"{v['per_line_rms']['median']:11.4f} "
                f"{br.get('central', {}).get('rms', float('nan')):8.4f} "
                f"{br.get('edge', {}).get('rms', float('nan')):8.4f} "
                f"{br.get('corner', {}).get('rms', float('nan')):8.4f}")
        say(f"    diagonal-family holdout (zero weight for row/column objectives), rms px:")
        for k in sorted(res[c["cid"]]):
            if not k.startswith("diagonal_holdout"):
                continue
            v = res[c["cid"]][k]
            if "error" in v:
                say(f"      {v['map']:10} error {v['error'][:60]}")
                continue
            say(f"      {v['map']:10} families {v['families']:3d} points {v['points']:5d} "
                f"rms {v['rms_px']:8.4f} max {v['max_px']:8.3f}"
                + ("   [not genuinely held out for PD-D]" if v.get("caveat") else ""))

    pw = pairwise(cams, all_maps, say)
    kl = knownlength(xdoc, say)
    figs = plots(cams, pw, args.outdir, say)

    R = {"superseded_claims": [
            "2015-06-22-1 Clearwater ('mid') has an inconsistent plumbline lattice",
            "PD-D cannot be fitted for mid/Left or mid/Right",
            "the mid cameras contribute no PD-D evidence to the method comparison"],
         "frozen_inputs": frozen, "pd_fits": pd, "map_provenance": prov,
         "maps": all_maps, "residuals": res, "pairwise_map_disagreement": pw,
         "known_length": kl, "figures": figs,
         "reused_artifacts": {"sd_real": sdreal, "xdoc_objectives": xdoc}}
    for spec in SR.DOCS:
        W.document_started(spec["key"], doc_key=spec["key"])
        W.document_completed(spec["key"], completed_candidates=METHODS)
    path = W.write(R)
    say("")
    say(f"  wrote {path}   [{time.time() - t0:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
