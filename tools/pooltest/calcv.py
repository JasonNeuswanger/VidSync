#!/usr/bin/env python3
"""Grouped calibration-only cross-validation, identifiability, and null/injection experiments.

ANALYSIS ONLY. No production behaviour, default, or .vsd is touched.

WHY CALIBRATION-ONLY. Production selects ONE 13-parameter distortion map per VSCalibration, and there is
one VSCalibration per video clip (see VSCalibration.h: distortionCenterX/Y, K1..K7, P1..P4, and no eta
field at all). So the operational decision is DOCUMENT-WIDE PER CAMERA and must be made at calibration
time, before any measurement click exists. Any evidence that requires known-length targets is therefore
ineligible as a predictor, however informative it is as an outcome. This module builds the only kind of
out-of-sample evidence available at that moment: held-out plumbline straightness.

GROUPED FOLDS, NOT RANDOM POINTS. A fold is an ENTIRE stored line object. Withholding random points from
a line would leave the rest of that same line in the training set, and since straightness is a property
of the line as a whole, the held-out points would be predicted largely by their own line's retained
neighbours. That is leakage of exactly the kind the grouping is meant to prevent. Folds are therefore
line-complete, and the fold definition is candidate-independent: it comes from the stored line records,
never from any fitted map.

SCORING. For a held-out line, each candidate map undistorts its observations, then ONLY the line's two
nuisance straight-line parameters are fitted (total least squares: direction and offset). The score is
the continuous RMS orthogonal deviation from that best-fit straight line. Nothing about the held-out line
enters the distortion fit, and the nuisance fit has no freedom to absorb curvature.

IN-SAMPLE OBJECTIVE IMPROVEMENT IS NOT EVIDENCE OF GENERALIZATION. M1 nests M0, so it improves or
preserves its training objective by construction. Only the held-out score below speaks to generalization.

Run with ~/.venvs/vidsync/bin/python.
"""

import copy
import math

import numpy as np

import harness_import

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")

FRAME_DIAG = math.hypot(LT.FRAME_W, LT.FRAME_H)


def per_mille_diag(px):
    """Normalized image units: parts per thousand of the frame diagonal, for cross-camera comparability."""
    return 1000.0 * px / FRAME_DIAG


# ============================================================== fold construction


def line_folds(caps, min_pts=5):
    """Candidate-independent folds: one per stored line object with at least `min_pts` observations."""
    out = []
    for ci, C in enumerate(caps):
        for li, ln in enumerate(C.lines):
            if len(ln["members"]) >= min_pts:
                out.append({"capture": ci, "line": li, "n_obs": len(ln["members"]),
                            "family": int(ln.get("family", -1)),
                            "timecode": C.timecode})
    return out


def caps_without(caps, ci_drop, li_drop):
    """Copy of `caps` with one stored line removed and incidences renumbered. No map is consulted."""
    new = []
    for ci, C in enumerate(caps):
        D = copy.copy(C)
        if ci != ci_drop:
            new.append(D)
            continue
        D.lines = [ln for li, ln in enumerate(C.lines) if li != li_drop]
        remap = {}
        k = 0
        for li in range(len(C.lines)):
            if li == li_drop:
                continue
            remap[li] = k
            k += 1
        D.inc = [[remap[li] for li in inc if li in remap] for inc in C.inc]
        new.append(D)
    return new


def straightness_rms(xy, theta14):
    """RMS orthogonal deviation of undistorted observations from their own best-fit straight line.

    Only the line's two nuisance parameters are fitted (TLS direction plus offset through the centroid),
    so the fit cannot absorb curvature: with k >= 3 points any bow shows up in the residual.
    """
    u = LT.U(np.asarray(xy, float), np.asarray(theta14, float))
    if not np.all(np.isfinite(u)) or len(u) < 3:
        return float("nan"), float("nan"), None
    c = u.mean(0)
    A = u - c
    _, _, Vt = np.linalg.svd(A, full_matrices=False)
    n = Vt[-1]                                   # unit normal of the TLS line
    d = A @ n
    return (float(math.sqrt((d ** 2).mean())), float(np.abs(d).max()), d)


# ============================================================== the grouped CV


