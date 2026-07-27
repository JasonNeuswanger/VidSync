#!/usr/bin/env python3
"""Step 1 two-distance diagnostic: is the fitted distortion specific to the board's range?

`2015-09-04-1 Clearwater` carries two plumbline sets for the left camera, four seconds apart,
with the board nearer in the earlier one. If the underwater system is non-central, its effective
distortion carries a term in 1/Z, so a fit made at one range should fail to straighten lines at
the other, by an amount that is the refraction error budget.

Three things have to be right for the answer to mean anything.

*Score on straightness, not on a difference of parameters.* Straightness is invariant under any
homography applied after undistortion, so two fits can differ by an arbitrary 8-DOF gauge and
still be the same map as far as the geometry is concerned. Cross-residuals are gauge-invariant;
raw parameter or displacement-field differences are not.

*Control radial coverage.* The nearer board fills more of the frame, so a far-fitted model tested
on near lines is extrapolating. That confound points the same way as the hypothesis and is strong
enough to fake it -- it produced a spurious t = -2.87 in an earlier version of this investigation.
Every comparison here is restricted to the radius both sets reach.

*Establish the noise floor.* Corner localisation noise is measured from the data itself with a
centred four-point stencil on evenly spaced stretches of each line, independently of any
distortion model. A cross-residual is only interesting relative to that floor.
"""

import math
import sqlite3
import statistics
import sys
from collections import defaultdict

DOC = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")
CLIP = "Left Camera"

SCALE = [1.0e3, 1.0e3, 5.0e-8, 1.0e-14, 1.0e-21, 1.0e-27, 1.0e-34, 1.0e-40, 1.0e-43,
         1.0e-7, 1.0e-7, 1.0e-7, 1.0e-10]


