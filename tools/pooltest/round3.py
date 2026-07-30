#!/usr/bin/env python3
"""Round 3: four clips, two nuisance structures, global-envelope eta profiles, bound test, geometry.

Documents, exactly two:
  2015-09-04-1 Clearwater.vsd   clips 'Left Camera', 'Right Camera'
  2016-08-13-2 Chena.vsd        clips 'Left Camera', 'Right Camera'

Left and right within a document are approximate paired replicates of one camera design and
recording pipeline; they differ mainly in board orientation and in the arrangement, length and
coverage of the captured lines. Task 4 quantifies exactly those differences so that paired eta
differences can be read against them.

Saves every retained fit to /tmp/round3.npz for the diagnostics script.
Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("normfit", os.path.join(HERE, "normfit.py"))
N = importlib.util.module_from_spec(_s)
_s.loader.exec_module(N)
R, W, H = N.R, N.W, N.H

FOLDER = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
DOCS = [("Clearwater", os.path.join(FOLDER, "2015-09-04-1 Clearwater.vsd")),
        ("Chena", os.path.join(FOLDER, "2016-08-13-2 Chena.vsd"))]
CLIPS = ["Left Camera", "Right Camera"]
# nuisance structures; indices into (xi, ups, a1..a4, q1..q4, eta)
NUIS = {"4p": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        "2p": [0, 1, 2, 3, 4, 5, 6, 7]}
ETAGRID = np.array([-0.004, -0.002, 0.0, 0.002, 0.004, 0.006, 0.007, 0.008, 0.009,
                    0.010, 0.011, 0.012, 0.014, 0.017, 0.020])


class Clip(N.Clip):
    def __init__(self, path, name):
        centre0, stored, sets = N.F.load(path, name)
        self.name = name
        self.lines = [Lg for tc in sorted(sets) for Lg in sets[tc]]
        self.lineset = {i: Lg for i, Lg in enumerate(self.lines)}
        self.xy = np.concatenate([np.asarray(Lg, float) for Lg in self.lines], axis=0)
        n = np.array([len(Lg) for Lg in self.lines])
        self.counts = n
        self.starts = np.concatenate([[0], np.cumsum(n)[:-1]])
        self.n = len(self.xy)
        self.nlines = len(self.lines)
        self.centre0 = np.array(centre0)


def one_fit(clip, free, s0, blo=None, bhi=None):
    blo = N.BLO if blo is None else blo
    bhi = N.BHI if bhi is None else bhi
    s0 = np.clip(np.asarray(s0, float), blo, bhi)

    def rr(w):
        v = s0.copy()
        v[free] = w
        return clip.resid_b(v)
    try:
        r = least_squares(rr, s0[free], method="trf", x_scale=1.0,
                          bounds=(blo[free], bhi[free]),
                          ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
    except Exception:                                        # noqa: BLE001
        return None
    v = s0.copy()
    v[free] = r.x
    return v, clip.sse(v), float(r.optimality)


def multistart(clip, free, base, nstart, rng, spread=0.35, blo=None, bhi=None):
    best, sses = None, []
    for i in range(nstart):
        s = base.copy()
        if i:
            s[free] = s[free] + rng.normal(0.0, spread, len(free))
        got = one_fit(clip, free, s, blo, bhi)
        if got is None:
            continue
        v, c, o = got
        sses.append(c)
        if best is None or c < best[1]:
            best = (v, c, o)
    v, c, o = best
    tol = max(1e-9, 1e-6 * c)
    return {"v": v, "sse": c, "rms": math.sqrt(c / clip.n), "opt": o,
            "nsame": sum(1 for x in sses if abs(x - c) <= tol), "nstart": len(sses)}


def envelope_profile(clip, nfree, v0, v1, rng, nfresh=2, blo=None, bhi=None):
    """Lowest SSE found at each fixed eta, from a branch out of the global M0 solution, a branch
    out of the global M1 solution in both directions, and fresh multistarts at every node."""
    free = np.array(nfree)
    best = {}

    def record(e, v, c):
        if e not in best or c < best[e][1]:
            best[e] = (v, c)

    # branch from M0 upward and downward
    for direction in (1, -1):
        warm = v0.copy()
        grid = ETAGRID[ETAGRID >= 0] if direction > 0 else ETAGRID[ETAGRID <= 0][::-1]
        for e in grid:
            s = warm.copy(); s[10] = e
            got = one_fit(clip, free, s, blo, bhi)
            if got:
                record(float(e), got[0], got[1]); warm = got[0]
    # branch from M1 in both directions
    e1 = v1[10]
    for direction in (1, -1):
        warm = v1.copy()
        grid = ETAGRID[ETAGRID >= e1] if direction > 0 else ETAGRID[ETAGRID <= e1][::-1]
        for e in grid:
            s = warm.copy(); s[10] = e
            got = one_fit(clip, free, s, blo, bhi)
            if got:
                record(float(e), got[0], got[1]); warm = got[0]
    # fresh multistarts at every node
    for e in ETAGRID:
        for _ in range(nfresh):
            s = v1.copy()
            s[free] = s[free] + rng.normal(0.0, 0.35, len(free))
            s[10] = e
            got = one_fit(clip, free, s, blo, bhi)
            if got:
                record(float(e), got[0], got[1])
    return [(e, best[e][1], best[e][0]) for e in sorted(best)]


def jac_sv(clip, v, free):
    eps = 1e-6
    J = []
    for j in free:
        a = v.copy(); a[j] += eps
        b = v.copy(); b[j] -= eps
        J.append((clip.resid(a) - clip.resid(b)) / (2 * eps))
    return np.linalg.svd(np.array(J).T, compute_uv=False)


def geometry(clip):
    """Line orientations, family split, lengths, corner radii, angular coverage by radius."""
    ang, ln = [], []
    for Lg in clip.lines:
        q = np.asarray(Lg, float)
        d = q[-1] - q[0]
        ang.append(math.degrees(math.atan2(d[1], d[0])) % 180)
        ln.append(float(np.linalg.norm(d)))
    ang = np.array(ang); ln = np.array(ln)
    ref = float(np.median(ang))
    fam = np.array([0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for a in ang])
    cen = np.array([W / 2, H / 2])
    d = clip.xy - cen
    r = np.hypot(d[:, 0], d[:, 1])
    phi = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
    cov = []
    for lo, hi in ((0, 300), (300, 600), (600, 900), (900, 1300)):
        m = (r >= lo) & (r < hi)
        if m.sum() < 5:
            cov.append((lo, hi, int(m.sum()), 0.0))
            continue
        hist = np.histogram(phi[m], bins=12, range=(-180, 180))[0]
        cov.append((lo, hi, int(m.sum()), 100.0 * float((hist > 0).sum()) / 12.0))
    return {"ang": ang, "len": ln, "fam": fam, "r": r, "cov": cov,
            "famang": [float(np.median(ang[fam == 0])),
                       float(np.median(ang[fam == 1])) if (fam == 1).any() else float("nan")]}


def main():
    say = lambda *a: print(" ".join(str(x) for x in a), flush=True)
    say("ROUND 3: TWO DOCUMENTS, FOUR CLIPS, AXIS-LOCKED CONJUGATED ANISOTROPY")
    say("  2015-09-04-1 Clearwater.vsd   clips 'Left Camera', 'Right Camera'")
    say("  2016-08-13-2 Chena.vsd        clips 'Left Camera', 'Right Camera'")
    say(f"  R = {R:.0f} px, radial order k1..k4, axis-locked eta, no free axis.")
    say("  Bounds: centre +/-0.25 R, alpha and q in [-5,5], eta in [-0.05,0.05];")
    say("  soft barrier on positive Jacobian determinant. Scale-ratio gate reported only.")

    clips = {}
    for dname, path in DOCS:
        for cname in CLIPS:
            clips[(dname, cname)] = Clip(path, cname)

    # ---------------- Task 4: geometry ----------------
    say("\n" + "=" * 104)
    say("TASK 4  CALIBRATION GEOMETRY OF THE FOUR CLIPS")
    say("=" * 104)
    for key, clip in clips.items():
        g = geometry(clip)
        say(f"\n  {key[0]} / {key[1]}: {clip.nlines} lines, {clip.n} line-point observations")
        say(f"    family A median orientation {g['famang'][0]:7.2f} deg, n={int((g['fam']==0).sum())}"
            f"    family B {g['famang'][1]:7.2f} deg, n={int((g['fam']==1).sum())}"
            f"    families differ by {abs(g['famang'][0]-g['famang'][1]):.1f} deg")
        q = np.percentile(g["ang"], [5, 50, 95])
        say(f"    line orientation percentiles 5/50/95: {q[0]:.1f} / {q[1]:.1f} / {q[2]:.1f} deg")
        q = np.percentile(g["len"], [10, 50, 90])
        say(f"    line length px 10/50/90: {q[0]:.0f} / {q[1]:.0f} / {q[2]:.0f}   "
            f"max {g['len'].max():.0f}")
        q = np.percentile(g["r"], [5, 25, 50, 75, 95])
        say(f"    corner radius from frame centre 5/25/50/75/95: " +
            " / ".join(f"{x:.0f}" for x in q))
        say(f"    angular coverage by radius band (n, percent of 30-deg sectors occupied):")
        for lo, hi, n_, pc in g["cov"]:
            say(f"      r {lo:4d}-{hi:4d}: n {n_:4d}, coverage {pc:5.1f}%")

    # ---------------- Tasks 1 and 2: fits ----------------
    say("\n" + "=" * 104)
    say("TASKS 1 AND 2  FITS AND GLOBAL-ENVELOPE ETA PROFILES")
    say("=" * 104)
    store = {}
    for key, clip in clips.items():
        for nn, nfree in NUIS.items():
            free0 = np.array(nfree)
            free1 = np.array(nfree + [10])
            base = np.zeros(11)
            base[0] = (clip.centre0[0] - W / 2) / R
            base[1] = (clip.centre0[1] - H / 2) / R
            rng = np.random.default_rng(101)
            t0 = time.time()
            m0 = multistart(clip, free0, base, 16, rng)
            b1 = m0["v"].copy()
            m1 = multistart(clip, free1, b1, 16, rng)
            # ensure the anisotropic solution also sees fresh starts far from M0
            m1b = multistart(clip, free1, base, 10, rng)
            if m1b["sse"] < m1["sse"]:
                m1 = m1b
            prof = envelope_profile(clip, nfree, m0["v"], m1["v"], rng)
            dt = time.time() - t0
            e0 = [p for p in prof if abs(p[0]) < 1e-12]
            envzero = e0[0][1] if e0 else float("nan")
            if envzero < m0["sse"] - max(1e-9, 1e-8 * m0["sse"]):
                m0 = {"v": e0[0][2], "sse": envzero,
                      "rms": math.sqrt(envzero / clip.n), "opt": float("nan"),
                      "nsame": -1, "nstart": m0["nstart"]}
            pmin = min(p[1] for p in prof)
            store[(key[0], key[1], nn)] = {"m0": m0, "m1": m1, "prof": prof}
            c1, k1, p1, e1 = N.norm_to_phys(m1["v"])
            c0_, k0_, p0_, _ = N.norm_to_phys(m0["v"])
            sv1 = jac_sv(clip, m1["v"], free1)
            sv0 = jac_sv(clip, m0["v"], free0)
            u1 = (clip.xy - c1) * N.amat(e1)
            u0 = clip.xy - c0_
            md1, gr1 = N.gate_stats(clip, m1["v"])
            md0, gr0 = N.gate_stats(clip, m0["v"])
            ab = [N.NORMNAMES[j] for j in free1
                  if abs(m1["v"][j] - N.BLO[j]) < 1e-7 or abs(m1["v"][j] - N.BHI[j]) < 1e-7]
            say(f"\n  --- {key[0]} / {key[1]} / nuisance {nn} "
                f"({clip.nlines} lines, {clip.n} obs) ---")
            say(f"    M0 eta=0 : RMS {m0['rms']:.6f}  SSE {m0['sse']:.4f}  "
                f"opt {m0['opt']:.2e}  starts {m0['nsame']}/{m0['nstart']}")
            say(f"       centre ({c0_[0]:.2f}, {c0_[1]:.2f})  "
                f"alpha " + " ".join(f"{m0['v'][2+j]:+.5f}" for j in range(4)) +
                "  q " + " ".join(f"{m0['v'][6+j]:+.5f}" for j in range(4)))
            say(f"       max radial {np.linalg.norm(N.delta_r(u0,k0_),axis=1).max():.1f} px, "
                f"max decentering {np.linalg.norm(N.d_p(u0,p0_),axis=1).max():.2f} px; "
                f"min det {md0:+.4f}, scale ratio {gr0:.3f}")
            say(f"       scaled singular values " +
                np.array2string(sv0, precision=3, max_line_width=250))
            say(f"       condition {sv0[0]/sv0[-1]:.3e}")
            say(f"    M1 free eta: RMS {m1['rms']:.6f}  SSE {m1['sse']:.4f}  "
                f"opt {m1['opt']:.2e}  starts {m1['nsame']}/{m1['nstart']}")
            say(f"       eta {e1:+.7f}  e_legacy {math.tanh(e1):+.7f}  "
                f"exp(2eta) {math.exp(2*e1):.7f}")
            say(f"       RMS reduction vs matching M0 {100*(1-m1['rms']/m0['rms']):+.2f}%")
            say(f"       centre ({c1[0]:.2f}, {c1[1]:.2f})  "
                f"alpha " + " ".join(f"{m1['v'][2+j]:+.5f}" for j in range(4)) +
                "  q " + " ".join(f"{m1['v'][6+j]:+.5f}" for j in range(4)))
            say(f"       max radial {np.linalg.norm(N.delta_r(u1,k1),axis=1).max():.1f} px, "
                f"max decentering {np.linalg.norm(N.d_p(u1,p1),axis=1).max():.2f} px; "
                f"min det {md1:+.4f}, scale ratio {gr1:.3f}")
            say(f"       scaled singular values " +
                np.array2string(sv1, precision=3, max_line_width=250))
            say(f"       condition {sv1[0]/sv1[-1]:.3e}   active bounds "
                f"{ab if ab else 'none'}")
            ok = abs(envzero - m0["sse"]) <= max(1e-6, 1e-6 * m0["sse"])
            say(f"    envelope profile: min {pmin:.4f} at eta "
                f"{[p[0] for p in prof if p[1]==pmin][0]:+.4f}; "
                f"value at eta=0 {envzero:.4f} vs best M0 {m0['sse']:.4f} -> "
                f"{'PROFILE (reproduces M0)' if ok else 'LOCAL BRANCH ONLY'}")
            say("    eta / SSE / excess over profile min:")
            for e, c, _ in prof:
                say(f"      {e:+.4f}  {c:12.4f}  {c-pmin:+11.4f}")
            say(f"    ({dt:.0f}s)")

    np.savez("/tmp/round3.npz",
             **{f"{a}|{b}|{c}|{w}": store[(a, b, c)][w]["v"]
                for (a, b, c) in store for w in ("m0", "m1")})

    # ---------------- Task 3: q3 bound ----------------
    say("\n" + "=" * 104)
    say("TASK 3  q3 / q4 BOUND TEST")
    say("=" * 104)
    for key in [k for k in store if k[2] == "4p"]:
        v = store[key]["m1"]["v"]
        onb = [j for j in (8, 9) if abs(v[j] - N.BLO[j]) < 1e-7 or abs(v[j] - N.BHI[j]) < 1e-7]
        if not onb:
            continue
        clip = clips[(key[0], key[1])]
        say(f"\n  {key[0]} / {key[1]} lands on bound(s) {[N.NORMNAMES[j] for j in onb]}")
        say(f"    {'|q3,q4| bound':>14} {'SSE':>12} {'eta':>11} {'q1':>9} {'q2':>9} "
            f"{'q3':>9} {'q4':>9} {'dec rms':>9} {'dec max':>9} {'min det':>9} {'on bound'}")
        for B in (5.0, 10.0, 20.0):
            blo, bhi = N.BLO.copy(), N.BHI.copy()
            blo[8] = blo[9] = -B
            bhi[8] = bhi[9] = +B
            rng = np.random.default_rng(5)
            m = multistart(clip, np.array(NUIS["4p"] + [10]), v.copy(), 10, rng,
                           blo=blo, bhi=bhi)
            c, k, p, e = N.norm_to_phys(m["v"])
            u = (clip.xy - c) * N.amat(e)
            dv = np.linalg.norm(N.d_p(u, p), axis=1)
            md, _ = N.gate_stats(clip, m["v"])
            onb2 = any(abs(m["v"][j] - blo[j]) < 1e-7 or abs(m["v"][j] - bhi[j]) < 1e-7
                       for j in (8, 9))
            say(f"    {B:14.0f} {m['sse']:12.4f} {e:+11.7f} {m['v'][6]:+9.5f} "
                f"{m['v'][7]:+9.5f} {m['v'][8]:+9.4f} {m['v'][9]:+9.4f} "
                f"{np.sqrt((dv**2).mean()):9.3f} {dv.max():9.3f} {md:+9.4f}   {onb2}")
        m2 = store[(key[0], key[1], "2p")]["m1"]
        c, k, p, e = N.norm_to_phys(m2["v"])
        u = (clip.xy - c) * N.amat(e)
        dv = np.linalg.norm(N.d_p(u, p), axis=1)
        say(f"    p1,p2-only comparison: SSE {m2['sse']:.4f}, eta {e:+.7f}, "
            f"dec rms {np.sqrt((dv**2).mean()):.3f}, dec max {dv.max():.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
