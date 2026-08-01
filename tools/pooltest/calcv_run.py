#!/usr/bin/env python3
"""Driver for the calibration-only operational-selection study. ANALYSIS ONLY.

Runs, per document and camera: grouped held-out-line cross-validation, eta identifiability and
multistart stability, leave-one-line-group-out variation in eta, induced-map stability, and the M0-null
and eta-injection simulations. Then evaluates provisional rule structures whose thresholds come only
from calibration repeatability, numerical tolerance, or the prespecified null -- never from known-length
outcomes.

Writes analysis-output/calcv_<label>.{json,log}. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np

import harness_import

L = harness_import.load
DS = L("downstream")
LT = L("lattice")
OB = L("objectives")
kl = L("knownlength")
CD = L("cloud_downstream")
CV = L("calcv")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
POOL = os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                        "2012-01-31_PoolTest_2026_Reanalysis.vsd")

# Every recording with validation ground truth, cloud or conventional. `role` keeps the frozen
# corpus.py manifest distinct from the explicitly analysed out-of-corpus document.
RECORDINGS = [
    {"key": "pool", "vsd": POOL, "focal": None, "role": "corpus", "unit_mm": 1000.0,
     "types": kl.POOL_CONVENTIONAL_TYPES},
    {"key": "8mm", "vsd": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"), "focal": 8,
     "role": "corpus", "unit_mm": 1.0, "types": None},
    {"key": "2015-07-10-1", "vsd": os.path.join(DM, "2015-07-10-1 Chena.vsd"), "focal": 10,
     "role": "corpus", "unit_mm": 1.0, "types": None},
    {"key": "2015-06-22-1", "vsd": os.path.join(DM, "2015-06-22-1 Clearwater.vsd"), "focal": 13,
     "role": "corpus", "unit_mm": 1.0, "types": None},
    {"key": "2016-06-09-1", "vsd": os.path.join(DM, "2016-06-09-1 Clearwater.vsd"), "focal": 17,
     "role": "explicit (NOT in corpus.py)", "unit_mm": 1.0, "types": None},
]


def gate(th, node_pts):
    return CD._gate_map(th, node_pts)


def fit_fn(D, est, model, warm):
    """The production-faithful gated path: M0 cold, M1 warm-started from the accepted M0 with eta = 0."""
    if est == "B":
        if model == "M0":
            r = OB.fit(D, "B", "M0", warm=False, max_nfev=3000)
            return np.array(r["theta14"], float), {"loss": r["loss"], "status": r["status"]}
        fr = OB.MODELS["M1"]
        x0 = np.asarray(warm, float).copy(); x0[13] = 0.0
        r = OB.fit(D, "B", "M1", x0_model=x0[fr] / OB.SCALE14[fr], warm=False, max_nfev=3000)
        return np.array(r["theta14"], float), {"loss": r["loss"], "status": r["status"]}
    if model == "M0":
        ev = OB.PDExact(D, "M0")
        b = OB.fit(D, "B", "M0", warm=False, max_nfev=3000)
        res, _ = ev.fit(ev.init_dlt(np.array(b["theta14"], float)))
        return ev.theta(res.x), {"loss": float(2 * res.cost), "status": int(res.status)}
    ev = OB.PDExact(D, "M1")
    seed = np.asarray(warm, float).copy(); seed[13] = 0.0
    res, _ = ev.fit(ev.init_dlt(seed))
    return ev.theta(res.x), {"loss": float(2 * res.cost), "status": int(res.status)}


def map_displacement(th_a, th_b, steps=90):
    gx, gy = np.meshgrid(np.linspace(0.5, LT.FRAME_W - 0.5, steps),
                         np.linspace(0.5, LT.FRAME_H - 0.5, steps))
    g = np.stack([gx.ravel(), gy.ravel()], axis=1)
    ua, ub = LT.U(g, np.asarray(th_a, float)), LT.U(g, np.asarray(th_b, float))
    m = np.linalg.norm(ub - ua, axis=1)
    ok = np.isfinite(m)
    return {"median_px": float(np.median(m[ok])), "p95_px": float(np.percentile(m[ok], 95)),
            "max_px": float(m[ok].max())}


# ============================================================== null and injection


def synth_capture(C, theta_truth, rng, sigma_px):
    """Rebuild one capture's observations from the TRUE map, preserving its actual line design.

    The design -- which lines exist, which observations lie on them, and where they sit in the image --
    is taken from the real capture. Only the observations are regenerated: the ideal straight line
    through each real line's undistorted points is re-sampled and pushed back through the inverse of the
    truth map, then localization noise is added in raw pixels.
    """
    D = __import__("copy").copy(C)
    u = LT.U(C.xy, np.asarray(theta_truth, float))
    u2 = u.copy()
    for ln in C.lines:
        m = list(ln["members"])
        if len(m) < 3:
            continue
        pts = u[m]
        c = pts.mean(0)
        A = pts - c
        _, _, Vt = np.linalg.svd(A, full_matrices=False)
        d = Vt[0]
        t = A @ d
        u2[m] = c + np.outer(t, d)                        # exactly straight in the undistorted plane
    raw, conv, _ = LT.inv_U(u2, np.asarray(theta_truth, float))
    if not np.all(conv):
        return None
    D.xy = raw + rng.normal(0.0, sigma_px, size=raw.shape)
    return D


def null_and_injection(say, caps, node_pts, sigma_px, etas, n_rep, seed):
    """M0 null and eta-injection, refit through the deterministic path. Conditional on this noise model."""
    rng = np.random.default_rng(seed)
    base = OB.fit(OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0), "B", "M0",
                  warm=False, max_nfev=3000)
    th_m0 = np.array(base["theta14"], float)
    out = {"noise_sigma_px": sigma_px, "n_replicates": n_rep,
           "truth_M0_theta14": th_m0.tolist(), "cases": []}
    for eta_true in etas:
        th_t = th_m0.copy(); th_t[13] = float(eta_true)
        recs = []
        for rep in range(n_rep):
            sc = [synth_capture(C, th_t, rng, sigma_px) for C in caps]
            if any(s is None for s in sc):
                continue
            try:
                Dl = OB.Dataset(sc, require_indexed=False, min_inc=1, kappa=3.0)
                if Dl.n < 20:
                    continue
                t0, d0 = fit_fn(Dl, "B", "M0", None)
                t1, d1 = fit_fn(Dl, "B", "M1", t0)
            except Exception:                                                # noqa: BLE001
                continue
            g1 = gate(t1, node_pts)
            improves = bool(d1["loss"] <= d0["loss"] + 1e-9 * max(abs(d0["loss"]), 1.0))
            cvres = CV.grouped_cv(say, sc, node_pts, gate, fit_fn, min_pts=5,
                                  max_folds=12, estimators=("B",))
            s = CV.summarize_cv(cvres, "B")
            recs.append({"eta_hat": float(t1[13]), "gate_ok": bool(g1["ok"]),
                         "improves": improves,
                         "accepted": bool(g1["ok"] and improves),
                         "cv_signed_mean_d_rms_px": s.get("signed_mean_d_rms_px"),
                         "cv_lines_improved": s.get("lines_improved"),
                         "cv_n_lines": s.get("n_lines")})
        if not recs:
            out["cases"].append({"eta_true": float(eta_true), "n": 0})
            continue
        eh = np.array([r["eta_hat"] for r in recs])
        cvd = np.array([r["cv_signed_mean_d_rms_px"] for r in recs
                        if r["cv_signed_mean_d_rms_px"] is not None], float)
        out["cases"].append({
            "eta_true": float(eta_true), "n": len(recs),
            "eta_hat_mean": float(eh.mean()), "eta_hat_sd": float(eh.std(ddof=1))
            if len(eh) > 1 else float("nan"),
            "eta_sign_correct_frac": (float(np.mean(np.sign(eh) == np.sign(eta_true)))
                                      if eta_true != 0 else None),
            "accepted_frac": float(np.mean([r["accepted"] for r in recs])),
            "gate_failure_frac": float(np.mean([not r["gate_ok"] for r in recs])),
            "cv_signed_mean_d_rms_px_mean": float(cvd.mean()) if cvd.size else float("nan"),
            "cv_signed_mean_d_rms_px_p95": float(np.percentile(cvd, 95)) if cvd.size else float("nan"),
            "cv_improves_frac": float(np.mean(cvd < 0)) if cvd.size else float("nan"),
            "records": recs})
    out["caveat"] = ("all spread here is CONDITIONAL on this localization-noise and line-design model; "
                     "it is not sampling uncertainty over camera recordings")
    return out


# ============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="v1")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--docs", nargs="*", default=None)
    ap.add_argument("--estimators", nargs="*", default=["B", "PD-D"])
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--sigma-px", type=float, default=0.35)
    ap.add_argument("--null-reps", type=int, default=6)
    ap.add_argument("--inject-etas", nargs="*", type=float,
                    default=[0.0, 0.004, 0.010, 0.017, -0.010])
    ap.add_argument("--skip-sim", action="store_true")
    args = ap.parse_args()
    stem = f"calcv_{args.label}"
    log = open(os.path.join(args.outdir, stem + ".log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    R = {"documents": {}, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "operational_decision": {
             "granularity": "ONE distortion map per VSCalibration, and one VSCalibration per video clip",
             "evidence": "VSCalibration.h stores distortionCenterX/Y and K1..K7, P1..P4 -- 13 scalars "
                         "per calibration, with no eta field and no per-measurement or per-region "
                         "alternative. Selection is therefore DOCUMENT-WIDE PER CAMERA and is made "
                         "before any measurement click exists.",
             "consequence": "measurement-specific depth, triangulation angle, support class and click "
                             "location are NOT selection-time predictors"}}
    say("=" * 112)
    say("CALIBRATION-ONLY OPERATIONAL-SELECTION STUDY")
    say("=" * 112)
    say(f"  operational granularity: {R['operational_decision']['granularity']}")
    say(f"  {R['operational_decision']['consequence']}")

    recs = [r for r in RECORDINGS if args.docs is None or r["key"] in args.docs]
    for spec in recs:
        if not os.path.exists(spec["vsd"]):
            say(f"\n  {spec['key']}: file not found, skipped")
            continue
        vsd = spec["vsd"]
        cals = DS.load_bound_cals(vsd)
        clips = sorted(cals)
        sha = cals[clips[0]]["identity"].doc_sha256
        D0 = kl.load(vsd, conventional_types=spec["types"], unit_mm=spec["unit_mm"])
        say(f"\n{'=' * 112}\n  {spec['key']}  (nominal {spec['focal']} mm, {spec['role']})")
        say(f"  SHA-256 {sha}")
        say(f"  validation families present: "
            f"{len(D0['conventional'])} conventional, {len(D0['clouds'])} clouds\n{'=' * 112}")
        docR = R["documents"][spec["key"]] = {
            "doc_sha256": sha, "focal_mm_metadata": spec["focal"], "role": spec["role"],
            "n_conventional": len(D0["conventional"]), "n_clouds": len(D0["clouds"]),
            "cameras": {}}
        for clip in clips:
            caps = LT.load_captures(vsd, clip)
            node_pts = np.array([[x, y] for x, y, _, _ in cals[clip]["front"] + cals[clip]["back"]],
                                float)
            Dfull = OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
            Dind = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
            contra = sum(C.notes["index_contradictions"] for C in caps)
            say(f"\n    {clip}: {len(caps)} capture(s), {Dfull.n} observations on {Dfull.nline} lines "
                f"(indexed subset {Dind.n} on {Dind.nline}), contradictions {contra}")
            camR = docR["cameras"][clip] = {
                "n_obs_all": int(Dfull.n), "n_lines_all": int(Dfull.nline),
                "n_obs_indexed": int(Dind.n), "n_lines_indexed": int(Dind.nline),
                "index_contradictions": int(contra)}

            # ---- full-data fits, for identifiability
            th0_b, d0_b = fit_fn(Dfull, "B", "M0", None)
            th1_b, d1_b = fit_fn(Dfull, "B", "M1", th0_b)
            g0, g1 = gate(th0_b, node_pts), gate(th1_b, node_pts)
            say(f"      full-data B: M0 loss {d0_b['loss']:.5f} gate {'ok' if g0['ok'] else 'REJECT'}; "
                f"M1 loss {d1_b['loss']:.5f} eta {th1_b[13]:+.7f} "
                f"gate {'ok' if g1['ok'] else 'REJECT'}")
            camR["full_fit"] = {"B/M0": {"loss": d0_b["loss"], "gate": g0},
                                "B/M1": {"loss": d1_b["loss"], "gate": g1,
                                         "eta": float(th1_b[13])},
                                "in_sample_note": "M1 nests M0 so this improvement is expected by "
                                                  "construction and is NOT evidence of generalization"}
            camR["map_displacement_M1_vs_M0"] = map_displacement(th0_b, th1_b)

            # ---- identifiability and stability
            ident = CV.eta_identifiability(Dfull, th1_b, node_pts)
            ms = CV.multistart_eta(Dfull, th0_b, n=5, spread=0.02)
            say(f"      eta identifiability: profile curvature {ident['profile_curvature']:.4g}, "
                f"convex {ident['profile_is_convex_at_optimum']}, J'J condition "
                f"{ident['JtJ_condition']:.3e}, bound proximity {ident['bound_proximity']:.4f}")
            if "max_abs_corr_with_other_params" in ident:
                say(f"      eta max |correlation| with another free parameter "
                    f"{ident['max_abs_corr_with_other_params']:.4f} "
                    f"(worst partner theta index {ident['worst_partner_free_index']})")
            say(f"      multistart: {ms['n_converged']}/{ms['n_started']} converged, eta spread "
                f"{ms['eta_spread']:.3e}, loss spread {ms['loss_spread']:.3e}, distinct basins "
                f"{ms['distinct_basins']}")
            camR["identifiability"] = ident
            camR["multistart"] = ms

            # ---- grouped held-out-line CV
            say(f"      grouped held-out-line CV ({', '.join(args.estimators)})")
            cv = CV.grouped_cv(say, caps, node_pts, gate, fit_fn, min_pts=5,
                               max_folds=args.max_folds, estimators=tuple(args.estimators))
            camR["cv"] = {"n_folds": cv["n_folds"], "fold_definition": cv["fold_definition"],
                          "score": cv["score"],
                          "gate_or_objective_rejections": cv["gate_or_objective_rejections"],
                          "fold_failures": cv["fold_failures"], "per_estimator": {}}
            for est in args.estimators:
                s = CV.summarize_cv(cv, est)
                camR["cv"]["per_estimator"][est] = s
                if not s.get("n_lines"):
                    say(f"        {est}: no scorable folds")
                    continue
                say(f"        {est}: {s['n_lines']} lines; equal-line mean straightness RMS "
                    f"{s['equal_line_mean_M0_rms_px']:.4f} -> {s['equal_line_mean_M1_rms_px']:.4f} px; "
                    f"p95 {s['equal_line_p95_M0_px']:.4f} -> {s['equal_line_p95_M1_px']:.4f} px")
                say(f"          signed mean change {s['signed_mean_d_rms_px']:+.5f} px "
                    f"({s['signed_mean_d_rms_permille']:+.5f} per-mille of frame diagonal); "
                    f"lines improved {s['lines_improved']}/{s['n_lines']}")
                say(f"          worst-line deterioration {s['worst_line_deterioration_px']:+.5f} px, "
                    f"best improvement {s['best_line_improvement_px']:+.5f} px, top-1 share of total "
                    f"improvement {s['concentration_top1_share']:.3f}")
                say(f"          transactional mean change (M0 stands when M1 is rejected) "
                    f"{s['transactional_mean_d_rms_px']:+.5f} px")
            # leave-one-line-group-out variation in eta, from the CV folds themselves
            etas = [f["candidates"]["B"]["M1"]["eta"] for f in cv["folds"]
                    if "B" in f["candidates"] and "M1" in f["candidates"]["B"]]
            if etas:
                e = np.array(etas)
                camR["eta_leave_one_line_out"] = {
                    "n": int(e.size), "mean": float(e.mean()), "sd": float(e.std(ddof=1))
                    if e.size > 1 else float("nan"),
                    "min": float(e.min()), "max": float(e.max()),
                    "range_over_mean": float((e.max() - e.min()) / abs(e.mean()))
                    if e.mean() else float("nan"),
                    "sign_stable": bool(np.all(np.sign(e) == np.sign(e[0])))}
                say(f"      eta across leave-one-line-out folds: mean {e.mean():+.7f}, sd "
                    f"{e.std(ddof=1) if e.size > 1 else float('nan'):.2e}, range "
                    f"[{e.min():+.7f}, {e.max():+.7f}], sign stable "
                    f"{camR['eta_leave_one_line_out']['sign_stable']}")
            say(f"      [{time.time() - t0:.1f}s]")

        # ---- null and injection, once per document on its first camera's design
        if not args.skip_sim:
            clip0 = clips[0]
            caps0 = LT.load_captures(vsd, clip0)
            node0 = np.array([[x, y] for x, y, _, _ in cals[clip0]["front"] + cals[clip0]["back"]],
                             float)
            say(f"\n    NULL AND INJECTION on {clip0}'s actual line design "
                f"(sigma {args.sigma_px} px, {args.null_reps} replicates per case)")
            sim = null_and_injection(say, caps0, node0, args.sigma_px, args.inject_etas,
                                     args.null_reps, seed=20260730)
            docR["simulation"] = sim
            say(f"      {'eta_true':>9} {'n':>3} {'eta_hat mean':>13} {'eta_hat sd':>11} "
                f"{'signOK':>7} {'accepted':>9} {'gateFail':>9} {'cv d_rms mean':>14} "
                f"{'cv improves':>12}")
            for c in sim["cases"]:
                if not c.get("n"):
                    say(f"      {c['eta_true']:+9.4f} {0:>3}  (no usable replicates)")
                    continue
                so = ("-" if c["eta_sign_correct_frac"] is None
                      else f"{c['eta_sign_correct_frac']:.2f}")
                say(f"      {c['eta_true']:+9.4f} {c['n']:>3} {c['eta_hat_mean']:+13.7f} "
                    f"{c['eta_hat_sd']:11.2e} {so:>7} {c['accepted_frac']:9.2f} "
                    f"{c['gate_failure_frac']:9.2f} {c['cv_signed_mean_d_rms_px_mean']:+14.6f} "
                    f"{c['cv_improves_frac']:12.2f}")
            say(f"      {sim['caveat']}")
            say(f"      [{time.time() - t0:.1f}s]")

    p = os.path.join(args.outdir, stem + ".json")
    json.dump(R, open(p, "w"), indent=1, default=str)
    say(f"\n  wrote {os.path.basename(p)}   [{time.time() - t0:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
