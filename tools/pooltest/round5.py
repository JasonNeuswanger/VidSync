#!/usr/bin/env python3
"""Targeted correction and extraction round on the four-document suite.

Refits with better 4p seeding (including the known Rokinon Left basin), extracts the full
k1..k7 results the previous round computed but did not report, and runs the Tokina 10 mm Left
diagnostic and the higher-decentering gauge diagnostic. No new documents, no broad multistart.

Run with ~/.venvs/vidsync/bin/python.
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
S = importlib.util.module_from_spec(_s)
_s.loader.exec_module(S)
R, W, H, ETA, M, BLO, BHI, NAMES = S.R, S.W, S.H, S.ETA, S.M, S.BLO, S.BHI, S.NAMES

# The known better Rokinon Left 4p basin, in the same normalized coordinates.
KNOWN_ROK_L = np.zeros(14)
KNOWN_ROK_L[0] = (964.4376 - 960.0) / R
KNOWN_ROK_L[1] = (537.6028 - 540.0) / R
KNOWN_ROK_L[2:6] = [0.472772, 0.525853, -0.318104, 0.429383]
KNOWN_ROK_L[9:13] = [-0.005379, -0.000828, -2.813777, 3.496022]
KNOWN_ROK_L[13] = 0.00834442


def worker(job):
    lens, path, cname = job
    tag = f"{lens} / {cname}"
    o = []
    say = o.append
    clip = S.Clip(path, cname)
    rng = np.random.default_rng(23)
    base = np.zeros(14)
    base[0] = (clip.centre0[0] - W / 2) / R
    base[1] = (clip.centre0[1] - H / 2) / R
    res = {}
    res["M0_2p"] = S.fitm(clip, M["M0_2p"], base, rng)
    b = res["M0_2p"]["v"].copy(); b[ETA] = 0.0
    res["M1_2p"] = S.fitm(clip, M["M1_2p"], b, rng)

    # 4p with a deliberately richer seed set: 2p-embedded, perturbations, and any known basin
    seeds4 = []
    for src in (res["M0_2p"]["v"], res["M1_2p"]["v"]):
        s = src.copy(); s[11] = s[12] = 0.0
        seeds4.append(s)
    for _ in range(3):
        s = res["M1_2p"]["v"].copy()
        s[9:13] = s[9:13] + rng.normal(0, 0.15, 4)
        s[11] = np.clip(s[11] + rng.normal(0, 2.0), -10, 10)
        s[12] = np.clip(s[12] + rng.normal(0, 2.0), -10, 10)
        seeds4.append(s)
    if lens.startswith("Rokinon") and cname == "Left Camera":
        seeds4.insert(0, KNOWN_ROK_L.copy())
        say("    (known Rokinon Left 4p basin seeded first)")

    def best_of(free, seeds):
        bb = None
        cnt = 0
        for s in seeds:
            g = S.fit1(clip, np.array(free), s)
            if g is None:
                continue
            if bb is None or g[1] < bb[1] - 1e-9:
                bb, cnt = g, 1
            elif abs(g[1] - bb[1]) <= max(1e-9, 1e-6 * bb[1]):
                cnt += 1
        v, c, opt = bb
        return {"v": v, "sse": c, "rms": math.sqrt(c / clip.n), "opt": opt,
                "nsame": cnt, "nstart": len(seeds), "free": np.array(free)}

    s0_4 = [s.copy() for s in seeds4]
    for s in s0_4:
        s[ETA] = 0.0
    res["M0_4p"] = best_of(M["M0_4p"], s0_4)
    res["M1_4p"] = best_of(M["M1_4p"], seeds4)

    # k1..k7 with the two requested starts
    s7a = res["M1_2p"]["v"].copy()
    s7b = s7a.copy(); s7b[6:9] = rng.normal(0, 0.1, 3)
    res["M1_2p_k7"] = best_of(M["M1_2p_k7"], [s7a, s7b])
    # verify the embedded k1..k4 solution reproduces its SSE inside the k7 code path
    emb = clip.sse(s7a)

    out = {"tag": tag, "lens": lens, "clip": cname, "n": clip.n, "nlines": clip.nlines,
           "emb_check": abs(emb - res["M1_2p"]["sse"]), "log": o}
    for nm, r in res.items():
        c, k, p, e = S.nphys(r["v"])
        sv, cond = S.svcond(clip, r["v"], r["free"])
        u = (clip.grid - c) * S.amat(e)
        dj = S.jdet(clip.grid, c, k, p, e)
        ab = [NAMES[j] for j in r["free"]
              if abs(r["v"][j] - BLO[j]) < 1e-7 or abs(r["v"][j] - BHI[j]) < 1e-7]
        out[nm] = {"v": r["v"].tolist(), "sse": r["sse"], "rms": r["rms"], "opt": r["opt"],
                   "nsame": r["nsame"], "nstart": r["nstart"], "eta": e, "cond": cond,
                   "sv": sv.tolist(), "bounds": ab, "mindet": float(dj.min()),
                   "maxrad": float(np.linalg.norm(S.delta_r(u, k), axis=1).max()),
                   "maxdec": float(np.linalg.norm(S.d_p(u, p), axis=1).max()),
                   "centre": c.tolist()}
    return out


def main():
    import sqlite3
    jobs = []
    for lens, path in S.SUITE:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        for (cn,) in db.execute("SELECT v.ZCLIPNAME FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v "
                                "ON v.Z_PK=c.ZVIDEOCLIP ORDER BY v.ZCLIPNAME"):
            jobs.append((lens, path, cn))
        db.close()
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=8) as ex:
        allr = list(ex.map(worker, jobs))
    print(f"refit of {len(allr)} clips in {time.time()-t0:.0f}s\n", flush=True)
    np.save("/tmp/round5.npy", np.array(allr, dtype=object), allow_pickle=True)

    print("=" * 108)
    print("TASK 2 AND 3  CORRECTED 2p VERSUS 4p, ALL CLIPS")
    print("=" * 108)
    print(f"  {'clip':22} {'M1_2p SSE':>11} {'M1_4p SSE':>11} {'dSSE':>9} {'%':>7} "
          f"{'eta 2p':>10} {'eta 4p':>10} {'cond ratio':>11} {'maxdec':>8} {'bounds':>8} "
          f"{'basin':>7}")
    for r in allr:
        a, b = r["M1_2p"], r["M1_4p"]
        d = a["sse"] - b["sse"]
        print(f"  {r['tag']:22} {a['sse']:11.4f} {b['sse']:11.4f} {d:9.4f} "
              f"{100*d/a['sse']:6.2f}% {a['eta']:+10.6f} {b['eta']:+10.6f} "
              f"{b['cond']/a['cond']:11.1f} {b['maxdec']:8.2f} "
              f"{','.join(b['bounds']) if b['bounds'] else 'none':>8} "
              f"{b['nsame']}/{b['nstart']:>3}")
    print("\n  M0_4p baselines (for reference; several remain constrained):")
    for r in allr:
        b = r["M0_4p"]
        print(f"  {r['tag']:22} SSE {b['sse']:11.4f} RMS {b['rms']:.6f} cond {b['cond']:9.2e} "
              f"bounds {','.join(b['bounds']) if b['bounds'] else 'none':>8} "
              f"maxdec {b['maxdec']:8.2f} mindet {b['mindet']:+.4f} basin {b['nsame']}/{b['nstart']}")

    print("\n" + "=" * 108)
    print("TASK 4  k1..k4 VERSUS k1..k7, BOTH WITH p1,p2 AND eta")
    print("=" * 108)
    for r in allr:
        a, b = r["M1_2p"], r["M1_2p_k7"]
        d = a["sse"] - b["sse"]
        print(f"\n  {r['tag']}  (N={r['n']})")
        print(f"    embedded k1..k4 solution re-evaluated in the k7 path: SSE difference "
              f"{r['emb_check']:.3e}")
        print(f"    k1..k4 SSE {a['sse']:11.4f} RMS {a['rms']:.6f}   ->   "
              f"k1..k7 SSE {b['sse']:11.4f} RMS {b['rms']:.6f}")
        print(f"    improvement {d:9.4f} SSE ({100*d/a['sse']:+.2f}%), nesting satisfied "
              f"{b['sse'] <= a['sse'] + 1e-9}")
        print(f"    eta {a['eta']:+.7f} -> {b['eta']:+.7f}, change {b['eta']-a['eta']:+.7f}")
        print(f"    alpha1..7 " + " ".join(f"{b['v'][2+j]:+.5f}" for j in range(7)))
        print(f"    condition {a['cond']:.3e} -> {b['cond']:.3e} (x{b['cond']/a['cond']:.1f}); "
              f"min det {b['mindet']:+.5f}; max radial {b['maxrad']:.1f} px")
        print(f"    optimality {b['opt']:.2e}; bounds "
              f"{','.join(b['bounds']) if b['bounds'] else 'none'}; "
              f"both starts agree: {b['nsame'] >= 2}")
        print(f"    smallest three scaled singular values " +
              " ".join(f"{x:.3e}" for x in b['sv'][-3:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