def grouped_cv(say, caps, node_pts, gate_fn, fit_fn, min_pts=5, max_folds=None, estimators=("B",)):
    """One held-out-line CV pass for one camera. Returns per-fold records and summaries.

    `fit_fn(caps_train, model, warm_theta)` must return (theta14, diag) and is expected to be the same
    gated M0-first path production would use. `gate_fn(theta14, node_pts)` is the physical-map gate.
    """
    folds = line_folds(caps, min_pts=min_pts)
    if max_folds:
        folds = folds[:max_folds]
    rows, nfail_gate, nfail_conv = [], 0, 0
    for f in folds:
        tr = caps_without(caps, f["capture"], f["line"])
        held = caps[f["capture"]]
        mem = [m for m in caps[f["capture"]].lines[f["line"]]["members"]]
        xy = held.xy[mem]
        rec = {**f, "candidates": {}}
        for est in estimators:
            try:
                Dtr = OB.Dataset(tr, require_indexed=(est == "PD-D"), min_inc=2, kappa=3.0)
                if Dtr.n < 20 or Dtr.nline < 3:
                    rec["candidates"][est] = {"error": "training set too small after fold removal"}
                    continue
                th0, d0 = fit_fn(Dtr, est, "M0", None)
                th1, d1 = fit_fn(Dtr, est, "M1", th0)
            except Exception as e:                                           # noqa: BLE001
                rec["candidates"][est] = {"error": f"{type(e).__name__}: {e}"}
                nfail_conv += 1
                continue
            g0, g1 = gate_fn(th0, node_pts), gate_fn(th1, node_pts)
            improves = bool(d1["loss"] <= d0["loss"] + 1e-9 * max(abs(d0["loss"]), 1.0))
            ok1 = bool(g1["ok"] and improves)
            if not ok1:
                nfail_gate += 1
            r0, m0, _ = straightness_rms(xy, th0)
            r1, m1, _ = straightness_rms(xy, th1)
            rec["candidates"][est] = {
                "M0": {"rms_px": r0, "max_px": m0, "loss": d0["loss"], "status": d0["status"],
                       "gate_ok": bool(g0["ok"])},
                "M1": {"rms_px": r1, "max_px": m1, "loss": d1["loss"], "status": d1["status"],
                       "gate_ok": bool(g1["ok"]), "eta": float(th1[13]),
                       "improves_own_M0_objective": improves, "operationally_accepted": ok1},
                "d_rms_px": (r1 - r0) if np.isfinite(r0) and np.isfinite(r1) else float("nan"),
                "d_rms_permille": (per_mille_diag(r1 - r0)
                                   if np.isfinite(r0) and np.isfinite(r1) else float("nan")),
                # The transactional reading: if M1 is not operationally accepted, M0 stands, so the
                # realized held-out change is zero, not the raw difference.
                "d_rms_px_transactional": ((r1 - r0) if ok1 else 0.0)}
        rows.append(rec)
    return {"folds": rows, "n_folds": len(rows), "gate_or_objective_rejections": nfail_gate,
            "fold_failures": nfail_conv,
            "fold_definition": f"one stored line object per fold, at least {min_pts} observations, "
                               f"defined from the stored records and independent of any fitted map",
            "score": "RMS orthogonal deviation of the undistorted held-out line from its own TLS line; "
                     "only the line's 2 nuisance parameters are fitted"}


def summarize_cv(cv, est):
    """Equal-line macro loss and its distribution. Lines are the unit; observations are not."""
    d = [f["candidates"][est]["d_rms_px"] for f in cv["folds"]
         if est in f["candidates"] and "d_rms_px" in f["candidates"][est]
         and np.isfinite(f["candidates"][est]["d_rms_px"])]
    dt = [f["candidates"][est]["d_rms_px_transactional"] for f in cv["folds"]
          if est in f["candidates"] and "d_rms_px_transactional" in f["candidates"][est]]
    m0 = [f["candidates"][est]["M0"]["rms_px"] for f in cv["folds"]
          if est in f["candidates"] and "M0" in f["candidates"][est]
          and np.isfinite(f["candidates"][est]["M0"]["rms_px"])]
    m1 = [f["candidates"][est]["M1"]["rms_px"] for f in cv["folds"]
          if est in f["candidates"] and "M1" in f["candidates"][est]
          and np.isfinite(f["candidates"][est]["M1"]["rms_px"])]
    if not d:
        return {"n_lines": 0}
    d = np.array(d); m0 = np.array(m0); m1 = np.array(m1)
    return {"n_lines": int(d.size),
            "equal_line_mean_M0_rms_px": float(m0.mean()),
            "equal_line_mean_M1_rms_px": float(m1.mean()),
            "equal_line_rms_M0_px": float(math.sqrt((m0 ** 2).mean())),
            "equal_line_rms_M1_px": float(math.sqrt((m1 ** 2).mean())),
            "equal_line_p95_M0_px": float(np.percentile(m0, 95)),
            "equal_line_p95_M1_px": float(np.percentile(m1, 95)),
            "signed_mean_d_rms_px": float(d.mean()),
            "signed_mean_d_rms_permille": float(per_mille_diag(d.mean())),
            "signed_median_d_rms_px": float(np.median(d)),
            "lines_improved": int((d < 0).sum()),
            "worst_line_deterioration_px": float(d.max()),
            "best_line_improvement_px": float(d.min()),
            "p95_abs_d_rms_px": float(np.percentile(np.abs(d), 95)),
            "transactional_mean_d_rms_px": float(np.mean(dt)) if dt else float("nan"),
            "concentration_top1_share": (float(max(0.0, -d.min()) / max(1e-12, -d[d < 0].sum()))
                                         if (d < 0).any() else float("nan")),
            "note": "the unit is the LINE. Observations within a line are not independent and are not "
                    "counted. `concentration_top1_share` is the single best line's share of the total "
                    "improvement: near 1 means the gain is one line, not a distributed effect."}


# ============================================================== identifiability


