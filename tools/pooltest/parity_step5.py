#!/usr/bin/env python3
"""Step 5 of the solver-parity audit: production-faithful downstream comparison.

Every candidate distortion model gets the SAME treatment: the whole refractive calibration is
rebuilt from the raw frame-node clicks through oracle.cpp (production's own call sequence -- front
homography uncorrected, back surface in a four-iteration refractive fixed point, camera position
recomputed every iteration), and every measurement is re-triangulated with parity.triangulate. No
candidate uses the document's stored homographies or camera position, including APP13.

Candidates, all fitted to the objective verified in parity_step2 with the solver of parity_step3:

  APP13         the thirteen parameters now stored in the document, taken as given
  POLISH13      the best gate-passing full-13 solution robust optimization reaches on the same
                objective. Same model, same data, same objective -- only the solver differs
  M0            centre + k1..k4 + p1,p2, everything else exactly zero
  M1            M0 plus scalar eta
  APP13+eta     all thirteen Brown-Conrady terms still free, plus eta, started from APP13
  POLISH13+eta  the same, started from POLISH13

The central comparison is APP13 vs POLISH13: it isolates solver convergence with model, objective
and data held fixed.

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
UNIT = 1.0
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
ORIGINAL_14 = [184, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 201]


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
nd = L("nodes")
kl = L("knownlength")
st = L("stage2")
pa = L("parity")
P2 = L("parity_step2")
P3 = L("parity_step3")


def _FK():
    """fisheye_knownlength_analysis, loaded LAZILY and only for this module's own main().

    It used to be imported at module level for build_cam / reconstruct / shape_report / stats, which
    made an AUTHORITATIVE chain pull a HISTORICAL module in at import time:

        lattice.py  ->  parity_step5.py  ->  fisheye_knownlength_analysis.py

    and importing that last module installs an eta-aware undistortion into a `parity` instance as an
    import side effect. Nothing upstream needs it: `lattice` uses only `SCALE14`, `ETA_SCALE` and
    `undistort14` from this module. So every authoritative run -- xdoc_objectives.py included -- was
    triggering, and being warned about, a historical side effect it never used. Deferring the import
    into `main()` severs that edge and leaves this script's own behaviour identical.
    """
    return L("fisheye_knownlength_analysis")


SCALE = F.SCALE
ETA_SCALE = 1.0e-2                          # eta is O(0.01); this keeps it O(1) like the others
SCALE14 = np.concatenate([SCALE, [ETA_SCALE]])
FULL13 = list(range(13))
M0_FREE = [0, 1, 2, 3, 4, 5, 9, 10]
M1_FREE = M0_FREE + [13]
FULL13_ETA = FULL13 + [13]


# --------------------------------------------------------------------------- eta-aware objective


def undistort14(xy, d):
    """Vectorized nodes.undistort13 with the optional 14th element eta.

    At eta = 0 this DELEGATES to fitter.undistort, the implementation Step 2 verified against
    production's undistortPoint. exp(0) is 1.0 and multiplying by it is the identity, so the
    conjugated form below is mathematically the same map -- but it accumulates the terms in a
    different order (x0 + (xd*R + dx) rather than (x0 + xd*R) + dx), which differs in the last bits.
    Delegating makes the eta = 0 nesting bit-exact by construction instead of merely close, so
    "M1 improves on M0" can never be an artefact of two spellings of the same arithmetic. The two
    forms are compared numerically in step 5's report; they agree to round-off.
    """
    if d[13] == 0.0:
        return F.undistort(np.asarray(xy, float), np.asarray(d, float)[:13], 0.0)
    return undistort_conjugated(xy, d)


def undistort_conjugated(xy, d):
    """The conjugated anisotropic form U(x) = c + A^-1 B(A (x - c)), A = diag(e^eta, e^-eta)."""
    xy = np.asarray(xy, float)
    ax = math.exp(d[13]); ay = 1.0 / ax
    xd = (xy[:, 0] - d[0]) * ax
    yd = (xy[:, 1] - d[1]) * ay
    s = xd * xd + yd * yd
    R = np.ones_like(s)
    sp = np.ones_like(s)
    for k in d[2:9]:
        sp = sp * s
        R = R + k * sp
    T = 1.0 + d[11] * s + d[12] * s * s
    ux = xd * R + (d[9] * (s + 2 * xd * xd) + 2 * d[10] * xd * yd) * T
    uy = yd * R + (2 * d[9] * xd * yd + d[10] * (s + 2 * yd * yd)) * T
    return np.stack([d[0] + ux / ax, d[1] + uy / ay], axis=1)


class Obj14(P3.Obj):
    """The Step-2-verified objective, extended by eta. With eta held at zero this class and
    parity_step3.Obj compute bit-identical residuals, which is asserted below rather than assumed."""

    def theta(self, x):
        return np.asarray(x, float) * SCALE14

    def resid(self, x):
        self.nev += 1
        d = self.theta(x)
        u = undistort14(self.pl.xy, d)
        pl = self.pl
        cx = np.add.reduceat(u[:, 0], pl.starts) / pl.counts
        cy = np.add.reduceat(u[:, 1], pl.starts) / pl.counts
        qx = u[:, 0] - np.repeat(cx, pl.counts)
        qy = u[:, 1] - np.repeat(cy, pl.counts)
        sxy = np.add.reduceat(qx * qy, pl.starts)
        sd = np.add.reduceat(qx * qx - qy * qy, pl.starts)
        th = 0.5 * np.arctan2(2.0 * sxy, sd)
        return -qx * np.repeat(np.sin(th), pl.counts) + qy * np.repeat(np.cos(th), pl.counts)


def fit14(obj, x0, free, label):
    x = np.asarray(x0, float).copy()
    held = [j for j in range(14) if j not in set(free)]
    x[held] = 0.0
    res = P3.robust_solve(obj, x, free, label)
    assert np.all(res["x"][held] == 0.0), f"{label}: a held parameter drifted off zero"
    return res


# --------------------------------------------------------------------------- metrics


def pair_error(X, pk_i, pk_j, true_mm, rec):
    if pk_i not in rec or pk_j not in rec:
        return None
    return float(np.linalg.norm(rec[pk_i]["X"] - rec[pk_j]["X"])) * UNIT - true_mm


def main():
    FK = _FK()        # HISTORICAL module, loaded HERE rather than at import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--step3", default=os.path.join(HERE, "analysis-output", "parity_step3.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "parity_step5.json"))
    args = ap.parse_args()
    say = print

    say("=" * 104)
    say("STEP 5  PRODUCTION-FAITHFUL DOWNSTREAM COMPARISON")
    say("=" * 104)
    say("  every candidate rebuilds front homography, refractive back surface and camera position")
    say("  from raw frame-node clicks via oracle.cpp; nothing reuses the document's stored matrices")

    cals = st.load_cal(args.vsd)
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)
    for clip, c in cals.items():
        nd.assert_node_orientation(db, c["pk"], c["s2f"], c["s2b"], c["dist"], clip)
    say(f"\n  node orientation invariant holds for all {len(cals)} cameras")

    D = kl.load(args.vsd)
    conv, cpts, cpairs, clouds = (D["conventional"], D["cloud_points"], D["cloud_pairs"],
                                  D["clouds"])
    clicks = D["clicks"]
    cnames = sorted(clouds)
    say(f"  annotations: {len(conv)} conventional, {len(clouds)} clouds / {len(cpts)} points / "
        f"{len(cpairs)} pairs, {len(D['exclusions'])} exclusions")

    app = P2.load_app13(args.vsd)
    step3 = json.load(open(args.step3)) if os.path.exists(args.step3) else {}

    # ------------------------------------------------------------------ candidate distortions
    say(f"\n  [A] CANDIDATE DISTORTION FITS, all on the verified objective")
    d14 = {}
    plum = {}
    fitinfo = {}
    for clip in CLIPS:
        lines, tcs, pk = P2.load_lines(args.vsd, clip)
        pl = F.Plumblines(lines)
        plum[clip] = pl
        o13 = P3.Obj(pl)
        o14 = Obj14(pl)
        th_app = app[clip]["theta"]
        x_app14 = np.concatenate([th_app / SCALE, [0.0]])

        # nesting check on the objective implementations themselves
        r13 = o13.resid(th_app / SCALE)
        r14 = o14.resid(x_app14)
        assert np.abs(r13 - r14).max() == 0.0, \
            f"{clip}: eta-extended objective is not bit-identical to the 13-parameter one at eta=0"
        # and how far the conjugated spelling sits from it, reported rather than assumed away
        gap = np.abs(undistort_conjugated(pl.xy, np.concatenate([th_app, [0.0]]))
                     - F.undistort(pl.xy, th_app, 0.0)).max()
        say(f"    {clip:14} eta=0 nesting of the objective implementations: bit-identical "
            f"(max |difference| {np.abs(r13 - r14).max():.1e} px over {pl.n} residuals); the "
            f"conjugated spelling itself differs by {gap:.1e} px")

        # APP13
        d14[("APP13", clip)] = np.concatenate([th_app, [0.0]])

        # POLISH13: best gate-passing full-13 endpoint from step 3, re-polished here
        seeds = [np.concatenate([th_app / SCALE, [0.0]])]
        xprod = np.zeros(14)
        xprod[0] = (FRAME_W / 2.0) / SCALE[0]; xprod[1] = (FRAME_H / 2.0) / SCALE[1]
        seeds.append(xprod)
        if clip in step3:
            for e in step3[clip]["endpoints"]:
                if e["gate_ok"]:
                    seeds.append(np.concatenate([np.array(e["x_scaled"], float), [0.0]]))
        cands = []
        for i, s in enumerate(seeds):
            r = fit14(o14, s, FULL13, f"POLISH13 seed {i}")
            th = o14.theta(r["x"])
            gr = F.gate_report(th[:13], pl, 0.0, (FRAME_W, FRAME_H))
            cands.append((r, th, gr))
        okc = [c for c in cands if c[2]["ok"]]
        pool = okc if okc else cands
        best = min(pool, key=lambda z: z[0]["sse"])
        d14[("POLISH13", clip)] = best[1]
        say(f"    {clip:14} POLISH13 from {len(seeds)} seeds: best gate-passing SSE "
            f"{best[0]['sse']:.6f} (all endpoints "
            f"{', '.join(f'{c[0]['sse']:.4f}{'' if c[2]['ok'] else '(gate FAIL)'}' for c in cands)})")

        # M0, M1
        rm0 = fit14(o14, xprod.copy(), M0_FREE, "M0")
        d14[("M0", clip)] = o14.theta(rm0["x"])
        s1 = rm0["x"].copy()
        m1c = [fit14(o14, s1, M1_FREE, "M1 from M0")]
        for e0 in (-0.02, -0.01, 0.01, 0.02, 0.04):
            s = rm0["x"].copy(); s[13] = e0 / ETA_SCALE
            m1c.append(fit14(o14, s, M1_FREE, f"M1 from eta={e0}"))
        rm1 = min(m1c, key=lambda z: z["sse"])
        d14[("M1", clip)] = o14.theta(rm1["x"])

        # full model plus eta
        sa = np.concatenate([th_app / SCALE, [0.0]])
        ae = [fit14(o14, sa, FULL13_ETA, "APP13+eta from APP13")]
        for e0 in (-0.01, 0.01, 0.02):
            s = sa.copy(); s[13] = e0 / ETA_SCALE
            ae.append(fit14(o14, s, FULL13_ETA, f"APP13+eta from eta={e0}"))
        rae = min(ae, key=lambda z: z["sse"])
        d14[("APP13+eta", clip)] = o14.theta(rae["x"])

        sp = best[0]["x"].copy(); sp[13] = 0.0
        pe = [fit14(o14, sp, FULL13_ETA, "POLISH13+eta from POLISH13")]
        for e0 in (-0.01, 0.01, 0.02):
            s = sp.copy(); s[13] = e0 / ETA_SCALE
            pe.append(fit14(o14, s, FULL13_ETA, f"POLISH13+eta from eta={e0}"))
        rpe = min(pe, key=lambda z: z["sse"])
        d14[("POLISH13+eta", clip)] = o14.theta(rpe["x"])

        # nesting of the eta models against their eta = 0 parents
        def sse_at(d):
            x = np.asarray(d, float) / SCALE14
            return o14.sse(x)
        fitinfo[clip] = {
            "APP13_sse": sse_at(d14[("APP13", clip)]),
            "POLISH13_sse": best[0]["sse"],
            "M0_sse": rm0["sse"], "M1_sse": rm1["sse"],
            "APP13eta_sse": rae["sse"], "POLISH13eta_sse": rpe["sse"],
            "M1_eta": d14[("M1", clip)][13],
            "APP13eta_eta": d14[("APP13+eta", clip)][13],
            "POLISH13eta_eta": d14[("POLISH13+eta", clip)][13],
        }

    MODELS = ["APP13", "POLISH13", "M0", "M1", "APP13+eta", "POLISH13+eta"]
    say(f"\n  [B] PLUMBLINE FIT AND GATE, per candidate")
    say(f"    {'model':14} {'camera':14} {'SSE':>13} {'RMS px':>9} {'eta':>11} {'R_scale':>9} "
        f"{'minDet':>9} {'gate':>6}")
    plumbtab = {}
    for m in MODELS:
        for clip in CLIPS:
            d = d14[(m, clip)]
            pl = plum[clip]
            o14 = Obj14(pl)
            sse = o14.sse(np.asarray(d, float) / SCALE14)
            gr = F.gate_report(np.asarray(d[:13]), pl, 0.0, (FRAME_W, FRAME_H))
            plumbtab[(m, clip)] = {"sse": sse, "rms": math.sqrt(sse / pl.n),
                                   "gate": bool(gr["ok"]),
                                   "R": gr["radial_scale_ratio"],
                                   "minDet": gr["min_det_box"], "eta": d[13]}
            say(f"    {m:14} {clip:14} {sse:13.5f} {math.sqrt(sse / pl.n):9.6f} {d[13]:+11.7f} "
                f"{gr['radial_scale_ratio']:9.6f} {gr['min_det_box']:+9.6f} "
                f"{'ok' if gr['ok'] else 'FAIL':>6}")

    say(f"\n  [C] NESTING against the eta = 0 parents (same data, same objective)")
    for clip in CLIPS:
        fi = fitinfo[clip]
        say(f"    {clip:14} M1 <= M0: {fi['M1_sse'] <= fi['M0_sse'] + 1e-9} "
            f"({fi['M1_sse']:.5f} vs {fi['M0_sse']:.5f}, gain {fi['M0_sse'] - fi['M1_sse']:+.5f}), "
            f"eta {fi['M1_eta']:+.7f}")
        say(f"    {'':14} APP13+eta <= APP13: "
            f"{fi['APP13eta_sse'] <= fi['APP13_sse'] + 1e-9} "
            f"({fi['APP13eta_sse']:.5f} vs {fi['APP13_sse']:.5f}, "
            f"gain {fi['APP13_sse'] - fi['APP13eta_sse']:+.5f}), eta {fi['APP13eta_eta']:+.7f}")
        say(f"    {'':14} POLISH13+eta <= POLISH13: "
            f"{fi['POLISH13eta_sse'] <= fi['POLISH13_sse'] + 1e-9} "
            f"({fi['POLISH13eta_sse']:.5f} vs {fi['POLISH13_sse']:.5f}, "
            f"gain {fi['POLISH13_sse'] - fi['POLISH13eta_sse']:+.5f}), "
            f"eta {fi['POLISH13eta_eta']:+.7f}")

    # ------------------------------------------------------------------ rebuild and measure
    say(f"\n  [D] REBUILD DOWNSTREAM CALIBRATION AND RE-MEASURE")
    cerr, perr, shp, camdiag = {}, {}, {}, {}
    for m in MODELS:
        cams = {}
        for clip in CLIPS:
            cams[clip] = FK.build_cam(cals[clip], list(d14[(m, clip)]))
            fr, _ = nd._rms_max(cals[clip]["front"], cams[clip]["s2f"], list(d14[(m, clip)]))
            br, _ = nd._rms_max(cals[clip]["back"], cams[clip]["s2b"], list(d14[(m, clip)]))
            camdiag[(m, clip)] = {"front_rms": fr * UNIT, "back_rms": br * UNIT,
                                  "camPLD": cams[clip]["camPLD"] * UNIT,
                                  "cam": cams[clip]["cam"]}
        rec = {}
        need = {pk for r in conv for pk in r["pks"]} | {p["pk"] for p in cpts}
        for pk in need:
            r = FK.reconstruct(pk, cams, clicks)
            if r is not None:
                rec[pk] = r
        ce = []
        for r in conv:
            e = pair_error(None, r["pks"][0], r["pks"][1], r["true"], rec)
            ce.append(float("nan") if e is None else e)
        pe = []
        for q in cpairs:
            e = pair_error(None, q["pks"][0], q["pks"][1], q["true"], rec)
            pe.append(float("nan") if e is None else e)
        cerr[m] = np.array(ce, float)
        perr[m] = np.array(pe, float)
        for cn in cnames:
            pts = clouds[cn]
            q2 = np.array([p["mm"] for p in pts], float)
            X = np.array([rec[p["pk"]]["X"] * UNIT for p in pts], float)
            shp[(m, cn)] = FK.shape_report(q2, X)
        say(f"    {m:14} reconstructed {len(rec)} points; "
            f"front/back node rms " +
            "  ".join(f"{clip.split()[0]} {camdiag[(m, clip)]['front_rms']:.3f}/"
                      f"{camdiag[(m, clip)]['back_rms']:.3f} mm" for clip in CLIPS))

    # ------------------------------------------------------------------ summary
    io = np.array([r["event"] in ORIGINAL_14 for r in conv])
    tcset = sorted({r["tc"] for r in conv})
    rows = []
    say(f"\n{'=' * 104}")
    say(f"  [E] HEADLINE COMPARISON (mm).  Central contrast: APP13 vs POLISH13")
    say(f"{'=' * 104}")
    say(f"    {'model':14} {'plumb L/R px':>17} {'conv42 MAE':>11} {'conv42 med':>11} "
        f"{'cloud-equal pair':>17} {'rigid RMS':>10} {'source-bal':>11}")
    for m in MODELS:
        c42 = FK.stats(cerr[m])
        cloud_equal = float(np.mean([np.mean([abs(perr[m][k]) for k, q in enumerate(cpairs)
                                             if q["cloud"] == cn]) for cn in cnames]))
        rigid = float(np.mean([shp[(m, cn)]["rms"] for cn in cnames]))
        pm = [np.mean([abs(cerr[m][k]) for k, r in enumerate(conv) if r["tc"] == tc])
              for tc in tcset]
        cm = [np.mean([abs(perr[m][k]) for k, q in enumerate(cpairs) if q["cloud"] == cn])
              for cn in cnames]
        srcbal = float(np.mean(pm + cm))
        c14 = FK.stats(cerr[m][io])
        prl = f"{plumbtab[(m, CLIPS[0])]['rms']:.4f}/{plumbtab[(m, CLIPS[1])]['rms']:.4f}"
        say(f"    {m:14} {prl:>17} {c42['mae']:11.4f} {c42['med']:11.4f} "
            f"{cloud_equal:17.4f} {rigid:10.4f} {srcbal:11.4f}")
        rows.append({"model": m, "plumb_rms_L": plumbtab[(m, CLIPS[0])]["rms"],
                     "plumb_rms_R": plumbtab[(m, CLIPS[1])]["rms"],
                     "eta_L": plumbtab[(m, CLIPS[0])]["eta"],
                     "eta_R": plumbtab[(m, CLIPS[1])]["eta"],
                     "gate_L": plumbtab[(m, CLIPS[0])]["gate"],
                     "gate_R": plumbtab[(m, CLIPS[1])]["gate"],
                     "conv14_mae": c14["mae"], "conv42_mae": c42["mae"],
                     "conv42_med": c42["med"], "conv42_rmse": c42["rmse"],
                     "cloud_equal_pair_mae": cloud_equal, "rigid_rms_mean": rigid,
                     "source_balanced": srcbal,
                     "rigid_per_cloud": {cn: shp[(m, cn)]["rms"] for cn in cnames},
                     "front_rms_L": camdiag[(m, CLIPS[0])]["front_rms"],
                     "back_rms_L": camdiag[(m, CLIPS[0])]["back_rms"],
                     "front_rms_R": camdiag[(m, CLIPS[1])]["front_rms"],
                     "back_rms_R": camdiag[(m, CLIPS[1])]["back_rms"],
                     "theta14_L": list(d14[(m, CLIPS[0])]),
                     "theta14_R": list(d14[(m, CLIPS[1])])})

    say(f"\n    per-cloud rigid RMS (mm)")
    say(f"    {'model':14} " + " ".join(f"{cn:>10}" for cn in cnames))
    for m in MODELS:
        say(f"    {m:14} " + " ".join(f"{shp[(m, cn)]['rms']:10.4f}" for cn in cnames))

    say(f"\n    conventional MAE by placement (mm)")
    say(f"    {'model':14} " + " ".join(f"{str(tc)[:12]:>13}" for tc in tcset))
    for m in MODELS:
        pm = [np.mean([abs(cerr[m][k]) for k, r in enumerate(conv) if r["tc"] == tc])
              for tc in tcset]
        say(f"    {m:14} " + " ".join(f"{v:13.4f}" for v in pm))

    a, b = "APP13", "POLISH13"
    say(f"\n    SOLVER-ONLY CONTRAST {b} minus {a}, model and objective held fixed:")
    for key, lbl in (("conv42_mae", "conventional MAE over 42"),
                     ("conv42_med", "conventional median"),
                     ("conv14_mae", "original-14 MAE"),
                     ("cloud_equal_pair_mae", "cloud-equal pair MAE"),
                     ("rigid_rms_mean", "cloud rigid RMS"),
                     ("source_balanced", "source-balanced")):
        ra = next(r for r in rows if r["model"] == a)
        rb = next(r for r in rows if r["model"] == b)
        say(f"      {lbl:28} {ra[key]:9.4f} -> {rb[key]:9.4f}   "
            f"{rb[key] - ra[key]:+8.4f} mm  ({'POLISH13 better' if rb[key] < ra[key] else 'APP13 better'})")

    db.close()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"rows": rows, "fitinfo": fitinfo}, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
