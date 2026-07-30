#!/usr/bin/env python3
"""Round 9b, all eight clips: strict two-family holdout, mode-separated harmonics, whitening.

Sections 4-6 of the final straightness-residual round.

Section 4 replaces the previous one-family fold scheme. Both line families are partitioned; a test
corner must have BOTH its parent lines held out, and a training corner must share NEITHER. Mixed
intersections are dropped from that fold. Every corner is tested exactly once across the crossed
folds.

Section 5 reports m=2 and m=4 separately with their aliasing, and puts every ratio on the same
points with the same normalized weights.

Section 6 propagates Cov(v) = N^-1 Cov(d) N^-T before reading anything into directional anisotropy.

Run with ~/.venvs/vidsync/bin/python.
"""

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

GA, GB = 3, 3
NBOOT = 120
HIER = [("H0", []), ("H2", [2]), ("H24", [2, 4]), ("H1234", [1, 2, 3, 4])]
NRAD0, NRADM = 3, 2


def leg(u, k):
    P = [np.ones_like(u), u, 0.5 * (3 * u * u - 1)]
    return np.stack(P[:k], axis=1)


def design(r, phi, modes, r0, r1):
    u = np.clip(2 * (r - r0) / max(r1 - r0, 1e-9) - 1.0, -1.0, 1.0)
    cols = [leg(u, NRAD0)]
    for m in modes:
        B = leg(u, NRADM)
        cols.append(B * np.cos(m * phi)[:, None])
        cols.append(B * np.sin(m * phi)[:, None])
    return np.concatenate(cols, axis=1)


def wls(X, y, w):
    sw = np.sqrt(w)
    b, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return b


def crossed_folds(la, lb, ga, gb, seed=5):
    """Partition both families, then form the crossed test/train masks."""
    rng = np.random.default_rng(seed)
    ua, ub = np.unique(la), np.unique(lb)
    Ga = {l: i % ga for i, l in enumerate(rng.permutation(ua))}
    Gb = {l: i % gb for i, l in enumerate(rng.permutation(ub))}
    A = np.array([Ga[l] for l in la])
    B = np.array([Gb[l] for l in lb])
    out = []
    for i in range(ga):
        for j in range(gb):
            te = (A == i) & (B == j)
            tr = (A != i) & (B != j)
            out.append((tr, te))
    return out, A, B


def cv_crossed(Xs, yr, yt, w, folds):
    """Held-out weighted MSE and cross-fitted angular prediction, strict two-family folds."""
    out = {}
    for nm, X in Xs.items():
        pr = np.full_like(yr, np.nan); pt = np.full_like(yt, np.nan)
        pra = np.zeros_like(yr); pta = np.zeros_like(yt)
        for tr, te in folds:
            if te.sum() == 0 or tr.sum() < X.shape[1] + 5:
                continue
            br = wls(X[tr], yr[tr], w[tr]); bt = wls(X[tr], yt[tr], w[tr])
            pr[te] = X[te] @ br; pt[te] = X[te] @ bt
            br2 = br.copy(); br2[:NRAD0] = 0
            bt2 = bt.copy(); bt2[:NRAD0] = 0
            pra[te] = X[te] @ br2; pta[te] = X[te] @ bt2
        ok = np.isfinite(pr) & np.isfinite(pt)
        ww = w * ok
        se = ww * ((yr - np.nan_to_num(pr)) ** 2 + (yt - np.nan_to_num(pt)) ** 2)
        out[nm] = (float(se.sum() / max(ww.sum(), 1e-12)),
                   float(math.sqrt((ww * (pra ** 2 + pta ** 2)).sum() / max(ww.sum(), 1e-12))),
                   ok, np.nan_to_num(pr), np.nan_to_num(pt))
    return out


