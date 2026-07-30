#!/usr/bin/env python3
"""Model-stability round, part 5: the eta identifiability profile for M1 and F13eta.

At each fixed eta on a dense grid, EVERY other free parameter is reoptimized, so the curve is a
profile of the objective over eta rather than a slice through it.

This is an identifiability profile, not a confidence interval. The objective is a sum of squared
orthogonal-regression residuals whose within-line errors are correlated by construction -- each
residual is measured against a line fitted to its own neighbours -- so the usual chi-square
calibration of a dSSE width does not apply. Widths are reported descriptively.

Separated from stab_gauge.py because the first attempt at this was wrong: holding eta by leaving it
out of the free set ran through a helper that FORCES held parameters to zero, so every grid point
silently refitted the eta = 0 model and the profile came out perfectly flat at M0's own SSE. The fix
is a solver that holds a parameter at a fixed nonzero value; the flatness was an artifact.

Writes analysis-output/stab_etaprofile.json. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
P2 = L("parity_step2")
P3 = L("parity_step3")
P5 = L("parity_step5")
DG = L("stab_degeneracy")
SCALE14 = P5.SCALE14
ETA_SCALE = P5.ETA_SCALE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--fits", default=os.path.join(HERE, "analysis-output", "stab_fits.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "stab_etaprofile.json"))
    args = ap.parse_args()
    say = print

    say("=" * 104)
    say("MODEL-STABILITY ROUND, PART 5: ETA IDENTIFIABILITY PROFILE")
    say("=" * 104)
    say("  all other free parameters reoptimized at each fixed eta; descriptive widths only")

    fits = json.load(open(args.fits))
    out = {}
    for clip in CLIPS:
        lines, tcs, pk = P2.load_lines(args.vsd, clip)
        pl = F.Plumblines(lines)
        obj = P5.Obj14(pl)
        out[clip] = {}
        for model in ("M1", "F13eta"):
            free = fits["free_sets"][model]
            nuis = [j for j in free if j != 13]
            cl = [c for c in fits["models"][model]["clusters"][clip]
                  if DG.on_physical_branch(c["rms"], c["eta"])
                  and fits["models"][model][clip][c["representative"]]["gate_ok"]]
            best = min(cl, key=lambda c: c["sse"])
            xb = np.array(fits["models"][model][clip][best["representative"]]["theta14"],
                          float) / SCALE14
            e0 = float(xb[13] * ETA_SCALE)
            # dense grid around the optimum, plus zero and both signs, to reveal asymmetry
            offs = [-0.020, -0.014, -0.010, -0.007, -0.005, -0.003, -0.002, -0.001, -0.0005,
                    0.0, 0.0005, 0.001, 0.002, 0.003, 0.005, 0.007, 0.010, 0.014, 0.020]
            grid = sorted(set([0.0] + [round(e0 + d, 8) for d in offs]))
            prof = []
            for e in grid:
                s = xb.copy(); s[13] = e / ETA_SCALE
                r = P3.robust_solve(obj, s, nuis, f"{model} eta={e}", require_held_zero=False)
                assert abs(r["x"][13] * ETA_SCALE - e) < 1e-12, "eta moved during the profile"
                prof.append({"eta": e, "sse": r["sse"]})
            lo = min(p["sse"] for p in prof)
            emin = [p["eta"] for p in prof if p["sse"] == lo][0]
            zero = [p for p in prof if p["eta"] == 0.0][0]
            # descriptive widths: how far eta must move for the profile to rise by 1% and 10%
            def halfwidth(frac):
                tgt = lo * (1.0 + frac)
                left = [p for p in prof if p["eta"] < emin and p["sse"] >= tgt]
                right = [p for p in prof if p["eta"] > emin and p["sse"] >= tgt]
                return (emin - max(p["eta"] for p in left) if left else float("nan"),
                        min(p["eta"] for p in right) - emin if right else float("nan"))
            w1, w10 = halfwidth(0.01), halfwidth(0.10)
            near = [p for p in prof if abs(p["eta"] - emin) <= 0.00301]
            curv = float("nan")
            if len(near) >= 3:
                gg = np.array([p["eta"] for p in near]); cc = np.array([p["sse"] for p in near])
                curv = float(np.polyfit(gg, cc, 2)[0] * 2)
            nmin = sum(1 for i in range(1, len(prof) - 1)
                       if prof[i]["sse"] < prof[i - 1]["sse"] and prof[i]["sse"] < prof[i + 1]["sse"])
            out[clip][model] = {"eta_hat": e0, "eta_at_profile_min": emin, "min_sse": lo,
                                "sse_at_zero": zero["sse"], "profile": prof,
                                "curvature": curv, "one_percent_halfwidth": w1,
                                "ten_percent_halfwidth": w10, "interior_minima": nmin}
            say(f"\n  {clip} / {model}: eta_hat {e0:+.7f}, profile minimum at eta {emin:+.7f}, "
                f"SSE {lo:.5f}")
            say(f"    {'eta':>10} {'SSE':>14} {'dSSE':>12} {'dSSE as % of min':>18}")
            for p in prof:
                mark = ""
                if p["eta"] == emin:
                    mark = "  <- minimum"
                elif p["eta"] == 0.0:
                    mark = "  <- eta = 0"
                say(f"    {p['eta']:+10.5f} {p['sse']:14.5f} {p['sse'] - lo:12.5f} "
                    f"{100 * (p['sse'] - lo) / lo:18.3f}{mark}")
            say(f"    dSSE at eta = 0: {zero['sse'] - lo:.5f} px^2, "
                f"{100 * (zero['sse'] - lo) / lo:.2f}% of the minimum")
            say(f"    local curvature d2SSE/deta2 {curv:.4e}")
            say(f"    eta offset for a 1% rise: {w1[0]:.5f} below, {w1[1]:.5f} above; "
                f"for a 10% rise: {w10[0]:.5f} below, {w10[1]:.5f} above")
            say(f"    interior local minima on this grid: {nmin} "
                f"({'single well' if nmin <= 1 else 'MULTIPLE minima'})")

    say(f"\n  COMPARISON")
    say(f"    {'camera':14} {'M1 eta':>11} {'F13eta eta':>11} {'M1 1% width':>22} "
        f"{'F13eta 1% width':>22}")
    for clip in CLIPS:
        a, b = out[clip]["M1"], out[clip]["F13eta"]
        say(f"    {clip:14} {a['eta_hat']:+11.7f} {b['eta_hat']:+11.7f} "
            f"{f'-{a['one_percent_halfwidth'][0]:.5f}/+{a['one_percent_halfwidth'][1]:.5f}':>22} "
            f"{f'-{b['one_percent_halfwidth'][0]:.5f}/+{b['one_percent_halfwidth'][1]:.5f}':>22}")
    say(f"    dSSE at eta = 0, as a percentage of each profile's own minimum:")
    for clip in CLIPS:
        a, b = out[clip]["M1"], out[clip]["F13eta"]
        say(f"      {clip:14} M1 {100 * (a['sse_at_zero'] - a['min_sse']) / a['min_sse']:8.2f}%   "
            f"F13eta {100 * (b['sse_at_zero'] - b['min_sse']) / b['min_sse']:8.2f}%")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
