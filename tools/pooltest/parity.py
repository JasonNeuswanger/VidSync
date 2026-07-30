#!/usr/bin/env python3
"""Stage-by-stage parity against VidSync's stored production output.

Stage 1 here isolates TRIANGULATION from calibration. It takes the calibration exactly as the
document stores it -- both homographies, the camera position, the distortion parameters -- and asks
whether a port of VidSync's triangulation reproduces the stored 3D coordinates of every measured
point. Refraction correction does not enter, because it only affects the back-plane homography,
which is taken as given here.

That matters because it splits the previously unexplained 0.856 vs 0.990 mm discrepancy into a
calibration-rebuild part and a triangulation part, and tells us which one to chase.

Production path, from VSPoint.m:147-283 and VSEventScreenPoint.m:150-192:
  seed  = least-squares closest point of approach of the per-camera sightlines, where a sightline is
          built by undistorting the click and projecting it through the screen-to-front and
          screen-to-back homographies, then lifting both to 3D at the two plane depths
  refine= Nelder-Mead (gsl nmsimplex2) on sum over cameras of squared pixel error between the
          reprojected undistorted screen point and the input undistorted screen point; initial step
          1.0 in each of 3 dimensions, convergence when simplex characteristic size < 1e-6,
          iteration cap 500
  length= single-precision Euclidean norm of the difference of the two stored 3D points

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


dc = L("distcal")
jw = L("jacweight")

POOL = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
        "2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
DOCS = [("2012 pool test (Sony)", POOL, None, 1000.0),
        ("2015-06-22-1 Clearwater (13 mm)", os.path.join(DM, "2015-06-22-1 Clearwater.vsd"),
         "Frame Test", 1.0),
        ("2015-09-04-1 Clearwater (8 mm)", os.path.join(DM, "2015-09-04-1 Clearwater.vsd"),
         "Length Tests", 1.0)]
AX = {"x": 0, "y": 1, "z": 2}


def undistort13(x, y, d):
    """The 13-PARAMETER shipped map only (VSCalibration.mm:219). Raw sensor pixel -> ideal pinhole.

    THIS FUNCTION IGNORES eta. It reads d[0:13] and nothing else, so if `d` is a 14-vector its
    anisotropy entry d[13] is silently discarded. That is correct for reproducing shipped behaviour and
    WRONG for any M1 candidate.

    It was called `undistort` until 2026-07-29, which made it look like the module's generic,
    candidate-aware distortion map. It is not, and four scripts compensated by monkeypatching
    `parity.undistort = nodes.undistort13` at import time -- hidden global state that decided whether
    eta reached a scientific result, and that leaked between scripts through import order. The name now
    states the limitation so no caller can mistake it for a general map.

    For candidate-aware work use `downstream.DistortionMap`, which carries all 14 parameters and is
    bound to the camera it was fitted for.
    """
    xd, yd = x - d[0], y - d[1]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(d[2:9], start=1))
    T = 1.0 + d[11] * s + d[12] * s * s
    return (d[0] + xd * R + (d[9] * (s + 2 * xd * xd) + 2 * d[10] * xd * yd) * T,
            d[1] + yd * R + (2 * d[9] * xd * yd + d[10] * (s + 2 * yd * yd)) * T)


_HISTORICAL_ETA_MAP = None
_HISTORICAL_ETA_REASON = None


def install_historical_eta_map(fn, reason):
    """FROZEN HISTORICAL ROUND SCRIPTS ONLY. Do not call from anything that reports a new result.

    `sightline` and `triangulate` in this module are ports of the SHIPPED 13-parameter pipeline. Four
    historical scripts (round10.py, calab.py and, until 2026-07-29, fisheye_knownlength_analysis.py)
    made them eta-aware by assigning `parity.undistort = nodes.undistort13` at import time. That
    assignment is gone: `undistort` no longer exists under that name, so the old line would silently
    do nothing and quietly drop eta from every sightline.

    This function is the replacement, and it is deliberately awkward: it must be called explicitly,
    it demands a written reason, and it announces itself. It exists ONLY so those frozen scripts keep
    reproducing the numbers they published. New work uses `downstream.DistortionMap`, which carries all
    14 parameters explicitly and is bound to its camera.
    """
    global _HISTORICAL_ETA_MAP, _HISTORICAL_ETA_REASON
    if not isinstance(reason, str) or len(reason.strip()) < 20:
        raise ValueError("install_historical_eta_map requires a written reason of at least 20 "
                         "characters naming the historical analysis being reproduced")
    _HISTORICAL_ETA_MAP = fn
    _HISTORICAL_ETA_REASON = reason.strip()
    sys.stderr.write(f"parity.py: HISTORICAL eta-aware map installed into sightline/triangulate. "
                     f"This module is now NOT reproducing shipped 13-parameter behaviour. "
                     f"Reason: {_HISTORICAL_ETA_REASON}\n")


def historical_eta_map_state():
    """Diagnostic: what, if anything, has been installed. Authoritative runs expect None."""
    return {"installed": _HISTORICAL_ETA_MAP is not None, "reason": _HISTORICAL_ETA_REASON}


def _undistort_active(x, y, d):
    """The map `sightline`/`triangulate` actually use: shipped 13-parameter unless a historical
    script explicitly installed an eta-aware one."""
    if _HISTORICAL_ETA_MAP is None:
        return undistort13(x, y, d)
    return _HISTORICAL_ETA_MAP(x, y, d)


def apply3(m, x, y):
    w = m[2][0] * x + m[2][1] * y + m[2][2]
    return ((m[0][0] * x + m[0][1] * y + m[0][2]) / w,
            (m[1][0] * x + m[1][1] * y + m[1][2]) / w)


def lift(h, v, depth, ah, av):
    if ah == "x":
        return (h, v, depth) if av == "y" else (h, depth, v)
    if ah == "y":
        return (v, h, depth) if av == "x" else (depth, h, v)
    return (v, depth, h) if av == "x" else (depth, v, h)


def drop(p, ah, av):
    return p[AX[ah]], p[AX[av]]


def cpa_lines(lines):
    """UtilityFunctions.mm:255. Least-squares closest point of approach of n 3D lines, plus the
    mean point-line distance from that point to each line."""
    A = np.zeros((3, 3)); b = np.zeros(3)
    for p, q in lines:
        d = np.array(q, float) - np.array(p, float)
        n = np.linalg.norm(d)
        if n == 0:
            continue
        v = d / n
        M = np.eye(3) - np.outer(v, v)
        A += M
        b += M @ np.array(p, float)
    P = np.linalg.solve(A, b)
    tot = 0.0
    for p, q in lines:
        x1x0 = np.array(p, float) - P
        x2x1 = np.array(q, float) - np.array(p, float)
        n2 = np.linalg.norm(x2x1)
        if n2 == 0:
            continue
        dsq = (np.dot(x1x0, x1x0) * n2 * n2 - np.dot(x1x0, x2x1) ** 2) / (n2 * n2)
        tot += math.sqrt(max(0.0, dsq))
    return P, tot / len(lines)


def sightline(sx, sy, c):
    u = _undistort_active(sx, sy, c["dist"])
    f = apply3(c["s2f"], *u)
    b = apply3(c["s2b"], *u)
    return (lift(f[0], f[1], c["front_d"], c["ah"], c["av"]),
            lift(b[0], b[1], c["back_d"], c["ah"], c["av"]))


def reproject(P, c):
    """VSPoint.m:30-53. Candidate 3D point -> line to camera -> front plane -> undistorted screen."""
    ax = AX[({"x", "y", "z"} - {c["ah"], c["av"]}).pop()]
    da = P[ax] - c["front_d"]
    db = c["cam"][ax] - c["front_d"]
    if abs(da - db) < 1e-15:
        return None
    t = da / (da - db)
    hit = tuple(P[i] + t * (c["cam"][i] - P[i]) for i in range(3))
    return apply3(c["f2s"], *drop(hit, c["ah"], c["av"]))


def triangulate(obs, exact=True):
    """obs is a list of (calibration dict, (screenX, screenY))."""
    lines = [sightline(xy[0], xy[1], c) for c, xy in obs]
    seed, pld = cpa_lines(lines)
    prep = [(c, _undistort_active(xy[0], xy[1], c["dist"])) for c, xy in obs]

    def res(P):
        out = []
        for c, u in prep:
            r = reproject(P, c)
            if r is None:
                return np.full(2 * len(prep), 1e9)
            out += [r[0] - u[0], r[1] - u[1]]
        return np.array(out)
    if not exact:
        return seed, pld, float("nan")
    r = least_squares(res, seed, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=20000)
    f = float(r.fun @ r.fun)
    return r.x, pld, math.sqrt(f / len(prep))


def load(vsd, typefilter):
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    cams = {}
    for row in db.execute(
            "SELECT v.ZCLIPNAME, c.ZAXISHORIZONTAL, c.ZAXISVERTICAL, c.ZPLANECOORDFRONT, "
            "c.ZPLANECOORDBACK, c.ZCAMERAX, c.ZCAMERAY, c.ZCAMERAZ, c.ZCAMERAMEANPLD, "
            "c.ZMATRIXSCREENTOQUADRATFRONT, c.ZMATRIXSCREENTOQUADRATBACK, "
            "c.ZMATRIXQUADRATFRONTTOSCREEN, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
            "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
            "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
            "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4 FROM ZVSCALIBRATION c "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
        cams[row[0]] = {
            "clip": row[0], "ah": row[1], "av": row[2], "front_d": row[3], "back_d": row[4],
            "cam": (row[5], row[6], row[7]), "camPLD": row[8],
            "s2f": jw.unarchive_matrix(row[9]), "s2b": jw.unarchive_matrix(row[10]),
            "f2s": jw.unarchive_matrix(row[11]), "dist": list(row[12:25])}
    clicks = defaultdict(dict)
    for pt, clip, x, y in db.execute(
            "SELECT p.ZPOINT, v.ZCLIPNAME, p.ZSCREENX, p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        clicks[pt][clip] = (x, y)
    sql = ("SELECT o.ZNAME2, t.ZNAME3, e.Z_PK, p.Z_PK, p.ZWORLDX, p.ZWORLDY, p.ZWORLDZ, "
           "p.ZMEANPLD, p.ZREPROJECTIONERRORNORM, p.ZNEARESTCAMERADISTANCE "
           "FROM ZVSVISIBLEITEM e "
           "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
           "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
           "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
           "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK WHERE e.Z_ENT = 17")
    args = ()
    if typefilter:
        sql += " AND t.ZNAME3 = ?"; args = (typefilter,)
    ev = defaultdict(list); names = {}
    for nm, tn, e, pk, wx, wy, wz, pld, rep, ncd in db.execute(
            sql + " ORDER BY e.Z_PK, p.ZINDEX", args):
        ev[e].append({"pk": pk, "w": (wx, wy, wz), "pld": pld, "rep": rep, "ncd": ncd})
        names[e] = (nm, tn)
    db.close()
    return cams, clicks, ev, names


def main():
    say = print
    say("=" * 100)
    say("STAGE 1 PARITY: triangulation only, calibration taken exactly as stored")
    say("=" * 100)
    for label, vsd, tf, unit in DOCS:
        cams, clicks, ev, names = load(vsd, tf)
        say(f"\n  {label}")
        dpos, dpld, drep = [], [], []
        nmiss = 0
        lens = []
        for e, pts in sorted(ev.items()):
            if len(pts) != 2:
                continue
            true = jw.true_length_mm(*names[e], unit)
            got = []
            for p in pts:
                obs = [(cams[c], clicks[p["pk"]][c]) for c in sorted(cams)
                       if c in clicks.get(p["pk"], {})]
                if len(obs) < 2:
                    nmiss += 1; got = None; break
                P, pld, rep = triangulate(obs)
                dpos.append(np.linalg.norm(P - np.array(p["w"], float)) * unit)
                if p["pld"] is not None:
                    dpld.append(abs(pld - p["pld"]) * unit)
                if p["rep"] is not None and np.isfinite(rep):
                    drep.append(abs(rep - p["rep"]))
                got.append(P)
            if got and true is not None:
                a = np.array(got[0], np.float32); b = np.array(got[1], np.float32)
                lens.append((float(np.linalg.norm(a - b)) * unit, true))
        dpos = np.array(dpos)
        say(f"    3D position vs stored, over {len(dpos)} points: median "
            f"{np.median(dpos):.3e} mm, 95th {np.percentile(dpos,95):.3e}, "
            f"max {dpos.max():.3e} mm")
        if dpld:
            dpld = np.array(dpld)
            say(f"    meanPLD vs stored: median {np.median(dpld):.3e} mm, max {dpld.max():.3e}")
        if drep:
            drep = np.array(drep)
            say(f"    reprojectionErrorNorm vs stored: median {np.median(drep):.3e} px, "
                f"max {drep.max():.3e} px")
        if nmiss:
            say(f"    {nmiss} events skipped for having fewer than two clicked cameras")
        e = [m - t for m, t in lens]
        n = len(e)
        say(f"    known lengths recomputed from OUR 3D points: n {n}, "
            f"mean abs err {sum(abs(v) for v in e)/n:.4f} mm, "
            f"rms {math.sqrt(sum(v*v for v in e)/n):.4f}, bias {sum(e)/n:+.4f}")
        # and the same lengths straight from the stored coordinates, as the app reports them
        se = []
        for ee, pts in sorted(ev.items()):
            if len(pts) != 2:
                continue
            true = jw.true_length_mm(*names[ee], unit)
            if true is None:
                continue
            a = np.array(pts[0]["w"], np.float32); b = np.array(pts[1]["w"], np.float32)
            se.append(float(np.linalg.norm(a - b)) * unit - true)
        n = len(se)
        say(f"    known lengths from STORED 3D points: n {n}, "
            f"mean abs err {sum(abs(v) for v in se)/n:.4f} mm, "
            f"rms {math.sqrt(sum(v*v for v in se)/n):.4f}, bias {sum(se)/n:+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
