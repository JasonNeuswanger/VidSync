#!/usr/bin/env python3
"""Optimizer and identifiability audit of the Tokina 10 mm pair (2015-07-16-2 Panguingue.vsd).

Sections 1-6 of the audit. Model is k1..k4 + p1,p2 + eta in the conjugated map. Run with
~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares, minimize

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("suite4", os.path.join(HERE, "suite4.py"))
S = importlib.util.module_from_spec(_s); _s.loader.exec_module(S)
R, W, H, ETA, M, BLO, BHI, NAMES = S.R, S.W, S.H, S.ETA, S.M, S.BLO, S.BHI, S.NAMES
ALL = {r["tag"]: r for r in np.load("/tmp/round5.npy", allow_pickle=True)}
PATH = {l: p for l, p in S.SUITE}
FREE0 = np.array(M["M0_2p"])          # xi,ups,a1..a4,q1,q2
FREE1 = np.array(M["M1_2p"])          # + eta
TAGS = ["Tokina 10 mm / Left Camera", "Tokina 10 mm / Right Camera"]


def clip_for(tag):
    lens, cn = tag.split(" / ")
    return S.Clip(PATH[lens], cn)


def sse_of(clip, v):
    """Independent re-evaluation from the parameter vector, not the optimizer's stored value."""
    r = clip.resid(np.asarray(v, float))
    return float(r @ r)


