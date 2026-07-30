#!/usr/bin/env python3
"""Known-length validation, 8 mm fisheye only, where the acceptance gate actually binds.

Split out from knownlen.py because this is the one document of the three where the shipped
scale-ratio bound of 4.0 is violated by the unconstrained fit. Enforcing it as a kinked penalty
inside a trust-region solve at 1e-15 tolerances does not converge in reasonable time, so the gated
fits here use a moderate penalty with 1e-11 tolerances and the achieved ratio is reported rather
than assumed.

Run with ~/.venvs/vidsync/bin/python.
"""

import math
import sys
import time

import numpy as np
from scipy.optimize import least_squares

import knownlen as K

Z, S, dc, jw = K.Z, K.S, K.dc, K.jw
BLO, BHI = Z.BLO, Z.BHI


class Gated(Z.G):
    def __init__(self, xy, counts, grid, cap):
        super().__init__(xy, counts)
        self.ggrid, self.cap = grid, cap

    def barrier(self, v):
        c, k, p, a, b = Z.nphys(v)
        dj = Z.jdet(self.ggrid, c, k, p, a, b)
        mg = np.sqrt(np.abs(dj))
        s = 200.0 * math.sqrt(self.n)
        out = [s * max(0.0, 0.05 - float(dj.min()))]
        if self.cap:
            r = float(mg.max() / max(mg.min(), 1e-12))
            out.append(s * max(0.0, r - self.cap))
        return np.array(out)


def fitq(g, free, s0, tol=1e-11, nfev=4000):
    free = np.asarray(free)
    s0 = np.clip(np.asarray(s0, float), BLO, BHI)

    def rr(x):
        v = s0.copy(); v[free] = x
        return g.rb(v)
    r = least_squares(rr, s0[free], method="trf", x_scale=1.0,
                      bounds=(BLO[free], BHI[free]),
                      ftol=tol, xtol=tol, gtol=tol, max_nfev=nfev)
    v = s0.copy(); v[free] = r.x
    return v, g.sse(v)


def main():
    t0 = time.time()
    say = print
    label, vsd, tf, unit = K.DOCS[2]
    say("=" * 100); say(label); say("=" * 100)
    cams, clicks, events, names, rng = K.load_doc(vsd, tf)
    clips = {c: S.Clip(vsd, c) for c in sorted(cams)}

    variants = [("isotropic k1-k4+p1,p2", Z.ISO, None),
                ("with eta  k1-k4+p1,p2+eta", Z.SCAL, None),
                ("isotropic, ratio capped at 4.0", Z.ISO, 4.0),
                ("with eta,  ratio capped at 4.0", Z.SCAL, 4.0)]
    dists = {"document as-is": {c: cams[c]["stored"] for c in cams}}
    info = {}
    for mlabel, free, cap in variants:
        dists[mlabel] = {}
        for clip in sorted(cams):
            clp = clips[clip]
            g = Gated(clp.xy, clp.counts, clp.grid, cap)
            s0 = np.zeros(15)
            s0[0] = (clp.centre0[0] - S.W / 2) / S.R
            s0[1] = (clp.centre0[1] - S.H / 2) / S.R
            tag = f"Rokinon 8 mm / {clip}"
            seeds = [s0]
            for key in ("M0_2p", "M1_2p"):
                s = np.zeros(15); s[:14] = np.array(Z.ALL[tag][key]["v"])
                if 13 not in free:
                    s[13] = 0.0
                seeds.append(s)
            best = None
            for s in seeds:
                try:
                    v, sse = fitq(g, free, s)
                except Exception:                            # noqa: BLE001
                    continue
                if best is None or sse < best[1]:
                    best = (v, sse)
            v = best[0]
            dj = Z.jdet(clp.grid, *Z.nphys(v))
            mg = np.sqrt(np.abs(dj))
            ratio = float(mg.max() / mg.min())
            # plumbline RMS excluding the barrier
            rr_ = clp.straight(Z.Uv(clp.xy, v))
            dists[mlabel][clip] = K.to_dist14(v)
            info[(mlabel, clip)] = (math.sqrt(float(rr_ @ rr_) / clp.n), v[13],
                                    float(dj.min()), ratio, clp.nlines, clp.n)

    say(f"\n  {'model':32} {'camera':14} {'lines/pts':>11} {'RMS px':>9} {'eta':>11} "
        f"{'min det':>9} {'ratio':>7} {'gate':>6}")
    for mlabel, _, _ in variants:
        for clip in sorted(cams):
            rms, eta, md, ratio, nl, npt = info[(mlabel, clip)]
            say(f"    {mlabel:32} {clip:14} {nl:4d}/{npt:<6d} {rms:9.4f} {eta:+11.7f} "
                f"{md:9.4f} {ratio:7.3f} {'ok' if md > 0 and ratio <= 4.02 else 'FAIL':>6}")

    res = {}
    for mlabel in dists:
        rows, pld = K.measure(cams, dists[mlabel], clicks, events, names, rng, unit)
        if rows is None:
            say(f"  {mlabel}: rebuild failed"); continue
        res[mlabel] = rows
        s = K.stats(rows)
        say(f"\n  {mlabel}: n {s['n']}, mean abs err {s['mae']:.4f} mm, rms {s['rms']:.4f}, "
            f"bias {s['bias']:+.4f}, sd {s['sd']:.4f}")

    for iso, eta, pl in ((variants[0][0], variants[1][0], "ratio bound NOT enforced"),
                         (variants[2][0], variants[3][0], "ratio capped at 4.0")):
        if iso not in res or eta not in res:
            continue
        say(f"\n  EFFECT OF ADDING ETA, {pl} (mean abs error, mm)")
        say(f"    {'object':22} {'n':>4} {'true':>8} {'isotropic':>11} {'with eta':>11} "
            f"{'change':>10} {'closer':>8}")
        for o in sorted({r["obj"] for r in res[iso]}):
            a = [r for r in res[iso] if r["obj"] == o]
            b = [r for r in res[eta] if r["obj"] == o]
            ea = [abs(r["meas"] - r["true"]) for r in a]
            eb = [abs(r["meas"] - r["true"]) for r in b]
            w = sum(1 for x, y in zip(eb, ea) if x < y)
            say(f"    {str(o):22} {len(a):4d} {a[0]['true']:8.1f} {sum(ea)/len(ea):11.4f} "
                f"{sum(eb)/len(eb):11.4f} {sum(eb)/len(eb)-sum(ea)/len(ea):+10.4f} "
                f"{w:3d}/{len(a):<4d}")
        ea = [abs(r["meas"] - r["true"]) for r in res[iso]]
        eb = [abs(r["meas"] - r["true"]) for r in res[eta]]
        w = sum(1 for x, y in zip(eb, ea) if x < y)
        d = [x - y for x, y in zip(eb, ea)]
        md_ = sum(d) / len(d)
        sd_ = math.sqrt(sum((v - md_) ** 2 for v in d) / (len(d) - 1))
        say(f"    {'ALL':22} {len(ea):4d} {'':>8} {sum(ea)/len(ea):11.4f} "
            f"{sum(eb)/len(eb):11.4f} {md_:+10.4f} {w:3d}/{len(ea):<4d}")
        say(f"    sign test p = {jw.sign_test(w, len(ea)):.4f}; paired change {md_:+.4f} mm, "
            f"se {sd_/math.sqrt(len(d)):.4f}, t = {md_/(sd_/math.sqrt(len(d))):+.2f}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
