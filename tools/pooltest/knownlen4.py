#!/usr/bin/env python3
"""Definitive known-length run: all three documents, thoroughly seeded.

Supersedes knownlen.py. That version seeded the isotropic fits only from the round-5 solutions and
a zero-centre start, and on the pool test it settled in a worse basin (left camera 0.2551 px where
0.2200 px exists). Comparing two models is only meaningful if each has genuinely reached its own
optimum, so every fit here is seeded from the zero start, the document's own stored parameters
converted into the fitting parameterization, the round-5 solutions where they exist, the previous
model in the sequence, and perturbations of all of those.

Models, all fitted from identical plumblines with an identical trust-region solver and identical
injectivity barrier:
  full-13   x0,y0,k1-k7,p1-p4   what the software ships
  10-param  x0,y0,k1-k4,p1,p2   the reduced model
  11-param  the same plus eta   the anisotropic-radius candidate

The whole downstream calibration is rebuilt under each: both homographies by normalized DLT from
re-undistorted frame-node clicks, and the camera position from re-undistorted back-node sightlines.

Run with ~/.venvs/vidsync/bin/python.
"""

import math
import sys
import time

import numpy as np

import knownlen as K

Z, S, dc, jw = K.Z, K.S, K.dc, K.jw
FULL13 = list(range(13))
MODELS = [("full-13  k1-k7+p1-p4", FULL13),
          ("10-param k1-k4+p1,p2", Z.ISO),
          ("11-param k1-k4+p1,p2+eta", Z.SCAL)]
LENS = {0: "Sony Handycam", 1: None, 2: "Rokinon 8 mm"}


def stored_v(d):
    v = np.zeros(15)
    v[0] = (d[0] - S.W / 2) / S.R
    v[1] = (d[1] - S.H / 2) / S.R
    for j in range(7):
        v[2 + j] = d[2 + j] * S.R ** (2 * (j + 1))
    v[9] = d[9] * S.R; v[10] = d[10] * S.R
    v[11] = d[11] * S.R ** 2; v[12] = d[12] * S.R ** 4
    return v


def paired(res, a, b, lbl, say):
    ea = [abs(r["meas"] - r["true"]) for r in res[a]]
    eb = [abs(r["meas"] - r["true"]) for r in res[b]]
    d = [y - x for x, y in zip(ea, eb)]
    w = sum(1 for x, y in zip(ea, eb) if y < x)
    t = sum(1 for x, y in zip(ea, eb) if y == x)
    m = sum(d) / len(d)
    sd = math.sqrt(sum((v - m) ** 2 for v in d) / (len(d) - 1))
    se = sd / math.sqrt(len(d))
    say(f"    {lbl:44} {m:+9.4f} {se:9.4f} {m/se:+8.2f} {w:5d}/{len(d)-t:<5d} "
        f"{jw.sign_test(w, len(d)-t):10.2e}")
    return m, se


