#!/usr/bin/env python3
"""How much gauge does each camera's undistortion carry, and does it leak into the refinement?

A plumbline fit determines the distortion only up to a homography, because straightness is a
homography-invariant property. The two-plane homographies absorb that gauge exactly, so it
cannot bias the geometry. But VSPoint.m's iterative refinement minimizes squared reprojection
error measured in *undistorted* coordinates, summed over cameras:

    cost += (reprojected.x - undistorted.x)^2 + (reprojected.y - undistorted.y)^2

Click noise is isotropic in *raw* pixels. Undistortion magnifies it by the local Jacobian, which
differs between the two cameras and varies across the frame. So each camera enters the objective
with a weight proportional to the square of a quantity the calibration never determined.

This measures the size of that weighting error where the measurements actually are.
"""

import math
import sqlite3
from collections import defaultdict

DOCS = {
    "2012 pool test": "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/"
                      "VidSync Projects/2012-01-31_PoolTest/"
                      "2012-01-31_PoolTest_2026_Reanalysis.vsd",
    "2016-08-13-2 Chena (8 mm)": "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/"
                                 "VidSync Projects/2016-08-13-2 Chena.vsd",
}


def jac(xd, yd, c):
    """d(undistorted)/d(distorted), as the 2x2 the C code builds in undistortionJacobian()."""
    k = c["k"]
    p1, p2, p3, p4 = c["p1"], c["p2"], c["p3"], c["p4"]
    s = xd * xd + yd * yd
    R = 1 + sum(kk * s ** i for i, kk in enumerate(k, start=1))
    Rp = sum(i * kk * s ** (i - 1) for i, kk in enumerate(k, start=1))
    T = 1 + p3 * s + p4 * s * s
    Tp = p3 + 2 * p4 * s
    Gx = p1 * (3 * xd * xd + yd * yd) + 2 * p2 * xd * yd
    Gy = 2 * p1 * xd * yd + p2 * (xd * xd + 3 * yd * yd)
    return (R + 2 * xd * xd * Rp + (6 * p1 * xd + 2 * p2 * yd) * T + 2 * xd * Gx * Tp,
            2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * yd * Gx * Tp,
            2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * xd * Gy * Tp,
            R + 2 * yd * yd * Rp + (2 * p1 * xd + 6 * p2 * yd) * T + 2 * yd * Gy * Tp)


def load(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    clipname = dict(db.execute("SELECT Z_PK, ZCLIPNAME FROM ZVSVIDEOCLIP"))
    cals = {}
    for row in db.execute(
            "SELECT Z_PK, ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, ZDISTORTIONK1, "
            "ZDISTORTIONK2, ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, ZDISTORTIONK6, "
            "ZDISTORTIONK7, ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, ZDISTORTIONP4 "
            "FROM ZVSCALIBRATION"):
        if row[2] is None:
            continue
        cals[row[1]] = {"name": clipname.get(row[1], "?"), "x0": row[2], "y0": row[3],
                        "k": [v or 0.0 for v in row[4:11]], "p1": row[11] or 0.0,
                        "p2": row[12] or 0.0, "p3": row[13] or 0.0, "p4": row[14] or 0.0}
    # where measurement clicks actually landed, per clip
    clicks = defaultdict(list)
    for clip, x, y in db.execute(
            "SELECT ZVIDEOCLIP, ZSCREENX, ZSCREENY FROM ZVSSCREENPOINT WHERE ZPOINT IS NOT NULL"):
        if x is not None:
            clicks[clip].append((x, y))
    db.close()
    # A fixed grid over the 1920x1080 frame, so the two cameras are always compared on the same
    # set of image positions whether or not the document carries measurement clicks.
    grid = [(x, y) for x in range(40, 1920, 40) for y in range(40, 1080, 40)]
    return cals, clicks, grid


for label, path in DOCS.items():
    print(f"\n{'='*72}\n{label}\n{'='*72}")
    cals, clicks, grid = load(path)
    lams = {}
    for clip, c in sorted(cals.items()):
        pts = clicks.get(clip) or grid
        src = "measurement clicks" if clicks.get(clip) else "frame grid"
        # local linear magnification of the undistortion, at the points that matter
        mags = []
        for x, y in pts:
            a, b, cc, d = jac(x - c["x0"], y - c["y0"], c)
            mags.append(math.sqrt(abs(a * d - b * cc)))   # sqrt(area mag) = length scale
        mags.sort()
        lam = sum(mags) / len(mags)
        lams[clip] = lam
        print(f"  {c['name']:14s} {src:19s} n={len(pts):5d}   mean magnification {lam:.4f}"
              f"   range {mags[0]:.3f} - {mags[-1]:.3f}")
    if len(lams) == 2:
        (a, la), (b, lb) = sorted(lams.items())
        print(f"\n  between-camera magnification ratio  {la/lb:.4f}")
        print(f"  implied weighting of {cals[a]['name']} vs {cals[b]['name']} in the "
              f"refinement objective: {(la/lb)**2:.4f}x")
        print("  (each camera's squared residual is inflated by its own magnification squared;")
        print("   equal weighting would need this to be 1.0)")
