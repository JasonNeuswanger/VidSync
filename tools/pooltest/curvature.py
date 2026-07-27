#!/usr/bin/env python3
"""Model-free test for subject-distance dependence of distortion.

For a central camera carrying any fixed distortion map D, the curvature of the image of a
straight world line is a function of image position and image direction ALONE, independent of the
line's distance. The argument is short: undistortion sends the image of a straight line to a
straight line; a straight line is determined by one point and one direction; so two world lines
whose images agree in position and direction at some pixel have identical undistorted lines and
therefore identical distorted curves. Depth cannot enter.

That makes distance dependence directly observable in the raw clicks, with no fitting, no model,
and no gauge freedom. Measure the signed curvature of every detected plumbline at every interior
point, bin by image radius and by line orientation, and compare the near board against the far
board. Any systematic disagreement in matched bins is refraction, and its size is the error
budget.

The null distribution comes from the data too: splitting one set in half and comparing the halves
gives the disagreement produced by corner noise and board-pose differences alone, at the same
range. Signal is only what exceeds that.

`2015-09-04-1 Clearwater`, left camera, carries two plumbline sets four seconds apart with the
board 1.35x closer in the earlier one.
"""

import math
import sqlite3
import statistics
from collections import defaultdict

DOC = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")
CLIP = "Left Camera"
HALF = 2                      # points each side of the centre point used for the local fit


def load():
    db = sqlite3.connect(f"file:{DOC}?mode=ro", uri=True)
    pk, cx, cy = db.execute(
        "SELECT c.Z_PK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY FROM ZVSCALIBRATION c "
        "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP WHERE v.ZCLIPNAME = ?", (CLIP,)).fetchone()
    sets = defaultdict(lambda: defaultdict(list))
    for tc, ln, x, y in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY FROM ZVSDISTORTIONLINE l "
            "JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
            "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
        if x is not None:
            sets[tc][ln].append((x, y))
    db.close()
    return (cx, cy), {tc: {ln: p for ln, p in d.items() if len(p) >= 2 * HALF + 1}
                      for tc, d in sets.items()}


def curvatures(lines, centre):
    """Signed curvature at each interior point, positive when the curve bends away from the
    image centre. Estimated by least squares of a parabola in the local chord frame, which is
    orientation-free once the sign is taken against the radial direction."""
    cx, cy = centre
    out = []
    for pts in lines.values():
        for i in range(HALF, len(pts) - HALF):
            win = pts[i - HALF:i + HALF + 1]
            ax, ay = win[0]
            bx, by = win[-1]
            L = math.hypot(bx - ax, by - ay)
            if L <= 0:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            nx, ny = -uy, ux
            ts, ns = [], []
            for px, py in win:
                ts.append((px - ax) * ux + (py - ay) * uy)
                ns.append((px - ax) * nx + (py - ay) * ny)
            # quadratic n = a t^2 + b t + c by normal equations
            S = [sum(t ** k for t in ts) for k in range(5)]
            R = [sum(n * t ** k for n, t in zip(ns, ts)) for k in range(3)]
            m = [[S[4], S[3], S[2], R[2]], [S[3], S[2], S[1], R[1]], [S[2], S[1], S[0], R[0]]]
            for col in range(3):
                piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
                if abs(m[piv][col]) < 1e-18:
                    break
                m[col], m[piv] = m[piv], m[col]
                d = m[col][col]
                m[col] = [v / d for v in m[col]]
                for r in range(3):
                    if r != col and m[r][col]:
                        f = m[r][col]
                        m[r] = [vr - f * vc for vr, vc in zip(m[r], m[col])]
            else:
                a, b = m[0][3], m[1][3]
                kappa = 2 * a / (1 + b * b) ** 1.5
                px, py = pts[i]
                ex, ey = px - cx, py - cy
                rad = math.hypot(ex, ey)
                if rad < 1e-6:
                    continue
                # sign against the outward radial direction, and the line's angle to it
                sgn = 1.0 if (nx * ex + ny * ey) >= 0 else -1.0
                cosang = abs(ux * ex + uy * ey) / rad
                out.append({"r": rad, "k": kappa * sgn, "cos": cosang, "span": L,
                            "x": px, "y": py})
    return out


def summarise(vals):
    n = len(vals)
    if n < 2:
        return float("nan"), float("nan"), n
    mean = sum(vals) / n
    sd = statistics.pstdev(vals) * math.sqrt(n / (n - 1))
    return mean, sd / math.sqrt(n), n


