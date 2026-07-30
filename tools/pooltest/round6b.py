#!/usr/bin/env python3
"""Isotropy analysis with an angular order chosen to pass its own injection tests.

The first attempt used mmax = 8 with four radial degrees of freedom. It failed validation: injecting
a constant radial field of amplitude a returned m=0 of 4a, and injecting isotropic noise returned
spurious m=2 coefficients an order of magnitude above the input. Design rank was full and the
condition number only 1.7e3 to 6.2e3, so this is not rank deficiency but angular aliasing -- the
corner distributions occupy only about two thirds of the 30-degree sectors beyond r = 600 px and
about 40 percent beyond 900, so high angular modes are far from orthogonal on the observed support
and a constant is absorbed into cancelling high-m coefficients.

This version chooses the largest angular order that passes three injection tests per clip and model,
and evaluates the mean field at the observed corner locations rather than on a uniform grid that
would extrapolate into empty sectors.
"""

import importlib.util
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "round6.py")).read().replace("sys.exit(main())", "pass")
NS = {"__name__": "imported", "__file__": os.path.join(HERE, "round6.py")}
exec(compile(src, "round6", "exec"), NS)
S, ALL = NS["S"], NS["ALL"]
clip_for, pair_index, rvectors = NS["clip_for"], NS["pair_index"], NS["rvectors"]
hfit, modeval, legendre_basis = NS["hfit"], NS["modeval"], NS["legendre_basis"]


def validate(rr, phi, amp, r0, r1, mmax, rng, deg=3):
    """Returns worst relative error across three injected fields."""
    rmid = 0.5 * (r0 + r1)
    worst = 0.0
    b, nb, X, cond, rank = hfit(rr, phi, amp * np.ones(len(rr)), r0, r1, mmax, deg)
    p0 = modeval(b, nb, 0, rmid, r0, r1, deg)[0]
    worst = max(worst, abs(p0 - amp) / amp)
    for m in range(1, mmax + 1):
        worst = max(worst, math.hypot(*modeval(b, nb, m, rmid, r0, r1, deg)) / amp)
    b, nb, _, _, _ = hfit(rr, phi, amp * np.cos(2 * phi), r0, r1, mmax, deg)
    if mmax >= 2:
        worst = max(worst, abs(math.hypot(*modeval(b, nb, 2, rmid, r0, r1, deg)) - amp) / amp)
    for m in [x for x in range(1, mmax + 1) if x != 2]:
        worst = max(worst, math.hypot(*modeval(b, nb, m, rmid, r0, r1, deg)) / amp)
    worst_noise = 0.0
    for k in range(3):
        y = rng.normal(0, amp, len(rr))
        b, nb, _, _, _ = hfit(rr, phi, y, r0, r1, mmax, deg)
        for m in range(1, mmax + 1):
            worst_noise = max(worst_noise, math.hypot(*modeval(b, nb, m, rmid, r0, r1, deg)) / amp)
    return worst, worst_noise, cond