def main():
    t0 = time.time()
    say = print
    for di, (label, vsd, tf, unit) in enumerate(K.DOCS):
        say("\n" + "=" * 104)
        say(label)
        say("=" * 104)
        cams, clicks, events, names, rng = K.load_doc(vsd, tf)
        clips = {c: S.Clip(vsd, c) for c in sorted(cams)}
        dists = {"document as-is": {c: cams[c]["stored"] for c in cams}}
        rmsr = {}
        for mlabel, _ in MODELS:
            dists[mlabel] = {}
        for clip in sorted(cams):
            clp = clips[clip]
            g = Z.G(clp.xy, clp.counts)
            sv = stored_v(cams[clip]["stored"])
            rs = clp.straight(Z.Uv(clp.xy, sv))
            rmsr[("document as-is", clip)] = (math.sqrt(float(rs @ rs) / clp.n), 0.0)
            s0 = np.zeros(15)
            s0[0] = (clp.centre0[0] - S.W / 2) / S.R
            s0[1] = (clp.centre0[1] - S.H / 2) / S.R
            pool = [s0, sv.copy()]
            tag = f"{LENS[di]} / {clip}" if LENS[di] else None
            if tag and tag in Z.ALL:
                for key in ("M0_2p", "M1_2p", "M1_2p_k7"):
                    if key in Z.ALL[tag]:
                        s = np.zeros(15); s[:14] = np.array(Z.ALL[tag][key]["v"])
                        pool.append(s)
            rr = np.random.default_rng(4)
            for mlabel, free in MODELS:
                seeds = [p.copy() for p in pool]
                for _ in range(4):
                    s = seeds[rr.integers(0, len(pool))].copy()
                    s[np.array(free)] += rr.normal(0, 0.03, len(free))
                    seeds.append(s)
                if 13 in free:
                    for e in (-0.02, 0.01, 0.02, 0.04):
                        s = pool[1].copy(); s[13] = e; seeds.append(s)
                # A seed must not smuggle in a parameter the model is not allowed to fit.
                # Without this the ten-parameter model inherits k5-k7 and p3,p4 from the
                # thirteen-parameter seed and is not a ten-parameter model at all.
                held = [j for j in range(15) if j not in free]
                for s in seeds:
                    s[held] = 0.0
                v, sse, _ = Z.best_fit(g, free, seeds)
                pool.append(v)
                dists[mlabel][clip] = K.to_dist14(v)
                dj = Z.jdet(clp.grid, *Z.nphys(v))
                mg = np.sqrt(np.abs(dj))
                rmsr[(mlabel, clip)] = (math.sqrt(sse / g.n), v[13],
                                        float(dj.min()), float(mg.max() / mg.min()))

        say(f"\n  plumbline fits on the current lines")
        say(f"    {'model':26} {'camera':14} {'RMS px':>9} {'eta':>11} {'min det':>9} "
            f"{'ratio':>7} {'gate':>6}")
        for mlabel in dists:
            for clip in sorted(cams):
                r = rmsr[(mlabel, clip)]
                if len(r) == 2:
                    say(f"    {mlabel:26} {clip:14} {r[0]:9.4f} {'':>11} {'':>9} {'':>7} "
                        f"{'':>6}")
                else:
                    say(f"    {mlabel:26} {clip:14} {r[0]:9.4f} {r[1]:+11.7f} {r[2]:9.4f} "
                        f"{r[3]:7.3f} {'ok' if r[2] > 0 and r[3] <= 4.0 else 'FAIL':>6}")

        res = {}
        say(f"\n  known-length accuracy, full calibration rebuilt under each")
        say(f"    {'model':26} {'n':>5} {'mean abs err':>13} {'rms':>9} {'bias':>9} {'sd':>9}")
        for mlabel in dists:
            rows, pld = K.measure(cams, dists[mlabel], clicks, events, names, rng, unit)
            if rows is None:
                say(f"    {mlabel}: rebuild failed"); continue
            res[mlabel] = rows
            s = K.stats(rows)
            say(f"    {mlabel:26} {s['n']:5d} {s['mae']:13.4f} {s['rms']:9.4f} "
                f"{s['bias']:+9.4f} {s['sd']:9.4f}")

        say(f"\n  paired per-measurement comparisons (negative change = improvement)")
        say(f"    {'comparison':44} {'change mm':>9} {'se':>9} {'t':>8} "
            f"{'better':>11} {'sign p':>10}")
        paired(res, "document as-is", MODELS[0][0], "converge properly, same 13 params", say)
        paired(res, MODELS[0][0], MODELS[1][0], "drop to 10 params, both converged", say)
        paired(res, MODELS[1][0], MODELS[2][0], "ADD ETA to the 10-param model", say)
        paired(res, "document as-is", MODELS[2][0], "document -> 11-param with eta", say)

        a, b = MODELS[1][0], MODELS[2][0]
        say(f"\n  effect of eta by object")
        say(f"    {'object':30} {'n':>5} {'true':>8} {'no eta':>10} {'with eta':>10} "
            f"{'change':>9} {'closer':>10}")
        for o in sorted({r["obj"] for r in res[a]}, key=lambda x: str(x)):
            x = [r for r in res[a] if r["obj"] == o]
            y = [r for r in res[b] if r["obj"] == o]
            ea = [abs(r["meas"] - r["true"]) for r in x]
            eb = [abs(r["meas"] - r["true"]) for r in y]
            w = sum(1 for p, q in zip(eb, ea) if p < q)
            say(f"    {str(o):30} {len(x):5d} {x[0]['true']:8.1f} {sum(ea)/len(ea):10.4f} "
                f"{sum(eb)/len(eb):10.4f} {sum(eb)/len(eb)-sum(ea)/len(ea):+9.4f} "
                f"{w:4d}/{len(x):<5d}")
        have = [r for r in res[a] if r["rng"] is not None]
        if len(have) > 40:
            qs = np.percentile([r["rng"] for r in have], [33, 67])
            say(f"    by nearest-camera distance (mm)")
            for lo, hi, nm in ((-1e18, qs[0], f"< {qs[0]:.0f}"),
                               (qs[0], qs[1], f"{qs[0]:.0f} - {qs[1]:.0f}"),
                               (qs[1], 1e18, f"> {qs[1]:.0f}")):
                ia = [i for i, r in enumerate(res[a])
                      if r["rng"] is not None and lo <= r["rng"] < hi]
                if not ia:
                    continue
                aa = [abs(res[a][i]["meas"] - res[a][i]["true"]) for i in ia]
                bb = [abs(res[b][i]["meas"] - res[b][i]["true"]) for i in ia]
                say(f"      {nm:28} {len(ia):5d} {'':>8} {sum(aa)/len(aa):10.4f} "
                    f"{sum(bb)/len(bb):10.4f} {sum(bb)/len(bb)-sum(aa)/len(aa):+9.4f}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
