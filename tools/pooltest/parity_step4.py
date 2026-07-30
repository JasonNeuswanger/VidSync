#!/usr/bin/env python3
"""Step 4 of the solver-parity audit: timecode composition on the Left clip.

The Left calibration carries two plumbline captures four seconds apart, and production fits both
jointly ([self.distortionLines allObjects] has no timecode filter). This fits the verified full-13
objective to each capture alone and to both jointly, then cross-evaluates every solution on every
capture, and reports MAP differences rather than only coefficient differences.

The Right clip has a single capture, so it is reported as the control: the same procedure with one
subset, which must reproduce the joint fit exactly.

Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_W, FRAME_H = 1920.0, 1080.0
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
nd = L("nodes")
kl = L("knownlength")
P2 = L("parity_step2")
P3 = L("parity_step3")
SCALE = F.SCALE
FULL13 = list(range(13))


def load_lines_by_tc(vsd, clip):
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    pk = db.execute("SELECT c.Z_PK FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v "
                    "ON v.Z_PK = c.ZVIDEOCLIP WHERE v.ZCLIPNAME = ?", (clip,)).fetchone()[0]
    byline, tc_of = defaultdict(list), {}
    for tc, ln, x, y in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY FROM ZVSDISTORTIONLINE l "
            "JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
            "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
        if x is not None:
            byline[ln].append((x, y)); tc_of[ln] = tc
    db.close()
    out = defaultdict(list)
    for ln in sorted(byline, key=lambda k: (tc_of[k], k)):
        out[tc_of[ln]].append(byline[ln])
    return dict(out), pk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "parity_step4.json"))
    args = ap.parse_args()
    say = print

    say("=" * 100)
    say("STEP 4  TIMECODE COMPOSITION")
    say("=" * 100)
    say("  same verified objective, same robust solver, only the observation subset changes")

    app = P2.load_app13(args.vsd)
    ann = kl.load(args.vsd, CLIPS)
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)
    results = {}

    for clip in CLIPS:
        bytc, pk = load_lines_by_tc(args.vsd, clip)
        tcs = sorted(bytc)
        theta_app = app[clip]["theta"]
        joint = [Lg for tc in tcs for Lg in bytc[tc]]

        front = np.array([[p[0], p[1]] for p in nd.front_calibration_nodes(db, pk)], float)
        back = np.array([[p[0], p[1]] for p in nd.back_calibration_nodes(db, pk)], float)
        clicks = np.array([xy for d in ann["clicks"].values() for cl, xy in d.items()
                           if cl == clip], float)
        gx, gy = np.meshgrid(np.linspace(0.0, FRAME_W, 61), np.linspace(0.0, FRAME_H, 61))
        supports = {"plumb": F.Plumblines(joint).xy, "nodes": np.vstack([front, back]),
                    "clicks": clicks, "frame": np.stack([gx.ravel(), gy.ravel()], axis=1)}

        say(f"\n{'=' * 100}")
        say(f"  {clip}   {len(tcs)} capture(s)")
        for tc in tcs:
            pls = F.Plumblines(bytc[tc])
            say(f"    {tc!r}: {pls.nlines} lines, {pls.n} points, image extent "
                f"x {pls.xy[:,0].min():.0f}-{pls.xy[:,0].max():.0f} "
                f"y {pls.xy[:,1].min():.0f}-{pls.xy[:,1].max():.0f}")
        say(f"{'=' * 100}")

        subsets = [(f"capture {i + 1}", bytc[tc]) for i, tc in enumerate(tcs)]
        if len(tcs) > 1:
            subsets.append(("both jointly (as the app does)", joint))
        else:
            subsets.append(("single capture = joint (control)", joint))

        # Fit each subset from a common, neutral start plus APP13, so a coefficient difference
        # between subsets cannot be an artefact of different seeds.
        fits = {}
        xprod = np.zeros(13)
        xprod[0] = (FRAME_W / 2.0) / SCALE[0]; xprod[1] = (FRAME_H / 2.0) / SCALE[1]
        for name, lines in subsets:
            pls = F.Plumblines(lines)
            obj = P3.Obj(pls)
            cands = [P3.robust_solve(obj, xprod.copy(), FULL13, f"{name} from production start"),
                     P3.robust_solve(obj, theta_app / SCALE, FULL13, f"{name} from APP13")]
            best = min(cands, key=lambda z: z["sse"])
            th = obj.theta(best["x"])
            gr = F.gate_report(th, pls, 0.0, (FRAME_W, FRAME_H))
            fits[name] = {"theta": th, "pl": pls, "sse": best["sse"],
                          "rms": math.sqrt(best["sse"] / pls.n), "gate": gr,
                          "seeds": {c["label"]: c["sse"] for c in cands}}
            say(f"\n    fit on {name}: {pls.nlines} lines / {pls.n} points")
            for lab, s in fits[name]["seeds"].items():
                say(f"      seed {lab:52} SSE {s:12.6f}")
            say(f"      chosen SSE {best['sse']:.6f}, RMS {fits[name]['rms']:.6f} px; gate ok "
                f"{gr['ok']}, R_scale {gr['radial_scale_ratio']:.6f}, "
                f"minDet box {gr['min_det_box']:+.6f}")

        # cross-evaluation: every solution on every subset, in the same units
        say(f"\n    CROSS-EVALUATION  per-point RMS in px (rows: fitted on; columns: evaluated on)")
        evalsets = [(f"capture {i + 1}", F.Plumblines(bytc[tc])) for i, tc in enumerate(tcs)]
        evalsets.append(("joint", F.Plumblines(joint)))
        hdr = "  ".join(f"{n:>14}" for n, _ in evalsets)
        say(f"      {'fitted on':34} {hdr}")
        for name, _ in subsets:
            th = fits[name]["theta"]
            cells = []
            for _, pls in evalsets:
                r = pls.residuals(th)
                cells.append(math.sqrt(float(r @ r) / pls.n))
            say(f"      {name:34} " + "  ".join(f"{c:14.6f}" for c in cells))
        th_app = theta_app
        cells = []
        for _, pls in evalsets:
            r = pls.residuals(th_app)
            cells.append(math.sqrt(float(r @ r) / pls.n))
        say(f"      {'APP13 (for reference)':34} " + "  ".join(f"{c:14.6f}" for c in cells))

        # map differences, which is what actually matters downstream
        say(f"\n    MAP DIFFERENCES between subset solutions (max/median/rms px)")
        names = [n for n, _ in subsets]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                d = P3.displacements(fits[names[i]]["theta"], fits[names[j]]["theta"], supports)
                say(f"      {names[i]} vs {names[j]}")
                say(f"        " + "  ".join(f"{k} {v[0]:.3f}/{v[1]:.3f}/{v[2]:.3f}"
                                            for k, v in d.items()))
        for n in names:
            d = P3.displacements(theta_app, fits[n]["theta"], supports)
            say(f"      APP13 vs {n}")
            say(f"        " + "  ".join(f"{k} {v[0]:.3f}/{v[1]:.3f}/{v[2]:.3f}"
                                        for k, v in d.items()))

        results[clip] = {n: {"theta": fits[n]["theta"].tolist(), "sse": fits[n]["sse"],
                             "rms": fits[n]["rms"], "n": fits[n]["pl"].n,
                             "nlines": fits[n]["pl"].nlines,
                             "gate_ok": bool(fits[n]["gate"]["ok"]),
                             "R_scale": fits[n]["gate"]["radial_scale_ratio"]}
                         for n in names}

    db.close()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
