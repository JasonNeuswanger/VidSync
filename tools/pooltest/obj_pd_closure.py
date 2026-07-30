#!/usr/bin/env python3
"""Closure round for the exact projective-lattice objective, using the fast PDExact evaluator.

Resolves the four things left open after Round 1 and the speed round:

  1  which observation set each Round-1 Delaunay triangle count described;
  2  strict M0 -> M1 nesting under exact PD;
  3  what spatial quadrature (Delaunay area weights) actually changes versus uniform point weights;
  4  whether the two Left captures want the same distortion map;
  5  whether the remaining projective residual is isotropic and harmonic-free.

Every fit uses objectives.PDExact with its analytic Jacobian. The old finite-difference PD optimizer
is not invoked. Nothing here touches the document, production code, or production defaults. No SD/ED,
no canonical lines, no known lengths, no point clouds, no refraction, no profile grids, no multistart.

Writes analysis-output/obj_pd_closure.{log,json} and three plots.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sys
import time

import numpy as np

import artifacts

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
FIT_LIMIT_S = 2.0


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LT = L("lattice")
OB = L("objectives")
GA = L("stab_gauge")
SCALE14 = LT.SCALE14
SLOW = []


def base_for(model):
    b = OB.default_base()
    for j in range(14):
        if j not in set(OB.MODELS[model]):
            b[j] = 0.0
    return b


# =============================================================== 1. weight audit


def weight_row(label, caps, kappa, mask, note):
    """One fully described quadrature computation."""
    w, info = LT.delaunay_weights(caps, kappa=kappa, mask=mask)
    return {"label": label, "kappa": kappa, "note": note,
            "n_observations_triangulated": int(info["n"]),
            "n_coincident_clusters": int(info["n_clusters"]),
            "n_clusters_with_coincidence": int(info["n_coincident_clusters"]),
            "raw_delaunay_triangles": int(info["triangles_kept"] + info["triangles_dropped"]),
            "triangles_retained": int(info["triangles_kept"]),
            "triangles_rejected": int(info["triangles_dropped"]),
            "unnormalized_mass_px2": float(info["unnormalized_mass_px2"]),
            "weight_min": float(w.min()), "weight_median": float(np.median(w)),
            "weight_max": float(w.max()), "weight_sum": float(w.sum()),
            "zero_weight_observations": int(info["zero_weight_observations"]),
            "w": w}


def section_weights(say, clip, caps, D, results):
    say(f"\n    WEIGHT AUDIT -- every quadrature calculation, fully described")
    caplist = ", ".join(repr(C.timecode) for C in caps)
    say(f"      camera {clip}; captures included: {caplist}")
    rows = []
    for kappa in (2.0, 3.0, 4.0):
        rows.append(weight_row(
            f"PRIMARY fitted subset (kappa={kappa})", caps, kappa, D.sel,
            "reliably indexed, largest connected component per capture, min 2 incidences -- "
            "EXACTLY the observations entering the PD fit"))
    for kappa in (2.0, 3.0, 4.0):
        rows.append(weight_row(
            f"all observations, unmasked (kappa={kappa})", caps, kappa, None,
            "every stored observation including unindexed, small-component and singly "
            "constrained ones -- this is what lattice.py's standalone audit reports"))
    say(f"      {'set':44} {'nObs':>5} {'clus':>5} {'coinc':>6} {'rawTri':>7} {'keep':>6} "
        f"{'rej':>5} {'mass Mpx2':>10} {'wmin':>7} {'wmed':>7} {'wmax':>7} {'wsum':>8}")
    for r in rows:
        say(f"      {r['label']:44} {r['n_observations_triangulated']:5d} "
            f"{r['n_coincident_clusters']:5d} {r['n_clusters_with_coincidence']:6d} "
            f"{r['raw_delaunay_triangles']:7d} {r['triangles_retained']:6d} "
            f"{r['triangles_rejected']:5d} {r['unnormalized_mass_px2'] / 1e6:10.4f} "
            f"{r['weight_min']:7.4f} {r['weight_median']:7.4f} "
            f"{r['weight_max']:7.4f} {r['weight_sum']:8.1f}")
    say(f"      restricted to largest connected indexed component: PRIMARY yes, unmasked no")
    say(f"      singly constrained / excluded observations present: PRIMARY no, unmasked yes")
    say(f"      zero-weight observations in the primary set: "
        f"{rows[1]['zero_weight_observations']}  (no excluded observation carries mass, because "
        f"only selected observations are supplied to the triangulation at all)")
    results["weights"] = [{k: v for k, v in r.items() if k != "w"} for r in rows]
    return rows


# =============================================================== shared evaluation


def gauge_mapdiff(P, th1, th2):
    """Raw and best-common-projective-gauge-removed map difference over the point set P."""
    U1 = LT.U(P, th1); U2 = LT.U(P, th2)
    e = np.linalg.norm(U1 - U2, axis=1)
    g = GA.fit_homography(U1, U2)
    eg = np.linalg.norm(GA.apply_H(g, U1) - U2, axis=1)
    return {"median": float(np.median(e)), "p95": float(np.percentile(e, 95)),
            "max": float(e.max()),
            "gauge_removed_median": float(np.median(eg)),
            "gauge_removed_p95": float(np.percentile(eg, 95)),
            "gauge_removed_max": float(eg.max())}


def resid_vectors(D, th, w):
    """Unweighted raw projective residual x - U^-1(pi(H s)), H profiled under weights w."""
    loss, ev, p = OB.profile_H(D, th, w=w)
    st = ev._state(p)
    v = D.xy - st["q"]
    return loss, v, ev, p


def radial_tangential(D, th, v, w):
    c = np.asarray(th)[:2]
    d = D.xy - c
    r = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
    rad = (v[:, 0] * d[:, 0] + v[:, 1] * d[:, 1]) / r
    tan = (-v[:, 0] * d[:, 1] + v[:, 1] * d[:, 0]) / r
    ws = w / w.sum()
    return {"radial_rms": float(math.sqrt(float(ws @ (rad ** 2)))),
            "tangential_rms": float(math.sqrt(float(ws @ (tan ** 2)))),
            "ratio_radial_over_tangential": float(math.sqrt(float(ws @ (rad ** 2))
                                                            / max(float(ws @ (tan ** 2)), 1e-30))),
            "rad": rad, "tan": tan, "phi": np.arctan2(d[:, 1], d[:, 0]), "r": r}


def diagonal_structural(caps, th, sel):
    """Corrected-space straightness of the r+-c diagonal families.

    These families are never used as explicit constraints by ANY objective here. For B they are a
    genuine zero-weight holdout. For PD the caveat is real and stated: the homography predicts every
    indexed corner, so the diagonals are implied by the fit rather than held out, and this column is a
    structural consistency check rather than an independent test.
    """
    allr = []
    per = []
    for ci, C in enumerate(caps):
        fams = [f for f in LT.diagonal_families(C, restrict=sel[ci]) if f["adequate"]]
        u = LT.U(C.xy, th)
        rr = []
        for f in fams:
            Pm = u[f["members"]]
            q = Pm - Pm.mean(axis=0)
            t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                                 float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            rr.append(-q[:, 0] * math.sin(t) + q[:, 1] * math.cos(t))
        if rr:
            v = np.concatenate(rr); allr.append(v)
            per.append({"timecode": C.timecode, "families": len(fams), "points": int(len(v)),
                        "rms": float(np.sqrt((v ** 2).mean()))})
    if not allr:
        return {"rms": float("nan"), "points": 0, "per_capture": per}
    v = np.concatenate(allr)
    return {"rms": float(np.sqrt((v ** 2).mean())), "points": int(len(v)), "per_capture": per}


def per_capture_rms(D, v, w):
    out = []
    for c in range(D.ncap):
        m = D.cap_of == c
        if not m.any():
            continue
        d = np.linalg.norm(v[m], axis=1)
        ws = w[m] / w[m].sum()
        out.append({"capture": int(c), "n": int(m.sum()),
                    "unweighted_rms": float(np.sqrt((d ** 2).mean())),
                    "weighted_rms": float(math.sqrt(float(ws @ (d ** 2))))})
    return out


def fit_pd(say, D, model, w, th_init, label, max_nfev=200):
    ev = OB.PDExact(D, model, base=base_for(model), w=w)
    p0 = ev.init_dlt(th_init)
    l0 = ev.loss(p0)
    ev.reset_counters()
    res, wall = ev.fit(p0, max_nfev=max_nfev)
    if wall > FIT_LIMIT_S:
        SLOW.append((label, wall, dict(ev.C)))
    return {"label": label, "model": model, "loss0": l0, "loss": float(2 * res.cost),
            "p": res.x.copy(), "theta14": ev.theta(res.x), "eta": float(ev.theta(res.x)[13]),
            "status": int(res.status), "optimality": float(res.optimality),
            "nfev": int(res.nfev), "njev": int(res.njev), "wall_s": wall,
            "counted_fun": ev.C["fun"], "counted_jac": ev.C["jac"],
            "newton_fallbacks": ev.C["newton_fallbacks"],
            "inverse_failures": ev.C["inverse_failures"], "ev": ev}


# =============================================================== 2. nesting


def section_nesting(say, clip, D, thB0, thB1, results):
    say(f"\n    STRICT M0 -> M1 NESTING under Delaunay-weighted exact PD")
    m0 = fit_pd(say, D, "M0", None, thB0, f"{clip} PD-D/M0")
    ev1 = OB.PDExact(D, "M1", base=base_for("M1"))
    # embed: same 8 model parameters, eta = 0, SAME homographies. MODELS['M1'] is MODELS['M0'] + [13],
    # so the model block keeps its order and eta is appended.
    p_emb = np.concatenate([m0["p"][:m0["ev"].nm], [0.0], m0["p"][m0["ev"].nm:]])
    l_emb = ev1.loss(p_emb)
    res1, wall1 = ev1.fit(p_emb)
    l1 = float(2 * res1.cost)
    th1 = ev1.theta(res1.x)
    # the same M1 basin reached from the independent B/M1 + DLT start
    alt = fit_pd(say, D, "M1", None, thB1, f"{clip} PD-D/M1 from B+DLT")
    dpar = float(np.abs(th1[OB.MODELS["M1"]] - alt["theta14"][OB.MODELS["M1"]]).max())
    md = gauge_mapdiff(D.xy, th1, alt["theta14"])
    unc = ev1.param_uncertainty(res1.x, ev1.free.index(13))
    say(f"      M0 optimized loss                  {m0['loss']:14.9f}   "
        f"({m0['wall_s'] * 1e3:.1f} ms, status {m0['status']}, optimality {m0['optimality']:.2e})")
    say(f"      embedded M0 as M1 at eta = 0       {l_emb:14.9f}   |difference| "
        f"{abs(l_emb - m0['loss']):.3e}  {'EXACT' if abs(l_emb - m0['loss']) <= 1e-9 else 'MISMATCH'}")
    say(f"      M1 optimized from the embedding    {l1:14.9f}   "
        f"({wall1 * 1e3:.1f} ms, status {res1.status}, optimality {res1.optimality:.2e})")
    say(f"      reduction attributable to eta      {m0['loss'] - l1:+14.9f}   "
        f"({100 * (m0['loss'] - l1) / max(m0['loss'], 1e-30):.2f}% of the M0 loss)")
    say(f"      eta {th1[13]:+.9f} +/- {unc['sd_raw_units']:.9f} (linearized, all other directions "
        f"including homographies projected out) = {abs(th1[13]) / max(unc['sd_raw_units'], 1e-30):.1f} sd")
    say(f"      M1 not worse than M0: {l1 <= m0['loss'] + 1e-9 * max(m0['loss'], 1.0)}")
    say(f"      same basin as the B/M1 + DLT start: loss {alt['loss']:.9f} (difference "
        f"{abs(l1 - alt['loss']):.3e}), max |dtheta_free| {dpar:.3e}")
    say(f"      map difference between the two M1 starts: median {md['median']:.2e} px, "
        f"gauge-removed median {md['gauge_removed_median']:.2e} px")
    results["nesting"] = {
        "M0_loss": m0["loss"], "embedded_M0_as_M1_loss": l_emb,
        "embedding_exact_to": abs(l_emb - m0["loss"]),
        "M1_loss_from_embedding": l1, "eta_reduction": m0["loss"] - l1,
        "eta": float(th1[13]), "eta_sd_linearized": unc["sd_raw_units"],
        "eta_curvature": unc["curvature"],
        "M1_not_worse": bool(l1 <= m0["loss"] + 1e-9 * max(m0["loss"], 1.0)),
        "M1_loss_from_B_DLT": alt["loss"], "basin_loss_difference": abs(l1 - alt["loss"]),
        "max_dtheta_between_starts": dpar, "map_difference_between_starts": md,
        "M0_status": m0["status"], "M0_optimality": m0["optimality"], "M0_wall_s": m0["wall_s"],
        "M1_status": int(res1.status), "M1_optimality": float(res1.optimality),
        "M1_wall_s": wall1, "theta14_M0": m0["theta14"].tolist(), "theta14_M1": th1.tolist()}
    return m0, {"theta14": th1, "p": res1.x, "loss": l1, "ev": ev1}


# =============================================================== 3. weighting


def evaluate_map(D, caps, th, wD, label):
    """One fitted map, scored under both weightings with the homographies reprofiled each time."""
    lu, vu, evu, pu = resid_vectors(D, th, 1.0)
    ld, vd, evd, pd = resid_vectors(D, th, wD)
    rtu = radial_tangential(D, th, vu, np.ones(D.n))
    rtd = radial_tangential(D, th, vd, wD)
    return {"label": label, "theta14": np.asarray(th).tolist(), "eta": float(th[13]),
            "centre": [float(th[0]), float(th[1])],
            "loss_uniform": lu, "loss_delaunay": ld,
            "per_capture_uniform": per_capture_rms(D, vu, np.ones(D.n)),
            "per_capture_delaunay": per_capture_rms(D, vd, wD),
            "radial_tangential_uniform": {k: v for k, v in rtu.items()
                                          if k not in ("rad", "tan", "phi", "r")},
            "radial_tangential_delaunay": {k: v for k, v in rtd.items()
                                           if k not in ("rad", "tan", "phi", "r")},
            "diagonal_structural": diagonal_structural(caps, th, D.sel),
            "_vu": vu, "_vd": vd, "_rtu": rtu, "_rtd": rtd}


def section_weighting(say, clip, caps, D, wD, thB0, thB1, results):
    say(f"\n    SPATIAL QUADRATURE: PD-U (uniform a_i = 1) vs PD-D (Delaunay area, mean 1)")
    say(f"      identical observations, identical nuisance-homography structure; only a_i differs")
    fits = {}
    for model, thi in (("M0", thB0), ("M1", thB1)):
        for scheme, w in (("U", 1.0), ("D", None)):
            f = fit_pd(say, D, model, w, thi, f"{clip} PD-{scheme}/{model}")
            f["cond"] = f["ev"].projected_conditioning(f["p"])["condition"]
            fits[(scheme, model)] = f
    say(f"      {'fit':12} {'ownLoss':>13} {'nfev':>5} {'ms':>6} {'eta':>11} {'centre x':>10} "
        f"{'centre y':>10} {'projCond':>10}")
    for k, f in fits.items():
        say(f"      PD-{k[0]}/{k[1]:8} {f['loss']:13.6f} {f['nfev']:5d} {f['wall_s'] * 1e3:6.1f} "
            f"{f['eta']:+11.7f} {f['theta14'][0]:10.4f} {f['theta14'][1]:10.4f} {f['cond']:10.3e}")

    say(f"\n      CROSS-EVALUATION: every map scored under both weightings, homographies reprofiled")
    ev = {}
    R1 = results["_r1"]
    for model in ("M0", "M1"):
        for scheme in ("U", "D"):
            ev[(scheme, model)] = evaluate_map(D, caps, fits[(scheme, model)]["theta14"], wD,
                                               f"PD-{scheme}/{model}")
        ev[("B", model)] = evaluate_map(D, caps, np.array(R1["fits"]["B/" + model]["theta14"], float),
                                        wD, f"B/{model} (historical, not refitted)")
    say(f"      {'map':34} {'uniformLoss':>13} {'delaunayLoss':>13} {'radRMS_u':>9} "
        f"{'tanRMS_u':>9} {'r/t':>6} {'diagRMS':>8}")
    for key in [("U", "M0"), ("D", "M0"), ("B", "M0"), ("U", "M1"), ("D", "M1"), ("B", "M1")]:
        e = ev[key]
        say(f"      {e['label']:34} {e['loss_uniform']:13.6f} {e['loss_delaunay']:13.6f} "
            f"{e['radial_tangential_uniform']['radial_rms']:9.4f} "
            f"{e['radial_tangential_uniform']['tangential_rms']:9.4f} "
            f"{e['radial_tangential_uniform']['ratio_radial_over_tangential']:6.3f} "
            f"{e['diagonal_structural']['rms']:8.4f}")
    say(f"      note: each scheme necessarily wins its own score. The comparison of interest is the "
        f"OTHER column and the map difference below.")

    say(f"\n      PER-CAPTURE exact projective residual RMS (unweighted px, under uniform scoring)")
    for key in [("U", "M1"), ("D", "M1"), ("B", "M1")]:
        s = "  ".join(f"cap{p['capture']} {p['unweighted_rms']:.4f} (n={p['n']})"
                      for p in ev[key]["per_capture_uniform"])
        say(f"        {ev[key]['label']:34} {s}")

    say(f"\n      MAP DIFFERENCE between the two weighting schemes over the informed region")
    mds = {}
    for model in ("M0", "M1"):
        md = gauge_mapdiff(D.xy, fits[("U", model)]["theta14"], fits[("D", model)]["theta14"])
        mds[model] = md
        say(f"        {model}: raw median {md['median']:8.4f} p95 {md['p95']:8.4f} max "
            f"{md['max']:8.4f} px")
        say(f"        {model}: gauge-removed median {md['gauge_removed_median']:8.4f} p95 "
            f"{md['gauge_removed_p95']:8.4f} max {md['gauge_removed_max']:8.4f} px  <-- the "
            f"nonprojective part")
        frac = md["gauge_removed_median"] / max(md["median"], 1e-30)
        say(f"        {model}: gauge-removed / raw median = {frac:.3f}, so "
            f"{100 * (1 - frac):.1f}% of the difference is pure projective gauge")
    results["weighting"] = {
        "fits": {f"PD-{k[0]}/{k[1]}": {kk: (vv.tolist() if isinstance(vv, np.ndarray) else vv)
                                       for kk, vv in f.items() if kk not in ("ev", "p")}
                 for k, f in fits.items()},
        "cross_evaluation": {f"{k[0]}/{k[1]}": {kk: vv for kk, vv in e.items()
                                               if not kk.startswith("_")}
                             for k, e in ev.items()},
        "scheme_map_difference": mds}
    return fits, ev


# =============================================================== 4. Left captures


def hull_mask(P, Q, grid):
    """Grid points inside the convex hulls of BOTH point sets."""
    from scipy.spatial import Delaunay as DT
    return (DT(P).find_simplex(grid) >= 0) & (DT(Q).find_simplex(grid) >= 0)


def section_captures(say, clip, caps, D, thB1, results):
    say(f"\n    LEFT-CAPTURE CONSISTENCY (diagnostic only; no capture-specific deployed correction)")
    subs, sfits = [], []
    for ci, C in enumerate(caps):
        Dc = OB.Dataset([C], require_indexed=True, min_inc=2, kappa=3.0)
        f = fit_pd(say, D if False else Dc, "M1", None, thB1, f"{clip} cap{ci} PD-D/M1")
        f["D"] = Dc
        unc = f["ev"].param_uncertainty(f["p"], f["ev"].free.index(13))
        f["eta_sd"] = unc["sd_raw_units"]
        f["cond"] = f["ev"].projected_conditioning(f["p"])["condition"]
        subs.append(Dc); sfits.append(f)
        say(f"      capture {ci} ({C.timecode!r}) alone: {Dc.n} observations, "
            f"{Dc.info['weights']['triangles_kept']} triangles, loss {f['loss']:.6f}, eta "
            f"{f['eta']:+.7f} +/- {f['eta_sd']:.7f}, projCond {f['cond']:.3e}, "
            f"{f['wall_s'] * 1e3:.1f} ms")
    shared = fit_pd(say, D, "M1", None, thB1, f"{clip} shared PD-D/M1")
    unc = shared["ev"].param_uncertainty(shared["p"], shared["ev"].free.index(13))
    shared["eta_sd"] = unc["sd_raw_units"]
    say(f"      shared two-capture fit: {D.n} observations, loss {shared['loss']:.6f}, eta "
        f"{shared['eta']:+.7f} +/- {shared['eta_sd']:.7f}, {shared['wall_s'] * 1e3:.1f} ms")

    # common informed support
    P0, P1 = subs[0].xy, subs[1].xy
    gx, gy = np.meshgrid(np.linspace(0, LT.FRAME_W, 97), np.linspace(0, LT.FRAME_H, 55))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    inb = hull_mask(P0, P1, grid)
    common = grid[inb]
    from scipy.spatial import ConvexHull
    a0 = ConvexHull(P0).volume; a1 = ConvexHull(P1).volume
    say(f"      convex-hull areas: capture 0 {a0 / 1e6:.3f} Mpx^2, capture 1 {a1 / 1e6:.3f} Mpx^2; "
        f"common support {len(common)} of {len(grid)} grid nodes "
        f"({100 * len(common) / len(grid):.1f}% of frame)")
    if len(common) < 200:
        say(f"      *** common informed support is too small for a reliable map comparison; "
            f"reporting that rather than extrapolating ***")
    ext = common.max(axis=0) - common.min(axis=0)
    say(f"      common-support extent {ext[0]:.0f} x {ext[1]:.0f} px, centroid "
        f"({common[:, 0].mean():.0f}, {common[:, 1].mean():.0f}) vs frame centre "
        f"({LT.FRAME_W / 2:.0f}, {LT.FRAME_H / 2:.0f})")

    md01 = gauge_mapdiff(common, sfits[0]["theta14"], sfits[1]["theta14"])
    md0s = gauge_mapdiff(common, sfits[0]["theta14"], shared["theta14"])
    md1s = gauge_mapdiff(common, sfits[1]["theta14"], shared["theta14"])
    say(f"      map differences over the COMMON support only:")
    for nm, m in (("capture0 vs capture1", md01), ("capture0 vs shared", md0s),
                  ("capture1 vs shared", md1s)):
        say(f"        {nm:22} raw median {m['median']:8.4f} p95 {m['p95']:8.4f} max "
            f"{m['max']:8.4f} | gauge-removed median {m['gauge_removed_median']:8.4f} p95 "
            f"{m['gauge_removed_p95']:8.4f} max {m['gauge_removed_max']:8.4f} px")

    say(f"\n      CROSS-EVALUATION: each distortion map on each capture, that capture's OWN "
        f"homography reprofiled and its OWN fixed Delaunay weights used")
    tab = {}
    names = ["capture-1-only map", "capture-2-only map", "shared map"]
    ths = [sfits[0]["theta14"], sfits[1]["theta14"], shared["theta14"]]
    for nm, th in zip(names, ths):
        row = []
        for ci in range(2):
            Dc = subs[ci]
            loss, v, _, _ = resid_vectors(Dc, th, Dc.w)
            d = np.linalg.norm(v, axis=1)
            ws = Dc.w / Dc.w.sum()
            row.append({"loss": loss, "unweighted_rms": float(np.sqrt((d ** 2).mean())),
                        "weighted_rms": float(math.sqrt(float(ws @ (d ** 2))))})
        tab[nm] = row
    say(f"      | {'distortion map':20} | {'capture 1 wRMS px':>18} | {'capture 2 wRMS px':>18} |")
    say(f"      | {'-' * 20} | {'-' * 18} | {'-' * 18} |")
    for nm in names:
        say(f"      | {nm:20} | {tab[nm][0]['weighted_rms']:18.5f} | "
            f"{tab[nm][1]['weighted_rms']:18.5f} |")
    own = [tab[names[i]][i]["weighted_rms"] for i in range(2)]
    xfer = [tab[names[1]][0]["weighted_rms"], tab[names[0]][1]["weighted_rms"]]
    say(f"      transfer penalty: capture 1 {xfer[0] - own[0]:+.5f} px, capture 2 "
        f"{xfer[1] - own[1]:+.5f} px (cross minus own)")
    sh = [tab["shared map"][i]["weighted_rms"] for i in range(2)]
    say(f"      shared-map penalty vs own: capture 1 {sh[0] - own[0]:+.5f} px, capture 2 "
        f"{sh[1] - own[1]:+.5f} px")
    # Elapsed time decoded with production's OWN convention rather than by reading the last field as
    # decimal seconds. UtilityFunctions.mm:163 formats timecodes as day:HH:mm:ss.subseconds/timescale
    # and :188 parses them back, so ".8/30" is 8/30 s = 0.267 s, not 0.8 s.
    tcs = [C.timecode for C in caps]

    def cmtime(s):
        p1 = s.split(":"); p2 = p1[3].split("."); p3 = p2[1].split("/")
        ts = int(p3[1])
        return (ts * (86400 * int(p1[0]) + 3600 * int(p1[1]) + 60 * int(p1[2]) + int(p2[0]))
                + int(p3[0])), ts

    (v0, ts), (v1, _) = cmtime(tcs[0]), cmtime(tcs[1])
    dt = (v1 - v0) / ts
    say(f"\n      INTERPRETATION. Captures {tcs[0]} and {tcs[1]} are {v1 - v0} frames = {dt:.3f} s "
        f"apart in production's convention (day:HH:mm:ss.subseconds/timescale). Reading the last "
        f"field as decimal seconds would wrongly give 3.2 s.")
    say(f"      The lens did not physically change in {dt:.1f} s. That is NOT the same as saying the "
        f"best EFFECTIVE fitted map cannot differ: in {dt:.1f} s the target can be repositioned, and "
        f"the effective map legitimately varies with target configuration.")
    say(f"      Candidate contributors, none of them separated by this test: target pose or distance, "
        f"noncentral geometry, target nonplanarity, detector bias, differing spatial support, and "
        f"ordinary estimator variability.")
    say(f"      SCOPE. The gauge-removed difference above is ONE between-capture contrast on one "
        f"document, not an estimated general systematic floor; two captures cannot support a variance "
        f"component. The linearized eta standard errors describe within-fit precision only.")
    results["_interp"] = {"timecodes": tcs, "frames_apart": int(v1 - v0), "timescale": ts,
                          "seconds_apart": dt,
                          "convention": "day:HH:mm:ss.subseconds/timescale; "
                                        "UtilityFunctions.mm:163 format, :188 parse"}
    results["captures"] = {
        "separate": [{k: (v.tolist() if isinstance(v, np.ndarray) else v)
                      for k, v in f.items() if k not in ("ev", "p", "D")} for f in sfits],
        "shared": {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                   for k, v in shared.items() if k not in ("ev", "p")},
        "common_support": {"grid_nodes": int(len(common)), "of": int(len(grid)),
                           "hull_area_cap0": a0, "hull_area_cap1": a1,
                           "extent": ext.tolist()},
        "map_differences_common_support": {"cap0_vs_cap1": md01, "cap0_vs_shared": md0s,
                                          "cap1_vs_shared": md1s},
        "cross_table": tab,
        "transfer_penalty_px": xfer, "own_px": own, "shared_penalty_px": sh}
    return subs, sfits, shared, common, md01


# =============================================================== 5. harmonics


def harmonic_regression(rt, w, mmax=4):
    """Joint weighted radial-by-harmonic regression, all harmonics estimated SIMULTANEOUSLY.

    Round 1 used the per-harmonic projection 2*mean(y cos m phi), which is only the least-squares
    estimate when the angular sampling is orthogonal. Angular coverage here is incomplete, so that
    estimator leaks power between harmonics. This fits

        y ~ a_0 + a_r rho + sum_{m=1..mmax} [ a_m cos(m phi) + b_m sin(m phi) ]

    jointly by weighted least squares, with rho the centred normalized radius so that a_0 is the
    weighted mean (the m = 0 level) and a_r its radial trend.

    PHASE CONVENTION, stated explicitly: phi = atan2(y - c_y, x - c_x) in RAW image pixels with y
    increasing DOWNWARD, so phi runs clockwise on screen. Each harmonic is reported as
    A_m cos(m (phi - phi_m)) with A_m = hypot(a_m, b_m) and phi_m = atan2(b_m, a_m) / m in degrees,
    i.e. the phase is the image-space angle of the harmonic's first maximum, not the argument m*phi_m.
    """
    phi, r = rt["phi"], rt["r"]
    rho = r / r.max()
    rho = rho - float(np.average(rho, weights=w))
    cols = [np.ones_like(phi), rho]
    names = ["m0_const", "radial_trend"]
    for m in range(1, mmax + 1):
        cols += [np.cos(m * phi), np.sin(m * phi)]
        names += [f"cos{m}", f"sin{m}"]
    X = np.stack(cols, axis=1)
    sw = np.sqrt(w)
    Xw = X * sw[:, None]
    # conditioning of the design as actually sampled, on unit-norm columns so it is scale free
    nrm = np.linalg.norm(Xw, axis=0)
    Xn = Xw / np.where(nrm > 0, nrm, 1.0)
    G = Xn.T @ Xn
    off = G - np.diag(np.diag(G))
    out = {"gram_condition": float(np.linalg.cond(G)),
           "max_abs_regressor_correlation": float(np.abs(off).max()),
           "worst_pair": [names[i] for i in np.unravel_index(np.abs(off).argmax(), off.shape)],
           "n": int(len(phi)), "components": {}}
    for comp in ("rad", "tan"):
        y = rt[comp]
        beta, *_ = np.linalg.lstsq(Xw, y * sw, rcond=None)
        pred = X @ beta
        res = y - pred
        d = {"m0_level": float(beta[0]), "radial_trend": float(beta[1]),
             "weighted_rms_total": float(math.sqrt(float((w / w.sum()) @ (y ** 2)))),
             "weighted_rms_after_removal": float(math.sqrt(float((w / w.sum()) @ (res ** 2)))),
             "harmonics": {}}
        for m in range(1, mmax + 1):
            a, b = float(beta[2 * m]), float(beta[2 * m + 1])
            amp = math.hypot(a, b)
            # naive per-harmonic projection, for comparison against the joint estimate
            na = 2.0 * float(np.average(y * np.cos(m * phi), weights=w))
            nb = 2.0 * float(np.average(y * np.sin(m * phi), weights=w))
            d["harmonics"][m] = {"cos": a, "sin": b, "amplitude": amp,
                                 "phase_deg": math.degrees(math.atan2(b, a)) / m,
                                 "naive_projection_amplitude": math.hypot(na, nb)}
        out["components"][comp] = d
    return out


def spatial_coherence(xy, rt):
    """Nearest-neighbour correlation of each residual component: cheap residual-structure check."""
    from scipy.spatial import cKDTree
    _, idx = cKDTree(xy).query(xy, k=2)
    nn = idx[:, 1]
    out = {}
    for comp in ("rad", "tan"):
        y = rt[comp]
        a, b = y - y.mean(), y[nn] - y.mean()
        s = float(np.sqrt((a ** 2).mean() * (b ** 2).mean()))
        out[f"{comp}_nn_correlation"] = float((a * b).mean() / s) if s > 0 else float("nan")
    return out


def section_harmonics(say, clip, D, ev_maps, results):
    say(f"\n    HARMONIC / ISOTROPY DIAGNOSTICS of the exact raw projective residual")
    say(f"      phase convention: phi = atan2(y - cy, x - cx) in raw pixels, y DOWNWARD; harmonic "
        f"reported as A_m cos(m(phi - phi_m)), phi_m in degrees of image angle")
    rows = {}
    for key, dw in [(("B", "M1"), "uniform"), (("U", "M1"), "uniform"), (("D", "M1"), "delaunay")]:
        e = ev_maps[key]
        rt = e["_rtu"] if dw == "uniform" else e["_rtd"]
        w = np.ones(D.n) if dw == "uniform" else D.w
        h = harmonic_regression(rt, w)
        h["diagnostic_weighting"] = dw
        h["spatial_coherence"] = spatial_coherence(D.xy, rt)
        # a common diagnostic weighting so the three maps are directly comparable
        hc = harmonic_regression(e["_rtu"], np.ones(D.n))
        rows[f"{key[0]}/{key[1]}"] = {"native": h, "common_uniform": hc}
        say(f"\n      {e['label']}   (native diagnostic weighting: {dw})")
        say(f"        Gram condition {h['gram_condition']:.3f}, max regressor correlation "
            f"{h['max_abs_regressor_correlation']:.4f} between {h['worst_pair'][0]} and "
            f"{h['worst_pair'][1]}")
        for comp in ("rad", "tan"):
            c = h["components"][comp]
            say(f"        {comp}: RMS {c['weighted_rms_total']:.4f} px, m0 level "
                f"{c['m0_level']:+.4f}, radial trend {c['radial_trend']:+.4f}, RMS after removing "
                f"all fitted structure {c['weighted_rms_after_removal']:.4f}")
            for m in (1, 2, 3, 4):
                hm = c["harmonics"][m]
                say(f"          m={m}  amp {hm['amplitude']:7.4f} px  phase "
                    f"{hm['phase_deg']:+8.2f} deg   (naive projection would give "
                    f"{hm['naive_projection_amplitude']:7.4f})")
        say(f"        radial/tangential RMS ratio "
            f"{(h['components']['rad']['weighted_rms_total'] / max(h['components']['tan']['weighted_rms_total'], 1e-30)):.4f}")
        say(f"        nearest-neighbour residual correlation: radial "
            f"{h['spatial_coherence']['rad_nn_correlation']:+.4f}, tangential "
            f"{h['spatial_coherence']['tan_nn_correlation']:+.4f}")
    results["harmonics"] = rows
    return rows


# =============================================================== plots


def plot_weights(clip, caps, D, rows, path):
    fig, ax = plt.subplots(1, 3, figsize=(17, 4.6))
    prim = [r for r in rows if r["label"].startswith("PRIMARY") and r["kappa"] == 3.0][0]
    unm = [r for r in rows if r["label"].startswith("all") and r["kappa"] == 3.0][0]
    sc = ax[0].scatter(D.xy[:, 0], D.xy[:, 1], c=prim["w"], s=16, cmap="viridis")
    ax[0].set_title(f"{clip}\nPRIMARY fitted subset n={prim['n_observations_triangulated']}, "
                    f"{prim['triangles_retained']} triangles", fontsize=9)
    plt.colorbar(sc, ax=ax[0])
    allxy = np.concatenate([C.xy for C in caps])
    sc = ax[1].scatter(allxy[:, 0], allxy[:, 1], c=unm["w"], s=16, cmap="viridis")
    ax[1].set_title(f"{clip}\nUNMASKED all n={unm['n_observations_triangulated']}, "
                    f"{unm['triangles_retained']} triangles", fontsize=9)
    plt.colorbar(sc, ax=ax[1])
    for r in rows:
        if r["label"].startswith("PRIMARY"):
            ax[2].plot(r["kappa"], r["triangles_retained"], "o-", color="C0")
        else:
            ax[2].plot(r["kappa"], r["triangles_retained"], "s-", color="C1")
    ax[2].plot([], [], "o-", color="C0", label="primary fitted subset")
    ax[2].plot([], [], "s-", color="C1", label="all observations")
    ax[2].set_xlabel("kappa"); ax[2].set_ylabel("triangles retained")
    ax[2].set_title("the count discrepancy explained", fontsize=9); ax[2].legend(fontsize=8)
    ax[2].grid(alpha=0.3)
    for a in ax[:2]:
        a.invert_yaxis(); a.set_aspect("equal"); a.set_xlim(0, LT.FRAME_W)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def plot_common_support(clip, subs, sfits, common, path):
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    ax[0].scatter(common[:, 0], common[:, 1], s=4, c="0.85", label="common informed support")
    ax[0].scatter(subs[0].xy[:, 0], subs[0].xy[:, 1], s=10, label="capture 0")
    ax[0].scatter(subs[1].xy[:, 0], subs[1].xy[:, 1], s=10, label="capture 1")
    ax[0].set_title(f"{clip}: capture support", fontsize=9); ax[0].legend(fontsize=8)
    U0 = LT.U(common, sfits[0]["theta14"]); U1 = LT.U(common, sfits[1]["theta14"])
    g = GA.fit_homography(U0, U1)
    eg = np.linalg.norm(GA.apply_H(g, U0) - U1, axis=1)
    sc = ax[1].scatter(common[:, 0], common[:, 1], c=eg, s=10, cmap="magma")
    ax[1].set_title(f"{clip}: capture0 vs capture1 map difference,\nprojective gauge removed "
                    f"(median {np.median(eg):.4f} px)", fontsize=9)
    plt.colorbar(sc, ax=ax[1])
    for a in ax:
        a.invert_yaxis(); a.set_aspect("equal"); a.set_xlim(0, LT.FRAME_W)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def plot_harmonics(clip, D, ev_maps, rows, path):
    keys = [("B", "M1"), ("U", "M1"), ("D", "M1")]
    fig, ax = plt.subplots(2, 3, figsize=(16, 8))
    for j, key in enumerate(keys):
        e = ev_maps[key]
        v = e["_vu"]
        q = ax[0, j].quiver(D.xy[:, 0], D.xy[:, 1], v[:, 0], v[:, 1], np.linalg.norm(v, axis=1),
                            cmap="magma", scale=8.0, width=0.004)
        ax[0, j].set_title(f"{e['label']}\nexact projective residual (rms "
                           f"{np.sqrt((np.linalg.norm(v, axis=1) ** 2).mean()):.4f} px)", fontsize=9)
        ax[0, j].invert_yaxis(); ax[0, j].set_aspect("equal"); ax[0, j].set_xlim(0, LT.FRAME_W)
        plt.colorbar(q, ax=ax[0, j])
        h = rows[f"{key[0]}/{key[1]}"]["common_uniform"]
        ms = [1, 2, 3, 4]
        wd = 0.35
        for i, comp in enumerate(("rad", "tan")):
            amps = [h["components"][comp]["harmonics"][m]["amplitude"] for m in ms]
            nai = [h["components"][comp]["harmonics"][m]["naive_projection_amplitude"] for m in ms]
            ax[1, j].bar(np.array(ms) + (i - 0.5) * wd, amps, wd * 0.8,
                         label=f"{comp} joint fit")
            ax[1, j].plot(np.array(ms) + (i - 0.5) * wd, nai, "k_", ms=10,
                          label="naive projection" if i == 0 else None)
        ax[1, j].set_xlabel("harmonic m"); ax[1, j].set_ylabel("amplitude px")
        ax[1, j].set_xticks(ms); ax[1, j].legend(fontsize=7); ax[1, j].grid(alpha=0.3)
        ax[1, j].set_title("common uniform diagnostic weighting", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--clips", nargs="*", default=CLIPS)
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = artifacts.ArtifactWriter(
        analysis="obj_pd_closure", script=__file__, outdir=args.outdir,
        requested_documents=args.clips, all_documents=CLIPS,
        requested_candidates=["PD-D/M0", "PD-D/M1", "PD-U/M1"],
        source_files=["obj_pd_closure.py", "objectives.py", "lattice.py", "artifacts.py"],
        calibration_node_source="not used: plumbline/lattice observations only")
    log = open(os.path.join(args.outdir, "obj_pd_closure.log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R1 = json.load(open(os.path.join(args.outdir, "obj_round1.json")))
    results = {}

    say("=" * 104)
    say("EXACT PROJECTIVE-LATTICE CLOSURE ROUND")
    say("=" * 104)
    say("  Weighting audit, strict M0/M1 nesting, uniform vs Delaunay quadrature, Left-capture")
    say("  consistency, and harmonic isotropy. All fits use objectives.PDExact with its analytic")
    say("  Jacobian. Nothing is promoted on the strength of this round.")

    for clip in args.clips:
        caps = LT.load_captures(args.vsd, clip)
        D = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
        rc = results[clip] = {"n_observations": D.n, "ncap": D.ncap, "_r1": R1[clip]}
        thB0 = np.array(R1[clip]["fits"]["B/M0"]["theta14"], float)
        thB1 = np.array(R1[clip]["fits"]["B/M1"]["theta14"], float)
        say(f"\n{'=' * 104}\n  {clip}: {D.n} fitted observations, {D.ncap} capture(s)\n{'=' * 104}")

        rows = section_weights(say, clip, caps, D, rc)
        plot_weights(clip, caps, D, rows,
                     os.path.join(args.outdir, f"obj_pd_closure_weights_{clip.split()[0]}.png"))
        section_nesting(say, clip, D, thB0, thB1, rc)
        fits, ev_maps = section_weighting(say, clip, caps, D, D.w, thB0, thB1, rc)
        if D.ncap >= 2:
            subs, sfits, shared, common, md01 = section_captures(say, clip, caps, D, thB1, rc)
            plot_common_support(clip, subs, sfits, common,
                               os.path.join(args.outdir,
                                            f"obj_pd_closure_support_{clip.split()[0]}.png"))
        else:
            say(f"\n    LEFT-CAPTURE CONSISTENCY: skipped, {clip} has one capture")
        hrows = section_harmonics(say, clip, D, ev_maps, rc)
        plot_harmonics(clip, D, ev_maps, hrows,
                       os.path.join(args.outdir,
                                    f"obj_pd_closure_harmonics_{clip.split()[0]}.png"))
        del rc["_r1"]

    say(f"\n{'=' * 104}\n  RUNTIME\n{'=' * 104}")
    if SLOW:
        for lbl, w, c in SLOW:
            say(f"    *** {lbl} took {w:.3f} s, over the {FIT_LIMIT_S} s per-fit limit; counters {c}")
    else:
        say(f"    every fit finished well inside the {FIT_LIMIT_S:.0f} s per-fit limit")
    say(f"    total {time.time() - t00:.1f} s")
    for clip in args.clips:
        if clip in results:
            W.document_completed(clip, completed_candidates=["PD-D/M0", "PD-D/M1", "PD-U/M1"])
    # Atomic, with the manifest embedded under "_manifest" so downstream_parity.py's
    # {clip: ...} reader keeps working. A partial clip scope goes to a _partial name instead.
    apath = W.write_embedded(results, "obj_pd_closure.json")
    say(f"    wrote {apath} (complete={W.manifest()['complete']}) and 3 plots per camera")
    return 0


if __name__ == "__main__":
    sys.exit(main())
