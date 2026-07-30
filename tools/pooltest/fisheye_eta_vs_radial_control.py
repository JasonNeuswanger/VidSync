#!/usr/bin/env python3
"""Control: is eta doing the work, or would ANY ninth parameter?

M1 beats M0 by adding one parameter (eta) to M0's eight. The obvious confound is parameter count:
restoring a dropped RADIAL term also costs exactly one parameter and stays inside Brown-Conrady.
This fits `M0+k5` (centre, k1..k5, p1,p2 -- nine free) and scores it on the same known lengths and
cloud shapes, through the same production-faithful pipeline.

This is a CONTROL, not a fifth candidate model: it does not introduce a new model family, it asks
whether the ninth degree of freedom has to be eta.

Run with ~/.venvs/vidsync/bin/python, after fisheye_knownlength_analysis.py.
"""

import importlib.util
import math
import os
import sqlite3
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fka",
                                              os.path.join(HERE, "fisheye_knownlength_analysis.py"))
A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)

CONTROLS = [("M0", A.Z.ISO), ("M0+k5", A.Z.ISO[:6] + [6] + A.Z.ISO[6:]), ("M1", A.Z.SCAL)]


def main():
    say = print
    vsd = A.FISHEYE
    say("=" * 100)
    say("CONTROL: eta versus one more radial term, at equal parameter count")
    say("=" * 100)
    cals = A.st.load_cal(vsd)
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    for clip, c in cals.items():
        A.nd.assert_node_orientation(db, c["pk"], c["s2f"], c["s2b"], c["dist"], clip)
    db.close()
    D = A.kl.load(vsd)
    conv, cpairs, clouds = D["conventional"], D["cloud_pairs"], D["clouds"]
    clicks = D["clicks"]
    cnames = sorted(clouds)
    plum = {cl: A.S.Clip(vsd, cl) for cl in sorted(cals)}

    say(f"\n  free parameter sets (index 6 is k5; index 13 is eta)")
    for nm, free in CONTROLS:
        say(f"    {nm:8} {sorted(free)}  -> {len(free)} free")
    assert len(CONTROLS[1][1]) == len(CONTROLS[2][1]), "control must match M1's parameter count"

    cams, prms = {}, {}
    for nm, free in CONTROLS:
        cams[nm] = {}
        for clip in sorted(cals):
            c = cals[clip]
            s0 = np.zeros(15)
            s0[0] = (plum[clip].centre0[0] - A.S.W / 2) / A.S.R
            s0[1] = (plum[clip].centre0[1] - A.S.H / 2) / A.S.R
            v, pr, _, _ = A.fit_model(plum[clip], sorted(free),
                                      [s0, A.stored_to_v(c["dist"])])
            cq, kq, pq, eq, _ = A.Z.nphys(v)
            d14 = [cq[0], cq[1], *kq, *pq, eq]
            gr = A.F.gate_report(np.array(d14[:13]), A.PL(plum[clip].xy), sref=0.0,
                                 frame=(A.FRAME_W, A.FRAME_H))
            cams[nm][clip] = A.build_cam(c, d14)
            prms[(nm, clip)] = (pr, d14[13], gr["ok"], gr["radial_scale_ratio"])

    say(f"\n  PLUMBLINE FIT (px) -- what each ninth parameter buys on the fitting objective")
    say(f"    {'model':8} " + " ".join(f"{cl:>16}" for cl in sorted(cals)) + f"  {'gate':>6}")
    for nm, _ in CONTROLS:
        say(f"    {nm:8} " + " ".join(f"{prms[(nm, cl)][0]:16.4f}" for cl in sorted(cals)) +
            f"  {'ok' if all(prms[(nm, cl)][2] for cl in sorted(cals)) else 'FAIL':>6}")

    # reconstruct and score
    res = {}
    for nm, _ in CONTROLS:
        X = {}
        for r in conv:
            for pk in r["pks"]:
                X[pk] = A.reconstruct(pk, cams[nm], clicks)["X"]
        for cn in cnames:
            for p in clouds[cn]:
                X[p["pk"]] = A.reconstruct(p["pk"], cams[nm], clicks)["X"]
        ce = [float(np.linalg.norm(np.array(X[r["pks"][0]], np.float32) -
                                  np.array(X[r["pks"][1]], np.float32))) - r["true"] for r in conv]
        pe = {cn: [float(np.linalg.norm(np.array(X[q["pks"][0]], np.float32) -
                                        np.array(X[q["pks"][1]], np.float32))) - q["true"]
                   for q in cpairs if q["cloud"] == cn] for cn in cnames}
        sh = {}
        for cn in cnames:
            q2 = np.array([p["mm"] for p in clouds[cn]], float)
            XX = np.array([X[p["pk"]] for p in clouds[cn]], float)
            sh[cn] = A.shape_report(q2, XX)["rms"]
        res[nm] = {"conv": ce, "pair": pe, "shape": sh}

    say(f"\n  KNOWN-LENGTH AND SHAPE ACCURACY (mm)")
    say(f"    {'model':8} {'conv42 MAE':>11} {'cloud-equal pair MAE':>21} "
        f"{'cloud rigid RMS mean':>21}")
    for nm, _ in CONTROLS:
        r = res[nm]
        say(f"    {nm:8} {np.mean(np.abs(r['conv'])):11.4f} "
            f"{np.mean([np.mean(np.abs(r['pair'][cn])) for cn in cnames]):21.4f} "
            f"{np.mean([r['shape'][cn] for cn in cnames]):21.4f}")

    say(f"\n  PER-CLOUD RIGID RMS (mm)")
    say(f"    {'model':8} " + " ".join(f"{cn:>10}" for cn in cnames))
    for nm, _ in CONTROLS:
        say(f"    {nm:8} " + " ".join(f"{res[nm]['shape'][cn]:10.4f}" for cn in cnames))

    say(f"\n  EACH NINTH PARAMETER versus M0 (negative favours the richer model)")
    say(f"    {'contrast':16} {'conv42':>9} {'pair (cloud-equal)':>19} {'rigid RMS':>11} "
        f"{'clouds improved':>16}")
    base = res["M0"]
    for nm in ("M0+k5", "M1"):
        r = res[nm]
        dc = np.mean(np.abs(r["conv"])) - np.mean(np.abs(base["conv"]))
        dp = (np.mean([np.mean(np.abs(r["pair"][cn])) for cn in cnames]) -
              np.mean([np.mean(np.abs(base["pair"][cn])) for cn in cnames]))
        ds = (np.mean([r["shape"][cn] for cn in cnames]) -
              np.mean([base["shape"][cn] for cn in cnames]))
        ni = sum(1 for cn in cnames if r["shape"][cn] < base["shape"][cn])
        say(f"    M0 -> {nm:10} {dc:+9.4f} {dp:+19.4f} {ds:+11.4f} "
            f"{str(ni)+'/'+str(len(cnames)):>16}")

    say(f"\n  CONCLUSION")
    r5, r1 = res["M0+k5"], res["M1"]
    s5 = np.mean([r5["shape"][cn] for cn in cnames])
    s1 = np.mean([r1["shape"][cn] for cn in cnames])
    if s1 < s5:
        say(f"    eta is not interchangeable with a radial term: at IDENTICAL parameter count, eta")
        say(f"    reaches {s1:.4f} mm mean rigid RMS against {s5:.4f} mm for the extra radial term.")
        say(f"    The ninth degree of freedom has to be the anisotropy, not more radial order.")
    else:
        say(f"    the ninth parameter is interchangeable: M0+k5 reaches {s5:.4f} mm against M1's")
        say(f"    {s1:.4f} mm. The eta result would then be a parameter-count effect, NOT evidence")
        say(f"    for anisotropy, and the M1 recommendation must be withdrawn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
