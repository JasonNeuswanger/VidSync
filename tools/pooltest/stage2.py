#!/usr/bin/env python3
"""Stage 2 parity: current-production recalibration versus stored historical calibration.

Drives the C++ oracle (oracle.cpp), which calls the same Accelerate LAPACK and GSL routines
production calls, through the exact `calculateCalibration` ordering: front surface uncorrected, then
the back surface in a fixed-point loop whose first iteration is uncorrected and whose camera position
is recomputed after every iteration.

Homographies are homogeneous, so coefficient comparison is meaningless. Everything here is compared
by INDUCED MAPPING at the calibration nodes, on a grid over the calibration plane, and at
extrapolation points, reported as maximum and RMS discrepancy in world units.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import subprocess
import sqlite3
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


jw = L("jacweight")
pa = L("parity")
DOCS = pa.DOCS
ORACLE = os.path.join(HERE, "oracle")


def load_cal(vsd):
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    out = {}
    for row in db.execute(
            "SELECT c.Z_PK, v.ZCLIPNAME, c.ZAXISHORIZONTAL, c.ZAXISVERTICAL, c.ZPLANECOORDFRONT, "
            "c.ZPLANECOORDBACK, c.ZCAMERAX, c.ZCAMERAY, c.ZCAMERAZ, c.ZCAMERAMEANPLD, "
            "c.ZMATRIXSCREENTOQUADRATFRONT, c.ZMATRIXSCREENTOQUADRATBACK, "
            "c.ZMATRIXQUADRATFRONTTOSCREEN, c.ZSHOULDCORRECTREFRACTION, "
            "c.ZFRONTQUADRATSURFACETHICKNESS, c.ZFRONTQUADRATSURFACEREFRACTIVEINDEX, "
            "c.ZMEDIUMREFRACTIVEINDEX, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
            "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
            "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
            "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4 FROM ZVSCALIBRATION c "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
        pk, clip = row[0], row[1]
        c = {"pk": pk, "clip": clip, "ah": row[2], "av": row[3], "front_d": row[4],
             "back_d": row[5], "cam": (row[6], row[7], row[8]), "camPLD": row[9],
             "s2f": jw.unarchive_matrix(row[10]), "s2b": jw.unarchive_matrix(row[11]),
             "f2s": jw.unarchive_matrix(row[12]), "refract": row[13],
             "thick": row[14], "n2": row[15], "n1": row[16], "dist": list(row[17:30]),
             "front": [], "back": []}
        out[clip] = c
    # The two Core Data relations are the opposite way round from their column names' suggestion.
    # Verified empirically on all six cameras: ZCALIBRATION nodes are reproduced by the stored
    # screen-to-quadrat-BACK matrix (0.0009 mm rms on the pool test) and ZCALIBRATION1 nodes by
    # screen-to-quadrat-FRONT (0.0006 mm), not the reverse. distcal.build and modeltest.py had these
    # swapped, which is a second independent defect in the old calibration rebuild alongside the
    # missing refraction correction.
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION IS NOT NULL ORDER BY ZINDEX"):
        for c in out.values():
            if c["pk"] == pk:
                c["back"].append((x, y, h, v))
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION1, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION1 IS NOT NULL ORDER BY ZINDEX"):
        for c in out.values():
            if c["pk"] == pk:
                c["front"].append((x, y, h, v))
    db.close()
    return out


def run_oracle(c, dist=None, eta=0.0, niter=0):
    d = c["dist"] if dist is None else dist
    lines = [f"{c['ah']} {c['av']} {c['front_d']!r} {c['back_d']!r} {c['thick']!r} "
             f"{c['n1']!r} {c['n2']!r} {1 if c['refract'] else 0} {niter}"]
    lines.append(" ".join(repr(float(v)) for v in d))
    lines.append(repr(float(eta)))
    lines.append(f"{len(c['front'])} {len(c['back'])}")
    for t in c["front"]:
        lines.append(" ".join(repr(float(v)) for v in t))
    for t in c["back"]:
        lines.append(" ".join(repr(float(v)) for v in t))
    r = subprocess.run([ORACLE], input="\n".join(lines) + "\n", capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"oracle failed: {r.stderr[:400]}")
    out = {"iters": [], "sv": [], "app": []}
    for ln in r.stdout.splitlines():
        t = ln.split()
        if t[0] in ("FRONT", "FRONTINV", "BACK", "BACKINV"):
            out[t[0]] = np.array([float(v) for v in t[1:]])
        elif t[0] == "SV":
            out["sv"].append(np.array([float(v) for v in t[1:]]))
        elif t[0] == "ITER":
            out["iters"].append({"it": int(t[1]), "corr": t[2].endswith("1"),
                                 "cam": tuple(float(v) for v in t[4:7]),
                                 "pld": float(t[8])})
        elif t[0].startswith("BACK") and t[0][4:].isdigit():
            out.setdefault("backiter", {})[int(t[0][4:])] = np.array([float(v) for v in t[1:]])
        elif t[0] == "CAM":
            out["cam"] = tuple(float(v) for v in t[1:4]); out["camPLD"] = float(t[4])
        elif t[0] == "APP":
            out["app"].append((float(t[2]), float(t[3]), int(t[4]), int(t[5]), float(t[6])))
    return out


def apply_stored(m, x, y):
    w = m[2][0] * x + m[2][1] * y + m[2][2]
    return ((m[0][0] * x + m[0][1] * y + m[0][2]) / w,
            (m[1][0] * x + m[1][1] * y + m[1][2]) / w)


def apply_flat(m, x, y, colmajor=True):
    if colmajor:
        w = m[2] * x + m[5] * y + m[8]
        return ((m[0] * x + m[3] * y + m[6]) / w, (m[1] * x + m[4] * y + m[7]) / w)
    w = m[6] * x + m[7] * y + m[8]
    return ((m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w)


def map_diff(stored, flat, pts, colmajor):
    a = np.array([apply_stored(stored, x, y) for x, y in pts])
    b = np.array([apply_flat(flat, x, y, colmajor) for x, y in pts])
    e = np.hypot(*(a - b).T)
    return float(e.max()), float(np.sqrt((e ** 2).mean()))


def main():
    say = print
    say("=" * 100)
    say("STAGE 2: current-production recalibration vs stored historical calibration")
    say("=" * 100)
    say("  Oracle calls Accelerate dgesvd/dgetrf/dgetri and GSL hybrids, i.e. the same routines")
    say("  production uses. Homographies compared by induced mapping, never by coefficients.")
    for label, vsd, tf, unit in DOCS:
        cals = load_cal(vsd)
        say(f"\n  {label}   world units in {'metres' if unit == 1000.0 else 'millimetres'}, "
            f"pane thickness {list(cals.values())[0]['thick']}")
        for clip in sorted(cals):
            c = cals[clip]
            o = run_oracle(c)
            # which flat-array convention reproduces the stored mapping
            und = [pa.undistort13(x, y, c["dist"]) for x, y, _, _ in c["front"]]
            best = None
            for cm in (True, False):
                mx, rms = map_diff(c["s2f"], o["FRONT"], und, cm)
                if best is None or mx < best[0]:
                    best = (mx, rms, cm)
            mxf, rmsf, cm = best
            undb = [pa.undistort13(x, y, c["dist"]) for x, y, _, _ in c["back"]]
            mxb, rmsb = map_diff(c["s2b"], o["BACK"], undb, cm)
            # grid over the calibration plane and extrapolation points
            sx = np.array([p[0] for p in c["front"]]); sy = np.array([p[1] for p in c["front"]])
            gx, gy = np.meshgrid(np.linspace(sx.min(), sx.max(), 12),
                                 np.linspace(sy.min(), sy.max(), 12))
            grid = [pa.undistort13(x, y, c["dist"]) for x, y in zip(gx.ravel(), gy.ravel())]
            mgf, rgf = map_diff(c["s2f"], o["FRONT"], grid, cm)
            ex = [pa.undistort13(x, y, c["dist"]) for x, y in
                  ((10, 10), (1910, 10), (10, 1070), (1910, 1070), (960, 540))]
            mef, ref_ = map_diff(c["s2f"], o["FRONT"], ex, cm)
            dcam = math.dist(o["cam"], c["cam"]) * unit
            say(f"    {clip:14} convention {'col-major' if cm else 'row-major'}")
            say(f"      front homography induced-mapping diff: nodes max {mxf*unit:.3e} mm "
                f"rms {rmsf*unit:.3e}; plane grid max {mgf*unit:.3e}; extrapolation max "
                f"{mef*unit:.3e} mm")
            say(f"      back  homography induced-mapping diff: nodes max {mxb*unit:.3e} mm "
                f"rms {rmsb*unit:.3e}")
            say(f"      camera position diff {dcam:.4e} mm; cameraMeanPLD "
                f"oracle {o['camPLD']*unit:.6f} vs stored {c['camPLD']*unit:.6f} mm")
            svr = o["sv"][0]
            say(f"      DLT singular values front: largest {svr[0]:.4g}, smallest "
                f"{svr[-1]:.4g}, ratio {svr[0]/svr[-1]:.4g}")
            for r in o["iters"]:
                say(f"      back iter {r['it']} corrected={int(r['corr'])} "
                    f"cam ({r['cam'][0]:.6f}, {r['cam'][1]:.6f}, {r['cam'][2]:.6f}) "
                    f"PLD {r['pld']*unit:.6f} mm")
            if o["app"]:
                it = np.array([a[2] for a in o["app"]])
                st = np.array([a[3] for a in o["app"]])
                rs = np.array([a[4] for a in o["app"]])
                shift = np.array([math.hypot(a[0] - t[2], a[1] - t[3])
                                  for a, t in zip(o["app"], c["back"])])
                say(f"      refraction solver: {len(it)} nodes, iterations {it.min()}-{it.max()}, "
                    f"all converged {bool((st == 0).all())}, max residual {rs.max():.2e}")
                say(f"      apparent-position shift of back nodes: median "
                    f"{np.median(shift)*unit:.4f} mm, max {shift.max()*unit:.4f} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