def analyse(job):
    tag, models = job
    o = []
    say = o.append
    clip = clip_for(tag)
    ref = np.array(ALL[tag]["M0_2p"]["v"])
    pairs, fam = pair_index(clip, ref)
    say(f"\n{'='*104}\n{tag}  {clip.nlines} lines, {clip.n} obs, {len(pairs)} paired corners")
    say("=" * 104)
    res = {}
    for mn in models:
        if mn not in ALL[tag]:
            continue
        v = np.array(ALL[tag][mn]["v"])
        c1 = S.nphys(v)[0]
        ein, cnd = rvectors(clip, v, pairs, loo=False)
        elo, _ = rvectors(clip, v, pairs, loo=True)
        ok = np.isfinite(elo[:, 0]) & np.isfinite(ein[:, 0])
        d = clip.xy[pairs[:, 0]] - c1
        rr = np.hypot(d[:, 0], d[:, 1])
        phi = np.arctan2(d[:, 1], d[:, 0])
        r0, r1 = np.percentile(rr[ok], 20), np.percentile(rr[ok], 80)
        band = ok & (rr >= r0) & (rr <= r1)
        rad = (elo[:, 0] * d[:, 0] + elo[:, 1] * d[:, 1]) / np.maximum(rr, 1e-9)
        tan = (-elo[:, 0] * d[:, 1] + elo[:, 1] * d[:, 0]) / np.maximum(rr, 1e-9)
        amp = float(np.sqrt((rad[band] ** 2).mean()))
        rng = np.random.default_rng(9)
        chosen, diag = None, []
        for dg in (3, 2, 1):
            for mm in (8, 6, 4, 3, 2):
                w, wn, cond = validate(rr[band], phi[band], amp, r0, r1, mm, rng, dg)
                diag.append((dg, mm, w, wn, cond))
                if chosen is None and w < 0.10 and wn < 0.25:
                    chosen = (dg, mm)
        say(f"\n  [{mn}] corners {int(ok.sum())}; two-normal condition median "
            f"{np.median(cnd[ok]):.4f}, max {cnd[ok].max():.4f}")
        say(f"    residual-vector RMS: in-sample {np.sqrt((ein[ok]**2).sum(1).mean()):.4f} px, "
            f"leave-one-out {np.sqrt((elo[ok]**2).sum(1).mean()):.4f} px")
        say(f"    (2-D corner vectors from two intersecting line fits; not the optimizer's "
            f"scalar per-line RMS)")
        say(f"    angular-order selection over r {r0:.0f}-{r1:.0f} px, {int(band.sum())} corners:")
        for dg, mm, w, wn, cond in diag:
            if wn < 0.6 or mm <= 3:
                say(f"      radial dof {dg+1}, mmax {mm}: injected-field error {w:6.3f}, "
                    f"worst spurious mode from noise {wn:6.3f}, condition {cond:.2e}"
                    + ("   <- selected" if chosen == (dg, mm) else ""))
        if chosen is None:
            say("    NO angular order passes validation; isotropy diagnostics omitted for "
                "this model")
            continue
        deg, mmax = chosen
        br, nb, _, _, _ = hfit(rr[band], phi[band], rad[band], r0, r1, mmax, deg)
        bt, _, _, _, _ = hfit(rr[band], phi[band], tan[band], r0, r1, mmax, deg)
        rgrid = np.linspace(r0, r1, 4)
        tot, best = 0.0, (0.0, 0, 0.0)
        for m in range(1, mmax + 1):
            ar = [math.hypot(*modeval(br, nb, m, x, r0, r1, deg)) for x in rgrid]
            at = [math.hypot(*modeval(bt, nb, m, x, r0, r1, deg)) for x in rgrid]
            tot += float(np.mean(np.array(ar) ** 2 + np.array(at) ** 2))
            if max(max(ar), max(at)) > best[0]:
                cc, ss = modeval(br, nb, m, rgrid[len(rgrid) // 2], r0, r1, deg)
                best = (max(max(ar), max(at)), m, math.degrees(math.atan2(ss, cc)))
            say(f"      m={m} radial " + " ".join(f"{x:6.3f}" for x in ar) +
                "  tangential " + " ".join(f"{x:6.3f}" for x in at))
        say(f"      m=0 radial " +
            " ".join(f"{modeval(br,nb,0,x,r0,r1,deg)[0]:6.3f}" for x in rgrid) +
            "  tangential " +
            " ".join(f"{modeval(bt,nb,0,x,r0,r1,deg)[0]:6.3f}" for x in rgrid))
        say(f"    coherent m>=1 power {tot:.4f} px^2; dominant m={best[1]} "
            f"amplitude {best[0]:.4f} phase {best[2]:+.1f} deg")

        # mean field at the observed corners (no extrapolation into empty sectors)
        B = legendre_basis(rr[band], r0, r1, deg)
        mr = B @ br[:nb]; mt = B @ bt[:nb]
        g0r, g0t = mr.copy(), mt.copy()
        for m in range(1, mmax + 1):
            i = nb * (1 + 2 * (m - 1))
            mr = mr + (B @ br[i:i+nb]) * np.cos(m*phi[band]) + (B @ br[i+nb:i+2*nb]) * np.sin(m*phi[band])
            mt = mt + (B @ bt[i:i+nb]) * np.cos(m*phi[band]) + (B @ bt[i+nb:i+2*nb]) * np.sin(m*phi[band])
        rmse = float(np.sqrt((elo[band] ** 2).sum(1).mean()))
        A_mean = float(np.sqrt(((mr-g0r)**2 + (mt-g0t)**2).mean()) / rmse)
        say(f"    A_mean at observed corners = {A_mean:.4f}   (residual RMS {rmse:.4f} px)")

        cr, ct = rad[band] - mr, tan[band] - mt
        ux, uy = np.cos(phi[band]), np.sin(phi[band])
        ex, ey = cr*ux - ct*uy, cr*uy + ct*ux

        def cs(mask):
            if mask.sum() < 25:
                return None
            C = np.cov(np.stack([ex[mask], ey[mask]], axis=1).T)
            w, V = np.linalg.eigh(C)
            return (w[1]/max(w[0], 1e-12), (w[1]-w[0])/(w[1]+w[0]),
                    math.degrees(math.atan2(V[1, 1], V[0, 1])) % 180,
                    float(np.var(cr[mask])/max(np.var(ct[mask]), 1e-12)))
        st = cs(np.ones(band.sum(), bool))
        say(f"    directional covariance (mean removed): R_Sigma {st[0]:.3f}, A_Sigma "
            f"{st[1]:.3f}, principal axis {st[2]:.1f} deg, R_rt {st[3]:.3f}")
        rb = rr[band]; edges = np.percentile(rb, [0, 33, 67, 100])
        for q in range(3):
            s2 = cs((rb >= edges[q]) & (rb <= edges[q+1]))
            if s2:
                say(f"      r {edges[q]:.0f}-{edges[q+1]:.0f}: R_Sigma {s2[0]:.3f}, "
                    f"axis {s2[2]:.1f} deg, R_rt {s2[3]:.3f}")

        # spatial autocorrelation
        pos = clip.xy[pairs[:, 0]][band]
        lineof = np.array([np.searchsorted(clip.starts, ia, side="right") - 1
                           for ia, ib in pairs])[band]
        D = np.hypot(pos[:, None, 0]-pos[None, :, 0], pos[:, None, 1]-pos[None, :, 1])
        same = lineof[:, None] == lineof[None, :]

        def acf(E, excl):
            v0 = float((E**2).sum(1).mean())
            r_ = []
            for lo, hi in ((40, 130), (130, 250), (250, 400), (400, 700)):
                mk = (D >= lo) & (D < hi)
                if excl:
                    mk = mk & ~same
                np.fill_diagonal(mk, False)
                if mk.sum() < 50:
                    r_.append(float("nan")); continue
                r_.append(float((E[:, None, :]*E[None, :, :]).sum(-1)[mk].mean()/v0))
            return r_
        Eraw = elo[band]; Emu = np.stack([ex, ey], axis=1)
        a1 = acf(Eraw, False); a2 = acf(Eraw, True); a3 = acf(Emu, True)
        say(f"    autocorrelation, bins 40-130 / 130-250 / 250-400 / 400-700 px")
        say(f"      raw, all pairs       " + " ".join(f"{x:+7.3f}" for x in a1))
        say(f"      raw, cross-line only " + " ".join(f"{x:+7.3f}" for x in a2))
        say(f"      mean removed, cross  " + " ".join(f"{x:+7.3f}" for x in a3))
        res[mn] = {"A_mean": A_mean, "R_Sigma": st[0], "R_rt": st[3], "axis": st[2],
                   "rms": rmse, "coh": tot, "acf_raw": a2[0], "acf_mu": a3[0],
                   "mmax": f"{deg+1}/{mmax}", "dom": best[1]}
    return tag, "\n".join(o), res


def main():
    t0 = time.time()
    jobs = []
    for tag in ALL:
        mods = ["M0_2p", "M1_2p"]
        if tag in ("Rokinon 8 mm / Left Camera", "Tokina 17 mm / Left Camera",
                   "Tokina 17 mm / Right Camera"):
            mods.append("M1_4p")
        jobs.append((tag, mods))
    summ = {}
    with ProcessPoolExecutor(max_workers=8) as ex:
        for tag, txt, r in ex.map(analyse, jobs):
            print(txt, flush=True)
            summ[tag] = r
    print("\n" + "=" * 104)
    print("SUMMARY  baseline -> anisotropic, validated angular order only")
    print("=" * 104)
    print(f"  {'clip':28} {'mmax':>7} {'LOO RMS':>15} {'A_mean':>15} {'R_Sigma':>15} "
          f"{'R_rt':>15} {'ACF raw':>15} {'ACF mean-rm':>15}")
    for tag, r in summ.items():
        if "M0_2p" not in r or "M1_2p" not in r:
            continue
        a, b = r["M0_2p"], r["M1_2p"]
        print(f"  {tag:28} {a['mmax']}|{b['mmax']:<7} "
              f"{a['rms']:6.3f}->{b['rms']:<7.3f} {a['A_mean']:6.3f}->{b['A_mean']:<7.3f} "
              f"{a['R_Sigma']:6.3f}->{b['R_Sigma']:<7.3f} {a['R_rt']:6.3f}->{b['R_rt']:<7.3f} "
              f"{a['acf_raw']:+6.3f}->{b['acf_raw']:<+7.3f} "
              f"{a['acf_mu']:+6.3f}->{b['acf_mu']:<+7.3f}")
    print(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
