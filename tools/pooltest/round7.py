#!/usr/bin/env python3
"""Cross-validated angular-structure hierarchy on M0 and M1 leave-one-out residual vectors.

Replaces the previous unregularized joint harmonic fit through m=8, whose rejection criterion was
wrong: an in-sample fit of many regressors to noise necessarily produces amplitude, which is
overfitting rather than evidence that harmonic analysis cannot be done. Here every angular claim is
judged by blocked held-out prediction against a line-cluster bootstrap null.

Folds are line clusters, not random corners: corners are grouped by their family-A parent line and
those lines are partitioned into five folds, so a held-out corner never shares a fitted family-A
line with the training set. Leakage through the family-B parent remains and is stated rather than
assumed away. The same line clusters are the resampling unit for the bootstrap null.

Run with ~/.venvs/vidsync/bin/python.
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

NFOLD = 5
NBOOT = 120
HIER = [("H0", []), ("H2", [2]), ("H24", [2, 4]), ("H1234", [1, 2, 3, 4])]


def leg(u, k):
    P = [np.ones_like(u), u, 0.5 * (3 * u * u - 1)]
    return np.stack(P[:k], axis=1)


def design(r, phi, modes, r0, r1, nrad0=3, nradm=2):
    u = np.clip(2 * (r - r0) / max(r1 - r0, 1e-9) - 1.0, -1.0, 1.0)
    cols = [leg(u, nrad0)]
    for m in modes:
        B = leg(u, nradm)
        cols.append(B * np.cos(m * phi)[:, None])
        cols.append(B * np.sin(m * phi)[:, None])
    return np.concatenate(cols, axis=1), nrad0


def wlstsq(X, y, w):
    sw = np.sqrt(w)
    b, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return b


def cv_hier(X_by_model, yr, yt, w, fold, nrad0):
    """Returns per-model held-out weighted MSE and the cross-fitted angular prediction."""
    out = {}
    for nm, X in X_by_model.items():
        pr = np.zeros_like(yr); pt = np.zeros_like(yt)
        pra = np.zeros_like(yr); pta = np.zeros_like(yt)
        for f in range(NFOLD):
            tr, te = fold != f, fold == f
            if te.sum() == 0 or tr.sum() < X.shape[1] + 5:
                continue
            br = wlstsq(X[tr], yr[tr], w[tr])
            bt = wlstsq(X[tr], yt[tr], w[tr])
            pr[te] = X[te] @ br
            pt[te] = X[te] @ bt
            # angular part only: zero the m=0 block
            br2 = br.copy(); br2[:nrad0] = 0
            bt2 = bt.copy(); bt2[:nrad0] = 0
            pra[te] = X[te] @ br2
            pta[te] = X[te] @ bt2
        se = w * ((yr - pr) ** 2 + (yt - pt) ** 2)
        out[nm] = (float(se.sum() / w.sum()),
                   float(math.sqrt((w * (pra ** 2 + pta ** 2)).sum() / w.sum())))
    return out


def analyse(job):
    tag, models = job
    o = []
    say = o.append
    clip = clip_for(tag)
    ref = np.array(ALL[tag]["M0_2p"]["v"])
    pairs, fam = pair_index(clip, ref)
    lineA = np.array([np.searchsorted(clip.starts, ia, side="right") - 1 for ia, ib in pairs])
    say(f"\n{'='*106}\n{tag}   {clip.nlines} lines, {clip.n} obs, {len(pairs)} paired corners")
    say("=" * 106)
    res = {}
    for mn in models:
        if mn not in ALL[tag]:
            continue
        v = np.array(ALL[tag][mn]["v"])
        c1 = S.nphys(v)[0]
        elo, cnd = rvectors(clip, v, pairs, loo=True)
        ok = np.isfinite(elo[:, 0])
        d = clip.xy[pairs[:, 0]] - c1
        rr = np.hypot(d[:, 0], d[:, 1]); phi = np.arctan2(d[:, 1], d[:, 0])
        keep = ok & (rr > np.percentile(rr[ok], 3)) & (rr < np.percentile(rr[ok], 97))
        R_, P_, E_, L_ = rr[keep], phi[keep], elo[keep], lineA[keep]
        yr = (E_[:, 0] * np.cos(P_) + E_[:, 1] * np.sin(P_))
        yt = (-E_[:, 0] * np.sin(P_) + E_[:, 1] * np.cos(P_))
        r0, r1 = R_.min(), R_.max()

        # angular-balancing weights inside three coarse radial bands
        w = np.ones(len(R_))
        bedge = np.percentile(R_, [0, 33, 67, 100])
        for bi in range(3):
            bm = (R_ >= bedge[bi]) & (R_ <= bedge[bi + 1])
            sec = np.floor((np.degrees(P_[bm]) + 180) / 30).astype(int) % 12
            cnt = np.bincount(sec, minlength=12).astype(float)
            w[bm] = 1.0 / np.maximum(cnt[sec], 1)
        w *= len(w) / w.sum()

        # line-cluster folds
        ul = np.unique(L_)
        rngf = np.random.default_rng(5)
        grp = {l: i % NFOLD for i, l in enumerate(rngf.permutation(ul))}
        fold = np.array([grp[l] for l in L_])

        Xs = {}
        for nm, modes in HIER:
            X, nrad0 = design(R_, P_, modes, r0, r1)
            Xs[nm] = X
        cv = cv_hier(Xs, yr, yt, w, fold, 3)
        wr = float(math.sqrt((w * (yr ** 2 + yt ** 2)).sum() / w.sum()))
        say(f"\n  [{mn}]  {len(R_)} corners after 3/97 pct radial trim, radius {r0:.0f}-{r1:.0f} px")
        say(f"    weighted residual-vector RMS {wr:.4f} px; {len(ul)} family-A line clusters, "
            f"{NFOLD} folds; columns per model " +
            ", ".join(f"{nm} {Xs[nm].shape[1]}" for nm, _ in HIER))
        say(f"    NOTE corners still share their family-B parent line across folds, so the")
        say(f"    held-out estimates are optimistic by an unquantified but bounded amount.")

        # bootstrap null: resample line clusters from an H0-only world
        Xh0 = Xs["H0"]
        bh_r = wlstsq(Xh0, yr, w); bh_t = wlstsq(Xh0, yt, w)
        resr = yr - Xh0 @ bh_r; rest = yt - Xh0 @ bh_t
        rngb = np.random.default_rng(11)
        null = {nm: [] for nm, _ in HIER[1:]}
        for _ in range(NBOOT):
            pick = rngb.choice(ul, size=len(ul), replace=True)
            idx = np.concatenate([np.where(L_ == l)[0] for l in pick])
            sgn = np.repeat(rngb.choice([-1.0, 1.0], size=len(pick)),
                            [int((L_ == l).sum()) for l in pick])
            yrb = (Xh0 @ bh_r)[idx] + sgn * resr[idx]
            ytb = (Xh0 @ bh_t)[idx] + sgn * rest[idx]
            Xb = {nm: Xs[nm][idx] for nm, _ in HIER}
            fb = fold[idx]
            cvb = cv_hier(Xb, yrb, ytb, w[idx], fb, 3)
            for nm, _ in HIER[1:]:
                prev = HIER[[h[0] for h in HIER].index(nm) - 1][0]
                null[nm].append((cvb[prev][0] - cvb[nm][0]) / max(cvb[prev][0], 1e-12))
        say(f"    nested held-out comparison (weighted joint radial+tangential MSE):")
        sel = "H0"
        for i, (nm, _) in enumerate(HIER):
            if i == 0:
                say(f"      H0     MSE {cv[nm][0]:8.5f}")
                continue
            prev = HIER[i - 1][0]
            dcv = (cv[prev][0] - cv[nm][0]) / max(cv[prev][0], 1e-12)
            nl = np.array(null[nm])
            p95 = float(np.percentile(nl, 95))
            passed = (dcv > p95) and (dcv > 0.0)
            if passed:
                sel = nm
            say(f"      {nm:6s} MSE {cv[nm][0]:8.5f}   dCV {dcv:+7.4f}   null 95th pct "
                f"{p95:+7.4f}   {'SUPPORTED' if passed else ('not positive' if dcv <= 0 else 'within null')}")
        ang_px = cv[sel][1]
        say(f"    selected {sel}; cross-fitted angular prediction RMS {ang_px:.4f} px "
            f"= {ang_px/wr:.3f} of the weighted residual RMS")
        if sel == "H0":
            say(f"    no angular extension is supported. As a scale for what could hide there,")
            say(f"    the cross-fitted angular prediction the H2 and H24 models do produce is "
                f"{cv['H2'][1]:.4f} and {cv['H24'][1]:.4f} px, that is "
                f"{cv['H2'][1]/wr:.3f} and {cv['H24'][1]/wr:.3f} of the residual RMS; since")
            say(f"    neither predicts held out, a real coherent angular field is bounded near "
                f"or below that.")

        # dominant supported mode
        dom = None
        if sel != "H0":
            X = Xs[sel]
            br = wlstsq(X, yr, w)
            mods = dict(HIER)[sel]
            amps = {}
            for j, m in enumerate(mods):
                i0 = 3 + j * 4
                amps[m] = float(np.hypot(np.abs(br[i0:i0+2]).max(),
                                         np.abs(br[i0+2:i0+4]).max()))
            dom = max(amps, key=amps.get)
            rmid = 0.5 * (r0 + r1)
            u = np.array([2 * (rmid - r0) / (r1 - r0) - 1.0])
            B = leg(u, 2)[0]
            j = mods.index(dom); i0 = 3 + j * 4
            cc = float(B @ br[i0:i0+2]); ss = float(B @ br[i0+2:i0+4])
            say(f"    dominant supported mode m={dom}, mid-radius amplitude "
                f"{math.hypot(cc,ss):.4f} px, phase {math.degrees(math.atan2(ss,cc)):+.1f} deg")

        # cross-fitted residuals -> covariance isotropy
        X = Xs[sel]
        pr = np.zeros_like(yr); pt = np.zeros_like(yt)
        for f in range(NFOLD):
            tr, te = fold != f, fold == f
            if te.sum() == 0 or tr.sum() < X.shape[1] + 5:
                continue
            pr[te] = X[te] @ wlstsq(X[tr], yr[tr], w[tr])
            pt[te] = X[te] @ wlstsq(X[tr], yt[tr], w[tr])
        cr, ct = yr - pr, yt - pt
        ux, uy = np.cos(P_), np.sin(P_)
        ex, ey = cr * ux - ct * uy, cr * uy + ct * ux

        def cov(mask):
            if mask.sum() < 30:
                return None
            ww = w[mask]
            E = np.stack([ex[mask], ey[mask]], axis=1)
            mu = (E * ww[:, None]).sum(0) / ww.sum()
            D = E - mu
            C = (D * ww[:, None]).T @ D / ww.sum()
            ev, V = np.linalg.eigh(C)
            vr = float((ww * cr[mask] ** 2).sum() / ww.sum())
            vt = float((ww * ct[mask] ** 2).sum() / ww.sum())
            return (ev[1] / max(ev[0], 1e-12), (ev[1] - ev[0]) / (ev[1] + ev[0]),
                    math.degrees(math.atan2(V[1, 1], V[0, 1])) % 180, vr / max(vt, 1e-12))
        st = cov(np.ones(len(R_), bool))
        # line-cluster bootstrap on the eigenvalue ratio
        rs = []
        for _ in range(60):
            pick = rngb.choice(ul, size=len(ul), replace=True)
            idx = np.concatenate([np.where(L_ == l)[0] for l in pick])
            m2 = np.zeros(len(R_), bool)
            E = np.stack([ex[idx], ey[idx]], axis=1)
            ww = w[idx]
            mu = (E * ww[:, None]).sum(0) / ww.sum()
            D = E - mu
            C = (D * ww[:, None]).T @ D / ww.sum()
            ev = np.linalg.eigvalsh(C)
            rs.append(ev[1] / max(ev[0], 1e-12))
        say(f"    post-mean covariance: eigenvalue ratio {st[0]:.3f} "
            f"[{np.percentile(rs,5):.3f}, {np.percentile(rs,95):.3f}], A_Sigma {st[1]:.3f}, "
            f"axis {st[2]:.1f} deg, R_rt {st[3]:.3f}")
        for bi in range(3):
            bm = (R_ >= bedge[bi]) & (R_ <= bedge[bi + 1])
            s2 = cov(bm)
            if s2:
                say(f"      r {bedge[bi]:.0f}-{bedge[bi+1]:.0f}: ratio {s2[0]:.3f}, "
                    f"axis {s2[2]:.1f} deg, R_rt {s2[3]:.3f}")

        # spatial correlation, cross-line pairs
        pos = clip.xy[pairs[:, 0]][keep]
        lineB = np.array([np.searchsorted(clip.starts, ib, side="right") - 1
                          for ia, ib in pairs])[keep]
        D = np.hypot(pos[:, None, 0] - pos[None, :, 0], pos[:, None, 1] - pos[None, :, 1])
        share = (L_[:, None] == L_[None, :]) | (lineB[:, None] == lineB[None, :])

        def acf(E):
            v0 = float((E ** 2).sum(1).mean())
            r_ = []
            for lo, hi in ((40, 130), (130, 250), (250, 400), (400, 700)):
                mk = (D >= lo) & (D < hi) & ~share
                np.fill_diagonal(mk, False)
                if mk.sum() < 40:
                    r_.append(float("nan")); continue
                r_.append(float((E[:, None, :] * E[None, :, :]).sum(-1)[mk].mean() / v0))
            return r_
        a_raw = acf(E_)
        a_mu = acf(np.stack([ex, ey], axis=1))
        say(f"    cross-line spatial correlation, 40-130 / 130-250 / 250-400 / 400-700 px")
        say(f"      raw          " + " ".join(f"{x:+7.3f}" for x in a_raw))
        say(f"      mean removed " + " ".join(f"{x:+7.3f}" for x in a_mu))
        if tag.startswith("Tokina 10 mm / Left"):
            say(f"    TARGETED: m=6 and m=8 tested one at a time against H24")
            for mex in (6, 8):
                Xe, _ = design(R_, P_, [2, 4, mex], r0, r1)
                cve = cv_hier({"H24": Xs["H24"], "E": Xe}, yr, yt, w, fold, 3)
                dd = (cve["H24"][0] - cve["E"][0]) / max(cve["H24"][0], 1e-12)
                say(f"      +m={mex}: MSE {cve['E'][0]:8.5f} vs H24 {cve['H24'][0]:8.5f}, "
                    f"dCV {dd:+7.4f}  {'supported' if dd > 0.02 else 'not supported'}")
        res[mn] = {"rms": wr, "sel": sel, "gain": (cv["H0"][0] - cv[sel][0]) / cv["H0"][0]
                   if sel != "H0" else 0.0, "ang": ang_px, "dom": dom,
                   "eig": st[0], "acf_raw": a_raw[0], "acf_mu": a_mu[0],
                   "lorms": float(np.sqrt((elo[ok] ** 2).sum(1).mean()))}
    return tag, "\n".join(o), res


def main():
    t0 = time.time()
    jobs = [(t, ["M0_2p", "M1_2p"]) for t in ALL]
    summ = {}
    with ProcessPoolExecutor(max_workers=8) as ex:
        for tag, txt, r in ex.map(analyse, jobs):
            print(txt, flush=True)
            summ[tag] = r
    print("\n" + "=" * 118)
    print("PRIMARY TABLE")
    print("=" * 118)
    print(f"  {'clip':28} {'LOO RMS M0->M1':>16} {'selected':>13} {'H0->sel gain':>14} "
          f"{'ang px':>13} {'dom':>7} {'eig ratio':>13} {'NN corr raw':>14} {'NN corr -mu':>14}")
    for tag, r in summ.items():
        a, b = r["M0_2p"], r["M1_2p"]
        print(f"  {tag:28} {a['lorms']:6.3f}->{b['lorms']:<8.3f} "
              f"{a['sel']:>5}->{b['sel']:<6} {a['gain']:+6.3f}->{b['gain']:<+6.3f} "
              f"{a['ang']:5.3f}->{b['ang']:<6.3f} "
              f"{str(a['dom']):>3}->{str(b['dom']):<3} "
              f"{a['eig']:5.2f}->{b['eig']:<6.2f} "
              f"{a['acf_raw']:+6.3f}->{b['acf_raw']:<+6.3f} "
              f"{a['acf_mu']:+6.3f}->{b['acf_mu']:<+6.3f}")
    print(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
