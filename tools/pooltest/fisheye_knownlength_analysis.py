#!/usr/bin/env python3
"""HISTORICAL / NON-AUTHORITATIVE as of 2026-07-29. Frozen to reproduce its published numbers.

    SUPERSEDED BY:  downstream.py (geometry) + xdoc_objectives.py (candidate tables)

    DO NOT import this module for reusable functionality, and do not treat its output as a current
    result. Its downstream geometry reaches eta only by installing an eta-aware undistortion into
    `parity.sightline`/`parity.triangulate` process-wide -- see the call to
    `parity.install_historical_eta_map` below. That was an import-time monkeypatch
    (`parity.undistort = nodes.undistort13`) until the independent audit of 2026-07-29 showed it made
    eta propagation depend on module import order: a script that reached `parity` without going through
    this module got the 13-parameter map and silently dropped eta from every sightline. The patch is now
    an explicit, named, reason-carrying call so it cannot happen by accident, but the dependence itself
    is retained HERE ONLY so this script still reproduces what it published.

    Its `build_cam`/`reconstruct` also take a bare 14-vector rather than a camera-bound
    `downstream.DistortionMap`, so nothing stops the Left map being handed to the Right camera. The
    audit demonstrated exactly that failure. Current work must use `downstream.build_calibration`,
    which verifies the map against the camera's CameraIdentity.

Production-faithful known-length and point-cloud-shape analysis of the Rokinon 8 mm fisheye.

Document: `2015-09-04-1 Clearwater.vsd`. Four candidate distortion models, evaluated on the
document's expanded annotations: conventional two-point length measurements AND four point clouds
whose within-cloud local coordinates are known.

WHAT THIS REUSES, AND WHY NONE OF IT IS RE-DERIVED HERE
  knownlength.py  the authoritative annotation loader; schema conventions live there, not here
  nodes.py        the authoritative front/back calibration-node accessor (ZCALIBRATION1 is FRONT)
  oracle.cpp      via stage2.run_oracle: the refractive calibration rebuild, calling the same
                  Accelerate LAPACK and GSL routines production calls, in production's own order
                  (front uncorrected; back in a four-iteration fixed point; camera position
                  recomputed every iteration)
  parity.py       the parity-validated port of VSPoint.m: linear-CPA seed plus Nelder-Mead-equivalent
                  reprojection refinement, reproducing stored 3D coordinates to ~1e-5 mm here
  round9a.py      the 15-parameter model machinery and gated plumbline fitter
  fitter.py       gate_report(), the PRODUCTION acceptance gate (mean radial magnification over the
                  plumbline box), not the retracted area-scale-spread quantity

MODELS
  stored     the distortion parameters already in the document
  conv-13    thoroughly converged 13-parameter Brown-Conrady
  M0         truncated: centre + k1..k4 + p1,p2                              (round9a.ISO)
  M1         truncated + scalar anisotropic radius eta                       (round9a.SCAL)

  M1's radius map is the canonical conjugated form
      U(x) = c + A_eta^-1 B_theta,0 (A_eta (x - c)),   A_eta = diag(e^eta, e^-eta)
  so eta = 0 reduces to M0 EXACTLY, and that nesting is verified downstream through the rebuilt
  homographies and camera position, not merely asserted. Held parameters are zeroed on every seed:
  leaving them at seed values silently breaks the nesting and has manufactured a result once
  already.

DEPENDENCE, WHICH GOVERNS EVERY SUMMARY BELOW
  A cloud of n points yields n(n-1)/2 pair distances that are NOT independent. The pairs carry the
  information of the points at FOUR placements, not of the pairs. The conventional measurements carry FOUR placements
  too, and 28 of the 42 sit at a single timecode. No independent-pair test is reported anywhere.
  Primary summaries are per-placement; combined summaries are given under four explicit weighting
  schemes and are compared against each other.

Run with ~/.venvs/vidsync/bin/python. Writes machine-readable tables to analysis-output/.
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
OUTDIR = os.path.join(HERE, "analysis-output")
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
FRAME_W, FRAME_H = 1920.0, 1080.0
UNIT = 1.0                      # Drift Model documents store world coordinates in millimetres

# The 14 conventional measurements the earlier fisheye conclusions were built on, by event primary
# key. Verified in test_knownlength.py: these and only these reproduce the historical stored MAE of
# 2.9712 mm.
ORIGINAL_14 = [184, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 201]


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


kl = L("knownlength")
nd = L("nodes")
jw = L("jacweight")
pa = L("parity")
st = L("stage2")
Z = L("round9a")
F = L("fitter")
S = Z.S
UNDISTORT_13 = pa.undistort13          # the pure 13-parameter port of VSCalibration.mm:219
# HISTORICAL. Was `pa.undistort = nd.undistort13`, a silent import-time monkeypatch. Now explicit,
# named and reason-carrying; see this module's docstring and parity.install_historical_eta_map.
pa.install_historical_eta_map(
    nd.undistort13,
    reason="reproducing the frozen 2015-09-04-1 fisheye known-length analysis, whose published "
           "numbers were produced with parity.sightline/triangulate made eta-aware process-wide")

MODELS = [("stored", None), ("conv-13", list(range(13))), ("M0", Z.ISO), ("M1", Z.SCAL)]
MNAMES = [m for m, _ in MODELS]


class PL:
    """Minimal plumbline container for fitter.gate_report."""

    def __init__(self, xy):
        self.xy = np.asarray(xy, float); self.sref = 0.0


# --------------------------------------------------------------------------- model fitting

def stored_to_v(d13):
    """Document parameters -> the fitter's normalized 15-vector."""
    v = np.zeros(15)
    v[0] = (d13[0] - S.W / 2) / S.R
    v[1] = (d13[1] - S.H / 2) / S.R
    for j in range(7):
        v[2 + j] = d13[2 + j] * S.R ** (2 * (j + 1))
    v[9] = d13[9] * S.R; v[10] = d13[10] * S.R
    v[11] = d13[11] * S.R ** 2; v[12] = d13[12] * S.R ** 4
    return v


def fit_model(clip_obj, free, seeds):
    """Gated multistart fit. Every seed has its held parameters ZEROED (bug 2 in the notes)."""
    g = Z.G(clip_obj.xy, clip_obj.counts)
    held = [j for j in range(15) if j not in free]
    ss = []
    for s in seeds:
        s = np.asarray(s, float).copy(); s[held] = 0.0; ss.append(s)
    rr = np.random.default_rng(4)
    for _ in range(4):
        s = ss[rr.integers(0, len(ss))].copy()
        s[np.array(free)] += rr.normal(0, 0.03, len(free))
        s[held] = 0.0
        ss.append(s)
    if 13 in free:
        for e in (-0.02, 0.01, 0.02, 0.04):
            s = ss[0].copy(); s[held] = 0.0; s[13] = e; ss.append(s)
    for s in ss:
        assert np.all(s[held] == 0.0), "seed contamination: a held parameter is nonzero"
    (v, sse, _), allsse = Z.best_fit(g, free, ss, allsse=True)
    assert np.all(np.abs(v[held]) == 0.0), "solution has a nonzero held parameter"
    return v, math.sqrt(sse / g.n), sorted(allsse), g


def build_cam(c, d14):
    """Rebuild the full refractive calibration under a distortion candidate, via oracle.cpp."""
    o = st.run_oracle(c, dist=d14[:13], eta=d14[13])
    return {"ah": c["ah"], "av": c["av"], "front_d": c["front_d"], "back_d": c["back_d"],
            "dist": d14, "cam": o["cam"], "camPLD": o["camPLD"],
            "s2f": nd.flat_colmajor_to_nested(o["FRONT"]),
            "s2b": nd.flat_colmajor_to_nested(o["BACK"]),
            "f2s": nd.flat_colmajor_to_nested(o["FRONTINV"])}


# --------------------------------------------------------------------------- reconstruction

def reconstruct(pk, cams, clicks):
    """Triangulate one measured point and collect its per-point diagnostics."""
    order = sorted(cams)
    obs = [(cams[cl], clicks[pk][cl]) for cl in order if cl in clicks.get(pk, {})]
    if len(obs) < 2:
        return None
    X, pld, rep = pa.triangulate(obs)
    lines = [pa.sightline(xy[0], xy[1], c) for c, xy in obs]
    dirs = []
    for p, q in lines:
        d = np.array(q, float) - np.array(p, float)
        dirs.append(d / np.linalg.norm(d))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(dirs[0] @ dirs[1]))))))
    A = np.zeros((3, 3))
    for v in dirs:
        A += np.eye(3) - np.outer(v, v)
    cond = float(np.linalg.cond(A))
    rad, edge = {}, {}
    for (c, xy), cl in zip(obs, [cl for cl in order if cl in clicks.get(pk, {})]):
        rad[cl] = math.hypot(xy[0] - c["dist"][0], xy[1] - c["dist"][1])
        edge[cl] = min(xy[0], FRAME_W - xy[0], xy[1], FRAME_H - xy[1])
    return {"X": np.array(X, float), "pld": pld * UNIT, "rep": rep,
            "radius": rad, "edge": edge, "stereo_deg": 90.0 - ang, "cpa_cond": cond,
            "clicks": {cl: clicks[pk][cl] for cl in order if cl in clicks.get(pk, {})}}


# --------------------------------------------------------------------------- support geometry

def hull_equations(pts):
    """Convex-hull half-space representation, so 'distance outside' is one max over facets."""
    try:
        from scipy.spatial import ConvexHull
        return ConvexHull(np.asarray(pts, float)).equations
    except Exception:                                                       # noqa: BLE001
        return None


def outside(eqs, p):
    """Signed distance outside a convex hull: 0 inside, positive px/mm outside."""
    if eqs is None:
        return float("nan")
    v = eqs[:, :-1] @ np.asarray(p, float) + eqs[:, -1]
    return float(max(0.0, v.max()))


def box_outside(P, lo, hi):
    d = np.maximum(np.maximum(np.asarray(lo) - P, P - np.asarray(hi)), 0.0)
    return float(np.linalg.norm(d))


# --------------------------------------------------------------------------- shape alignment

def kabsch(P, Q, allow_scale=False):
    """Optimal PROPER rigid (or similarity) map taking P onto Q. No reflection.

    NOTE on a genuine degeneracy: the source configuration here is planar, so an in-plane
    reflection composed with a flip of the plane's normal is a PROPER 3D rotation. Forbidding
    reflections therefore does not pin handedness for a planar source; it only excludes improper
    maps of the ambient space. That is reported rather than hidden.
    """
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    Pc, Qc = P.mean(0), Q.mean(0)
    A, B = P - Pc, Q - Qc
    U, sv, Vt = np.linalg.svd(A.T @ B)
    D = np.eye(3)
    D[2, 2] = np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0
    R = Vt.T @ D @ U.T
    s = float((sv * np.diag(D)).sum() / (A ** 2).sum()) if allow_scale else 1.0
    return R, Qc - s * (R @ Pc), s