def eta_profile(D, model_free, base_theta, etas):
    """Profile the objective over a FIXED eta grid, refitting the other parameters at each eta.

    zero_held=False is essential: holding eta at a nonzero value while zeroing held parameters would
    silently refit the eta = 0 model at every grid point, which is how an earlier attempt produced a
    perfectly flat profile.
    """
    out = []
    for e in etas:
        base = np.asarray(base_theta, float).copy()
        base[13] = float(e)
        try:
            r = OB.fit(D, "B", "M0", base=base, warm=False, max_nfev=800, zero_held=False)
            out.append({"eta": float(e), "loss": float(r["loss"]), "status": int(r["status"])})
        except Exception as e2:                                              # noqa: BLE001
            out.append({"eta": float(e), "loss": float("nan"), "error": str(e2)[:80]})
    return out


def eta_identifiability(D, th1, node_pts):
    """Curvature of the profile in eta, and eta's correlation with the Brown-Conrady coefficients."""
    th1 = np.asarray(th1, float)
    e0 = float(th1[13])
    span = max(2e-3, abs(e0) * 0.6)
    grid = np.linspace(e0 - span, e0 + span, 9)
    prof = eta_profile(D, "M1", th1, grid)
    ls = np.array([p["loss"] for p in prof], float)
    ok = np.isfinite(ls)
    curv = float("nan")
    if ok.sum() >= 3:
        c = np.polyfit(grid[ok], ls[ok], 2)
        curv = float(2 * c[0])
    # Local Jacobian of the B residual in the free parameters, for conditioning and correlation.
    fr = OB.MODELS["M1"]
    pk = OB.Pack("M1", nline=D.nline, ncap=D.ncap,
                 nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="B", free=fr)
    p0 = np.zeros(pk.n)
    p0[:pk.nm] = th1[fr] / OB.SCALE14[fr]
    base = OB.default_base()

    def rr(p):
        return OB.resid_B(p, D, pk, base)
    r0 = rr(p0)
    J = np.zeros((len(r0), pk.nm))
    for j in range(pk.nm):
        h = 1e-6 * max(1.0, abs(p0[j]))
        pp = p0.copy(); pp[j] += h
        J[:, j] = (rr(pp) - r0) / h
    JtJ = J.T @ J
    sv = np.linalg.svd(JtJ, compute_uv=False)
    cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")
    try:
        Cov = np.linalg.pinv(JtJ)
        sd = np.sqrt(np.clip(np.diag(Cov), 1e-300, None))
        Corr = Cov / np.outer(sd, sd)
        ie = list(fr).index(13)
        corr_eta = Corr[ie, :]
        worst = int(np.argmax(np.abs(np.delete(corr_eta, ie))))
        worst_idx = [j for j in range(len(fr)) if j != ie][worst]
        out_corr = {"max_abs_corr_with_other_params": float(np.max(np.abs(np.delete(corr_eta, ie)))),
                    "worst_partner_free_index": int(fr[worst_idx]),
                    "eta_std_err_units_of_scaled_param": float(sd[ie])}
    except Exception:                                                        # noqa: BLE001
        out_corr = {}
    return {"eta_hat": e0, "profile": prof, "profile_curvature": curv,
            "profile_is_convex_at_optimum": bool(np.isfinite(curv) and curv > 0),
            "JtJ_condition": cond, "eta_bound": float(LT.ETA_BOUND),
            "bound_proximity": float(abs(e0) / LT.ETA_BOUND),
            **out_corr,
            "note": "optimizer convergence is NOT parameter identification; the profile curvature and "
                    "the eta-versus-others correlation are what speak to identifiability"}


def multistart_eta(D, th0, n=5, spread=0.02):
    """Predetermined multistart protocol: eta seeded across its plausible range, everything else at M0."""
    fr = OB.MODELS["M1"]
    outs = []
    seeds = np.linspace(-spread, spread, n)
    for s in seeds:
        x0 = np.asarray(th0, float).copy()
        x0[13] = float(s)
        try:
            r = OB.fit(D, "B", "M1", x0_model=x0[fr] / OB.SCALE14[fr], warm=False, max_nfev=3000)
            outs.append({"seed_eta": float(s), "eta": float(r["eta"]), "loss": float(r["loss"]),
                         "status": int(r["status"])})
        except Exception as e:                                               # noqa: BLE001
            outs.append({"seed_eta": float(s), "error": str(e)[:80]})
    good = [o for o in outs if "eta" in o]
    etas = np.array([o["eta"] for o in good]) if good else np.zeros(0)
    losses = np.array([o["loss"] for o in good]) if good else np.zeros(0)
    return {"starts": outs, "n_started": len(outs), "n_converged": len(good),
            "eta_spread": float(etas.max() - etas.min()) if etas.size else float("nan"),
            "loss_spread": float(losses.max() - losses.min()) if losses.size else float("nan"),
            "distinct_basins": (int(np.sum(losses > losses.min() * 1.01 + 1e-9))
                               if losses.size else 0),
            "protocol": f"{n} starts, eta seeded on linspace(-{spread}, {spread}), all other "
                        f"parameters at the converged M0 values; predetermined, not chosen post hoc"}
