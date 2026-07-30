#!/usr/bin/env python3
"""Repair two bad 4p fits, then the Tokina 10 mm Left diagnostic and the 4p gauge diagnostic."""

import importlib.util
import math
import os
import sys

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("suite4", os.path.join(HERE, "suite4.py"))
S = importlib.util.module_from_spec(_s); _s.loader.exec_module(S)
_t = importlib.util.spec_from_file_location("round5", os.path.join(HERE, "round5.py"))
T5 = importlib.util.module_from_spec(_t); _t.loader.exec_module(T5)
R, W, H, ETA, M, BLO, BHI, NAMES = S.R, S.W, S.H, S.ETA, S.M, S.BLO, S.BHI, S.NAMES

ALL = {r["tag"]: r for r in np.load("/tmp/round5.npy", allow_pickle=True)}
PATH = {l: p for l, p in S.SUITE}


def clip_for(tag):
    lens, cn = tag.split(" / ")
    return S.Clip(PATH[lens], cn)


def refit(clip, free, seeds):
    bb, cnt = None, 0
    for s in seeds:
        g = S.fit1(clip, np.array(free), np.clip(s, BLO, BHI))
        if g is None:
            continue
        if bb is None or g[1] < bb[1] - 1e-9:
            bb, cnt = g, 1
        elif abs(g[1] - bb[1]) <= max(1e-9, 1e-6 * bb[1]):
            cnt += 1
    return bb, cnt, len(seeds)


