#!/usr/bin/env python3
"""Minimal test of the ellipticity remedy on one document, in-sample only.

Fits Brown-Conrady with and without a single ellipticity parameter and reports both the residual
and, more to the point, the m = 2 harmonic of the residual field afterwards. The rms says whether
the fit improved; the harmonic says whether the specific structure the parameter was introduced to
absorb has actually gone.

No cross-validation here -- this is the fast first look, to size the effect and the runtime before
committing to a fuller comparison.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def lm(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = lm("elliptest")
F = E.F
VSD = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")


def ell_undistort(xy, theta):
    """Brown-Conrady evaluated on an elliptical radius, as an anisotropic pre-scale."""
    e = theta[13] if len(theta) > 13 else 0.0
    if e != 0.0:
        cx, cy = theta[0], theta[1]
        xy = np.stack([cx + (xy[:, 0] - cx) * (1.0 + e),
                       cy + (xy[:, 1] - cy) * (1.0 - e)], axis=1)
    return F.undistort(xy, theta[:13], 0.0)


def corner_field(lineset, theta):
    """2D residual vectors at corners shared by both line families."""
    L = {k: np.asarray(v, float) for k, v in lineset.items() if len(v) >= 4}
    fits = {}
    for k, pts in L.items():
        u = ell_undistort(pts, theta)
        c = u.mean(axis=0)
        q = u - c
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        d = np.array([math.cos(th), math.sin(th)])
        fits[k] = (d, -q[:, 0] * d[1] + q[:, 1] * d[0])
    angs = {k: math.degrees(math.atan2(f[0][1], f[0][0])) % 180 for k, f in fits.items()}
    ref = sorted(angs.values())[len(angs) // 2]
    fam = {k: 0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for k, a in angs.items()}
    index = {}
    for k, pts in L.items():
        if fam[k] == 0:
            for i, p in enumerate(pts):
                index[(round(p[0], 3), round(p[1], 3))] = (k, i)
    out = []
    for kb, pts in L.items():
        if fam[kb] != 1:
            continue
        for ib, p in enumerate(pts):
            hit = index.get((round(p[0], 3), round(p[1], 3)))
            if hit is None:
                continue
            ka, ia = hit
            ua, ub = fits[ka][0], fits[kb][0]
            na = np.array([-ua[1], ua[0]])
            nb = np.array([-ub[1], ub[0]])
            det = na[0] * nb[1] - na[1] * nb[0]
            if abs(det) < 0.25:
                continue
            ra, rb = fits[ka][1][ia], fits[kb][1][ib]
            out.append((p[0], p[1], (ra * nb[1] - rb * na[1]) / det,
                        (na[0] * rb - nb[0] * ra) / det))
    return np.asarray(out)


def harmonics(field, centre):
    x, y, ex, ey = field.T
    dx, dy = x - centre[0], y - centre[1]
    r = np.hypot(dx, dy)
    keep = r > 1e-6
    dx, dy, r = dx[keep], dy[keep], r[keep]
    rad = (ex[keep] * dx + ey[keep] * dy) / r
    phi = np.arctan2(dy, dx)
    rows = []
    for lo, hi in ((300, 700), (700, 1400)):
        m = (r >= lo) & (r < hi)
        if m.sum() < 30:
            continue
        vals = []
        for mm in (1, 2, 3):
            a = 2.0 * float(np.mean(rad[m] * np.cos(mm * phi[m])))
            b = 2.0 * float(np.mean(rad[m] * np.sin(mm * phi[m])))
            vals.append((math.hypot(a, b), math.degrees(math.atan2(b, a))))
        rows.append((lo, hi, int(m.sum()), vals))
    return rows


def main():
    base = F.MODELS["full-13"]
    for clip in ("Left Camera", "Right Camera"):
        centre, stored, sets = F.load(VSD, clip)
        lines = [L for tc in sorted(sets) for L in sets[tc]]
        lineset = {i: L for i, L in enumerate(lines)}
        pl = E.EllipticalPlumblines(lines)
        print(f"\n{'='*78}\n{clip}: {len(lines)} lines, {pl.n} points\n{'='*78}")
        for label, mask, use_e in (("Brown-Conrady 13", base, False),
                                   ("+ ellipticity", base + [13], True)):
            t0 = time.time()
            th, rms = E.fit_e(pl, mask, centre, use_e, restarts=3)
            dt = time.time() - t0
            ok, mindet, ratio = F.gate(th[:13], pl)
            e = th[13]
            print(f"  {label:18s} rms {rms:.4f} px   ellipticity "
                  f"{(f'{e:+.6f}' if use_e else '     -   ')}   "
                  f"gate {'PASS' if ok else 'REJECT'} (ratio {ratio:.2f})   [{dt:.0f}s]")
            fld = corner_field(lineset, th)
            for lo, hi, n, vals in harmonics(fld, (th[0], th[1])):
                s = "  ".join(f"m={i+1}: {a:5.3f}@{p:+4.0f}" for i, (a, p) in enumerate(vals))
                print(f"      residual harmonics r {lo}-{hi} (n={n}): {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