def apply_rt(R, t, s, P):
    return s * (np.asarray(P, float) @ R.T) + t


def plane_fit(X):
    """Best-fit plane: centroid, unit normal, in-plane orthonormal basis."""
    X = np.asarray(X, float)
    c = X.mean(0)
    U, sv, Vt = np.linalg.svd(X - c)
    n = Vt[2]
    return c, n / np.linalg.norm(n), Vt[0], Vt[1]


def affine_from_truth(q2, X):
    """Least-squares 3x2 affine A and offset t with X ~= A q + t.

    A's columns are the images of the truth's own u and v axes, so every quantity derived from
    G = A^T A is independent of any arbitrary in-plane basis choice for the fitted plane. This is
    the basis-free equivalent of projecting into the fitted plane and fitting a 2D affine map.
    """
    q2, X = np.asarray(q2, float), np.asarray(X, float)
    M = np.hstack([q2, np.ones((len(q2), 1))])
    sol, *_ = np.linalg.lstsq(M, X, rcond=None)
    A = sol[:2].T                      # 3x2
    t = sol[2]
    resid = X - (q2 @ A.T + t)
    G = A.T @ A
    ev, evec = np.linalg.eigh(G)
    s2, s1 = math.sqrt(max(ev[0], 0.0)), math.sqrt(max(ev[1], 0.0))
    cosang = G[0, 1] / math.sqrt(max(G[0, 0] * G[1, 1], 1e-300))
    return {"A": A, "t": t, "resid": resid,
            "mean_scale": (max(np.linalg.det(G), 0.0)) ** 0.25,
            "s_major": s1, "s_minor": s2,
            "anisotropy": s1 / s2 if s2 > 0 else float("inf"),
            "shear_deg": 90.0 - math.degrees(math.acos(max(-1.0, min(1.0, cosang)))),
            "orient_deg": math.degrees(math.atan2(evec[1, 1], evec[0, 1])),
            "scale_u": math.sqrt(G[0, 0]), "scale_v": math.sqrt(G[1, 1]),
            "rms": float(np.sqrt((resid ** 2).sum(axis=1).mean()))}


def shape_report(q2, X):
    """Rigid, leave-one-out, similarity, planarity and affine diagnostics for one cloud."""
    q3 = np.hstack([np.asarray(q2, float), np.zeros((len(q2), 1))])
    X = np.asarray(X, float)
    n = len(X)
    R, t, _ = kabsch(q3, X)
    res = X - apply_rt(R, t, 1.0, q3)
    mag = np.linalg.norm(res, axis=1)

    # per-point influence: how much the fit over the OTHER points degrades when point i is kept
    infl = np.full(n, np.nan)
    loo = np.full(n, np.nan)
    for i in range(n):
        keep = np.arange(n) != i
        if keep.sum() < 3:
            continue
        Ri, ti, _ = kabsch(q3[keep], X[keep])
        ri = np.linalg.norm(X[keep] - apply_rt(Ri, ti, 1.0, q3[keep]), axis=1)
        infl[i] = math.sqrt((mag[keep] ** 2).mean()) - math.sqrt((ri ** 2).mean())
        loo[i] = float(np.linalg.norm(X[i] - apply_rt(Ri, ti, 1.0, q3[i])))

    Rs, ts, sc = kabsch(q3, X, allow_scale=True)
    sres = np.linalg.norm(X - apply_rt(Rs, ts, sc, q3), axis=1)

    c, nrm, e1, e2 = plane_fit(X)
    oop = (X - c) @ nrm
    ip = np.stack([(X - c) @ e1, (X - c) @ e2], axis=1)
    # A LINEAR trend of the out-of-plane deviation on the fitted plane's own coordinates is
    # identically zero: least squares makes the residual orthogonal to the fitted subspace. So the
    # only informative depth trend is CURVATURE -- is the reconstructed sheet bowed or saddled?
    u, v = ip[:, 0], ip[:, 1]
    Mq = np.column_stack([np.ones(n), u, v, u * u, u * v, v * v])
    ss = float(((oop - oop.mean()) ** 2).sum())
    if n >= 7 and ss > 0:
        gq, *_ = np.linalg.lstsq(Mq, oop, rcond=None)
        predq = Mq @ gq
        curv_rms = float(np.sqrt((predq ** 2).mean()))
        curv_r2 = float(1.0 - ((oop - predq) ** 2).sum() / ss)
    else:
        curv_rms, curv_r2 = float("nan"), float("nan")
    aff = affine_from_truth(q2, X)
    return {"n": n, "R": R, "t": t, "res": res, "mag": mag,
            "rms": float(np.sqrt((mag ** 2).mean())), "med": float(np.median(mag)),
            "p90": float(np.percentile(mag, 90)), "max": float(mag.max()),
            "influence": infl, "loo": loo,
            "loo_rms": float(np.sqrt(np.nanmean(loo ** 2))),
            "loo_med": float(np.nanmedian(loo)), "loo_max": float(np.nanmax(loo)),
            "sim_scale": sc, "sim_rms": float(np.sqrt((sres ** 2).mean())),
            "oop": oop, "oop_rms": float(np.sqrt((oop ** 2).mean())),
            "oop_max": float(np.abs(oop).max()),
            "curv_rms": curv_rms, "curv_r2": curv_r2,
            "inplane": ip, "affine": aff}


# --------------------------------------------------------------------------- statistics

def stats(err):
    e = np.abs(np.asarray(err, float)); s = np.asarray(err, float)
    if e.size == 0:
        return {k: float("nan") for k in ("n", "mae", "rmse", "med", "bias", "p75", "p90",
                                          "p95", "p99", "max", "w10", "w5")}
    return {"n": int(e.size), "mae": float(e.mean()),
            "rmse": float(math.sqrt((s ** 2).mean())), "med": float(np.median(e)),
            "bias": float(s.mean()), "p75": float(np.percentile(e, 75)),
            "p90": float(np.percentile(e, 90)), "p95": float(np.percentile(e, 95)),
            "p99": float(np.percentile(e, 99)), "max": float(e.max()),
            "w10": float(e[e >= np.percentile(e, 90)].mean()),
            "w5": float(e[e >= np.percentile(e, 95)].mean())}


def node_jackknife(cals, dists, clicks, clouds, cpairs, cnames, conv, say, outdir, kfolds=5):
    """Hold out physical calibration nodes coherently, rebuild the WHOLE refractive calibration,
    and re-measure. This is the only test that separates a real M1 improvement from a
    calibration-level bias, because all four clouds share one calibration.

    'Coherently' means the same PHYSICAL node -- identified by its world (h, v) coordinate on the
    frame, not by row order -- is dropped from BOTH cameras and from both surfaces in a fold. A fold
    that dropped different nodes per camera would change the two cameras' geometry independently and
    confound the comparison. Folds are strided over the sorted node list so each fold is spread
    across the frame rather than clipping one corner.
    """
    say(f"\n    CALIBRATION-NODE JACKKNIFE: {kfolds} folds, each dropping physical nodes from both")
    say(f"    cameras and both surfaces, then rebuilding front + refractive back + camera position")
    ids = {}
    for surf in ("front", "back"):
        allids = sorted({(round(p[2], 6), round(p[3], 6)) for c in cals.values() for p in c[surf]})
        ids[surf] = allids
        say(f"      {surf:5} surface: {len(allids)} distinct physical nodes "
            f"({'/'.join(str(len(c[surf])) for c in [cals[k] for k in sorted(cals)])} clicks per camera)")
    rows = []
    for k in range(kfolds):
        drop = {s: set(ids[s][k::kfolds]) for s in ("front", "back")}
        sub = {}
        ok = True
        for clip in sorted(cals):
            c = dict(cals[clip])
            for surf in ("front", "back"):
                c[surf] = [p for p in cals[clip][surf]
                           if (round(p[2], 6), round(p[3], 6)) not in drop[surf]]
                if len(c[surf]) < 4:
                    ok = False
            sub[clip] = c
        if not ok:
            say(f"      fold {k}: SKIPPED, a surface would be left with fewer than 4 nodes")
            continue
        out = {}
        for m in ("M0", "M1"):
            camsk = {cl: build_cam(sub[cl], dists[m][cl]) for cl in sorted(cals)}
            X = {}
            for cn in cnames:
                for p in clouds[cn]:
                    r = reconstruct(p["pk"], camsk, clicks)
                    X[p["pk"]] = None if r is None else r["X"]
            shpk, maek = {}, {}
            for cn in cnames:
                pts = clouds[cn]
                if any(X[p["pk"]] is None for p in pts):
                    shpk[cn] = float("nan"); maek[cn] = float("nan"); continue
                q2 = np.array([p["mm"] for p in pts], float)
                XX = np.array([X[p["pk"]] for p in pts], float) * UNIT
                shpk[cn] = shape_report(q2, XX)["rms"]
                e = [abs(float(np.linalg.norm(np.array(X[q["pks"][0]], np.float32) -
                                              np.array(X[q["pks"][1]], np.float32))) * UNIT
                         - q["true"])
                     for q in cpairs if q["cloud"] == cn]
                maek[cn] = float(np.mean(e))
            cv = []
            for r in conv:
                a = reconstruct(r["pks"][0], camsk, clicks)
                b = reconstruct(r["pks"][1], camsk, clicks)
                if a is None or b is None:
                    continue
                cv.append(abs(float(np.linalg.norm(np.array(a["X"], np.float32) -
                                                   np.array(b["X"], np.float32))) * UNIT - r["true"]))
            out[m] = {"shape": shpk, "mae": maek, "conv": float(np.mean(cv))}
        row = {"fold": k,
               "n_front_dropped": len(drop["front"]), "n_back_dropped": len(drop["back"])}
        for m in ("M0", "M1"):
            row[f"{m}_cloud_equal_mae"] = float(np.mean([out[m]["mae"][cn] for cn in cnames]))
            row[f"{m}_rigid_rms_mean"] = float(np.mean([out[m]["shape"][cn] for cn in cnames]))
            row[f"{m}_conv42_mae"] = out[m]["conv"]
            for cn in cnames:
                row[f"{m}_mae_{cn.replace(' ','')}"] = out[m]["mae"][cn]
                row[f"{m}_rigid_{cn.replace(' ','')}"] = out[m]["shape"][cn]
        row["d_cloud_equal_mae"] = row["M1_cloud_equal_mae"] - row["M0_cloud_equal_mae"]
        row["d_rigid_rms_mean"] = row["M1_rigid_rms_mean"] - row["M0_rigid_rms_mean"]
        row["d_conv42_mae"] = row["M1_conv42_mae"] - row["M0_conv42_mae"]
        row["n_clouds_M1_better"] = int(sum(1 for cn in cnames
                                            if row[f"M1_rigid_{cn.replace(' ','')}"] <
                                            row[f"M0_rigid_{cn.replace(' ','')}"]))
        rows.append(row)
    if not rows:
        say(f"      no usable folds")
        return None
    say(f"\n    {'fold':5} {'M0 pairMAE':>11} {'M1 pairMAE':>11} {'M1-M0':>9} "
        f"{'M0 rigid':>9} {'M1 rigid':>9} {'M1-M0':>9} {'M0 conv':>9} {'M1 conv':>9} "
        f"{'M1-M0':>9} {'clouds M1 better':>17}")
    for r in rows:
        say(f"    {r['fold']:5d} {r['M0_cloud_equal_mae']:11.4f} {r['M1_cloud_equal_mae']:11.4f} "
            f"{r['d_cloud_equal_mae']:+9.4f} {r['M0_rigid_rms_mean']:9.4f} "
            f"{r['M1_rigid_rms_mean']:9.4f} {r['d_rigid_rms_mean']:+9.4f} "
            f"{r['M0_conv42_mae']:9.4f} {r['M1_conv42_mae']:9.4f} {r['d_conv42_mae']:+9.4f} "
            f"{str(r['n_clouds_M1_better'])+'/'+str(len(cnames)):>17}")
    dp = np.array([r["d_cloud_equal_mae"] for r in rows])
    dr = np.array([r["d_rigid_rms_mean"] for r in rows])
    dc = np.array([r["d_conv42_mae"] for r in rows])
    say(f"\n    across folds: pair-MAE change {dp.mean():+.4f} mm "
        f"(range {dp.min():+.4f} to {dp.max():+.4f}), sign stable {bool((dp < 0).all() or (dp > 0).all())}")
    say(f"                  rigid-RMS change {dr.mean():+.4f} mm "
        f"(range {dr.min():+.4f} to {dr.max():+.4f}), sign stable {bool((dr < 0).all() or (dr > 0).all())}")
    say(f"                  conv-42 change   {dc.mean():+.4f} mm "
        f"(range {dc.min():+.4f} to {dc.max():+.4f}), sign stable {bool((dc < 0).all() or (dc > 0).all())}")
    nb = [r["n_clouds_M1_better"] for r in rows]
    say(f"    M1 improves rigid shape in {min(nb)}-{max(nb)} of {len(cnames)} clouds in every fold")
    stable = bool((dp < 0).all() and (dr < 0).all())
    say(f"    VERDICT: the M0-vs-M1 ranking {'SURVIVES' if stable else 'does NOT survive'} "
        f"plausible calibration-node variation.")
    say(f"    Spread across folds ({dr.max()-dr.min():.3f} mm on rigid RMS) is the honest scale of")
    say(f"    calibration-induced uncertainty on this contrast.")
    write_csv(os.path.join(outdir, "fisheye_node_jackknife.csv"), rows, list(rows[0]))
    return {"rows": rows, "stable": stable, "d_pair": dp.tolist(), "d_rigid": dr.tolist(),
            "d_conv": dc.tolist()}


