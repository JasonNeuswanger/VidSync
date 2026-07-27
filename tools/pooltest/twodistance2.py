#!/usr/bin/env python3
"""Two-distance diagnostic, using VidSync's own solver output.

`2015-09-04-1 Clearwater`'s left camera carries two plumbline sets four seconds apart, the board
1.35x closer in the earlier one. Three exports hold the distortion parameters VidSync's own
Nelder-Mead solve produced from the near set alone, the far set alone, and both combined. That
supplies the converged fits an earlier pure-Python attempt could not reach.

The test: if the underwater system is non-central, its effective distortion carries a term in
1/Z, and a fit made at one range will fail to straighten lines at the other. Score on
straightness, which is exactly the gauge-invariant quantity -- two fits differing by a homography
are the same map as far as the downstream plane homographies are concerned, and only
non-straightness is charged.

Radial coverage is controlled throughout: the nearer board fills more of the frame, so an
uncontrolled comparison measures extrapolation rather than range. Every figure below is
restricted to the radius both sets reach, with both fits scored on the identical point set.
"""

import math
import re
import sqlite3
import statistics
from collections import defaultdict

VSD = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")
EXPORTS = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/Exports"
FITS = [("near-only", "2015-09-04-1 Clearwater - NearDistortionSetOnly.xml"),
        ("far-only", "2015-09-04-1 Clearwater - FarDistortionSetOnly.xml"),
        ("both", "2015-09-04-1 Clearwater - BothDistortionSets.xml")]
CLIP = "Left Camera"

KEYS = ["distortionCenterX", "distortionCenterY", "distortionK1", "distortionK2", "distortionK3",
        "distortionK4", "distortionK5", "distortionK6", "distortionK7", "distortionP1",
        "distortionP2", "distortionP3", "distortionP4"]


def undistort(x, y, c):
    xd, yd = x - c[0], y - c[1]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c[2:9], start=1))
    T = 1 + c[11] * s + c[12] * s * s
    return (c[0] + xd * R + (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T,
            c[1] + yd * R + (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T)


def jac(x, y, c):
    xd, yd = x - c[0], y - c[1]
    k = c[2:9]
    p1, p2, p3, p4 = c[9], c[10], c[11], c[12]
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


def line_res(pts):
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    th = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(th), math.sin(th)
    return [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]


def straightness(lines, c, rlimit, centre):
    res = []
    for pts in lines:
        q = [p for p in pts if math.hypot(p[0] - centre[0], p[1] - centre[1]) <= rlimit]
        if len(q) < 3:
            continue
        res += line_res([undistort(x, y, c) for x, y in q])
    return math.sqrt(sum(r * r for r in res) / len(res)), len(res)


def noise_floor(lines):
    """Corner noise from the centred four-point stencil on evenly spaced stretches: the
    combination (-p0+3p1-3p2+p3)/sqrt(20) kills any quadratic through four equally spaced
    collinear points, so it sees localisation noise only."""
    vals = []
    for pts in lines:
        for i in range(len(pts) - 3):
            q = pts[i:i + 4]
            d = [math.dist(q[j], q[j + 1]) for j in range(3)]
            if min(d) <= 0 or (max(d) - min(d)) / min(d) > 0.05:
                continue
            ux, uy = q[3][0] - q[0][0], q[3][1] - q[0][1]
            L = math.hypot(ux, uy)
            if L == 0:
                continue
            nx, ny = -uy / L, ux / L
            vals.append(sum(w * (p[0] * nx + p[1] * ny)
                            for w, p in zip((-1, 3, -3, 1), q)) / math.sqrt(20.0))
    return (math.sqrt(sum(v * v for v in vals) / len(vals)), len(vals)) if vals else (None, 0)


def read_fit(path, clip):
    s = open(path, encoding="utf-8").read()
    i = s.find(f'<videoClip name="{clip}"')
    if i < 0:
        raise SystemExit(f"clip {clip} not found in {path}")
    seg = s[i:i + 6000]
    out = []
    for k in KEYS:
        m = re.search(k + r'="(-?[\d.eE+]+)"', seg)
        if not m:
            raise SystemExit(f"{k} missing in {path}")
        out.append(float(m.group(1)))
    return out


def solve8(a, b):
    n = 8
    m = [a[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        d = m[col][col]
        m[col] = [v / d for v in m[col]]
        for r in range(n):
            if r != col and m[r][col]:
                f = m[r][col]
                m[r] = [vr - f * vc for vr, vc in zip(m[r], m[col])]
    return [m[i][n] for i in range(n)]


def best_homography(src, dst):
    A, B = [], []
    for (u, v), (x, y) in zip(src, dst):
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); B.append(x)
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y]); B.append(y)
    ata = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(8)] for i in range(8)]
    atb = [sum(A[r][i] * B[r] for r in range(len(A))) for i in range(8)]
    return solve8(ata, atb)


