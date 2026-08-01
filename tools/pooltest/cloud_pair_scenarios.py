#!/usr/bin/env python3
"""Recompute cloud-balanced estimands under named exclusion scenarios, from a persisted pairs CSV.

WHY THIS IS SOUND WITHOUT REFITTING. Cloud points are external ground truth, never calibration inputs:
the distortion maps are fitted to plumblines alone. Removing a cloud point therefore cannot change any
map, and removing it from the scoring set removes exactly the pairs incident on it. Every candidate keeps
the identical pair set within a scenario, so the paired contrasts remain paired.

THREE CATEGORIES OF EXCLUSION, KEPT DISTINCT. Conflating them is how a sensitivity analysis turns into a
result.

  DATA DEFECT -- a point whose recorded grid label and whose click disagree by an integer number of grid
  rows. This is an internal inconsistency in the ground truth, demonstrable without reference to any
  candidate map, and it is NOT a threshold choice. Such a point measures nothing until the operator
  resolves which of the two is wrong.

  SUPPORT -- a whole cloud excluded because it sits far outside the calibrated node volume, so its error
  is dominated by extrapolation rather than by the distortion model.

  RESIDUAL THRESHOLD -- points above an absolute reprojection-residual cut. Predetermined, and reported
  only as sensitivity. At 17 mm this selects nothing, which is itself worth stating.

Writes analysis-output/cloud_pair_scenarios_<label>.{json,log}. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
CANDS = ["stored", "B/M0", "B/M1", "PD-D/M0", "PD-D/M1"]
CONTRASTS = [("B/M1", "B/M0"), ("PD-D/M1", "PD-D/M0"), ("PD-D/M0", "B/M0"), ("PD-D/M1", "B/M1")]


def stats(err):
    e = np.abs(np.asarray(err, float)); s = np.asarray(err, float)
    if e.size == 0:
        return {"n": 0}
    return {"n": int(e.size), "mae": float(e.mean()), "rmse": float(math.sqrt((s ** 2).mean())),
            "med": float(np.median(e)), "bias": float(s.mean()),
            "p90": float(np.percentile(e, 90)), "p95": float(np.percentile(e, 95)),
            "max": float(e.max())}


def aggregate(per):
    """The documented cloud-balanced estimands. Key names ARE the formulas."""
    v = [s for s in per.values() if s.get("n")]
    if not v:
        return {}
    return {"n_groups": len(v), "n_pairs_total": int(sum(s["n"] for s in v)),
            "meanMAE": float(np.mean([s["mae"] for s in v])),
            "meanRMSE": float(np.mean([s["rmse"] for s in v])),
            "balRMSE": float(math.sqrt(np.mean([s["rmse"] ** 2 for s in v]))),
            "meanMedian": float(np.mean([s["med"] for s in v])),
            "meanBias": float(np.mean([s["bias"] for s in v])),
            "meanP90": float(np.mean([s["p90"] for s in v])),
            "meanP95": float(np.mean([s["p95"] for s in v])),
            "meanMax": float(np.mean([s["max"] for s in v])),
            "worstPair": float(max(s["max"] for s in v))}


def load_pairs(path):
    rows = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            rows[r["candidate"]].append({
                "cloud": r["cloud"], "i": int(r["event_i"]), "j": int(r["event_j"]),
                "true": float(r["true_mm"]), "err": float(r["err_mm"]),
                "orient": float(r["orient_deg"]), "radius": float(r["radius_px"]),
                "edge": float(r["edge_px"]), "camdist": float(r["camdist_mm"]),
                "rep": float(r["rep_px"]),
                "outvol": float(r["outside_cal_volume_mm"]),
                "outhull": float(r["outside_nodehull_px"])})
    return dict(rows)


def scenario(rows, drop_events=(), drop_clouds=()):
    de, dc = set(drop_events), set(drop_clouds)
    return {c: [r for r in rows[c]
                if r["cloud"] not in dc and r["i"] not in de and r["j"] not in de]
            for c in rows}


def report(say, R, name, desc, sub, category):
    per = {c: {g: stats([r["err"] for r in sub[c] if r["cloud"] == g])
               for g in sorted({r["cloud"] for r in sub[c]})} for c in sub}
    agg = {c: aggregate(per[c]) for c in sub}
    cands = [c for c in CANDS if c in sub and sub[c]]
    say(f"\n  {'=' * 104}")
    say(f"  SCENARIO: {name}   [{category}]")
    say(f"  {desc}")
    say(f"  {'=' * 104}")
    if not cands or not agg.get(cands[0]):
        say("    no pairs remain"); return
    say(f"    clouds retained {agg[cands[0]]['n_groups']}, pairs per candidate "
        f"{agg[cands[0]]['n_pairs_total']}")
    say(f"\n    PER-CLOUD")
    say(f"      {'candidate':10} {'cloud':10} {'n':>5} {'bias':>9} {'MAE':>9} {'RMSE':>9} "
        f"{'median':>9} {'p90':>9} {'p95':>9} {'max':>9}")
    for c in cands:
        for g in sorted(per[c]):
            s = per[c][g]
            if not s.get("n"):
                continue
            say(f"      {c:10} {g:10} {s['n']:5d} {s['bias']:+9.4f} {s['mae']:9.4f} "
                f"{s['rmse']:9.4f} {s['med']:9.4f} {s['p90']:9.4f} {s['p95']:9.4f} {s['max']:9.4f}")
    say(f"\n    CLOUD-BALANCED, C = {agg[cands[0]]['n_groups']}")
    say(f"      meanMAE=(1/C)sum MAE_c   meanRMSE=(1/C)sum RMSE_c   "
        f"balRMSE=sqrt((1/C)sum MSE_c)")
    say(f"      meanMax=(1/C)sum max_c (a mean, not a maximum)   worstPair=max over all pairs")
    say(f"      {'candidate':10} {'meanMAE':>9} {'meanRMSE':>9} {'balRMSE':>9} {'meanMedian':>11} "
        f"{'meanBias':>9} {'meanP90':>9} {'meanMax':>9} {'worstPair':>10}")
    for c in cands:
        a = agg[c]
        say(f"      {c:10} {a['meanMAE']:9.4f} {a['meanRMSE']:9.4f} {a['balRMSE']:9.4f} "
            f"{a['meanMedian']:11.4f} {a['meanBias']:+9.4f} {a['meanP90']:9.4f} "
            f"{a['meanMax']:9.4f} {a['worstPair']:10.4f}")
    pool = {c: stats([r["err"] for r in sub[c]]) for c in cands}
    say(f"\n    POOLED OVER ALL PAIRS -- DESCRIPTIVE ONLY; pairs are dependent and n is not an "
        f"effective sample size")
    say(f"      {'candidate':10} {'n':>5} {'MAE':>9} {'RMSE':>9} {'median':>9} {'bias':>9} "
        f"{'max':>9}")
    for c in cands:
        s = pool[c]
        say(f"      {c:10} {s['n']:5d} {s['mae']:9.4f} {s['rmse']:9.4f} {s['med']:9.4f} "
            f"{s['bias']:+9.4f} {s['max']:9.4f}")
    say(f"\n    PAIRED CONTRASTS on identical pairs; negative means the FIRST candidate is better")
    C = {}
    for a, b in CONTRASTS:
        if a not in sub or b not in sub:
            continue
        ka = {(r["cloud"], r["i"], r["j"]): r for r in sub[a]}
        kb = {(r["cloud"], r["i"], r["j"]): r for r in sub[b]}
        keys = sorted(set(ka) & set(kb))
        pg = defaultdict(list)
        for k in keys:
            pg[k[0]].append(abs(ka[k]["err"]) - abs(kb[k]["err"]))
        gm = {g: float(np.mean(v)) for g, v in sorted(pg.items())}
        mean_pg = float(np.mean(list(gm.values()))) if gm else float("nan")
        say(f"      {a} minus {b}  ({len(keys)} pairs)")
        for g in gm:
            say(f"        {g:10} n {len(pg[g]):5d}  mean d|err| {gm[g]:+9.4f} mm  pairs improved "
                f"{sum(1 for x in pg[g] if x < 0):5d}/{len(pg[g]):<5d}")
        say(f"        mean_per_group_mean_d_abs_err {mean_pg:+9.4f} mm; clouds improved "
            f"{sum(1 for v in gm.values() if v < 0)}/{len(gm)}")
        C[f"{a} minus {b}"] = {"n_pairs": len(keys), "per_group_mean_d_abs_err": gm,
                               "mean_per_group_mean_d_abs_err": mean_pg,
                               "groups_improved": int(sum(1 for v in gm.values() if v < 0)),
                               "n_groups": len(gm)}
    R["scenarios"][name] = {"description": desc, "category": category,
                            "per_cloud": per, "cloud_balanced": agg,
                            "pooled_descriptive": pool, "contrasts": C}


def covariates(say, R, name, sub, cands):
    say(f"\n    M1-MINUS-M0 BY COVARIATE, PD-D, quartile bins fixed from PD-D/M0 geometry")
    a, b = "PD-D/M1", "PD-D/M0"
    if a not in sub or b not in sub:
        return
    ka = {(r["cloud"], r["i"], r["j"]): r for r in sub[a]}
    kb = {(r["cloud"], r["i"], r["j"]): r for r in sub[b]}
    keys = sorted(set(ka) & set(kb))
    out = {}
    for lab, key in (("true length mm", "true"), ("pair orientation deg", "orient"),
                     ("image radius px", "radius"), ("min screen edge px", "edge"),
                     ("reconstructed camera distance mm", "camdist"),
                     ("outside calibrated volume mm", "outvol"),
                     ("outside node image hull px", "outhull")):
        v = np.array([kb[k][key] for k in keys], float)
        if not np.isfinite(v).any():
            continue
        q = np.nanpercentile(v, [0, 25, 50, 75, 100])
        say(f"      {lab}")
        out[lab] = []
        for i in range(4):
            lo, hi = q[i], q[i + 1]
            sel = [k for k in keys if kb[k][key] >= lo and
                   (kb[k][key] <= hi if i == 3 else kb[k][key] < hi)]
            if not sel:
                continue
            d = float(np.mean([abs(ka[k]["err"]) - abs(kb[k]["err"]) for k in sel]))
            m0 = float(np.mean([abs(kb[k]["err"]) for k in sel]))
            m1 = float(np.mean([abs(ka[k]["err"]) for k in sel]))
            say(f"        [{lo:9.2f}, {hi:9.2f}] n {len(sel):5d}   M0 MAE {m0:8.4f}  M1 MAE "
                f"{m1:8.4f}  d|err| {d:+8.4f}")
            out[lab].append({"lo": float(lo), "hi": float(hi), "n": len(sel),
                             "m0_mae": m0, "m1_mae": m1, "d_abs_err": d})
    R["scenarios"][name]["covariates_pd"] = out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True, help="a cloud_downstream *_pairs.csv")
    ap.add_argument("--label", required=True)
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--defect-events", nargs="*", type=int, default=(),
                    help="DATA DEFECT: events whose grid label and click disagree by an integer "
                         "number of grid rows")
    ap.add_argument("--support-clouds", nargs="*", default=(),
                    help="SUPPORT: whole clouds dominated by extrapolation beyond the node volume")
    ap.add_argument("--rep-thresholds", nargs="*", type=float, default=[5.0, 6.0])
    args = ap.parse_args()
    stem = f"cloud_pair_scenarios_{args.label}"
    log = open(os.path.join(args.outdir, stem + ".log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    rows = load_pairs(args.pairs)
    R = {"pairs_csv": os.path.abspath(args.pairs), "scenarios": {},
         "defect_events": list(args.defect_events), "support_clouds": list(args.support_clouds)}
    say("=" * 112)
    say(f"CLOUD-PAIR EXCLUSION SCENARIOS -- {os.path.basename(args.pairs)}")
    say("=" * 112)
    say("  No refitting: cloud points are ground truth, never calibration inputs, so every candidate")
    say("  map is identical across scenarios and only the scoring set changes.")

    cands = [c for c in CANDS if c in rows]
    report(say, R, "complete", "PRIMARY as specified: every cloud, every eligible point, every pair.",
           rows, "complete data")
    covariates(say, R, "complete", rows, cands)

    if args.defect_events:
        s = scenario(rows, drop_events=args.defect_events)
        report(say, R, "defect-excluded",
               f"Excluding {len(args.defect_events)} points whose recorded grid label and click "
               f"disagree by an integer number of grid rows: events "
               f"{sorted(args.defect_events)}. Not a threshold choice.",
               s, "data defect")
        covariates(say, R, "defect-excluded", s, cands)
        if args.support_clouds:
            s2 = scenario(rows, drop_events=args.defect_events,
                          drop_clouds=args.support_clouds)
            report(say, R, "defect-and-support-excluded",
                   f"Also excluding {list(args.support_clouds)}, dominated by extrapolation beyond "
                   f"the calibrated node volume.", s2, "data defect + support")
            covariates(say, R, "defect-and-support-excluded", s2, cands)
    if args.support_clouds:
        s3 = scenario(rows, drop_clouds=args.support_clouds)
        report(say, R, "support-excluded",
               f"Excluding {list(args.support_clouds)} only, keeping the label-inconsistent points, "
               f"so the two exclusion categories can be told apart.", s3, "support")

    say(f"\n  {'=' * 104}")
    say(f"  PREDETERMINED RESIDUAL-THRESHOLD SENSITIVITY (reprojection residual, px)")
    say(f"  {'=' * 104}")
    base = rows[cands[0]]
    rp = np.array([r["rep"] for r in base])
    say(f"    pair-level max-endpoint reprojection residual: median {np.median(rp):.3f}, "
        f"p90 {np.percentile(rp, 90):.3f}, p95 {np.percentile(rp, 95):.3f}, max {rp.max():.3f} px")
    say(f"    continuous distribution, deciles: " + ", ".join(
        f"{np.percentile(rp, q):.2f}" for q in range(10, 101, 10)))
    R["reprojection_distribution"] = {
        "median": float(np.median(rp)), "p90": float(np.percentile(rp, 90)),
        "p95": float(np.percentile(rp, 95)), "max": float(rp.max()),
        "deciles": [float(np.percentile(rp, q)) for q in range(10, 101, 10)]}
    for thr in args.rep_thresholds:
        n = int((rp >= thr).sum())
        say(f"    pairs with an endpoint at or above {thr:.0f} px: {n}"
            + ("  -- this convention selects NOTHING in this document, so it cannot be a "
               "sensitivity analysis here" if n == 0 else ""))
        R.setdefault("threshold_counts", {})[str(thr)] = n
    say(f"    No post-hoc cutoff has been invented from the observed 17 mm residuals.")

    p = os.path.join(args.outdir, stem + ".json")
    json.dump(R, open(p, "w"), indent=1, default=str)
    say(f"\n  wrote {os.path.basename(p)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
