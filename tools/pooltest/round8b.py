#!/usr/bin/env python3
"""Sections 5 and 6 of the Tokina audit: synthetic recovery and the joint Left/Right diagnostic.

Section 5 needs the inverse of the centred Brown-Conrady map. A fixed-point iteration diverges at
this distortion strength, so Newton with the analytic 2x2 Jacobian is used and its accuracy is
reported. Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("suite4", os.path.join(HERE, "suite4.py"))
S = importlib.util.module_from_spec(_s); _s.loader.exec_module(S)
R, W, H, ETA, M, BLO, BHI = S.R, S.W, S.H, S.ETA, S.M, S.BLO, S.BHI
ALL = {r["tag"]: r for r in np.load("/tmp/round5.npy", allow_pickle=True)}
PATH = {l: p for l, p in S.SUITE}
FREE0 = np.array(M["M0_2p"]); FREE1 = np.array(M["M1_2p"])
TAGS = ["Tokina 10 mm / Left Camera", "Tokina 10 mm / Right Camera"]


def clip_for(tag):
    lens, cn = tag.split(" / ")
    return S.Clip(PATH[lens], cn)


def bc0(u, k, p):
    return u + S.delta_r(u, k) + S.d_p(u, p)


def bc0_jac(u, k, p):
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
    a = Rr + 2 * ux * ux * Rp + (6 * p[0] * ux + 2 * p[1] * uy) * T + 2 * ux * Gx * Tp
    b = 2 * ux * uy * Rp + (2 * p[0] * uy + 2 * p[1] * ux) * T + 2 * uy * Gx * Tp
    c = 2 * ux * uy * Rp + (2 * p[0] * uy + 2 * p[1] * ux) * T + 2 * ux * Gy * Tp
    d = Rr + 2 * uy * uy * Rp + (2 * p[0] * ux + 6 * p[1] * uy) * T + 2 * uy * Gy * Tp
    return a, b, c, d


def bc0_inv(t, k, p, iters=40):
    u = t.copy()
    for _ in range(iters):
        F = bc0(u, k, p) - t
        a, b, c, d = bc0_jac(u, k, p)
        det = a * d - b * c
        det = np.where(np.abs(det) < 1e-12, 1e-12, det)
        du = np.stack([(d * F[:, 0] - b * F[:, 1]) / det,
                       (-c * F[:, 0] + a * F[:, 1]) / det], axis=1)
        u = u - du
        if np.abs(du).max() < 1e-12:
            break
    return u


def fit_ls(clip, free, s0):
    s0 = np.clip(np.asarray(s0, float), BLO, BHI)

    def rr(w):
        v = s0.copy(); v[free] = w
        return clip.rb(v)
    r = least_squares(rr, s0[free], method="trf", x_scale=1.0, bounds=(BLO[free], BHI[free]),
                      ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
    v = s0.copy(); v[free] = r.x
    rr2 = clip.resid(v)
    return v, float(rr2 @ rr2)


def main():
    t0 = time.time()
    say = print
    clips = {t: clip_for(t) for t in TAGS}
    v1 = {t: np.array(ALL[t]["M1_2p"]["v"]) for t in TAGS}
    v0 = {t: np.array(ALL[t]["M0_2p"]["v"]) for t in TAGS}

    say("=" * 108)
    say("5  SYNTHETIC RECOVERY ON THE OBSERVED TOKINA 10 mm RIGHT GEOMETRY")
    say("=" * 108)
    clip = clips[TAGS[1]]
    c, k, p, _ = S.nphys(v1[TAGS[1]])
    U = S.Uv(clip.xy, v1[TAGS[1]])
    Y = U.copy()
    for li in range(clip.nlines):
        a, b = clip.starts[li], clip.starts[li] + clip.counts[li]
        P = U[a:b]
        cen = P.mean(axis=0); q = P - cen
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        dv = np.array([math.cos(th), math.sin(th)])
        Y[a:b] = cen + np.outer(q @ dv, dv)
    inv = bc0_inv(Y - c, k, p)
    say(f"    Newton inverse accuracy: max |B0(B0^-1(y)) - y| "
        f"{np.abs(bc0(inv, k, p) - (Y - c)).max():.3e} px")
    say(f"    truth construction: corrected points projected onto their own fitted lines, so the")
    say(f"    synthetic world is exactly straight by construction")
    rng = np.random.default_rng(31)
    rr = clip.resid(v1[TAGS[1]])
    NOISE = math.sqrt(float(rr @ rr) / (clip.n - 2 * clip.nlines))
    say(f"    matched noise from the Right clip itself: sqrt(SSE / (n - 2*nlines)) = "
        f"sqrt({float(rr @ rr):.4f} / ({clip.n} - 2*{clip.nlines})) = {NOISE:.4f} px")
    say(f"    replicate noise {NOISE:.4f} px per coordinate, independent per corner; the observed")
    say(f"    line/pass dependence is NOT reproduced, so dispersion below is a lower bound")
    say(f"\n    {'injected eta':>13} {'noiseless':>13} {'mean of 20':>12} {'sd':>10} "
        f"{'min':>11} {'max':>11} {'fails':>6}")
    for einj in (0.0, -0.0053, 0.008):
        am = S.amat(einj)
        Xs = c + bc0_inv((Y - c) * am, k, p) / am
        syn = S.Clip.__new__(S.Clip); syn.__dict__.update(clip.__dict__); syn.xy = Xs
        vv, _ = fit_ls(syn, FREE1, v0[TAGS[1]].copy())
        en = S.nphys(vv)[3]
        est, fails = [], 0
        for _ in range(20):
            s2 = S.Clip.__new__(S.Clip); s2.__dict__.update(clip.__dict__)
            s2.xy = Xs + rng.normal(0, NOISE, Xs.shape)
            try:
                v2, _ = fit_ls(s2, FREE1, v0[TAGS[1]].copy())
                est.append(S.nphys(v2)[3])
            except Exception:                                # noqa: BLE001
                fails += 1
        e = np.array(est)
        say(f"    {einj:+13.5f} {en:+13.7f} {e.mean():+12.7f} {e.std(ddof=1):10.7f} "
            f"{e.min():+11.7f} {e.max():+11.7f} {fails:6d}")
    say(f"\n    The separation between 0 and -0.0053 relative to the replicate dispersion above")
    say(f"    is the direct test of whether this geometry could tell them apart.")

    say("\n" + "=" * 108)
    say("6  JOINT LEFT/RIGHT DIAGNOSTIC, SEPARATE NUISANCE PARAMETERS")
    say("=" * 108)
    cL, cR = clips[TAGS[0]], clips[TAGS[1]]
    aL, aR = v1[TAGS[0]].copy(), v1[TAGS[1]].copy()
    nF = len(FREE0)

    def joint(mode):
        if mode == "zero":
            x0 = np.concatenate([aL[FREE0], aR[FREE0]])
            lo = np.concatenate([BLO[FREE0], BLO[FREE0]])
            hi = np.concatenate([BHI[FREE0], BHI[FREE0]])
        elif mode == "shared":
            x0 = np.concatenate([aL[FREE0], aR[FREE0], [0.5 * (aL[ETA] + aR[ETA])]])
            lo = np.concatenate([BLO[FREE0], BLO[FREE0], [BLO[ETA]]])
            hi = np.concatenate([BHI[FREE0], BHI[FREE0], [BHI[ETA]]])
        else:
            x0 = np.concatenate([aL[FREE0], aR[FREE0], [aL[ETA]], [aR[ETA]]])
            lo = np.concatenate([BLO[FREE0], BLO[FREE0], [BLO[ETA]], [BLO[ETA]]])
            hi = np.concatenate([BHI[FREE0], BHI[FREE0], [BHI[ETA]], [BHI[ETA]]])

        def unpack(x):
            a = aL.copy(); a[FREE0] = x[:nF]
            b = aR.copy(); b[FREE0] = x[nF:2 * nF]
            if mode == "zero":
                a[ETA] = b[ETA] = 0.0
            elif mode == "shared":
                a[ETA] = b[ETA] = x[2 * nF]
            else:
                a[ETA] = x[2 * nF]; b[ETA] = x[2 * nF + 1]
            return a, b

        def rr(x):
            a, b = unpack(x)
            return np.concatenate([cL.rb(a), cR.rb(b)])
        r = least_squares(rr, np.clip(x0, lo, hi), method="trf", x_scale=1.0, bounds=(lo, hi),
                          ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
        a, b = unpack(r.x)
        ra, rb = cL.resid(a), cR.resid(b)
        return float(ra @ ra), float(rb @ rb), S.nphys(a)[3], S.nphys(b)[3]
    say(f"    {'model':24} {'SSE Left':>11} {'SSE Right':>11} {'total':>11} "
        f"{'eta L':>11} {'eta R':>11}")
    tot = {}
    for mode, lbl in (("zero", "eta_L = eta_R = 0"), ("shared", "one shared eta"),
                      ("sep", "separate eta_L, eta_R")):
        sl, sr, el, er = joint(mode)
        tot[mode] = (sl, sr, sl + sr)
        say(f"    {lbl:24} {sl:11.5f} {sr:11.5f} {sl + sr:11.5f} {el:+11.7f} {er:+11.7f}")
    say(f"\n    total penalty, shared versus separate {tot['shared'][2] - tot['sep'][2]:10.5f} SSE")
    say(f"    total penalty, zero versus separate   {tot['zero'][2] - tot['sep'][2]:10.5f} SSE")
    say(f"    total penalty, zero versus shared     {tot['zero'][2] - tot['shared'][2]:10.5f} SSE")
    say(f"    clip-specific cost of the shared solution: Left "
        f"{tot['shared'][0] - tot['sep'][0]:+.5f}, Right {tot['shared'][1] - tot['sep'][1]:+.5f}")
    say(f"\n  runtime {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