def fit_ls(clip, free, s0):
    s0 = np.clip(np.asarray(s0, float), BLO, BHI)

    def rr(w):
        v = s0.copy(); v[free] = w
        return clip.rb(v)
    r = least_squares(rr, s0[free], method="trf", x_scale=1.0, bounds=(BLO[free], BHI[free]),
                      ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
    v = s0.copy(); v[free] = r.x
    return v, sse_of(clip, v), float(r.optimality), r.status, r.nfev


def fit_lbfgs(clip, free, s0):
    s0 = np.clip(np.asarray(s0, float), BLO, BHI)

    def f(w):
        v = s0.copy(); v[free] = w
        rb = clip.rb(v)
        return float(rb @ rb)
    r = minimize(f, s0[free], method="L-BFGS-B",
                 bounds=list(zip(BLO[free], BHI[free])),
                 options={"maxiter": 40000, "maxfun": 60000, "ftol": 1e-18, "gtol": 1e-14})
    v = s0.copy(); v[free] = r.x
    return v, sse_of(clip, v), float(np.max(np.abs(r.jac))), r.status, r.nfev


def jac(clip, v, free, h=1e-6):
    J = []
    for j in free:
        a = v.copy(); a[j] += h
        b = v.copy(); b[j] -= h
        J.append((clip.resid(a) - clip.resid(b)) / (2 * h))
    return np.array(J).T


def main():
    say = print
    t0 = time.time()
    clips = {t: clip_for(t) for t in TAGS}

    # ---------------- 1. nesting and reproduction ----------------
    say("=" * 108)
    say("1  NESTING CHECK AND INDEPENDENT REPRODUCTION OF THE TOKINA 10 mm FITS")
    say("=" * 108)
    base = {}
    for tag in TAGS:
        clip = clips[tag]
        v0 = np.array(ALL[tag]["M0_2p"]["v"]); v1 = np.array(ALL[tag]["M1_2p"]["v"])
        s0 = v0.copy(); s0[ETA] = 0.0
        emb = sse_of(clip, s0)
        map0 = S.Uv(clip.xy, v0); mape = S.Uv(clip.xy, s0)
        J1 = jac(clip, v1, FREE1)
        sv = np.linalg.svd(J1, compute_uv=False)
        JT = J1.T @ J1
        Cv = np.linalg.pinv(JT)
        dg = np.sqrt(np.diag(Cv))
        corr = Cv / np.outer(dg, dg)
        ie = list(FREE1).index(ETA)
        pc = sorted(((abs(corr[ie, k]), NAMES[FREE1[k]]) for k in range(len(FREE1))
                     if k != ie), reverse=True)
        say(f"\n  {tag}   {clip.nlines} lines, {clip.n} observations")
        for nm, v in (("M0", v0), ("M1", v1)):
            c, k, p, e = S.nphys(v)
            fr = FREE0 if nm == "M0" else FREE1
            vv, s_, opt, st, nf = fit_ls(clip, fr, v)
            ab = [NAMES[j] for j in fr if abs(v[j]-BLO[j]) < 1e-7 or abs(v[j]-BHI[j]) < 1e-7]
            Jn = jac(clip, v, fr)
            svn = np.linalg.svd(Jn, compute_uv=False)
            say(f"    {nm}: stored SSE {ALL[tag][nm+'_2p']['sse']:.6f}, independently "
                f"re-evaluated {sse_of(clip, v):.6f}, RMS {math.sqrt(sse_of(clip,v)/clip.n):.6f}")
            say(f"       eta {e:+.7f}; xi {v[0]:+.6f} ups {v[1]:+.6f}; alpha " +
                " ".join(f"{v[2+j]:+.5f}" for j in range(4)) +
                f"; q1 {v[9]:+.5f} q2 {v[10]:+.5f}")
            say(f"       re-optimizing from itself gives {s_:.6f} (change {s_-sse_of(clip,v):+.2e}), "
                f"first-order optimality {opt:.3e}, status {st}")
            say(f"       active bounds {ab if ab else 'none'}; Jacobian condition "
                f"{svn[0]/svn[-1]:.3e}; smallest sv {svn[-1]:.4e}")
        say(f"    embedded M0 at eta=0 inside M1: SSE {emb:.10f} vs M0 {sse_of(clip,v0):.10f}, "
            f"difference {abs(emb-sse_of(clip,v0)):.2e}; max map difference "
            f"{np.abs(map0-mape).max():.2e} px")
        say(f"    M1 objective {sse_of(clip,v1):.6f} <= M0 {sse_of(clip,v0):.6f}: "
            f"{sse_of(clip,v1) <= sse_of(clip,v0)+1e-9}")
        say(f"    strongest parameter correlations with eta: " +
            ", ".join(f"{n} {c:.3f}" for c, n in pc[:4]))
        base[tag] = (v0, v1)

    # ---------------- 2. nuisance-reoptimized profile ----------------
    say("\n" + "=" * 108)
    say("2  NUISANCE-REOPTIMIZED PROFILE OVER ETA")
    say("=" * 108)
    grid = np.round(np.arange(-0.020, 0.0201, 0.001), 6)
    prof = {}
    for tag in TAGS:
        clip = clips[tag]
        v0, v1 = base[tag]
        best = {}

        def rec(e, v):
            s = sse_of(clip, v)
            if e not in best or s < best[e][0]:
                best[e] = (s, v)
        for start, order in ((v1, grid), (v1, grid[::-1]), (v0, grid), (v0, grid[::-1])):
            warm = start.copy()
            for e in order:
                s = warm.copy(); s[ETA] = float(e)
                vv, ss, _, _, _ = fit_ls(clip, FREE0, s)
                rec(float(e), vv); warm = vv
        rng = np.random.default_rng(3)
        for e in grid[::4]:
            for _ in range(2):
                s = v1.copy(); s[ETA] = float(e)
                s[FREE0] = np.clip(s[FREE0] + rng.normal(0, 0.25, len(FREE0)),
                                   BLO[FREE0], BHI[FREE0])
                vv, ss, _, _, _ = fit_ls(clip, FREE0, s)
                rec(float(e), vv)
        smin = min(best[e][0] for e in best)
        emin = [e for e in best if best[e][0] == smin][0]
        prof[tag] = (best, smin, emin)
        say(f"\n  {tag}: profile minimum SSE {smin:.5f} at eta {emin:+.4f}")
        say(f"    eta      dSSE        |    eta      dSSE        |    eta      dSSE")
        ks = sorted(best)
        for i in range(0, len(ks), 3):
            row = []
            for e in ks[i:i+3]:
                row.append(f"{e:+.3f} {best[e][0]-smin:10.4f}")
            say("      " + "   |   ".join(row))
        # curvature from a local parabola over +/-0.003
        loc = [(e, best[e][0]) for e in ks if abs(e - emin) <= 0.0031]
        if len(loc) >= 3:
            cur = float(np.polyfit([x[0] for x in loc], [x[1] for x in loc], 2)[0] * 2)
            say(f"    local curvature d2SSE/deta2 {cur:.4e}, per observation {cur/clip.n:.4e}")
        say(f"    dSSE at eta=0 {best[0.0][0]-smin:.4f}; at -0.0053 "
            f"{best[-0.005][0]-smin:.4f}; at +0.008 {best[0.008][0]-smin:.4f}")

    # registered test: Right initialized at the Left estimate
    say("\n  REGISTERED TEST: Tokina Right initialized at the Left eta, nuisance reoptimized")
    clipR = clips[TAGS[1]]
    etaL = float(base[TAGS[0]][1][ETA])
    for lbl, seed in (("from Right M1 nuisance", base[TAGS[1]][1].copy()),
                      ("from Right M0 nuisance", base[TAGS[1]][0].copy()),
                      ("from Left nuisance", base[TAGS[0]][1].copy())):
        s = seed.copy(); s[ETA] = etaL
        vv, ss, opt, _, _ = fit_ls(clipR, FREE1, s)
        say(f"    {lbl:24s}: converges to eta {S.nphys(vv)[3]:+.7f}, SSE {ss:.5f} "
            f"(Right M1 SSE {sse_of(clipR, base[TAGS[1]][1]):.5f})")

    # ---------------- 3. multistart and solver audit ----------------
    say("\n" + "=" * 108)
    say("3  MULTISTART AND SOLVER ROBUSTNESS")
    say("=" * 108)
    for tag in TAGS:
        clip = clips[tag]
        v0, v1 = base[tag]
        seeds = [("embedded M0", (lambda v: (v.copy()))(v0)), ("current M1", v1.copy())]
        for e in (-0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02):
            s = v0.copy(); s[ETA] = e
            seeds.append((f"eta seed {e:+.3f}", s))
        rng = np.random.default_rng(19)
        for i in range(3):
            s = v1.copy(); s[0] += rng.normal(0, 0.05); s[1] += rng.normal(0, 0.05)
            seeds.append((f"centre perturb {i+1}", s))
        Jw = jac(clip, v1, FREE1)
        _, _, Vt = np.linalg.svd(Jw, full_matrices=False)
        for i in range(2):
            s = v1.copy(); s[FREE1] += 0.4 * Vt[-1-i]
            seeds.append((f"weak-direction perturb {i+1}", s))
        # radial-order ladder
        lad = v0.copy(); lad[4] = lad[5] = 0.0; lad[9] = lad[10] = 0.0; lad[ETA] = 0.0
        lad, _, _, _, _ = fit_ls(clip, np.array([0, 1, 2, 3]), lad)
        lad, _, _, _, _ = fit_ls(clip, np.array([0, 1, 2, 3, 4, 5]), lad)
        lad, _, _, _, _ = fit_ls(clip, FREE0, lad)
        seeds.append(("radial-order ladder", lad))
        say(f"\n  {tag}")
        say(f"    {'seed':26} {'trf SSE':>12} {'trf eta':>11} {'L-BFGS-B SSE':>13} "
            f"{'lbfgs eta':>11}")
        bestv, bests = None, np.inf
        for nm, s in seeds:
            va, sa, _, _, _ = fit_ls(clip, FREE1, s)
            vb, sb, _, _, _ = fit_lbfgs(clip, FREE1, s)
            say(f"    {nm:26} {sa:12.5f} {S.nphys(va)[3]:+11.7f} {sb:13.5f} "
                f"{S.nphys(vb)[3]:+11.7f}")
            for vv, ss in ((va, sa), (vb, sb)):
                if ss < bests:
                    bestv, bests = vv, ss
        say(f"    lowest verified SSE across all seeds and both solvers: {bests:.5f}, "
            f"eta {S.nphys(bestv)[3]:+.7f}")
        say(f"    current stored M1 SSE {sse_of(clip, v1):.5f}; "
            f"{'SOLVER FAILURE, a lower basin exists' if bests < sse_of(clip,v1)-1e-6 else 'stored solution is the best found'}")
        # Jacobian finite-difference consistency
        for h in (1e-5, 1e-6, 1e-7):
            Jh = jac(clip, v1, FREE1, h)
            say(f"    finite-difference Jacobian step {h:.0e}: relative difference from "
                f"h=1e-6 {np.abs(Jh-Jw).max()/max(np.abs(Jw).max(),1e-30):.2e}")

    # ---------------- 4. identification of eta ----------------
    say("\n" + "=" * 108)
    say("4  IDENTIFICATION OF ETA")
    say("=" * 108)
    for tag in TAGS:
        clip = clips[tag]
        v1 = base[tag][1]
        Jn = jac(clip, v1, FREE0)
        Je = jac(clip, v1, np.array([ETA]))[:, 0]
        Q, _ = np.linalg.qr(Jn)
        perp = Je - Q @ (Q.T @ Je)
        best, smin, emin = prof[tag]
        loc = [(e, best[e][0]) for e in sorted(best) if abs(e - emin) <= 0.0031]
        cur = float(np.polyfit([x[0] for x in loc], [x[1] for x in loc], 2)[0] * 2)
        d = clip.xy - S.nphys(v1)[0]
        rr = np.hypot(d[:, 0], d[:, 1])
        contrib = perp ** 2
        say(f"\n  {tag}")
        say(f"    ||J_eta|| {np.linalg.norm(Je):.4e}; ||J_eta,perp|| {np.linalg.norm(perp):.4e}; "
            f"retained fraction {np.linalg.norm(perp)/np.linalg.norm(Je):.4f}")
        say(f"    profile curvature {cur:.4e}, per observation {cur/clip.n:.4e}")
        say(f"    2 x ||J_eta,perp||^2 = {2*np.linalg.norm(perp)**2:.4e}, which should match "
            f"the curvature to leading order")
        for lo, hi in ((0, 300), (300, 500), (500, 700), (700, 1100)):
            m = (rr >= lo) & (rr < hi)
            if m.sum() < 10:
                continue
            say(f"      r {lo:4d}-{hi:4d}: {int(m.sum()):4d} pts, "
                f"{100*contrib[m].sum()/contrib.sum():5.1f}% of the perpendicular information")
        ang = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 180
        for lo, hi in ((0, 45), (45, 90), (90, 135), (135, 180)):
            m = (ang >= lo) & (ang < hi)
            if m.sum() < 10:
                continue
            say(f"      polar angle {lo:3d}-{hi:3d} deg: {int(m.sum()):4d} pts, "
                f"{100*contrib[m].sum()/contrib.sum():5.1f}%")

    # ---------------- 5. synthetic recovery on Tokina Right geometry ----------------
    say("\n" + "=" * 108)
    say("5  SYNTHETIC RECOVERY ON THE OBSERVED TOKINA 10 mm RIGHT GEOMETRY")
    say("=" * 108)
    clip = clips[TAGS[1]]
    v1 = base[TAGS[1]][1]
    c, k, p, _ = S.nphys(v1)

    def bc_inv(t, k, p, iters=60):
        u = t.copy()
        for _ in range(iters):
            u = t - S.delta_r(u, k) - S.d_p(u, p)
        return u
    # exact straight-line truth: project corrected points onto their fitted lines
    U = S.Uv(clip.xy, v1)
    Y = U.copy()
    for li in range(clip.nlines):
        a, b = clip.starts[li], clip.starts[li] + clip.counts[li]
        P = U[a:b]
        cen = P.mean(axis=0); q = P - cen
        th = 0.5 * math.atan2(2*float(q[:, 0]@q[:, 1]), float(q[:, 0]@q[:, 0]-q[:, 1]@q[:, 1]))
        dvec = np.array([math.cos(th), math.sin(th)])
        Y[a:b] = cen + np.outer(q @ dvec, dvec)
    chk = bc_inv(S.bc0(Y - c, k, p) if False else (Y - c), k, p)
    say(f"    inverse-map check: max |B0(B0^-1(y)) - y| "
        f"{np.abs(S.bc0(bc_inv(Y-c, k, p), k, p) - (Y-c)).max():.2e} px")
    rngn = np.random.default_rng(31)
    NOISE = 0.20
    say(f"    corner-localization noise used for replicates: {NOISE:.2f} px per coordinate")
    say(f"    {'injected eta':>13} {'noiseless recovered':>20} {'mean over 20':>13} "
        f"{'sd':>9} {'failures':>9}")
    for einj in (0.0, -0.0053, 0.008):
        a = S.amat(einj)
        Xs = c + bc_inv((Y - c) * a, k, p) / a
        syn = S.Clip.__new__(S.Clip)
        syn.__dict__.update(clip.__dict__)
        syn.xy = Xs
        vv, ss, _, _, _ = fit_ls(syn, FREE1, base[TAGS[1]][0].copy())
        e_noiseless = S.nphys(vv)[3]
        ests, fails = [], 0
        for _ in range(20):
            syn2 = S.Clip.__new__(S.Clip)
            syn2.__dict__.update(clip.__dict__)
            syn2.xy = Xs + rngn.normal(0, NOISE, Xs.shape)
            try:
                v2, s2, _, _, _ = fit_ls(syn2, FREE1, base[TAGS[1]][0].copy())
                ests.append(S.nphys(v2)[3])
            except Exception:                                # noqa: BLE001
                fails += 1
        ests = np.array(ests)
        say(f"    {einj:+13.5f} {e_noiseless:+20.7f} {ests.mean():+13.7f} "
            f"{ests.std(ddof=1):9.7f} {fails:9d}")
    say(f"    separation check: can this geometry distinguish 0 from -0.0053? "
        f"compare the dispersion above with the 0.0053 offset.")

    # ---------------- 6. joint Left/Right ----------------
    say("\n" + "=" * 108)
    say("6  JOINT LEFT/RIGHT DIAGNOSTIC, SEPARATE NUISANCE PARAMETERS")
    say("=" * 108)
    cL, cR = clips[TAGS[0]], clips[TAGS[1]]
    vL, vR = base[TAGS[0]][1].copy(), base[TAGS[1]][1].copy()

    def joint(mode):
        nL, nR = len(FREE0), len(FREE0)
        if mode == "zero":
            x0 = np.concatenate([vL[FREE0], vR[FREE0]])
        elif mode == "shared":
            x0 = np.concatenate([vL[FREE0], vR[FREE0], [0.5*(vL[ETA]+vR[ETA])]])
        else:
            x0 = np.concatenate([vL[FREE0], vR[FREE0], [vL[ETA]], [vR[ETA]]])

        def unpack(x):
            a = vL.copy(); a[FREE0] = x[:nL]
            b = vR.copy(); b[FREE0] = x[nL:nL+nR]
            if mode == "zero":
                a[ETA] = b[ETA] = 0.0
            elif mode == "shared":
                a[ETA] = b[ETA] = x[nL+nR]
            else:
                a[ETA] = x[nL+nR]; b[ETA] = x[nL+nR+1]
            return a, b

        def rr(x):
            a, b = unpack(x)
            return np.concatenate([cL.rb(a), cR.rb(b)])
        lo = np.concatenate([BLO[FREE0], BLO[FREE0]] +
                            ([] if mode == "zero" else
                             ([[BLO[ETA]]] if mode == "shared" else [[BLO[ETA]], [BLO[ETA]]])))
        hi = np.concatenate([BHI[FREE0], BHI[FREE0]] +
                            ([] if mode == "zero" else
                             ([[BHI[ETA]]] if mode == "shared" else [[BHI[ETA]], [BHI[ETA]]])))
        r = least_squares(rr, np.clip(x0, lo, hi), method="trf", x_scale=1.0, bounds=(lo, hi),
                          ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
        a, b = unpack(r.x)
        return sse_of(cL, a), sse_of(cR, b), S.nphys(a)[3], S.nphys(b)[3]
    say(f"    {'model':22} {'SSE Left':>11} {'SSE Right':>11} {'total':>11} "
        f"{'eta L':>11} {'eta R':>11}")
    tots = {}
    for mode, lbl in (("zero", "eta_L = eta_R = 0"), ("shared", "one shared eta"),
                      ("sep", "separate eta_L, eta_R")):
        sl, sr, el, er = joint(mode)
        tots[mode] = sl + sr
        say(f"    {lbl:22} {sl:11.5f} {sr:11.5f} {sl+sr:11.5f} {el:+11.7f} {er:+11.7f}")
    say(f"    penalty of shared versus separate: {tots['shared']-tots['sep']:.5f} SSE")
    say(f"    penalty of zero versus separate:   {tots['zero']-tots['sep']:.5f} SSE")
    say(f"    penalty of zero versus shared:     {tots['zero']-tots['shared']:.5f} SSE")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