def analyse(job):
    tag, = job
    o = []
    say = o.append
    clip = clip_for(tag)
    ref = np.array(ALL[tag]["M0_2p"]["v"])
    pairs, fam = pair_index(clip, ref)
    lineA = np.array([np.searchsorted(clip.starts, ia, side="right") - 1 for ia, ib in pairs])
    lineB = np.array([np.searchsorted(clip.starts, ib, side="right") - 1 for ia, ib in pairs])
    say(f"\n{'='*108}\n{tag}   {clip.nlines} lines "
        f"({(fam==0).sum()}A/{(fam==1).sum()}B), {clip.n} obs, {len(pairs)} paired corners")
    say("=" * 108)
    res = {}
    for mn in ("M0_2p", "M1_2p"):
        v = np.array(ALL[tag][mn]["v"])
        c1 = S.nphys(v)[0]
        elo, cnd = rvectors(clip, v, pairs, loo=True)
        ok0 = np.isfinite(elo[:, 0])
        d = clip.xy[pairs[:, 0]] - c1
        rr = np.hypot(d[:, 0], d[:, 1]); phi = np.arctan2(d[:, 1], d[:, 0])
        keep = ok0 & (rr > np.percentile(rr[ok0], 3)) & (rr < np.percentile(rr[ok0], 97))
        R_, P_, E_ = rr[keep], phi[keep], elo[keep]
        LA, LB = lineA[keep], lineB[keep]
        yr = E_[:, 0] * np.cos(P_) + E_[:, 1] * np.sin(P_)
        yt = -E_[:, 0] * np.sin(P_) + E_[:, 1] * np.cos(P_)
        r0, r1 = R_.min(), R_.max()

        w = np.ones(len(R_))
        bedge = np.percentile(R_, [0, 33, 67, 100])
        for bi in range(3):
            bm = (R_ >= bedge[bi]) & (R_ <= bedge[bi + 1])
            sec = np.floor((np.degrees(P_[bm]) + 180) / 30).astype(int) % 12
            cnt = np.bincount(sec, minlength=12).astype(float)
            w[bm] = 1.0 / np.maximum(cnt[sec], 1)
        w *= len(w) / w.sum()

        folds, GAi, GBi = crossed_folds(LA, LB, GA, GB)
        trn = np.array([tr.sum() for tr, te in folds])
        tes = np.array([te.sum() for tr, te in folds])
        drop = len(R_) - tes.sum()
        Xs = {nm: design(R_, P_, modes, r0, r1) for nm, modes in HIER}
        cv = cv_crossed(Xs, yr, yt, w, folds)
        cover = cv["H0"][2]

        say(f"\n  [{mn}]  {len(R_)} corners kept, radius {r0:.0f}-{r1:.0f} px, "
            f"{len(np.unique(LA))} A-clusters x {len(np.unique(LB))} B-clusters")
        say(f"    strict crossed folds: {GA}x{GB} = {len(folds)}; train per fold "
            f"{trn.min()}-{trn.max()} (median {int(np.median(trn))}), test per fold "
            f"{tes.min()}-{tes.max()}, total tested {int(cover.sum())} of {len(R_)}")
        say(f"    every tested corner has BOTH parents held out and no training corner shares "
            f"either; {drop} corners fall in no crossed test cell")

        # ---- consistent scales, all on the covered points with the same normalized weights
        ww = w * cover
        wn = ww / ww.sum()
        obs_rms = float(math.sqrt((( yr ** 2 + yt ** 2) * cover).sum() / max(cover.sum(), 1)))
        bal_rms = float(math.sqrt((wn * (yr ** 2 + yt ** 2)).sum()))
        say(f"    scales on the SAME {int(cover.sum())} covered points: ordinary observed-point "
            f"RMS {obs_rms:.4f} px, angular-balanced RMS {bal_rms:.4f} px")

        say(f"    nested strict-holdout comparison (weighted joint radial+tangential MSE):")
        gains = {}
        for i, (nm, _) in enumerate(HIER):
            if i == 0:
                say(f"      H0     MSE {cv[nm][0]:8.5f}")
                continue
            prev = HIER[i - 1][0]
            dcv = (cv[prev][0] - cv[nm][0]) / max(cv[prev][0], 1e-12)
            gains[nm] = dcv
            say(f"      {nm:6s} MSE {cv[nm][0]:8.5f}   dCV vs {prev:5s} {dcv:+7.4f}")

        # ---- bootstrap null over A-line clusters
        Xh0 = Xs["H0"]
        bh_r = wls(Xh0, yr, w); bh_t = wls(Xh0, yt, w)
        rr_ = yr - Xh0 @ bh_r; rt_ = yt - Xh0 @ bh_t
        rngb = np.random.default_rng(11)
        ua = np.unique(LA)
        null = {nm: [] for nm, _ in HIER[1:]}
        for _ in range(NBOOT):
            pick = rngb.choice(ua, size=len(ua), replace=True)
            idx = np.concatenate([np.where(LA == l)[0] for l in pick])
            sgn = np.repeat(rngb.choice([-1.0, 1.0], size=len(pick)),
                            [int((LA == l).sum()) for l in pick])
            yrb = (Xh0 @ bh_r)[idx] + sgn * rr_[idx]
            ytb = (Xh0 @ bh_t)[idx] + sgn * rt_[idx]
            fb, _, _ = crossed_folds(LA[idx], LB[idx], GA, GB, seed=int(rngb.integers(1e6)))
            cvb = cv_crossed({nm: Xs[nm][idx] for nm, _ in HIER}, yrb, ytb, w[idx], fb)
            for i, (nm, _) in enumerate(HIER[1:], start=1):
                prev = HIER[i - 1][0]
                null[nm].append((cvb[prev][0] - cvb[nm][0]) / max(cvb[prev][0], 1e-12))
        # A step must beat its own null, improve on its predecessor, AND beat H0 outright.
        # Without the last clause a model whose null is catastrophically negative is declared
        # supported while predicting worse than no angular model at all.
        sel = "H0"
        for i, (nm, _) in enumerate(HIER[1:], start=1):
            p95 = float(np.percentile(null[nm], 95))
            beatsH0 = cv[nm][0] < cv["H0"][0]
            passed = (gains[nm] > p95) and (gains[nm] > 0.0) and beatsH0
            if passed:
                sel = nm
            why = ("SUPPORTED" if passed else
                   "not positive" if gains[nm] <= 0 else
                   "worse than H0 outright" if not beatsH0 else "within null")
            say(f"      {nm:6s} null 95th {p95:+7.4f}  vs H0 {cv[nm][0]/cv['H0'][0]:6.3f}x  -> {why}")
        ang = cv[sel][1]
        say(f"    selected {sel}; cross-fitted angular prediction RMS {ang:.4f} px "
            f"= {ang/max(bal_rms,1e-9):.3f} of the angular-balanced RMS on the same points")

        # ---- mode-separated reporting on the H24 design
        X24 = Xs["H24"]
        b24r = wls(X24, yr, w); b24t = wls(X24, yt, w)
        modeinfo = {}
        for j, m in enumerate((2, 4)):
            i0 = NRAD0 + j * 2 * NRADM
            sl = slice(i0, i0 + 2 * NRADM)
            Xm = np.zeros_like(X24); Xm[:, sl] = X24[:, sl]
            pmr, pmt = Xm @ b24r, Xm @ b24t
            amp = float(math.sqrt((wn * (pmr ** 2 + pmt ** 2)).sum()))
            rq = np.percentile(R_, [17, 50, 83])
            radial = []
            for rx in rq:
                u = np.array([2 * (rx - r0) / max(r1 - r0, 1e-9) - 1.0])
                Bv = leg(u, NRADM)[0]
                cc = float(Bv @ b24r[i0:i0 + NRADM]); ss = float(Bv @ b24r[i0 + NRADM:i0 + 2 * NRADM])
                radial.append(math.hypot(cc, ss))
            u = np.array([2 * (rq[1] - r0) / max(r1 - r0, 1e-9) - 1.0])
            Bv = leg(u, NRADM)[0]
            cc = float(Bv @ b24r[i0:i0 + NRADM]); ss = float(Bv @ b24r[i0 + NRADM:i0 + 2 * NRADM])
            ph = math.degrees(math.atan2(ss, cc)) / m
            modeinfo[m] = (amp, radial, ph, rq)
        # aliasing between the m=2 and m=4 blocks after removing the m=0 block
        sw = np.sqrt(w)[:, None]
        X0 = X24[:, :NRAD0] * sw
        Q0, _ = np.linalg.qr(X0)
        def resid_block(sl):
            Bm = X24[:, sl] * sw
            Bm = Bm - Q0 @ (Q0.T @ Bm)
            Qb, _ = np.linalg.qr(Bm)
            return Qb
        Q2 = resid_block(slice(NRAD0, NRAD0 + 2 * NRADM))
        Q4 = resid_block(slice(NRAD0 + 2 * NRADM, NRAD0 + 4 * NRADM))
        cc_ = np.linalg.svd(Q2.T @ Q4, compute_uv=False)
        say(f"    mode-separated on the H24 design, amplitudes as weighted RMS over the same "
            f"points:")
        for m in (2, 4):
            amp, radial, ph, rq = modeinfo[m]
            say(f"      m={m}: amplitude {amp:.4f} px; radial profile at r="
                f"{rq[0]:.0f}/{rq[1]:.0f}/{rq[2]:.0f} px -> "
                f"{radial[0]:.4f}/{radial[1]:.4f}/{radial[2]:.4f} px; phase {ph:+.1f} deg")
        say(f"      held-out gain attributable to m=2 (H0->H2) {gains['H2']:+.4f}, "
            f"to m=4 given m=2 (H2->H24) {gains['H24']:+.4f}")
        say(f"      m=2 / m=4 aliasing: canonical correlations "
            f"{', '.join(f'{x:.3f}' for x in cc_)}")

        # ---- section 6: whitening
        say(f"    directional residual scatter, raw then whitened:")
        wh = whiten(clip, v, pairs, keep, P_, cv[sel], w, cover)
        for lbl, (er, et) in wh["sets"]:
            ex = er * np.cos(P_) - et * np.sin(P_)
            ey = er * np.sin(P_) + et * np.cos(P_)
            st = covstats(ex, ey, er, et, ww)
            say(f"      {lbl:26} eig ratio {st[0]:6.3f}, A_Sigma {st[1]:+.3f}, "
                f"axis {st[2]:6.1f} deg, R_rt {st[3]:6.3f}")
        say(f"      covariance model: sigma_corner {wh['sigma']:.4f} px, median geometric "
            f"amplification |N^-1| {wh['amp']:.3f}, condition of N median {wh['ncond']:.2f}, "
            f"90th {wh['ncond90']:.2f}")
        rs = []
        rngc = np.random.default_rng(23)
        erw, etw = wh["sets"][-1][1]
        for _ in range(200):
            pick = rngc.choice(ua, size=len(ua), replace=True)
            idx = np.concatenate([np.where(LA == l)[0] for l in pick])
            ex = erw[idx] * np.cos(P_[idx]) - etw[idx] * np.sin(P_[idx])
            ey = erw[idx] * np.sin(P_[idx]) + etw[idx] * np.cos(P_[idx])
            rs.append(covstats(ex, ey, erw[idx], etw[idx], ww[idx])[0])
        say(f"      whitened eigenvalue ratio 5th-95th over 200 A-cluster resamples "
            f"[{np.percentile(rs,5):.3f}, {np.percentile(rs,95):.3f}]")

        # ---- cross-line pair verification
        pos = clip.xy[pairs[:, 0]][keep]
        D = np.hypot(pos[:, None, 0] - pos[None, :, 0], pos[:, None, 1] - pos[None, :, 1])
        share = (LA[:, None] == LA[None, :]) | (LB[:, None] == LB[None, :])
        np.fill_diagonal(share, True)
        chk = int((share & ~((LA[:, None] == LA[None, :]) | (LB[:, None] == LB[None, :]))).sum())
        er, et = wh["sets"][-1][1]
        E = np.stack([er * np.cos(P_) - et * np.sin(P_),
                      er * np.sin(P_) + et * np.cos(P_)], axis=1)
        v0 = float((E ** 2).sum(1).mean())
        acf, npair = [], []
        for lo, hi in ((40, 130), (130, 250), (250, 400), (400, 700)):
            mk = (D >= lo) & (D < hi) & ~share
            if mk.sum() < 40:
                acf.append(float("nan")); npair.append(int(mk.sum())); continue
            acf.append(float((E[:, None, :] * E[None, :, :]).sum(-1)[mk].mean() / v0))
            npair.append(int(mk.sum()))
        say(f"    cross-line spatial correlation of WHITENED residuals, verified to share "
            f"neither parent (violations {chk}):")
        say(f"      40-130 / 130-250 / 250-400 / 400-700 px  "
            + " ".join(f"{x:+.3f}" for x in acf))
        say(f"      pair counts                              "
            + " ".join(f"{x:7d}" for x in npair))
        res[mn] = {"sel": sel, "ang": ang, "bal": bal_rms, "obs": obs_rms,
                   "g2": gains["H2"], "g24": gains["H24"],
                   "a2": modeinfo[2][0], "a4": modeinfo[4][0],
                   "alias": float(cc_.max()),
                   "eig_raw": covstats(*rot(wh["sets"][0][1], P_), ww)[0],
                   "eig_wh": covstats(*rot(wh["sets"][-1][1], P_), ww)[0]}
    return tag, "\n".join(o), res


