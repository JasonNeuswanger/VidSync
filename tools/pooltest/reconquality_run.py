#!/usr/bin/env python3
"""Drive reconquality.py over every validation recording that has the required observations.

ANALYSIS ONLY: no production undistortion, model default, selection policy or .vsd is touched.

SCOPE RULE. Point-cloud metrics run where clouds exist; conventional-segment metrics run where
conventional measurements exist. No recording is dropped for lacking one family and no valid evidence is
discarded to manufacture a balanced corpus. The recording-by-family matrix therefore has empty cells, and
that is reported rather than hidden.

ESTIMAND. The paired M1-minus-M0 change on identical observations within a recording, per estimator.
Candidates are fitted exactly as in cloud_downstream.py: M0 first, M1 warm-started from the accepted M0
with eta = 0, both gated on the objective and on every physical-map test, and known-length never selects
a fit.

AGGREGATION HIERARCHY, in order and never collapsed:
  1. every cloud or placement individually;
  2. the equal-cloud macro-summary within the recording, i.e. unweighted over clouds;
  3. leave-one-cloud-out sensitivity of that summary;
  4. raw point-, edge- or pair-weighted summaries, labelled as inventory-specific descriptive quantities.
No information-weighted primary is introduced, because no weight construction independent of the observed
M0/M1 outcome has been defined. No bootstrap interval over placements is produced: a handful of
deliberately chosen target placements is not a random sample from a population of placements, so the
individual paired effects and the leave-one-cloud-out stability ARE the uncertainty statement.

Writes analysis-output/reconquality_<label>.{json,log}. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np

import harness_import

L = harness_import.load
DS = L("downstream")
LT = L("lattice")
OB = L("objectives")
kl = L("knownlength")
RQ = L("reconquality")
CD = L("cloud_downstream")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
CANDS = ["B/M0", "B/M1", "PD-D/M0", "PD-D/M1"]
PAIRS = [("B/M1", "B/M0"), ("PD-D/M1", "PD-D/M0")]


def log_ratio(meas, true):
    return math.log(meas / true) if meas > 0 and true > 0 else float("nan")


# ============================================================== per-recording


def build_candidates(say, vsd, cals, clips):
    """Same gated M0-first path as cloud_downstream, reused rather than reimplemented."""
    maps_by_clip, fitdiag, validities, plumb = {}, {}, {}, {}
    for clip in clips:
        caps = LT.load_captures(vsd, clip)
        Dd = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
        contra = sum(C.notes["index_contradictions"] for C in caps)
        plumb[clip] = CD.plumbline_provenance(caps, Dd)
        if contra or Dd.n < 20:
            say(f"      {clip}: lattice did not validate ({contra} contradictions, {Dd.n} obs); "
                f"PD-D is not forced onto it and this recording is skipped")
            return None, None, None, plumb
        node_pts = np.array([[x, y] for x, y, _, _ in cals[clip]["front"] + cals[clip]["back"]], float)
        th, dg, vv = CD.fit_gated(say, Dd, node_pts, clip)
        maps_by_clip[clip], fitdiag[clip], validities[clip] = th, dg, vv
    return maps_by_clip, fitdiag, validities, plumb


def cloud_metrics(say, R, key, D0, cals, clips, maps, unit_mm):
    """Primary per-cloud panels for every candidate, plus aggregation and LOCO."""
    sup = CD.cal_support(cals)
    per_cand = {}
    for name in [c for c in CANDS if c in maps]:
        cams = {c: DS.build_calibration(cals[c], maps[name][c]) for c in clips}
        clouds = {}
        for ckey, pts in sorted(D0["clouds"].items()):
            idx = list(range(len(pts)))
            N = np.array([p["mm"] for p in pts], float)
            clicks_by_index = {i: {c: D0["clicks"][pts[i]["pk"]][c] for c in clips
                                  if c in D0["clicks"].get(pts[i]["pk"], {})} for i in idx}
            X, ok = [], True
            for i in idx:
                obs = [(cams[c], clicks_by_index[i][c]) for c in clips if c in clicks_by_index[i]]
                if len(obs) < 2:
                    ok = False
                    break
                X.append(DS.triangulate_lm(obs)["X"] * unit_mm)
            if not ok or len(N) < 4:
                continue
            P = np.array(X, float)
            panel = RQ.cloud_panel(N, P, clicks_by_index, cams, clips, do_heldout=True)
            panel["support"] = {
                "mean_camdist_mm": float(np.mean([
                    min(float(np.linalg.norm(P[i] / unit_mm - np.array(cams[c]["cam"], float)))
                        for c in clips) * unit_mm for i in idx])),
                "mean_outside_cal_volume_mm": float(np.mean([
                    CD.box_outside(P[i] / unit_mm, sup["lo3"], sup["hi3"]) * unit_mm for i in idx])),
                "max_outside_nodehull_px": float(max(
                    CD.hull_outside(sup["hulls"][c], clicks_by_index[i][c])
                    for i in idx for c in clips if c in clicks_by_index[i]))}
            panel["timecode"] = pts[0]["tc"]
            panel["obj_pk"] = pts[0]["cloud_pk"]
            clouds[ckey] = panel
        per_cand[name] = clouds
    if not per_cand:
        return None

    # ---- paired M1 minus M0 per cloud, per metric, on identical observations
    fams = {
        "scale_log_s": lambda p: p["scale"]["log_s"],
        "shape_rms_sim_mm": lambda p: p["shape"]["rms_sim_mm"],
        "affine_band_mm2": lambda p: p["shape"]["bands"]["affine_beyond_similarity"],
        "normal_quadratic_mm2": lambda p: p["shape"]["bands"]["normal_quadratic"],
        "tangential_quadratic_mm2": lambda p: p["shape"]["bands"]["tangential_quadratic"],
        "higher_residual_mm2": lambda p: p["shape"]["bands"]["higher_residual"],
        "bowl_curvature": lambda p: p["shape"]["normal_curvature"]["bowl_mean_curvature"],
        "saddle_magnitude": lambda p: p["shape"]["normal_curvature"]["saddle_magnitude"],
        "plane_rms_mm": lambda p: p["plane"]["rms_mm"],
        "edge_rms_log": lambda p: p["edges"].get("rms_log", float("nan")),
        "edge_signed_mean_log": lambda p: p["edges"].get("signed_mean_log", float("nan")),
        "edge_rms_mm": lambda p: p["edges"].get("rms_mm", float("nan")),
        "heldout_rms_px": lambda p: float(np.mean([v["rms_px"] for v in
                                                  p["heldout"]["per_camera"].values() if v.get("n")]))
        if p.get("heldout") else float("nan"),
        "allpairs_mae_mm_descriptive": lambda p: p["all_pairs_descriptive"]["mae_mm"],
        "internal_reproject_median_px": lambda p: (p["internal_consistency"]["reproject_rms_px"]
                                                  .get("median", float("nan"))
                                                  if p.get("internal_consistency") else float("nan")),
    }
    SIGNED = {"scale_log_s", "bowl_curvature", "saddle_magnitude", "edge_signed_mean_log"}
    paired = {}
    for a, b in PAIRS:
        if a not in per_cand or b not in per_cand:
            continue
        shared = sorted(set(per_cand[a]) & set(per_cand[b]))
        blk = {}
        for fname, f in fams.items():
            d = {}
            for g in shared:
                va, vb = f(per_cand[a][g]), f(per_cand[b][g])
                if not (np.isfinite(va) and np.isfinite(vb)):
                    continue
                rec = {"M0": vb, "M1": va, "diff": va - vb}
                if fname not in SIGNED and vb > 0 and va > 0:
                    rec["log_ratio_M1_over_M0"] = math.log(va / vb)
                d[g] = rec
            if not d:
                continue
            vals = [d[g]["diff"] for g in d]
            blk[fname] = {
                "signed_quantity": fname in SIGNED,
                "per_cloud": d,
                "equal_cloud_mean_diff": float(np.mean(vals)),
                "n_clouds": len(vals),
                "clouds_improved": (None if fname in SIGNED
                                    else int(sum(1 for v in vals if v < 0))),
                "loco": {g: float(np.mean([d[h]["diff"] for h in d if h != g])) for g in d}
                if len(vals) > 2 else {},
                "mean_log_ratio": (float(np.mean([d[g]["log_ratio_M1_over_M0"] for g in d
                                                 if "log_ratio_M1_over_M0" in d[g]]))
                                   if fname not in SIGNED and
                                   any("log_ratio_M1_over_M0" in d[g] for g in d) else None)}
        paired[f"{a} minus {b}"] = blk
    R.setdefault("clouds", {})[key] = {"per_candidate": per_cand, "paired": paired,
                                       "aggregation_note":
                                       "level 2 is the EQUAL-CLOUD mean of per-cloud differences; "
                                       "level 3 is leave-one-cloud-out of that mean; no "
                                       "information-weighted primary and no bootstrap over placements"}
    return per_cand, paired


def conventional_metrics(say, R, key, D0, cals, clips, maps, unit_mm, sup):
    """Signed physical and signed log-length error per measurement, kept apart from clouds."""
    conv = D0["conventional"]
    if not conv:
        return None
    rows = {}
    for name in [c for c in CANDS if c in maps]:
        cams = {c: DS.build_calibration(cals[c], maps[name][c]) for c in clips}
        rr = []
        for r in conv:
            a, b = r["pks"]
            obs = {}
            for pk in (a, b):
                o = [(cams[c], D0["clicks"][pk][c]) for c in clips if c in D0["clicks"].get(pk, {})]
                if len(o) < 2:
                    obs = None
                    break
                obs[pk] = DS.triangulate_lm(o)
            if obs is None:
                continue
            d = float(np.linalg.norm(obs[a]["X"] - obs[b]["X"])) * unit_mm
            rr.append({"event": int(r["event"]), "obj": str(r["obj"]), "tc": str(r["tc"]),
                       "true_mm": float(r["true"]), "meas_mm": d, "err_mm": d - float(r["true"]),
                       "log_ratio": log_ratio(d, float(r["true"])),
                       "camdist_mm": 0.5 * (
                           min(float(np.linalg.norm(obs[a]["X"] - np.array(cams[c]["cam"], float)))
                               for c in clips)
                           + min(float(np.linalg.norm(obs[b]["X"] - np.array(cams[c]["cam"], float)))
                                 for c in clips)) * unit_mm,
                       "outside_cal_volume_mm": max(
                           CD.box_outside(obs[a]["X"], sup["lo3"], sup["hi3"]),
                           CD.box_outside(obs[b]["X"], sup["lo3"], sup["hi3"])) * unit_mm})
        rows[name] = rr
    out = {"per_candidate": {}, "paired": {}}
    for name, rr in rows.items():
        e = np.array([r["err_mm"] for r in rr]); lg = np.array([r["log_ratio"] for r in rr])
        out["per_candidate"][name] = {
            "n": len(rr), "mae_mm": float(np.abs(e).mean()), "bias_mm": float(e.mean()),
            "rmse_mm": float(math.sqrt((e ** 2).mean())),
            "signed_mean_log": float(lg.mean()), "rms_log": float(math.sqrt((lg ** 2).mean())),
            "p95_abs_mm": float(np.percentile(np.abs(e), 95)), "max_abs_mm": float(np.abs(e).max())}
    for a, b in PAIRS:
        if a not in rows or b not in rows:
            continue
        ka = {r["event"]: r for r in rows[a]}
        kb = {r["event"]: r for r in rows[b]}
        ev = sorted(set(ka) & set(kb))
        d_abs = np.array([abs(ka[e]["err_mm"]) - abs(kb[e]["err_mm"]) for e in ev])
        d_log = np.array([abs(ka[e]["log_ratio"]) - abs(kb[e]["log_ratio"]) for e in ev])
        strat = {}
        for sname, keyf in (("object", lambda r: r["obj"]), ("timecode", lambda r: r["tc"]),
                            ("true_length_mm", lambda r: f"{r['true_mm']:.0f}")):
            per = defaultdict(list)
            for e in ev:
                per[keyf(ka[e])].append(abs(ka[e]["err_mm"]) - abs(kb[e]["err_mm"]))
            gm = {k: float(np.mean(v)) for k, v in sorted(per.items())}
            strat[sname] = {"per_group": gm, "n_per_group": {k: len(v) for k, v in sorted(per.items())},
                            "equal_group_mean": float(np.mean(list(gm.values()))),
                            "groups_improved": int(sum(1 for v in gm.values() if v < 0)),
                            "n_groups": len(gm)}
        out["paired"][f"{a} minus {b}"] = {
            "n": len(ev), "mean_d_abs_err_mm": float(d_abs.mean()),
            "mean_d_abs_log": float(d_log.mean()),
            "measurements_improved": int((d_abs < 0).sum()), "strata": strat}
    out["rows"] = rows
    R.setdefault("conventional", {})[key] = out
    return out


# ============================================================== difficulty profiles


def difficulty_profiles(R, key, per_cand):
    """Frozen covariates, one at a time. Pairing already controls difficulty; these locate the change."""
    a, b = "PD-D/M1", "PD-D/M0"
    if a not in per_cand or b not in per_cand:
        return
    shared = sorted(set(per_cand[a]) & set(per_cand[b]))
    prof = {}
    covs = {"mean_camdist_mm": lambda p: p["support"]["mean_camdist_mm"],
            "mean_outside_cal_volume_mm": lambda p: p["support"]["mean_outside_cal_volume_mm"],
            "target_extent_mm": lambda p: p["target_extent_mm"],
            "k_points": lambda p: p["k"]}
    for cname, f in covs.items():
        rows = []
        for g in shared:
            rows.append({"cloud": g, "covariate": f(per_cand[b][g]),
                         "d_shape_rms_mm": per_cand[a][g]["shape"]["rms_sim_mm"]
                         - per_cand[b][g]["shape"]["rms_sim_mm"],
                         "d_log_s": per_cand[a][g]["scale"]["log_s"]
                         - per_cand[b][g]["scale"]["log_s"],
                         "d_edge_rms_log": per_cand[a][g]["edges"].get("rms_log", float("nan"))
                         - per_cand[b][g]["edges"].get("rms_log", float("nan"))})
        prof[cname] = sorted(rows, key=lambda r: r["covariate"])
    R.setdefault("difficulty_profiles", {})[key] = {
        "covariates_frozen_from": "PD-D/M0 geometry and the observed clicks",
        "profiles": prof,
        "note": "one covariate at a time; with a handful of clouds per recording these are ordered "
                "listings rather than binned curves, deliberately avoiding sparse multidimensional "
                "bins and post-hoc cutoffs"}


# ============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="all")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--vsd", nargs="*", default=())
    ap.add_argument("--docs", nargs="*", default=None)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    stem = f"reconquality_{args.label}"
    log = open(os.path.join(args.outdir, stem + ".log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    found = CD.discover(extra_vsds=args.vsd)
    docs = [d for d in found if args.docs is None or d["key"] in args.docs]
    R = {"documents": {}, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "scope_rule": "cloud metrics where clouds exist, conventional metrics where conventional "
                       "measurements exist; no recording excluded for lacking a family"}
    say("=" * 112)
    say("RECONSTRUCTION-QUALITY METRIC FRAMEWORK")
    say("=" * 112)
    say(f"  recordings: {[d['key'] for d in docs]}")

    for spec in docs:
        vsd = spec["vsd"]
        cals = DS.load_bound_cals(vsd)
        clips = sorted(cals)
        sha = cals[clips[0]]["identity"].doc_sha256
        D0 = spec["loaded"]
        say(f"\n{'=' * 112}\n  {spec['label']}\n  SHA-256 {sha}\n{'=' * 112}")
        say(f"    {len(D0['clouds'])} cloud(s), {len(D0['cloud_points'])} cloud points, "
            f"{len(D0['conventional'])} conventional measurement(s)")
        maps_by_clip, fitdiag, validities, plumb = build_candidates(say, vsd, cals, clips)
        docR = R["documents"][spec["key"]] = {
            "label": spec["label"], "doc_sha256": sha, "role": spec.get("role"),
            "focal_mm_metadata": spec.get("focal_mm"), "plumblines": plumb,
            "n_clouds": len(D0["clouds"]), "n_cloud_points": len(D0["cloud_points"]),
            "n_conventional": len(D0["conventional"])}
        if maps_by_clip is None:
            docR["skipped"] = "lattice did not validate"
            continue
        docR["fits"] = {c: {k: {kk: vv for kk, vv in v.items()} for k, v in fitdiag[c].items()}
                        for c in clips}
        docR["theta14"] = {c: {k: [float(x) for x in np.asarray(maps_by_clip[c][k], float)]
                               for k in sorted(maps_by_clip[c])} for c in clips}
        maps = {k: {c: DS.DistortionMap.for_camera(maps_by_clip[c][k], cals[c], name=f"{k}/{c}",
                                                   source="fitted this run") for c in clips}
                for k in CANDS if all(k in maps_by_clip[c] for c in clips)}
        bad = sorted({k for c in clips for k, d in fitdiag[c].items() if not d["gate"]["ok"]})
        if bad:
            say(f"    GATE-REJECTED on a camera, so M0 stands for them: {bad}")
            maps = {k: v for k, v in maps.items() if k not in bad}
        docR["gate_rejected"] = bad
        sup = CD.cal_support(cals)

        if D0["clouds"]:
            say(f"\n    CLOUD PANELS ({len(D0['clouds'])} clouds x {len(maps)} candidates, "
                f"held-out LOPO reprojection included)")
            res = cloud_metrics(say, R, spec["key"], D0, cals, clips, maps, spec["unit_mm"])
            if res:
                per_cand, paired = res
                ex = next(iter(next(iter(per_cand.values())).values()))
                say(f"      identity checks on the first panel: scale "
                    f"{'OK' if ex['identities']['scale']['holds'] else 'FAILED'} "
                    f"(rel {ex['identities']['scale']['rel_err']:.2e}), bands "
                    f"{'OK' if ex['identities']['bands']['holds'] else 'FAILED'} "
                    f"(rel {ex['identities']['bands']['rel_err']:.2e})")
                nb = sum(1 for cd in per_cand.values() for p in cd.values()
                         if not (p["identities"]["scale"]["holds"] and p["identities"]["bands"]["holds"]))
                say(f"      panels failing an identity check: {nb} of "
                    f"{sum(len(cd) for cd in per_cand.values())}")
                for name in [c for c in CANDS if c in per_cand]:
                    say(f"\n      {name}")
                    say(f"        {'cloud':10} {'k':>3} {'log s':>10} {'shapeRMS':>9} {'affine':>9} "
                        f"{'normQuad':>9} {'tanQuad':>9} {'higher':>9} {'planeRMS':>9} "
                        f"{'edgeRMSlog':>11} {'heldoutPx':>10}")
                    for g, p in sorted(per_cand[name].items()):
                        bd = p["shape"]["bands"]
                        ho = (np.mean([v["rms_px"] for v in p["heldout"]["per_camera"].values()
                                       if v.get("n")]) if p.get("heldout") else float("nan"))
                        say(f"        {g:10} {p['k']:>3} {p['scale']['log_s']:+10.6f} "
                            f"{p['shape']['rms_sim_mm']:9.4f} "
                            f"{bd['affine_beyond_similarity']:9.2f} {bd['normal_quadratic']:9.2f} "
                            f"{bd['tangential_quadratic']:9.2f} {bd['higher_residual']:9.2f} "
                            f"{p['plane']['rms_mm']:9.4f} "
                            f"{p['edges'].get('rms_log', float('nan')):11.6f} {ho:10.4f}")
                say(f"\n      PAIRED M1 MINUS M0, equal-cloud mean of per-cloud differences, with "
                    f"leave-one-cloud-out range")
                for cn, blk in paired.items():
                    say(f"        {cn}")
                    say(f"          {'metric':30} {'equalCloudMean':>15} {'clouds<0':>9} "
                        f"{'LOCO min':>11} {'LOCO max':>11} {'meanLogRatio':>13}")
                    for fname, v in blk.items():
                        lo = min(v["loco"].values()) if v["loco"] else float("nan")
                        hi = max(v["loco"].values()) if v["loco"] else float("nan")
                        ci = ("signed" if v["signed_quantity"]
                              else f"{v['clouds_improved']}/{v['n_clouds']}")
                        mlr = v["mean_log_ratio"]
                        say(f"          {fname:30} {v['equal_cloud_mean_diff']:+15.6g} {ci:>9} "
                            f"{lo:+11.4g} {hi:+11.4g} "
                            f"{(f'{mlr:+13.6f}' if mlr is not None else 'n/a':>13}")
                difficulty_profiles(R, spec["key"], per_cand)

        if D0["conventional"]:
            say(f"\n    CONVENTIONAL SEGMENTS ({len(D0['conventional'])}), separate family")
            cv = conventional_metrics(say, R, spec["key"], D0, cals, clips, maps, spec["unit_mm"], sup)
            if cv:
                say(f"      {'candidate':10} {'n':>4} {'MAE mm':>9} {'bias mm':>9} "
                    f"{'meanLog':>10} {'rmsLog':>10}")
                for name in [c for c in CANDS if c in cv["per_candidate"]]:
                    s = cv["per_candidate"][name]
                    say(f"      {name:10} {s['n']:>4} {s['mae_mm']:9.4f} {s['bias_mm']:+9.4f} "
                        f"{s['signed_mean_log']:+10.6f} {s['rms_log']:10.6f}")
                for cn, v in cv["paired"].items():
                    say(f"      {cn}: mean d|err| {v['mean_d_abs_err_mm']:+9.4f} mm, mean d|log| "
                        f"{v['mean_d_abs_log']:+9.6f}, improved {v['measurements_improved']}/{v['n']}")
                    for sname, st in v["strata"].items():
                        say(f"        by {sname:14} equal-group mean {st['equal_group_mean']:+9.4f} mm, "
                            f"groups improved {st['groups_improved']}/{st['n_groups']}  "
                            + ", ".join(f"{k}:{x:+.4f}" for k, x in st["per_group"].items()))
        say(f"    [{time.time() - t0:.1f}s]")

    # ---- recording x family matrix
    say(f"\n{'=' * 112}\n  RECORDING BY METRIC-FAMILY MATRIX of paired M1-minus-M0 effects\n{'=' * 112}")
    say("  Empty cells mean the recording lacks that observation family, not that the effect is zero.")
    fam_rows = ["scale_log_s", "shape_rms_sim_mm", "edge_rms_log", "heldout_rms_px",
                "plane_rms_mm", "allpairs_mae_mm_descriptive"]
    for est in ("PD-D/M1 minus PD-D/M0", "B/M1 minus B/M0"):
        say(f"\n  {est}")
        hdr = f"    {'metric family':30}" + "".join(f"{k[:14]:>16}" for k in R["documents"])
        say(hdr)
        for fname in fam_rows:
            cells = []
            for k in R["documents"]:
                blk = R.get("clouds", {}).get(k, {}).get("paired", {}).get(est, {})
                v = blk.get(fname)
                cells.append(f"{v['equal_cloud_mean_diff']:+16.6g}" if v else f"{'-':>16}")
            say(f"    {fname:30}" + "".join(cells))
        cells = []
        for k in R["documents"]:
            v = R.get("conventional", {}).get(k, {}).get("paired", {}).get(est)
            cells.append(f"{v['mean_d_abs_err_mm']:+16.6g}" if v else f"{'-':>16}")
        say(f"    {'conventional d|err| mm':30}" + "".join(cells))
    say("\n  Signed quantities (scale, curvature) are differences, never loss ratios. Positive-loss")
    say("  quantities also carry log(L_M1/L_M0) in the JSON. Correlated summaries within one recording")
    say("  are NOT independent votes: the scale, shape, plane, edge and all-pairs columns are different")
    say("  views of the same reconstruction and are reported for structure, not for counting.")

    p = os.path.join(args.outdir, stem + ".json")
    json.dump(R, open(p, "w"), indent=1, default=str)
    say(f"\n  wrote {os.path.basename(p)}   [{time.time() - t0:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
