#!/usr/bin/env python3
"""Downstream known-length evaluation of POINT-CLOUD ground truth, for any cloud-bearing document.

WHY THIS EXISTS. xdoc_objectives.py is the production-faithful downstream path, but it measures only
`D0["conventional"]`. The 10 mm document 2015-07-10-1 Chena carries ZERO conventional measurements and
1070 within-cloud pairs, so before this script there was no route from the 10 mm ground truth to a
rebuilt stereo measurement at all. That was the blocker, and it is new code rather than a re-run.

WHAT IS THE SAME AS xdoc_objectives.py, deliberately: bound calibrations (downstream.load_bound_cals),
one DistortionMap per camera bound to that camera's CameraIdentity, DS.build_calibration to rebuild the
whole refractive geometry conditional on the candidate map, DS.triangulate_lm for endpoints, and
fail-closed exclusion of any candidate whose fit is invalid on either camera. Calibration fits are
selected by their own calibration objectives and gates ONLY; known-length never chooses a fit.

WHAT IS NEW.

  M0-FIRST INITIALIZATION AND AN EXPLICIT M1 GATE. A solver `success` flag is not a safeguard: on the
  8 mm document an off-centre B/M1 start reported completed=True at loss 25008 against 282 for the good
  basin, a 716 px map difference. Every M1 fit here is warm-started from the SAME OBJECTIVE's converged
  M0 fit with eta = 0, must then improve that objective's own loss, and must pass the physical-map
  gates (finite parameters, positive eta-aware Jacobian determinant over the working domain, radial
  scale, conditioning, Newton inverse round trip). If any of that fails, M1 is REJECTED and the
  already-accepted M0 map stands. `gate` records which test failed.

  CLOUDS ARE THE DEPENDENCE UNIT. A cloud of n points yields n(n-1)/2 pairs in which each point appears
  n-1 times, so pair count is not a sample size. Every headline number here is either per-cloud or
  cloud-balanced (the unweighted mean over clouds, so a 26-point cloud does not outvote a 16-point one
  through pair count alone). All-pair pooled summaries are printed too, labelled DESCRIPTIVE. Nothing
  is bootstrapped over pairs and 1070 is never presented as an effective sample size; with four clouds
  the four paired cloud effects are shown directly instead of an interval built on an assumption.

  A DIGITIZATION AUDIT that needs the reconstruction: per-point incident pair error, leave-one-point-out
  cloud metrics, out-of-plane residual against each placement's own best-fit plane, a scale-locked
  Procrustes fit of the reconstructed points onto that cloud's note coordinates (which localizes a
  single bad click far better than any pair statistic), a left/right swap test on the worst points, and
  duplicate-click detection.

Cloud-bearing documents are DISCOVERED, not hard-coded, so the same evaluator serves the 8 mm
regression check and anything digitized later. Writes analysis-output/cloud_downstream_<scope>.{log,json}
plus per-pair and per-point CSVs. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np

import artifacts
import fitvalidity as FV
import harness_import

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")

L = harness_import.load
DS = L("downstream")
LT = L("lattice")
OB = L("objectives")
kl = L("knownlength")
corpus = L("corpus")

# PD-D and B only. SD-D is the NON-LATTICE FALLBACK: its production-equivalent driver is sd_fast via
# sd_real.Fitter and its maps are reused through a verified provenance artifact, never refit through
# objectives.resid_SD (whose finite-difference tolerances are unreachable by construction, so it is
# always ruled non-convergent). Refitting it here would manufacture exactly that artefact, so it is
# omitted rather than reported badly. Both documents below are PD-D admissible, so the fallback is not
# the question the 10 mm ground truth answers.
OBJECTIVES = ["B", "PD-D"]
CANDIDATES = ["stored"] + [f"{o}/{m}" for o in OBJECTIVES for m in ("M0", "M1")]
B_MAX_NFEV = 3000


def stats(err):
    e = np.abs(np.asarray(err, float)); s = np.asarray(err, float)
    if e.size == 0:
        return {"n": 0}
    return {"n": int(e.size), "mae": float(e.mean()), "rmse": float(math.sqrt((s ** 2).mean())),
            "med": float(np.median(e)), "bias": float(s.mean()),
            "p90": float(np.percentile(e, 90)), "p95": float(np.percentile(e, 95)),
            "max": float(e.max())}


def cloud_balanced(per_cloud, key):
    """Unweighted mean over clouds. The whole point is that it does NOT weight by pair count."""
    v = [s[key] for s in per_cloud.values() if s.get("n")]
    return float(np.mean(v)) if v else float("nan")


# =============================================================== gated fitting


def _gate_map(th14, node_pts):
    """The physical-map gates, estimator-neutral. Never sqrt(loss/n), which is incommensurate."""
    th14 = np.asarray(th14, float)
    if not np.all(np.isfinite(th14)):
        return {"ok": False, "why": "nonfinite parameters"}
    ad = LT.admissible(th14, node_pts)
    why = []
    if not ad["gate_ok"]:
        why.append(f"production gate failed (radial scale {ad['R_scale']:.4f}, "
                   f"min core det {ad['min_det_core_box']:.4g})")
    if not ad["eta_in_bound"]:
        why.append(f"eta {ad['eta']:+.6f} out of bound")
    if not ad["min_det_full_box"] > 0.0:
        why.append(f"eta-aware Jacobian determinant reaches {ad['min_det_full_box']:.4g} <= 0, "
                   f"so the map is not locally injective on the working domain")
    if not ad["roundtrip_box_all_converged"]:
        why.append("Newton inverse did not converge on the working domain")
    if not ad["roundtrip_box_px"] < 1e-9:
        why.append(f"inverse round trip {ad['roundtrip_box_px']:.3g} px")
    return {"ok": not why, "why": "; ".join(why),
            "R_scale": ad["R_scale"], "min_det_full_box": ad["min_det_full_box"],
            "min_det_full_frame": ad["min_det_full_frame"],
            "max_local_aniso_box": ad["max_local_aniso_box"],
            "roundtrip_box_px": ad["roundtrip_box_px"], "eta": ad["eta"]}


def fit_gated(say, D, node_pts, clip):
    """B and PD-D at M0 then M1, M1 warm-started from its own objective's M0 fit with eta = 0.

    Returns {name: theta14}, diagnostics, FitValidity records. An M1 fit that fails to improve its own
    objective, or fails a map gate, is recorded and DROPPED -- the transaction returns the accepted M0
    map, which is what production would keep.
    """
    out, diag = {}, {}
    # ---- B/M0, the initialization every other objective uses
    t0 = time.time()
    r0 = OB.fit(D, "B", "M0", warm=False, max_nfev=B_MAX_NFEV)
    out["B/M0"] = np.array(r0["theta14"], float)
    diag["B/M0"] = {"loss": r0["loss"], "nfev": r0["nfev"], "status": r0["status"],
                    "eta": r0["eta"], "wall_s": time.time() - t0, "init": "cold (undistorted base)",
                    "objective_note": "B's own line-ODR cost; comparable between B/M0 and B/M1 "
                                      "because M1 nests M0, and NOT across objectives"}
    # ---- B/M1 warm-started from B/M0 with eta = 0
    fr1 = OB.MODELS["M1"]
    x0 = out["B/M0"].copy(); x0[13] = 0.0
    t0 = time.time()
    r1 = OB.fit(D, "B", "M1", x0_model=x0[fr1] / OB.SCALE14[fr1], warm=False, max_nfev=B_MAX_NFEV)
    diag["B/M1"] = {"loss": r1["loss"], "nfev": r1["nfev"], "status": r1["status"],
                    "eta": r1["eta"], "wall_s": time.time() - t0,
                    "init": "warm from B/M0 with eta = 0",
                    "objective_note": diag["B/M0"]["objective_note"]}
    out["B/M1"] = np.array(r1["theta14"], float)

    # ---- PD-D/M0 from B/M0's DLT
    ev0 = OB.PDExact(D, "M0")
    res0, w0 = ev0.fit(ev0.init_dlt(out["B/M0"]))
    th_pd0 = ev0.theta(res0.x)
    out["PD-D/M0"] = th_pd0
    diag["PD-D/M0"] = {"loss": float(2 * res0.cost), "nfev": int(res0.nfev),
                       "status": int(res0.status), "eta": float(th_pd0[13]), "wall_s": w0,
                       "optimality": float(res0.optimality),
                       "projected_condition": ev0.projected_conditioning(res0.x)["condition"],
                       "inverse_failures": ev0.C["inverse_failures"],
                       "init": "DLT from B/M0",
                       "objective_note": "exact projective lattice cost; comparable M0 vs M1, not "
                                         "across objectives"}
    # ---- PD-D/M1 warm-started from the PD-D/M0 OPTIMUM with eta = 0, not from B
    ev1 = OB.PDExact(D, "M1")
    th_seed = th_pd0.copy(); th_seed[13] = 0.0
    res1, w1 = ev1.fit(ev1.init_dlt(th_seed))
    th_pd1 = ev1.theta(res1.x)
    out["PD-D/M1"] = th_pd1
    diag["PD-D/M1"] = {"loss": float(2 * res1.cost), "nfev": int(res1.nfev),
                       "status": int(res1.status), "eta": float(th_pd1[13]), "wall_s": w1,
                       "optimality": float(res1.optimality),
                       "projected_condition": ev1.projected_conditioning(res1.x)["condition"],
                       "inverse_failures": ev1.C["inverse_failures"],
                       "init": "DLT from the converged PD-D/M0 map with eta = 0",
                       "objective_note": diag["PD-D/M0"]["objective_note"]}

    # ---- gates: map physics for everything, plus the nesting requirement for M1
    for k in list(out):
        diag[k]["gate"] = _gate_map(out[k], node_pts)
    for obj in OBJECTIVES:
        l0, l1 = diag[f"{obj}/M0"]["loss"], diag[f"{obj}/M1"]["loss"]
        tol = 1e-9 * max(abs(l0), 1.0)
        improved = bool(l1 <= l0 + tol)
        diag[f"{obj}/M1"]["improves_own_M0_objective"] = improved
        diag[f"{obj}/M1"]["own_loss_M0"] = l0
        diag[f"{obj}/M1"]["loss_ratio_M1_over_M0"] = float(l1 / l0) if l0 else float("nan")
        if not improved:
            diag[f"{obj}/M1"]["gate"]["ok"] = False
            diag[f"{obj}/M1"]["gate"]["why"] = (
                f"M1 loss {l1:.6g} does not improve its own M0 loss {l0:.6g}; the extra parameter "
                f"found a worse basin, so M0 stands" + (
                    "; " + diag[f"{obj}/M1"]["gate"]["why"] if diag[f"{obj}/M1"]["gate"]["why"]
                    else ""))

    val = {}
    for k, d in diag.items():
        cap = B_MAX_NFEV if k.startswith("B/") else None
        v = FV.from_least_squares(k, d, max_nfev=cap, theta14=out[k])
        v.admissible = bool(d["gate"]["ok"])
        v.inverse_ok = bool(d["gate"].get("roundtrip_box_px", 1.0) < 1e-9)
        v.extra["min_det_full_frame"] = d["gate"].get("min_det_full_frame")
        v.extra["gate_why"] = d["gate"]["why"]
        val[k] = v

    say(f"        {'fit':10} {'ownLoss':>15} {'nfev':>6} {'stat':>5} {'eta':>12} {'wall s':>8} "
        f"{'gate':>6}  init / note")
    for k in ["B/M0", "B/M1", "PD-D/M0", "PD-D/M1"]:
        d = diag[k]
        say(f"        {k:10} {d['loss']:15.5f} {d['nfev']:6d} {d['status']:5d} "
            f"{d['eta']:+12.7f} {d['wall_s']:8.2f} {'ok' if d['gate']['ok'] else 'REJECT':>6}  "
            f"{d['init']}")
        if not d["gate"]["ok"]:
            say(f"          {k} GATE FAILURE -> M0 stands: {d['gate']['why']}")
    return out, diag, val


# =============================================================== downstream measurement


def measure(say, cals, maps, pairs, clicks, unit_mm, validities):
    """Rebuild each candidate's whole downstream geometry and measure EVERY pair, same pairs for all.

    Returns {name: rows}, {name: caldiag}. A candidate invalid or gate-rejected on either camera is
    reconstructed not at all: a stereo measurement needs both cameras.
    """
    clips = sorted(cals)
    rows, cdiag, pts3d = {}, {}, {}
    for name, per in maps.items():
        cams = {c: DS.build_calibration(cals[c], per[c]) for c in clips}
        cdiag[name] = {c: {**DS.node_residuals(cals[c], cams[c]),
                           "cam": list(cams[c]["cam"])} for c in clips}
        if name != "stored":
            bad = FV.invalid_reasons(validities, name, clips)
            if bad:
                say(f"        {name:10} EXCLUDED from measurements -- {bad}")
                cdiag[name]["_excluded"] = bad
                continue
        need = sorted({pk for r in pairs for pk in r["pks"]})
        X, PD = {}, {}
        for pk in need:
            obs = DS.observations(pk, cams, clicks)
            if len(obs) < 2:
                continue
            t = DS.triangulate_lm(obs)
            X[pk] = t["X"]
            d = DS.point_diagnostics(obs, t["X"])
            PD[pk] = {**d, "rep_px": t["rep"], "tri_cost": t["cost"],
                      "clicks": {c: list(clicks[pk][c]) for c in clips if c in clicks.get(pk, {})}}
        pts3d[name] = {"X": X, "diag": PD}
        rr = []
        for r in pairs:
            a, b = r["pks"]
            if a not in X or b not in X:
                continue
            d = float(np.linalg.norm(X[a] - X[b])) * unit_mm
            rr.append({"key": r["key"], "group": r["group"], "tc": r["tc"], "true": r["true"],
                       "meas": d, "err": d - r["true"],
                       "pct": 100.0 * (d - r["true"]) / r["true"],
                       "i": r["i"], "j": r["j"],
                       "radius": max(PD[a]["radius"], PD[b]["radius"]),
                       "edge": min(PD[a]["edge"], PD[b]["edge"]),
                       "rep_px": max(PD[a]["rep_px"], PD[b]["rep_px"]),
                       "camdist": 0.5 * (PD[a]["camdist"] + PD[b]["camdist"]) * unit_mm,
                       "orient_deg": r.get("orient_deg", float("nan"))})
        rows[name] = rr
    return rows, cdiag, pts3d


# =============================================================== reporting


def report_groups(say, rows, R, tag, label, reportable, group_label="cloud"):
    """Per-group, cloud-balanced, then pooled-and-labelled-descriptive."""
    say(f"\n      PER-{group_label.upper()} RESULTS -- {label}")
    per = {}
    groups = sorted({r["group"] for rr in rows.values() for r in rr})
    for name in reportable:
        per[name] = {g: stats([r["err"] for r in rows[name] if r["group"] == g]) for g in groups}
    say(f"        {'candidate':10} {group_label:12} {'nPairs':>7} {'MAE':>9} {'RMSE':>9} "
        f"{'median':>9} {'bias':>9} {'p90':>9} {'p95':>9} {'max':>9}")
    for name in reportable:
        for g in groups:
            s = per[name][g]
            if not s.get("n"):
                continue
            say(f"        {name:10} {g:12} {s['n']:7d} {s['mae']:9.4f} {s['rmse']:9.4f} "
                f"{s['med']:9.4f} {s['bias']:+9.4f} {s['p90']:9.4f} {s['p95']:9.4f} "
                f"{s['max']:9.4f}")
    say(f"\n      {group_label.upper()}-BALANCED AGGREGATE (unweighted mean over "
        f"{len(groups)} {group_label}s, so pair count does not decide the answer)")
    say(f"        {'candidate':10} {'MAE':>9} {'RMSE':>9} {'median':>9} {'bias':>9} {'p90':>9} "
        f"{'max':>9}")
    bal = {}
    for name in reportable:
        bal[name] = {k: cloud_balanced(per[name], k)
                     for k in ("mae", "rmse", "med", "bias", "p90", "p95", "max")}
        b = bal[name]
        say(f"        {name:10} {b['mae']:9.4f} {b['rmse']:9.4f} {b['med']:9.4f} "
            f"{b['bias']:+9.4f} {b['p90']:9.4f} {b['max']:9.4f}")
    say(f"\n      POOLED OVER ALL PAIRS -- DESCRIPTIVE ONLY. The pairs are strongly dependent (each "
        f"point sits in n-1 of them),")
    say(f"      so this is not a sample of independent measurements and its n is not an effective "
        f"sample size.")
    say(f"        {'candidate':10} {'nPairs':>7} {'MAE':>9} {'RMSE':>9} {'median':>9} {'bias':>9} "
        f"{'p90':>9} {'max':>9}")
    pool = {}
    for name in reportable:
        s = pool[name] = stats([r["err"] for r in rows[name]])
        say(f"        {name:10} {s['n']:7d} {s['mae']:9.4f} {s['rmse']:9.4f} {s['med']:9.4f} "
            f"{s['bias']:+9.4f} {s['p90']:9.4f} {s['max']:9.4f}")
    R.setdefault("per_group", {})[tag] = per
    R.setdefault("group_balanced", {})[tag] = bal
    R.setdefault("pooled_descriptive", {})[tag] = pool
    return per, bal, pool


def report_paired(say, rows, R, tag, contrasts, group_label="cloud"):
    """Paired M1-minus-M0 on EXACTLY the same pairs, shown as the individual group effects."""
    say(f"\n      PAIRED CONTRASTS on identical pairs. Negative means the FIRST candidate has the "
        f"smaller absolute error.")
    say(f"      With four {group_label}s the four paired effects are shown directly rather than "
        f"summarised by an interval.")
    C = {}
    for a, b in contrasts:
        if a not in rows or b not in rows:
            say(f"        {a} - {b:12} unavailable (a candidate was excluded or gate-rejected)")
            C[f"{a} minus {b}"] = {"available": False}
            continue
        ka = {r["key"]: r for r in rows[a]}
        kb = {r["key"]: r for r in rows[b]}
        keys = sorted(set(ka) & set(kb), key=str)
        pergrp = defaultdict(list)
        for k in keys:
            pergrp[ka[k]["group"]].append(abs(ka[k]["err"]) - abs(kb[k]["err"]))
        gm = {g: float(np.mean(v)) for g, v in sorted(pergrp.items())}
        gimp = {g: int(sum(1 for x in v if x < 0)) for g, v in sorted(pergrp.items())}
        gn = {g: len(v) for g, v in sorted(pergrp.items())}
        alld = np.array([abs(ka[k]["err"]) - abs(kb[k]["err"]) for k in keys])
        say(f"        {a} minus {b}   ({len(keys)} shared pairs)")
        for g in gm:
            say(f"          {g:12} n {gn[g]:5d}   mean d|err| {gm[g]:+9.4f} mm   pairs improved "
                f"{gimp[g]:5d}/{gn[g]:<5d}")
        say(f"          {group_label}-balanced mean d|err| {np.mean(list(gm.values())):+9.4f} mm; "
            f"{group_label}s improved {sum(1 for v in gm.values() if v < 0)}/{len(gm)}; "
            f"pooled (descriptive) {alld.mean():+9.4f} mm")
        C[f"{a} minus {b}"] = {"available": True, "n_pairs": len(keys),
                               "per_group_mean_d_abs_err": gm, "per_group_n": gn,
                               "per_group_pairs_improved": gimp,
                               "group_balanced_mean_d_abs_err": float(np.mean(list(gm.values()))),
                               "groups_improved": int(sum(1 for v in gm.values() if v < 0)),
                               "n_groups": len(gm),
                               "pooled_mean_d_abs_err_descriptive": float(alld.mean())}
    R.setdefault("paired", {})[tag] = C
    return C


def report_behaviour(say, rows, R, tag, reportable):
    """Behaviour by true distance, orientation, image location and placement, on fixed B/M0 bins."""
    base = rows.get("B/M0") or rows[reportable[-1]]
    say(f"\n      BEHAVIOUR BY COVARIATE (bins fixed from B/M0 geometry, identical pairs per bin)")
    out = {}
    specs = [("true length mm", "true", 4), ("pair orientation deg", "orient_deg", 4),
             ("max image radius px", "radius", 4), ("min screen edge px", "edge", 4),
             ("mean camera distance mm", "camdist", 4)]
    for gname, gkey, nq in specs:
        v = np.array([r[gkey] for r in base], float)
        if not np.isfinite(v).any():
            continue
        qs = np.nanpercentile(v, np.linspace(0, 100, nq + 1))
        say(f"        {gname}")
        out[gname] = []
        for b in range(nq):
            lo, hi = qs[b], qs[b + 1]
            idx = {r["key"] for r in base
                   if (r[gkey] >= lo and (r[gkey] <= hi if b == nq - 1 else r[gkey] < hi))}
            if not idx:
                continue
            cells = {n: float(np.mean([abs(r["err"]) for r in rows[n] if r["key"] in idx]))
                     for n in reportable}
            say(f"          [{lo:9.2f}, {hi:9.2f}] n {len(idx):5d}  " +
                "  ".join(f"{n} {cells[n]:7.3f}" for n in reportable))
            out[gname].append({"lo": float(lo), "hi": float(hi), "n": len(idx), "mae": cells})
    R.setdefault("behaviour", {})[tag] = out


# =============================================================== digitization audit


def _procrustes_locked(notes, P):
    """Best rigid placement of the 2D note frame into 3D with SCALE LOCKED AT 1 (mm onto mm).

    Locking the scale is the point: it makes the residual sensitive to a single mis-clicked point
    instead of absorbing the error into a global stretch. The free-scale factor is returned separately
    so a calibration scale error can be told apart from a digitization shape error.
    """
    N = np.asarray(notes, float); P = np.asarray(P, float)
    Nc, Pc = N - N.mean(0), P - P.mean(0)
    A = Pc.T @ Nc                                     # (3, 2)
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    Rm = U @ Vt                                       # (3, 2), orthonormal columns
    fit = Nc @ Rm.T
    resid = np.linalg.norm(Pc - fit, axis=1)
    denom = float((Nc ** 2).sum())
    scale = float(S.sum() / denom) if denom > 0 else float("nan")
    free = np.linalg.norm(Pc - scale * fit, axis=1)
    return {"resid_mm": resid, "rms_mm": float(math.sqrt((resid ** 2).mean())),
            "free_scale": scale, "resid_free_mm": free,
            "rms_free_mm": float(math.sqrt((free ** 2).mean()))}


def _plane_rms(P):
    P = np.asarray(P, float)
    c = P.mean(0)
    _, s, Vt = np.linalg.svd(P - c, full_matrices=False)
    n = Vt[-1]
    d = (P - c) @ n
    return float(math.sqrt((d ** 2).mean())), float(np.abs(d).max()), d


def audit(say, R, tag, doc, clouds, pairs, pts3d, cals, clicks, name):
    """Everything that needs the reconstruction. Reported for ONE candidate map, named in `name`."""
    if name not in pts3d:
        say(f"\n      DIGITIZATION AUDIT skipped: {name} was not reconstructed")
        return {}
    X, PDG = pts3d[name]["X"], pts3d[name]["diag"]
    clips = sorted(cals)
    say(f"\n      DIGITIZATION AND GEOMETRY AUDIT under {name}")
    say(f"      Reconstruction-dependent, so it is reported under ONE map; the point rankings are "
        f"stable across candidates because a bad click is bad under every map.")
    A = {"candidate": name, "clouds": {}, "points": [], "suspects": []}

    # incident pair error per point
    inc = defaultdict(list)
    ev2pk = {}
    for g, pts in clouds.items():
        for p in pts:
            ev2pk[p["event"]] = p["pk"]
    for r in pairs:
        a, b = r["pks"]
        if a not in X or b not in X:
            continue
        e = float(np.linalg.norm(X[a] - X[b])) - r["true"]
        inc[a].append(e); inc[b].append(e)

    say(f"\n        {'cloud':12} {'n':>4} {'planeRMS':>9} {'planeMax':>9} {'procRMS':>9} "
        f"{'procMax':>9} {'freeScale':>10} {'freeRMS':>9}  worst point")
    for g, pts in sorted(clouds.items()):
        use = [p for p in pts if p["pk"] in X]
        if len(use) < 3:
            continue
        P = np.array([X[p["pk"]] for p in use], float)
        N = np.array([p["mm"] for p in use], float)
        prms, pmax, dsign = _plane_rms(P)
        pr = _procrustes_locked(N, P)
        w = int(np.argmax(pr["resid_mm"]))
        A["clouds"][g] = {"n": len(use), "plane_rms_mm": prms, "plane_max_mm": pmax,
                          "procrustes_rms_mm": pr["rms_mm"],
                          "procrustes_max_mm": float(pr["resid_mm"].max()),
                          "free_scale": pr["free_scale"],
                          "procrustes_free_rms_mm": pr["rms_free_mm"],
                          "worst_event": int(use[w]["event"]),
                          "worst_resid_mm": float(pr["resid_mm"][w])}
        say(f"        {g:12} {len(use):>4} {prms:9.4f} {pmax:9.4f} {pr['rms_mm']:9.4f} "
            f"{pr['resid_mm'].max():9.4f} {pr['free_scale']:10.6f} {pr['rms_free_mm']:9.4f}  "
            f"event {use[w]['event']} at {pr['resid_mm'][w]:.3f} mm")
        for k, p in enumerate(use):
            ie = np.array(inc[p["pk"]], float)
            A["points"].append({
                "cloud": g, "event": int(p["event"]), "pk": int(p["pk"]), "mm": list(p["mm"]),
                "n_incident": int(ie.size),
                "incident_mae": float(np.abs(ie).mean()) if ie.size else float("nan"),
                "incident_bias": float(ie.mean()) if ie.size else float("nan"),
                "incident_max_abs": float(np.abs(ie).max()) if ie.size else float("nan"),
                "procrustes_resid_mm": float(pr["resid_mm"][k]),
                "out_of_plane_mm": float(dsign[k]),
                "rep_px": PDG[p["pk"]]["rep_px"], "radius": PDG[p["pk"]]["radius"],
                "edge": PDG[p["pk"]]["edge"], "camdist": PDG[p["pk"]]["camdist"],
                "stereo_deg": PDG[p["pk"]]["stereo_deg"],
                "clicks": PDG[p["pk"]]["clicks"], "X": [float(v) for v in X[p["pk"]]]})

    # leave-one-point-out: how much each point moves its own cloud's MAE
    say(f"\n        LEAVE-ONE-POINT-OUT: change in that cloud's pair MAE when the point's "
        f"{'n-1'} incident pairs are removed")
    say(f"        A strongly negative dMAE means the cloud is materially better without that point.")
    bycloud = defaultdict(list)
    for r in pairs:
        a, b = r["pks"]
        if a in X and b in X:
            bycloud[r["group"]].append((a, b, abs(float(np.linalg.norm(X[a] - X[b])) - r["true"])))
    lopo = {}
    for g, lst in sorted(bycloud.items()):
        base = float(np.mean([e for _, _, e in lst]))
        d = {}
        for p in {a for a, _, _ in lst} | {b for _, b, _ in lst}:
            rest = [e for a, b, e in lst if a != p and b != p]
            d[p] = (float(np.mean(rest)) - base) if rest else float("nan")
        lopo[g] = {"base_mae": base, "dmae": {int(k): v for k, v in d.items()}}
        worst = sorted(d.items(), key=lambda z: z[1])[:3]
        say(f"          {g:12} base MAE {base:8.4f} mm; most improving removals: " + ", ".join(
            f"pk {p} {v:+.4f}" for p, v in worst))
    A["lopo"] = lopo
    for rec in A["points"]:
        rec["lopo_dmae"] = lopo.get(rec["cloud"], {}).get("dmae", {}).get(rec["pk"])

    # duplicate clicks within a camera
    dup = []
    for g, pts in sorted(clouds.items()):
        for c in clips:
            seen = {}
            for p in pts:
                xy = clicks.get(p["pk"], {}).get(c)
                if xy is None:
                    continue
                k = (round(xy[0], 3), round(xy[1], 3))
                if k in seen:
                    dup.append({"cloud": g, "camera": c, "xy": list(k),
                                "events": [seen[k], int(p["event"])]})
                seen[k] = int(p["event"])
    A["duplicate_clicks"] = dup
    say(f"\n        duplicate screen clicks within a cloud and camera: {len(dup)}"
        + ("" if not dup else f"  {dup[:4]}"))

    # suspects, and a left/right swap test on them
    ranked = sorted(A["points"], key=lambda r: -r["procrustes_resid_mm"])
    say(f"\n        WORST POINTS by scale-locked Procrustes residual (the sharpest single-point "
        f"detector here)")
    say(f"        {'cloud':12} {'event':>7} {'pk':>7} {'proc mm':>9} {'outPlane':>9} "
        f"{'incMAE':>9} {'incBias':>9} {'lopo dMAE':>10} {'rep px':>8} {'note mm':>16}")
    for rec in ranked[:12]:
        say(f"        {rec['cloud']:12} {rec['event']:>7} {rec['pk']:>7} "
            f"{rec['procrustes_resid_mm']:9.3f} {rec['out_of_plane_mm']:+9.3f} "
            f"{rec['incident_mae']:9.3f} {rec['incident_bias']:+9.3f} "
            f"{(rec['lopo_dmae'] if rec['lopo_dmae'] is not None else float('nan')):+10.4f} "
            f"{rec['rep_px']:8.3f} {str([round(v, 1) for v in rec['mm']]):>16}")
    A["ranked_worst"] = ranked[:12]

    # a left/right swap on the worst points: does exchanging the two cameras' clicks help?
    if len(clips) == 2:
        say(f"\n        LEFT/RIGHT SWAP TEST on the ten worst points. A swap that LOWERS the residual "
            f"materially")
        say(f"        would indicate the two cameras' clicks were entered the wrong way round.")
        cams = pts3d[name].get("cams")
        swaps = []
        for rec in ranked[:10]:
            g = rec["cloud"]
            use = [p for p in clouds[g] if p["pk"] in X]
            P = np.array([X[p["pk"]] for p in use], float)
            N = np.array([p["mm"] for p in use], float)
            k = [p["pk"] for p in use].index(rec["pk"])
            base = _procrustes_locked(N, P)["resid_mm"][k]
            Xs = pts3d[name]["swapped"].get(rec["pk"]) if "swapped" in pts3d[name] else None
            if Xs is None:
                continue
            P2 = P.copy(); P2[k] = Xs
            sw = _procrustes_locked(N, P2)["resid_mm"][k]
            swaps.append({"cloud": g, "event": rec["event"], "pk": rec["pk"],
                          "resid_mm": float(base), "resid_swapped_mm": float(sw),
                          "improves": bool(sw < 0.5 * base)})
            say(f"          {g:12} event {rec['event']:>7}  as digitized {base:8.3f} mm   "
                f"swapped {sw:8.3f} mm   {'*** SWAP IS BETTER ***' if sw < 0.5 * base else 'no'}")
        A["swap_test"] = swaps
    R.setdefault("audit", {})[tag] = A
    return A


# =============================================================== main


def discover(drift_dir=None, chena_dir=None):
    """Every corpus document that actually contains Length Point Cloud objects."""
    found = []
    for d in corpus.documents(drift_dir, chena_dir):
        if not d["present"]:
            continue
        types = kl.POOL_CONVENTIONAL_TYPES if d["key"] == "pool" else None
        unit = 1000.0 if d["key"] == "pool" else 1.0
        D = kl.load(d["vsd"], conventional_types=types, unit_mm=unit)
        if D["cloud_objects"]:
            found.append({**d, "types": types, "unit_mm": unit, "loaded": D})
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--docs", nargs="*", default=None,
                    help="corpus keys to evaluate; default is every cloud-bearing document found")
    ap.add_argument("--audit-candidate", default="PD-D/M0",
                    help="which reconstruction the digitization audit is reported under")
    ap.add_argument("--no-swap-test", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    t00 = time.time()
    found = discover()
    allkeys = [d["key"] for d in found]
    docs = [d for d in found if args.docs is None or d["key"] in args.docs]

    W = artifacts.ArtifactWriter(
        analysis="cloud_downstream", script=__file__, outdir=args.outdir,
        requested_documents=[d["key"] for d in docs], all_documents=allkeys,
        requested_candidates=CANDIDATES,
        objective_versions={
            "B": f"objectives.fit(B), max_nfev={B_MAX_NFEV}; M1 warm-started from B/M0 with eta=0",
            "PD-D": "objectives.PDExact; M1 warm-started from the converged PD-D/M0 map with eta=0",
            "SD-D": "NOT EVALUATED here: the production-equivalent driver is sd_fast/sd_real.Fitter "
                    "with provenance-verified map reuse, and refitting through objectives.resid_SD "
                    "would be ruled non-convergent by construction",
            "M1_gate": "improves its own objective's M0 loss AND passes finite/radial-scale/"
                       "Jacobian-determinant/conditioning/Newton-inverse map gates, else M0 stands",
            "distortion_map": "lattice.U (14-parameter, eta-aware)",
            "ground_truth": "knownlength.load cloud_pairs, grouped by obj_pk (2026-07-30 fix)",
            "dependence_unit": "the cloud object; cloud-balanced aggregation, no pair bootstrap"},
        source_files=["cloud_downstream.py", "knownlength.py", "downstream.py", "objectives.py",
                      "lattice.py", "fitvalidity.py", "artifacts.py", "corpus.py"],
        extra_modules=(),
        calibration_node_source="ZVSSCREENPOINT via downstream.load_bound_cals")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    R = {"documents": {}}
    say("=" * 112)
    say("POINT-CLOUD DOWNSTREAM KNOWN-LENGTH EVALUATION")
    say("=" * 112)
    say(f"  scope {W.document_scope}  ->  {W.basename('json')}")
    say(f"  cloud-bearing documents discovered in the corpus: {allkeys}")
    say(f"  evaluating: {[d['key'] for d in docs]}")
    say("  Fits are chosen by their own calibration objectives and map gates ONLY. Known-length is the")
    say("  outcome, never the selector. Comparisons are WITHIN estimator (B/M1 vs B/M0, PD-D/M1 vs")
    say("  PD-D/M0); 'stored' is a descriptive operational benchmark and NOT a model-class comparison,")
    say("  because the stored parameters were fitted to superseded plumbline observations.")

    for spec in docs:
        vsd = spec["vsd"]
        say(f"\n{'=' * 112}\n  {spec['label']}\n  {os.path.basename(vsd)}\n{'=' * 112}")
        cals = DS.load_bound_cals(vsd)
        clips = sorted(cals)
        doc_sha = cals[clips[0]]["identity"].doc_sha256
        D0 = spec["loaded"]
        st = os.stat(vsd)
        docR = R["documents"][spec["key"]] = {
            "label": spec["label"], "vsd": vsd, "doc_key": DS.document_key(vsd),
            "doc_sha256": doc_sha, "size_bytes": st.st_size, "mtime_epoch": st.st_mtime,
            "focal_mm_metadata": spec["focal_mm"],
            "cameras": {c: cals[c]["identity"].to_dict() for c in clips}}
        W.document_started(spec["key"], sha256=doc_sha, doc_key=DS.document_key(vsd),
                           node_source="vsd (ZVSSCREENPOINT)", label=spec["label"])
        say(f"    document SHA-256 {doc_sha}")
        say(f"    size {st.st_size} bytes")
        for c in clips:
            say(f"      {c:14} cal_pk={cals[c]['identity'].cal_pk} "
                f"clip_pk={cals[c]['identity'].clip_pk}")

        # ---- ground truth inventory, proven complete
        say(f"\n    CLOUD GROUND-TRUTH INVENTORY (grouped by obj_pk; name is display metadata)")
        say(f"      {'obj_pk':>7} {'name':14} {'points':>7} {'pairs':>7} {'n(n-1)/2':>9} "
            f"{'timecode':>22} {'true mm range':>20}")
        inv = []
        for rec in sorted(D0["cloud_objects"], key=lambda r: r["key"]):
            tl = [q["true"] for q in D0["cloud_pairs"] if q["cloud"] == rec["key"]]
            n = rec["n_points"]
            say(f"      {rec['obj_pk']:>7} {rec['name'][:14]:14} {n:>7} {rec['n_pairs']:>7} "
                f"{n * (n - 1) // 2:>9} {(rec['timecodes'][0] if rec['timecodes'] else '-'):>22} "
                f"{f'{min(tl):.1f} - {max(tl):.1f}' if tl else '-':>20}")
            inv.append({**rec, "expected_pairs": n * (n - 1) // 2})
        tot = sum(r["expected_pairs"] for r in inv)
        say(f"      total {len(D0['cloud_points'])} eligible points, {len(D0['cloud_pairs'])} pairs; "
            f"sum n(n-1)/2 = {tot}  {'MATCH' if tot == len(D0['cloud_pairs']) else 'MISMATCH'}")
        say(f"      loader exclusions {len(D0['exclusions'])}; conventional measurements "
            f"{len(D0['conventional'])}")
        docR["cloud_inventory"] = inv
        docR["n_cloud_points"] = len(D0["cloud_points"])
        docR["n_cloud_pairs"] = len(D0["cloud_pairs"])
        docR["n_conventional"] = len(D0["conventional"])
        docR["exclusions"] = [list(map(str, e)) for e in D0["exclusions"]]

        # ---- pair records in the shape measure() wants
        ev2note = {p["event"]: p["mm"] for p in D0["cloud_points"]}
        pairs = []
        for q in D0["cloud_pairs"]:
            d = np.array(ev2note[q["j"]], float) - np.array(ev2note[q["i"]], float)
            pairs.append({**q, "key": ("cloud", q["cloud_pk"], q["i"], q["j"]),
                          "group": q["cloud"],
                          "orient_deg": float(math.degrees(math.atan2(abs(d[1]), abs(d[0])))
                                              if len(d) >= 2 else float("nan"))})
        conv = [{**r, "key": ("conv", r["event"]), "group": str(r["obj"]),
                 "i": r["event"], "j": r["event"]} for r in D0["conventional"]]

        # ---- lattice state and gated fits per camera
        say(f"\n    LATTICE STATE AND GATED FITS")
        maps_by_clip, fitdiag, validities = {}, {}, {}
        for clip in clips:
            caps = LT.load_captures(vsd, clip)
            Dd = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
            contra = sum(C.notes["index_contradictions"] for C in caps)
            say(f"      {clip}: {len(caps)} capture(s), {Dd.n} indexed observations on {Dd.nline} "
                f"lines, index contradictions {contra}")
            if contra or Dd.n < 20:
                say(f"        *** PD-D not admissible here; this document would need the SD-D "
                    f"fallback and is NOT evaluated by forcing a lattice ***")
                W.document_failed(spec["key"], f"{clip}: lattice did not validate")
                maps_by_clip = None
                break
            node_pts = np.array([[x, y] for x, y, _, _ in cals[clip]["front"] + cals[clip]["back"]],
                                float)
            th, dg, vv = fit_gated(say, Dd, node_pts, clip)
            maps_by_clip[clip] = th
            fitdiag[clip] = dg
            validities[clip] = vv
        if maps_by_clip is None:
            continue
        docR["fits"] = {c: {k: {kk: vv for kk, vv in d.items()} for k, d in fitdiag[c].items()}
                        for c in clips}
        docR["fit_validity"] = {c: {k: v.to_dict() for k, v in validities[c].items()}
                                for c in clips}
        for c in clips:
            for k, v in validities[c].items():
                W.candidate_validity(spec["key"], c, k, v.to_dict())
        docR["eta"] = {c: {k: float(fitdiag[c][k]["eta"]) for k in fitdiag[c]} for c in clips}

        rejected = sorted({k for c in clips for k, d in fitdiag[c].items() if not d["gate"]["ok"]})
        if rejected:
            say(f"\n    GATE-REJECTED on at least one camera, so M0 stands for them: {rejected}")
        docR["gate_rejected"] = rejected

        # ---- candidate maps, each bound to its camera
        maps = {"stored": {c: DS.DistortionMap.from13_for_camera(
            cals[c]["dist"], cals[c], name=f"stored/{c}",
            source="ZVSCALIBRATION stored columns") for c in clips}}
        for k in [f"{o}/{m}" for o in OBJECTIVES for m in ("M0", "M1")]:
            if all(k in maps_by_clip[c] for c in clips):
                maps[k] = {c: DS.DistortionMap.for_camera(
                    maps_by_clip[c][k], cals[c], name=f"{k}/{c}", source="fitted this run")
                    for c in clips}

        # ---- downstream
        say(f"\n    DOWNSTREAM REBUILD AND MEASUREMENT ({len(pairs)} cloud pairs"
            + (f", {len(conv)} conventional" if conv else "") + ")")
        rows, cdiag, pts3d = measure(say, cals, maps, pairs, D0["clicks"], spec["unit_mm"],
                                     validities)
        reportable = [k for k in CANDIDATES if k in rows and rows[k]]
        say(f"      reportable candidates: {reportable}")
        say(f"      calibration node residuals (front RMS px, estimator-neutral): " + ", ".join(
            f"{k} " + "/".join(f"{cdiag[k][c]['front_rms']:.3f}" for c in clips)
            for k in reportable))
        docR["calibration_diagnostics"] = {
            k: {c: {kk: (vv if not isinstance(vv, np.ndarray) else vv.tolist())
                    for kk, vv in cdiag[k][c].items() if kk != "cam"}
                for c in clips if c in cdiag[k]} for k in cdiag}

        tag = spec["key"]
        report_groups(say, rows, R, tag, f"{spec['label']} | cloud pairs", reportable)
        contrasts = [("B/M1", "B/M0"), ("PD-D/M1", "PD-D/M0"), ("PD-D/M0", "B/M0"),
                     ("PD-D/M1", "B/M1")]
        contrasts = [(a, b) for a, b in contrasts if a in rows and b in rows]
        report_paired(say, rows, R, tag, contrasts)
        report_behaviour(say, rows, R, tag, reportable)

        # ---- conventional, when the document has any, on the SAME rebuilt geometry
        if conv:
            say(f"\n    SAME-DOCUMENT CONVENTIONAL MEASUREMENTS ({len(conv)}), same rebuilt "
                f"geometry, for reconciliation with the established analysis")
            crows, _, _ = measure(say, cals, maps, conv, D0["clicks"], spec["unit_mm"], validities)
            creport = [k for k in CANDIDATES if k in crows and crows[k]]
            say(f"      {'candidate':10} {'n':>5} {'MAE':>9} {'RMSE':>9} {'median':>9} "
                f"{'bias':>9} {'p90':>9} {'max':>9}")
            cs = {}
            for k in creport:
                s = cs[k] = stats([r["err"] for r in crows[k]])
                say(f"      {k:10} {s['n']:5d} {s['mae']:9.4f} {s['rmse']:9.4f} {s['med']:9.4f} "
                    f"{s['bias']:+9.4f} {s['p90']:9.4f} {s['max']:9.4f}")
            R.setdefault("conventional", {})[tag] = cs
            report_paired(say, crows, R, f"{tag}/conventional", contrasts, group_label="object")

        # ---- audit
        cand = args.audit_candidate if args.audit_candidate in pts3d else reportable[-1]
        if not args.no_swap_test and len(clips) == 2:
            cams = {c: DS.build_calibration(cals[c], maps[cand][c]) for c in clips}
            sw = {}
            for p in D0["cloud_points"]:
                cl = D0["clicks"].get(p["pk"], {})
                if not all(c in cl for c in clips):
                    continue
                obs = [(cams[clips[0]], cl[clips[1]]), (cams[clips[1]], cl[clips[0]])]
                try:
                    sw[p["pk"]] = DS.triangulate_lm(obs)["X"]
                except Exception:                                            # noqa: BLE001
                    pass
            pts3d[cand]["swapped"] = sw
        audit(say, R, tag, spec, D0["clouds"], pairs, pts3d, cals, D0["clicks"], cand)

        # ---- CSVs
        base = os.path.join(args.outdir, f"cloud_downstream_{spec['key'].replace('/', '_')}")
        with open(base + "_pairs.csv", "w") as f:
            f.write("candidate,cloud,tc,event_i,event_j,true_mm,meas_mm,err_mm,pct,orient_deg,"
                    "radius_px,edge_px,camdist_mm,rep_px\n")
            for k in reportable:
                for r in rows[k]:
                    f.write(f"{k},{r['group']},{r['tc']},{r['i']},{r['j']},{r['true']:.6f},"
                            f"{r['meas']:.6f},{r['err']:.6f},{r['pct']:.6f},"
                            f"{r['orient_deg']:.4f},{r['radius']:.3f},{r['edge']:.3f},"
                            f"{r['camdist']:.3f},{r['rep_px']:.5f}\n")
        pa = R.get("audit", {}).get(tag, {})
        if pa.get("points"):
            keys = ["cloud", "event", "pk", "n_incident", "incident_mae", "incident_bias",
                    "incident_max_abs", "procrustes_resid_mm", "out_of_plane_mm", "lopo_dmae",
                    "rep_px", "radius", "edge", "camdist", "stereo_deg"]
            with open(base + "_points.csv", "w") as f:
                f.write(",".join(keys) + ",note_mm\n")
                for r in pa["points"]:
                    f.write(",".join("" if r.get(k) is None else
                                     (f"{r[k]:.6f}" if isinstance(r[k], float) else str(r[k]))
                                     for k in keys)
                            + f",\"{r['mm']}\"\n")
        say(f"\n    wrote {os.path.basename(base)}_pairs.csv"
            + (f" and _points.csv" if pa.get("points") else ""))
        W.document_completed(spec["key"], completed_candidates=sorted(rows))
        say(f"    [{time.time() - t00:.1f}s elapsed]")

    path = W.write(R)
    man = W.manifest()
    say(f"\n  scope {man['document_scope']}: requested {man['requested_documents']}, completed "
        f"{man['completed_documents']}, complete={man['complete']}")
    say(f"  wrote {path}   [{time.time() - t00:.1f}s total]")
    if not man["complete"]:
        say("  *** THIS ARTIFACT IS NOT COMPLETE and is named accordingly ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
