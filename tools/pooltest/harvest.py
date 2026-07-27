#!/usr/bin/env python3
"""Harvest every plumbline calibration in the Drift Model project folder.

All these deployments used the same physical calibration frame and the same chessboard, so the
angular size of a chessboard cell in the image is a proxy for the board's range: cell size in
pixels is proportional to 1/Z. That makes the folder a natural experiment on whether the fitted
distortion depends on how far away the board was.

Writes one row per (document, camera) to stdout as TSV.
"""

import glob
import math
import os
import sqlite3
import statistics
import sys
from collections import defaultdict

FOLDER = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"


def undistort(x, y, c):
    xd, yd = x - c["x0"], y - c["y0"]
    s = xd * xd + yd * yd
    R = 1.0
    for i, k in enumerate(c["k"], start=1):
        R += k * s ** i
    T = 1 + c["p3"] * s + c["p4"] * s * s
    dx = (c["p1"] * (s + 2 * xd * xd) + 2 * c["p2"] * xd * yd) * T
    dy = (2 * c["p1"] * xd * yd + c["p2"] * (s + 2 * yd * yd)) * T
    return c["x0"] + xd * R + dx, c["y0"] + yd * R + dy


def radial_disp(r, c):
    """Pure radial displacement of the fitted model at image radius r, in pixels."""
    s = r * r
    return r * sum(k * s ** i for i, k in enumerate(c["k"], start=1))


def line_residuals(pts):
    """Orthogonal-regression residuals of a set of points about their best-fit line."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    th = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(th), math.sin(th)
    return [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]


def straightness(lines, c):
    """Rms per-point straightness residual of these plumblines under calibration c."""
    res = []
    for pts in lines:
        if len(pts) < 3:
            continue
        res += line_residuals([undistort(x, y, c) for x, y in pts])
    return math.sqrt(sum(r * r for r in res) / len(res)) if res else None


def read(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        clipname = {pk: n for pk, n in db.execute(
            "SELECT Z_PK, ZCLIPNAME FROM ZVSVIDEOCLIP")}
        cals = {}
        for row in db.execute(
                "SELECT Z_PK, ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, "
                "ZDISTORTIONK1, ZDISTORTIONK2, ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, "
                "ZDISTORTIONK6, ZDISTORTIONK7, ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, "
                "ZDISTORTIONP4, ZDISTORTIONREMAININGPERPOINT FROM ZVSCALIBRATION"):
            if row[2] is None or row[4] is None:
                continue
            cals[row[0]] = {"clip": clipname.get(row[1], "?"),
                            "x0": row[2], "y0": row[3], "k": [v or 0.0 for v in row[4:11]],
                            "p1": row[11] or 0.0, "p2": row[12] or 0.0,
                            "p3": row[13] or 0.0, "p4": row[14] or 0.0,
                            "stored": row[15]}
        lines = defaultdict(lambda: defaultdict(list))
        for cal, ln, x, y in db.execute(
                "SELECT l.ZCALIBRATION, l.Z_PK, p.ZSCREENX, p.ZSCREENY "
                "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK "
                "ORDER BY l.ZCALIBRATION, l.Z_PK, p.ZINDEX1"):
            if x is not None and y is not None:
                lines[cal][ln].append((x, y))
        return cals, lines
    finally:
        db.close()


def summarise(doc, pk, c, lines):
    pls = [p for p in lines.values() if len(p) >= 3]
    pts = [q for p in pls for q in p]
    if len(pts) < 40 or len(pls) < 6:
        return None

    # Cell size proxied by the spacing between neighbouring points along a line. Measured in
    # *undistorted* coordinates and only near the image centre: distortion itself compresses
    # spacing towards the edges, and using a distorted spacing to predict distortion would be
    # circular.
    near, allsp = [], []
    for p in pls:
        u = [undistort(x, y, c) for x, y in p]
        for a, b in zip(u, u[1:]):
            d = math.dist(a, b)
            if not (1.0 < d < 400.0):
                continue
            allsp.append(d)
            mr = 0.5 * (math.hypot(a[0] - c["x0"], a[1] - c["y0"]) +
                        math.hypot(b[0] - c["x0"], b[1] - c["y0"]))
            if mr < 500:
                near.append(d)
    if len(allsp) < 30:
        return None
    sp = sorted(allsp)
    cell_near = statistics.median(near) if len(near) >= 10 else float("nan")
    cell_p90 = sp[int(0.90 * (len(sp) - 1))]
    cv = statistics.pstdev(allsp) / statistics.mean(allsp)

    radii = sorted(math.hypot(x - c["x0"], y - c["y0"]) for x, y in pts)
    rmax = radii[int(0.95 * (len(radii) - 1))]
    resid = straightness(pls, c)

    return {"doc": doc, "cal": pk, "clip": c["clip"], "npts": len(pts), "nlines": len(pls),
            "cell_near": cell_near, "cell_p90": cell_p90, "cell_med": statistics.median(allsp),
            "cv": cv, "rmax": rmax, "resid": resid, "stored": c["stored"],
            "d200": radial_disp(200, c), "d400": radial_disp(400, c),
            "d600": radial_disp(600, c), "d800": radial_disp(800, c)}


def main():
    cols = ["doc", "cal", "clip", "npts", "nlines", "cell_near", "cell_p90", "cell_med", "cv",
            "rmax", "resid", "stored", "d200", "d400", "d600", "d800"]
    print("\t".join(cols))
    for path in sorted(glob.glob(os.path.join(FOLDER, "*.vsd"))):
        doc = os.path.basename(path)[:-4]
        try:
            cals, lines = read(path)
        except Exception as e:                       # noqa: BLE001 - report and continue
            print(f"# {doc}: {e}", file=sys.stderr)
            continue
        for pk, c in sorted(cals.items()):
            row = summarise(doc, pk, c, lines.get(pk, {}))
            if row:
                print("\t".join(
                    f"{row[k]:.4g}" if isinstance(row[k], float) else str(row[k])
                    for k in cols))


if __name__ == "__main__":
    main()
