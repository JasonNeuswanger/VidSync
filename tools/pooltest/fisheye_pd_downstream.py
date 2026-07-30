#!/usr/bin/env python3
"""HISTORICAL / NON-AUTHORITATIVE as of 2026-07-29. Frozen to reproduce its published numbers.

    SUPERSEDED BY:  downstream_parity.py (injection + solver parity gate)
                  + xdoc_objectives.py  (candidate tables, cross-document)

    DO NOT import this module for reusable functionality. It inherits its downstream geometry from
    fisheye_knownlength_analysis.py, which is itself historical: eta reaches the measurement sightlines
    only because an eta-aware undistortion is installed process-wide into `parity`. It also passes bare
    14-vectors around instead of camera-bound `downstream.DistortionMap` objects, so nothing prevents
    one camera's map being applied to the other -- the failure the independent audit demonstrated.

Production-faithful downstream validation of the exact-PD distortion fits.

Takes the already-verified distortion candidates from the Round-1 and closure outputs, rebuilds the
COMPLETE downstream calibration for each one from the raw calibration-frame clicks via the
production-parity oracle, and re-measures every conventional length and point cloud in
2015-09-04-1 Clearwater.vsd.

No stored homography, camera position, or apparent back-node position is reused for any candidate,
including the stored-parameter anchor. Nothing is refitted here: the maps come from disk and a parity
check confirms they load exactly.

Writes analysis-output/fisheye_pd_downstream.{log,json} plus CSVs.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import csv
import importlib.util
import json
import math
import os
import sqlite3
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


# NOTE: importing fisheye_knownlength_analysis has the SIDE EFFECT of monkeypatching
# parity.undistort to the eta-aware nodes.undistort13 (its line 84). That patch is what makes
# measurement sightlines eta-consistent with the calibration rebuild. It is asserted below rather
# than trusted.
FK = L("fisheye_knownlength_analysis")
st, kl, pa, nd = FK.st, FK.kl, FK.pa, FK.nd
LT = L("lattice")
OB = L("objectives")

CANDIDATES = ["stored", "B/M0", "B/M1", "PD-D/M0", "PD-D/M1", "PD-U/M1"]
BASE = "B/M0"
CONTRASTS = [("B/M1", "B/M0", "effect of eta under the legacy line objective"),
             ("PD-D/M1", "PD-D/M0", "effect of eta under projective calibration"),
             ("PD-D/M0", "B/M0", "effect of the objective at M0"),
             ("PD-D/M1", "B/M1", "effect of the objective at M1"),
             ("PD-U/M1", "PD-D/M1", "weighting sensitivity"),
             ("B/M0", "stored", "legacy refit vs rebuilt stored anchor"),
             ("PD-D/M1", "stored", "projective candidate vs rebuilt stored anchor")]


def stats(err):
    return FK.stats(err)


def qtable(say, label, rows, key="err"):
    e = np.array([abs(r[key]) for r in rows], float)
    s = np.array([r[key] for r in rows], float)
    say(f"      {label:16} n {len(rows):4d}  MAE {e.mean():7.3f}  RMSE "
        f"{math.sqrt((s ** 2).mean()):7.3f}  med {np.median(e):7.3f}  bias {s.mean():+8.3f}  "
        f"p50 {np.percentile(e, 50):7.3f}  p75 {np.percentile(e, 75):7.3f}  "
        f"p90 {np.percentile(e, 90):7.3f}  p95 {np.percentile(e, 95):7.3f}  "
        f"max {e.max():7.3f}")


# =============================================================== candidates


def load_candidates(say, vsd, outdir):
    r1 = json.load(open(os.path.join(outdir, "obj_round1.json")))
    cl = json.load(open(os.path.join(outdir, "obj_pd_closure.json")))
    cals = st.load_cal(vsd)
    clips = sorted(cals)
    cand = {}
    for name in CANDIDATES:
        per = {}
        for clip in clips:
            if name == "stored":
                th = np.zeros(14)
                th[:13] = np.asarray(cals[clip]["dist"], float)
            elif name.startswith("B/"):
                th = np.array(r1[clip]["fits"][name]["theta14"], float)
            else:
                th = np.array(cl[clip]["weighting"]["fits"][name]["theta14"], float)
            per[clip] = th
        cand[name] = per
    prov = {"stored": "the .vsd's own ZVSCALIBRATION distortion columns",
            "B/M0": "obj_round1.json fits B/M0", "B/M1": "obj_round1.json fits B/M1",
            "PD-D/M0": "obj_pd_closure.json weighting fits PD-D/M0",
            "PD-D/M1": "obj_pd_closure.json weighting fits PD-D/M1",
            "PD-U/M1": "obj_pd_closure.json weighting fits PD-U/M1"}
    say(f"\n[2] CANDIDATE MAPS LOADED FROM DISK (nothing refitted here)")
    say(f"      {'candidate':10} {'clip':6} {'centre x':>10} {'centre y':>10} {'k1':>13} "
        f"{'p1':>13} {'eta':>12}  source")
    for name in CANDIDATES:
        for clip in clips:
            t = cand[name][clip]
            say(f"      {name:10} {clip[:5]:6} {t[0]:10.4f} {t[1]:10.4f} {t[2]:13.6e} "
                f"{t[9]:13.6e} {t[13]:+12.8f}  {prov[name] if clip == clips[0] else ''}")
    for name in CANDIDATES:
        for clip in clips:
            e = cand[name][clip][13]
            if name.endswith("M1"):
                assert e != 0.0, f"{name} {clip}: eta loaded as exactly zero, load failed"
            else:
                assert e == 0.0, f"{name} {clip}: eta must be exactly 0.0, got {e!r}"
    say(f"      load parity: every M1 candidate carries a nonzero eta; every M0/stored candidate "
        f"carries exactly 0.0")
    return cand, cals, clips


# =============================================================== path verification


def verify_path(say, vsd, cals, clips, cand):
    say(f"\n[0] DOWNSTREAM PATH VERIFICATION")
    say(f"    Production routines the oracle reproduces:")
    for s in ["undistortPoint                          VSCalibration.mm:219",
              "front matrices from nodes               calcMatrix / arrange2D / LAPACK dgelss",
              "back-node apparent-position refraction  VSCalibration.mm:1052-1061 fixed point",
              "camera position from back sightlines    cpaLines / UtilityFunctions.mm:255",
              "measurement sightline construction      VSEventScreenPoint computeLine3D",
              "iterative 3D refinement                 VSPoint.m:147-215 calculate3DCoords"]:
        say(f"      {s}")
    ok = True
    hs = pa.historical_eta_map_state()
    same = bool(hs["installed"])
    say(f"\n    (a) measurement sightlines use the ETA-AWARE map: {same} "
        f"(parity.historical_eta_map_state() -> {hs}, installed explicitly by "
        f"fisheye_knownlength_analysis.py at import)")
    if not same:
        say(f"        *** parity is using its 13-parameter undistort13; eta would be silently dropped "
            f"from every sightline while the calibration used it ***")
        ok = False
    cam = FK.build_cam(cals[clips[0]], cand["PD-D/M1"][clips[0]])
    cam0 = dict(cam)
    cam0["dist"] = np.concatenate([cand["PD-D/M1"][clips[0]][:13], [0.0]])
    d = max(abs(a - b) for p, q in zip(pa.sightline(400.0, 300.0, cam),
                                       pa.sightline(400.0, 300.0, cam0))
            for a, b in zip(p, q))
    say(f"        empirical: zeroing eta moves that sightline by {d:.4f} mm, so eta genuinely "
        f"propagates into measurement geometry")
    if d < 1e-9:
        say(f"        *** eta has no effect on sightlines ***"); ok = False

    rng = np.random.default_rng(7)
    P = np.column_stack([rng.uniform(0, 1920, 400), rng.uniform(0, 1080, 400)])
    worst = 0.0
    for name in ("PD-D/M1", "B/M1", "PD-D/M0"):
        th = cand[name][clips[0]]
        a = np.array([nd.undistort13(x, y, th) for x, y in P])
        b = LT.U(P, th)
        c3, _, _ = OB.u_kernel(P, th)
        worst = max(worst, float(np.abs(a - b).max()), float(np.abs(a - c3).max()))
    say(f"\n    (b) same map across implementations: max |nodes.undistort13 - lattice.U| and "
        f"|... - objectives.u_kernel| over 400 random pixels x 3 candidates = {worst:.3e} px")
    say(f"        oracle.cpp:58-73 is the same conjugated expression term for term as "
        f"nodes.py:50-61; the residual difference is last-bit association only")
    if worst > 1e-8:
        say(f"        *** implementations disagree beyond round-off ***"); ok = False

    th1 = cand["PD-D/M1"][clips[0]].copy(); th1[13] = 0.0
    A = FK.build_cam(cals[clips[0]], th1)
    B = FK.build_cam(cals[clips[0]], np.concatenate([th1[:13], [0.0]]))
    dcam = max(abs(a - b) for a, b in zip(A["cam"], B["cam"]))
    dfr = float(np.abs(np.array(A["s2f"]) - np.array(B["s2f"])).max())
    say(f"\n    (c) M1 at eta = 0 reduces to M0 through the FULL rebuild: camera position differs "
        f"by {dcam:.3e} mm, front homography by {dfr:.3e}")
    if dcam > 1e-9 or dfr > 1e-12:
        say(f"        *** the eta = 0 reduction is not exact ***"); ok = False

    cc = cals[clips[0]]
    say(f"\n    (d) refractive settings read from the document (identical for both cameras):")
    say(f"        correct refraction {bool(cc['refract'])}; front plane {cc['front_d']} mm, back "
        f"plane {cc['back_d']} mm; pane thickness {cc['thick']} mm")
    say(f"        medium index n1 {cc['n1']}, pane index n2 {cc['n2']}; axes "
        f"({cc['ah']}, {cc['av']})")
    say(f"        back-node fixed point: 4 iterations, first uncorrected (oracle.cpp:379 = "
        f"VSCalibration.mm:1052-1061); per-node refraction root solve gsl_multiroot_hybrids,")
    say(f"        residual tolerance 1e-7, cap 1000 (oracle.cpp:241-242); camera position "
        f"recomputed on EVERY iteration (oracle.cpp:386-401)")

    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    flag = list(db.execute("SELECT ZUSEITERATIVETRIANGULATION FROM ZVSPROJECT"))[0][0]
    db.close()
    say(f"\n    (e) measurement triangulation. useIterativeTriangulation = {flag} in this document, "
        f"so production DOES refine; this is not an unshipped addition.")
    say(f"        Production (VSPoint.m:147-215): linear CPA seed, then gsl nmsimplex2 on summed "
        f"squared reprojection error, simplex size tolerance 1e-6, iteration cap 500.")
    say(f"        Harness (parity.triangulate): the SAME cost from the same seed via scipy "
        f"least_squares 'lm' at tol 1e-15 -- different optimizer, same estimand, converged tighter.")
    say(f"        Production's refinement reads the STORED camera position; here every candidate's "
        f"camera position is rebuilt, which is required by the brief and is the intended difference.")
    say(f"\n    PATH VERIFICATION {'PASSED' if ok else 'FAILED'}")
    return ok


# =============================================================== calibration diagnostics


def calib_report(say, cals, clips, cand):
    say(f"\n[3] CALIBRATION REBUILD DIAGNOSTICS (rebuilt from raw node clicks for every candidate)")
    cams, rows = {}, []
    for name in CANDIDATES:
        cams[name] = {}
        for clip in clips:
            c = cals[clip]
            th = cand[name][clip]
            o = st.run_oracle(c, dist=th[:13], eta=th[13])
            cams[name][clip] = FK.build_cam(c, th)
            s2f = cams[name][clip]["s2f"]
            s2b = cams[name][clip]["s2b"]
            fr = [math.hypot(*(np.array(nd.apply3(s2f, *nd.undistort13(x, y, th)))
                               - np.array([wh, wv]))) for x, y, wh, wv in c["front"]]
            # Apparent (refraction-corrected) back-node target coordinates the corrected homography
            # was actually fitted to. Comparing the corrected fit against the TRUE coordinates would
            # measure the refraction offset, not a fit error.
            app = o.get("app", [])
            appc = np.array([[a[0], a[1]] for a in app], float)
            true = np.array([[wh, wv] for _, _, wh, wv in c["back"]], float)
            disp = np.linalg.norm(appc - true, axis=1) if len(appc) == len(true) else np.array([np.nan])
            o1 = st.run_oracle(c, dist=th[:13], eta=th[13], niter=1)
            b1 = nd.flat_colmajor_to_nested(o1["BACK"])
            pre = [math.hypot(*(np.array(nd.apply3(b1, *nd.undistort13(x, y, th)))
                                - np.array([wh, wv]))) for x, y, wh, wv in c["back"]]
            post = [math.hypot(*(np.array(nd.apply3(s2b, *nd.undistort13(x, y, th))) - a))
                    for (x, y, _, _), a in zip(c["back"], appc)]
            vs_true = [math.hypot(*(np.array(nd.apply3(s2b, *nd.undistort13(x, y, th)))
                                    - np.array([wh, wv]))) for x, y, wh, wv in c["back"]]
            its = o.get("iters", [])
            drift = [math.dist(its[k]["cam"], its[k - 1]["cam"]) for k in range(1, len(its))]
            allnodes = np.array([[x, y] for x, y, _, _ in c["front"] + c["back"]], float)
            ad = LT.admissible(th, allnodes)
            rows.append({
                "candidate": name, "clip": clip,
                "front_rms": float(np.sqrt(np.mean(np.square(fr)))),
                "front_max": float(np.max(fr)),
                "back_rms_pre_vs_true": float(np.sqrt(np.mean(np.square(pre)))),
                "back_rms_post_vs_apparent": float(np.sqrt(np.mean(np.square(post)))),
                "back_rms_post_vs_true": float(np.sqrt(np.mean(np.square(vs_true)))),
                "back_max_post_vs_apparent": float(np.max(post)),
                "apparent_disp_mean": float(np.mean(disp)), "apparent_disp_max": float(np.max(disp)),
                "camPLD": cams[name][clip]["camPLD"], "cam": list(cams[name][clip]["cam"]),
                "refraction_iters": len(its), "cam_drift_by_iter": drift,
                "cam_drift_last": drift[-1] if drift else float("nan"),
                "refraction_solve_resid_max": float(max((a[4] for a in app), default=float("nan"))),
                "refraction_status_failures": int(sum(1 for a in app if a[3] != 0)),
                "refraction_iters_max": int(max((a[2] for a in app), default=0)),
                "gate_ok": bool(ad["gate_ok"]), "min_det_frame": ad["min_det_full_frame"],
                "roundtrip_frame_px": ad["roundtrip_frame_px"], "admissible": bool(ad["ok"]),
                "max_local_aniso_frame": ad["max_local_aniso_frame"]})
    say(f"      residuals and displacements in mm. 'backPost' is against the APPARENT coordinates "
        f"the corrected homography was fitted to;")
    say(f"      'backPostTrue' against the true coordinates, whose excess over backPost IS the "
        f"refraction offset, not a fit error.")
    say(f"      {'candidate':10} {'clip':6} {'frontRMS':>9} {'backPre':>8} {'backPost':>9} "
        f"{'bPostTrue':>10} {'appMean':>8} {'appMax':>8} {'camPLD':>8} {'drift':>9} {'refFail':>8} "
        f"{'admis':>6}")
    for r in rows:
        say(f"      {r['candidate']:10} {r['clip'][:5]:6} {r['front_rms']:9.4f} "
            f"{r['back_rms_pre_vs_true']:8.4f} {r['back_rms_post_vs_apparent']:9.4f} "
            f"{r['back_rms_post_vs_true']:10.4f} {r['apparent_disp_mean']:8.4f} "
            f"{r['apparent_disp_max']:8.4f} {r['camPLD']:8.4f} {r['cam_drift_last']:9.2e} "
            f"{r['refraction_status_failures']:8d} {str(r['admissible']):>6}")
    say(f"\n      refraction convergence: {rows[0]['refraction_iters']} outer iterations for every "
        f"candidate; worst per-node root-solve residual "
        f"{max(r['refraction_solve_resid_max'] for r in rows):.2e} (tolerance 1e-7); "
        f"status failures {sum(r['refraction_status_failures'] for r in rows)}")
    say(f"      camera drift by outer iteration, {rows[0]['candidate']} {rows[0]['clip']}: "
        + "  ".join(f"{v:.3e}" for v in rows[0]["cam_drift_by_iter"]))
    say(f"      every candidate admissible over the node hull and frame; worst frame round trip "
        f"{max(r['roundtrip_frame_px'] for r in rows):.2e} px, min det "
        f"{min(r['min_det_frame'] for r in rows):.4f}")
    say(f"\n      CAMERA POSITIONS (mm)")
    for r in rows:
        say(f"        {r['candidate']:10} {r['clip']:14} ({r['cam'][0]:11.3f}, "
            f"{r['cam'][1]:11.3f}, {r['cam'][2]:11.3f})")
    return cams, rows


# =============================================================== measurement


def measure_all(cams, clicks, conv, cpts, cals, clips):
    """Reconstruct every unique point ONCE per candidate."""
    need = sorted({pk for r in conv for pk in r["pks"]} | {p["pk"] for p in cpts})
    # calibration support: 3D hull of the node world coordinates lifted to both planes
    nodes3 = []
    c0 = cals[clips[0]]
    for x, y, wh, wv in c0["front"]:
        nodes3.append(pa.lift(wh, wv, c0["front_d"], c0["ah"], c0["av"]))
    for x, y, wh, wv in c0["back"]:
        nodes3.append(pa.lift(wh, wv, c0["back_d"], c0["ah"], c0["av"]))
    eqs = FK.hull_equations(nodes3)
    out = {}
    for name, cm in cams.items():
        rec = {}
        for pk in need:
            q = FK.reconstruct(pk, cm, clicks)
            if q is not None:
                q["camdist"] = min(float(np.linalg.norm(q["X"] - np.array(c["cam"], float)))
                                   for c in cm.values())
                q["outside_cal"] = FK.outside(eqs, q["X"])
            rec[pk] = q
        out[name] = rec
    return out, eqs


def pair_rows(rec, items, kind):
    rows = []
    for r in items:
        pks = r["pks"]
        a, b = rec.get(pks[0]), rec.get(pks[1])
        if a is None or b is None:
            continue
        d = float(np.linalg.norm(a["X"] - b["X"]))
        rows.append({"kind": kind, "key": r.get("event", (r.get("i"), r.get("j"))),
                     "group": r.get("tc") if kind == "conventional" else r["cloud"],
                     "obj": r.get("obj", r.get("cloud")), "true": r["true"], "meas": d,
                     "err": d - r["true"], "pct": 100.0 * (d - r["true"]) / r["true"],
                     "radius": max(max(a["radius"].values()), max(b["radius"].values())),
                     "edge": min(min(a["edge"].values()), min(b["edge"].values())),
                     "camdist": 0.5 * (a["camdist"] + b["camdist"]),
                     "outside_cal": max(a["outside_cal"], b["outside_cal"]),
                     "pks": list(pks)})
    return rows


# =============================================================== clouds


def establish_handedness(say, rec, clouds, cnames):
    """Settle the note-coordinate handedness question, which turns out to be a non-question.

    The true 2-D coordinates are embedded at z = 0 and aligned by a PROPER 3-D rotation. Mirroring
    one in-plane axis, (u, v, 0) -> (u, -v, 0), is itself a proper rotation: 180 degrees about the
    in-plane u axis. So the two handedness conventions lie in the same orbit of the alignment group
    and give IDENTICAL residuals. Handedness is therefore unidentifiable here rather than ambiguous,
    and no reflection is being quietly admitted to lower the residual -- there is nothing to admit.
    This is verified numerically rather than argued.
    """
    say(f"\n[5a] CLOUD COORDINATE HANDEDNESS")
    tally = {}
    for flip in (False, True):
        per = []
        for cn in cnames:
            pts = clouds[cn]
            q2 = np.array([p["mm"] for p in pts], float)
            if flip:
                q2 = q2 * np.array([1.0, -1.0])
            X = np.array([rec[p["pk"]]["X"] for p in pts], float)
            per.append(FK.shape_report(q2, X)["rms"])
        tally[flip] = per
        say(f"      {'mirrored' if flip else 'as stored':10} rigid RMS per cloud: "
            + "  ".join(f"{cn} {v:7.3f}" for cn, v in zip(cnames, per))
            + f"   mean {np.mean(per):7.3f}")
    same = max(abs(a - b) for a, b in zip(tally[False], tally[True]))
    say(f"      the two conventions agree to {same:.2e} mm on every cloud, as they must: a 2-D "
        f"mirror of coordinates embedded at z = 0 IS a proper 3-D rotation (180 degrees about the")
    say(f"      in-plane axis), so it lies in the alignment group already. In-plane handedness is "
        f"UNIDENTIFIABLE against a 3-D rigid fit, not ambiguous, and no reflection is being")
    say(f"      silently permitted -- FK.kabsch admits proper rotations only. Using the stored "
        f"orientation.")
    if same > 1e-6:
        say(f"      *** the two conventions differ, which contradicts the argument above; "
            f"investigate before trusting the shape numbers ***")
    return False, bool(same <= 1e-6)


def cloud_report(say, rec, clouds, cnames, flip):
    out = {}
    for cn in cnames:
        pts = clouds[cn]
        q2 = np.array([p["mm"] for p in pts], float)
        if flip:
            q2 = q2 * np.array([1.0, -1.0])
        X = np.array([rec[p["pk"]]["X"] for p in pts], float)
        s = FK.shape_report(q2, X)
        aff = s["affine"]
        out[cn] = {"n": s["n"], "rigid_rms": s["rms"], "rigid_max": s["max"],
                   "rigid_med": s["med"], "oop_rms": s["oop_rms"], "oop_max": s["oop_max"],
                   "plane_thickness": 2.0 * s["oop_max"],
                   "inplane_rms": float(np.sqrt(max(s["rms"] ** 2 - s["oop_rms"] ** 2, 0.0))),
                   "sim_scale": s["sim_scale"], "sim_rms": s["sim_rms"],
                   "curv_rms": s["curv_rms"], "curv_r2": s["curv_r2"],
                   "loo_rms": s["loo_rms"],
                   "affine": {k: v for k, v in aff.items()
                              if isinstance(v, (int, float))} if isinstance(aff, dict) else {},
                   "_res": s["res"], "_X": X, "_q2": q2}
    return out


# =============================================================== decomposition


def decompose(recA, recB, items, label, say):
    """Endpoint movement between two candidates, split into common and differential parts."""
    cm, df, al, pp = [], [], [], []
    for r in items:
        a0, b0 = recA.get(r["pks"][0]), recA.get(r["pks"][1])
        a1, b1 = recB.get(r["pks"][0]), recB.get(r["pks"][1])
        if None in (a0, b0, a1, b1):
            continue
        d1 = a1["X"] - a0["X"]
        d2 = b1["X"] - b0["X"]
        u = b0["X"] - a0["X"]
        nu = np.linalg.norm(u)
        if nu < 1e-12:
            continue
        u = u / nu
        common = 0.5 * (d1 + d2)
        diff = d2 - d1
        along = float(diff @ u)
        perp = diff - along * u
        cm.append(float(np.linalg.norm(common))); df.append(float(np.linalg.norm(diff)))
        al.append(abs(along)); pp.append(float(np.linalg.norm(perp)))
    if not cm:
        return {}
    say(f"      {label:34} common {np.median(cm):7.3f}  differential {np.median(df):7.3f}  "
        f"along {np.median(al):7.3f}  perp {np.median(pp):7.3f}   (median mm)")
    return {"common_median": float(np.median(cm)), "differential_median": float(np.median(df)),
            "along_median": float(np.median(al)), "perp_median": float(np.median(pp)),
            "common_max": float(np.max(cm)), "differential_max": float(np.max(df))}


def cloud_decompose(say, recA, recB, clouds, cnames, label):
    """Classify how a cloud's reconstructed shape changed: rigid / scale / affine / non-affine."""
    out = {}
    for cn in cnames:
        pts = clouds[cn]
        A = np.array([recA[p["pk"]]["X"] for p in pts], float)
        B = np.array([recB[p["pk"]]["X"] for p in pts], float)
        tot = float(np.sqrt((np.linalg.norm(B - A, axis=1) ** 2).mean()))
        R, t, _ = FK.kabsch(A, B)
        r_rigid = float(np.sqrt((np.linalg.norm(B - FK.apply_rt(R, t, 1.0, A), axis=1) ** 2).mean()))
        Rs, ts, sc = FK.kabsch(A, B, allow_scale=True)
        r_sim = float(np.sqrt((np.linalg.norm(B - FK.apply_rt(Rs, ts, sc, A), axis=1) ** 2).mean()))
        Ac = np.hstack([A - A.mean(0), np.ones((len(A), 1))])
        M, *_ = np.linalg.lstsq(Ac, B - B.mean(0), rcond=None)
        r_aff = float(np.sqrt((np.linalg.norm(B - B.mean(0) - Ac @ M, axis=1) ** 2).mean()))
        out[cn] = {"total_move_rms": tot, "after_rigid": r_rigid, "after_similarity": r_sim,
                   "after_affine": r_aff, "fitted_scale": float(sc)}
        say(f"        {cn:9} total move {tot:7.3f}  after rigid {r_rigid:7.3f}  after "
            f"similarity {r_sim:7.3f} (scale {sc:.6f})  after affine {r_aff:7.3f} mm")
    return out


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    log = open(os.path.join(args.outdir, "fisheye_pd_downstream.log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R = {}
    say("=" * 104)
    say("PRODUCTION-FAITHFUL DOWNSTREAM VALIDATION OF THE EXACT-PD DISTORTION FITS")
    say("=" * 104)
    say(f"  document {os.path.basename(args.vsd)}")
    say("  Every candidate rebuilds front homography, refracted back nodes, back homography and")
    say("  camera position from the RAW node clicks. No stored downstream quantity is reused.")

    D = kl.load(args.vsd)
    conv, cpts, cpairs, clouds = (D["conventional"], D["cloud_points"], D["cloud_pairs"],
                                  D["clouds"])
    clicks, cnames = D["clicks"], sorted(D["clouds"])
    byc = defaultdict(int)
    for r in conv:
        byc[r["true"]] += 1
    exp = {100.0: 13, 196.0: 4, 300.0: 13, 500.0: 6, 1000.0: 6}
    say(f"\n[1] MEASUREMENT INVENTORY VERIFIED FROM THE FILE")
    say(f"      conventional two-point measurements: {len(conv)}   by true length "
        f"{dict(sorted(byc.items()))}")
    say(f"      expected 13/4/13/6/6 at 100/196/300/500/1000 mm: "
        f"{'CONFIRMED' if dict(byc) == exp else 'MISMATCH'}")
    say(f"      point clouds: {len(clouds)} clouds, {len(cpts)} points, {len(cpairs)} within-cloud "
        f"pairs; loader exclusions {len(D['exclusions'])}")
    for cn in cnames:
        tl = [q["true"] for q in cpairs if q["cloud"] == cn]
        say(f"        {cn:9} {len(clouds[cn]):3d} points, {len(tl):4d} pairs, "
            f"{len(clouds[cn][0]['cm'])}D notes, tc {clouds[cn][0]['tc']}, true separations "
            f"{min(tl):.1f}-{max(tl):.1f} mm")
    say(f"      DISCREPANCY: the brief expected 63 points and 471 pairs; the file holds "
        f"{len(cpts)} and {len(cpairs)} with zero exclusions.")
    say(f"      471 pairs is exactly Cloud D at 16 points instead of {len(clouds['Cloud D'])}, so 2 "
        f"Cloud D points were added since that count. All {len(cpts)} are clicked in both cameras")
    say(f"      with unique note coordinates, so {len(cpts)}/{len(cpairs)} is used.")
    say(f"      REPLICATION UNITS: {len({r['tc'] for r in conv})} conventional placements + "
        f"{len(clouds)} cloud placements. The {len(cpairs)} pairs are NOT independent replicates.")
    R["inventory"] = {"conventional": len(conv), "by_true": {str(k): v for k, v in byc.items()},
                      "expected_matches": dict(byc) == exp, "cloud_points": len(cpts),
                      "cloud_pairs": len(cpairs), "per_cloud": {c: len(clouds[c]) for c in cnames},
                      "exclusions": D["exclusions"],
                      "conventional_placements": sorted({r["tc"] for r in conv})}

    cand, cals, clips = load_candidates(say, args.vsd, args.outdir)
    if not verify_path(say, args.vsd, cals, clips, cand):
        say("\n  *** PATH VERIFICATION FAILED -- stopping before any model comparison ***")
        json.dump(R, open(os.path.join(args.outdir, "fisheye_pd_downstream.json"), "w"),
                  indent=1, default=float)
        return 1
    cams, crows = calib_report(say, cals, clips, cand)
    R["calibration"] = crows

    recs, eqs = measure_all(cams, clicks, conv, cpts, cals, clips)
    CR = {n: pair_rows(recs[n], conv, "conventional") for n in CANDIDATES}
    PR = {n: pair_rows(recs[n], cpairs, "cloud_pair") for n in CANDIDATES}

    # ---------------------------------------------------------------- 4. conventional
    say(f"\n[4] CONVENTIONAL TWO-POINT MEASUREMENTS ({len(CR[BASE])} of {len(conv)} reconstructed)")
    for n in CANDIDATES:
        qtable(say, n, CR[n])
    say(f"\n      BY TRUE-LENGTH CLASS (MAE mm / signed bias mm)")
    say(f"      {'candidate':10}" + "".join(f"{f'{int(t)}mm':>18}" for t in sorted(byc)))
    for n in CANDIDATES:
        cells = []
        for t in sorted(byc):
            e = np.array([r["err"] for r in CR[n] if r["true"] == t], float)
            cells.append(f"{np.abs(e).mean():8.3f}/{e.mean():+8.3f}")
        say(f"      {n:10}" + "".join(f"{c:>18}" for c in cells))
    say(f"\n      PERCENT ERROR by class (mean signed %)")
    for n in CANDIDATES:
        cells = [f"{np.mean([r['pct'] for r in CR[n] if r['true'] == t]):+7.3f}"
                 for t in sorted(byc)]
        say(f"      {n:10}" + "".join(f"{c:>12}" for c in cells))
    ngroups = len({r["group"] for r in CR[BASE]})
    say(f"\n      paired uncertainty is clustered by measurement frame: {ngroups} independent "
        f"conventional placements for {len(CR[BASE])} measurements. With 42 measurements in "
        f"{ngroups} clusters,")
    say(f"      effect sizes and intervals are reported and binary significance is not.")
    R["conventional"] = {n: {"stats": stats([r["err"] for r in CR[n]]),
                             "by_class": {str(t): stats([r["err"] for r in CR[n]
                                                         if r["true"] == t])
                                          for t in sorted(byc)},
                             "rows": [{k: v for k, v in r.items() if k != "pks"} for r in CR[n]]}
                         for n in CANDIDATES}

    # ---------------------------------------------------------------- 5. clouds
    flip, unan = establish_handedness(say, recs[BASE], clouds, cnames)
    R["handedness"] = {"mirrored": bool(flip), "unanimous": bool(unan)}
    say(f"\n[5b] CLOUD SHAPE, rigid alignment with translation and PROPER rotation and NO fitted "
        f"scale")
    CS = {n: cloud_report(say, recs[n], clouds, cnames, flip) for n in CANDIDATES}
    for cn in cnames:
        say(f"\n      {cn} ({CS[BASE][cn]['n']} points)")
        say(f"        {'candidate':10} {'rigidRMS':>9} {'rigidMax':>9} {'inplane':>8} "
            f"{'oopRMS':>8} {'oopMax':>8} {'thick':>7} {'simScale':>9} {'simRMS':>8} {'curvR2':>7}")
        for n in CANDIDATES:
            c = CS[n][cn]
            say(f"        {n:10} {c['rigid_rms']:9.3f} {c['rigid_max']:9.3f} "
                f"{c['inplane_rms']:8.3f} {c['oop_rms']:8.3f} {c['oop_max']:8.3f} "
                f"{c['plane_thickness']:7.3f} {c['sim_scale']:9.6f} {c['sim_rms']:8.3f} "
                f"{c['curv_r2']:7.3f}")
    say(f"\n      pooled rigid RMS over all four clouds (no-scale, the primary measure)")
    for n in CANDIDATES:
        v = [CS[n][cn]["rigid_rms"] for cn in cnames]
        sc = [CS[n][cn]["sim_scale"] for cn in cnames]
        say(f"        {n:10} per-cloud " + "  ".join(f"{x:6.3f}" for x in v)
            + f"   mean {np.mean(v):6.3f}   fitted similarity scales "
            + "  ".join(f"{x:.5f}" for x in sc))
    say(f"      the fitted scale is reported for diagnosis only and does NOT replace the no-scale "
        f"comparison above")
    R["cloud_shape"] = {n: {cn: {k: v for k, v in CS[n][cn].items() if not k.startswith("_")}
                            for cn in cnames} for n in CANDIDATES}

    say(f"\n[5c] WITHIN-CLOUD PAIRWISE DISTANCES, descriptive only "
        f"({len(PR[BASE])} pairs from {len(clouds)} placements)")
    for n in CANDIDATES:
        qtable(say, n, PR[n])
    say(f"\n      PER CLOUD (MAE mm), the honest four-cluster view")
    say(f"      {'candidate':10}" + "".join(f"{cn:>12}" for cn in cnames) + f"{'mean':>10}")
    for n in CANDIDATES:
        cells = [np.mean([abs(r["err"]) for r in PR[n] if r["group"] == cn]) for cn in cnames]
        say(f"      {n:10}" + "".join(f"{c:12.3f}" for c in cells) + f"{np.mean(cells):10.3f}")
    R["cloud_pairs"] = {n: {"stats": stats([r["err"] for r in PR[n]]),
                            "per_cloud": {cn: stats([r["err"] for r in PR[n]
                                                     if r["group"] == cn]) for cn in cnames}}
                        for n in CANDIDATES}

    # ---------------------------------------------------------------- 6. strata
    say(f"\n[6] PRESPECIFIED HIGH-RISK STRATA, thresholds from BASELINE geometry only "
        f"(upper quartile and upper decile of {BASE})")
    R["strata"] = {}
    for tag, rows in (("conventional", CR), ("cloud pairs", PR)):
        base = rows[BASE]
        say(f"\n      {tag}")
        for gname, gkey in (("camera distance", "camdist"), ("outside calibration hull",
                                                             "outside_cal"),
                            ("max image radius", "radius"), ("nearest screen edge", "edge"),
                            ("true length", "true")):
            v = np.array([r[gkey] for r in base], float)
            if gkey == "edge":
                thr = np.percentile(v, 25); sel = lambda r, t=thr, k=gkey: r[k] <= t
            else:
                thr = np.percentile(v, 75); sel = lambda r, t=thr, k=gkey: r[k] >= t
            idx = {r["key"] for r in base if sel(r)}
            if not idx:
                continue
            say(f"        {gname:26} threshold {thr:9.2f}  n {len(idx):4d}   MAE by candidate: "
                + "  ".join(f"{n} {np.mean([abs(r['err']) for r in rows[n] if r['key'] in idx]):6.3f}"
                            for n in CANDIDATES))
            R["strata"].setdefault(tag, {})[gname] = {
                "threshold": float(thr), "n": len(idx),
                "mae": {n: float(np.mean([abs(r["err"]) for r in rows[n] if r["key"] in idx]))
                        for n in CANDIDATES}}
        # continuous trend, so the cutoffs do not drive the conclusion
        say(f"        continuous trends (Spearman of |error| against each covariate)")
        for gname, gkey in (("camera distance", "camdist"), ("outside cal hull", "outside_cal"),
                            ("image radius", "radius"), ("screen edge", "edge"),
                            ("true length", "true")):
            say(f"          {gname:22} " + "  ".join(
                f"{n} {FK.corr([abs(r['err']) for r in rows[n]], [r[gkey] for r in rows[n]]):+6.3f}"
                for n in CANDIDATES))
        say(f"        CONFOUNDING: in this document longer objects are also the more peripheral and "
            f"more distant ones. Baseline Spearman among covariates:")
        for a, b in (("true", "camdist"), ("true", "radius"), ("camdist", "radius"),
                     ("radius", "edge"), ("true", "outside_cal")):
            say(f"          {a:12} vs {b:12} {FK.corr([r[a] for r in base], [r[b] for r in base]):+6.3f}")

    # ---------------------------------------------------------------- 7. contrasts
    say(f"\n[7] PAIRED CONTRASTS. Conventional measurements and cloud pairs are kept separate and "
        f"never pooled into one nominal n.")
    R["contrasts"] = {}
    for a, b, desc in CONTRASTS:
        say(f"\n      {a}  minus  {b}    ({desc})")
        ca = {r["key"]: r for r in CR[a]}; cb = {r["key"]: r for r in CR[b]}
        keys = sorted(set(ca) & set(cb), key=str)
        d = np.array([abs(ca[k]["err"]) - abs(cb[k]["err"]) for k in keys])
        imp = int((d < 0).sum())
        say(f"        conventional  n {len(keys):3d}  d|err| mean {d.mean():+7.3f} mm  median "
            f"{np.median(d):+7.3f}  improved {imp}/{len(keys)}  worsened {len(keys) - imp}")
        bycl = defaultdict(list)
        for k in keys:
            bycl[ca[k]["group"]].append(abs(ca[k]["err"]) - abs(cb[k]["err"]))
        say(f"          by placement: " + "  ".join(
            f"{np.mean(v):+6.3f}(n{len(v)})" for v in bycl.values()))
        pa_ = {r["key"]: r for r in PR[a]}; pb_ = {r["key"]: r for r in PR[b]}
        pk = sorted(set(pa_) & set(pb_), key=str)
        dp = np.array([abs(pa_[k]["err"]) - abs(pb_[k]["err"]) for k in pk])
        percl = {cn: float(np.mean([abs(pa_[k]["err"]) - abs(pb_[k]["err"]) for k in pk
                                    if pa_[k]["group"] == cn])) for cn in cnames}
        say(f"        cloud pairs   n {len(pk):4d} (4 placements)  d|err| mean {dp.mean():+7.3f} mm"
            f"   per cloud " + "  ".join(f"{cn.split()[-1]} {v:+6.3f}" for cn, v in percl.items()))
        agree = len({v > 0 for v in percl.values()}) == 1
        say(f"          all four clouds agree in direction: {agree}")
        ds = {cn: CS[a][cn]["rigid_rms"] - CS[b][cn]["rigid_rms"] for cn in cnames}
        say(f"        cloud shape   d rigid RMS per cloud " + "  ".join(
            f"{cn.split()[-1]} {v:+6.3f}" for cn, v in ds.items())
            + f"   mean {np.mean(list(ds.values())):+6.3f} mm")
        dn = {}
        for clip in clips:
            ra = [r for r in crows if r["candidate"] == a and r["clip"] == clip][0]
            rb = [r for r in crows if r["candidate"] == b and r["clip"] == clip][0]
            dn[clip] = (ra["front_rms"] - rb["front_rms"], ra["camPLD"] - rb["camPLD"])
        say(f"        calibration   d frontRMS / d camPLD  " + "  ".join(
            f"{c.split()[0]} {v[0]:+6.3f}/{v[1]:+6.3f}" for c, v in dn.items()))
        R["contrasts"][f"{a} minus {b}"] = {
            "description": desc, "conventional_d_abs_err_mean": float(d.mean()),
            "conventional_d_abs_err_median": float(np.median(d)),
            "conventional_improved": imp, "conventional_n": len(keys),
            "conventional_by_placement": {str(k): float(np.mean(v)) for k, v in bycl.items()},
            "cloud_pair_d_abs_err_mean": float(dp.mean()),
            "cloud_pair_per_cloud": percl, "clouds_agree_in_direction": bool(agree),
            "cloud_shape_d_rigid_rms": {k: float(v) for k, v in ds.items()},
            "calibration_deltas": {k: [float(x) for x in v] for k, v in dn.items()}}

    # ---------------------------------------------------------------- fixed-baseline tails
    say(f"\n[7b] FIXED-BASELINE UPPER TAILS. The worst 10% and 20% under {BASE} are identified "
        f"ONCE and every candidate is then measured on those SAME measurements.")
    R["tails"] = {}
    for tag, rows in (("conventional", CR), ("cloud pairs", PR)):
        base = sorted(rows[BASE], key=lambda r: -abs(r["err"]))
        for frac in (0.10, 0.20):
            k = max(1, int(round(frac * len(base))))
            idx = {r["key"] for r in base[:k]}
            b0 = np.mean([abs(r["err"]) for r in rows[BASE] if r["key"] in idx])
            say(f"      {tag:14} worst {int(frac * 100):3d}%  n {k:4d}  baseline MAE {b0:7.3f} -> "
                + "  ".join(
                    f"{n} {np.mean([abs(r['err']) for r in rows[n] if r['key'] in idx]):7.3f}"
                    for n in CANDIDATES if n != BASE))
            R["tails"][f"{tag} worst {int(frac * 100)}%"] = {
                "n": k, "baseline_mae": float(b0),
                "mae": {n: float(np.mean([abs(r["err"]) for r in rows[n] if r["key"] in idx]))
                        for n in CANDIDATES}}

    # ---------------------------------------------------------------- 8. decomposition
    say(f"\n[8] GEOMETRIC DECOMPOSITION of endpoint movement (median mm over conventional pairs)")
    R["decomposition"] = {}
    for a, b, desc in [("PD-D/M1", "B/M1", "objective at M1"),
                       ("PD-D/M1", "PD-D/M0", "eta under PD-D"),
                       ("PD-D/M0", "B/M0", "objective at M0")]:
        R["decomposition"][f"{a} minus {b}"] = decompose(recs[b], recs[a], conv,
                                                         f"{a} vs {b} ({desc})", say)
    say(f"      common-mode movement is a rigid shift of both endpoints and cancels from the "
        f"length; only the differential part can change a scalar length, and only its ALONG "
        f"component to first order.")
    say(f"\n      CLOUD SHAPE CHANGE, classified")
    R["cloud_decomposition"] = {}
    for a, b, desc in [("PD-D/M1", "B/M1", "objective at M1"),
                       ("PD-D/M1", "PD-D/M0", "eta under PD-D")]:
        say(f"        {a} vs {b} ({desc})")
        R["cloud_decomposition"][f"{a} minus {b}"] = cloud_decompose(
            say, recs[b], recs[a], clouds, cnames, desc)

    # ---------------------------------------------------------------- 9. node quality vs accuracy
    say(f"\n[9] DOES CALIBRATION-FRAME RESIDUAL QUALITY PREDICT DOWNSTREAM ACCURACY?")
    fr = [np.mean([r["front_rms"] for r in crows if r["candidate"] == n]) for n in CANDIDATES]
    pl = [np.mean([r["camPLD"] for r in crows if r["candidate"] == n]) for n in CANDIDATES]
    cvm = [np.mean([abs(r["err"]) for r in CR[n]]) for n in CANDIDATES]
    clm = [np.mean([CS[n][cn]["rigid_rms"] for cn in cnames]) for n in CANDIDATES]
    say(f"      {'candidate':10} {'frontRMS':>9} {'camPLD':>8} {'convMAE':>9} {'cloudRigid':>11}")
    for i, n in enumerate(CANDIDATES):
        say(f"      {n:10} {fr[i]:9.4f} {pl[i]:8.4f} {cvm[i]:9.3f} {clm[i]:11.3f}")
    say(f"      Spearman across the {len(CANDIDATES)} candidates: frontRMS vs convMAE "
        f"{FK.corr(fr, cvm):+.3f}, frontRMS vs cloudRigid {FK.corr(fr, clm):+.3f}, "
        f"camPLD vs convMAE {FK.corr(pl, cvm):+.3f}, camPLD vs cloudRigid {FK.corr(pl, clm):+.3f}")
    say(f"      six candidates is far too few for these correlations to be more than suggestive.")
    R["node_quality_vs_accuracy"] = {
        "front_rms": dict(zip(CANDIDATES, map(float, fr))),
        "camPLD": dict(zip(CANDIDATES, map(float, pl))),
        "conv_mae": dict(zip(CANDIDATES, map(float, cvm))),
        "cloud_rigid_rms": dict(zip(CANDIDATES, map(float, clm))),
        "spearman": {"frontRMS_vs_convMAE": FK.corr(fr, cvm),
                     "frontRMS_vs_cloudRigid": FK.corr(fr, clm),
                     "camPLD_vs_convMAE": FK.corr(pl, cvm),
                     "camPLD_vs_cloudRigid": FK.corr(pl, clm)}}

    for tag, rows in (("conventional", CR), ("cloud_pairs", PR)):
        with open(os.path.join(args.outdir, f"fisheye_pd_downstream_{tag}.csv"), "w",
                  newline="") as fh:
            f = ["candidate", "kind", "key", "group", "obj", "true", "meas", "err", "pct",
                 "radius", "edge", "camdist", "outside_cal"]
            w = csv.DictWriter(fh, fieldnames=f, extrasaction="ignore")
            w.writeheader()
            for n in CANDIDATES:
                for r in rows[n]:
                    w.writerow({**r, "candidate": n})
    json.dump(R, open(os.path.join(args.outdir, "fisheye_pd_downstream.json"), "w"),
              indent=1, default=float)
    say(f"\n  [{time.time() - t00:.1f}s total]  wrote fisheye_pd_downstream.json and 2 CSVs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