def undistort(x, y, c):
    xd, yd = x - c[0], y - c[1]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c[2:9], start=1))
    T = 1 + c[11] * s + c[12] * s * s
    return (c[0] + xd * R + (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T,
            c[1] + yd * R + (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T)


def jac_det(x, y, c):
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
    a = R + 2 * xd * xd * Rp + (6 * p1 * xd + 2 * p2 * yd) * T + 2 * xd * Gx * Tp
    b = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * yd * Gx * Tp
    cc = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * xd * Gy * Tp
    d = R + 2 * yd * yd * Rp + (2 * p1 * xd + 6 * p2 * yd) * T + 2 * yd * Gy * Tp
    return a * d - b * cc


def line_res(pts):
    n = len(pts)
    if n < 3:
        return []
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    th = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(th), math.sin(th)
    return [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]


def straightness(lines, c, rlimit=None, centre=None):
    res = []
    for pts in lines:
        if rlimit is not None:
            cx, cy = centre
            pts = [p for p in pts if math.hypot(p[0] - cx, p[1] - cy) <= rlimit]
        if len(pts) < 3:
            continue
        res += line_res([undistort(x, y, c) for x, y in pts])
    return (math.sqrt(sum(r * r for r in res) / len(res)), len(res)) if res else (None, 0)


def noise_floor(lines):
    """Corner noise from the centred four-point stencil, on evenly spaced stretches only.

    For four collinear, equally spaced points the combination (-p0 + 3p1 - 3p2 + p3)/sqrt(20)
    annihilates any quadratic through them, so it measures localisation noise without assuming
    a distortion model. Restricted to stretches whose spacing is uniform to 5%, since unequal
    spacing leaks real curvature into the estimate.
    """
    vals = []
    for pts in lines:
        for i in range(len(pts) - 3):
            q = pts[i:i + 4]
            d = [math.dist(q[j], q[j + 1]) for j in range(3)]
            if min(d) <= 0 or (max(d) - min(d)) / min(d) > 0.05:
                continue
            ux, uy = (q[3][0] - q[0][0]), (q[3][1] - q[0][1])
            L = math.hypot(ux, uy)
            if L == 0:
                continue
            nx, ny = -uy / L, ux / L
            comb = sum(w * (p[0] * nx + p[1] * ny) for w, p in zip((-1, 3, -3, 1), q))
            vals.append(comb / math.sqrt(20.0))
    return (math.sqrt(sum(v * v for v in vals) / len(vals)), len(vals)) if vals else (None, 0)


def nelder_mead(f, x0, step, tol=1e-9, maxit=40000):
    n = len(x0)
    pts = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step
        pts.append(p)
    vals = [f(p) for p in pts]
    for _ in range(maxit):
        o = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in o]
        vals = [vals[i] for i in o]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol):
            break
        cen = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        ref = [cen[j] + (cen[j] - pts[-1][j]) for j in range(n)]
        fr = f(ref)
        if fr < vals[0]:
            ex = [cen[j] + 2 * (cen[j] - pts[-1][j]) for j in range(n)]
            fe = f(ex)
            pts[-1], vals[-1] = (ex, fe) if fe < fr else (ref, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = ref, fr
        else:
            co = [cen[j] + 0.5 * (pts[-1][j] - cen[j]) for j in range(n)]
            fc = f(co)
            if fc < vals[-1]:
                pts[-1], vals[-1] = co, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    i = min(range(n + 1), key=lambda i: vals[i])
    return pts[i], vals[i]


def fit(lines, seed_centre):
    """Replicates VidSync's solve: Nelder-Mead on the 13 scaled parameters, minimizing the plain
    sum of squared orthogonal-regression residuals over all lines."""
    def cost(v):
        c = [v[i] * SCALE[i] for i in range(13)]
        t = 0.0
        for pts in lines:
            if len(pts) < 3:
                continue
            t += sum(r * r for r in line_res([undistort(x, y, c) for x, y in pts]))
        return t

    x0 = [seed_centre[0] / SCALE[0], seed_centre[1] / SCALE[1]] + [0.0] * 11
    best, bv = None, float("inf")
    for step in (25.0, 5.0, 1.0):
        v, val = nelder_mead(cost, x0 if best is None else best, step)
        if val < bv:
            best, bv = v, val
    return [best[i] * SCALE[i] for i in range(13)]


def gate(c, lines):
    pts = [q for p in lines for q in p]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dets = [jac_det(min(xs) + (max(xs) - min(xs)) * i / 40,
                    min(ys) + (max(ys) - min(ys)) * j / 40, c)
            for i in range(41) for j in range(41)]
    mags = [math.sqrt(abs(jac_det(x, y, c))) for x, y in pts]
    ok = (all(math.isfinite(v) for v in c) and min(dets) > 0
          and 0.25 < max(mags) / min(mags) < 4.0)
    return ok, min(dets), max(mags) / min(mags)


def main():
    db = sqlite3.connect(f"file:{DOC}?mode=ro", uri=True)
    calpk, = db.execute(
        "SELECT c.Z_PK FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP "
        "WHERE v.ZCLIPNAME = ?", (CLIP,)).fetchone()
    stored = list(db.execute(
        "SELECT ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, ZDISTORTIONK1, ZDISTORTIONK2, "
        "ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, ZDISTORTIONK6, ZDISTORTIONK7, "
        "ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, ZDISTORTIONP4 FROM ZVSCALIBRATION "
        "WHERE Z_PK = ?", (calpk,)).fetchone())
    sets = defaultdict(lambda: defaultdict(list))
    for tc, ln, x, y in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY FROM ZVSDISTORTIONLINE l "
            "JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
            "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (calpk,)):
        if x is not None:
            sets[tc][ln].append((x, y))
    db.close()

    tcs = sorted(sets)
    if len(tcs) != 2:
        print(f"expected two timecodes, found {len(tcs)}: {tcs}")
        return 1

    info = {}
    for tc in tcs:
        lines = [p for p in sets[tc].values() if len(p) >= 3]
        pts = [q for p in lines for q in p]
        sp = [math.dist(a, b) for p in lines for a, b in zip(p, p[1:])
              if 1 < math.dist(a, b) < 400]
        radii = sorted(math.hypot(x - stored[0], y - stored[1]) for x, y in pts)
        nf, nn = noise_floor(lines)
        info[tc] = {"lines": lines, "pts": pts, "cell": statistics.median(sp),
                    "rmax": radii[int(0.98 * (len(radii) - 1))], "noise": nf, "nn": nn}

    print("=" * 78)
    print(f"{CLIP} of 2015-09-04-1 Clearwater -- two plumbline sets, 8 mm fisheye")
    print("=" * 78)
    print(f"  {'timecode':>18} {'lines':>6} {'pts':>5} {'cell px':>8} {'r98':>6} "
          f"{'corner noise':>13}")
    for tc in tcs:
        d = info[tc]
        print(f"  {tc:>18} {len(d['lines']):6d} {len(d['pts']):5d} {d['cell']:8.1f} "
              f"{d['rmax']:6.0f} {d['noise']:9.3f} px (n={d['nn']})")

    near = max(tcs, key=lambda t: info[t]["cell"])
    far = min(tcs, key=lambda t: info[t]["cell"])
    ratio = info[near]["cell"] / info[far]["cell"]
    print(f"\n  nearer set is {near} (larger cell), farther is {far}")
    print(f"  cell size ratio {ratio:.3f}, so the board's range differs by that factor "
          f"and 1/Z by {1 - 1/ratio:+.1%}")
    if near != tcs[0]:
        print("  NOTE: that is the LATER timecode, opposite to what was described -- "
              "check before interpreting")
    else:
        print("  consistent with the earlier timecode being the closer board")

    rlim = min(info[near]["rmax"], info[far]["rmax"])
    ctr = (stored[0], stored[1])
    print(f"\n  all comparisons below restricted to r <= {rlim:.0f} px, the radius both "
          f"sets reach")

    print("\n" + "=" * 78)
    print("independent fits, then cross-evaluation (straightness is gauge-invariant)")
    print("=" * 78)
    fits = {}
    for tc in tcs:
        c = fit(info[tc]["lines"], ctr)
        ok, mindet, sr = gate(c, info[tc]["lines"])
        fits[tc] = c
        print(f"  fit on {tc}: gate {'PASS' if ok else 'REJECT'} "
              f"(min det {mindet:+.3f}, scale ratio {sr:.2f})")

    print(f"\n  {'evaluated on':>18} {'own fit':>10} {'other fit':>11} {'stored':>9} "
          f"{'noise floor':>12}")
    for tc in tcs:
        own, n1 = straightness(info[tc]["lines"], fits[tc], rlim, ctr)
        oth, _ = straightness(info[tc]["lines"], fits[far if tc == near else near], rlim, ctr)
        sto, _ = straightness(info[tc]["lines"], stored, rlim, ctr)
        print(f"  {tc:>18} {own:10.3f} {oth:11.3f} {sto:9.3f} {info[tc]['noise']:12.3f}"
              f"   (n={n1})")

    print("\n  interpretation: the excess of 'other fit' over 'own fit' is the part of the")
    print("  distortion that is specific to the board's range. Compare it to the noise floor.")
    for tc in tcs:
        own, _ = straightness(info[tc]["lines"], fits[tc], rlim, ctr)
        oth, _ = straightness(info[tc]["lines"], fits[far if tc == near else near], rlim, ctr)
        excess = math.sqrt(max(0.0, oth * oth - own * own))
        print(f"    {tc}: transfer excess {excess:6.3f} px "
              f"against corner noise {info[tc]['noise']:.3f} px")

    # Shape of the difference, after removing the homography the objective cannot see.
    print("\n" + "=" * 78)
    print("shape of the difference field, gauge removed")
    print("=" * 78)
    grid = [(x, y) for x in range(60, 1861, 50) for y in range(60, 1021, 50)
            if math.hypot(x - ctr[0], y - ctr[1]) <= rlim]
    a = [undistort(x, y, fits[near]) for x, y in grid]
    b = [undistort(x, y, fits[far]) for x, y in grid]
    H = solve_homography(b, a)
    resid = []
    for (x, y), pa, pb in zip(grid, a, b):
        w = H[6] * pb[0] + H[7] * pb[1] + 1.0
        hx = (H[0] * pb[0] + H[1] * pb[1] + H[2]) / w
        hy = (H[3] * pb[0] + H[4] * pb[1] + H[5]) / w
        resid.append((x, y, pa[0] - hx, pa[1] - hy))
    rms = math.sqrt(sum(dx * dx + dy * dy for _, _, dx, dy in resid) / len(resid))
    print(f"  rms residual difference after removing the best-fit homography: {rms:.3f} px")
    print(f"  (before removing it, the raw field difference is "
          f"{math.sqrt(sum((pa[0]-pb[0])**2 + (pa[1]-pb[1])**2 for pa, pb in zip(a, b))/len(a)):.1f} px, "
          f"which is almost entirely gauge and means nothing)")
    print(f"\n  {'radius band':>14} {'n':>5} {'rms':>8} {'radial':>8} {'tangential':>11}")
    for lo, hi in ((0, 300), (300, 500), (500, 700), (700, 1200)):
        s = [r for r in resid if lo <= math.hypot(r[0] - ctr[0], r[1] - ctr[1]) < hi]
        if len(s) < 8:
            continue
        rad, tan = [], []
        for x, y, dx, dy in s:
            ex, ey = x - ctr[0], y - ctr[1]
            L = math.hypot(ex, ey) or 1.0
            rad.append((dx * ex + dy * ey) / L)
            tan.append((-dx * ey + dy * ex) / L)
        print(f"  {f'{lo}-{hi}':>14} {len(s):5d} "
              f"{math.sqrt(sum(dx*dx+dy*dy for _,_,dx,dy in s)/len(s)):8.3f} "
              f"{math.sqrt(sum(v*v for v in rad)/len(rad)):8.3f} "
              f"{math.sqrt(sum(v*v for v in tan)/len(tan)):11.3f}")
    return 0


def solve_homography(src, dst):
    a, b = [], []
    for (u, v), (x, y) in zip(src, dst):
        a.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); b.append(x)
        a.append([0, 0, 0, u, v, 1, -u * y, -v * y]); b.append(y)
    n = 8
    ata = [[sum(a[r][i] * a[r][j] for r in range(len(a))) for j in range(n)] for i in range(n)]
    atb = [sum(a[r][i] * b[r] for r in range(len(a))) for i in range(n)]
    m = [ata[i][:] + [atb[i]] for i in range(n)]
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


if __name__ == "__main__":
    sys.exit(main())
