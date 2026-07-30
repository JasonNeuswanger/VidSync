#!/usr/bin/env python3
"""Explicit, independently recorded fit status, and the one ranking rule that consumes it.

WHY THIS EXISTS, 2026-07-29 (revision 2). `fitvalidity.FitValidity` carries a single boolean `valid`
that conflates several independent facts, and its `admissible` field is filled from
`lattice.admissible` -- the PRODUCTION gate -- while the frozen empirical gate used everywhere else in
this harness is `mapmetrics.admissibility_v2`. The two disagree, and pool/Right PD-D/M1 is the case that
exposed it: the serialized record says `valid: true, admissible: true` (production gate: min det over the
full frame 0.9298 > 0), whereas the frozen gate says `safe: false, physically_plausible: false`. It was
therefore counted among "all valid candidates" and was eligible to win a ranking, which is wrong.

THE SCHEMA. Five states, recorded separately, never collapsed:

  optimizer_converged      the optimizer reported a convergence criterion (status > 0) AND did not
                           reach its evaluation cap. A cap is not convergence.
  numerically_invertible   the shipped inverse converged everywhere sampled, with zero failures and a
                           maximum round-trip below INVERSE_ROUNDTRIP_TOL_PX.
  empirically_admissible   the FROZEN gate `mapmetrics.admissibility_v2` reports safe AND physically
                           plausible. Recorded next to, and never merged with, `production_gate_ok`
                           (`lattice.admissible`), which is a different and weaker test.
  eligible_for_ranking     the conjunction of the three above plus finite parameters, evaluated for a
                           SINGLE camera. Document-level eligibility additionally requires every camera
                           of the document to be eligible, because a stereo measurement uses both.
  diagnostic_only          not eligible. Always accompanied by `diagnostic_reasons`, and such a record
                           stays in labelled diagnostic tables rather than disappearing.

Passing the frozen gate is an EMPIRICAL result on a finite grid at a finite cell bound; it is not proof
of global injectivity or physical correctness. Nothing here re-fits, re-optimizes or recomputes a map.

Run with ~/.venvs/vidsync/bin/python. Imported by sd_report_regen.py and test_fitstatus.py.
"""

import numpy as np

INVERSE_ROUNDTRIP_TOL_PX = 1e-9

STATES = ("optimizer_converged", "numerically_invertible", "empirically_admissible",
          "eligible_for_ranking", "diagnostic_only")

# The exact ranking rule, in one place so the report cannot state a different one.
RANKING_RULE = (
    "A candidate is eligible for an ACCEPTED ranking on a document if and only if, for EVERY camera of "
    "that document: (1) the optimizer reported a convergence criterion (status > 0) and did not reach "
    "its evaluation cap; (2) the map is numerically invertible -- zero shipped-inverse failures and "
    "maximum round-trip < 1e-9 px; (3) the map passes the FROZEN empirical gate "
    "mapmetrics.admissibility_v2 (safe AND physically_plausible), which is a stricter test than the "
    "production gate lattice.admissible; and (4) its parameters are finite. Any candidate failing any "
    "condition on any camera is DIAGNOSTIC-ONLY: it is retained in labelled diagnostic tables, is "
    "excluded from every accepted ranking and from accepted-map synthesis, and is never counted among "
    "'all valid candidates'. The stored calibration anchor is not an optimizer output and is ranked "
    "separately as a reference, never as an accepted fitted candidate.")


