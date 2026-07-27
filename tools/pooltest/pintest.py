#!/usr/bin/env python3
"""Does fixing the scale gauge beat catching the runaway with a penalty?

The plumbline objective is not scale-invariant: shrinking the undistorted image scales every
residual, so the objective always improves in that direction. Brown-Conrady's leading 1 pins the
radial map only at r = 0, where there is almost no data, and seven radial terms can imitate a
constant over the covered annulus. The acceptance gate catches the resulting runaway after the fact,
and every gated fit in this project has landed exactly on the gate's scale-ratio limit -- meaning the
constraint, not the data, was setting the answer.

The alternative is to fix the gauge by construction: impose R(s_ref) = 1 at a radius inside the data,
so a uniform rescaling is no longer representable at all. This compares the two on the things that
matter -- whether the fit is reproducible, whether it stops pinning against the gate, and above all
whether it measures known lengths better.

Two consequences to expect and not misread. The reported plumbline residual will go *up*, because the
runaway was genuinely lowering it; that number becomes meaningful rather than gameable, and is no
longer comparable with historical values. And the fitted parameter values change even where the map
does not, since a different gauge representative of the same geometry is being reported.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import statistics
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def lm(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


fitter = lm("fitter")
dc = lm("distcal")
mt = lm("modeltest")
VSD = dc.VSD


def sets_for(clip):
    centre, stored, sets = fitter.load(VSD, clip)
    return centre, stored, sets


def main():
    print("=" * 86)
    print("Fixing the scale gauge versus catching the runaway with a penalty")
    print("=" * 86)

    cams, clicks, events, names = mt_load()

    # reference radius: the middle of where the data actually is
    refs = {}
    for clip in cams:
        centre, _, sets = sets_for(clip)
        lines = [L for tc in sorted(sets) for L in sets[tc]]
        pl = fitter.Plumblines(lines)
        r = np.hypot(pl.xy[:, 0] - centre[0], pl.xy[:, 1] - centre[1])
        refs[clip] = (centre, lines, pl, float(np.median(r)))
        print(f"  {clip:14s} {pl.nlines:3d} lines, {pl.n:4d} pts, "
              f"radii {r.min():.0f}-{r.max():.0f} px, pinning at median {refs[clip][3]:.0f}")

    variants = [("penalty only", None), ("scale pinned", "median")]
    models = ["full-13", "k1-k4+p1-p4"]

    print(f"\n  {'model':>14} {'gauge':>14} {'camera':>14} {'rms px':>8} {'ratio':>7} "
          f"{'spread':>9}")
    fits = {}
    for model in models:
        for vname, vkind in variants:
            for clip in cams:
                centre, lines, pl, rref = refs[clip]
                pin = rref if vkind else None
                th, rms = fitter.fit(pl, fitter.MODELS[model], centre, restarts=6, pin=pin)
                ok, md, ratio = fitter.gate(th, pl)
                # reproducibility: refit from a different random stream and compare the maps
                th2, rms2 = fitter.fit(pl, fitter.MODELS[model], centre, restarts=3, pin=pin)
                u1 = fitter.undistort(pl.xy, th)
                u2 = fitter.undistort(pl.xy, th2)
                spread = float(np.sqrt(((u1 - u2) ** 2).sum(axis=1).mean()))
                fits[(model, vname, clip)] = th
                print(f"  {model:>14} {vname:>14} {clip:>14} {rms:8.4f} {ratio:7.2f} "
                      f"{spread:8.3f}p")

    print("\n  'ratio' is the gate's scale-ratio statistic; 3.80 means the fit is sitting exactly")
    print("  on the penalty boundary. 'spread' is how far two independent refits of the same data")
    print("  disagree, in pixels of undistorted position -- a direct measure of reproducibility.")

    print("\n" + "=" * 86)
    print("KNOWN-LENGTH ACCURACY (14 measurements, mm)")
    print("=" * 86)
    print(f"  {'model':>14} {'gauge':>14} {'mean abs err':>13} {'rms':>8} {'bias':>8} {'sd':>8}")
    rows, _ = mt.measure(cams, clicks, events, names, {c: cams[c]["stored"] for c in cams})
    s = mt.summarise(rows)
    print(f"  {'document as-is':>14} {'(stored)':>14} {s['mae']:13.3f} {s['rms']:8.3f} "
          f"{s['bias']:+8.3f} {s['sd']:8.3f}")
    for model in models:
        for vname, _ in variants:
            dists = {c: list(fits[(model, vname, c)]) for c in cams}
            rows, _ = mt.measure(cams, clicks, events, names, dists)
            s = mt.summarise(rows)
            print(f"  {model:>14} {vname:>14} {s['mae']:13.3f} {s['rms']:8.3f} "
                  f"{s['bias']:+8.3f} {s['sd']:8.3f}")
    return 0


def mt_load():
    import sqlite3
    db = sqlite3.connect(f"file:{VSD}?mode=ro", uri=True)
    cams = {}
    for pk, clip, ah, av, fd, bd, *dp in db.execute(
            "SELECT c.Z_PK, v.ZCLIPNAME, c.ZAXISHORIZONTAL, c.ZAXISVERTICAL, "
            "c.ZPLANECOORDFRONT, c.ZPLANECOORDBACK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
            "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
            "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
            "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4 FROM ZVSCALIBRATION c "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
        cams[clip] = {"pk": pk, "clip": clip, "ah": ah, "av": av, "front_d": fd, "back_d": bd,
                      "stored": list(dp), "front": [], "back": []}
    bypk = {c["pk"]: c for c in cams.values()}
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION IS NOT NULL ORDER BY ZINDEX"):
        bypk[pk]["front"].append((x, y, h, v))
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION1, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION1 IS NOT NULL ORDER BY ZINDEX"):
        bypk[pk]["back"].append((x, y, h, v))
    clicks = defaultdict(dict)
    for pt, clip, x, y in db.execute(
            "SELECT p.ZPOINT, v.ZCLIPNAME, p.ZSCREENX, p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        clicks[pt][clip] = (x, y)
    events, names = defaultdict(list), {}
    for name, ev, pk in db.execute(
            "SELECT o.ZNAME2, e.Z_PK, p.Z_PK FROM ZVSVISIBLEITEM e "
            "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
            "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
            "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
            "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK "
            "WHERE e.Z_ENT = 17 AND t.ZNAME3 = 'Length Tests' ORDER BY e.Z_PK, p.ZINDEX"):
        events[ev].append(pk)
        names[ev] = name
    db.close()
    return cams, clicks, events, names


if __name__ == "__main__":
    sys.exit(main())
