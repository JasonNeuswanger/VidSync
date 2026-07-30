#!/usr/bin/env python3
"""Pool test addendum: both refits beat the document by ~10% on 1010 known lengths. Why?

Two candidate causes, and they need separating because only one of them is a recommendation:
  - the model reduction from thirteen parameters to ten, or
  - simply converging the objective properly, which the shipped Nelder-Mead does not.

Fitting the full thirteen with the same trust-region solver isolates them. If full-13 refitted also
beats the document, the gain is convergence. If only the ten-parameter fits beat it, the gain is the
model reduction.

Also reports the plumbline RMS of the document's own stored parameters evaluated on the current
plumblines, which tells us whether the document was fitted to this same data at all.

Run with ~/.venvs/vidsync/bin/python.
"""

import math
import sys
import time

import numpy as np

import knownlen as K

Z, S, dc, jw = K.Z, K.S, K.dc, K.jw
FULL13 = list(range(13))


def main():
    t0 = time.time()
    say = print
    label, vsd, tf, unit = K.DOCS[0]
    say("=" * 100); say(label); say("=" * 100)
    cams, clicks, events, names, rng = K.load_doc(vsd, tf)
    clips = {c: S.Clip(vsd, c) for c in sorted(cams)}

    def stored_v(clip):
        """The document's stored 13 parameters as a suite4 15-vector."""
        d = cams[clip]["stored"]
        v = np.zeros(15)
        v[0] = (d[0] - S.W / 2) / S.R
        v[1] = (d[1] - S.H / 2) / S.R
        for j in range(7):
            v[2 + j] = d[2 + j] * S.R ** (2 * (j + 1))
        v[9] = d[9] * S.R; v[10] = d[10] * S.R
        v[11] = d[11] * S.R ** 2; v[12] = d[12] * S.R ** 4
        return v

    say(f"\n  plumbline RMS on the CURRENT plumblines:")
    say(f"    {'camera':14} {'stored params':>15} {'refit full-13':>15} {'refit 10-param':>15} "
        f"{'refit +eta':>12}")
    dists, info = {"document as-is": {c: cams[c]["stored"] for c in cams}}, {}
    variants = [("refit full-13   k1-k7+p1-p4", FULL13),
                ("refit 10-param  k1-k4+p1,p2", Z.ISO),
                ("refit 11-param  k1-k4+p1,p2+eta", Z.SCAL)]
    for mlabel, free in variants:
        dists[mlabel] = {}
    for clip in sorted(cams):
        clp = clips[clip]
        g = Z.G(clp.xy, clp.counts)
        sv = stored_v(clip)
        rs = clp.straight(Z.Uv(clp.xy, sv))
        row = [math.sqrt(float(rs @ rs) / clp.n)]
        prev = [sv]
        for mlabel, free in variants:
            s0 = np.zeros(15)
            s0[0] = (clp.centre0[0] - S.W / 2) / S.R
            s0[1] = (clp.centre0[1] - S.H / 2) / S.R
            tag = f"Sony Handycam / {clip}"
            seeds = [s0, sv.copy()] + [p.copy() for p in prev]
            for key in ("M0_2p", "M1_2p"):
                s = np.zeros(15); s[:14] = np.array(Z.ALL[tag][key]["v"])
                seeds.append(s)
            for s in seeds:
                if 13 not in free:
                    s[13] = 0.0
            v, sse, _ = Z.best_fit(g, free, seeds)
            prev.append(v)
            dists[mlabel][clip] = K.to_dist14(v)
            row.append(math.sqrt(sse / g.n))
            info[(mlabel, clip)] = v
        say(f"    {clip:14} {row[0]:15.4f} {row[1]:15.4f} {row[2]:15.4f} {row[3]:12.4f}")

    say(f"\n  known-length accuracy, whole calibration rebuilt under each (n = 1010):")
    say(f"    {'model':34} {'mean abs err':>13} {'rms':>9} {'bias':>9} {'sd':>9}")
    res = {}
    for mlabel in dists:
        rows, pld = K.measure(cams, dists[mlabel], clicks, events, names, rng, unit)
        res[mlabel] = rows
        s = K.stats(rows)
        say(f"    {mlabel:34} {s['mae']:13.4f} {s['rms']:9.4f} {s['bias']:+9.4f} {s['sd']:9.4f}")

    base = "document as-is"
    say(f"\n  paired against the document's own parameters:")
    eb = [abs(r["meas"] - r["true"]) for r in res[base]]
    for mlabel in dists:
        if mlabel == base:
            continue
        ea = [abs(r["meas"] - r["true"]) for r in res[mlabel]]
        d = [x - y for x, y in zip(ea, eb)]
        w = sum(1 for x, y in zip(ea, eb) if x < y)
        m = sum(d) / len(d)
        sd = math.sqrt(sum((v - m) ** 2 for v in d) / (len(d) - 1))
        say(f"    {mlabel:34} change {m:+8.4f} mm, se {sd/math.sqrt(len(d)):.4f}, "
            f"t {m/(sd/math.sqrt(len(d))):+7.2f}, closer on {w}/{len(d)}, "
            f"sign p {jw.sign_test(w, len(d)):.2e}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
