#!/usr/bin/env python3
"""Dimensionless reparameterization, optimizer recovery, gauge quotient, residual-space harmonics.

Stage 0  normalized parameterization and numerical equivalence tests
Stage 1  converged M0 / M1 fits for both clips, with eta profiling
Stage 2  sensitivity of eta to the centre / decentering nuisance structure
Stage 3  baseline-to-anisotropic map difference modulo the downstream projective gauge
Stage 4  residual-space telescoping decomposition with a valid joint harmonic estimator

Constraints. A first pass was run with no constraint at all, on the reasoning that the previous
round's gate penalty sat on its scale-ratio limit in every fit and so would confound both the
stationarity diagnostics and the eta profile. That pass produced garbage, and instructively so:
every solution drove the distortion centre 3500 to 4600 px outside a 1080 px frame, three of four
folded the map over (negative minimum Jacobian determinant), scale ratios reached 2067, and the
residual fell as low as 0.028 px. That is the degeneracy the acceptance gate exists to catch,
unmasked, and it retrospectively explains the 0.0037 px per point fits recorded earlier.

This round therefore uses explicit box bounds, which the normalized parameterization makes natural
because every variable is O(1), plus a soft barrier on bijectivity only. The scale-ratio half of the
production gate is deliberately not imposed, since it was separately shown to clip legitimate
wide-lens solutions; the minimum-determinant half is the principled one and is retained.

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
W, H = 1920.0, 1080.0
R = 1040.0                       # characteristic radius: the useful image radius
NORMNAMES = ["xi", "ups", "a1", "a2", "a3", "a4", "q1", "q2", "q3", "q4", "eta"]


# ------------------------------------------------------------------ parameterization

def norm_to_phys(v):
    """(xi, ups, alpha1..4, q1..4, eta) -> (c, k1..k4, p1..p4, eta) in pixel units."""
    c = np.array([v[0] * R + W / 2.0, v[1] * R + H / 2.0])
    k = np.array([v[2 + j] / R ** (2 * (j + 1)) for j in range(4)])
    p = np.array([v[6] / R, v[7] / R, v[8] / R ** 2, v[9] / R ** 4])
    return c, k, p, v[10]


def phys_to_norm(c, k, p, eta):
    return np.array([(c[0] - W / 2.0) / R, (c[1] - H / 2.0) / R,
                     k[0] * R ** 2, k[1] * R ** 4, k[2] * R ** 6, k[3] * R ** 8,
                     p[0] * R, p[1] * R, p[2] * R ** 2, p[3] * R ** 4, eta])


def delta_r(u, k):
    s = u[:, 0] ** 2 + u[:, 1] ** 2
    Rr = np.zeros_like(s)
    sp = np.ones_like(s)
    for ki in k:
        sp = sp * s
        Rr = Rr + ki * sp
    return u * Rr[:, None]


def d_p(u, p):
    ux, uy = u[:, 0], u[:, 1]
    s = ux * ux + uy * uy
    T = 1.0 + p[2] * s + p[3] * s * s
    return np.stack([(p[0] * (s + 2 * ux * ux) + 2 * p[1] * ux * uy) * T,
                     (2 * p[0] * ux * uy + p[1] * (s + 2 * uy * uy)) * T], axis=1)


def bc0(u, k, p):
    return u + delta_r(u, k) + d_p(u, p)


def amat(eta):
    return np.array([math.exp(eta), math.exp(-eta)])


def Umap(x, c, k, p, eta):
    a = amat(eta)
    return c + bc0((x - c) * a, k, p) / a


def Unorm(x, v):
    c, k, p, eta = norm_to_phys(v)
    return Umap(x, c, k, p, eta)


# ------------------------------------------------------------------ objective

class Clip:
    def __init__(self, name):
        centre0, stored, sets = F.load(VSD, name)
        self.name = name
        self.lines = [Lg for tc in sorted(sets) for Lg in sets[tc]]
        self.lineset = {i: Lg for i, Lg in enumerate(self.lines)}
        self.xy = np.concatenate([np.asarray(Lg, float) for Lg in self.lines], axis=0)
        n = np.array([len(Lg) for Lg in self.lines])
        self.counts = n
        self.starts = np.concatenate([[0], np.cumsum(n)[:-1]])
        self.n = len(self.xy)
        self.nlines = len(self.lines)
        self.centre0 = np.array(centre0)

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
        return self.straight(Unorm(self.xy, v))

    def resid_b(self, v):
        return np.concatenate([self.resid(v), barrier(self, v)])

    def sse(self, v):
        r = self.resid(v)
        return float(r @ r)


# box bounds on the normalized vector; the centre is confined to +/- 0.25 R = +/- 260 px of the
# frame centre, which is generous next to the 30-100 px offsets every credible fit has shown.
BLO = np.array([-0.25, -0.25, -5., -5., -5., -5., -5., -5., -5., -5., -0.05])
BHI = np.array([+0.25, +0.25, +5., +5., +5., +5., +5., +5., +5., +5., +0.05])


def barrier(clip, v):
    """Soft barrier on bijectivity only: penalize any non-positive Jacobian determinant."""
    c, k, p, eta = norm_to_phys(v)
    full = np.zeros(13)
    full[0], full[1] = c
    full[2:6] = k
    full[9:13] = p
    a = amat(eta)
    lo, hi = clip.xy.min(axis=0), clip.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 13), np.linspace(lo[1], hi[1], 13))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    det = F.jac_det(((grid - c) * a) + c, full, 0.0)
    return np.array([200.0 * math.sqrt(clip.n) * max(0.0, 0.05 - float(det.min()))])


def gate_stats(clip, v):
    c, k, p, eta = norm_to_phys(v)
    full = np.zeros(13)
    full[0], full[1] = c
    full[2:6] = k
    full[9:13] = p
    a = amat(eta)
    lo, hi = clip.xy.min(axis=0), clip.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 25), np.linspace(lo[1], hi[1], 25))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    det = F.jac_det(((grid - c) * a) + c, full, 0.0)
    mags = np.sqrt(np.abs(F.jac_det(((clip.xy - c) * a) + c, full, 0.0)))
    return float(det.min()), float(mags.max() / mags.min())


def fieldmax(clip, v):
    c, k, p, eta = norm_to_phys(v)
    u = (clip.xy - c) * amat(eta)
    return (float(np.linalg.norm(delta_r(u, k), axis=1).max()),
            float(np.linalg.norm(d_p(u, p), axis=1).max()))


# ------------------------------------------------------------------ fitting

def fit(clip, free, seeds, label=""):
    """free is the index list into the 11-vector; everything else is held at the seed value."""
    best = None
    basins = []
    for s0 in seeds:
        s0 = np.asarray(s0, float)

        def rr(w, s0=s0):
            v = s0.copy()
            v[free] = w
            return clip.resid_b(v)

        s0 = np.clip(s0, BLO, BHI)
        try:
            r = least_squares(rr, s0[free], method="trf", x_scale=1.0,
                              bounds=(BLO[free], BHI[free]),
                              ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
        except Exception:                                    # noqa: BLE001
            continue
        v = s0.copy()
        v[free] = r.x
        c = clip.sse(v)
        basins.append(c)
        if best is None or c < best[1]:
            best = (v, c, r)
    if best is None:
        return None
    v, c, r = best
    tol = max(1e-9, 1e-6 * c)
    nsame = sum(1 for b in basins if abs(b - c) <= tol)
    return {"v": v, "sse": c, "rms": math.sqrt(c / clip.n), "opt": float(r.optimality),
            "nfev": r.nfev, "njev": r.njev, "status": r.status, "msg": r.message.strip(),
            "nstarts": len(basins), "nsame": nsame,
            "basins": sorted(set(round(b, 6) for b in basins))[:6], "label": label}


def seedset(clip, base, free, nrand, rng, spread=0.4):
    out = [base.copy()]
    for _ in range(nrand):
        s = base.copy()
        s[free] = s[free] + rng.normal(0.0, spread, len(free))
        out.append(s)
    return out


def profile_eta(clip, vbest, free_nuis, grid):
    rows = []
    for e in grid:
        s0 = vbest.copy()
        s0[10] = e

        def rr(w, s0=s0):
            v = s0.copy()
            v[free_nuis] = w
            return clip.resid_b(v)
        s0 = np.clip(s0, BLO, BHI)
        r = least_squares(rr, s0[free_nuis], method="trf", x_scale=1.0,
                          bounds=(BLO[free_nuis], BHI[free_nuis]),
                          ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
        v = s0.copy()
        v[free_nuis] = r.x
        c, k, p, _ = norm_to_phys(v)
        rows.append((e, clip.sse(v), c[0], c[1], v[2], v[6]))
    return rows


def main():
    out = []

    def say(*a):
        line = " ".join(str(x) for x in a)
        print(line, flush=True)
        out.append(line)

    say("NORMALIZED REPARAMETERIZATION, OPTIMIZER RECOVERY, GAUGE QUOTIENT, RESIDUAL HARMONICS")
    say(f"Document 2015-09-04-1 Clearwater.vsd; clips 'Left Camera' and 'Right Camera'")
    say(f"Characteristic radius R = {R:.1f} px (the useful image radius; no prior calibration-")
    say(f"domain radius exists in the codebase). Frame {W:.0f} x {H:.0f}.")
    say("t = s/R^2, alpha_j = k_j R^(2j), q1 = p1 R, q2 = p2 R, q3 = p3 R^2, q4 = p4 R^4,")
    say("xi = (x0 - W/2)/R, ups = (y0 - H/2)/R. Optimized vector is")
    say("(xi, ups, alpha1..alpha4, q1..q4, eta), all nominally O(1); x_scale = 1.")
    say("Box bounds: centre offsets in [-0.25, +0.25] R, alpha and q in [-5, +5], eta in")
    say("[-0.05, +0.05]. A soft barrier enforces a positive Jacobian determinant. The gate's")
    say("scale-ratio test is reported but not imposed. An earlier unconstrained pass failed")
    say("completely and is described in the module docstring.")

    # ---------------- Stage 0: equivalence tests ----------------
    say("\n" + "=" * 96)
    say("STAGE 0  NUMERICAL EQUIVALENCE OF THE TWO PARAMETERIZATIONS")
    say("=" * 96)
    rng = np.random.default_rng(20260727)
    e_round, e_coord, e_obj, e_nest = 0.0, 0.0, 0.0, 0.0
    clipL = Clip("Left Camera")
    for _ in range(200):
        v = np.zeros(11)
        v[0] = rng.normal(0, 0.1); v[1] = rng.normal(0, 0.1)
        v[2:6] = rng.normal(0, 0.5, 4)
        v[6:10] = rng.normal(0, 0.2, 4)
        v[10] = rng.normal(0, 0.02)
        c, k, p, eta = norm_to_phys(v)
        e_round = max(e_round, float(np.abs(phys_to_norm(c, k, p, eta) - v).max()))
        x = np.stack([rng.uniform(0, W, 400), rng.uniform(0, H, 400)], axis=1)
        e_coord = max(e_coord, float(np.abs(Unorm(x, v) - Umap(x, c, k, p, eta)).max()))
        r1 = clipL.straight(Unorm(clipL.xy, v))
        r2 = clipL.straight(Umap(clipL.xy, c, k, p, eta))
        e_obj = max(e_obj, abs(float(r1 @ r1) - float(r2 @ r2)))
        v0 = v.copy(); v0[10] = 0.0
        c0, k0, p0, _ = norm_to_phys(v0)
        full = np.zeros(13); full[0], full[1] = c0; full[2:6] = k0; full[9:13] = p0
        e_nest = max(e_nest, float(np.abs(Unorm(x, v0) - F.undistort(x, full, 0.0)).max()))
    say(f"  200 random feasible parameter vectors, 400 random image locations each")
    say(f"  physical -> normalized -> physical round trip, max abs error : {e_round:.3e}")
    say(f"  corrected coordinates, both parameterizations, max abs diff  : {e_coord:.3e} px")
    say(f"  objective (SSE) equality, max abs difference                 : {e_obj:.3e}")
    say(f"  exact nesting at eta = 0 against the existing implementation : {e_nest:.3e} px")
    say("  Analytic Jacobians are not used; the optimizer takes finite differences, so no")
    say("  Jacobian equivalence test applies.")

    # ---------------- Stage 1: converged fits ----------------
    say("\n" + "=" * 96)
    say("STAGE 1  CONVERGED FITS, BOTH CLIPS")
    say("=" * 96)
    FREE0 = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    FREE1 = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    results = {}
    for name in ("Left Camera", "Right Camera"):
        clip = Clip(name) if name != "Left Camera" else clipL
        say(f"\n  --- {name}: {clip.nlines} lines, {clip.n} observations ---")
        base = np.zeros(11)
        base[0] = (clip.centre0[0] - W / 2) / R
        base[1] = (clip.centre0[1] - H / 2) / R
        rg = np.random.default_rng(7)
        t0 = time.time()
        m0 = fit(clip, FREE0, seedset(clip, base, FREE0, 23, rg), "M0")
        t_m0 = time.time() - t0
        s1 = [m0["v"].copy()] + seedset(clip, base, FREE1, 23, rg)
        for s in s1[1:]:
            s[10] = rg.normal(0, 0.02)
        t0 = time.time()
        m1 = fit(clip, FREE1, s1, "M1")
        t_m1 = time.time() - t0
        results[name] = (clip, m0, m1)
        for tag, m, tt in (("M0 baseline eta=0", m0, t_m0), ("M1 conjugated free eta", m1, t_m1)):
            c, k, p, eta = norm_to_phys(m["v"])
            mind, ratio = gate_stats(clip, m["v"])
            fr, fp = fieldmax(clip, m["v"])
            say(f"    {tag}")
            say(f"      RMS {m['rms']:.6f} px   SSE {m['sse']:.4f}   "
                f"scaled optimality {m['opt']:.3e}   status {m['status']}")
            say(f"      starts {m['nstarts']}, reaching this basin {m['nsame']}; "
                f"distinct basin SSEs seen {m['basins']}")
            say(f"      eta {eta:+.8f}  e_legacy {math.tanh(eta):+.8f}  "
                f"exp(2 eta) {math.exp(2*eta):.8f}")
            say(f"      centre ({c[0]:.4f}, {c[1]:.4f})   xi {m['v'][0]:+.6f}  "
                f"ups {m['v'][1]:+.6f}")
            say(f"      alpha {m['v'][2]:+.6f} {m['v'][3]:+.6f} {m['v'][4]:+.6f} {m['v'][5]:+.6f}")
            say(f"      q     {m['v'][6]:+.6f} {m['v'][7]:+.6f} {m['v'][8]:+.6f} {m['v'][9]:+.6f}")
            say(f"      k     {k[0]:+.6e} {k[1]:+.6e} {k[2]:+.6e} {k[3]:+.6e}")
            say(f"      p     {p[0]:+.6e} {p[1]:+.6e} {p[2]:+.6e} {p[3]:+.6e}")
            say(f"      max radial displacement {fr:.3f} px, max decentering {fp:.3f} px")
            say(f"      min Jacobian determinant {mind:+.5f}, gate scale ratio {ratio:.3f}"
                f"{'  (would FAIL the 4.0 gate)' if ratio >= 4.0 else ''}")
            at = [NORMNAMES[j] for j in (FREE1 if tag.startswith("M1") else FREE0)
                  if abs(m['v'][j] - BLO[j]) < 1e-7 or abs(m['v'][j] - BHI[j]) < 1e-7]
            say(f"      active bounds: {at if at else 'none'}")
            say(f"      nfev {m['nfev']}, njev {m['njev']}, runtime {tt:.0f}s")
        say(f"    L(M1) <= L(M0): {m1['sse'] <= m0['sse'] + 1e-9}  "
            f"({m1['sse']:.4f} vs {m0['sse']:.4f}); "
            f"RMS reduction {100*(1-m1['rms']/m0['rms']):+.2f}%")

    np.save("/tmp/normfit_results.npy",
            np.array([results[n][1]["v"] for n in results] +
                     [results[n][2]["v"] for n in results]))
    with open("/tmp/normfit_stage1.txt", "w") as fh:
        fh.write("\n".join(out))
    say("\n  (stage 1 written to /tmp/normfit_stage1.txt; fitted vectors to "
        "/tmp/normfit_results.npy)")

    # ---------------- eta profiles ----------------
    say("\n" + "=" * 96)
    say("STAGE 1b  ETA PROFILES (eta fixed on a grid, all nuisance parameters reoptimized)")
    say("=" * 96)
    for name in results:
        clip, m0, m1 = results[name]
        eh = norm_to_phys(m1["v"])[3]
        grid = np.array([-0.004, 0.0, 0.002, 0.004, 0.006, eh, 0.010, 0.012, 0.016, 0.020])
        grid = np.unique(np.round(grid, 8))
        say(f"\n  --- {name}, eta-hat {eh:+.6f} ---")
        say(f"    {'eta':>10} {'profiled SSE':>14} {'dSSE':>12} {'x0':>10} {'y0':>10} "
            f"{'alpha1':>10} {'q1':>10}")
        rows = profile_eta(clip, m1["v"], FREE0, grid)
        smin = min(r[1] for r in rows)
        for e, sse, x0, y0, a1, q1 in rows:
            mark = "  <- eta-hat" if abs(e - eh) < 1e-9 else ""
            say(f"    {e:+10.6f} {sse:14.4f} {sse-smin:12.4f} {x0:10.3f} {y0:10.3f} "
                f"{a1:10.5f} {q1:10.5f}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