def rot(rt, P_):
    er, et = rt
    return (er * np.cos(P_) - et * np.sin(P_), er * np.sin(P_) + et * np.cos(P_), er, et)


def covstats(ex, ey, er, et, ww):
    E = np.stack([ex, ey], axis=1)
    mu = (E * ww[:, None]).sum(0) / ww.sum()
    D = E - mu
    C = (D * ww[:, None]).T @ D / ww.sum()
    ev, V = np.linalg.eigh(C)
    vr = float((ww * er ** 2).sum() / ww.sum())
    vt = float((ww * et ** 2).sum() / ww.sum())
    return (ev[1] / max(ev[0], 1e-12), (ev[1] - ev[0]) / (ev[1] + ev[0]),
            math.degrees(math.atan2(V[1, 1], V[0, 1])) % 180, vr / max(vt, 1e-12))


def whiten(clip, v, pairs, keep, P_, cvsel, w, cover):
    """Propagate Cov(v) = N^-1 Cov(d) N^-T and whiten.

    d holds the two scalar leave-one-out normal residuals of a corner to its two parent lines.
    With isotropic corner-localization noise of variance s^2 the model is
        Var(d_A) = s^2 (1 + hA),  Var(d_B) = s^2 (1 + hB),  Cov(d_A, d_B) = s^2 (nA . nB),
    the off-diagonal arising because the same localization error enters both projections; the two
    line-fit errors are independent because the lines share only the excluded corner.
    """
    U = S.Uv(clip.xy, v)
    nrm = np.empty((clip.n, 2)); hlev = np.empty(clip.n)
    for li in range(clip.nlines):
        a, b = clip.starts[li], clip.starts[li] + clip.counts[li]
        P = U[a:b]; q = P - P.mean(0)
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        nrm[a:b] = [-math.sin(th), math.cos(th)]
        t = q[:, 0] * math.cos(th) + q[:, 1] * math.sin(th)
        n = b - a
        ss = float(t @ t)
        hlev[a:b] = 1.0 / max(n - 1, 1) + t ** 2 / np.maximum(ss - t ** 2, 1e-9)
    ia, ib = pairs[keep, 0], pairs[keep, 1]
    nA, nB = nrm[ia], nrm[ib]
    elo, _ = rvectors(clip, v, pairs, loo=True)
    E = elo[keep]
    dA = (E * nA).sum(1); dB = (E * nB).sum(1)
    hA, hB = hlev[ia], hlev[ib]
    dot = (nA * nB).sum(1)
    s2 = float(np.mean(dA ** 2 / (1 + hA)) + np.mean(dB ** 2 / (1 + hB))) / 2
    sig = math.sqrt(max(s2, 1e-12))
    er_raw = E[:, 0] * np.cos(P_) + E[:, 1] * np.sin(P_)
    et_raw = -E[:, 0] * np.sin(P_) + E[:, 1] * np.cos(P_)
    _, angp, ok, pr, pt = cvsel[0], cvsel[1], cvsel[2], cvsel[3], cvsel[4]
    er_c, et_c = er_raw - pr, et_raw - pt
    amps, erw, etw = [], np.empty(len(dA)), np.empty(len(dA))
    nconds = []
    for i in range(len(dA)):
        N = np.array([nA[i], nB[i]])
        try:
            Ni = np.linalg.inv(N)
        except np.linalg.LinAlgError:
            erw[i] = etw[i] = 0.0; amps.append(np.nan); nconds.append(np.nan); continue
        Cd = s2 * np.array([[1 + hA[i], dot[i]], [dot[i], 1 + hB[i]]])
        Cv = Ni @ Cd @ Ni.T
        ev, V = np.linalg.eigh(Cv)
        ev = np.maximum(ev, 1e-12)
        Wm = V @ np.diag(ev ** -0.5) @ V.T
        ph = P_[i]
        Rt = np.array([[math.cos(ph), math.sin(ph)], [-math.sin(ph), math.cos(ph)]])
        vec = np.array([er_c[i], et_c[i]])
        xy = Rt.T @ vec
        z = Rt @ (Wm @ xy)
        erw[i], etw[i] = z
        amps.append(np.linalg.norm(Ni, 2))
        nconds.append(np.linalg.cond(N))
    return {"sets": [("raw", (er_raw, et_raw)),
                     ("angular model removed", (er_c, et_c)),
                     ("whitened", (erw, etw))],
            "sigma": sig, "amp": float(np.nanmedian(amps)),
            "ncond": float(np.nanmedian(nconds)),
            "ncond90": float(np.nanpercentile(nconds, 90))}


def main():
    t0 = time.time()
    summ = {}
    with ProcessPoolExecutor(max_workers=8) as ex:
        for tag, txt, r in ex.map(analyse, [(t,) for t in ALL]):
            print(txt, flush=True)
            summ[tag] = r
    print("\n" + "=" * 124)
    print("SUMMARY, STRICT TWO-FAMILY HOLDOUT")
    print("=" * 124)
    print(f"  {'clip':28} {'model':6} {'sel':>6} {'dCV m2':>8} {'dCV m4':>8} {'amp m2':>8} "
          f"{'amp m4':>8} {'alias':>6} {'bal RMS':>8} {'ang RMS':>8} {'eig raw':>8} {'eig wh':>7}")
    for tag, r in summ.items():
        for mn in ("M0_2p", "M1_2p"):
            a = r[mn]
            print(f"  {tag:28} {mn:6} {a['sel']:>6} {a['g2']:+8.4f} {a['g24']:+8.4f} "
                  f"{a['a2']:8.4f} {a['a4']:8.4f} {a['alias']:6.3f} {a['bal']:8.4f} "
                  f"{a['ang']:8.4f} {a['eig_raw']:8.3f} {a['eig_wh']:7.3f}")
    print(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
