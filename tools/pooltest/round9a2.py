#!/usr/bin/env python3
"""Round 9a follow-up: is the free-axis gain real, and could isotropic misspecification fake the
Left/Right disagreement?

Three questions the first pass left open.
  A. The Right free-axis b landed on its box bound with a scale ratio above the production gate.
     Profile b all the way to the bound and record admissibility at each step.
  B. In-sample SSE cannot promote a model. Compare isotropic, scalar and free-axis by held-out
     straightness on line-cluster folds.
  C. Twenty replicates cannot resolve a one-percent tail. Run 200 under a common isotropic truth
     and measure how often the observed Left/Right split appears by chance.

Run with ~/.venvs/vidsync/bin/python.
"""

import math
import sys
import time

import numpy as np

import round9a as Z

S, R, ETA, BIDX = Z.S, Z.R, Z.ETA, Z.BIDX
TAGS, SHORT = Z.TAGS, Z.SHORT
NFOLD = 6


def gate(gr, v):
    """Evaluated on suite4's own disc-masked grid, the domain every previously reported scale
    ratio used."""
    c, k, p, a, b = Z.nphys(v)
    dj = Z.jdet(gr, c, k, p, a, b)
    mg = np.sqrt(np.abs(dj))
    return float(dj.min()), float(mg.max() / mg.min())


def zero_out(v, free):
    """A seed must not smuggle a parameter the model is not allowed to use."""
    s = v.copy()
    for j in (ETA, BIDX):
        if j not in free:
            s[j] = 0.0
    return s


def cv_lines(g, free, seed0, nfold=NFOLD, seed=13):
    """Held-out straightness: fit the distortion on training lines, score on held-out lines."""
    rng = np.random.default_rng(seed)
    li = Z.line_info(g, seed0)
    order = {f: rng.permutation(np.where(li["fam"] == f)[0]) for f in (0, 1)}
    fold = np.empty(g.nlines, int)
    for f in (0, 1):
        for i, l in enumerate(order[f]):
            fold[l] = i % nfold
    tot, cnt = 0.0, 0
    for k in range(nfold):
        tr, te = fold != k, fold == k
        if te.sum() == 0 or tr.sum() < 6:
            continue
        gtr = Z.subset(g, tr)
        v = Z.fit(gtr, free, seed0.copy())[0]
        gte = Z.subset(g, te)
        r = gte.straight(Z.Uv(gte.xy, v))
        tot += float(r @ r); cnt += gte.n
    return math.sqrt(tot / cnt), cnt