def main():
    db = sqlite3.connect(f"file:{VSD}?mode=ro", uri=True)
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

    lines, cells, rmax, floor = {}, {}, {}, {}
    for tc, d in sets.items():
        L = [p for p in d.values() if len(p) >= 3]
        lines[tc] = L
        sp = [math.dist(a, b) for p in L for a, b in zip(p, p[1:]) if 1 < math.dist(a, b) < 400]
        cells[tc] = statistics.median(sp)
        rr = sorted(math.hypot(x - cx, y - cy) for p in L for x, y in p)
        rmax[tc] = rr[int(0.98 * (len(rr) - 1))]
        floor[tc] = noise_floor(L)

    near = max(cells, key=lambda t: cells[t])
    far = min(cells, key=lambda t: cells[t])
    label = {near: "near set", far: "far set"}
    fits = {n: read_fit(f"{EXPORTS}/{f}", CLIP) for n, f in FITS}
    centre = (cx, cy)
    rlim = min(rmax.values())

    print("=" * 84)
    print(f"{CLIP}, 2015-09-04-1 Clearwater -- 8 mm fisheye, VidSync's own fits")
    print("=" * 84)
    for tc in (near, far):
        print(f"  {label[tc]:9s} {tc}  {len(lines[tc]):3d} lines "
              f"{sum(len(p) for p in lines[tc]):4d} pts  cell {cells[tc]:6.1f} px  "
              f"r98 {rmax[tc]:4.0f}  corner noise {floor[tc][0]:.3f} px (n={floor[tc][1]})")
    print(f"  board range ratio {cells[near]/cells[far]:.3f}; 1/Z differs by "
          f"{1 - cells[far]/cells[near]:+.1%}")
    print(f"  comparisons restricted to r <= {rlim:.0f} px, the radius both sets reach")

    print(f"\n  fitted distortion centres, which the solve places freely:")
    for n, c in fits.items():
        print(f"    {n:10s} ({c[0]:7.1f}, {c[1]:7.1f})")

    print("\n" + "=" * 84)
    print("CROSS-EVALUATION  (rms straightness residual, px -- gauge-invariant)")
    print("=" * 84)
    print(f"  {'evaluated on':>12} {'n':>5} " + "".join(f"{n:>12}" for n, _ in FITS)
          + f"{'noise floor':>13}")
    res = {}
    for tc in (near, far):
        row = []
        for n, _ in FITS:
            v, cnt = straightness(lines[tc], fits[n], rlim, centre)
            res[(tc, n)] = v
            row.append(v)
        print(f"  {label[tc]:>12} {cnt:5d} " + "".join(f"{v:12.4f}" for v in row)
              + f"{floor[tc][0]:13.3f}")

    print("\n  in-sample values are on the diagonal: near-only on the near set, far-only on the")
    print("  far set. The transfer penalty is the excess of the off-diagonal over the diagonal.")
    for tc, own, other in ((near, "near-only", "far-only"), (far, "far-only", "near-only")):
        a, b = res[(tc, own)], res[(tc, other)]
        excess = math.sqrt(max(0.0, b * b - a * a))
        print(f"    {label[tc]}: own {a:.4f} -> other {b:.4f}, "
              f"excess {excess:.4f} px  (corner noise {floor[tc][0]:.3f})")
    print("\n  and what the combined fit costs each set relative to its own:")
    for tc, own in ((near, "near-only"), (far, "far-only")):
        a, b = res[(tc, own)], res[(tc, "both")]
        print(f"    {label[tc]}: own {a:.4f} -> both {b:.4f}, "
              f"excess {math.sqrt(max(0.0, b*b - a*a)):.4f} px")

    # gate
    print("\n" + "=" * 84)
    print("acceptance gate on each fit")
    print("=" * 84)
    allpts = [p for tc in lines for pp in lines[tc] for p in pp]
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    for n, c in fits.items():
        dets = [jac(min(xs) + (max(xs) - min(xs)) * i / 40,
                    min(ys) + (max(ys) - min(ys)) * j / 40, c) for i in range(41)
                for j in range(41)]
        dets = [a * d - b * cc for a, b, cc, d in
                [jac(min(xs) + (max(xs) - min(xs)) * i / 40,
                     min(ys) + (max(ys) - min(ys)) * j / 40, c)
                 for i in range(41) for j in range(41)]]
        mags = [math.sqrt(abs(a * d - b * cc)) for a, b, cc, d in
                (jac(x, y, c) for x, y in allpts)]
        sr = max(mags) / min(mags)
        print(f"  {n:10s} min det {min(dets):+8.3f}  scale ratio {sr:5.2f}  "
              f"-> {'PASS' if min(dets) > 0 and 0.25 < sr < 4.0 else 'REJECT'}")

    # difference field, gauge removed
    print("\n" + "=" * 84)
    print("difference between the near-only and far-only maps, after removing the gauge")
    print("=" * 84)
    grid = [(x, y) for x in range(40, 1901, 40) for y in range(40, 1061, 40)
            if math.hypot(x - cx, y - cy) <= rlim]
    a = [undistort(x, y, fits["near-only"]) for x, y in grid]
    b = [undistort(x, y, fits["far-only"]) for x, y in grid]
    raw = math.sqrt(sum((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                        for p, q in zip(a, b)) / len(a))
    H = best_homography(b, a)
    resid = []
    for (x, y), pa, pb in zip(grid, a, b):
        w = H[6] * pb[0] + H[7] * pb[1] + 1.0
        resid.append((x, y, pa[0] - (H[0] * pb[0] + H[1] * pb[1] + H[2]) / w,
                      pa[1] - (H[3] * pb[0] + H[4] * pb[1] + H[5]) / w))
    rms = math.sqrt(sum(dx * dx + dy * dy for _, _, dx, dy in resid) / len(resid))
    print(f"  raw field difference {raw:8.2f} px  <- almost entirely gauge, means nothing")
    print(f"  after removing the best-fit homography {rms:.3f} px  <- the part that bends lines")
    print(f"\n  {'radius':>12} {'n':>5} {'rms':>8} {'radial':>8} {'tangential':>11}")
    for lo, hi in ((0, 300), (300, 500), (500, 700), (700, 1100)):
        s = [r for r in resid if lo <= math.hypot(r[0] - cx, r[1] - cy) < hi]
        if len(s) < 8:
            continue
        rad, tan = [], []
        for x, y, dx, dy in s:
            ex, ey = x - cx, y - cy
            L = math.hypot(ex, ey) or 1.0
            rad.append((dx * ex + dy * ey) / L)
            tan.append((-dx * ey + dy * ex) / L)
        print(f"  {f'{lo}-{hi}':>12} {len(s):5d} "
              f"{math.sqrt(sum(dx*dx+dy*dy for _,_,dx,dy in s)/len(s)):8.3f} "
              f"{math.sqrt(sum(v*v for v in rad)/len(rad)):8.3f} "
              f"{math.sqrt(sum(v*v for v in tan)/len(tan)):11.3f}")


if __name__ == "__main__":
    main()