def compare(label, a, b, centre, scale):
    """Binned comparison of two curvature samples. Returns the pooled z of the differences."""
    print(f"\n  {label}")
    print(f"    {'radius':>10} {'orient':>10} {'nA':>4} {'nB':>4} "
          f"{'kappa A':>11} {'kappa B':>11} {'difference':>16} {'z':>6}")
    diffs = []
    for lo, hi in ((0, 350), (350, 550), (550, 750), (750, 1100)):
        for oname, olo, ohi in (("radial", 0.7, 1.01), ("tangential", 0.0, 0.4)):
            sa = [w["k"] for w in a if lo <= w["r"] < hi and olo <= w["cos"] < ohi]
            sb = [w["k"] for w in b if lo <= w["r"] < hi and olo <= w["cos"] < ohi]
            if len(sa) < 8 or len(sb) < 8:
                continue
            ma, ea, na = summarise(sa)
            mb, eb, nb = summarise(sb)
            se = math.hypot(ea, eb)
            z = (ma - mb) / se if se > 0 else float("nan")
            diffs.append((ma - mb, se))
            print(f"    {f'{lo}-{hi}':>10} {oname:>10} {na:4d} {nb:4d} "
                  f"{ma*scale:11.2f} {mb*scale:11.2f} {(ma-mb)*scale:+11.2f}"
                  f" +/-{se*scale:5.2f} {z:6.2f}")
    if diffs:
        w = sum(d / (s * s) for d, s in diffs) / sum(1 / (s * s) for d, s in diffs)
        we = math.sqrt(1 / sum(1 / (s * s) for d, s in diffs))
        print(f"    {'POOLED':>21} {'':9} {'':11} {'':11} {w*scale:+11.2f}"
              f" +/-{we*scale:5.2f} {w/we:6.2f}")
    return diffs


def main():
    centre, sets = load()
    tcs = sorted(sets)
    cells = {}
    for tc in tcs:
        sp = [math.dist(p[i], p[i + 1]) for p in sets[tc].values() for i in range(len(p) - 1)
              if 1 < math.dist(p[i], p[i + 1]) < 400]
        cells[tc] = statistics.median(sp)
    near = max(tcs, key=lambda t: cells[t])
    far = min(tcs, key=lambda t: cells[t])

    print("=" * 84)
    print(f"{CLIP}, 2015-09-04-1 Clearwater (8 mm fisheye behind a dome)")
    print("=" * 84)
    for tc in tcs:
        which = "NEAR" if tc == near else "FAR "
        print(f"  {which} {tc}  {len(sets[tc]):3d} lines, "
              f"{sum(len(p) for p in sets[tc].values()):4d} points, cell {cells[tc]:.1f} px")
    print(f"  board range ratio {cells[near]/cells[far]:.3f}; 1/Z differs by "
          f"{1 - cells[far]/cells[near]:+.1%}")
    print(f"  distortion centre used for the radial frame: "
          f"({centre[0]:.1f}, {centre[1]:.1f})")

    kn = curvatures(sets[near], centre)
    kf = curvatures(sets[far], centre)
    print(f"\n  curvature samples: {len(kn)} near, {len(kf)} far "
          f"(local parabola over {2*HALF+1} points)")
    print(f"  median chord span: {statistics.median([w['span'] for w in kn]):.0f} px near, "
          f"{statistics.median([w['span'] for w in kf]):.0f} px far")
    print("\n  curvature is reported x 1e6 per pixel throughout.")

    scale = 1e6
    print("\n" + "=" * 84)
    print("NULL: split-half within the far set -- same range, so this is noise plus pose")
    print("=" * 84)
    fl = sorted(sets[far])
    ha = {k: sets[far][k] for k in fl[0::2]}
    hb = {k: sets[far][k] for k in fl[1::2]}
    compare("far half A vs far half B", curvatures(ha, centre), curvatures(hb, centre),
            centre, scale)

    print("\n" + "=" * 84)
    print("SIGNAL: near board vs far board")
    print("=" * 84)
    compare("near vs far", kn, kf, centre, scale)

    print("\n  A real 1/Z term should show a consistent sign across radius bands and be")
    print("  larger than the split-half null. Note the near-vs-far comparison also absorbs")
    print("  any change in board pose between the two frames, so it is an upper bound.")


if __name__ == "__main__":
    main()
