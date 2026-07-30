#!/usr/bin/env python3
"""Model-stability round, part 1: the controlled seed battery for M0, M1, F13eta and full 13.

Every fit uses the objective verified in parity_step2 -- the plain sum of squared
orthogonal-regression residuals over every plumbline of the calibration, unpenalized -- in
production's own scaled parameter units. Two solvers are run from every seed:

  1  the exact production GSL 2.6 Nelder-Mead (plumb_oracle, masked so held parameters stay at
     exactly zero and eta can be freed; the 13-parameter no-eta path is bit-identical to before,
     which the replay regression check in the report confirms)
  2  the verified robust trust-region + Nelder-Mead alternation from parity_step3

Models (free index sets over the 14-vector: 0,1 centre; 2..8 k1..k7; 9..12 p1..p4; 13 eta):

  M0      [0,1,2,3,4,5,9,10]        centre, k1..k4, p1, p2
  M1      M0 + [13]                 plus scalar eta
  FULL13  [0..12]                   all thirteen Brown-Conrady
  F13eta  [0..13]                   all thirteen plus eta

Held parameters are forced to exactly zero in every seed and asserted at every endpoint, so nothing
can leak from a seed into a parameter the model does not have.

Writes analysis-output/stab_fits.json. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sqlite3
import sys
import time

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
P5 = L("parity_step5")
SCALE14 = P5.SCALE14
ETA_SCALE = P5.ETA_SCALE
PNAMES14 = F.NAMES + ["eta"]

MODELS = {
    "M0": [0, 1, 2, 3, 4, 5, 9, 10],
    "M1": [0, 1, 2, 3, 4, 5, 9, 10, 13],
    "FULL13": list(range(13)),
    "F13eta": list(range(14)),
}
# Which parity_step5 row supplies "the existing best endpoint for that model"
PRIOR_ROW = {"M0": "M0", "M1": "M1", "FULL13": "POLISH13", "F13eta": "POLISH13+eta"}


def project(x14, free):
    """Force every parameter outside `free` to exactly zero."""
    y = np.asarray(x14, float).copy()
    held = [j for j in range(14) if j not in set(free)]
    y[held] = 0.0
    return y


def solve_production(lines, x14, free):
    """Production GSL 2.6 Nelder-Mead from a given scaled start, with a free mask."""
    theta = np.asarray(x14, float) * SCALE14
    mask = [1 if j in set(free) else 0 for j in range(14)]
    o = P2.run_oracle("solve", theta[:13], lines, use_prod_start=0,
                      eta=float(theta[13]), freemask=mask)
    x = np.concatenate([o["SOLVED"], [o["SOLVEDETA"]]]) / SCALE14
    return {"x": project(x, free), "sse": o["FINALSSE"], "iters": int(o["ITERS"]),
            "status": int(o["STATUS"]), "size": o["SIMPLEXSIZE"],
            "termination": ("simplex size below 1e-10" if int(o["STATUS"]) == 0
                            else ("iteration cap" if int(o["STATUS"]) == -2
                                  else f"gsl status {int(o['STATUS'])}"))}


def solve_robust(obj, x14, free, label):
    r = P5.fit14(obj, np.asarray(x14, float), free, label)
    return {"x": r["x"], "sse": r["sse"], "iters": r["nfev"], "status": r["ls_status"],
            "size": float("nan"),
            "termination": (f"trf status {r['ls_status']} after {r['rounds']} alternation(s)"
                            + (f", Nelder-Mead gained {r['nm_gain']:.3g}"
                               if r["nm_gain"] > 0 else ""))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "stab_fits.json"))
    args = ap.parse_args()
    say = print
    t0 = time.time()

    say("=" * 104)
    say("MODEL-STABILITY ROUND, PART 1: CONTROLLED SEED BATTERY")
    say("=" * 104)

    app = P2.load_app13(args.vsd)
    prior = {r["model"]: r for r in
             json.load(open(os.path.join(HERE, "analysis-output", "parity_step5.json")))["rows"]}
    step3 = json.load(open(os.path.join(HERE, "analysis-output", "parity_step3.json")))

    out = {"models": {}, "eta_scale": ETA_SCALE, "free_sets": MODELS}
    plum, objs = {}, {}
    for clip in CLIPS:
        lines, tcs, pk = P2.load_lines(args.vsd, clip)
        plum[clip] = (F.Plumblines(lines), lines, pk)
        objs[clip] = P5.Obj14(plum[clip][0])

    # ------------------------------------------------------------------ exact nesting first
    say(f"\n[1] EXACT NESTING, verified numerically before any fitting")
    nest = {}
    for clip in CLIPS:
        pl, lines, pk = plum[clip]
        o14 = objs[clip]
        o13 = P3.Obj(pl)
        key = "theta14_L" if clip == CLIPS[0] else "theta14_R"
        # M1 at eta = 0 against M0's own solution
        m0 = np.array(prior["M0"][key], float)
        assert m0[13] == 0.0
        r_m1_at0 = o14.resid(m0 / SCALE14)
        r_m0 = o14.resid(project(m0 / SCALE14, MODELS["M0"]))
        d1 = float(np.abs(r_m1_at0 - r_m0).max())
        # F13eta at eta = 0 against the 13-parameter objective and map
        a13 = np.array(prior["APP13"][key], float)
        r_f_at0 = o14.resid(a13 / SCALE14)
        r_13 = o13.resid(a13[:13] / F.SCALE)
        d2 = float(np.abs(r_f_at0 - r_13).max())
        u_f = P5.undistort14(pl.xy, a13)
        u_13 = F.undistort(pl.xy, a13[:13], 0.0)
        d3 = float(np.abs(u_f - u_13).max())
        # production-equivalent evaluator, eta path at eta = 0 vs the verbatim path
        oe = P2.run_oracle("eval", a13[:13], lines, eta=0.0, freemask=[1] * 13 + [0])
        d4 = abs(oe["SSE"] - float(r_13 @ r_13))
        nest[clip] = {"m1_at_eta0_vs_m0_resid": d1, "f13eta_at_eta0_vs_full13_resid": d2,
                      "f13eta_at_eta0_vs_full13_map": d3, "oracle_eta_path_vs_verbatim_sse": d4}
        say(f"    {clip:14} M1(eta=0) vs M0 residuals: max |difference| {d1:.1e} px")
        say(f"    {'':14} F13eta(eta=0) vs full-13 residuals: {d2:.1e} px; map: {d3:.1e} px")
        say(f"    {'':14} oracle eta-aware evaluator vs verbatim path at eta=0: SSE difference "
            f"{d4:.1e} px^2")
    out["nesting"] = nest

    # ------------------------------------------------------------------ seed battery
    rng = np.random.default_rng(20260728)
    for mname, free in MODELS.items():
        out["models"][mname] = {}
        for clip in CLIPS:
            pl, lines, pk = plum[clip]
            obj = objs[clip]
            key = "theta14_L" if clip == CLIPS[0] else "theta14_R"
            xprod = np.zeros(14)
            xprod[0] = (FRAME_W / 2.0) / SCALE14[0]
            xprod[1] = (FRAME_H / 2.0) / SCALE14[1]
            x_best = np.array(prior[PRIOR_ROW[mname]][key], float) / SCALE14
            x_app = np.array(prior["APP13"][key], float) / SCALE14
            x_pol = np.array(prior["POLISH13"][key], float) / SCALE14
            eta_prev = float(np.array(prior["M1"][key], float)[13]) / ETA_SCALE

            seeds = [("production cold start", project(xprod, free)),
                     ("existing best endpoint", project(x_best, free)),
                     ("APP13 projected", project(x_app, free)),
                     ("POLISH13 projected", project(x_pol, free))]
            base = project(x_best, free)
            for i, amp in enumerate((0.02, 0.02, 0.20, 0.20)):
                d = rng.normal(0.0, amp, 14) * np.maximum(np.abs(base), 1.0)
                seeds.append((f"perturbation {'small' if amp < 0.1 else 'large'} "
                              f"{1 + (i % 2)} (amp {amp:g})", project(base + d, free)))
            if 13 in free:
                # eta seeded at zero and at the previously fitted value, on three bases
                for lbl, b in (("production cold start", xprod), ("APP13 projected", x_app),
                               ("POLISH13 projected", x_pol)):
                    s = project(b, free).copy(); s[13] = eta_prev
                    seeds.append((f"{lbl}, eta at previous fit", s))
                s = project(x_best, free).copy(); s[13] = 0.0
                seeds.append(("existing best endpoint, eta forced to 0", s))

            say(f"\n[2] {mname} / {clip}   {len(free)} free parameters, {len(seeds)} seeds, "
                f"two solvers each")
            eps = []
            for lbl, s in seeds:
                held = [j for j in range(14) if j not in set(free)]
                assert np.all(s[held] == 0.0), f"seed {lbl} leaks a held parameter"
                sse0 = obj.sse(s)
                for solver, fn in (("production NM", lambda: solve_production(lines, s, free)),
                                   ("robust", lambda: solve_robust(obj, s, free, lbl))):
                    r = fn()
                    heldv = r["x"][held] if held else np.array([])
                    assert np.all(heldv == 0.0), f"{mname}/{clip}/{lbl}/{solver} moved a held param"
                    th = r["x"] * SCALE14
                    gr = F.gate_report(th[:13], pl, 0.0, (FRAME_W, FRAME_H))
                    eps.append({"seed": lbl, "solver": solver, "seed_sse": sse0,
                                "sse": r["sse"], "rms": math.sqrt(r["sse"] / pl.n),
                                "iters": r["iters"], "status": r["status"],
                                "termination": r["termination"], "x": r["x"].tolist(),
                                "theta14": th.tolist(), "eta": float(th[13]),
                                "gate_ok": bool(gr["ok"]),
                                "R_scale": gr["radial_scale_ratio"],
                                "min_det_box": gr["min_det_box"],
                                "min_det_frame": gr["min_det_frame"],
                                "frame_warning": bool(gr["frame_warning"])})
                    say(f"      {lbl:44} {solver:14} SSE {r['sse']:13.6f} "
                        f"RMS {math.sqrt(r['sse'] / pl.n):9.6f} eta {th[13]:+.7f} "
                        f"{'gate ok' if gr['ok'] else 'gate FAIL'}")
            out["models"][mname][clip] = eps

    # ------------------------------------------------------------------ full-13 sensitivity extras
    say(f"\n[3] EXTRA FULL-13 ENDPOINTS for the empirical sensitivity envelope")
    for clip in CLIPS:
        pl, lines, pk = plum[clip]
        obj = objs[clip]
        extra = []
        # production restart at APP13, already computed in step 3
        s3 = step3[clip]
        extra.append({"seed": "production restart at APP13", "solver": "production NM",
                      "theta14": list(np.array(s3["restart_production"]["theta"], float)) + [0.0],
                      "sse": s3["restart_production"]["sse"],
                      "iters": s3["restart_production"]["iters"],
                      "status": s3["restart_production"]["status"],
                      "termination": ("iteration cap" if s3["restart_production"]["status"] == -2
                                      else "simplex size below 1e-10")})
        # the tiny-start-perturbation endpoints, recomputed (their coefficients were not cached)
        for e in (1e-12, 1e-9, 1e-6):
            for sgn in (+1, -1):
                st = np.zeros(13)
                st[0] = (FRAME_W / 2.0) * (1.0 + sgn * e)
                st[1] = (FRAME_H / 2.0) * (1.0 - sgn * e)
                o = P2.run_oracle("solve", st, lines, use_prod_start=0)
                extra.append({"seed": f"start epsilon {sgn * e:+.0e}", "solver": "production NM",
                              "theta14": list(o["SOLVED"]) + [0.0], "sse": o["FINALSSE"],
                              "iters": int(o["ITERS"]), "status": int(o["STATUS"]),
                              "termination": ("simplex size below 1e-10" if int(o["STATUS"]) == 0
                                              else "iteration cap")})
        # controlled-multistart endpoints from step 3
        for e in s3["endpoints"]:
            extra.append({"seed": f"step3 multistart: {e['label']}", "solver": "robust",
                          "theta14": list(np.array(e["theta"], float)) + [0.0], "sse": e["sse"],
                          "iters": -1, "status": e["ls_status"],
                          "termination": f"trf status {e['ls_status']}"})
        for e in extra:
            th = np.array(e["theta14"], float)
            gr = F.gate_report(th[:13], pl, 0.0, (FRAME_W, FRAME_H))
            e.update(x=(th / SCALE14).tolist(), rms=math.sqrt(e["sse"] / pl.n),
                     eta=0.0, gate_ok=bool(gr["ok"]), R_scale=gr["radial_scale_ratio"],
                     min_det_box=gr["min_det_box"], min_det_frame=gr["min_det_frame"],
                     frame_warning=bool(gr["frame_warning"]), seed_sse=float("nan"))
        out["models"]["FULL13"][clip].extend(extra)
        say(f"    {clip:14} added {len(extra)} endpoints; FULL13 pool now "
            f"{len(out['models']['FULL13'][clip])}")

    # historical previous in-app endpoint: metrics survive in the cached summary, coefficients do not
    out["historical_note"] = (
        "The previous in-app 13-parameter endpoint's coefficients were overwritten by the "
        "2026-07-28 recompute and are not recoverable from any artifact in this repository. Its "
        "downstream metrics survive in analysis-output/fisheye_model_summary.csv (row 'stored') and "
        "are carried into the envelope from there, labelled historical. Its gate diagnostics also "
        "survive in fisheye_validation.json: radial scale ratio 1.4424639733464366 / "
        "1.4309822750745114 and minimum determinant 1.0012277598973023 / 1.0000067617602235.")
    say(f"\n    historical previous in-app endpoint: coefficients NOT recoverable; its metrics are "
        f"carried from the cached summary and labelled historical")

    # ------------------------------------------------------------------ clustering
    say(f"\n[4] ENDPOINT CLUSTERS  (same SSE to 1e-6 relative AND map agreement under 0.01 px)")
    gx, gy = np.meshgrid(np.linspace(0.0, FRAME_W, 41), np.linspace(0.0, FRAME_H, 41))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    for mname in MODELS:
        for clip in CLIPS:
            eps = out["models"][mname][clip]
            maps = [P5.undistort14(grid, np.array(e["theta14"], float)) for e in eps]
            order = sorted(range(len(eps)), key=lambda i: eps[i]["sse"])
            clusters = []
            for i in order:
                hit = None
                for c in clusters:
                    j = c["members"][0]
                    if (abs(eps[i]["sse"] - eps[j]["sse"]) <= 1e-6 * max(eps[j]["sse"], 1.0)
                            and float(np.abs(maps[i] - maps[j]).max()) < 0.01):
                        hit = c; break
                if hit is None:
                    clusters.append({"members": [i], "sse": eps[i]["sse"]})
                else:
                    hit["members"].append(i)
            for ci, c in enumerate(clusters):
                for i in c["members"]:
                    eps[i]["cluster"] = ci
            out["models"][mname].setdefault("clusters", {})[clip] = [
                {"index": ci, "sse": c["sse"], "n": len(c["members"]),
                 "rms": math.sqrt(c["sse"] / plum[clip][0].n),
                 "representative": c["members"][0],
                 "eta": eps[c["members"][0]]["eta"],
                 "seeds": sorted({eps[i]["seed"] for i in c["members"]})}
                for ci, c in enumerate(clusters)]
            reps = [c["members"][0] for c in clusters]
            spread = 0.0
            for a in range(len(reps)):
                for b in range(a + 1, len(reps)):
                    spread = max(spread, float(np.abs(maps[reps[a]] - maps[reps[b]]).max()))
            out["models"][mname].setdefault("cluster_map_spread", {})[clip] = spread
            say(f"    {mname:8} {clip:14} {len(eps):3d} endpoints -> {len(clusters):2d} cluster(s); "
                f"SSE " + ", ".join(f"{c['sse']:.4f}(n={len(c['members'])})" for c in clusters[:6])
                + (f" ...; max inter-cluster map spread {spread:.3f} px" if len(clusters) > 1
                   else "; single cluster"))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}   [{time.time() - t0:.0f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
