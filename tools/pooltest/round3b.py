#!/usr/bin/env python3
"""Round 3, tasks 5 and 6: repaired harmonic estimator and projective-gauge comparison, four clips.

The previous joint estimator used quadratics in t = (r/R)^2 for every angular mode and failed its
own validation. The radial anisotropy's radial component is exactly

    r * sum_j alpha_j t^j [ (cosh 2eta + sinh 2eta cos 2phi)^j - 1 ],

so its radial factors are r t^j for j = 1..4. The basis is replaced by {1, r, r t, r t^2, r t^3,
r t^4}, which spans them exactly. Validation is on Delta_A,r sampled at each clip's own corners and
projected about that fit's own anisotropy centre.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("round3", os.path.join(HERE, "round3.py"))
T = importlib.util.module_from_spec(_s)
_s.loader.exec_module(T)
N, R, W, Hh = T.N, T.R, T.W, T.H

MMAX = 4
RREF = (300.0, 600.0, 900.0)


def radial_basis(r):
    t = (r / R) ** 2
    return np.stack([np.ones_like(r), r, r * t, r * t ** 2, r * t ** 3, r * t ** 4], axis=1)


def design(r, phi):
    B = radial_basis(r)
    cols = [B]
    for m in range(1, MMAX + 1):
        cols.append(B * np.cos(m * phi)[:, None])
        cols.append(B * np.sin(m * phi)[:, None])
    return np.concatenate(cols, axis=1), B.shape[1]


def harm(pos, vec, cref, rrefs=RREF):
    d = pos - cref
    r = np.hypot(d[:, 0], d[:, 1])
    keep = (r > 150.0) & np.isfinite(vec[:, 0]) & np.isfinite(vec[:, 1])
    d, r, v = d[keep], r[keep], vec[keep]
    phi = np.arctan2(d[:, 1], d[:, 0])
    rad = (v[:, 0] * d[:, 0] + v[:, 1] * d[:, 1]) / r
    tan = (-v[:, 0] * d[:, 1] + v[:, 1] * d[:, 0]) / r
    X, nb = design(r, phi)
    sv = np.linalg.svd(X, compute_uv=False)
    out = {}
    for nm, y in (("rad", rad), ("tan", tan)):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        for m in (1, 2, 3):
            i = nb * (1 + 2 * (m - 1))
            for rr in rrefs:
                b = radial_basis(np.array([rr]))[0]
                cc = float(beta[i:i + nb] @ b)
                ss = float(beta[i + nb:i + 2 * nb] @ b)
                out[(nm, m, rr)] = (cc, ss, math.hypot(cc, ss),
                                    math.degrees(math.atan2(ss, cc)))
    return out, int(keep.sum()), int((sv > sv[0] * 1e-10).sum()), float(sv[0] / sv[-1]), X.shape[1]


def pairs_of(clip, v):
    c, k, p, eta = N.norm_to_phys(v)
    L = {i: np.asarray(q, float) for i, q in clip.lineset.items() if len(q) >= 4}
    fits = {}
    for i, pts in L.items():
        u = N.Umap(pts, c, k, p, eta)
        q = u - u.mean(axis=0)
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        fits[i] = np.array([math.cos(th), math.sin(th)])
    angs = {i: math.degrees(math.atan2(dd[1], dd[0])) % 180 for i, dd in fits.items()}
    ref = sorted(angs.values())[len(angs) // 2]
    fam = {i: 0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for i, a in angs.items()}
    idx = {}
    for i, pts in L.items():
        if fam[i] == 0:
            for j, q in enumerate(pts):
                idx[(round(q[0], 3), round(q[1], 3))] = (i, j)
    pr = []
    for ib, pts in L.items():
        if fam[ib] != 1:
            continue
        for jb, q in enumerate(pts):
            hit = idx.get((round(q[0], 3), round(q[1], 3)))
            if hit:
                pr.append((hit[0], hit[1], ib, jb, q[0], q[1]))
    return pr


def resid_field(clip, v, pr):
    c, k, p, eta = N.norm_to_phys(v)
    L = {i: np.asarray(q, float) for i, q in clip.lineset.items() if len(q) >= 4}
    fits = {}
    for i, pts in L.items():
        u = N.Umap(pts, c, k, p, eta)
        q = u - u.mean(axis=0)
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        dd = np.array([math.cos(th), math.sin(th)])
        fits[i] = (dd, -q[:, 0] * dd[1] + q[:, 1] * dd[0])
    out = []
    for ia, ja, ib, jb, px, py in pr:
        ua, ub = fits[ia][0], fits[ib][0]
        na = np.array([-ua[1], ua[0]]); nb = np.array([-ub[1], ub[0]])
        det = na[0] * nb[1] - na[1] * nb[0]
        if abs(det) < 0.25:
            out.append((np.nan, np.nan)); continue
        ra, rb = fits[ia][1][ja], fits[ib][1][jb]
        out.append(((ra * nb[1] - rb * na[1]) / det, (na[0] * rb - nb[0] * ra) / det))
    return np.asarray(out)


def align(src, tgt, kind):
    n = len(src)
    A = np.zeros((2 * n, 6)); b = np.zeros(2 * n)
    A[0::2, 0] = src[:, 0]; A[0::2, 1] = src[:, 1]; A[0::2, 2] = 1
    A[1::2, 3] = src[:, 0]; A[1::2, 4] = src[:, 1]; A[1::2, 5] = 1
    b[0::2] = tgt[:, 0]; b[1::2] = tgt[:, 1]
    aff, *_ = np.linalg.lstsq(A, b, rcond=None)
    pred = np.stack([src @ aff[0:2] + aff[2], src @ aff[3:5] + aff[5]], axis=1)
    if kind == "affine":
        return tgt - pred
    sc = np.abs(src).max()
    h0 = np.concatenate([aff, [0.0, 0.0]])

    def res(h):
        w = (h[6] * src[:, 0] + h[7] * src[:, 1]) / sc + 1.0
        return np.concatenate([(h[0] * src[:, 0] + h[1] * src[:, 1] + h[2]) / w - tgt[:, 0],
                               (h[3] * src[:, 0] + h[4] * src[:, 1] + h[5]) / w - tgt[:, 1]])
    r = least_squares(res, h0, method="lm", xtol=1e-15, ftol=1e-15, max_nfev=20000)
    h = r.x
    w = (h[6] * src[:, 0] + h[7] * src[:, 1]) / sc + 1.0
    pred = np.stack([(h[0] * src[:, 0] + h[1] * src[:, 1] + h[2]) / w,
                     (h[3] * src[:, 0] + h[4] * src[:, 1] + h[5]) / w], axis=1)
    return tgt - pred


def stats(dv, grid, c):
    mag = np.linalg.norm(dv, axis=1)
    d = grid - c
    rr = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
    rad = (dv[:, 0] * d[:, 0] + dv[:, 1] * d[:, 1]) / rr
    tan = (-dv[:, 0] * d[:, 1] + dv[:, 1] * d[:, 0]) / rr
    return (float(np.sqrt((mag ** 2).mean())), float(np.median(mag)), float(mag.max()),
            float(np.sqrt((rad ** 2).mean())), float(np.sqrt((tan ** 2).mean())))


def main():
    say = lambda *a: print(" ".join(str(x) for x in a), flush=True)
    Z = np.load("/tmp/round3.npz")
    clips = {}
    for dn, path in T.DOCS:
        for cn in T.CLIPS:
            clips[(dn, cn)] = T.Clip(path, cn)

    say("=" * 104)
    say("TASK 5  REPAIRED HARMONIC ESTIMATOR")
    say("=" * 104)
    say(f"  radial basis per angular mode: 1, r, r t, r t^2, r t^3, r t^4 with t = (r/R)^2;")
    say(f"  angular modes m = 0..{MMAX}; joint SVD fit; coefficients reported at r = 300/600/900 px.")
    say("  Validation: Delta_A,r at each clip's own corners, projected about that fit's own")
    say("  anisotropy centre. It is analytically even with zero tangential component.")

    for nn in ("4p", "2p"):
        for key in clips:
            k4 = f"{key[0]}|{key[1]}|{nn}"
            v0, v1 = Z[k4 + "|m0"], Z[k4 + "|m1"]
            clip = clips[key]
            pr = pairs_of(clip, v0)
            pos = np.array([[q[4], q[5]] for q in pr])
            c1, k1, p1, e1 = N.norm_to_phys(v1)
            a = N.amat(e1)
            dAr = N.delta_r((pos - c1) * a, k1) / a - N.delta_r(pos - c1, k1)
            h, nk, rank, cond, ncol = harm(pos, dAr, c1)
            ratio = (h[("rad", 1, 900.0)][2] + h[("rad", 3, 900.0)][2]) / \
                max(h[("rad", 2, 900.0)][2], 1e-12)
            tanmax = max(abs(h[("tan", m, rr)][2]) for m in (1, 2, 3) for rr in RREF)
            say(f"\n  {key[0]} / {key[1]} / {nn}: corners {len(pos)}, used {nk}, "
                f"design {ncol} cols, rank {rank}, condition {cond:.2e}")
            say(f"    validation on Delta_A,r: radial m2 at 900 px "
                f"{h[('rad',2,900.0)][2]:.4f}, odd m1+m3 {h[('rad',1,900.0)][2]:.4f}+"
                f"{h[('rad',3,900.0)][2]:.4f}, odd/even {ratio:.4f}; "
                f"max |tangential| {tanmax:.2e}")
            say(f"    -> {'PASSES' if ratio < 0.02 and tanmax < 1e-3 else 'FAILS'} "
                f"the even-field validation")

    say("\n" + "=" * 104)
    say("TASK 5b  RESIDUAL HARMONICS ABOUT EACH FIT'S OWN ANISOTROPY CENTRE")
    say("=" * 104)
    for nn in ("4p", "2p"):
        say(f"\n  ===== nuisance {nn} =====")
        for key in clips:
            k4 = f"{key[0]}|{key[1]}|{nn}"
            v0, v1 = Z[k4 + "|m0"], Z[k4 + "|m1"]
            clip = clips[key]
            pr = pairs_of(clip, v0)
            pos = np.array([[q[4], q[5]] for q in pr])
            c1 = N.norm_to_phys(v1)[0]
            fb = resid_field(clip, v0, pr)
            ff = resid_field(clip, v1, pr)
            hb, _, _, _, _ = harm(pos, fb, c1)
            hf, _, _, _, _ = harm(pos, ff, c1)
            mb = np.linalg.norm(fb[np.isfinite(fb[:, 0])], axis=1)
            mf = np.linalg.norm(ff[np.isfinite(ff[:, 0])], axis=1)
            say(f"\n  {key[0]} / {key[1]}  (polar origin = anisotropy centre "
                f"{c1[0]:.1f}, {c1[1]:.1f})")
            say(f"    residual vector rms: baseline {np.sqrt((mb**2).mean()):.4f} px -> "
                f"final {np.sqrt((mf**2).mean()):.4f} px")
            for rr in RREF:
                say(f"    r={rr:.0f}: m2 radial baseline amp {hb[('rad',2,rr)][2]:7.4f} "
                    f"ph {hb[('rad',2,rr)][3]:+7.1f}  ->  final amp {hf[('rad',2,rr)][2]:7.4f} "
                    f"ph {hf[('rad',2,rr)][3]:+7.1f}")
            for rr in RREF:
                say(f"    r={rr:.0f}: remaining radial m1 {hf[('rad',1,rr)][2]:7.4f}, "
                    f"m3 {hf[('rad',3,rr)][2]:7.4f}; tangential m1 {hf[('tan',1,rr)][2]:7.4f}, "
                    f"m3 {hf[('tan',3,rr)][2]:7.4f}")

    say("\n" + "=" * 104)
    say("TASK 6  PROJECTIVE-GAUGE COMPARISON, FOUR CLIPS")
    say("=" * 104)
    say("  Displacement RMS is reported before alignment, after the best affine post-map, and")
    say("  after the best projective homography. These are reductions in displacement RMS; the")
    say("  aligned and removed components are not orthogonal, so the ratio is not an additive")
    say("  'fraction of the map that is gauge'.")
    for nn in ("4p", "2p"):
        say(f"\n  ===== nuisance {nn} =====")
        for key in clips:
            k4 = f"{key[0]}|{key[1]}|{nn}"
            v0, v1 = Z[k4 + "|m0"], Z[k4 + "|m1"]
            clip = clips[key]
            lo, hi = clip.xy.min(axis=0), clip.xy.max(axis=0)
            gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 60), np.linspace(lo[1], hi[1], 40))
            grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
            cc = 0.5 * (lo + hi)
            grid = grid[np.hypot(grid[:, 0] - cc[0], grid[:, 1] - cc[1])
                        <= 0.5 * np.hypot(*(hi - lo))]
            c0, k0, p0, _ = N.norm_to_phys(v0)
            c1, k1, p1, e1 = N.norm_to_phys(v1)
            U0 = N.Umap(grid, c0, k0, p0, 0.0)
            U1 = N.Umap(grid, c1, k1, p1, e1)
            Uc = N.Umap(grid, c1, k1, p1, 0.0)
            say(f"\n  {key[0]} / {key[1]}  ({len(grid)} grid points)")
            for lab, src, tgt in (("U0 -> U1 full change", U0, U1),
                                  ("Uc -> U1 direct anisotropy", Uc, U1)):
                say(f"    {lab}")
                for kind, dv in (("before alignment", tgt - src),
                                 ("after best affine", align(src, tgt, "affine")),
                                 ("after homography", align(src, tgt, "homog"))):
                    s = stats(dv, grid, c1)
                    say(f"      {kind:20s} rms {s[0]:9.4f}  median {s[1]:9.4f}  "
                        f"max {s[2]:9.4f}  radial rms {s[3]:8.4f}  tangential rms {s[4]:8.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
