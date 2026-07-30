#!/usr/bin/env python3
"""THE central, authoritative accessor for VidSync calibration-frame nodes.

  ZVSSCREENPOINT.ZCALIBRATION1  contains the FRONT surface nodes
  ZVSSCREENPOINT.ZCALIBRATION   contains the BACK  surface nodes

That is the opposite of what the column names suggest, and getting it backwards silently produces a
calibration that still fits its own (wrong) nodes and therefore looks healthy. It cost this project
one full round of invalid known-length rankings. `distcal.build()` and `modeltest.py` both had it
backwards; every path should go through the helpers here instead of querying those columns directly.

Established empirically on all six cameras of the three known-length documents by asking which
stored homography reproduces which node set. On the pool test, ZCALIBRATION nodes pass through the
stored screen-to-quadrat-BACK matrix at 0.0009 mm rms versus 0.128 mm through screen-to-front, while
ZCALIBRATION1 nodes pass through screen-to-FRONT at 0.0006 mm versus 0.253 mm through screen-to-back.
`assert_node_orientation()` re-checks that relationship and raises if it is ever reversed.

Run directly to execute the invariant test on all three documents.
"""

import importlib.util
import math
import os
import sqlite3
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FRONT_COLUMN = "ZCALIBRATION1"
BACK_COLUMN = "ZCALIBRATION"


def _nodes(db, column, cal_pk):
    q = (f"SELECT ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD FROM ZVSSCREENPOINT "
         f"WHERE {column} = ? ORDER BY ZINDEX")
    return [tuple(r) for r in db.execute(q, (cal_pk,))]


def front_calibration_nodes(db, cal_pk):
    """Front-surface frame nodes as (screenX, screenY, worldH, worldV)."""
    return _nodes(db, FRONT_COLUMN, cal_pk)


def back_calibration_nodes(db, cal_pk):
    """Back-surface frame nodes as (screenX, screenY, worldH, worldV)."""
    return _nodes(db, BACK_COLUMN, cal_pk)


def undistort13(x, y, d):
    """VSCalibration.mm:219, with an optional 14th element eta. eta = 0 reduces exactly."""
    eta = d[13] if len(d) > 13 else 0.0
    ax = math.exp(eta); ay = 1.0 / ax
    xd = (x - d[0]) * ax
    yd = (y - d[1]) * ay
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(d[2:9], start=1))
    T = 1.0 + d[11] * s + d[12] * s * s
    ux = xd * R + (d[9] * (s + 2 * xd * xd) + 2 * d[10] * xd * yd) * T
    uy = yd * R + (2 * d[9] * xd * yd + d[10] * (s + 2 * yd * yd)) * T
    return (d[0] + ux / ax, d[1] + uy / ay)


def apply3(m, x, y):
    w = m[2][0] * x + m[2][1] * y + m[2][2]
    return ((m[0][0] * x + m[0][1] * y + m[0][2]) / w,
            (m[1][0] * x + m[1][1] * y + m[1][2]) / w)


def flat_colmajor_to_nested(m):
    """The oracle emits production's internal column-major 9-vector; apply3 wants nested rows."""
    return [[m[0], m[3], m[6]], [m[1], m[4], m[7]], [m[2], m[5], m[8]]]


def _rms_max(nodes, mat, dist):
    e = []
    for sx, sy, wh, wv in nodes:
        ux, uy = undistort13(sx, sy, dist)
        px, py = apply3(mat, ux, uy)
        e.append(math.hypot(px - wh, py - wv))
    return math.sqrt(sum(v * v for v in e) / len(e)), max(e)


def assert_node_orientation(db, cal_pk, s2f, s2b, dist, label="", ratio=3.0):
    """Front nodes must map substantially better through the front matrix than the back matrix, and
    conversely. Raises AssertionError if the relationship is reversed or ambiguous."""
    fn = front_calibration_nodes(db, cal_pk)
    bn = back_calibration_nodes(db, cal_pk)
    f_via_f, _ = _rms_max(fn, s2f, dist)
    f_via_b, _ = _rms_max(fn, s2b, dist)
    b_via_b, _ = _rms_max(bn, s2b, dist)
    b_via_f, _ = _rms_max(bn, s2f, dist)
    ok = (f_via_b > ratio * f_via_f) and (b_via_f > ratio * b_via_b)
    if not ok:
        raise AssertionError(
            f"node orientation invariant FAILED for {label}: front nodes rms "
            f"{f_via_f:.6g} via front vs {f_via_b:.6g} via back; back nodes rms "
            f"{b_via_b:.6g} via back vs {b_via_f:.6g} via front. If these are reversed, the "
            f"{FRONT_COLUMN}/{BACK_COLUMN} mapping in nodes.py is wrong for this document.")
    return {"front_via_front": f_via_f, "front_via_back": f_via_b,
            "back_via_back": b_via_b, "back_via_front": b_via_f}


def main():
    jw_spec = importlib.util.spec_from_file_location("jacweight",
                                                    os.path.join(HERE, "jacweight.py"))
    jw = importlib.util.module_from_spec(jw_spec); jw_spec.loader.exec_module(jw)
    POOL = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
            "2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd")
    DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
    docs = [("pool test", POOL),
            ("13 mm", os.path.join(DM, "2015-06-22-1 Clearwater.vsd")),
            ("8 mm fisheye", os.path.join(DM, "2015-09-04-1 Clearwater.vsd"))]
    fails = 0
    print("INVARIANT: front nodes fit the front matrix, back nodes fit the back matrix")
    for label, vsd in docs:
        db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
        for row in db.execute(
                "SELECT c.Z_PK, v.ZCLIPNAME, c.ZMATRIXSCREENTOQUADRATFRONT, "
                "c.ZMATRIXSCREENTOQUADRATBACK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
                "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
                "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
                "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4 FROM ZVSCALIBRATION c "
                "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
            pk, clip = row[0], row[1]
            s2f = jw.unarchive_matrix(row[2]); s2b = jw.unarchive_matrix(row[3])
            dist = list(row[4:17])
            try:
                d = assert_node_orientation(db, pk, s2f, s2b, dist, f"{label} / {clip}")
                print(f"  [ok ] {label:13} {clip:14} front {d['front_via_front']:.6g} vs "
                      f"{d['front_via_back']:.6g};  back {d['back_via_back']:.6g} vs "
                      f"{d['back_via_front']:.6g}")
            except AssertionError as e:
                fails += 1
                print(f"  [FAIL] {e}")
        db.close()
    print(f"\n{'all invariants hold' if not fails else str(fails) + ' FAILURES'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