def main():
    say = print
    say("=" * 108)
    say("TASK 3 REPAIR  the two 4p solutions that failed their own checks")
    say("=" * 108)
    rng = np.random.default_rng(31)
    fixed = {}
    for tag, why in (("Tokina 10 mm / Left Camera",
                      "M1_4p SSE 171.4550 exceeded its own M0_4p 160.6078: nesting violated"),
                     ("Sony Handycam / Right Camera",
                      "M1_4p pinned xi at its bound with eta jumping to +0.027")):
        r = ALL[tag]
        clip = clip_for(tag)
        say(f"\n  {tag}\n    problem: {why}")
        seeds = [np.array(r["M0_4p"]["v"]), np.array(r["M1_4p"]["v"]),
                 np.array(r["M1_2p"]["v"])]
        seeds[0] = seeds[0].copy(); seeds[0][ETA] = r["M1_2p"]["eta"]
        s = np.array(r["M0_4p"]["v"]).copy(); s[ETA] = 0.0
        seeds.append(s)
        for _ in range(6):
            q = np.array(r["M0_4p"]["v"]).copy()
            q[ETA] = r["M1_2p"]["eta"] + rng.normal(0, 0.004)
            q[9:13] += rng.normal(0, 0.2, 4)
            seeds.append(q)
        bb, cnt, ns = refit(clip, M["M1_4p"], seeds)
        v, sse, opt = bb
        c, k, p, e = S.nphys(v)
        sv, cond = S.svcond(clip, v, np.array(M["M1_4p"]))
        u = (clip.grid - c) * S.amat(e)
        dj = S.jdet(clip.grid, c, k, p, e)
        ab = [NAMES[j] for j in M["M1_4p"]
              if abs(v[j] - BLO[j]) < 1e-7 or abs(v[j] - BHI[j]) < 1e-7]
        m0 = r["M0_4p"]["sse"]
        say(f"    repaired M1_4p: SSE {sse:.4f} (was {r['M1_4p']['sse']:.4f}), "
            f"RMS {math.sqrt(sse/clip.n):.6f}")
        say(f"      eta {e:+.7f} (was {r['M1_4p']['eta']:+.7f}); centre "
            f"({c[0]:.2f},{c[1]:.2f}); max decentering "
            f"{np.linalg.norm(S.d_p(u,p),axis=1).max():.2f} px")
        say(f"      condition {cond:.3e}; min det {dj.min():+.5f}; "
            f"bounds {ab if ab else 'none'}; basin {cnt}/{ns}")
        say(f"      nesting against M0_4p {m0:.4f}: {sse <= m0 + 1e-9}")
        fixed[tag] = {"v": v, "sse": sse, "rms": math.sqrt(sse / clip.n), "eta": e,
                      "cond": cond, "bounds": ab, "maxdec":
                      float(np.linalg.norm(S.d_p(u, p), axis=1).max())}

    # ---------------- Tokina 10 mm diagnostic ----------------
    say("\n" + "=" * 108)
    say("TASK 5  TOKINA 10 mm LEFT DIAGNOSTIC, WITH RIGHT FOR CONTRAST")
    say("=" * 108)
    for tag in ("Tokina 10 mm / Left Camera", "Tokina 10 mm / Right Camera"):
        r = ALL[tag]
        clip = clip_for(tag)
        v1 = np.array(r["M1_2p"]["v"]); v0 = np.array(r["M0_2p"]["v"])
        vc = v1.copy(); vc[ETA] = 0.0            # fixed-nuisance counterfactual U_c
        sse0, ssec, ssea = clip.sse(v0), clip.sse(vc), clip.sse(v1)
        N = clip.n
        say(f"\n  {tag}   N={N}")
        say(f"    M0_2p (own optimum)          SSE {sse0:10.4f}  RMS {math.sqrt(sse0/N):.6f}")
        say(f"    U_c fixed-nuisance, eta=0    SSE {ssec:10.4f}  RMS {math.sqrt(ssec/N):.6f}")
        say(f"    U_A final anisotropic        SSE {ssea:10.4f}  RMS {math.sqrt(ssea/N):.6f}")
        say(f"    direct anisotropy step U_c -> U_A improves SSE by {ssec-ssea:.4f} "
            f"({100*(ssec-ssea)/ssec:+.2f}%): {'YES' if ssea < ssec else 'NO'}")
        say(f"    of the total M0 -> M1 improvement {sse0-ssea:.4f}, the direct step accounts "
            f"for {ssec-ssea:.4f} ({100*(ssec-ssea)/max(sse0-ssea,1e-12):.1f}%); nuisance "
            f"movement accounts for {sse0-ssec:.4f} ({100*(sse0-ssec)/max(sse0-ssea,1e-12):.1f}%)")

        # residual structure
        L, fam, angs, pr = S.pairs_of(clip, v0)
        if len(pr) >= 80:
            pos = np.array([[q[4], q[5]] for q in pr])
            c1 = S.nphys(v1)[0]
            d = pos - c1
            rr = np.hypot(d[:, 0], d[:, 1])
            pct = [float(np.percentile(rr, q)) for q in (20, 40, 60, 80)]
            ck, kk, pk, ek = S.nphys(v1)
            a = S.amat(ek)
            dAr = S.delta_r((pos - ck) * a, kk) / a - S.delta_r(pos - ck, kk)
            hv, cnd, nk = S.harm(pos, dAr, c1, tuple(pct))
            odd = hv[("rad", 1, pct[2])][2] + hv[("rad", 3, pct[2])][2]
            ev = max(hv[("rad", 2, pct[2])][2], 1e-12)
            say(f"    harmonic estimator validation on Delta_A,r: odd/even {odd/ev:.4f}, "
                f"design condition {cnd:.2e} -> {'PASS' if odd/ev < 0.02 else 'FAIL'}")
            say(f"    radial percentiles 20/40/60/80 = " +
                "/".join(f"{x:.0f}" for x in pct) + " px")
            for lbl, vv in (("baseline M0", v0), ("U_c fixed nuisance", vc),
                            ("U_A final", v1)):
                hh, _, _ = S.harm(pos, S.rfield(clip, vv, pr), c1, tuple(pct))
                for m in (2,):
                    line = "  ".join(
                        f"r{px:.0f}: cos {hh[('rad',m,px)][0]:+7.4f} sin "
                        f"{hh[('rad',m,px)][1]:+7.4f}" for px in pct)
                    say(f"      m=2 radial, {lbl:20s} {line}")
            # m=0 and m=4 need the raw beta; approximate m=4 via the same estimator call
            for lbl, vv in (("baseline M0", v0), ("U_A final", v1)):
                hh, _, _ = S.harm(pos, S.rfield(clip, vv, pr), c1, tuple(pct), mmax=4)
                say(f"      m=1,3 radial, {lbl:20s} " + "  ".join(
                    f"r{px:.0f}: m1 {hh[('rad',1,px)][2]:6.3f} m3 {hh[('rad',3,px)][2]:6.3f}"
                    for px in pct))

        # SSE partition by line family and radial quartile
        say(f"    SSE partition (per point, px^2). Families assigned from the baseline fit.")
        fa = np.concatenate([np.full(len(clip.lines[i]), fam.get(i, 0))
                             for i in range(clip.nlines)])
        dd = clip.xy - S.nphys(v1)[0]
        rp = np.hypot(dd[:, 0], dd[:, 1])
        qs = np.percentile(rp, [25, 50, 75])
        rq = np.digitize(rp, qs)
        for lbl, vv in (("M0 baseline", v0), ("U_c", vc), ("U_A", v1)):
            res = clip.resid(vv) ** 2
            byf = [res[fa == f].mean() if (fa == f).any() else float("nan") for f in (0, 1)]
            byr = [res[rq == q].mean() for q in range(4)]
            say(f"      {lbl:12s} family A {byf[0]:8.4f}  family B {byf[1]:8.4f}   "
                f"radial quartiles " + " ".join(f"{x:8.4f}" for x in byr))

    # ---------------- gauge diagnostic ----------------
    say("\n" + "=" * 108)
    say("TASK 6  IS THE EXTRA 4p MAP MEANINGFULLY NONPROJECTIVE?")
    say("=" * 108)
    targets = ["Rokinon 8 mm / Left Camera", "Tokina 10 mm / Left Camera",
               "Tokina 17 mm / Left Camera", "Tokina 17 mm / Right Camera",
               "Sony Handycam / Right Camera"]
    for tag in targets:
        r = ALL[tag]
        clip = clip_for(tag)
        v2 = np.array(r["M1_2p"]["v"])
        v4 = np.array(fixed[tag]["v"]) if tag in fixed else np.array(r["M1_4p"]["v"])
        U2 = S.Uv(clip.grid, v2); U4 = S.Uv(clip.grid, v4)
        c4 = S.nphys(v4)[0]
        say(f"\n  {tag}")
        sv = np.array(r["M1_4p"]["sv"])
        say(f"    smallest three scaled singular values of the 4p Jacobian: " +
            " ".join(f"{x:.3e}" for x in sv[-3:]))
        # loadings of the smallest singular direction
        eps = 1e-6
        J = []
        free = np.array(M["M1_4p"])
        for j in free:
            a = v4.copy(); a[j] += eps
            b = v4.copy(); b[j] -= eps
            J.append((clip.resid(a) - clip.resid(b)) / (2 * eps))
        Jm = np.array(J).T
        _, s_, Vt = np.linalg.svd(Jm, full_matrices=False)
        w = Vt[-1]
        say(f"    loadings of the weakest direction: " + "  ".join(
            f"{NAMES[free[i]]} {w[i]:+.3f}" for i in np.argsort(-np.abs(w))[:5]))
        for kind, dv in (("before alignment", U4 - U2),
                         ("after best affine", T5.S.align(U2, U4, "affine")),
                         ("after homography", T5.S.align(U2, U4, "homog"))):
            mag = np.linalg.norm(dv, axis=1)
            dg = clip.grid - c4
            rrg = np.maximum(np.hypot(dg[:, 0], dg[:, 1]), 1e-9)
            rad = (dv[:, 0] * dg[:, 0] + dv[:, 1] * dg[:, 1]) / rrg
            tan = (-dv[:, 0] * dg[:, 1] + dv[:, 1] * dg[:, 0]) / rrg
            say(f"      {kind:20s} rms {np.sqrt((mag**2).mean()):9.4f}  "
                f"max {mag.max():9.4f}  radial rms {np.sqrt((rad**2).mean()):8.4f}  "
                f"tangential rms {np.sqrt((tan**2).mean()):8.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
