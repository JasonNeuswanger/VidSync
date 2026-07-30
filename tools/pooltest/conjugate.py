#!/usr/bin/env python3
"""Canonical axis-locked anisotropic radius by conjugation, and its decomposition.

Phase 1 implements U(x) = c + A^-1 [ B_0(A(x - c)) ], with A = diag(exp(eta), exp(-eta)), so the
whole Brown-Conrady correction is conjugated -- radial and decentering alike -- rather than the
input being pre-scaled with no matching undo on the output. det A = 1 by construction, the pure
affine part cancels exactly from the corrected output, and eta = 0 reproduces the existing map
numerically. The radial factor keeps its pinned f(0) = 1; no free constant radial coefficient is
introduced.

Phase 2 decomposes the change from baseline to conjugated fit along an explicit telescoping path,
and splits the direct anisotropy increment into its exact radial and decentering parts. Harmonics
are compared through cosine and sine coefficients, never by differencing amplitudes.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("fitter", os.path.join(HERE, "fitter.py"))
F = importlib.util.module_from_spec(_s)
_s.loader.exec_module(F)

VSD = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")
# scaled units: x0, y0, k1..k4, p1..p4, eta
PSCALE = np.array([1.0e3, 1.0e3, 5.0e-8, 1.0e-14, 1.0e-21, 1.0e-27,
                   1.0e-7, 1.0e-7, 1.0e-7, 1.0e-10, 1.0e-3])
PNAMES = ["x0", "y0", "k1", "k2", "k3", "k4", "p1", "p2", "p3", "p4", "eta"]


# ---------------------------------------------------------------- model pieces

def delta_r(u, k):
    """Radial correction only, on centered coordinates."""
    s = u[:, 0] ** 2 + u[:, 1] ** 2
    R = np.zeros_like(s)
    sp = np.ones_like(s)
    for ki in k:
        sp = sp * s
        R = R + ki * sp
    return u * R[:, None]


def d_p(u, p):
    """The complete implemented decentering correction, on centered coordinates."""
    ux, uy = u[:, 0], u[:, 1]
    s = ux * ux + uy * uy
    T = 1.0 + p[2] * s + p[3] * s * s
    dx = (p[0] * (s + 2 * ux * ux) + 2 * p[1] * ux * uy) * T
    dy = (2 * p[0] * ux * uy + p[1] * (s + 2 * uy * uy)) * T
    return np.stack([dx, dy], axis=1)


def bc0(u, k, p):
    """Centered Brown-Conrady: B(z) = z + delta_r(z) + D_p(z)."""
    return u + delta_r(u, k) + d_p(u, p)


def amat(eta):
    return np.array([math.exp(eta), math.exp(-eta)])


def U(x, eta, k, p, c):
    """Conjugated correction. eta = 0 reproduces the existing map exactly."""
    a = amat(eta)
    u = (x - c) * a
    return c + bc0(u, k, p) / a


def unpack(v):
    q = v * PSCALE
    return q[10], q[2:6], q[6:10], np.array([q[0], q[1]])


# ---------------------------------------------------------------- objective

class Lines:
    def __init__(self, lines):
        self.xy = np.concatenate([np.asarray(L, float) for L in lines], axis=0)
        n = np.array([len(L) for L in lines])
        self.counts = n
        self.starts = np.concatenate([[0], np.cumsum(n)[:-1]])
        self.n = len(self.xy)
        self.nlines = len(lines)

    def straight(self, pts):
        cx = np.add.reduceat(pts[:, 0], self.starts) / self.counts
        cy = np.add.reduceat(pts[:, 1], self.starts) / self.counts
        qx = pts[:, 0] - np.repeat(cx, self.counts)
        qy = pts[:, 1] - np.repeat(cy, self.counts)
        sxy = np.add.reduceat(qx * qy, self.starts)
        sd = np.add.reduceat(qx * qx - qy * qy, self.starts)
        th = 0.5 * np.arctan2(2.0 * sxy, sd)
        return -qx * np.repeat(np.sin(th), self.counts) + qy * np.repeat(np.cos(th), self.counts)

    def resid(self, v):
        eta, k, p, c = unpack(v)
        return self.straight(U(self.xy, eta, k, p, c))


def gate_terms(L, v):
    """The acceptance-gate penalty, identical in both arms so the comparison is like for like."""
    eta, k, p, c = unpack(v)
    lo, hi = L.xy.min(axis=0), L.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 15), np.linspace(lo[1], hi[1], 15))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    full = np.zeros(13)
    full[0], full[1] = c
    full[2:6] = k
    full[9:13] = p
    a = amat(eta)
    det = F.jac_det(((grid - c) * a) + c, full, 0.0)
    mags = np.sqrt(np.abs(F.jac_det(((L.xy - c) * a) + c, full, 0.0)))
    ratio = mags.max() / mags.min() if mags.min() > 0 else 1e6
    W = 50.0 * math.sqrt(L.n)
    return np.array([W * max(0.0, 0.05 - float(det.min())),
                     W * max(0.0, float(ratio) - 3.8)]), float(ratio), float(det.min())


def full_resid(L, v):
    pen, _, _ = gate_terms(L, v)
    return np.concatenate([L.resid(v), pen])


def report_fit(L, v):
    r = L.resid(v)
    sse = float(r @ r)
    pen, ratio, mindet = gate_terms(L, v)
    return sse, math.sqrt(sse / L.n), sse + float(pen @ pen), ratio, mindet


# ---------------------------------------------------------------- corners and harmonics

def pair_corners(lineset, eta, k, p, c):
    L = {i: np.asarray(v, float) for i, v in lineset.items() if len(v) >= 4}
    fits = {}
    for i, pts in L.items():
        u = U(pts, eta, k, p, c)
        q = u - u.mean(axis=0)
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        fits[i] = np.array([math.cos(th), math.sin(th)])
    angs = {i: math.degrees(math.atan2(d[1], d[0])) % 180 for i, d in fits.items()}
    ref = sorted(angs.values())[len(angs) // 2]
    fam = {i: 0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for i, a in angs.items()}
    index = {}
    for i, pts in L.items():
        if fam[i] == 0:
            for j, q in enumerate(pts):
                index[(round(q[0], 3), round(q[1], 3))] = (i, j)
    pairs = []
    for ib, pts in L.items():
        if fam[ib] != 1:
            continue
        for jb, q in enumerate(pts):
            hit = index.get((round(q[0], 3), round(q[1], 3)))
            if hit is not None:
                pairs.append((hit[0], hit[1], ib, jb, q[0], q[1]))
    return L, fam, pairs


def residual_field(L, pairs, eta, k, p, c):
    fits = {}
    for i, pts in L.items():
        u = U(pts, eta, k, p, c)
        cen = u.mean(axis=0)
        q = u - cen
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        d = np.array([math.cos(th), math.sin(th)])
        fits[i] = (d, -q[:, 0] * d[1] + q[:, 1] * d[0])
    out = []
    for ia, ja, ib, jb, px, py in pairs:
        ua, ub = fits[ia][0], fits[ib][0]
        na = np.array([-ua[1], ua[0]])
        nb = np.array([-ub[1], ub[0]])
        det = na[0] * nb[1] - na[1] * nb[0]
        if abs(det) < 0.25:
            out.append((np.nan, np.nan))
            continue
        ra, rb = fits[ia][1][ja], fits[ib][1][jb]
        out.append(((ra * nb[1] - rb * na[1]) / det, (na[0] * rb - nb[0] * ra) / det))
    return np.asarray(out)


def harmonics(pos, vec, cref, keep):
    d = pos - cref
    r = np.hypot(d[:, 0], d[:, 1])
    m = keep & (r > 150.0) & np.isfinite(vec[:, 0])
    dx, dy, rr = d[m, 0], d[m, 1], r[m]
    rad = (vec[m, 0] * dx + vec[m, 1] * dy) / rr
    tan = (-vec[m, 0] * dy + vec[m, 1] * dx) / rr
    phi = np.arctan2(dy, dx)
    out = {}
    for name, comp in (("rad", rad), ("tan", tan)):
        for mm in (1, 2, 3):
            a = 2.0 * float(np.mean(comp * np.cos(mm * phi)))
            b = 2.0 * float(np.mean(comp * np.sin(mm * phi)))
            out[(name, mm)] = (a, b, math.hypot(a, b), math.degrees(math.atan2(b, a)))
    return out, int(m.sum())


def show(tag, h):
    for name in ("rad", "tan"):
        for mm in (1, 2, 3):
            a, b, amp, ph = h[(name, mm)]
            print(f"    {tag:34s} {name} m={mm}  cos {a:+9.4f}  sin {b:+9.4f}  "
                  f"amp {amp:8.4f}  phase {ph:+7.1f}")


# ---------------------------------------------------------------- main

def main():
    print("Document: 2015-09-04-1 Clearwater.vsd")
    print("Model: U(x) = c + A^-1 [ B_0( A(x-c) ) ],  A = diag(exp(eta), exp(-eta)),  det A = 1")
    print("Free parameters: x0, y0, k1..k4, p1..p4, eta   (11; baseline is the same minus eta)")
    print("Objective: summed squared orthogonal-regression residual, plus the unchanged")
    print("acceptance-gate penalty (zero on the feasible side), identical in both arms.\n")

    for clip in ("Left Camera", "Right Camera"):
        centre0, stored, sets = F.load(VSD, clip)
        lines = [Lg for tc in sorted(sets) for Lg in sets[tc]]
        lineset = {i: Lg for i, Lg in enumerate(lines)}
        L = Lines(lines)
        print("=" * 96)
        print(f"CLIP: {clip}   lines {L.nlines}   line-point observations {L.n}")
        print("=" * 96)

        # ---- baseline: k1..k4 + p1..p4 + centre, eta absent ----
        mask_base = list(range(10))                     # everything except eta
        rng = np.random.default_rng(5)
        best, bcost = None, np.inf
        t0 = time.time()
        for t in range(3):
            s0 = np.zeros(11)
            s0[0], s0[1] = centre0[0] / PSCALE[0], centre0[1] / PSCALE[1]
            if t:
                s0[2:10] += rng.normal(0, 3.0, 8)
            def rb(w, s0=s0):
                v = s0.copy()
                v[mask_base] = w
                v[10] = 0.0
                return full_resid(L, v)
            r = least_squares(rb, s0[mask_base], method="trf", x_scale="jac",
                              ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20000)
            v = s0.copy(); v[mask_base] = r.x; v[10] = 0.0
            c = float(r.fun @ r.fun)
            if c < bcost:
                best, bcost, rbase = v.copy(), c, r
        tbase = time.time() - t0
        sse0, rms0, pen0, ratio0, mindet0 = report_fit(L, best)
        eta0, k0, p0, c0 = unpack(best)

        print(f"  baseline k1..k4 fit: RMS {rms0:.6f} px   SSE {sse0:.4f}   "
              f"penalized objective {pen0:.4f}")
        print(f"    gate scale ratio {ratio0:.3f}, min det {mindet0:+.4f}; "
              f"{3} starts, {tbase:.0f}s")

        # ---- verification at eta = 0 ----
        vchk = best.copy()
        eta_c, k_c, p_c, c_c = unpack(vchk)
        full13 = np.zeros(13); full13[0], full13[1] = c_c; full13[2:6] = k_c; full13[9:13] = p_c
        mine = U(L.xy, 0.0, k_c, p_c, c_c)
        theirs = F.undistort(L.xy, full13, 0.0)
        dmax = float(np.abs(mine - theirs).max())
        rme = L.resid(vchk)
        rth = F.Plumblines(lines, 0.0).residuals(full13)
        objdiff = abs(float(rme @ rme) - float(rth @ rth))
        vstart = best.copy(); vstart[10] = 0.0
        sse_s, rms_s, pen_s, _, _ = report_fit(L, vstart)
        print(f"  verification at eta = 0:")
        print(f"    max coordinate difference against the existing implementation "
              f"{dmax:.3e} px")
        print(f"    objective difference {objdiff:.3e} (absolute, on SSE)")
        print(f"    embedded start SSE {sse_s:.6f} vs baseline SSE {sse0:.6f}, "
              f"difference {abs(sse_s-sse0):.3e}")

        # ---- one anisotropic fit, initialized at the baseline with eta = 0 ----
        t0 = time.time()
        ra = least_squares(lambda w: full_resid(L, w), vstart, method="trf", x_scale="jac",
                           ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20000)
        tan_ = time.time() - t0
        v1 = ra.x
        sse1, rms1, pen1, ratio1, mindet1 = report_fit(L, v1)
        eta1, k1_, p1_, c1_ = unpack(v1)
        elg = math.tanh(eta1)
        RA = math.exp(2 * eta1)
        print(f"  conjugated fit: RMS {rms1:.6f} px   SSE {sse1:.4f}   "
              f"penalized objective {pen1:.4f}")
        print(f"    RMS reduction {100*(1-rms1/rms0):+.2f}%   "
              f"{'OK' if pen1 <= pen_s + 1e-9 else 'OPTIMIZER FAILURE: worse than start'}")
        print(f"    eta {eta1:+.8f}   e_legacy = tanh(eta) {elg:+.8f}   "
              f"R_A = exp(2 eta) {RA:.8f}")
        print(f"    gate scale ratio {ratio1:.3f}, min det {mindet1:+.4f}")
        print(f"    optimizer: status {ra.status} ({ra.message.strip()}), "
              f"optimality {ra.optimality:.3e}, nfev {ra.nfev}, njev {ra.njev}, {tan_:.0f}s")
        print(f"  fitted centre baseline ({c0[0]:.4f}, {c0[1]:.4f}) -> "
              f"conjugated ({c1_[0]:.4f}, {c1_[1]:.4f})   shift "
              f"({c1_[0]-c0[0]:+.4f}, {c1_[1]-c0[1]:+.4f}) px")
        for i, nm in enumerate(["k1", "k2", "k3", "k4"]):
            print(f"    {nm}: {k0[i]:+.10e} -> {k1_[i]:+.10e}   "
                  f"ratio {k1_[i]/k0[i] if k0[i] else float('nan'):+.4f}")
        for i, nm in enumerate(["p1", "p2", "p3", "p4"]):
            print(f"    {nm}: {p0[i]:+.10e} -> {p1_[i]:+.10e}   "
                  f"ratio {p1_[i]/p0[i] if p0[i] else float('nan'):+.4f}")

        # ---- Phase 2 ----
        Ld, fam, pairs = pair_corners(lineset, 0.0, k0, p0, c0)
        pos = np.array([[q[4], q[5]] for q in pairs])
        keep = np.ones(len(pos), bool)
        cref = c0
        print(f"\n  PHASE 2 decomposition   paired corners {len(pos)}   "
              f"common reference centre for projection ({cref[0]:.4f}, {cref[1]:.4f})")
        print(f"  corners with r > 150 px are used for harmonics")
        print("  counterfactual definition: centre contribution is "
              "U(eta1,k1,p1,c1) - U(eta1,k1,p1,c0), all else fixed at final values")

        maps = {
            "U0 baseline": U(pos, 0.0, k0, p0, c0),
            "Uk radial refit": U(pos, 0.0, k1_, p0, c0),
            "Up decentering refit": U(pos, 0.0, k1_, p1_, c0),
            "Uc centre refit": U(pos, 0.0, k1_, p1_, c1_),
            "UA direct anisotropy": U(pos, eta1, k1_, p1_, c1_),
        }
        order = list(maps)
        incs = {}
        for i in range(1, len(order)):
            incs[f"{i}. {order[i].split()[1]}+ incr"] = maps[order[i]] - maps[order[i - 1]]

        a = amat(eta1)
        u1 = (pos - c1_) * a
        u0 = pos - c1_
        dAr = delta_r(u1, k1_) / a - delta_r(u0, k1_)
        dAp = d_p(u1, p1_) / a - d_p(u0, p1_)
        cf = U(pos, eta1, k1_, p1_, c1_) - U(pos, eta1, k1_, p1_, c0)
        chk = float(np.abs((maps["UA direct anisotropy"] - maps["Uc centre refit"])
                           - (dAr + dAp)).max())
        print(f"  exactness check: |(UA - Uc) - (dA_r + dA_p)| max {chk:.3e} px "
              f"(the affine part must cancel identically)")

        fb = residual_field(Ld, pairs, 0.0, k0, p0, c0)
        ff = residual_field(Ld, pairs, eta1, k1_, p1_, c1_)
        fields = [("baseline residual field", fb), ("final residual field", ff)]
        fields += [(nm, inc) for nm, inc in incs.items()]
        fields += [("dA_r direct radial anisotropy", dAr),
                   ("dA_p decentering interaction", dAp),
                   ("centre-shift counterfactual", cf)]
        for nm, fld in fields:
            h, nn = harmonics(pos, np.asarray(fld, float), cref, keep)
            print(f"\n    [{nm}]  n={nn}")
            show("", h)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
