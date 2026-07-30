#!/usr/bin/env python3
"""Final straightness-residual cleanup: Tokina 10 mm Left completion, k7 extraction, isotropy.

Reuses the converged fits in /tmp/round5.npy. The only new optimization is the balanced-objective
check for Tokina 10 mm Left. Run with ~/.venvs/vidsync/bin/python.
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
_s = importlib.util.spec_from_file_location("suite4", os.path.join(HERE, "suite4.py"))
S = importlib.util.module_from_spec(_s); _s.loader.exec_module(S)
R, W, H, ETA, M, BLO, BHI, NAMES = S.R, S.W, S.H, S.ETA, S.M, S.BLO, S.BHI, S.NAMES
ALL = {r["tag"]: r for r in np.load("/tmp/round5.npy", allow_pickle=True)}
PATH = {l: p for l, p in S.SUITE}
# repaired Tokina 10 mm Left 4p from the previous round
TOK10L_4P = None


def clip_for(tag):
    lens, cn = tag.split(" / ")
    return S.Clip(PATH[lens], cn)


# ----------------------------------------------------------------- residual vectors

def line_fits(clip, v, loo):
    """Per-line TLS. If loo, each point's residual is to the line fitted without it, computed
    from running sums so the cost stays linear."""
    U = S.Uv(clip.xy, v)
    out_res = np.empty(clip.n)
    out_dir = np.empty((clip.n, 2))
    for li in range(clip.nlines):
        a, b = clip.starts[li], clip.starts[li] + clip.counts[li]
        P = U[a:b]
        n = len(P)
        Sx, Sy = P[:, 0].sum(), P[:, 1].sum()
        Sxx, Syy, Sxy = (P[:, 0] ** 2).sum(), (P[:, 1] ** 2).sum(), (P[:, 0] * P[:, 1]).sum()
        for i in range(n):
            if loo:
                m = n - 1
                sx, sy = Sx - P[i, 0], Sy - P[i, 1]
                sxx = Sxx - P[i, 0] ** 2
                syy = Syy - P[i, 1] ** 2
                sxy = Sxy - P[i, 0] * P[i, 1]
            else:
                m, sx, sy, sxx, syy, sxy = n, Sx, Sy, Sxx, Syy, Sxy
            cx, cy = sx / m, sy / m
            Mxx = sxx - m * cx * cx
            Myy = syy - m * cy * cy
            Mxy = sxy - m * cx * cy
            th = 0.5 * math.atan2(2 * Mxy, Mxx - Myy)
            ux, uy = math.cos(th), math.sin(th)
            out_res[a + i] = -(P[i, 0] - cx) * uy + (P[i, 1] - cy) * ux
            out_dir[a + i] = (ux, uy)
    return out_res, out_dir


def pair_index(clip, v):
    """Corner pairing between the two line families, computed once from a reference map."""
    U = S.Uv(clip.xy, v)
    ang = np.empty(clip.nlines)
    for li in range(clip.nlines):
        a, b = clip.starts[li], clip.starts[li] + clip.counts[li]
        d = U[b - 1] - U[a]
        ang[li] = math.degrees(math.atan2(d[1], d[0])) % 180
    z = np.exp(2j * np.radians(ang))
    ref = math.degrees(np.angle(z.mean())) / 2 % 180
    fam = np.array([0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for a in ang])
    idx = {}
    for li in range(clip.nlines):
        if fam[li] != 0:
            continue
        a = clip.starts[li]
        for j in range(clip.counts[li]):
            p = clip.xy[a + j]
            idx[(round(p[0], 3), round(p[1], 3))] = a + j
    pairs = []
    for li in range(clip.nlines):
        if fam[li] != 1:
            continue
        a = clip.starts[li]
        for j in range(clip.counts[li]):
            p = clip.xy[a + j]
            k = idx.get((round(p[0], 3), round(p[1], 3)))
            if k is not None:
                pairs.append((k, a + j))
    return np.array(pairs), fam


def rvectors(clip, v, pairs, loo):
    res, dirs = line_fits(clip, v, loo)
    out = np.full((len(pairs), 2), np.nan)
    cond = np.full(len(pairs), np.nan)
    for t, (ia, ib) in enumerate(pairs):
        na = np.array([-dirs[ia, 1], dirs[ia, 0]])
        nb = np.array([-dirs[ib, 1], dirs[ib, 0]])
        det = na[0] * nb[1] - na[1] * nb[0]
        cond[t] = 1.0 / max(abs(det), 1e-12)
        if abs(det) < 0.2:
            continue
        ra, rb = res[ia], res[ib]
        out[t] = ((ra * nb[1] - rb * na[1]) / det, (na[0] * rb - nb[0] * ra) / det)
    return out, cond


# ----------------------------------------------------------------- harmonic estimator

def legendre_basis(r, r0, r1, deg=3):
    u = np.clip(2 * (r - r0) / max(r1 - r0, 1e-9) - 1.0, -1.0, 1.0)
    B = [np.ones_like(u), u, 0.5 * (3 * u ** 2 - 1), 0.5 * (5 * u ** 3 - 3 * u)]
    return np.stack(B[:deg + 1], axis=1)


def hfit(r, phi, y, r0, r1, mmax, deg=3):
    B = legendre_basis(r, r0, r1, deg)
    nb = B.shape[1]
    cols = [B]
    for m in range(1, mmax + 1):
        cols.append(B * np.cos(m * phi)[:, None])
        cols.append(B * np.sin(m * phi)[:, None])
    X = np.concatenate(cols, axis=1)
    Q, Rr = np.linalg.qr(X)
    sv = np.linalg.svd(X, compute_uv=False)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta, nb, X, float(sv[0] / sv[-1]), int((sv > sv[0] * 1e-10).sum())


def modeval(beta, nb, m, rr, r0, r1, deg=3):
    b = legendre_basis(np.array([rr]), r0, r1, deg)[0]
    if m == 0:
        return float(beta[:nb] @ b), 0.0
    i = nb * (1 + 2 * (m - 1))
    return float(beta[i:i + nb] @ b), float(beta[i + nb:i + 2 * nb] @ b)


# ----------------------------------------------------------------- per-clip worker

def analyse(job):
    tag, models = job
    o = []
    say = o.append
    clip = clip_for(tag)
    ref = np.array(ALL[tag]["M0_2p"]["v"])
    pairs, fam = pair_index(clip, ref)
    say(f"\n{'='*104}\n{tag}   {clip.nlines} lines, {clip.n} obs, {len(pairs)} paired corners")
    say("=" * 104)
    results = {}
    for mn in models:
        v = np.array(ALL[tag][mn]["v"]) if mn in ALL[tag] else None
        if v is None:
            continue
        c1 = S.nphys(v)[0]
        ein, cnd = rvectors(clip, v, pairs, loo=False)
        elo, _ = rvectors(clip, v, pairs, loo=True)
        ok = np.isfinite(elo[:, 0]) & np.isfinite(ein[:, 0])
        d = clip.xy[pairs[:, 0]] - c1
        rr = np.hypot(d[:, 0], d[:, 1])
        phi = np.arctan2(d[:, 1], d[:, 0])
        r0, r1 = np.percentile(rr[ok], 20), np.percentile(rr[ok], 80)
        band = ok & (rr >= r0) & (rr <= r1)
        nb_ = int(band.sum())
        mmax = 8 if nb_ > 3 * 4 * 17 else (6 if nb_ > 3 * 4 * 13 else 4)
        rms_in = float(np.sqrt((ein[ok] ** 2).sum(1).mean()))
        rms_lo = float(np.sqrt((elo[ok] ** 2).sum(1).mean()))
        say(f"\n  [{mn}]  retained corners {int(ok.sum())}; two-normal condition "
            f"median {np.median(cnd[ok]):.3f}, 95th {np.percentile(cnd[ok],95):.3f}, "
            f"max {cnd[ok].max():.3f}")
        say(f"    residual-vector RMS: in-sample {rms_in:.4f} px, leave-one-out {rms_lo:.4f} px")
        say(f"    (these are 2-D corner-vector RMS from two intersecting line fits; not "
            f"comparable to the optimizer's scalar per-line residual RMS)")
        say(f"    harmonic domain r {r0:.0f} to {r1:.0f} px, {nb_} corners, mmax {mmax}")

        # radial / tangential LOO components
        rad = (elo[:, 0] * d[:, 0] + elo[:, 1] * d[:, 1]) / np.maximum(rr, 1e-9)
        tan = (-elo[:, 0] * d[:, 1] + elo[:, 1] * d[:, 0]) / np.maximum(rr, 1e-9)
        br, nbas, X, cond_d, rank = hfit(rr[band], phi[band], rad[band], r0, r1, mmax)
        bt, _, _, _, _ = hfit(rr[band], phi[band], tan[band], r0, r1, mmax)
        say(f"    design {X.shape[1]} cols, rank {rank}, condition {cond_d:.2e}")

        # validation injections
        inj = {}
        amp = float(np.sqrt((rad[band] ** 2).mean()))
        for nmv, yv in (("pure m=0", amp * np.ones(band.sum())),
                        ("pure m=2", amp * np.cos(2 * phi[band])),
                        ("isotropic noise", np.random.default_rng(4).normal(0, amp,
                                                                            band.sum()))):
            bb, _, _, _, _ = hfit(rr[band], phi[band], yv, r0, r1, mmax)
            rmid = 0.5 * (r0 + r1)
            p0 = abs(modeval(bb, nbas, 0, rmid, r0, r1)[0])
            pm = [math.hypot(*modeval(bb, nbas, m, rmid, r0, r1)) for m in range(1, mmax + 1)]
            inj[nmv] = (p0, max(pm), pm[1] if mmax >= 2 else 0.0)
            say(f"    inject {nmv:16s}: m0 {p0:8.4f}, m2 {inj[nmv][2]:8.4f}, "
                f"largest other mode {max(pm[:1]+pm[2:]) if mmax>2 else 0:8.4f}")

        # mode power by radius
        rgrid = np.linspace(r0, r1, 5)
        say(f"    coherent mode amplitudes at r = " + " ".join(f"{x:.0f}" for x in rgrid))
        tot = 0.0
        best = (0.0, 0, 0.0)
        for m in range(1, mmax + 1):
            ar = [math.hypot(*modeval(br, nbas, m, x, r0, r1)) for x in rgrid]
            at = [math.hypot(*modeval(bt, nbas, m, x, r0, r1)) for x in rgrid]
            tot += float(np.mean(np.array(ar) ** 2 + np.array(at) ** 2))
            mx = max(max(ar), max(at))
            if mx > best[0]:
                cc, ss = modeval(br, nbas, m, rgrid[len(rgrid)//2], r0, r1)
                best = (mx, m, math.degrees(math.atan2(ss, cc)))
            if m <= 4:
                say(f"      m={m} radial " + " ".join(f"{x:6.3f}" for x in ar) +
                    "   tangential " + " ".join(f"{x:6.3f}" for x in at))
        m0r = [modeval(br, nbas, 0, x, r0, r1)[0] for x in rgrid]
        m0t = [modeval(bt, nbas, 0, x, r0, r1)[0] for x in rgrid]
        say(f"      m=0 radial " + " ".join(f"{x:6.3f}" for x in m0r) +
            "   tangential " + " ".join(f"{x:6.3f}" for x in m0t))
        say(f"    total coherent m>=1 power {tot:.4f} px^2; dominant mode m={best[1]} "
            f"amplitude {best[0]:.4f} phase {best[2]:+.1f} deg")

        # A_mean on an angularly uniform grid
        gr, gp = np.meshgrid(np.linspace(r0, r1, 12), np.linspace(-math.pi, math.pi, 48,
                                                                  endpoint=False))
        gr, gp = gr.ravel(), gp.ravel()
        mu_r = np.zeros_like(gr); g0_r = np.zeros_like(gr)
        mu_t = np.zeros_like(gr); g0_t = np.zeros_like(gr)
        Bg = legendre_basis(gr, r0, r1)
        g0_r = Bg @ br[:nbas]; g0_t = Bg @ bt[:nbas]
        mu_r = g0_r.copy(); mu_t = g0_t.copy()
        for m in range(1, mmax + 1):
            i = nbas * (1 + 2 * (m - 1))
            mu_r += (Bg @ br[i:i+nbas]) * np.cos(m * gp) + (Bg @ br[i+nbas:i+2*nbas]) * np.sin(m*gp)
            mu_t += (Bg @ bt[i:i+nbas]) * np.cos(m * gp) + (Bg @ bt[i+nbas:i+2*nbas]) * np.sin(m*gp)
        rmse = float(np.sqrt((elo[band] ** 2).sum(1).mean()))
        A_mean = float(np.sqrt(((mu_r - g0_r) ** 2 + (mu_t - g0_t) ** 2).mean()) / rmse)
        say(f"    A_mean (coherent angular structure / residual RMS) = {A_mean:.4f}")

        # directional covariance after removing the fitted mean field
        Bd = legendre_basis(rr[band], r0, r1)
        mr = Bd @ br[:nbas]; mt = Bd @ bt[:nbas]
        for m in range(1, mmax + 1):
            i = nbas * (1 + 2 * (m - 1))
            mr += (Bd @ br[i:i+nbas]) * np.cos(m*phi[band]) + (Bd @ br[i+nbas:i+2*nbas]) * np.sin(m*phi[band])
            mt += (Bd @ bt[i:i+nbas]) * np.cos(m*phi[band]) + (Bd @ bt[i+nbas:i+2*nbas]) * np.sin(m*phi[band])
        cr = rad[band] - mr; ct = tan[band] - mt
        ux = np.cos(phi[band]); uy = np.sin(phi[band])
        ex = cr * ux - ct * uy; ey = cr * uy + ct * ux
        def cov_stats(mask):
            if mask.sum() < 20:
                return None
            E = np.stack([ex[mask], ey[mask]], axis=1)
            C = np.cov(E.T)
            w, V = np.linalg.eigh(C)
            return (w[1] / max(w[0], 1e-12), (w[1]-w[0])/(w[1]+w[0]),
                    math.degrees(math.atan2(V[1,1], V[0,1])) % 180,
                    float(np.var(cr[mask]) / max(np.var(ct[mask]), 1e-12)))
        st = cov_stats(np.ones(band.sum(), bool))
        say(f"    directional covariance (mean field removed): R_Sigma {st[0]:.3f}, "
            f"A_Sigma {st[1]:.3f}, principal axis {st[2]:.1f} deg, R_rt {st[3]:.3f}")
        rb_ = rr[band]
        edges = np.percentile(rb_, [0, 33, 67, 100])
        for q in range(3):
            mm = (rb_ >= edges[q]) & (rb_ <= edges[q+1])
            s2 = cov_stats(mm)
            if s2:
                say(f"      r {edges[q]:.0f}-{edges[q+1]:.0f}: R_Sigma {s2[0]:.3f}, "
                    f"A_Sigma {s2[1]:.3f}, axis {s2[2]:.1f} deg, R_rt {s2[3]:.3f}")

        # spatial autocorrelation
        pos = clip.xy[pairs[:, 0]]
        sameline = np.zeros((len(pairs), len(pairs)), bool)
        lineof = np.zeros(len(pairs), int)
        for t, (ia, ib) in enumerate(pairs):
            lineof[t] = np.searchsorted(clip.starts, ia, side="right") - 1
        idxb = np.where(band)[0]
        Pb = pos[idxb]
        Eraw = elo[idxb]
        Emu = np.stack([ex, ey], axis=1)
        Lb = lineof[idxb]
        D = np.hypot(Pb[:, None, 0] - Pb[None, :, 0], Pb[:, None, 1] - Pb[None, :, 1])
        same = (Lb[:, None] == Lb[None, :])
        def acf(E, excl):
            v0 = float((E ** 2).sum(1).mean())
            outl = []
            for lo, hi in ((40, 130), (130, 250), (250, 400), (400, 700)):
                mm = (D >= lo) & (D < hi)
                if excl:
                    mm &= ~same
                np.fill_diagonal(mm, False)
                if mm.sum() < 50:
                    outl.append(float("nan")); continue
                num = (E[:, None, :] * E[None, :, :]).sum(-1)[mm].mean()
                outl.append(float(num / v0))
            return outl
        say(f"    spatial autocorrelation, bins 40-130 / 130-250 / 250-400 / 400-700 px")
        say(f"      raw LOO, all pairs        " +
            " ".join(f"{x:+7.3f}" for x in acf(Eraw, False)))
        say(f"      raw LOO, cross-line only  " +
            " ".join(f"{x:+7.3f}" for x in acf(Eraw, True)))
        say(f"      mean removed, cross-line  " +
            " ".join(f"{x:+7.3f}" for x in acf(Emu, True)))
        results[mn] = {"A_mean": A_mean, "R_Sigma": st[0], "A_Sigma": st[1], "axis": st[2],
                       "R_rt": st[3], "rms_lo": rms_lo, "coh": tot,
                       "acf1": acf(Emu, True)[0]}
    return tag, "\n".join(o), results


def main():
    t0 = time.time()
    # ---------------- Part A: Tokina 10 mm Left completion ----------------
    print("=" * 104)
    print("PART A  TOKINA 10 mm LEFT: COMPLETE m=0, 2, 4 DIAGNOSIS AND BALANCED-OBJECTIVE CHECK")
    print("=" * 104, flush=True)
    tagL = "Tokina 10 mm / Left Camera"
    clip = clip_for(tagL)
    v0 = np.array(ALL[tagL]["M0_2p"]["v"]); v1 = np.array(ALL[tagL]["M1_2p"]["v"])
    vc = v1.copy(); vc[ETA] = 0.0
    c1 = S.nphys(v1)[0]
    pairs, fam = pair_index(clip, v0)
    d = clip.xy[pairs[:, 0]] - c1
    rr = np.hypot(d[:, 0], d[:, 1]); phi = np.arctan2(d[:, 1], d[:, 0])
    pct = [float(np.percentile(rr, q)) for q in (20, 40, 60, 80)]
    r0, r1 = pct[0], pct[3]
    print(f"  polar origin = final anisotropy centre ({c1[0]:.2f}, {c1[1]:.2f}); "
          f"radii {['%.0f'%x for x in pct]} px")
    fields = {}
    for nm, vv in (("M0", v0), ("U_c", vc), ("U_A", v1)):
        e, _ = rvectors(clip, vv, pairs, loo=False)
        fields[nm] = e
    fields["U_A - U_c"] = fields["U_A"] - fields["U_c"]
    for nm in ("M0", "U_c", "U_A", "U_A - U_c"):
        e = fields[nm]
        ok = np.isfinite(e[:, 0]) & (rr >= r0) & (rr <= r1)
        rad = (e[:, 0]*d[:, 0] + e[:, 1]*d[:, 1]) / np.maximum(rr, 1e-9)
        tan = (-e[:, 0]*d[:, 1] + e[:, 1]*d[:, 0]) / np.maximum(rr, 1e-9)
        br, nbas, _, _, _ = hfit(rr[ok], phi[ok], rad[ok], r0, r1, 4)
        bt, _, _, _, _ = hfit(rr[ok], phi[ok], tan[ok], r0, r1, 4)
        print(f"\n  [{nm}]")
        for m in (0, 2, 4):
            for lbl, bb in (("radial", br), ("tangential", bt)):
                s = []
                for x in pct:
                    cc, ss = modeval(bb, nbas, m, x, r0, r1)
                    if m == 0:
                        s.append(f"r{x:.0f}: {cc:+7.4f}")
                    else:
                        s.append(f"r{x:.0f}: cos {cc:+7.4f} sin {ss:+7.4f} "
                                 f"amp {math.hypot(cc,ss):6.4f} ph {math.degrees(math.atan2(ss,cc)):+6.1f}")
                print(f"    m={m} {lbl:11s} " + "  ".join(s))
    # intrinsic direct anisotropy increment on a uniform angular grid
    ck, kk, pk, ek = S.nphys(v1)
    a = S.amat(ek)
    print(f"\n  intrinsic direct anisotropy increment on a uniform angular grid (512 angles):")
    for x in pct:
        ph = np.linspace(0, 2*math.pi, 512, endpoint=False)
        uu = np.stack([x*np.cos(ph), x*np.sin(ph)], axis=1)
        dA = (S.delta_r(uu*a, kk)/a - S.delta_r(uu, kk)) + (S.d_p(uu*a, pk)/a - S.d_p(uu, pk))
        rc = dA[:, 0]*np.cos(ph) + dA[:, 1]*np.sin(ph)
        F = np.fft.rfft(rc)/len(ph)
        print(f"    r={x:.0f}: m0 {F[0].real:+8.5f}  m2 amp {2*abs(F[2]):7.5f} "
              f"ph {math.degrees(np.angle(F[2])):+7.1f}  m4 amp {2*abs(F[4]):7.5f} "
              f"ph {math.degrees(np.angle(F[4])):+7.1f}")

    # balanced objective
    print(f"\n  BALANCED OBJECTIVE (equal total weight to each occupied family-by-quartile "
          f"stratum)")
    fa = np.concatenate([np.full(clip.counts[i], fam[i]) for i in range(clip.nlines)])
    dd = clip.xy - c1
    rp = np.hypot(dd[:, 0], dd[:, 1])
    qs = np.percentile(rp, [25, 50, 75])
    rq = np.digitize(rp, qs)
    wt = np.zeros(clip.n)
    strata = []
    for f in (0, 1):
        for q in range(4):
            m = (fa == f) & (rq == q)
            if m.sum() >= 10:
                strata.append((f, q, int(m.sum())))
                wt[m] = 1.0 / m.sum()
    wt *= clip.n / wt.sum()
    print(f"    {len(strata)} occupied strata, sizes " +
          " ".join(str(s[2]) for s in strata))
    sw = np.sqrt(wt)

    def bres(v):
        return np.concatenate([clip.resid(v) * sw, clip.barrier(v)])

    def bfit(free, seed):
        best = None
        for s in ([seed] + [np.clip(seed + np.concatenate(
                [np.random.default_rng(i).normal(0, .1, 13), [0.]]), BLO, BHI)
                for i in range(3)]):
            s = np.clip(s, BLO, BHI)
            def rf(w, s=s):
                v = s.copy(); v[np.array(free)] = w
                return bres(v)
            r = least_squares(rf, s[np.array(free)], method="trf", x_scale=1.0,
                              bounds=(BLO[np.array(free)], BHI[np.array(free)]),
                              ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20000)
            v = s.copy(); v[np.array(free)] = r.x
            c = float((clip.resid(v)*sw) @ (clip.resid(v)*sw))
            if best is None or c < best[1]:
                best = (v, c)
        return best
    s0 = v1.copy(); s0[ETA] = 0.0
    vb0, cb0 = bfit(M["M0_2p"], s0)
    vb1, cb1 = bfit(M["M1_2p"], v1.copy())
    print(f"    balanced eta=0 : balanced SSE {cb0:.4f}, ordinary SSE {clip.sse(vb0):.4f}")
    print(f"    balanced free  : balanced SSE {cb1:.4f}, ordinary SSE {clip.sse(vb1):.4f}, "
          f"eta {S.nphys(vb1)[3]:+.7f}")
    print(f"    sign of eta under balanced weighting: "
          f"{'NEGATIVE, preserved' if S.nphys(vb1)[3] < 0 else 'POSITIVE, sign flipped'}")
    resb = clip.resid(vb1)**2; res0 = clip.resid(vb0)**2
    print(f"    balanced solution per-point SSE by family: A "
          f"{res0[fa==0].mean():.4f} -> {resb[fa==0].mean():.4f}, B "
          f"{res0[fa==1].mean():.4f} -> {resb[fa==1].mean():.4f}")
    print(f"    by radial quartile: " + "  ".join(
        f"{res0[rq==q].mean():.4f}->{resb[rq==q].mean():.4f}" for q in range(4)))
    # Tokina 10 Right balanced curve at fixed nuisance
    tagR = "Tokina 10 mm / Right Camera"
    clipR = clip_for(tagR)
    vR = np.array(ALL[tagR]["M1_2p"]["v"])
    faR = np.concatenate([np.full(clipR.counts[i], pair_index(clipR, vR)[1][i])
                          for i in range(clipR.nlines)])
    ddR = clipR.xy - S.nphys(vR)[0]
    rqR = np.digitize(np.hypot(ddR[:, 0], ddR[:, 1]),
                      np.percentile(np.hypot(ddR[:, 0], ddR[:, 1]), [25, 50, 75]))
    wR = np.zeros(clipR.n)
    for f in (0, 1):
        for q in range(4):
            m = (faR == f) & (rqR == q)
            if m.sum() >= 10:
                wR[m] = 1.0 / m.sum()
    wR *= clipR.n / wR.sum()
    print(f"\n  Tokina 10 mm Right, balanced objective at fixed nuisance, versus eta:")
    for e in (-0.006, -0.003, 0.0, 0.003, 0.006):
        vv = vR.copy(); vv[ETA] = e
        rres = clipR.resid(vv)
        print(f"    eta {e:+.4f}: balanced SSE {float((rres*rres*wR).sum()):.4f}")

    # ---------------- Part B: k7 both starts ----------------
    print("\n" + "=" * 104)
    print("PART B  k1..k7 + p1,p2 + eta: BOTH REQUESTED STARTS")
    print("=" * 104, flush=True)
    for tag in ALL:
        clip = clip_for(tag)
        rng = np.random.default_rng(23)
        s7a = np.array(ALL[tag]["M1_2p"]["v"]).copy()
        s7b = s7a.copy(); s7b[6:9] = rng.normal(0, 0.1, 3)
        got = []
        for nm, s in (("warm", s7a), ("perturbed", s7b)):
            g = S.fit1(clip, np.array(M["M1_2p_k7"]), s)
            got.append((nm, g[1], S.nphys(g[0])[3], g[0]))
        got_s = sorted(got, key=lambda z: z[1])
        v = got_s[0][3]
        c, k, p, e = S.nphys(v)
        sv, cond = S.svcond(clip, v, np.array(M["M1_2p_k7"]))
        dj = S.jdet(clip.grid, c, k, p, e)
        u = (clip.grid - c) * S.amat(e)
        ab = [NAMES[j] for j in M["M1_2p_k7"]
              if abs(v[j]-BLO[j]) < 1e-7 or abs(v[j]-BHI[j]) < 1e-7]
        base = ALL[tag]["M1_2p"]["sse"]
        print(f"\n  {tag}")
        for nm, sse, et, _ in got:
            print(f"    start {nm:10s} SSE {sse:11.4f}  eta {et:+.7f}"
                  f"{'   <- retained' if abs(sse-got_s[0][1])<1e-9 else ''}")
        print(f"    spread between starts: SSE {abs(got[0][1]-got[1][1]):.4f} "
              f"({100*abs(got[0][1]-got[1][1])/base:.2f}% of the k1..k4 SSE), "
              f"eta {abs(got[0][2]-got[1][2]):.7f}")
        print(f"    alpha5,6,7 {v[6]:+.5f} {v[7]:+.5f} {v[8]:+.5f}; bounds "
              f"{ab if ab else 'none'}")
        print(f"    condition {cond:.3e}; smallest three sv " +
              " ".join(f"{x:.3e}" for x in sv[-3:]))
        print(f"    min det {dj.min():+.5f}; max radial "
              f"{np.linalg.norm(S.delta_r(u,k),axis=1).max():.1f} px; "
              f"k1..k4 SSE {base:.4f} -> {got_s[0][1]:.4f} "
              f"({100*(1-got_s[0][1]/base):+.2f}%)")

    # ---------------- Parts C-F ----------------
    print("\n" + "=" * 104)
    print("PARTS C TO F  RESIDUAL VECTORS AND ISOTROPY, ALL CLIPS")
    print("=" * 104, flush=True)
    jobs = []
    for tag in ALL:
        mods = ["M0_2p", "M1_2p"]
        if tag in ("Rokinon 8 mm / Left Camera", "Tokina 17 mm / Left Camera",
                   "Tokina 17 mm / Right Camera"):
            mods.append("M1_4p")
        jobs.append((tag, mods))
    summary = {}
    with ProcessPoolExecutor(max_workers=8) as ex:
        for tag, txt, res in ex.map(analyse, jobs):
            print(txt, flush=True)
            summary[tag] = res
    print("\n" + "=" * 104)
    print("SUMMARY  isotropy indices, baseline -> anisotropic")
    print("=" * 104)
    print(f"  {'clip':28} {'A_mean':>16} {'R_Sigma':>16} {'R_rt':>16} "
          f"{'adjacent ACF':>16} {'LOO RMS px':>16}")
    for tag, r in summary.items():
        if "M0_2p" not in r or "M1_2p" not in r:
            continue
        a, b = r["M0_2p"], r["M1_2p"]
        print(f"  {tag:28} {a['A_mean']:7.3f}->{b['A_mean']:<7.3f} "
              f"{a['R_Sigma']:7.3f}->{b['R_Sigma']:<7.3f} "
              f"{a['R_rt']:7.3f}->{b['R_rt']:<7.3f} "
              f"{a['acf1']:+7.3f}->{b['acf1']:<+7.3f} "
              f"{a['rms_lo']:7.3f}->{b['rms_lo']:<7.3f}")
    print(f"\n  total runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