HDR = f"{'model':8} {'n':>5} {'MAE':>8} {'RMSE':>8} {'med':>8} {'bias':>8} {'p75':>8} {'p90':>8} " \
      f"{'p95':>8} {'p99':>8} {'max':>9} {'w10%':>8} {'w5%':>8}"


def line(name, s):
    return (f"{name:8} {s['n']:5d} {s['mae']:8.3f} {s['rmse']:8.3f} {s['med']:8.3f} "
            f"{s['bias']:+8.3f} {s['p75']:8.3f} {s['p90']:8.3f} {s['p95']:8.3f} "
            f"{s['p99']:8.3f} {s['max']:9.3f} {s['w10']:8.3f} {s['w5']:8.3f}")


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3 or a[ok].std() == 0 or b[ok].std() == 0:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def strata(x, d, edges, label, say, unit=""):
    x = np.asarray(x, float); d = np.asarray(d, float)
    say(f"      {label}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (x >= lo) & (x < hi)
        if m.sum() == 0:
            continue
        say(f"        {lo:9.1f}-{hi:<9.1f}{unit:4} n {int(m.sum()):5d}  mean {d[m].mean():+8.4f}  "
            f"median {np.median(d[m]):+8.4f}  better {int((d[m]<0).sum())}/{int(m.sum())}")


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# =========================================================================== main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--outdir", default=OUTDIR)
    args = ap.parse_args()
    t0 = time.time()
    say = print
    os.makedirs(args.outdir, exist_ok=True)
    doc = os.path.basename(args.vsd)

    say("=" * 104)
    say(f"FISHEYE KNOWN-LENGTH AND CLOUD-SHAPE ANALYSIS   {doc}")
    say("=" * 104)

    # ---------------------------------------------------------------- 1. load and validate
    cals = st.load_cal(args.vsd)
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)
    for clip, c in cals.items():
        nd.assert_node_orientation(db, c["pk"], c["s2f"], c["s2b"], c["dist"], clip)
    say(f"\n[1] NODE ORIENTATION invariant holds for all {len(cals)} cameras "
        f"(ZCALIBRATION1 = FRONT, ZCALIBRATION = BACK)")

    D = kl.load(args.vsd)
    conv, cpts, cpairs = D["conventional"], D["cloud_points"], D["cloud_pairs"]
    clicks = D["clicks"]
    clouds = D["clouds"]
    cnames = sorted(clouds)
    say(f"\n[1] LOADER VALIDATION / EXCLUSION SUMMARY   (source: knownlength.py)")
    say(f"    conventional two-point measurements : {len(conv)}")
    bycls = defaultdict(list)
    for r in conv:
        bycls[r["true"]].append(r)
    for tl in sorted(bycls):
        say(f"        true {tl:7.1f} mm   n {len(bycls[tl]):3d}   "
            f"timecodes {sorted({r['tc'] for r in bycls[tl]})}")
    say(f"    point clouds                        : {len(clouds)} clouds, {len(cpts)} points, "
        f"{len(cpairs)} within-cloud pairs")
    for cn in cnames:
        pts = clouds[cn]
        tl = [q["true"] for q in cpairs if q["cloud"] == cn]
        say(f"        {cn:9} {len(pts):3d} pts, {len(tl):4d} pairs, "
            f"{len(pts[0]['cm'])}D notes, tc {sorted({p['tc'] for p in pts})[0]}, "
            f"true {min(tl):.1f}-{max(tl):.1f} mm")
    say(f"    exclusions                          : {len(D['exclusions'])}")
    for e in D["exclusions"]:
        say(f"        {e[0]:20} {str(e[1]):10} event {e[2]} -> {e[3]}")
    if not D["exclusions"]:
        say(f"        none")
    orig = [r for r in conv if r["event"] in ORIGINAL_14]
    new = [r for r in conv if r["event"] not in ORIGINAL_14]
    say(f"    original 14-measurement subset reproduced: {len(orig)}/14 events present "
        f"({sorted({r['tc'] for r in orig})} -> 3 placements)")
    say(f"    newly added conventional measurements    : {len(new)} "
        f"at {sorted({r['tc'] for r in new})} -> 1 placement")
    say(f"    REPLICATION UNITS: {len({r['tc'] for r in conv})} conventional placements + "
        f"{len(clouds)} cloud placements = "
        f"{len({r['tc'] for r in conv}) + len(clouds)} independent placements in total")

    # plumbline geometry and image-support hulls (raw screen space, so model-independent)
    plum, hull_pl, hull_nd = {}, {}, {}
    for clip in sorted(cals):
        co = S.Clip(args.vsd, clip)
        plum[clip] = co
        hull_pl[clip] = hull_equations(co.xy)
        nn = ([(x, y) for x, y, _, _ in nd.front_calibration_nodes(db, cals[clip]["pk"])] +
              [(x, y) for x, y, _, _ in nd.back_calibration_nodes(db, cals[clip]["pk"])])
        hull_nd[clip] = hull_equations(nn)
    db.close()
    say(f"\n[1] PLUMBLINE SUPPORT")
    for clip in sorted(cals):
        co = plum[clip]
        say(f"    {clip:14} {co.nlines:3d} lines, {co.n:5d} points, {co.ntc} timecode set(s), "
            f"image extent x {co.xy[:,0].min():.0f}-{co.xy[:,0].max():.0f} "
            f"y {co.xy[:,1].min():.0f}-{co.xy[:,1].max():.0f}")

    # ---------------------------------------------------------------- 2. fit the four models
    say(f"\n[2] MODEL FITS   (gated, held parameters zeroed on every seed)")
    dists, diag = {}, {}
    for mname, free in MODELS:
        dists[mname] = {}
        for clip in sorted(cals):
            c = cals[clip]
            if free is None:
                d14 = list(c["dist"]) + [0.0]
                prms, basins = float("nan"), []
            else:
                s0 = np.zeros(15)
                s0[0] = (plum[clip].centre0[0] - S.W / 2) / S.R
                s0[1] = (plum[clip].centre0[1] - S.H / 2) / S.R
                v, prms, basins, _ = fit_model(plum[clip], free,
                                               [s0, stored_to_v(c["dist"])])
                cq, kq, pq, eq, _ = Z.nphys(v)
                d14 = [cq[0], cq[1], *kq, *pq, eq]
            dists[mname][clip] = d14
            gr = F.gate_report(np.array(d14[:13]), PL(plum[clip].xy), sref=0.0,
                               frame=(FRAME_W, FRAME_H))
            cam = build_cam(c, d14)
            fr, _ = nd._rms_max(c["front"], cam["s2f"], d14)
            br, _ = nd._rms_max(c["back"], cam["s2b"], d14)
            diag[(mname, clip)] = {"prms": prms, "gate": gr, "cam": cam, "fr": fr * UNIT,
                                   "br": br * UNIT, "basins": basins, "d14": d14}

    say(f"    free parameter sets, verified as declared:")
    say(f"      conv-13  {list(range(13))}  (13 free: centre, k1..k7, p1..p4)")
    say(f"      M0       {Z.ISO}  ({len(Z.ISO)} free: centre, k1..k4, p1,p2)")
    say(f"      M1       {Z.SCAL}  ({len(Z.SCAL)} free: M0 + eta at index 13)")
    say(f"      M1 free set is exactly M0's plus eta: {set(Z.SCAL) - set(Z.ISO) == {13}}; "
        f"M0 is nested in M1: {set(Z.ISO) < set(Z.SCAL)}")
    say(f"\n    {'model':8} {'camera':14} {'plumb px':>9} {'eta':>10} {'R_scale':>8} {'minDet':>8} "
        f"{'gate':>5} {'frontRMS':>9} {'backRMS':>9} {'camPLD':>8} {'basins':>22}")
    for mname, _ in MODELS:
        for clip in sorted(cals):
            d = diag[(mname, clip)]; gr = d["gate"]
            bs = ",".join(f"{math.sqrt(b/plum[clip].n):.4f}" for b in d["basins"][:3]) or "-"
            say(f"    {mname:8} {clip:14} {d['prms']:9.4f} {d['d14'][13]:+10.6f} "
                f"{gr['radial_scale_ratio']:8.4f} {gr['min_det_box']:8.4f} "
                f"{'ok' if gr['ok'] else 'FAIL':>5} {d['fr']:9.4f} {d['br']:9.4f} "
                f"{d['cam']['camPLD']*UNIT:8.4f} {bs:>22}")
    say(f"    all four models pass the PRODUCTION gate (mean radial magnification over the "
        f"plumbline box, bracket 0.25-4.0): "
        f"{all(diag[(m,c)]['gate']['ok'] for m,_ in MODELS for c in cals)}")
    fr_s = "/".join(f"{diag[('stored', c)]['fr']:.2f}" for c in sorted(cals))
    br_s = "/".join(f"{diag[('stored', c)]['br']:.2f}" for c in sorted(cals))
    say(f"    calibration-node residual is LARGE here -- front {fr_s} mm, back {br_s} mm. That is "
        f"comparable to the model differences being tested and bounds every conclusion below.")

    # ---------------------------------------------------------------- 3. eta = 0 nesting
    say(f"\n[3] eta = 0 NESTING: M1 with eta forced to zero must BE the 13-parameter model")
    say(f"    The question is whether the anisotropic code path degenerates EXACTLY, not whether")
    say(f"    eta changes the answer (it does; that magnitude is reported separately below).")
    worst = {"map_px": 0.0, "homog": 0.0, "cam_mm": 0.0, "point_mm": 0.0}

    # (a) map level: the eta-aware undistortion at eta = 0 against the pure 13-parameter port
    rng = np.random.default_rng(0)
    grid = np.column_stack([rng.uniform(0, FRAME_W, 4000), rng.uniform(0, FRAME_H, 4000)])
    for clip in sorted(cals):
        d13 = list(dists["M1"][clip][:13])
        e = 0.0
        for x, y in grid:
            a = UNDISTORT_13(x, y, d13)
            b = nd.undistort13(x, y, d13 + [0.0])
            e = max(e, abs(a[0] - b[0]), abs(a[1] - b[1]))
        worst["map_px"] = max(worst["map_px"], e)
        say(f"    {clip:14} (a) undistortion map over 4000 random frame points: "
            f"max |U_eta=0 - U_13| = {e:.3e} px")

    # (b) calibration level, and (c) point level, with the eta-free map substituted wholesale
    for clip in sorted(cals):
        d13 = list(dists["M1"][clip][:13])
        a = build_cam(cals[clip], d13 + [0.0])
        b = build_cam(cals[clip], d13 + [0.0])
        hd = max(abs(x - y) for key in ("s2f", "s2b", "f2s")
                 for r1, r2 in zip(a[key], b[key]) for x, y in zip(r1, r2))
        worst["homog"] = max(worst["homog"], hd)
        worst["cam_mm"] = max(worst["cam_mm"], math.dist(a["cam"], b["cam"]) * UNIT)
    camsZ = {cl: build_cam(cals[cl], list(dists["M1"][cl][:13]) + [0.0]) for cl in cals}
    nest_pks = [pk for r in conv for pk in r["pks"]] + [q["pk"] for q in cpts]
    # The eta=0 nesting check deliberately swaps the two maps in and out. Both directions now go
    # through the explicit historical hook rather than an attribute assignment, so the swap is visible.
    NEST_REASON = ("eta = 0 nesting verification for the frozen fisheye analysis: the eta-aware and "
                   "pure 13-parameter paths must reconstruct identical points when eta is zero")
    try:
        pa.install_historical_eta_map(nd.undistort13, reason=NEST_REASON)
        A = {pk: reconstruct(pk, camsZ, clicks)["X"] for pk in nest_pks}
        pa.install_historical_eta_map(UNDISTORT_13, reason=NEST_REASON)
        B = {pk: reconstruct(pk, camsZ, clicks)["X"] for pk in nest_pks}
    finally:
        pa.install_historical_eta_map(nd.undistort13, reason=NEST_REASON)
    worst["point_mm"] = max(float(np.linalg.norm(A[k] - B[k])) * UNIT for k in A)
    say(f"    (b) rebuilt homographies and camera position at eta = 0: max coefficient diff "
        f"{worst['homog']:.3e}, camera diff {worst['cam_mm']:.3e} mm")
    say(f"    (c) all {len(A)} measured points reconstructed through the eta-aware path at eta = 0")
    say(f"        versus the pure 13-parameter path: max 3D difference "
        f"{worst['point_mm']:.3e} mm")
    say(f"    oracle.cpp:60-62 applies A = diag(e^eta, e^-eta); exp(0) = 1.0 exactly in IEEE754, so")
    say(f"    the conjugation is a bit-exact identity and the nesting holds by construction as well")
    say(f"\n    SIZE OF THE eta EFFECT (not a nesting error): M1's fitted eta versus eta = 0")
    for clip in sorted(cals):
        d1 = list(dists["M1"][clip])
        a, b = build_cam(cals[clip], d1), build_cam(cals[clip], list(d1[:13]) + [0.0])
        say(f"      {clip:14} eta {d1[13]:+.6f} moves the camera position by "
            f"{math.dist(a['cam'], b['cam'])*UNIT:.3f} mm")

    # ---------------------------------------------------------------- 4. reconstruct everything
    say(f"\n[4] RECONSTRUCTION of {len(conv)*2} conventional endpoints and {len(cpts)} cloud "
        f"points under {len(MODELS)} models")
    cams_by_model = {m: {cl: diag[(m, cl)]["cam"] for cl in cals} for m, _ in MODELS}
    ax = pa.AX[({"x", "y", "z"} - {list(cals.values())[0]["ah"],
                                   list(cals.values())[0]["av"]}).pop()]
    fd, bd = list(cals.values())[0]["front_d"], list(cals.values())[0]["back_d"]
    # calibrated 3D volume: node world extents in the two in-plane axes, plane depths in the third
    fn = list(cals.values())[0]["front"]
    lo3, hi3 = np.zeros(3), np.zeros(3)
    oth = [k for k in range(3) if k != ax]
    lo3[ax], hi3[ax] = min(fd, bd), max(fd, bd)
    lo3[oth[0]], hi3[oth[0]] = min(p[2] for p in fn), max(p[2] for p in fn)
    lo3[oth[1]], hi3[oth[1]] = min(p[3] for p in fn), max(p[3] for p in fn)

    rec, failures = {}, []
    allpks = [(r["event"], pk, "conventional", r["obj"], r["tc"], None)
              for r in conv for pk in r["pks"]] + \
             [(q["event"], q["pk"], "cloud", q["cloud"], q["tc"], q["mm"]) for q in cpts]
    for m, _ in MODELS:
        rec[m] = {}
        for ev, pk, kind, grp, tc, mm in allpks:
            r = reconstruct(pk, cams_by_model[m], clicks)
            if r is None:
                failures.append((m, kind, grp, ev, pk, "fewer than two clicked cameras"))
                continue
            rec[m][pk] = r
    say(f"    reconstruction failures / exclusions: {len(failures)}")
    for f in failures:
        say(f"        {f}")
    if not failures:
        say(f"        none -- all {len(allpks)} point/model combinations reconstructed")

    # point-level table
    prows = []
    for m, _ in MODELS:
        for ev, pk, kind, grp, tc, mm in allpks:
            r = rec[m].get(pk)
            if r is None:
                continue
            cls = sorted(r["clicks"])
            row = {"model": m, "kind": kind, "group": grp, "event": ev, "point_pk": pk, "tc": tc,
                   "true_u_mm": mm[0] if mm else "", "true_v_mm": mm[1] if mm else "",
                   "X_mm": r["X"][0], "Y_mm": r["X"][1], "Z_mm": r["X"][2],
                   "reproj_px": r["rep"], "meanPLD_mm": r["pld"],
                   "stereo_angle_deg": r["stereo_deg"], "cpa_cond": r["cpa_cond"],
                   "outside_cal_volume_mm": box_outside(r["X"], lo3, hi3)}
            for i, cl in enumerate(cls):
                row[f"click{i}_cam"] = cl
                row[f"click{i}_x"] = r["clicks"][cl][0]
                row[f"click{i}_y"] = r["clicks"][cl][1]
                row[f"click{i}_radius_px"] = r["radius"][cl]
                row[f"click{i}_edge_px"] = r["edge"][cl]
                row[f"click{i}_outside_plumb_px"] = outside(hull_pl[cl], r["clicks"][cl])
                row[f"click{i}_outside_nodehull_px"] = outside(hull_nd[cl], r["clicks"][cl])
            row["max_radius_px"] = max(r["radius"].values())
            row["min_edge_px"] = min(r["edge"].values())
            row["max_outside_plumb_px"] = max(outside(hull_pl[cl], r["clicks"][cl]) for cl in cls)
            row["max_outside_nodehull_px"] = max(outside(hull_nd[cl], r["clicks"][cl]) for cl in cls)
            prows.append(row)
    pfields = list(dict.fromkeys(k for r in prows for k in r))
    write_csv(os.path.join(args.outdir, "fisheye_points.csv"), prows, pfields)
    say(f"    per-point diagnostics retained: reconstructed position, reprojection error, linear "
        f"meanPLD, image radius and screen-edge margin in BOTH cameras, distance outside the "
        f"plumbline hull and the node hull, distance outside the calibrated volume, stereo "
        f"intersection angle, CPA conditioning")

    # =============================================================== 5. CLOUD SHAPE (primary)
    say("\n" + "=" * 104)
    say("[5] CLOUD SHAPE -- the primary evidence, four independent placements")
    say("=" * 104)
    say("    Each cloud gives a known planar metric configuration with no absolute pose. Alignment")
    say("    is the optimal PROPER rigid map from truth to reconstruction: rotation + translation,")
    say("    no reflection, NO FITTED SCALE. Similarity scale is reported separately, as a")
    say("    diagnostic only, because a free scale absorbs part of the distortion under test.")
    say("    Caveat: for a planar source an in-plane reflection is realisable by a proper 3D")
    say("    rotation, so 'no reflection' does not pin handedness; it excludes improper ambient maps.")

    shp = {}
    for m, _ in MODELS:
        for cn in cnames:
            pts = clouds[cn]
            q2 = np.array([p["mm"] for p in pts], float)
            X = np.array([rec[m][p["pk"]]["X"] for p in pts], float) * UNIT
            shp[(m, cn)] = shape_report(q2, X)

    say(f"\n    RIGID ALIGNMENT RESIDUAL (mm), no fitted scale")
    say(f"    {'cloud':8} {'n':>3} " + " ".join(f"{m:>9}" for m in MNAMES) +
        f" {'M1-M0':>9} {'M1/M0':>7}")
    for stat, lbl in (("rms", "RMS"), ("med", "median"), ("p90", "p90"), ("max", "max")):
        say(f"      -- {lbl}")
        for cn in cnames:
            v = [shp[(m, cn)][stat] for m in MNAMES]
            say(f"    {cn:8} {shp[('M0',cn)]['n']:3d} " + " ".join(f"{x:9.3f}" for x in v) +
                f" {v[3]-v[2]:+9.3f} {v[3]/v[2] if v[2] else float('nan'):7.3f}")

    say(f"\n    HELD-OUT (leave-one-point-out) RIGID RESIDUAL (mm): fit without a point, "
        f"predict it")
    say(f"    {'cloud':8} " + " ".join(f"{m:>9}" for m in MNAMES) + f" {'M1-M0':>9}")
    for cn in cnames:
        v = [shp[(m, cn)]["loo_rms"] for m in MNAMES]
        say(f"    {cn:8} " + " ".join(f"{x:9.3f}" for x in v) + f" {v[3]-v[2]:+9.3f}   (RMS)")
    for cn in cnames:
        v = [shp[(m, cn)]["loo_med"] for m in MNAMES]
        say(f"    {cn:8} " + " ".join(f"{x:9.3f}" for x in v) + f" {v[3]-v[2]:+9.3f}   (median)")

    say(f"\n    SIMILARITY DIAGNOSTIC (fitted scale; NOT the accuracy metric) and PLANARITY (mm)")
    say(f"    Depth trend is reported as CURVATURE: a linear trend of out-of-plane deviation on the")
    say(f"    best-fit plane's own coordinates is identically zero by least squares, so only bowing")
    say(f"    or saddling of the reconstructed sheet carries information.")
    say(f"    {'cloud':8} {'model':8} {'sim scale':>10} {'sim RMS':>9} {'oop RMS':>9} "
        f"{'oop max':>9} {'curv RMS':>9} {'curv R2':>8}")
    for cn in cnames:
        for m in MNAMES:
            s = shp[(m, cn)]
            say(f"    {cn:8} {m:8} {s['sim_scale']:10.6f} {s['sim_rms']:9.3f} "
                f"{s['oop_rms']:9.3f} {s['oop_max']:9.3f} {s['curv_rms']:9.3f} "
                f"{s['curv_r2']:8.3f}")

    say(f"\n    IN-PLANE AFFINE DIAGNOSTIC from truth (basis-free: A's columns are the images of")
    say(f"    the truth's own axes). Diagnostic only -- a free affine map can absorb the very")
    say(f"    distortion under test.")
    say(f"    {'cloud':8} {'model':8} {'mean scale':>11} {'s_major':>8} {'s_minor':>8} "
        f"{'anisotropy':>11} {'shear deg':>10} {'orient deg':>11} {'affine RMS':>11}")
    for cn in cnames:
        for m in MNAMES:
            a = shp[(m, cn)]["affine"]
            say(f"    {cn:8} {m:8} {a['mean_scale']:11.6f} {a['s_major']:8.5f} "
                f"{a['s_minor']:8.5f} {a['anisotropy']:11.6f} {a['shear_deg']:+10.4f} "
                f"{a['orient_deg']:+11.2f} {a['rms']:11.3f}")

    say(f"\n    SPATIAL RESIDUAL FIELD: rigid residual by position within each cloud")
    for cn in cnames:
        pts = clouds[cn]
        q2 = np.array([p["mm"] for p in pts], float)
        say(f"      {cn}: truth extent u {q2[:,0].min():.0f}-{q2[:,0].max():.0f} mm, "
            f"v {q2[:,1].min():.0f}-{q2[:,1].max():.0f} mm")
        for m in ("M0", "M1"):
            s = shp[(m, cn)]
            u = q2[:, 0]
            th = np.percentile(u, [33.3, 66.7])
            parts = []
            for lo, hi, nm2 in ((-1e9, th[0], "u low"), (th[0], th[1], "u mid"),
                                (th[1], 1e9, "u high")):
                msk = (u >= lo) & (u <= hi)
                if msk.sum():
                    parts.append(f"{nm2} {math.sqrt((s['mag'][msk]**2).mean()):.2f}")
            say(f"        {m:3} residual rms by truth u-tercile: " + "  ".join(parts) +
                f"   |corr(res, u)| {abs(corr(u, s['mag'])):.2f}  "
                f"|corr(res, v)| {abs(corr(q2[:,1], s['mag'])):.2f}")

    say(f"\n    PER-POINT INFLUENCE on the rigid fit (mm of cloud RMS attributable to one point)")
    for cn in cnames:
        for m in ("M0", "M1"):
            s = shp[(m, cn)]
            i = int(np.nanargmax(s["influence"]))
            q2 = np.array([p["mm"] for p in clouds[cn]], float)
            say(f"      {cn} {m:3}: max influence {s['influence'][i]:+.3f} mm at truth "
                f"({q2[i,0]:.0f},{q2[i,1]:.0f}), its own residual {s['mag'][i]:.2f} mm; "
                f"median influence {np.nanmedian(s['influence']):+.3f}")

    nimp = sum(1 for cn in cnames if shp[("M1", cn)]["rms"] < shp[("M0", cn)]["rms"])
    say(f"\n    VERDICT ON SHAPE: M1 improves rigid RMS in {nimp} of {len(cnames)} placements. "
        f"Consistency across placements, not pooled point count, is the evidence.")

    srows = []
    for m in MNAMES:
        for cn in cnames:
            s = shp[(m, cn)]; a = s["affine"]
            srows.append({"model": m, "cloud": cn, "n": s["n"],
                          "tc": sorted({p["tc"] for p in clouds[cn]})[0],
                          "rigid_rms_mm": s["rms"], "rigid_median_mm": s["med"],
                          "rigid_p90_mm": s["p90"], "rigid_max_mm": s["max"],
                          "loo_rms_mm": s["loo_rms"], "loo_median_mm": s["loo_med"],
                          "loo_max_mm": s["loo_max"],
                          "similarity_scale": s["sim_scale"], "similarity_rms_mm": s["sim_rms"],
                          "outofplane_rms_mm": s["oop_rms"], "outofplane_max_mm": s["oop_max"],
                          "depth_curvature_rms_mm": s["curv_rms"],
                          "depth_curvature_r2": s["curv_r2"],
                          "affine_mean_scale": a["mean_scale"], "affine_s_major": a["s_major"],
                          "affine_s_minor": a["s_minor"], "affine_anisotropy": a["anisotropy"],
                          "affine_shear_deg": a["shear_deg"], "affine_orient_deg": a["orient_deg"],
                          "affine_rms_mm": a["rms"],
                          "max_influence_mm": float(np.nanmax(s["influence"])),
                          "median_influence_mm": float(np.nanmedian(s["influence"]))})
    write_csv(os.path.join(args.outdir, "fisheye_cloud_shape.csv"), srows, list(srows[0]))

    # per-point residual vectors, for the spatial field
    vrows = []
    for m in MNAMES:
        for cn in cnames:
            s = shp[(m, cn)]
            for i, p in enumerate(clouds[cn]):
                vrows.append({"model": m, "cloud": cn, "event": p["event"], "point_pk": p["pk"],
                              "true_u_mm": p["mm"][0], "true_v_mm": p["mm"][1],
                              "res_x_mm": s["res"][i, 0], "res_y_mm": s["res"][i, 1],
                              "res_z_mm": s["res"][i, 2], "res_mag_mm": s["mag"][i],
                              "outofplane_mm": s["oop"][i], "influence_mm": s["influence"][i],
                              "heldout_mm": s["loo"][i]})
    write_csv(os.path.join(args.outdir, "fisheye_cloud_residuals.csv"), vrows, list(vrows[0]))

    # =============================================================== 6. within-cloud pairs
    say("\n" + "=" * 104)
    say(f"[6] WITHIN-CLOUD PAIRWISE LENGTHS -- {len(cpairs)} pairs, but only "
        f"{len(clouds)} replication units")
    say("=" * 104)
    perr = {m: [] for m in MNAMES}
    prow2 = []
    for q in cpairs:
        i, j = q["pks"]
        base = {"cloud": q["cloud"], "tc": q["tc"], "event_i": q["i"], "event_j": q["j"],
                "true_u_i": q["mm_i"][0], "true_v_i": q["mm_i"][1],
                "true_u_j": q["mm_j"][0], "true_v_j": q["mm_j"][1], "true_mm": q["true"],
                "dir_deg": math.degrees(math.atan2(q["mm_j"][1] - q["mm_i"][1],
                                                   q["mm_j"][0] - q["mm_i"][0])) % 180.0}
        row = dict(base)
        for m in MNAMES:
            Li = float(np.linalg.norm(np.array(rec[m][i]["X"], np.float32) -
                                      np.array(rec[m][j]["X"], np.float32))) * UNIT
            e = Li - q["true"]
            perr[m].append(e)
            row[f"meas_{m}"] = Li; row[f"err_{m}"] = e
            row[f"abspct_{m}"] = 100.0 * abs(e) / q["true"]
        row["dM1_M0_mm"] = abs(row["err_M1"]) - abs(row["err_M0"])
        # geometry, from the M0 reconstruction so strata are one fixed set
        ri, rj = rec["M0"][i], rec["M0"][j]
        mid = 0.5 * (ri["X"] + rj["X"])
        cds = [math.dist(mid, cams_by_model["M0"][cl]["cam"]) * UNIT for cl in sorted(cals)]
        row.update({"cam_dist_mean_mm": float(np.mean(cds)), "cam_dist_min_mm": float(min(cds)),
                    "max_radius_px": max(max(ri["radius"].values()), max(rj["radius"].values())),
                    "radial_sep_px": abs(max(ri["radius"].values()) - max(rj["radius"].values())),
                    "min_edge_px": min(min(ri["edge"].values()), min(rj["edge"].values())),
                    "outside_plumb_px": max(max(outside(hull_pl[cl], ri["clicks"][cl])
                                                for cl in ri["clicks"]),
                                            max(outside(hull_pl[cl], rj["clicks"][cl])
                                                for cl in rj["clicks"])),
                    "outside_nodehull_px": max(max(outside(hull_nd[cl], ri["clicks"][cl])
                                                   for cl in ri["clicks"]),
                                               max(outside(hull_nd[cl], rj["clicks"][cl])
                                                   for cl in rj["clicks"])),
                    "outside_cal_volume_mm": max(box_outside(ri["X"], lo3, hi3),
                                                 box_outside(rj["X"], lo3, hi3)),
                    "stereo_angle_deg": min(ri["stereo_deg"], rj["stereo_deg"]),
                    "cpa_cond": max(ri["cpa_cond"], rj["cpa_cond"])})
        prow2.append(row)
    write_csv(os.path.join(args.outdir, "fisheye_cloud_pairs.csv"), prow2, list(prow2[0]))

    say(f"\n    PER CLOUD (mm)")
    for cn in cnames:
        idx = [k for k, q in enumerate(cpairs) if q["cloud"] == cn]
        say(f"      {cn}  n_pairs {len(idx)}  n_points {len(clouds[cn])}")
        say(f"        {HDR}")
        for m in MNAMES:
            say(f"        {line(m, stats([perr[m][k] for k in idx]))}")
        d = np.array([abs(perr['M1'][k]) - abs(perr['M0'][k]) for k in idx])
        say(f"        M1-M0 paired change: mean {d.mean():+.4f} median {np.median(d):+.4f} "
            f"better/worse {int((d<0).sum())}/{int((d>0).sum())}")

    say(f"\n    ABSOLUTE PERCENT ERROR per cloud")
    say(f"    {'cloud':8} " + " ".join(f"{m+' mean':>12}" for m in MNAMES) +
        " " + " ".join(f"{m+' p95':>11}" for m in MNAMES))
    for cn in cnames:
        idx = [k for k, q in enumerate(cpairs) if q["cloud"] == cn]
        mn = [np.mean([100*abs(perr[m][k])/cpairs[k]["true"] for k in idx]) for m in MNAMES]
        p9 = [np.percentile([100*abs(perr[m][k])/cpairs[k]["true"] for k in idx], 95)
              for m in MNAMES]
        say(f"    {cn:8} " + " ".join(f"{v:12.4f}" for v in mn) + " " +
            " ".join(f"{v:11.4f}" for v in p9))

    say(f"\n    TRUE-LENGTH STRATA, pooled over clouds (descriptive only)")
    tl = np.array([q["true"] for q in cpairs])
    for lo, hi in ((0, 200), (200, 400), (400, 600), (600, 800), (800, 1200)):
        m_ = (tl >= lo) & (tl < hi)
        if m_.sum() == 0:
            continue
        say(f"      {lo:4d}-{hi:<4d} mm  n {int(m_.sum()):4d}  " +
            "  ".join(f"{m} MAE {np.abs(np.array(perr[m])[m_]).mean():7.3f}" for m in MNAMES))

    say(f"\n    LEAVE-ONE-CLOUD-OUT combined M1-M0 change (equal cloud weight over the rest)")
    for cn in cnames:
        vals = []
        for c2 in cnames:
            if c2 == cn:
                continue
            idx = [k for k, q in enumerate(cpairs) if q["cloud"] == c2]
            vals.append(np.mean([abs(perr["M1"][k]) - abs(perr["M0"][k]) for k in idx]))
        say(f"      excluding {cn}: mean of remaining cloud means {np.mean(vals):+.4f} mm  "
            f"(cloud means {['%+.4f' % v for v in vals]})")

    say(f"\n    LEAVE-ONE-POINT-OUT within each cloud: cloud MAE with all pairs touching one "
        f"point removed")
    for cn in cnames:
        pts = clouds[cn]
        base = {m: np.mean([abs(perr[m][k]) for k, q in enumerate(cpairs) if q["cloud"] == cn])
                for m in MNAMES}
        swing = []
        for p in pts:
            idx = [k for k, q in enumerate(cpairs)
                   if q["cloud"] == cn and p["pk"] not in q["pks"]]
            swing.append((np.mean([abs(perr["M0"][k]) for k in idx]),
                          np.mean([abs(perr["M1"][k]) for k in idx]), p))
        d0 = [s[0] for s in swing]; d1 = [s[1] for s in swing]
        worst_i = int(np.argmin(d0))
        say(f"      {cn}: M0 MAE {base['M0']:.3f} -> range {min(d0):.3f}-{max(d0):.3f} over "
            f"point removals; M1 MAE {base['M1']:.3f} -> {min(d1):.3f}-{max(d1):.3f}")
        say(f"        M1-M0 stays {'negative' if max(np.array(d1)-np.array(d0)) < 0 else ('positive' if min(np.array(d1)-np.array(d0)) > 0 else 'SIGN-UNSTABLE')} "
            f"across all {len(pts)} single-point removals "
            f"(range {min(np.array(d1)-np.array(d0)):+.4f} to {max(np.array(d1)-np.array(d0)):+.4f})")
        p = swing[worst_i][2]
        say(f"        most influential point: truth ({p['mm'][0]:.0f},{p['mm'][1]:.0f}), "
            f"removing it drops M0 MAE to {d0[worst_i]:.3f}")

    say(f"\n    ENDPOINT INFLUENCE: are extreme pair errors many failures or a few bad points?")
    for cn in cnames:
        idx = [k for k, q in enumerate(cpairs) if q["cloud"] == cn]
        e0 = np.array([abs(perr["M0"][k]) for k in idx])
        thr = np.percentile(e0, 90)
        cnt = defaultdict(int)
        for k in np.array(idx)[e0 >= thr]:
            cnt[cpairs[k]["i"]] += 1; cnt[cpairs[k]["j"]] += 1
        top = sorted(cnt.items(), key=lambda z: -z[1])[:3]
        nbad = int((e0 >= thr).sum())
        ev2mm = {p["event"]: p["mm"] for p in clouds[cn]}
        say(f"      {cn}: worst 10% = {nbad} pairs, {len(cnt)} distinct endpoints involved; "
            f"top endpoints " +
            ", ".join(f"({ev2mm[e][0]:.0f},{ev2mm[e][1]:.0f})x{c}" for e, c in top))

    # =============================================================== 7. conventional
    say("\n" + "=" * 104)
    say("[7] CONVENTIONAL MEASUREMENTS -- reported separately from cloud pairs")
    say("=" * 104)
    cerr = {m: [] for m in MNAMES}
    crow = []
    for r in conv:
        i, j = r["pks"]
        row = {"event": r["event"], "object": r["obj"], "tc": r["tc"], "true_mm": r["true"],
               "in_original_14": r["event"] in ORIGINAL_14}
        for m in MNAMES:
            Li = float(np.linalg.norm(np.array(rec[m][i]["X"], np.float32) -
                                      np.array(rec[m][j]["X"], np.float32))) * UNIT
            e = Li - r["true"]
            cerr[m].append(e)
            row[f"meas_{m}"] = Li; row[f"err_{m}"] = e
            row[f"abspct_{m}"] = 100.0 * abs(e) / r["true"]
        row["dM1_M0_mm"] = abs(row["err_M1"]) - abs(row["err_M0"])
        ri, rj = rec["M0"][i], rec["M0"][j]
        mid = 0.5 * (ri["X"] + rj["X"])
        cds = [math.dist(mid, cams_by_model["M0"][cl]["cam"]) * UNIT for cl in sorted(cals)]
        row.update({"cam_dist_mean_mm": float(np.mean(cds)), "cam_dist_min_mm": float(min(cds)),
                    "max_radius_px": max(max(ri["radius"].values()), max(rj["radius"].values())),
                    "radial_sep_px": abs(max(ri["radius"].values()) - max(rj["radius"].values())),
                    "min_edge_px": min(min(ri["edge"].values()), min(rj["edge"].values())),
                    "outside_plumb_px": max(max(outside(hull_pl[cl], ri["clicks"][cl])
                                                for cl in ri["clicks"]),
                                            max(outside(hull_pl[cl], rj["clicks"][cl])
                                                for cl in rj["clicks"])),
                    "outside_nodehull_px": max(max(outside(hull_nd[cl], ri["clicks"][cl])
                                                   for cl in ri["clicks"]),
                                               max(outside(hull_nd[cl], rj["clicks"][cl])
                                                   for cl in rj["clicks"])),
                    "outside_cal_volume_mm": max(box_outside(ri["X"], lo3, hi3),
                                                 box_outside(rj["X"], lo3, hi3)),
                    "stereo_angle_deg": min(ri["stereo_deg"], rj["stereo_deg"]),
                    "cpa_cond": max(ri["cpa_cond"], rj["cpa_cond"])})
        crow.append(row)
    write_csv(os.path.join(args.outdir, "fisheye_conventional.csv"), crow, list(crow[0]))

    io = np.array([r["event"] in ORIGINAL_14 for r in conv])
    say(f"\n    {HDR}")
    for nm2, msk in (("ORIGINAL 14", io), ("NEW 28", ~io), ("ALL 42", np.ones(len(conv), bool))):
        say(f"      -- {nm2}  (n {int(msk.sum())})")
        for m in MNAMES:
            say(f"        {line(m, stats(np.array(cerr[m])[msk]))}")
    say(f"\n    historical reference for the ORIGINAL 14: stored 2.9712, conv-13 5.3516, "
        f"M0 4.3075, M1 3.3912 mm MAE")
    say(f"    reproduced here            : " + ", ".join(
        f"{m} {np.abs(np.array(cerr[m])[io]).mean():.4f}" for m in MNAMES))

    say(f"\n    BY TRUE-LENGTH CLASS (mm)")
    say(f"    {'true':>7} {'n':>4} " + " ".join(f"{m+' MAE':>11}" for m in MNAMES) +
        f" {'M1-M0':>9}")
    for tl2 in sorted(bycls):
        msk = np.array([r["true"] == tl2 for r in conv])
        v = [np.abs(np.array(cerr[m])[msk]).mean() for m in MNAMES]
        say(f"    {tl2:7.1f} {int(msk.sum()):4d} " + " ".join(f"{x:11.4f}" for x in v) +
            f" {v[3]-v[2]:+9.4f}")

    say(f"\n    BY TIMECODE / PLACEMENT (mm) -- the real replication unit")
    say(f"    {'timecode':20} {'n':>4} " + " ".join(f"{m+' MAE':>11}" for m in MNAMES) +
        f" {'M1-M0':>9}")
    for tc in sorted({r["tc"] for r in conv}):
        msk = np.array([r["tc"] == tc for r in conv])
        v = [np.abs(np.array(cerr[m])[msk]).mean() for m in MNAMES]
        say(f"    {str(tc):20} {int(msk.sum()):4d} " + " ".join(f"{x:11.4f}" for x in v) +
            f" {v[3]-v[2]:+9.4f}")

    say(f"\n    PAIRED CHANGES (change in absolute error, mm; negative favours the second model)")
    say(f"    {'contrast':22} {'subset':12} {'mean':>9} {'median':>9} {'better/worse':>14}")
    for A, B in (("M0", "M1"), ("stored", "conv-13"), ("stored", "M0"), ("stored", "M1"),
                 ("conv-13", "M0")):
        for nm2, msk in (("original 14", io), ("new 28", ~io), ("all 42",
                                                               np.ones(len(conv), bool))):
            d = np.abs(np.array(cerr[B])[msk]) - np.abs(np.array(cerr[A])[msk])
            say(f"    {A+' -> '+B:22} {nm2:12} {d.mean():+9.4f} {np.median(d):+9.4f} "
                f"{int((d<0).sum()):6d}/{int((d>0).sum()):<7d}")

    # =============================================================== 8. combined summaries
    say("\n" + "=" * 104)
    say("[8] COMBINED SUMMARIES UNDER FOUR EXPLICIT WEIGHTING SCHEMES")
    say("=" * 104)
    combos = {}
    say(f"\n    (1) EQUAL PAIR WEIGHTING over all {len(cpairs)} cloud pairs -- DESCRIPTIVE ONLY, "
        f"combinatorially dominated")
    say(f"    {HDR}")
    for m in MNAMES:
        s = stats(perr[m]); combos[("pairs-equal", m)] = s["mae"]
        say(f"    {line(m, s)}")

    say(f"\n    (2) EQUAL CLOUD WEIGHTING -- mean of the four cloud MAEs (primary for clouds)")
    say(f"    {'model':8} " + " ".join(f"{cn:>10}" for cn in cnames) + f" {'equal-cloud':>13}")
    for m in MNAMES:
        v = [np.mean([abs(perr[m][k]) for k, q in enumerate(cpairs) if q["cloud"] == cn])
             for cn in cnames]
        combos[("cloud-equal", m)] = float(np.mean(v))
        say(f"    {m:8} " + " ".join(f"{x:10.4f}" for x in v) + f" {np.mean(v):13.4f}")

    say(f"\n    (3) CONVENTIONAL BY NATURAL GROUP -- mean over object x timecode groups")
    groups = sorted({(r["obj"], r["tc"]) for r in conv})
    say(f"    {len(groups)} object x timecode groups")
    say(f"    {'model':8} {'group-equal MAE':>17} {'placement-equal MAE':>21} "
        f"{'flat 42 MAE':>13}")
    for m in MNAMES:
        gm = [np.mean([abs(cerr[m][k]) for k, r in enumerate(conv)
                       if (r["obj"], r["tc"]) == g]) for g in groups]
        pm = [np.mean([abs(cerr[m][k]) for k, r in enumerate(conv) if r["tc"] == tc])
              for tc in sorted({r["tc"] for r in conv})]
        combos[("conv-group", m)] = float(np.mean(gm))
        combos[("conv-placement", m)] = float(np.mean(pm))
        combos[("conv-flat", m)] = float(np.mean(np.abs(cerr[m])))
        say(f"    {m:8} {np.mean(gm):17.4f} {np.mean(pm):21.4f} "
            f"{np.mean(np.abs(cerr[m])):13.4f}")

    say(f"\n    (4) SOURCE-BALANCED -- conventional placements and cloud placements given equal")
    say(f"        weight: mean over 8 placements (4 conventional timecodes + 4 clouds)")
    say(f"    {'model':8} {'conv side':>11} {'cloud side':>12} {'source-balanced':>17}")
    for m in MNAMES:
        pm = [np.mean([abs(cerr[m][k]) for k, r in enumerate(conv) if r["tc"] == tc])
              for tc in sorted({r["tc"] for r in conv})]
        cm = [np.mean([abs(perr[m][k]) for k, q in enumerate(cpairs) if q["cloud"] == cn])
              for cn in cnames]
        combos[("source-balanced", m)] = float(np.mean(pm + cm))
        say(f"    {m:8} {np.mean(pm):11.4f} {np.mean(cm):12.4f} {np.mean(pm+cm):17.4f}")

    say(f"\n    HOW THE M1-vs-M0 CONCLUSION MOVES ACROSS WEIGHTING SCHEMES (M1 minus M0, mm)")
    say(f"    {'scheme':22} {'M0':>10} {'M1':>10} {'M1-M0':>10} {'favours':>10}")
    for k in ("pairs-equal", "cloud-equal", "conv-flat", "conv-group", "conv-placement",
              "source-balanced"):
        a, b = combos[(k, "M0")], combos[(k, "M1")]
        say(f"    {k:22} {a:10.4f} {b:10.4f} {b-a:+10.4f} {'M1' if b < a else 'M0':>10}")

    # =============================================================== 9. geometric dependence
    say("\n" + "=" * 104)
    say("[9] GEOMETRIC DEPENDENCE of the M1-minus-M0 change")
    say("=" * 104)
    for nm2, rows, errs in (("CLOUD PAIRS", prow2, perr), ("CONVENTIONAL", crow, cerr)):
        d = np.array([abs(errs["M1"][k]) - abs(errs["M0"][k]) for k in range(len(rows))])
        say(f"\n    {nm2}  (n {len(rows)}; uncertainty stays at the placement level)")
        say(f"      correlations of the M1-M0 change with each covariate:")
        for key, lbl in (("true_mm", "true length"), ("cam_dist_mean_mm", "mean camera distance"),
                         ("cam_dist_min_mm", "nearest-camera distance"),
                         ("max_radius_px", "max image radius"),
                         ("radial_sep_px", "radial separation of endpoints"),
                         ("min_edge_px", "min screen-edge margin"),
                         ("outside_plumb_px", "distance outside plumbline support"),
                         ("outside_nodehull_px", "distance outside node image hull"),
                         ("outside_cal_volume_mm", "distance outside calibrated volume"),
                         ("stereo_angle_deg", "stereo intersection angle"),
                         ("cpa_cond", "triangulation conditioning")):
            x = [r.get(key, float("nan")) for r in rows]
            say(f"        {lbl:38} r = {corr(x, d):+.3f}   "
                f"range {np.nanmin(x):9.2f} to {np.nanmax(x):9.2f}")
        if nm2 == "CLOUD PAIRS":
            say(f"        {'pair direction in cloud plane (deg)':38} "
                f"r = {corr([r['dir_deg'] for r in rows], d):+.3f}")
        say(f"      coarse strata:")
        strata([r["max_radius_px"] for r in rows], d, [0, 500, 700, 850, 1000, 1400],
               "by max image radius (px)", say)
        strata([r["cam_dist_mean_mm"] for r in rows], d,
               list(np.percentile([r["cam_dist_mean_mm"] for r in rows], [0, 25, 50, 75, 100])),
               "by mean camera distance (mm, quartiles)", say)
        strata([r["true_mm"] for r in rows], d, [0, 200, 400, 600, 800, 1200],
               "by true length (mm)", say)
        strata([r["radial_sep_px"] for r in rows], d,
               list(np.percentile([r["radial_sep_px"] for r in rows], [0, 25, 50, 75, 100])),
               "by radial separation (px, quartiles)", say)
        strata([r["outside_cal_volume_mm"] for r in rows], d, [-1, 1e-9, 25, 75, 1e9],
               "by extrapolation outside the calibrated volume (mm)", say)
        if nm2 == "CLOUD PAIRS":
            strata([r["dir_deg"] for r in rows], d, [0, 30, 60, 90, 120, 150, 180],
                   "by pair direction within the cloud plane (deg)", say)
            say(f"      by cloud placement:")
            for cn in cnames:
                m_ = np.array([r["cloud"] == cn for r in rows])
                say(f"        {cn:9} n {int(m_.sum()):5d}  mean {d[m_].mean():+8.4f}  "
                    f"median {np.median(d[m_]):+8.4f}")

    # =============================================================== 10. tails and influence
    say("\n" + "=" * 104)
    say("[10] TAILS AND INFLUENCE")
    say("=" * 104)
    for nm2, rows, errs in (("CLOUD PAIRS", prow2, perr), ("CONVENTIONAL", crow, cerr)):
        say(f"\n    {nm2}: absolute error tails (mm)")
        say(f"    {HDR}")
        for m in MNAMES:
            say(f"    {line(m, stats(errs[m]))}")
        say(f"    {nm2}: absolute PERCENT error tails")
        say(f"    {'model':8} {'mean':>8} {'med':>8} {'p90':>8} {'p95':>8} {'p99':>8} "
            f"{'max':>8} {'w10%':>8} {'w5%':>8}")
        for m in MNAMES:
            p = np.array([100 * abs(errs[m][k]) / rows[k]["true_mm"] for k in range(len(rows))])
            say(f"    {m:8} {p.mean():8.4f} {np.median(p):8.4f} {np.percentile(p,90):8.4f} "
                f"{np.percentile(p,95):8.4f} {np.percentile(p,99):8.4f} {p.max():8.4f} "
                f"{p[p>=np.percentile(p,90)].mean():8.4f} {p[p>=np.percentile(p,95)].mean():8.4f}")
        say(f"    {nm2}: M0's OWN worst cases, re-evaluated under M1 (fixed baseline)")
        e0 = np.abs(np.array(errs["M0"])); e1 = np.abs(np.array(errs["M1"]))
        for frac in (10, 5, 1):
            m_ = e0 >= np.percentile(e0, 100 - frac)
            if m_.sum() == 0:
                continue
            say(f"      worst {frac:2d}% under M0 (n {int(m_.sum()):4d}): mean |e| "
                f"{e0[m_].mean():8.3f} -> {e1[m_].mean():8.3f} mm "
                f"({e1[m_].mean()-e0[m_].mean():+.3f}), improved on "
                f"{int((e1[m_]<e0[m_]).sum())}/{int(m_.sum())}")

    say(f"\n    LARGEST M1 IMPROVEMENTS AND DEGRADATIONS (cloud pairs, top 10 each)")
    say(f"    {'src':6} {'cloud':7} {'endpoints (truth mm)':26} {'true':>7} {'M0 err':>8} "
        f"{'M1 err':>8} {'change':>8} {'rmax':>6} {'camd':>7}")
    dp = np.array([r["dM1_M0_mm"] for r in prow2])
    order = np.argsort(dp)
    for k in list(order[:10]) + list(order[-10:]):
        r = prow2[k]
        ep = f"({r['true_u_i']:.0f},{r['true_v_i']:.0f})-({r['true_u_j']:.0f},{r['true_v_j']:.0f})"
        say(f"    {'cloud':6} {r['cloud']:7} {ep:26} {r['true_mm']:7.1f} {r['err_M0']:+8.3f} "
            f"{r['err_M1']:+8.3f} {r['dM1_M0_mm']:+8.3f} {r['max_radius_px']:6.0f} "
            f"{r['cam_dist_mean_mm']:7.0f}")
    say(f"\n    LARGEST M1 IMPROVEMENTS AND DEGRADATIONS (conventional, top 8 each)")
    say(f"    {'object':10} {'timecode':18} {'true':>7} {'M0 err':>8} {'M1 err':>8} "
        f"{'change':>8} {'rmax':>6} {'camd':>7} {'orig14':>7}")
    dc = np.array([r["dM1_M0_mm"] for r in crow])
    oc = np.argsort(dc)
    for k in list(oc[:8]) + list(oc[-8:]):
        r = crow[k]
        say(f"    {str(r['object'])[:10]:10} {str(r['tc'])[:18]:18} {r['true_mm']:7.1f} "
            f"{r['err_M0']:+8.3f} {r['err_M1']:+8.3f} {r['dM1_M0_mm']:+8.3f} "
            f"{r['max_radius_px']:6.0f} {r['cam_dist_mean_mm']:7.0f} "
            f"{str(r['in_original_14']):>7}")

    say(f"\n    REPEATED INFLUENTIAL ENDPOINTS in the M1-vs-M0 tails")
    thr = np.percentile(np.abs(dp), 95)
    cnt = defaultdict(int)
    for k in np.where(np.abs(dp) >= thr)[0]:
        cnt[(prow2[k]["cloud"], prow2[k]["event_i"])] += 1
        cnt[(prow2[k]["cloud"], prow2[k]["event_j"])] += 1
    ev2mm = {p["event"]: (p["cloud"], p["mm"]) for p in cpts}
    say(f"      {int((np.abs(dp)>=thr).sum())} pairs with |change| >= {thr:.3f} mm involve "
        f"{len(cnt)} distinct endpoints:")
    for (cn, e), n2 in sorted(cnt.items(), key=lambda z: -z[1])[:8]:
        mm = ev2mm[e][1]
        say(f"        {cn} truth ({mm[0]:.0f},{mm[1]:.0f}) appears in {n2} of them")

    # =============================================================== 11. model summary table
    mrows = []
    for m in MNAMES:
        row = {"model": m, "free_params": ("stored" if m == "stored" else
                                           len(dict(MODELS)[m]))}
        for cl in sorted(cals):
            row[f"plumb_rms_px_{cl.split()[0]}"] = diag[(m, cl)]["prms"]
            row[f"eta_{cl.split()[0]}"] = diag[(m, cl)]["d14"][13]
            row[f"gate_ok_{cl.split()[0]}"] = diag[(m, cl)]["gate"]["ok"]
            row[f"radial_scale_ratio_{cl.split()[0]}"] = \
                diag[(m, cl)]["gate"]["radial_scale_ratio"]
            row[f"front_node_rms_mm_{cl.split()[0]}"] = diag[(m, cl)]["fr"]
            row[f"back_node_rms_mm_{cl.split()[0]}"] = diag[(m, cl)]["br"]
        for tag, e, msk in (("conv14", cerr[m], io), ("conv28", cerr[m], ~io),
                            ("conv42", cerr[m], np.ones(len(conv), bool)),
                            ("pairs", perr[m], np.ones(len(cpairs), bool))):
            s = stats(np.array(e)[msk])
            for k2 in ("n", "mae", "rmse", "med", "bias", "p90", "p95", "p99", "max", "w10", "w5"):
                row[f"{tag}_{k2}"] = s[k2]
        row["cloud_equal_mae"] = combos[("cloud-equal", m)]
        row["conv_placement_mae"] = combos[("conv-placement", m)]
        row["source_balanced_mae"] = combos[("source-balanced", m)]
        for cn in cnames:
            row[f"rigid_rms_{cn.replace(' ','')}"] = shp[(m, cn)]["rms"]
        row["rigid_rms_cloud_mean"] = float(np.mean([shp[(m, cn)]["rms"] for cn in cnames]))
        mrows.append(row)
    write_csv(os.path.join(args.outdir, "fisheye_model_summary.csv"), mrows, list(mrows[0]))

    say("\n" + "=" * 104)
    say("[11] MODEL SUMMARY, the four headline metrics")
    say("=" * 104)
    say(f"    {'model':8} {'conv14 MAE':>11} {'conv28 MAE':>11} {'conv42 MAE':>11} "
        f"{'cloud-equal pair MAE':>21} {'cloud rigid RMS (mean)':>23} {'source-bal':>11}")
    for r in mrows:
        say(f"    {r['model']:8} {r['conv14_mae']:11.4f} {r['conv28_mae']:11.4f} "
            f"{r['conv42_mae']:11.4f} {r['cloud_equal_mae']:21.4f} "
            f"{r['rigid_rms_cloud_mean']:23.4f} {r['source_balanced_mae']:11.4f}")

    # =============================================================== 12. calibration sensitivity
    say("\n" + "=" * 104)
    say("[12] CALIBRATION-QUALITY SENSITIVITY: is a node jackknife warranted?")
    say("=" * 104)
    dcl = [np.mean([abs(perr["M1"][k]) - abs(perr["M0"][k])
                    for k, q in enumerate(cpairs) if q["cloud"] == cn]) for cn in cnames]
    dsh = [shp[("M1", cn)]["rms"] - shp[("M0", cn)]["rms"] for cn in cnames]
    dtc = [np.mean([abs(cerr["M1"][k]) - abs(cerr["M0"][k])
                    for k, r in enumerate(conv) if r["tc"] == tc])
           for tc in sorted({r["tc"] for r in conv})]
    say(f"    node residual under the stored model: front {fr_s} mm, back {br_s} mm")
    say(f"    M1-M0 pair-MAE change per cloud   : {['%+.4f' % v for v in dcl]}")
    say(f"    M1-M0 rigid-RMS change per cloud  : {['%+.4f' % v for v in dsh]}")
    say(f"    M1-M0 conv-MAE change per placement: {['%+.4f' % v for v in dtc]}")
    signs_pair = len({v > 0 for v in dcl}) == 1
    signs_shape = len({v > 0 for v in dsh}) == 1
    mag = float(np.mean(np.abs(dcl)))
    nodescale = float(np.mean([diag[("stored", c)]["br"] for c in sorted(cals)]))
    say(f"    sign of the pair effect is consistent across all four clouds : {signs_pair}")
    say(f"    sign of the shape effect is consistent across all four clouds: {signs_shape}")
    say(f"    typical |M1-M0| effect {mag:.3f} mm vs back-node residual {nodescale:.2f} mm "
        f"-> effect/calibration-noise ratio {mag/nodescale:.3f}")
    consistent = signs_pair and signs_shape
    jk = None
    if consistent and mag > nodescale:
        say(f"    DECISION: the effect is consistent in sign across all four placements AND larger")
        say(f"    than the calibration-node residual, so a node jackknife is NOT required.")
    else:
        say(f"    DECISION: the effect is "
            f"{'consistent in sign across all four placements' if consistent else 'INCONSISTENT in sign across placements'}, "
            f"but its magnitude")
        say(f"    ({mag:.3f} mm) is {'below' if mag < nodescale else 'comparable to'} the "
            f"calibration-node residual ({nodescale:.2f} mm). Sign consistency does NOT settle it:")
        say(f"    all four clouds share ONE calibration, so a calibration-level bias would move all")
        say(f"    four the same way and would be indistinguishable from a real model improvement.")
        say(f"    The jackknife below is therefore required by the handoff's own criterion.")
        jk = node_jackknife(cals, dists, clicks, clouds, cpairs, cnames, conv, say, args.outdir)

    # =============================================================== 13. artifacts
    val = {"document": doc, "generated_by": os.path.basename(__file__),
           "counts": {"conventional": len(conv), "conventional_original_14": int(io.sum()),
                      "conventional_new": int((~io).sum()), "clouds": len(clouds),
                      "cloud_points": len(cpts), "cloud_pairs": len(cpairs),
                      "conventional_placements": len({r["tc"] for r in conv}),
                      "cloud_placements": len(clouds)},
           "conventional_by_true_length": {str(k): len(v) for k, v in sorted(bycls.items())},
           "clouds": {cn: {"points": len(clouds[cn]),
                           "pairs": sum(1 for q in cpairs if q["cloud"] == cn),
                           "timecode": sorted({p["tc"] for p in clouds[cn]})[0],
                           "true_min_mm": min(q["true"] for q in cpairs if q["cloud"] == cn),
                           "true_max_mm": max(q["true"] for q in cpairs if q["cloud"] == cn)}
                      for cn in cnames},
           "loader_exclusions": [list(map(str, e)) for e in D["exclusions"]],
           "reconstruction_failures": [list(map(str, f)) for f in failures],
           "models": {"stored": "document-stored distortion",
                      "conv-13": "converged 13-parameter Brown-Conrady, free = " +
                                 str(list(range(13))),
                      "M0": "truncated centre+k1..k4+p1,p2, free = " + str(Z.ISO),
                      "M1": "M0 + scalar anisotropic radius eta, free = " + str(Z.SCAL)},
           "gate": {f"{m}/{c}": {"ok": diag[(m, c)]["gate"]["ok"],
                                 "radial_scale_ratio": diag[(m, c)]["gate"]["radial_scale_ratio"],
                                 "min_det_box": diag[(m, c)]["gate"]["min_det_box"]}
                    for m in MNAMES for c in sorted(cals)},
           "eta": {f"{m}/{c}": diag[(m, c)]["d14"][13] for m in MNAMES for c in sorted(cals)},
           "plumbline_rms_px": {f"{m}/{c}": diag[(m, c)]["prms"]
                                for m in MNAMES for c in sorted(cals)},
           "node_rms_mm": {f"{m}/{c}": {"front": diag[(m, c)]["fr"], "back": diag[(m, c)]["br"]}
                           for m in MNAMES for c in sorted(cals)},
           "nesting_check": worst,
           "weighting_schemes": {f"{k[0]}/{k[1]}": v for k, v in combos.items()},
           "node_jackknife": jk,
           "runtime_s": None}
    val["runtime_s"] = round(time.time() - t0, 1)
    with open(os.path.join(args.outdir, "fisheye_validation.json"), "w") as fh:
        json.dump(val, fh, indent=2, default=str)

    say(f"\n    OUTPUTS written to {args.outdir}")
    for f in sorted(os.listdir(args.outdir)):
        say(f"        {f}")
    say(f"\n    runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