def camera_status(candidate, camera, *, optimizer=None, adm_v2=None, inverse=None,
                  production_gate_ok=None, theta14=None, not_fitted_reason=None):
    """One explicit status record for one candidate on one camera. Pure; no map is evaluated.

    `optimizer` is an objectives/sd_fast-shaped dict (status, nfev, max_nfev / hit_nfev_cap,
    termination, loss, optimality). `adm_v2` is a `mapmetrics.admissibility_v2` result or the subset
    stored in an artifact. `inverse` is {"shipped_failures", "max_roundtrip_px"}.
    """
    reasons = []
    if not_fitted_reason:
        return {"candidate": candidate, "camera": camera, "fitted": False,
                "optimizer_converged": False, "numerically_invertible": False,
                "empirically_admissible": False, "eligible_for_ranking": False,
                "diagnostic_only": True, "diagnostic_reasons": [f"not fitted: {not_fitted_reason}"],
                "production_gate_ok": None, "evidence": {}}

    o = optimizer or {}
    status = o.get("status")
    nfev, cap = o.get("nfev"), o.get("max_nfev")
    hit_cap = o.get("hit_nfev_cap")
    if hit_cap is None and cap is not None and nfev is not None:
        hit_cap = int(nfev) >= int(cap)
    conv = bool(status is not None and int(status) > 0 and not hit_cap)
    if status is None:
        reasons.append("no optimizer status recorded")
    elif int(status) <= 0:
        reasons.append(f"optimizer status {status} is not a convergence criterion")
    if hit_cap:
        reasons.append(f"reached the evaluation cap ({nfev} of {cap}); a cap is not convergence")

    inv = inverse or {}
    rt = inv.get("max_roundtrip_px")
    fails = inv.get("shipped_failures")
    invertible = bool(fails == 0 and rt is not None and float(rt) < INVERSE_ROUNDTRIP_TOL_PX)
    if fails is None or rt is None:
        invertible = False
        reasons.append("no inverse audit recorded")
    else:
        if fails:
            reasons.append(f"{fails} shipped-inverse failure(s)")
        if float(rt) >= INVERSE_ROUNDTRIP_TOL_PX:
            reasons.append(f"inverse round-trip {float(rt):.3e} px >= {INVERSE_ROUNDTRIP_TOL_PX:g}")

    a = adm_v2 or {}
    safe, plaus = a.get("safe"), a.get("physically_plausible")
    admissible = bool(safe) and bool(plaus)
    if safe is None:
        admissible = False
        reasons.append("no frozen-gate (admissibility_v2) result recorded")
    else:
        if not safe:
            reasons.append("frozen empirical gate: admissibility_v2 safe=False")
        if plaus is False:
            reasons.append("frozen empirical gate: physically_plausible=False")

    th = None if theta14 is None else np.asarray(theta14, float).ravel()
    finite = True if th is None else bool(th.size == 14 and np.all(np.isfinite(th)))
    if not finite:
        reasons.append("non-finite or misshaped parameter vector")

    elig = bool(conv and invertible and admissible and finite)
    return {"candidate": candidate, "camera": camera, "fitted": True,
            "optimizer_converged": conv, "numerically_invertible": invertible,
            "empirically_admissible": admissible, "eligible_for_ranking": elig,
            "diagnostic_only": not elig, "diagnostic_reasons": reasons,
            "production_gate_ok": None if production_gate_ok is None else bool(production_gate_ok),
            "evidence": {"optimizer_status": status, "nfev": nfev, "max_nfev": cap,
                         "hit_nfev_cap": bool(hit_cap) if hit_cap is not None else None,
                         "termination": o.get("termination"), "loss": o.get("loss"),
                         "optimality": o.get("optimality"),
                         "adm_v2": {k: a.get(k) for k in ("safe", "physically_plausible", "min_det",
                                                          "min_sigma", "expansion_ratio",
                                                          "roundtrip_px") if k in a},
                         "inverse": {"shipped_failures": fails, "max_roundtrip_px": rt}}}


def document_status(candidate, per_camera):
    """Document-level eligibility: every camera must be eligible, because stereo uses both."""
    cams = list(per_camera)
    elig = bool(cams) and all(per_camera[c]["eligible_for_ranking"] for c in cams)
    reasons = {c: per_camera[c]["diagnostic_reasons"] for c in cams
               if per_camera[c]["diagnostic_only"]}
    return {"candidate": candidate, "cameras": cams,
            "eligible_for_ranking": elig, "diagnostic_only": not elig,
            "diagnostic_reasons_by_camera": reasons,
            "n_cameras_eligible": sum(1 for c in cams if per_camera[c]["eligible_for_ranking"]),
            "n_cameras": len(cams)}


def rank(metric_by_candidate, doc_status, lower_is_better=True, anchor="stored"):
    """The accepted ranking plus the labelled diagnostic rows. Never mixes the two.

    `metric_by_candidate` maps candidate -> scalar (e.g. known-length MAE). `doc_status` maps candidate
    -> `document_status` result. The anchor (the stored calibration) is reported separately: it is not an
    optimizer output, so it can be neither converged nor capped, and ranking it against fitted candidates
    as if it were one would be a category error.
    """
    accepted, diagnostic = [], []
    for cand, val in metric_by_candidate.items():
        if val is None or not np.isfinite(float(val)):
            continue
        if cand == anchor:
            continue
        st = doc_status.get(cand)
        row = {"candidate": cand, "metric": float(val)}
        if st is None:
            row["excluded_reason"] = ["no status record"]
            diagnostic.append(row)
        elif st["eligible_for_ranking"]:
            accepted.append(row)
        else:
            row["excluded_reason"] = st["diagnostic_reasons_by_camera"]
            diagnostic.append(row)
    accepted.sort(key=lambda r: r["metric"], reverse=not lower_is_better)
    diagnostic.sort(key=lambda r: r["metric"], reverse=not lower_is_better)
    anchor_val = metric_by_candidate.get(anchor)
    return {"accepted_ranking": accepted,
            "best_accepted": accepted[0] if accepted else None,
            "diagnostic_only_rows": diagnostic,
            "reference_anchor": ({"candidate": anchor, "metric": float(anchor_val)}
                                 if anchor_val is not None else None),
            "n_accepted": len(accepted), "n_diagnostic_only": len(diagnostic),
            "rule": RANKING_RULE}