def main():
    t0 = time.time()
    say = print
    dat = {}
    for tg in TAGS:
        g, clip = Z.load_clip(tg)
        v1 = np.zeros(15); v1[:14] = np.array(Z.ALL[tg]["M1_2p"]["v"])
        v0 = np.zeros(15); v0[:14] = np.array(Z.ALL[tg]["M0_2p"]["v"])
        dat[tg] = {"g": g, "v1": v1, "v0": v0, "li": Z.line_info(g, v1),
                   "grid": clip.grid}

    say("=" * 108)
    say("A  THE FREE-AXIS b PROFILED OUT TO ITS BOX BOUND, WITH ADMISSIBILITY")
    say("=" * 108)
    say("  The production acceptance gate requires min det J > 0 and scale ratio <= 4.0.")
    for tg in TAGS:
        d = dat[tg]; g = d["g"]
        seeds = [d["v1"].copy(), d["v0"].copy()]
        vf = Z.best_fit(g, Z.FREEAX, seeds + [_s(d["v1"], b) for b in
                                              (-.04, -.02, .02, .04)])[0]
        say(f"\n  {SHORT[tg]}   free-axis optimum a {vf[ETA]:+.7f}  b {vf[BIDX]:+.7f}")
        say(f"    {'b':>8} {'SSE':>11} {'a at that b':>13} {'min det':>10} {'scale ratio':>12} "
            f"{'gate':>7}")
        fr = [j for j in Z.FREEAX if j != BIDX]
        for b in (0.0, 0.005, 0.01, 0.02, 0.03, 0.04, 0.045, 0.05):
            s = vf.copy(); s[BIDX] = b
            v = Z.fit(g, fr, s)[0]
            md, sr = gate(d["grid"], v)
            say(f"    {b:+8.3f} {g.sse(v):11.5f} {v[ETA]:+13.7f} {md:10.4f} {sr:12.3f} "
                f"{'ok' if md > 0 and sr <= 4.0 else 'FAIL':>7}")
        md, sr = gate(d["grid"], d["v1"])
        say(f"    scalar model for comparison: min det {md:.4f}, scale ratio {sr:.3f}, "
            f"{'ok' if md > 0 and sr <= 4.0 else 'FAIL'}")

    say("\n" + "=" * 108)
    say("B  HELD-OUT STRAIGHTNESS ON LINE-CLUSTER FOLDS (in-sample SSE cannot promote a model)")
    say("=" * 108)
    say(f"  {NFOLD} folds, whole lines held out and stratified by family; the distortion is fitted")
    say("  on training lines only and scored on the straightness of held-out lines.")
    say(f"\n  {'clip':7} {'model':12} {'in-sample RMS':>15} {'held-out RMS':>14} "
        f"{'held-out pts':>13}")
    for tg in TAGS:
        d = dat[tg]; g = d["g"]
        for nm, free in (("isotropic", Z.ISO), ("scalar eta", Z.SCAL),
                         ("free axis", Z.FREEAX)):
            seeds = [zero_out(d["v0"], free), zero_out(d["v1"], free)]
            if free is Z.FREEAX:
                seeds += [_s(d["v1"], b) for b in (0.005, 0.02, 0.05, -0.02)]
            vin = Z.best_fit(g, free, seeds)[0]
            ins = math.sqrt(g.sse(vin) / g.n)
            ho, cnt = cv_lines(g, free, zero_out(d["v1"], free))
            say(f"  {SHORT[tg]:7} {nm:12} {ins:15.6f} {ho:14.6f} {cnt:13d}")

    say("\n" + "=" * 108)
    say("C  HOW OFTEN A COMMON ISOTROPIC TRUTH FAKES THE OBSERVED SPLIT (200 replicates)")
    say("=" * 108)
    rows = {tg: Z.truth_from_intersections(dat[tg]["g"], dat[tg]["v0"], dat[tg]["li"])
            for tg in TAGS}
    NREP = 200
    obsL, obsR = dat[TAGS[0]]["v1"][ETA], dat[TAGS[1]]["v1"][ETA]
    est = {}
    for tg in TAGS:
        d = dat[tg]
        c, k, p, _, _ = Z.nphys(d["v0"])

        def fwd(u, c=c, k=k, p=p):
            t = u - c
            rr = np.hypot(t[:, 0], t[:, 1])
            bump = 0.5 * np.exp(-((rr / R - 0.75) / 0.15) ** 2)
            return c + t + S.delta_r(t, k) + S.d_p(t, p) + t * (bump / np.maximum(rr, 1e-9))[:, None]
        X, cnt, Ut = Z.build_synth(rows[tg], fwd)
        gs = Z.G(X, cnt)
        real = d["g"].straight(Z.Uv(d["g"].xy, d["v1"]))
        blocks = [real[d["g"].starts[i]:d["g"].starts[i] + d["g"].counts[i]]
                  for i in range(d["g"].nlines)]
        nrm = np.empty((gs.n, 2))
        for i in range(gs.nlines):
            a, b = gs.starts[i], gs.starts[i] + gs.counts[i]
            q = gs.xy[a:b] - gs.xy[a:b].mean(0)
            th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                                  float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            nrm[a:b] = [-math.sin(th), math.cos(th)]
        rng = np.random.default_rng(2024)
        out = []
        for _ in range(NREP):
            pert = np.empty(gs.n)
            for i in range(gs.nlines):
                a, b = gs.starts[i], gs.starts[i] + gs.counts[i]
                blk = blocks[rng.integers(0, len(blocks))]
                reps = int(np.ceil((b - a) / len(blk)))
                pert[a:b] = np.tile(blk, reps)[:b - a] * rng.choice([-1.0, 1.0])
            g2 = Z.G(gs.xy + nrm * pert[:, None], cnt)
            s0 = d["v0"].copy(); s0[ETA] = 0.0
            try:
                out.append(Z.fit(g2, Z.SCAL, s0)[0][ETA])
            except Exception:                                # noqa: BLE001
                pass
        est[tg] = np.array(out)
        say(f"  {SHORT[tg]}: {len(out)} replicates, mean {np.mean(out):+.7f}, "
            f"sd {np.std(out, ddof=1):.7f}, 2.5th {np.percentile(out,2.5):+.7f}, "
            f"97.5th {np.percentile(out,97.5):+.7f}")
    L, Rr = est[TAGS[0]], est[TAGS[1]]
    n = min(len(L), len(Rr))
    pl = float(np.mean(L <= obsL))
    pr = float(np.mean(np.abs(Rr) <= 0.0005))
    pj = float(np.mean((L[:n] <= obsL) & (np.abs(Rr[:n]) <= 0.0005)))
    say(f"\n  observed Left {obsL:+.7f}, Right {obsR:+.7f}")
    say(f"    P(Left replicate <= observed Left)            {pl:.3f}")
    say(f"    P(|Right replicate| <= 0.0005)                {pr:.3f}")
    say(f"    P(both, pairing replicates independently)     {pj:.3f}  (product {pl*pr:.4f})")
    say(f"    difference L-R: observed {obsL-obsR:+.7f}, replicate mean "
        f"{np.mean(L[:n]-Rr[:n]):+.7f}, sd {np.std(L[:n]-Rr[:n], ddof=1):.7f}, "
        f"P(<= observed) {float(np.mean(L[:n]-Rr[:n] <= obsL-obsR)):.3f}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


def _s(v, b):
    s = v.copy(); s[BIDX] = b
    return s


if __name__ == "__main__":
    sys.exit(main())
