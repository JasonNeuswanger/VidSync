#!/usr/bin/env python3
"""Judge candidate distortion models on known lengths, not on residuals.

The held-out plumbline comparison favours a ten-parameter model (x0, y0, k1-k4, p1-p4) over the
shipped thirteen. This asks the only question that decides whether that should ship: does it measure
better? Three times in this project a better calibration residual has accompanied *worse*
measurements, so nothing gets recommended on a residual.

For each candidate model, both cameras' distortion is refitted from their own plumblines with the
acceptance gate enforced, then the whole downstream calibration is rebuilt on top of it -- both
homographies from the frame node clicks by normalized DLT, and the camera position from the back-node
sightlines -- and all 14 `Length Tests` measurements are re-triangulated.

Refraction correction of the back-plane nodes is not replicated, so absolute errors sit slightly
above the document's own. That is harmless because every model is treated identically and only the
comparison between them is being read; as a fidelity check, the document's own stored distortion run
through this same rebuild gives 2.879 mm against the exact harness's 2.971 mm.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import re
import statistics
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fitter = load_module("fitter")
dc = load_module("distcal")

CANDIDATES = ["full-13", "k1-k5+p1-p4", "k1-k4+p1-p4", "k1-k3+p1-p4"]


def fit_camera(vsd, clip, model, restarts=6):
    """Refit one camera's distortion from all its plumblines, gate enforced."""
    centre, stored, sets = fitter.load(vsd, clip)
    lines = [L for tc in sorted(sets) for L in sets[tc]]
    pl = fitter.Plumblines(lines)
    theta, rms = fitter.fit(pl, fitter.MODELS[model], centre, restarts=restarts)
    ok, mindet, ratio = fitter.gate(theta, pl)
    return list(theta), rms, ok, ratio, pl.nlines, pl.n


def measure(cams, clicks, events, names, dists):
    """Rebuild both calibrations under the given distortion parameters and re-measure."""
    built = {clip: dc.build(cams[clip], dists[clip]) for clip in cams}
    rows = []
    for ev, pks in sorted(events.items()):
        if len(pks) != 2:
            continue
        m = re.match(r"([\d.]+)\s*cm", names[ev] or "")
        if not m:
            continue
        true = float(m.group(1)) * 10.0
        pos, ok = [], True
        for pk in pks:
            obs = [(built[c], clicks[pk][c]) for c in built if c in clicks[pk]]
            if len(obs) < 2:
                ok = False
                break
            seed = dc.cpa(dc.sightline(*obs[0][1], obs[0][0]),
                          dc.sightline(*obs[1][1], obs[1][0]))
            if seed is None:
                ok = False
                break
            pos.append(dc.refine(obs, seed))
        if ok:
            rows.append((names[ev], true, math.dist(pos[0], pos[1])))
    pld = {c: built[c]["pld"] for c in built}
    return rows, pld


def summarise(rows):
    e = [r[2] - r[1] for r in rows]
    n = len(e)
    mean = sum(e) / n
    return {"n": n, "mae": sum(abs(v) for v in e) / n,
            "rms": math.sqrt(sum(v * v for v in e) / n), "bias": mean,
            "sd": math.sqrt(sum((v - mean) ** 2 for v in e) / (n - 1)), "err": e}


def main():
    vsd = dc.VSD
    import sqlite3
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
                      "stored": list(dp), "front": [], "back": []}
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

    print("=" * 84)
    print("Do fewer radial terms measure better? 2015-09-04-1 Clearwater, 8 mm fisheye")
    print("=" * 84)

    results = {}
    # reference: the distortion currently in the document, rebuilt the same way
    rows, pld = measure(cams, clicks, events, names,
                        {c: cams[c]["stored"] for c in cams})
    results["document as-is"] = (summarise(rows), None, pld)
    print(f"  reference, document's stored distortion: "
          f"mae {results['document as-is'][0]['mae']:.3f} mm")

    for model in CANDIDATES:
        dists, info = {}, {}
        for clip in cams:
            theta, rms, ok, ratio, nl, npt = fit_camera(vsd, clip, model)
            dists[clip] = theta
            info[clip] = (rms, ok, ratio, nl, npt)
            print(f"  {model:14s} {clip:14s} refit on {nl:3d} lines / {npt:4d} pts -> "
                  f"{rms:.4f} px, gate {'PASS' if ok else 'REJECT'} (ratio {ratio:.2f})")
        rows, pld = measure(cams, clicks, events, names, dists)
        results[model] = (summarise(rows), info, pld)

    print("\n" + "=" * 84)
    print("KNOWN-LENGTH ACCURACY (14 measurements, mm)")
    print("=" * 84)
    print(f"  {'model':>16} {'plumbline px':>13} {'mean abs err':>13} {'rms':>8} "
          f"{'bias':>8} {'sd':>8}")
    for k, (s, info, pld) in results.items():
        px = ("  ".join(f"{info[c][0]:.3f}" for c in sorted(info))) if info else "  (stored)"
        print(f"  {k:>16} {px:>13} {s['mae']:13.3f} {s['rms']:8.3f} {s['bias']:+8.3f} "
              f"{s['sd']:8.3f}")

    base = results["full-13"][0]
    print(f"\n  paired against the full 13-parameter refit, per measurement:")
    for k, (s, info, pld) in results.items():
        if k in ("full-13", "document as-is"):
            continue
        d = [a - b for a, b in zip(s["err"], base["err"])]
        better = sum(1 for a, b in zip(s["err"], base["err"]) if abs(a) < abs(b))
        print(f"    {k:>16}  mean change {sum(d)/len(d):+7.3f} mm, "
              f"closer to truth on {better} of {len(d)}")
    print("\n  A model only earns a change if it is at least as accurate here. The plumbline")
    print("  residual is not evidence: it is the quantity that has misled three times.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
