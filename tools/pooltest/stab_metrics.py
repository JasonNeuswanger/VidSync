#!/usr/bin/env python3
"""Model-stability round, part 3: production-faithful measurement stability across solver endpoints.

Every candidate is a pairing of one Left-camera endpoint cluster with one Right-camera endpoint
cluster of the same model -- a solver realization of that model. For each, the ENTIRE downstream
calibration is rebuilt from raw frame-node clicks through oracle.cpp (front homography uncorrected,
back surface in the four-iteration refractive fixed point, camera position recomputed every
iteration) and all 149 measured points are re-triangulated with parity.triangulate. Nothing reuses
the document's stored matrices.

The endpoints are deliberately chosen sensitivity runs, not independent statistical replicates.
Spread is reported as median, range and interquartile range; no sampling p-values, confidence
intervals or binomial probabilities are attached to any of it.

Writes analysis-output/stab_metrics.json. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import csv
import importlib.util
import itertools
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
ORIGINAL_14 = [184, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 201]
MAXPAIRS = 14


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
nd = L("nodes")
kl = L("knownlength")
st = L("stage2")
P2 = L("parity_step2")
P5 = L("parity_step5")
FK = L("fisheye_knownlength_analysis")
DG = L("stab_degeneracy")
SCALE14 = P5.SCALE14
METRICS = ["conv42_mae", "conv42_med", "conv14_mae", "cloud_equal_pair_mae",
           "rigid_rms_mean", "source_balanced"]
MLABEL = {"conv42_mae": "conventional 42 MAE", "conv42_med": "conventional 42 median",
          "conv14_mae": "original 14 MAE", "cloud_equal_pair_mae": "cloud-equal pair MAE",
          "rigid_rms_mean": "equal-cloud rigid RMS", "source_balanced": "source-balanced"}


def spread(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], float)
    if v.size == 0:
        return {k: float("nan") for k in ("n", "median", "min", "max", "range", "q1", "q3", "iqr")}
    q1, q3 = np.percentile(v, [25, 75])
    return {"n": int(v.size), "median": float(np.median(v)), "min": float(v.min()),
            "max": float(v.max()), "range": float(v.max() - v.min()),
            "q1": float(q1), "q3": float(q3), "iqr": float(q3 - q1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--fits", default=os.path.join(HERE, "analysis-output", "stab_fits.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "stab_metrics.json"))
    args = ap.parse_args()
    say = print
    t0 = time.time()

    say("=" * 104)
    say("MODEL-STABILITY ROUND, PART 3: PRODUCTION-FAITHFUL MEASUREMENT STABILITY")
    say("=" * 104)
    say("  every candidate rebuilds homographies, refraction and camera position from raw node")
    say("  clicks; endpoints are sensitivity runs, so spread is descriptive only")

    fits = json.load(open(args.fits))
    cals = st.load_cal(args.vsd)
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)
    for clip, c in cals.items():
        nd.assert_node_orientation(db, c["pk"], c["s2f"], c["s2b"], c["dist"], clip)
    db.close()
    D = kl.load(args.vsd)
    conv, cpts, cpairs, clouds = (D["conventional"], D["cloud_points"], D["cloud_pairs"],
                                  D["clouds"])
    clicks = D["clicks"]
    cnames = sorted(clouds)
    io = np.array([r["event"] in ORIGINAL_14 for r in conv])
    tcset = sorted({r["tc"] for r in conv})
    plum = {clip: F.Plumblines(P2.load_lines(args.vsd, clip)[0]) for clip in CLIPS}

    def measure(th_by_clip):
        cams = {}
        for clip in CLIPS:
            cams[clip] = FK.build_cam(cals[clip], list(th_by_clip[clip]))
        rec = {}
        need = {pk for r in conv for pk in r["pks"]} | {p["pk"] for p in cpts}
        for pk in need:
            r = FK.reconstruct(pk, cams, clicks)
            if r is not None:
                rec[pk] = r
        ce, pe = [], []
        for r in conv:
            a, b = r["pks"]
            ce.append(float(np.linalg.norm(rec[a]["X"] - rec[b]["X"])) - r["true"]
                      if a in rec and b in rec else float("nan"))
        for q in cpairs:
            a, b = q["pks"]
            pe.append(float(np.linalg.norm(rec[a]["X"] - rec[b]["X"])) - q["true"]
                      if a in rec and b in rec else float("nan"))
        ce, pe = np.array(ce), np.array(pe)
        rigid = {}
        for cn in cnames:
            pts = clouds[cn]
            q2 = np.array([p["mm"] for p in pts], float)
            X = np.array([rec[p["pk"]]["X"] for p in pts], float)
            rigid[cn] = FK.shape_report(q2, X)["rms"]
        c42 = FK.stats(ce); c14 = FK.stats(ce[io])
        cm = [float(np.mean([abs(pe[k]) for k, q in enumerate(cpairs) if q["cloud"] == cn]))
              for cn in cnames]
        pm = [float(np.mean([abs(ce[k]) for k, r in enumerate(conv) if r["tc"] == tc]))
              for tc in tcset]
        return {"conv42_mae": c42["mae"], "conv42_med": c42["med"], "conv14_mae": c14["mae"],
                "cloud_equal_pair_mae": float(np.mean(cm)),
                "rigid_rms_mean": float(np.mean([rigid[cn] for cn in cnames])),
                "source_balanced": float(np.mean(pm + cm)),
                "rigid_per_cloud": rigid, "n_reconstructed": len(rec)}

    # Admissibility, one rule for the whole round: on the physical branch (stab_degeneracy), passing
    # the shipped production gate, and within 2x of the model's best admissible SSE. The first drops
    # collapsed and large-|eta| maps the shipped gate fails to reject; the second drops what
    # production would refuse to store; the third drops gross convergence failures while keeping
    # genuine alternative basins, which sit at 1.09x to 1.27x. Nothing is dropped silently.
    excluded = []

    out = {"models": {}, "candidates": {}, "excluded": excluded,
           "admissibility": "physical branch AND shipped gate AND SSE <= 2x model best"}
    for model in ("M0", "M1", "FULL13", "F13eta"):
        cl = {}
        for clip in CLIPS:
            allc = fits["models"][model]["clusters"][clip]
            eps = fits["models"][model][clip]
            ok = [c for c in allc
                  if DG.on_physical_branch(c["rms"], c["eta"])
                  and eps[c["representative"]]["gate_ok"]]
            b = min((c["sse"] for c in ok), default=float("inf"))
            keep = [c for c in ok if c["sse"] <= 2.0 * b]
            for c in allc:
                if c in keep:
                    continue
                ep = eps[c["representative"]]
                why = ("off physical branch" if not DG.on_physical_branch(c["rms"], c["eta"])
                       else ("gate rejects" if not ep["gate_ok"] else "beyond 2x the best SSE"))
                excluded.append({"model": model, "clip": clip, "cluster": c["index"],
                                 "sse": c["sse"], "rms": c["rms"], "eta": c["eta"],
                                 "reason": why, "seeds": c["seeds"]})
                say(f"    EXCLUDED {model}/{clip} cluster {c['index']}: SSE {c['sse']:.4g}, "
                    f"RMS {c['rms']:.4g} px, eta {c['eta']:+.6f} -- {why}")
            cl[clip] = keep
        combos = list(itertools.product(range(len(cl[CLIPS[0]])), range(len(cl[CLIPS[1]]))))
        # prioritize best-best, then by combined SSE, and cap the work
        combos.sort(key=lambda ij: cl[CLIPS[0]][ij[0]]["sse"] + cl[CLIPS[1]][ij[1]]["sse"])
        dropped = max(0, len(combos) - MAXPAIRS)
        combos = combos[:MAXPAIRS]
        say(f"\n[{model}] {len(cl[CLIPS[0]])} Left cluster(s) x {len(cl[CLIPS[1]])} Right "
            f"cluster(s) -> {len(combos)} candidate(s) rebuilt"
            + (f"; {dropped} higher-SSE combination(s) NOT run, so this envelope is a lower bound "
               f"on the model's spread" if dropped else ""))
        rows = []
        for i, j in combos:
            th = {}
            sse = {}
            for clip, ci in ((CLIPS[0], i), (CLIPS[1], j)):
                c = cl[clip][ci]
                ep = fits["models"][model][clip][c["representative"]]
                th[clip] = np.array(ep["theta14"], float)
                sse[clip] = ep["sse"]
            m = measure(th)
            m.update(model=model, left_cluster=cl[CLIPS[0]][i]["index"],
                     right_cluster=cl[CLIPS[1]][j]["index"],
                     sse_L=sse[CLIPS[0]], sse_R=sse[CLIPS[1]],
                     rms_L=math.sqrt(sse[CLIPS[0]] / plum[CLIPS[0]].n),
                     rms_R=math.sqrt(sse[CLIPS[1]] / plum[CLIPS[1]].n),
                     eta_L=float(th[CLIPS[0]][13]), eta_R=float(th[CLIPS[1]][13]),
                     historical=False)
            rows.append(m)
            say(f"    L{i}/R{j}  plumb {m['rms_L']:.4f}/{m['rms_R']:.4f} px  eta "
                f"{m['eta_L']:+.6f}/{m['eta_R']:+.6f}  conv42 {m['conv42_mae']:7.4f}  "
                f"med {m['conv42_med']:7.4f}  pair {m['cloud_equal_pair_mae']:7.4f}  "
                f"rigid {m['rigid_rms_mean']:7.4f}  srcbal {m['source_balanced']:7.4f}")
        out["candidates"][model] = rows
        out["models"][model] = {k: spread([r[k] for r in rows]) for k in METRICS}
        out["models"][model]["rigid_per_cloud"] = {
            cn: spread([r["rigid_per_cloud"][cn] for r in rows]) for cn in cnames}
        out["models"][model]["n_candidates"] = len(rows)
        out["models"][model]["dropped_combinations"] = dropped

    # the historical previous in-app endpoint, metrics only, from the cached summary
    hist = None
    csvp = os.path.join(HERE, "analysis-output", "fisheye_model_summary.csv")
    if os.path.exists(csvp):
        for r in csv.DictReader(open(csvp)):
            if r["model"] == "stored":
                hist = {"model": "FULL13", "historical": True,
                        "conv42_mae": float(r["conv42_mae"]), "conv42_med": float(r["conv42_med"]),
                        "conv14_mae": float(r["conv14_mae"]),
                        "cloud_equal_pair_mae": float(r["cloud_equal_mae"]),
                        "rigid_rms_mean": float(r["rigid_rms_cloud_mean"]),
                        "source_balanced": float(r["source_balanced_mae"]),
                        "rigid_per_cloud": {cn: float(r[f"rigid_rms_{cn.replace(' ', '')}"])
                                            for cn in cnames},
                        "rms_L": float("nan"), "rms_R": float("nan"),
                        "sse_L": float("nan"), "sse_R": float("nan"),
                        "eta_L": 0.0, "eta_R": 0.0, "left_cluster": -1, "right_cluster": -1,
                        "n_reconstructed": -1}
    if hist is not None:
        out["candidates"]["FULL13"].append(hist)
        say(f"\n  historical previous in-app endpoint added to the FULL13 envelope from the cached")
        say(f"  summary (coefficients unrecoverable, so no plumbline residual or map for it): "
            f"conv42 {hist['conv42_mae']:.4f}, pair {hist['cloud_equal_pair_mae']:.4f}, "
            f"rigid {hist['rigid_rms_mean']:.4f}, srcbal {hist['source_balanced']:.4f}")
        out["models"]["FULL13_with_historical"] = {
            k: spread([r[k] for r in out["candidates"]["FULL13"]]) for k in METRICS}

    # ------------------------------------------------------------------ summary
    say(f"\n{'=' * 104}")
    say(f"  SPREAD ACROSS SOLVER ENDPOINTS, per model (mm). Sensitivity runs, not replicates.")
    say(f"{'=' * 104}")
    for k in METRICS:
        say(f"\n    {MLABEL[k]}")
        say(f"      {'model':22} {'n':>3} {'median':>9} {'min':>9} {'max':>9} {'range':>9} "
            f"{'IQR':>9}")
        for model in ("M0", "M1", "FULL13", "F13eta", "FULL13_with_historical"):
            if model not in out["models"]:
                continue
            s = out["models"][model][k] if k in out["models"][model] else None
            if s is None:
                continue
            say(f"      {model:22} {s['n']:3d} {s['median']:9.4f} {s['min']:9.4f} {s['max']:9.4f} "
                f"{s['range']:9.4f} {s['iqr']:9.4f}")

    say(f"\n    per-cloud rigid RMS spread (median [min, max] mm)")
    say(f"      {'model':10} " + " ".join(f"{cn:>26}" for cn in cnames))
    for model in ("M0", "M1", "FULL13", "F13eta"):
        cells = []
        for cn in cnames:
            s = out["models"][model]["rigid_per_cloud"][cn]
            cells.append(f"{s['median']:8.3f} [{s['min']:7.3f},{s['max']:7.3f}]")
        say(f"      {model:10} " + " ".join(f"{c:>26}" for c in cells))

    # ------------------------------------------------------------------ SSE vs metric
    say(f"\n  RELATIONSHIP BETWEEN PLUMBLINE SSE AND MEASUREMENT ERROR, within model")
    say(f"    Pearson and Spearman over this small, deliberately selected endpoint set. Descriptive")
    say(f"    only: no causal or population claim follows from it.")
    out["sse_vs_metric"] = {}
    for model in ("M0", "M1", "FULL13", "F13eta"):
        rows = [r for r in out["candidates"][model] if not r.get("historical")]
        if len(rows) < 3:
            say(f"    {model:8} only {len(rows)} candidate(s); no correlation reported")
            continue
        tot = np.array([r["sse_L"] + r["sse_R"] for r in rows], float)
        line = []
        out["sse_vs_metric"][model] = {}
        for k in METRICS:
            y = np.array([r[k] for r in rows], float)
            if tot.std() == 0 or y.std() == 0:
                pr = sp = float("nan")
            else:
                pr = float(np.corrcoef(tot, y)[0, 1])
                rx = np.argsort(np.argsort(tot)); ry = np.argsort(np.argsort(y))
                sp = float(np.corrcoef(rx, ry)[0, 1])
            out["sse_vs_metric"][model][k] = {"pearson": pr, "spearman": sp, "n": len(rows)}
            line.append(f"{k.split('_')[0]} r={pr:+.2f}/rho={sp:+.2f}")
        say(f"    {model:8} n={len(rows)}  " + "  ".join(line))

    # ------------------------------------------------------------------ envelope comparison
    say(f"\n  M1 AND F13eta AGAINST THE EMPIRICAL FULL-13 SENSITIVITY ENVELOPE")
    say(f"    Empirical comparison over the endpoints actually run; not a probability statement.")
    envrows = out["candidates"]["FULL13"]
    out["envelope_comparison"] = {}
    for k in METRICS:
        env = np.array([r[k] for r in envrows], float)
        best, med, worst = float(env.min()), float(np.median(env)), float(env.max())
        say(f"\n    {MLABEL[k]}: full-13 envelope best {best:.4f}, median {med:.4f}, "
            f"worst {worst:.4f} (n={len(env)})")
        out["envelope_comparison"][k] = {"env_best": best, "env_median": med, "env_worst": worst,
                                         "env_n": len(env), "models": {}}
        for model in ("M0", "M1", "F13eta"):
            v = np.array([r[k] for r in out["candidates"][model]], float)
            nb = int((v < best).sum()); nm = int((v < med).sum()); nw = int((v < worst).sum())
            say(f"      {model:8} n={len(v)}: median {float(np.median(v)):.4f}; beats envelope "
                f"best in {nb}/{len(v)}, median in {nm}/{len(v)}, worst in {nw}/{len(v)}; "
                f"median minus envelope best {float(np.median(v)) - best:+.4f}, minus envelope "
                f"median {float(np.median(v)) - med:+.4f}")
            out["envelope_comparison"][k]["models"][model] = {
                "n": len(v), "median": float(np.median(v)),
                "beats_env_best": nb, "beats_env_median": nm, "beats_env_worst": nw,
                "median_minus_env_best": float(np.median(v)) - best,
                "median_minus_env_median": float(np.median(v)) - med}

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}   [{time.time() - t0:.0f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
