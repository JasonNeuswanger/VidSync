#!/usr/bin/env python3
"""Known-length validation of the anisotropic-radius term.

The question: does adding eta to the production distortion model measure better in millimetres,
on objects whose true length is known?

Design. Every model is refitted from the same plumblines with the same trust-region solver and the
same acceptance gate, then the ENTIRE downstream calibration is rebuilt on top of it -- both
homographies by normalized DLT from re-undistorted frame-node clicks, and the camera position from
the re-undistorted back-node sightlines -- before any length is re-triangulated. Comparing a refit
against the document's stored parameters is NOT the experiment; the stored parameters were fitted to
a different detection of the plumblines, a confound already documented. The experiment is the
isotropic refit against the eta refit, which differ in exactly one parameter and nothing else.

distcal.undistort is monkeypatched with an eta-aware version taking a 14-element vector, so build,
sightline and refine all pick up the conjugated map with no duplicated geometry code. A 13-element
vector, or a 14th element of zero, reproduces the original function exactly; this is asserted at
startup rather than assumed.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


dc = L("distcal")
jw = L("jacweight")
Z = L("round9a")
S = Z.S
ORIG_UNDISTORT = dc.undistort

POOL = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
        "2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
DOCS = [
    ("2012 pool test, Sony Handycam, mild distortion, 1010 known lengths",
     POOL, None, 1000.0),
    ("2015-06-22-1 Clearwater, 13 mm, 57 known lengths",
     os.path.join(DM, "2015-06-22-1 Clearwater.vsd"), "Frame Test", 1.0),
    ("2015-09-04-1 Clearwater, Rokinon 8 mm fisheye, 14 known lengths",
     dc.VSD, "Length Tests", 1.0),
]
MODELS = [("isotropic k1-k4+p1,p2", Z.ISO, False),
          ("with eta  k1-k4+p1,p2+eta", Z.SCAL, False),
          ("isotropic, scale gate enforced", Z.ISO, True),
          ("with eta, scale gate enforced", Z.SCAL, True)]


class GG(Z.G):
    """suite4 geometry with the production acceptance gate as a hard barrier during fitting.

    suite4's own barrier only enforces injectivity (min det J). The shipped gate also caps the
    scale ratio at 4.0, and on the 8 mm fisheye that bound is what binds, so a fit that ignores it
    is not a fit the software would accept.
    """

    def __init__(self, xy, counts, grid, scale_gate):
        super().__init__(xy, counts)
        self.ggrid = grid
        self.scale_gate = scale_gate

    def barrier(self, v):
        c, k, p, a, b = Z.nphys(v)
        dj = Z.jdet(self.ggrid, c, k, p, a, b)
        mg = np.sqrt(np.abs(dj))
        s = 200.0 * math.sqrt(self.n)
        out = [s * max(0.0, 0.05 - float(dj.min()))]
        if self.scale_gate:
            out.append(s * max(0.0, float(mg.max() / max(mg.min(), 1e-12)) - 4.0))
        return np.array(out)


def undistort_eta(x, y, c):
    """Conjugated axis-locked map: U = c + A^-1 B(A(x-c)), A = diag(e^eta, e^-eta)."""
    eta = c[13] if len(c) > 13 else 0.0
    if eta == 0.0:
        return ORIG_UNDISTORT(x, y, c)
    ax = math.exp(eta); ay = 1.0 / ax
    xd = (x - c[0]) * ax
    yd = (y - c[1]) * ay
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c[2:9], start=1))
    T = 1 + c[11] * s + c[12] * s * s
    ux = xd * R + (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T
    uy = yd * R + (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T
    return (c[0] + ux / ax, c[1] + uy / ay)


dc.undistort = undistort_eta


def to_dist14(v):
    """suite4 15-vector -> [x0, y0, k1..k7, p1..p4, eta] in raw pixel units."""
    c, k, p, e, _b = Z.nphys(v)
    return [c[0], c[1], *k, *p, e]


def load_doc(vsd, typefilter):
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    cams = {}
    for pk, clip, ah, av, fd, bd, *dp in db.execute(
            "SELECT c.Z_PK, v.ZCLIPNAME, c.ZAXISHORIZONTAL, c.ZAXISVERTICAL, "
            "c.ZPLANECOORDFRONT, c.ZPLANECOORDBACK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
            "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
            "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
            "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4 FROM ZVSCALIBRATION c "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
        cams[clip] = {"pk": pk, "clip": clip, "ah": ah, "av": av, "front_d": fd, "back_d": bd,
                      "stored": list(dp) + [0.0], "front": [], "back": []}
    bypk = {c["pk"]: c for c in cams.values()}
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION IS NOT NULL ORDER BY ZINDEX"):
        bypk[pk]["back"].append((x, y, h, v))
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION1, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION1 IS NOT NULL ORDER BY ZINDEX"):
        bypk[pk]["front"].append((x, y, h, v))
    clicks = defaultdict(dict)
    for pt, clip, x, y in db.execute(
            "SELECT p.ZPOINT, v.ZCLIPNAME, p.ZSCREENX, p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        clicks[pt][clip] = (x, y)
    sql = ("SELECT o.ZNAME2, t.ZNAME3, e.Z_PK, p.Z_PK, p.ZNEARESTCAMERADISTANCE "
           "FROM ZVSVISIBLEITEM e "
           "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
           "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
           "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
           "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK WHERE e.Z_ENT = 17")
    args = ()
    if typefilter:
        sql += " AND t.ZNAME3 = ?"; args = (typefilter,)
    events, names, rng = defaultdict(list), {}, defaultdict(list)
    for name, tname, ev, pk, ncd in db.execute(sql + " ORDER BY e.Z_PK, p.ZINDEX", args):
        events[ev].append(pk)
        names[ev] = (name, tname)
        if ncd is not None:
            rng[ev].append(ncd)
    db.close()
    return cams, clicks, events, names, rng


def measure(cams, dists, clicks, events, names, rng, unit_mm):
    built = {clip: dc.build(cams[clip], dists[clip]) for clip in cams}
    if any(b["s2f"] is None or b["cam"] is None for b in built.values()):
        return None, None
    rows = []
    for ev, pks in sorted(events.items()):
        if len(pks) != 2:
            continue
        true = jw.true_length_mm(*names[ev], unit_mm)
        if true is None:
            continue
        pos, ok = [], True
        for pk in pks:
            obs = [(built[c], clicks[pk][c]) for c in sorted(built) if c in clicks[pk]]
            if len(obs) < 2:
                ok = False; break
            seed = dc.cpa(dc.sightline(*obs[0][1], obs[0][0]),
                          dc.sightline(*obs[1][1], obs[1][0]))
            if seed is None:
                ok = False; break
            pos.append(dc.refine(obs, seed))
        if ok:
            rows.append({"obj": names[ev][0], "true": true,
                         "meas": math.dist(pos[0], pos[1]) * unit_mm,
                         "rng": (sum(rng[ev]) / len(rng[ev]) * unit_mm) if rng[ev] else None})
    return rows, {c: built[c]["pld"] for c in built}


def stats(rows):
    e = [r["meas"] - r["true"] for r in rows]
    n = len(e); m = sum(e) / n
    return {"n": n, "mae": sum(abs(v) for v in e) / n,
            "rms": math.sqrt(sum(v * v for v in e) / n), "bias": m,
            "sd": math.sqrt(sum((v - m) ** 2 for v in e) / (n - 1)) if n > 1 else 0.0}


def main():
    t0 = time.time()
    say = print

    # startup assertion: the patched map must reproduce the original when eta is zero
    d13 = [960.0, 540.0, -1e-7, 1e-13, 0, 0, 0, 0, 0, 1e-6, -2e-6, 1e-8, 0]
    mx = max(abs(a - b) for x, y in ((100., 200.), (1800., 1000.), (960., 540.))
             for a, b in zip(ORIG_UNDISTORT(x, y, d13), undistort_eta(x, y, d13 + [0.0])))
    say(f"patched undistort reproduces the original at eta=0 to {mx:.1e} px")
    # and it must agree with the suite4 map the fitting was done under
    vv = np.zeros(15); vv[0] = 0.01; vv[1] = -0.02; vv[2] = -0.3; vv[3] = 0.1
    vv[9] = 0.02; vv[10] = -0.01; vv[13] = 0.03
    P = np.array([[100., 200.], [1800., 1000.], [960., 540.], [400., 900.]])
    ref = Z.Uv(P, vv)
    got = np.array([undistort_eta(x, y, to_dist14(vv)) for x, y in P])
    say(f"patched undistort agrees with the fitted suite4 map to "
        f"{np.abs(ref - got).max():.1e} px at eta = +0.030")

    for label, vsd, tf, unit in DOCS:
        say("\n" + "=" * 100)
        say(label)
        say("=" * 100)
        cams, clicks, events, names, rng = load_doc(vsd, tf)
        dists, info = {"document as-is": {}}, {}
        for clip in cams:
            dists["document as-is"][clip] = cams[clip]["stored"]
        clips = {c: S.Clip(vsd, c) for c in sorted(cams)}
        prev = {}

        for mlabel, free, gated in MODELS:
            dists[mlabel] = {}
            for clip in sorted(cams):
                clp = clips[clip]
                g = GG(clp.xy, clp.counts, clp.grid, gated)
                s0 = np.zeros(15)
                s0[0] = (clp.centre0[0] - S.W / 2) / S.R
                s0[1] = (clp.centre0[1] - S.H / 2) / S.R
                seeds = [s0] + [v.copy() for v in prev.get(clip, [])]
                rr = np.random.default_rng(9)
                for _ in range(4):
                    s = seeds[-1].copy(); s[np.array(free)] += rr.normal(0, 0.05, len(free))
                    seeds.append(s)
                if 13 in free:
                    for e in (-0.02, 0.01, 0.02, 0.04):
                        s = seeds[0].copy(); s[13] = e; seeds.append(s)
                for s in seeds:
                    if 13 not in free:
                        s[13] = 0.0
                v, sse, _ = Z.best_fit(g, free, seeds)
                prev.setdefault(clip, []).append(v)
                dj = Z.jdet(clp.grid, *Z.nphys(v))
                mg = np.sqrt(np.abs(dj))
                ratio = float(mg.max() / mg.min())
                dists[mlabel][clip] = to_dist14(v)
                info[(mlabel, clip)] = (math.sqrt(sse / g.n), v[13], float(dj.min()), ratio,
                                        g.nlines, g.n)

        say(f"\n  plumbline refits (identical lines and solver; the scale-ratio bound is enforced")
        say(f"  during fitting only in the last two rows, and only min det J elsewhere):")
        say(f"    {'model':32} {'camera':14} {'lines/pts':>11} {'RMS px':>9} {'eta':>11} "
            f"{'min det':>9} {'ratio':>7} {'gate':>6}")
        for mlabel, _, _ in MODELS:
            for clip in sorted(cams):
                rms, eta, md, ratio, nl, npt = info[(mlabel, clip)]
                say(f"    {mlabel:32} {clip:14} {nl:4d}/{npt:<6d} {rms:9.4f} {eta:+11.7f} "
                    f"{md:9.4f} {ratio:7.3f} "
                    f"{'ok' if md > 0 and ratio <= 4.001 else 'FAIL':>6}")

        res = {}
        for mlabel in dists:
            rows, pld = measure(cams, dists[mlabel], clicks, events, names, rng, unit)
            if rows is None:
                say(f"  {mlabel}: calibration rebuild failed"); continue
            res[mlabel] = rows
            s = stats(rows)
            say(f"\n  {mlabel}: n {s['n']}, mean abs err {s['mae']:.4f} mm, rms {s['rms']:.4f}, "
                f"bias {s['bias']:+.4f}, sd {s['sd']:.4f}")
            say(f"    back-node PLD " + ", ".join(f"{c} {pld[c]*unit:.4f} mm" for c in sorted(pld)))

        for iso, eta, pl in (
                (MODELS[0][0], MODELS[1][0], "scale bound NOT enforced during fitting"),
                (MODELS[2][0], MODELS[3][0], "scale bound enforced during fitting")):
            if iso not in res or eta not in res:
                continue
            say(f"\n  EFFECT OF ADDING ETA, {pl} (mean abs error, mm)")
            say(f"    {'object':30} {'n':>5} {'true':>9} {'isotropic':>12} "
                f"{'with eta':>12} {'change':>10} {'closer':>9}")
            for o in sorted({r["obj"] for r in res[iso]}):
                a = [r for r in res[iso] if r["obj"] == o]
                b = [r for r in res[eta] if r["obj"] == o]
                ea = [abs(r["meas"] - r["true"]) for r in a]
                eb = [abs(r["meas"] - r["true"]) for r in b]
                w = sum(1 for x, y in zip(eb, ea) if x < y)
                say(f"    {str(o):30} {len(a):5d} {a[0]['true']:9.1f} "
                    f"{sum(ea)/len(ea):12.4f} {sum(eb)/len(eb):12.4f} "
                    f"{sum(eb)/len(eb)-sum(ea)/len(ea):+10.4f} {w:4d}/{len(a):<4d}")
            ea = [abs(r["meas"] - r["true"]) for r in res[iso]]
            eb = [abs(r["meas"] - r["true"]) for r in res[eta]]
            w = sum(1 for x, y in zip(eb, ea) if x < y)
            t = sum(1 for x, y in zip(eb, ea) if x == y)
            say(f"    {'ALL':30} {len(ea):5d} {'':>9} {sum(ea)/len(ea):12.4f} "
                f"{sum(eb)/len(eb):12.4f} {sum(eb)/len(eb)-sum(ea)/len(ea):+10.4f} "
                f"{w:4d}/{len(ea)-t:<4d}")
            say(f"    eta closer to truth on {w} of {len(ea)-t} non-tied, sign test p = "
                f"{jw.sign_test(w, len(ea)-t):.4f}")
            d = [x - y for x, y in zip(eb, ea)]
            md_ = sum(d) / len(d)
            sd_ = math.sqrt(sum((v - md_) ** 2 for v in d) / (len(d) - 1))
            say(f"    paired change in absolute error {md_:+.4f} mm, sd {sd_:.4f}, "
                f"se {sd_/math.sqrt(len(d)):.4f}, t = {md_/(sd_/math.sqrt(len(d))):+.2f}")

            have = [r for r in res[iso] if r["rng"] is not None]
            if len(have) > 40:
                qs = np.percentile([r["rng"] for r in have], [33, 67])
                say(f"    by nearest-camera distance (mm):")
                for lo, hi, nm in ((-1e18, qs[0], f"< {qs[0]:.0f}"),
                                   (qs[0], qs[1], f"{qs[0]:.0f} - {qs[1]:.0f}"),
                                   (qs[1], 1e18, f"> {qs[1]:.0f}")):
                    ia = [i for i, r in enumerate(res[iso])
                          if r["rng"] is not None and lo <= r["rng"] < hi]
                    if not ia:
                        continue
                    aa = [abs(res[iso][i]["meas"] - res[iso][i]["true"]) for i in ia]
                    bb = [abs(res[eta][i]["meas"] - res[eta][i]["true"]) for i in ia]
                    say(f"      {nm:20} {len(ia):5d} {sum(aa)/len(aa):12.4f} "
                        f"{sum(bb)/len(bb):12.4f} {sum(bb)/len(bb)-sum(aa)/len(aa):+10.4f}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
