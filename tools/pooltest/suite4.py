#!/usr/bin/env python3
"""Heterogeneous four-document suite: does the conjugated axis-locked anisotropy hold up?

Documents, lenses, and the exact filenames located on disk:
  Rokinon 8 mm fisheye  2015-09-04-1 Clearwater.vsd
  Tokina zoom at 10 mm  2015-07-16-2 Panguingue.vsd
  Tokina zoom at 17 mm  2016-08-02-2 Clearwater.vsd   (note the zero-padded month and day)
  Sony Handycam, low distortion
                        2012-01-31_PoolTest_2026_Reanalysis.vsd

Parameter vector is always length 14: xi, ups, alpha1..alpha7, q1..q4, eta, with unused alphas
held at zero. q3 and q4 bounds are widened to +/- 10 so the previously observed Clearwater Right
optimum near q3 = -6.1 lies in the interior; that change makes the Rokinon fits worth recomputing
rather than reused, so all eight clips are fitted under identical settings.

Clips are processed in parallel, one worker per clip, each writing its own log so progress is
visible. Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
PT = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
      "2012-01-31_PoolTest")
SUITE = [
    ("Rokinon 8 mm", os.path.join(DM, "2015-09-04-1 Clearwater.vsd")),
    ("Tokina 10 mm", os.path.join(DM, "2015-07-16-2 Panguingue.vsd")),
    ("Tokina 17 mm", os.path.join(DM, "2016-08-02-2 Clearwater.vsd")),
    ("Sony Handycam", os.path.join(PT, "2012-01-31_PoolTest_2026_Reanalysis.vsd")),
]
W, H, R = 1920.0, 1080.0, 1040.0
XI, UPS, A1, Q1, ETA = 0, 1, 2, 9, 13
M = {"M0_2p": [0, 1, 2, 3, 4, 5, 9, 10],
     "M1_2p": [0, 1, 2, 3, 4, 5, 9, 10, 13],
     "M0_4p": [0, 1, 2, 3, 4, 5, 9, 10, 11, 12],
     "M1_4p": [0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13],
     "M1_2p_k7": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13]}
BLO = np.array([-.25, -.25] + [-5.] * 7 + [-5., -5., -10., -10.] + [-0.05])
BHI = np.array([+.25, +.25] + [+5.] * 7 + [+5., +5., +10., +10.] + [+0.05])
NAMES = ["xi", "ups"] + [f"a{j}" for j in range(1, 8)] + ["q1", "q2", "q3", "q4", "eta"]


def nphys(v):
    c = np.array([v[0] * R + W / 2, v[1] * R + H / 2])
    k = np.array([v[1 + j] / R ** (2 * j) for j in range(1, 8)])
    p = np.array([v[9] / R, v[10] / R, v[11] / R ** 2, v[12] / R ** 4])
    return c, k, p, v[13]


def delta_r(u, k):
    s = u[:, 0] ** 2 + u[:, 1] ** 2
    Rr = np.zeros_like(s); sp = np.ones_like(s)
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


def amat(e):
    return np.array([math.exp(e), math.exp(-e)])


def Umap(x, c, k, p, e):
    a = amat(e)
    u = (x - c) * a
    return c + (u + delta_r(u, k) + d_p(u, p)) / a


def Uv(x, v):
    return Umap(x, *nphys(v))


def jdet(x, c, k, p, e):
    a = amat(e)
    u = (x - c) * a
    ux, uy = u[:, 0], u[:, 1]
    s = ux * ux + uy * uy
    Rr = np.ones_like(s); Rp = np.zeros_like(s)
    for i, ki in enumerate(k, start=1):
        Rr = Rr + ki * s ** i
        Rp = Rp + i * ki * s ** (i - 1)
    T = 1 + p[2] * s + p[3] * s * s
    Tp = p[2] + 2 * p[3] * s
    Gx = p[0] * (3 * ux * ux + uy * uy) + 2 * p[1] * ux * uy
    Gy = 2 * p[0] * ux * uy + p[1] * (ux * ux + 3 * uy * uy)
    aa = Rr + 2 * ux * ux * Rp + (6 * p[0] * ux + 2 * p[1] * uy) * T + 2 * ux * Gx * Tp
    bb = 2 * ux * uy * Rp + (2 * p[0] * uy + 2 * p[1] * ux) * T + 2 * uy * Gx * Tp
    cc = 2 * ux * uy * Rp + (2 * p[0] * uy + 2 * p[1] * ux) * T + 2 * ux * Gy * Tp
    dd = Rr + 2 * uy * uy * Rp + (2 * p[0] * ux + 6 * p[1] * uy) * T + 2 * uy * Gy * Tp
    return aa * dd - bb * cc


class Clip:
    def __init__(self, path, name):
        spec = importlib.util.spec_from_file_location("fitter", os.path.join(HERE, "fitter.py"))
        F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)
        centre0, stored, sets = F.load(path, name)
        self.lines = [Lg for tc in sorted(sets) for Lg in sets[tc]]
        self.ntc = len(sets)
        self.lineset = {i: Lg for i, Lg in enumerate(self.lines)}
        self.xy = np.concatenate([np.asarray(Lg, float) for Lg in self.lines], axis=0)
        n = np.array([len(Lg) for Lg in self.lines])
        self.counts, self.n, self.nlines = n, len(self.xy), len(self.lines)
        self.starts = np.concatenate([[0], np.cumsum(n)[:-1]])
        self.centre0 = np.array(centre0)
        lo, hi = self.xy.min(axis=0), self.xy.max(axis=0)
        gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 50), np.linspace(lo[1], hi[1], 34))
        g = np.stack([gx.ravel(), gy.ravel()], axis=1)
        cc = 0.5 * (lo + hi)
        self.grid = g[np.hypot(g[:, 0] - cc[0], g[:, 1] - cc[1]) <= 0.5 * np.hypot(*(hi - lo))]

    def straight(self, pts):
        cx = np.add.reduceat(pts[:, 0], self.starts) / self.counts
        cy = np.add.reduceat(pts[:, 1], self.starts) / self.counts
        qx = pts[:, 0] - np.repeat(cx, self.counts)
        qy = pts[:, 1] - np.repeat(cy, self.counts)
        sxy = np.add.reduceat(qx * qy, self.starts)
        sd = np.add.reduceat(qx * qx - qy * qy, self.starts)
        th = 0.5 * np.arctan2(2.0 * sxy, sd)
        return -qx * np.repeat(np.sin(th), self.counts) + qy * np.repeat(np.cos(th), self.counts)

    def barrier(self, v):
        c, k, p, e = nphys(v)
        lo, hi = self.xy.min(axis=0), self.xy.max(axis=0)
        gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 13), np.linspace(lo[1], hi[1], 13))
        g = np.stack([gx.ravel(), gy.ravel()], axis=1)
        return np.array([200.0 * math.sqrt(self.n) * max(0.0, 0.05 - float(jdet(g, c, k, p, e).min()))])

    def resid(self, v):
        return self.straight(Uv(self.xy, v))

    def rb(self, v):
        return np.concatenate([self.resid(v), self.barrier(v)])

    def sse(self, v):
        r = self.resid(v)
        return float(r @ r)


def fit1(clip, free, s0):
    s0 = np.clip(np.asarray(s0, float), BLO, BHI)

    def rr(w):
        v = s0.copy(); v[free] = w
        return clip.rb(v)
    try:
        r = least_squares(rr, s0[free], method="trf", x_scale=1.0, bounds=(BLO[free], BHI[free]),
                          ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20000)
    except Exception:                                       # noqa: BLE001
        return None
    v = s0.copy(); v[free] = r.x
    return v, clip.sse(v), float(r.optimality)


def fitm(clip, free, base, rng, maxstart=6, spread=0.3):
    """Stop once two materially different starts agree on an admissible basin."""
    free = np.array(free)
    best, sses, hits = None, [], 0
    for i in range(maxstart):
        s = base.copy()
        if i:
            s[free] = s[free] + rng.normal(0, spread, len(free))
        got = fit1(clip, free, s)
        if got is None:
            continue
        v, c, o = got
        sses.append(c)
        if best is None or c < best[1] - 1e-9:
            best, hits = (v, c, o), 1
        elif abs(c - best[1]) <= max(1e-9, 1e-6 * best[1]):
            hits += 1
        if hits >= 2 and i >= 2:
            break
    v, c, o = best
    return {"v": v, "sse": c, "rms": math.sqrt(c / clip.n), "opt": o,
            "nsame": sum(1 for x in sses if abs(x - c) <= max(1e-9, 1e-6 * c)),
            "nstart": len(sses), "free": free}


def svcond(clip, v, free):
    eps = 1e-6
    J = []
    for j in free:
        a = v.copy(); a[j] += eps
        b = v.copy(); b[j] -= eps
        J.append((clip.resid(a) - clip.resid(b)) / (2 * eps))
    sv = np.linalg.svd(np.array(J).T, compute_uv=False)
    return sv, float(sv[0] / sv[-1])


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
    sc = np.abs(src).max(); h0 = np.concatenate([aff, [0., 0.]])

    def res(h):
        w = (h[6] * src[:, 0] + h[7] * src[:, 1]) / sc + 1.0
        return np.concatenate([(h[0]*src[:,0]+h[1]*src[:,1]+h[2])/w - tgt[:,0],
                               (h[3]*src[:,0]+h[4]*src[:,1]+h[5])/w - tgt[:,1]])
    r = least_squares(res, h0, method="lm", xtol=1e-14, ftol=1e-14, max_nfev=8000)
    h = r.x
    w = (h[6] * src[:, 0] + h[7] * src[:, 1]) / sc + 1.0
    pred = np.stack([(h[0]*src[:,0]+h[1]*src[:,1]+h[2])/w,
                     (h[3]*src[:,0]+h[4]*src[:,1]+h[5])/w], axis=1)
    return tgt - pred


# ---------------- harmonics ----------------
def rbasis(r):
    t = (r / R) ** 2
    return np.stack([np.ones_like(r), r, r * t, r * t ** 2, r * t ** 3, r * t ** 4], axis=1)


def harm(pos, vec, cref, rrefs, mmax=4):
    d = pos - cref
    rr = np.hypot(d[:, 0], d[:, 1])
    keep = (rr > 150.0) & np.isfinite(vec[:, 0])
    d, rr, v = d[keep], rr[keep], vec[keep]
    phi = np.arctan2(d[:, 1], d[:, 0])
    rad = (v[:, 0] * d[:, 0] + v[:, 1] * d[:, 1]) / rr
    tan = (-v[:, 0] * d[:, 1] + v[:, 1] * d[:, 0]) / rr
    B = rbasis(rr); nb = B.shape[1]
    cols = [B]
    for m in range(1, mmax + 1):
        cols.append(B * np.cos(m * phi)[:, None]); cols.append(B * np.sin(m * phi)[:, None])
    X = np.concatenate(cols, axis=1)
    sv = np.linalg.svd(X, compute_uv=False)
    out = {}
    for nm, y in (("rad", rad), ("tan", tan)):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        for m in (1, 2, 3):
            i = nb * (1 + 2 * (m - 1))
            for r0 in rrefs:
                bb = rbasis(np.array([r0]))[0]
                cc = float(beta[i:i+nb] @ bb); ss = float(beta[i+nb:i+2*nb] @ bb)
                out[(nm, m, r0)] = (cc, ss, math.hypot(cc, ss), math.degrees(math.atan2(ss, cc)))
    return out, float(sv[0] / sv[-1]), int(keep.sum())


def pairs_of(clip, v):
    L = {i: np.asarray(q, float) for i, q in clip.lineset.items() if len(q) >= 4}
    fits = {}
    for i, pts in L.items():
        u = Uv(pts, v); q = u - u.mean(axis=0)
        th = 0.5*math.atan2(2*float(q[:,0]@q[:,1]), float(q[:,0]@q[:,0]-q[:,1]@q[:,1]))
        fits[i] = (np.array([math.cos(th), math.sin(th)]),
                   -q[:,0]*math.sin(th) + q[:,1]*math.cos(th))
    angs = {i: math.degrees(math.atan2(dd[1], dd[0])) % 180 for i, (dd, _) in fits.items()}
    ref = sorted(angs.values())[len(angs)//2]
    fam = {i: 0 if min(abs(a-ref), 180-abs(a-ref)) < 45 else 1 for i, a in angs.items()}
    idx = {}
    for i, pts in L.items():
        if fam[i] == 0:
            for j, q in enumerate(pts):
                idx[(round(q[0],3), round(q[1],3))] = (i, j)
    pr = []
    for ib, pts in L.items():
        if fam[ib] != 1:
            continue
        for jb, q in enumerate(pts):
            hit = idx.get((round(q[0],3), round(q[1],3)))
            if hit:
                pr.append((hit[0], hit[1], ib, jb, q[0], q[1]))
    return L, fam, angs, pr


def rfield(clip, v, pr):
    L = {i: np.asarray(q, float) for i, q in clip.lineset.items() if len(q) >= 4}
    fits = {}
    for i, pts in L.items():
        u = Uv(pts, v); q = u - u.mean(axis=0)
        th = 0.5*math.atan2(2*float(q[:,0]@q[:,1]), float(q[:,0]@q[:,0]-q[:,1]@q[:,1]))
        dd = np.array([math.cos(th), math.sin(th)])
        fits[i] = (dd, -q[:,0]*dd[1] + q[:,1]*dd[0])
    out = []
    for ia, ja, ib, jb, px, py in pr:
        ua, ub = fits[ia][0], fits[ib][0]
        na = np.array([-ua[1], ua[0]]); nb = np.array([-ub[1], ub[0]])
        det = na[0]*nb[1] - na[1]*nb[0]
        if abs(det) < 0.25:
            out.append((np.nan, np.nan)); continue
        ra, rb = fits[ia][1][ja], fits[ib][1][jb]
        out.append(((ra*nb[1]-rb*na[1])/det, (na[0]*rb-nb[0]*ra)/det))
    return np.asarray(out)


def do_clip(job):
    lens, path, cname = job
    tag = f"{lens} / {os.path.basename(path)} / {cname}"
    out = []
    say = out.append
    t0 = time.time()
    clip = Clip(path, cname)
    rng = np.random.default_rng(17)
    base = np.zeros(14)
    base[0] = (clip.centre0[0] - W/2) / R
    base[1] = (clip.centre0[1] - H/2) / R

    say(f"\n{'='*104}\n{tag}\n{'='*104}")
    say(f"  frame 1920x1080, R = {R:.0f} px; {clip.nlines} lines, {clip.n} observations, "
        f"{clip.ntc} timecode(s)")

    # ---- Stage 6 geometry (cheap, do first) ----
    L, fam, angs, pr = pairs_of(clip, base)
    a0 = np.array([angs[i] for i in L if fam[i] == 0])
    a1 = np.array([angs[i] for i in L if fam[i] == 1])

    def cmed(a):
        z = np.exp(2j * np.radians(a))
        return math.degrees(np.angle(z.mean())) / 2 % 180
    m0, m1 = cmed(a0), (cmed(a1) if len(a1) else float("nan"))
    sep = abs(m0 - m1)
    sep = min(sep, 180 - sep)
    ln = np.array([float(np.linalg.norm(np.asarray(q)[-1] - np.asarray(q)[0]))
                   for q in clip.lines])
    d = clip.xy - np.array([W/2, H/2]); rr = np.hypot(d[:,0], d[:,1])
    say(f"  GEOMETRY: family A median {m0:.1f} deg (n={len(a0)}), family B {m1:.1f} deg "
        f"(n={len(a1)}), circular separation mod 180 = {sep:.1f} deg")
    say(f"    line length median {np.median(ln):.0f} px, 90th pct {np.percentile(ln,90):.0f}; "
        f"corner radius median {np.median(rr):.0f} px, 90th pct {np.percentile(rr,90):.0f}")
    say(f"    multiple timecodes combined: {'YES' if clip.ntc > 1 else 'no'}")
    r60, r80 = float(np.percentile(rr, 60)), float(np.percentile(rr, 80))

    # ---- Stage 1 fits ----
    res = {}
    res["M0_2p"] = fitm(clip, M["M0_2p"], base, rng)
    b = res["M0_2p"]["v"].copy(); b[ETA] = 0.0
    res["M1_2p"] = fitm(clip, M["M1_2p"], b, rng)
    b4 = res["M0_2p"]["v"].copy(); b4[11] = b4[12] = 0.0
    res["M0_4p"] = fitm(clip, M["M0_4p"], b4, rng)
    b4a = res["M1_2p"]["v"].copy(); b4a[11] = b4a[12] = 0.0
    res["M1_4p"] = fitm(clip, M["M1_4p"], b4a, rng)

    for nm in ("M0_2p", "M1_2p", "M0_4p", "M1_4p"):
        r = res[nm]
        c, k, p, e = nphys(r["v"])
        sv, cond = svcond(clip, r["v"], r["free"])
        u = (clip.grid - c) * amat(e)
        mr = float(np.linalg.norm(delta_r(u, k), axis=1).max())
        mp = float(np.linalg.norm(d_p(u, p), axis=1).max())
        dj = jdet(clip.grid, c, k, p, e)
        mg = np.sqrt(np.abs(dj))
        ab = [NAMES[j] for j in r["free"]
              if abs(r["v"][j]-BLO[j]) < 1e-7 or abs(r["v"][j]-BHI[j]) < 1e-7]
        base_nm = "M0_2p" if nm.endswith("2p") else "M0_4p"
        red = (100*(1-r["rms"]/res[base_nm]["rms"]) if nm.startswith("M1") else 0.0)
        redsse = (100*(1-r["sse"]/res[base_nm]["sse"]) if nm.startswith("M1") else 0.0)
        say(f"  {nm}: RMS {r['rms']:.6f}  SSE {r['sse']:.4f}" +
            (f"  RMSred {red:+.2f}%  SSEred {redsse:+.2f}%" if nm.startswith("M1") else ""))
        if nm.startswith("M1"):
            say(f"    eta {e:+.7f}  e_legacy {math.tanh(e):+.7f}  exp(2eta) {math.exp(2*e):.7f}")
        say(f"    centre ({c[0]:.2f},{c[1]:.2f})  alpha " +
            " ".join(f"{r['v'][2+j]:+.5f}" for j in range(4)) +
            "  q " + " ".join(f"{r['v'][9+j]:+.5f}" for j in range(4)))
        say(f"    max radial {mr:.1f} px, max decentering {mp:.2f} px, min det {dj.min():+.4f}, "
            f"scale ratio {mg.max()/mg.min():.3f}")
        say(f"    condition {cond:.3e}, optimality {r['opt']:.2e}, "
            f"starts {r['nsame']}/{r['nstart']}, active bounds {ab if ab else 'none'}")
        if nm.startswith("M1"):
            ok = r["sse"] <= res[base_nm]["sse"] + 1e-9
            say(f"    nesting L(M1)<=L(M0): {ok}")

    # ---- Stage 2 eta scan on M1_2p ----
    eh = res["M1_2p"]["v"][ETA]
    grid = sorted(set([0.0] + [round(eh + dd, 6) for dd in (-0.006, -0.003, 0, 0.003, 0.006)]))
    grid = [g for g in grid if -0.05 <= g <= 0.05]
    scan = []
    for g in grid:
        bestc = None
        for seed in (res["M1_2p"]["v"], res["M0_2p"]["v"]):
            s = seed.copy(); s[ETA] = g
            got = fit1(clip, np.array(M["M0_2p"]), s)
            if got and (bestc is None or got[1] < bestc):
                bestc = got[1]
        scan.append((g, bestc))
    smin = min(s[1] for s in scan)
    say(f"  ETA SCAN (M1_2p, nuisance reoptimized at fixed eta):")
    for g, c in scan:
        say(f"    eta {g:+.6f}  SSE {c:12.4f}  excess {c-smin:+11.4f}"
            + ("   <- free optimum" if abs(g-eh) < 1e-9 else "")
            + ("   <- zero" if abs(g) < 1e-12 else ""))
    z = [c for g, c in scan if abs(g) < 1e-12][0]
    near = [(g, c) for g, c in scan if abs(g - eh) <= 0.0031]
    if len(near) >= 3:
        gg = np.array([x[0] for x in near]); cc = np.array([x[1] for x in near])
        curv = float(np.polyfit(gg, cc, 2)[0] * 2)
    else:
        curv = float("nan")
    say(f"    excess at eta=0: {z-smin:.4f} SSE ({100*(z-smin)/max(smin,1e-9):.2f}% of minimum); "
        f"local curvature d2SSE/deta2 {curv:.4e}, per observation {curv/clip.n:.4e}")

    # ---- Stage 3 diagnostics ----
    v1 = res["M1_2p"]["v"]; c, k, p, e = nphys(v1)
    u = (clip.grid - c) * amat(e)
    dr = np.linalg.norm(delta_r(u, k), axis=1)
    mg = np.sqrt(np.abs(jdet(clip.grid, c, k, p, e)))
    v0 = v1.copy(); v0[ETA] = 0.0
    UA = Uv(clip.grid, v1); U0 = Uv(clip.grid, v0)
    dv = UA - U0
    da = align(U0, UA, "affine"); dh = align(U0, UA, "homog")
    dsse = res["M0_2p"]["sse"] - res["M1_2p"]["sse"]
    say(f"  DISTORTION-STRENGTH AND LEVERAGE DIAGNOSTICS (best M1_2p, area-uniform grid "
        f"{len(clip.grid)} pts)")
    say(f"    symmetric radial correction: rms {np.sqrt((dr**2).mean()):.2f} px "
        f"({np.sqrt((dr**2).mean())/R:.4f} R), max {dr.max():.2f} px ({dr.max()/R:.4f} R)")
    say(f"    radial scale variation over domain (sqrt det J): {mg.min():.3f} to {mg.max():.3f}, "
        f"ratio {mg.max()/mg.min():.3f}")
    say(f"    direct anisotropy |U_eta - U_0| rms {np.sqrt((dv**2).sum(1).mean()):.4f} px, "
        f"after affine {np.sqrt((da**2).sum(1).mean()):.4f}, "
        f"after homography {np.sqrt((dh**2).sum(1).mean()):.4f}")
    say(f"    profile curvature per observation {curv/clip.n:.4e}; "
        f"SSE improvement per observation {dsse/clip.n:.5f} px^2")

    # ---- Stage 4 k1..k7 ----
    s7 = res["M1_2p"]["v"].copy()
    r7 = fitm(clip, M["M1_2p_k7"], s7, rng, maxstart=2, spread=0.15)
    c7, k7, p7, e7 = nphys(r7["v"])
    sv7, cond7 = svcond(clip, r7["v"], r7["free"])
    dj7 = jdet(clip.grid, c7, k7, p7, e7)
    ab7 = [NAMES[j] for j in r7["free"]
           if abs(r7["v"][j]-BLO[j]) < 1e-7 or abs(r7["v"][j]-BHI[j]) < 1e-7]
    say(f"  RADIAL-ORDER SENSITIVITY k1..k7 + p1,p2 + eta (warm start + 1 perturbed)")
    say(f"    SSE {r7['sse']:.4f} vs k1..k4 {res['M1_2p']['sse']:.4f} "
        f"({100*(1-r7['sse']/res['M1_2p']['sse']):+.2f}%), RMS {r7['rms']:.6f}")
    say(f"    eta {e7:+.7f} vs {eh:+.7f}, change {e7-eh:+.7f} "
        f"({100*(e7-eh)/eh if eh else float('nan'):+.2f}%)")
    say(f"    added a5,a6,a7 " + " ".join(f"{r7['v'][6+j]:+.5f}" for j in range(3)) +
        f"; condition {cond7:.3e}; min det {dj7.min():+.4f}; "
        f"bounds {ab7 if ab7 else 'none'}; starts {r7['nsame']}/{r7['nstart']}")
    say(f"    nesting SSE(k7) <= SSE(k4): {r7['sse'] <= res['M1_2p']['sse'] + 1e-9}")

    # ---- Stage 5 harmonics ----
    say(f"  HARMONICS at 60th/80th percentile corner radius ({r60:.0f}/{r80:.0f} px)")
    for nm in ("M1_2p", "M1_4p"):
        v1 = res[nm]["v"]; v0 = res["M0_2p" if nm.endswith("2p") else "M0_4p"]["v"]
        c1 = nphys(v1)[0]
        _, _, _, prb = pairs_of(clip, v0)
        if len(prb) < 80:
            say(f"    {nm}: only {len(prb)} paired corners, skipped")
            continue
        pos = np.array([[q[4], q[5]] for q in prb])
        ck, kk, pk, ek = nphys(v1)
        a = amat(ek)
        dAr = delta_r((pos - ck) * a, kk) / a - delta_r(pos - ck, kk)
        hv, cnd, nk = harm(pos, dAr, c1, (r60, r80))
        odd = hv[("rad",1,r60)][2] + hv[("rad",3,r60)][2]
        ev = max(hv[("rad",2,r60)][2], 1e-12)
        tmax = max(abs(hv[("tan",m,rx)][2]) for m in (1,2,3) for rx in (r60, r80))
        okv = odd/ev < 0.02 and tmax < 1e-3
        say(f"    {nm}: validation on Delta_A,r odd/even {odd/ev:.4f}, max|tan| {tmax:.1e}, "
            f"design condition {cnd:.2e}, n {nk} -> {'PASS' if okv else 'FAIL'}")
        hb, _, _ = harm(pos, rfield(clip, v0, prb), c1, (r60, r80))
        hf, _, _ = harm(pos, rfield(clip, v1, prb), c1, (r60, r80))
        for rx in (r60, r80):
            b2, f2 = hb[("rad",2,rx)], hf[("rad",2,rx)]
            say(f"      r={rx:.0f}: m2 baseline {b2[2]:7.4f} ph {b2[3]:+7.1f} -> final "
                f"{f2[2]:7.4f} ph {f2[3]:+7.1f}  ({100*(1-f2[2]/max(b2[2],1e-12)):+6.1f}%)")
        if okv:
            for rx in (r60,):
                say(f"      r={rx:.0f}: final radial m1 {hf[('rad',1,rx)][2]:.4f}, "
                    f"m3 {hf[('rad',3,rx)][2]:.4f}; tangential m1 {hf[('tan',1,rx)][2]:.4f}, "
                    f"m3 {hf[('tan',3,rx)][2]:.4f}")
    say(f"  [{time.time()-t0:.0f}s]")
    txt = "\n".join(out)
    with open(f"/tmp/suite4_{abs(hash(tag))%100000}.log", "w") as fh:
        fh.write(txt)
    return tag, txt


def main():
    jobs = []
    for lens, path in SUITE:
        import sqlite3
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        for (cn,) in db.execute(
                "SELECT v.ZCLIPNAME FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v "
                "ON v.Z_PK=c.ZVIDEOCLIP ORDER BY v.ZCLIPNAME"):
            jobs.append((lens, path, cn))
        db.close()
    print(f"{len(jobs)} clips queued across {len(SUITE)} documents", flush=True)
    with ProcessPoolExecutor(max_workers=8) as ex:
        for tag, txt in ex.map(do_clip, jobs):
            print(txt, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
