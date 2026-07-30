#!/usr/bin/env python3
"""Does one ellipticity parameter absorb the m = 2 residual?

The anisotropy map finds a large m = 2 harmonic in the radial residual, at a phase of almost exactly
180 degrees in every camera of every 8 mm document measured. An m = 2 pattern locked to the *image
axes* rather than to a per-rig direction is not a decentred-dome signature, which would point
wherever that dome happens to be off centre. It says the iso-distortion contours are ellipses
aligned with the sensor, not circles.

A pure anisotropic scaling cannot be the cause, because that is affine, bends no line, and is
absorbed by the two-plane homographies downstream. What the data is asking for is the *non-affine*
version: a radial series whose argument is an elliptical radius.

That is one extra parameter, and it has a tidy implementation. Composing an anisotropic pre-scale
with the existing Brown-Conrady map gives exactly elliptical iso-contours; the affine part left over
on the output side is gauge and needs no undoing. So:

    undistort_elliptical(p) = brown_conrady(diag(1 + e, 1 - e) . (p - centre) + centre)

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fitter", os.path.join(HERE, "fitter.py"))
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)

VSD_LIST = [
    ("2016-08-13-2 Chena", ["Right Camera", "Left Camera"]),
    ("2015-09-04-1 Clearwater", ["Left Camera", "Right Camera"]),
    ("2016-08-07-1 Panguingue", ["Left Camera", "Right Camera"]),
]
FOLDER = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
E_SCALE = 1.0e-3          # so a unit step in the optimizer is a 0.1% ellipticity


class EllipticalPlumblines(F.Plumblines):
    """Plumblines whose residual is evaluated through an elliptical Brown-Conrady map.

    Parameter 13 of the extended vector is the ellipticity e; e = 0 reproduces the shipped model
    exactly, so the comparison is strictly nested."""

    def residuals(self, theta):
        e = theta[13] if len(theta) > 13 else 0.0
        xy = self.xy
        if e != 0.0:
            cx, cy = theta[0], theta[1]
            xy = np.stack([cx + (xy[:, 0] - cx) * (1.0 + e),
                           cy + (xy[:, 1] - cy) * (1.0 - e)], axis=1)
        u = F.undistort(xy, theta[:13], self.sref)
        cx_ = np.add.reduceat(u[:, 0], self.starts) / self.counts
        cy_ = np.add.reduceat(u[:, 1], self.starts) / self.counts
        qx = u[:, 0] - np.repeat(cx_, self.counts)
        qy = u[:, 1] - np.repeat(cy_, self.counts)
        sxy = np.add.reduceat(qx * qy, self.starts)
        sd = np.add.reduceat(qx * qx - qy * qy, self.starts)
        th = 0.5 * np.arctan2(2.0 * sxy, sd)
        return -qx * np.repeat(np.sin(th), self.counts) + qy * np.repeat(np.cos(th), self.counts)


def expand14(v, mask, centre, use_e):
    theta = np.zeros(14)
    theta[0], theta[1] = centre
    for val, j in zip(v, mask):
        theta[j] = val * (E_SCALE if j == 13 else F.SCALE[j])
    return theta


def fit_e(pl, mask, centre, use_e, restarts=6):
    from scipy.optimize import least_squares, minimize
    lo, hi = pl.xy.min(axis=0), pl.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 15), np.linspace(lo[1], hi[1], 15))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    W = 50.0 * math.sqrt(pl.n)

    def pen(theta):
        det = F.jac_det(grid, theta[:13], pl.sref)
        mags = np.sqrt(np.abs(F.jac_det(pl.xy, theta[:13], pl.sref)))
        ratio = mags.max() / mags.min() if mags.min() > 0 else 1e6
        return np.array([W * max(0.0, 0.05 - float(det.min())),
                         W * max(0.0, float(ratio) - 3.8)])

    def resid(v):
        th = expand14(v, mask, centre, use_e)
        return np.concatenate([pl.residuals(th), pen(th)])

    rng = np.random.default_rng(11)
    seeds = [np.zeros(len(mask))]
    for _ in range(restarts - 1):
        seeds.append(rng.normal(0.0, 3.0, len(mask)))
    for s in seeds:
        for k, j in enumerate(mask):
            if j < 2:
                s[k] = centre[j] / F.SCALE[j]
    best, brms = None, np.inf
    for s in seeds:
        try:
            r = least_squares(resid, s, method="trf", x_scale="jac",
                              ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20000)
        except Exception:                                    # noqa: BLE001
            continue
        th = expand14(r.x, mask, centre, use_e)
        rr = pl.residuals(th)
        rms = float(np.sqrt(rr @ rr / pl.n))
        if rms < brms:
            best, brms = th, rms
    return best, brms


def crossval_e(lines, mask, centre, use_e, folds=6):
    rng = np.random.default_rng(3)
    order = rng.permutation(len(lines))
    num, den = 0.0, 0
    for i in range(folds):
        g = set(order[i::folds].tolist())
        test = [lines[j] for j in g]
        train = [lines[j] for j in range(len(lines)) if j not in g]
        if len(train) < 8 or not test:
            continue
        th, _ = fit_e(EllipticalPlumblines(train), mask, centre, use_e, restarts=3)
        r = EllipticalPlumblines(test).residuals(th)
        num += float(r @ r)
        den += len(r)
    return math.sqrt(num / den) if den else float("nan")


def main():
    base = F.MODELS["full-13"]
    print(f"  {'document':>26} {'camera':>14} {'model':>16} {'in-sample':>10} "
          f"{'held-out':>9} {'ellipticity':>12}")
    for doc, clips in VSD_LIST:
        path = os.path.join(FOLDER, doc + ".vsd")
        for clip in clips:
            centre, stored, sets = F.load(path, clip)
            lines = [L for tc in sorted(sets) for L in sets[tc]]
            pl = EllipticalPlumblines(lines)
            for label, mask, use_e in (("Brown-Conrady 13", base, False),
                                       ("+ ellipticity", base + [13], True)):
                th, rms = fit_e(pl, mask, centre, use_e)
                ho = crossval_e(lines, mask, centre, use_e)
                e = th[13]
                print(f"  {doc[:26]:>26} {clip:>14} {label:>16} {rms:10.4f} {ho:9.4f} "
                      f"{(f'{e:+.5f}' if use_e else '-'):>12}")
    print("\n  A positive ellipticity stretches x relative to y before the radial map is applied,")
    print("  so the iso-distortion contours become ellipses aligned with the sensor axes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
