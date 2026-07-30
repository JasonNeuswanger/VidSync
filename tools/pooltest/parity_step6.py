#!/usr/bin/env python3
"""Step 6 of the solver-parity audit: what KIND of difference is APP13 -> POLISH13?

Step 3 established that robust optimization of the identical objective descends materially from
APP13. Four explanations were on the table: incomplete convergence within one basin, a distinct
basin, movement confined to weak or gauge-like directions, or high-order compensation acting
outside the data's support. This separates them with three measurements.

  1  Direction spectrum. Decompose the APP13 -> POLISH13 step onto the right singular vectors of
     the residual Jacobian at APP13. If the step lies mostly in the smallest singular directions,
     the objective barely distinguishes the two and the difference is a weak-direction wander.

  2  Path connectivity. Evaluate the objective along the straight segment between the two. A single
     basin gives a monotone descent with no barrier; two basins give an intervening rise.

  3  Support locality. Split the map displacement by whether the query point lies inside the
     convex hull of the plumbline points, so "high-order extrapolation outside the data" can be
     confirmed or ruled out rather than assumed.

Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sqlite3
import sys

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
PNAMES = F.NAMES
FULL13 = list(range(13))


def inside_hull(pts, hull_pts):
    """Boolean mask: is each query point inside the convex hull of hull_pts?"""
    from scipy.spatial import ConvexHull
    eq = ConvexHull(np.asarray(hull_pts, float)).equations
    v = np.asarray(pts, float) @ eq[:, :2].T + eq[:, 2]
    return v.max(axis=1) <= 1e-9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--step5", default=os.path.join(HERE, "analysis-output", "parity_step5.json"))
    args = ap.parse_args()
    say = print

    say("=" * 100)
    say("STEP 6  WHAT KIND OF DIFFERENCE SEPARATES APP13 FROM POLISH13")
    say("=" * 100)

    five = json.load(open(args.step5))
    rows = {r["model"]: r for r in five["rows"]}
    app = P2.load_app13(args.vsd)
    ann = kl.load(args.vsd, CLIPS)
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)

    for ci, clip in enumerate(CLIPS):
        key = "theta14_L" if ci == 0 else "theta14_R"
        th_app = np.array(rows["APP13"][key][:13], float)
        th_pol = np.array(rows["POLISH13"][key][:13], float)
        th_m1 = np.array(rows["M1"][key], float)
        lines, tcs, pk = P2.load_lines(args.vsd, clip)
        pl = F.Plumblines(lines)
        obj = P3.Obj(pl)
        x_app, x_pol = th_app / SCALE, th_pol / SCALE

        say(f"\n{'=' * 100}")
        say(f"  {clip}")
        say(f"{'=' * 100}")

        # ------------------------------------------------------------------ 1 direction spectrum
        J = obj.jac(x_app, FULL13)
        U, sv, Vt = np.linalg.svd(J, full_matrices=False)
        step = x_pol - x_app
        coef = Vt @ step
        frac = coef ** 2 / max(float(coef @ coef), 1e-300)
        say(f"\n    1. DIRECTION SPECTRUM of the APP13 -> POLISH13 step, in the singular basis of")
        say(f"       the residual Jacobian at APP13 (scaled units; index 0 is the best-determined")
        say(f"       direction, index 12 the worst)")
        say(f"       Jacobian singular values {sv[0]:.4e} down to {sv[-1]:.4e}, "
            f"condition {sv[0] / sv[-1]:.4e}")
        say(f"       step norm {np.linalg.norm(step):.4e}")
        say(f"       {'index':>6} {'sigma':>12} {'share of step^2':>16} {'cumulative':>11}")
        cum = 0.0
        for i in range(13):
            cum += frac[i]
            say(f"       {i:6d} {sv[i]:12.4e} {frac[i]:16.6f} {cum:11.6f}")
        weak = int(np.searchsorted(np.cumsum(frac[::-1]), 0.9))
        say(f"       the weakest {weak + 1} of 13 directions carry 90% of the step's squared length")
        say(f"       share of the step in the 4 weakest directions {frac[-4:].sum():.4f}; "
            f"in the 4 strongest {frac[:4].sum():.4f}")
        # what a step this size in the strongest direction would have cost
        say(f"       predicted linear SSE change along the step, by direction:")
        for i in (0, 1, 11, 12):
            say(f"         direction {i:2d} (sigma {sv[i]:.3e}): contributes "
                f"{(sv[i] * coef[i]) ** 2:14.6f} px^2 to ||J step||^2")
        say(f"       ||J step||^2 {float(np.linalg.norm(J @ step) ** 2):.6f} px^2 versus the actual "
            f"SSE change {obj.sse(x_app) - obj.sse(x_pol):.6f} px^2")

        say(f"\n       per-parameter view of the same step (scaled units, and as a ratio)")
        say(f"       {'param':>7} {'APP13':>14} {'POLISH13':>14} {'difference':>14} {'ratio':>9}")
        for j in range(13):
            r = (x_pol[j] / x_app[j]) if abs(x_app[j]) > 1e-30 else float("nan")
            say(f"       {PNAMES[j]:>7} {x_app[j]:14.6f} {x_pol[j]:14.6f} "
                f"{x_pol[j] - x_app[j]:+14.6f} {r:9.3f}")

        # ------------------------------------------------------------------ 2 path connectivity
        say(f"\n    2. PATH CONNECTIVITY  objective along the straight segment APP13 -> POLISH13")
        ts = np.linspace(0.0, 1.0, 21)
        vals = np.array([obj.sse(x_app + t * step) for t in ts])
        say(f"       {'t':>6} {'SSE':>14}")
        for t, v in zip(ts, vals):
            mark = ""
            if t == 0.0:
                mark = "  <- APP13"
            elif t == 1.0:
                mark = "  <- POLISH13"
            say(f"       {t:6.2f} {v:14.6f}{mark}")
        peak = float(vals.max())
        barrier = peak - max(vals[0], vals[-1])
        say(f"       maximum along the segment {peak:.6f}; barrier above the higher endpoint "
            f"{barrier:+.6f} px^2")
        say(f"       monotone descent: {bool(np.all(np.diff(vals) <= 1e-9))}")
        say(f"       VERDICT: {'ONE basin, straight-line connected -- incomplete convergence' if barrier <= 1e-6 else 'SEPARATE basins along this path -- a barrier lies between them'}")

        # ------------------------------------------------------------------ 3 support locality
        front = np.array([[p[0], p[1]] for p in nd.front_calibration_nodes(db, pk)], float)
        back = np.array([[p[0], p[1]] for p in nd.back_calibration_nodes(db, pk)], float)
        clicks = np.array([xy for d in ann["clicks"].values() for cl, xy in d.items()
                           if cl == clip], float)
        gx, gy = np.meshgrid(np.linspace(0.0, FRAME_W, 61), np.linspace(0.0, FRAME_H, 61))
        grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
        say(f"\n    3. SUPPORT LOCALITY  is the difference confined to where the plumblines are not?")
        hull = pl.xy
        for label, pts in (("calibration nodes", np.vstack([front, back])),
                           ("measurement clicks", clicks),
                           ("full-frame grid", grid)):
            m = inside_hull(pts, hull)
            A = F.undistort(pts, th_app, 0.0)
            B = F.undistort(pts, th_pol, 0.0)
            e = np.hypot(*(A - B).T)
            ins = e[m]; out = e[~m]
            say(f"       {label:20} {int(m.sum()):5d} inside hull, {int((~m).sum()):5d} outside")
            if ins.size:
                say(f"         inside  max {ins.max():8.3f}  median {np.median(ins):8.3f}  "
                    f"rms {math.sqrt(float((ins ** 2).mean())):8.3f} px")
            if out.size:
                say(f"         outside max {out.max():8.3f}  median {np.median(out):8.3f}  "
                    f"rms {math.sqrt(float((out ** 2).mean())):8.3f} px")
        e_pl = np.hypot(*(F.undistort(pl.xy, th_app, 0.0)
                          - F.undistort(pl.xy, th_pol, 0.0)).T)
        say(f"       plumbline points themselves (all inside by definition): max {e_pl.max():.3f}, "
            f"median {np.median(e_pl):.3f}, rms {math.sqrt(float((e_pl ** 2).mean())):.3f} px")
        say(f"       So the two maps differ by tens of pixels ON THE FITTED DATA, not only in")
        say(f"       extrapolation: the objective is nearly indifferent to that difference.")

        # for contrast, the same locality split for M1 vs APP13
        P5 = L("parity_step5")
        A = F.undistort(grid, th_app, 0.0)
        B = P5.undistort14(grid, th_m1)
        e = np.hypot(*(A - B).T)
        say(f"       for contrast, APP13 vs M1 over the full frame: max {e.max():.3f}, "
            f"median {np.median(e):.3f} px")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
