#!/usr/bin/env python3
"""Regression tests for fail-closed fit validity, including the real audited capped fits.

The defect: `xdoc_objectives.py` recorded `hit_nfev_cap` and then reported the capped fits anyway. On
the pool test, SD-D/M0 appeared in the published summary at MAE 0.9585 mm -- second best of seven
candidates -- from a fit that stopped at its 1200-evaluation ceiling with SciPy status 0, which means
"maximum number of function evaluations reached" and is not a convergence code.

Section [4] replays the REAL fit statuses recorded in the stale artifact and asserts that every one of
the capped candidates the audit listed is now excluded.

Run with ~/.venvs/vidsync/bin/python.
"""

import json
import os
import sys
import traceback

import harness_import

harness_import.ensure_path()
import fitvalidity as FV                                                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def main():
    print("=" * 100)
    print("FIT VALIDITY (FAIL-CLOSED) REGRESSION TESTS")
    print("=" * 100)

    # ------------------------------------------------------------------ 1. synthetic records
    print(f"\n[1] SYNTHETIC valid and capped fit records")
    converged = FV.from_least_squares(
        "PD-D/M1", {"status": 2, "nfev": 27, "loss": 1.5, "optimality": 1e-9,
                    "nests_under_M0": True}, max_nfev=1200, theta14=[0.0] * 14,
        admissible=True, inverse_ok=True)
    check("a status-2 fit well under the cap is valid", converged.valid, str(converged))
    check("its termination reason names the ftol criterion",
          "ftol" in converged.termination_reason, converged.termination_reason)

    capped = FV.from_least_squares(
        "SD-D/M0", {"status": 0, "nfev": 1200, "loss": 0.44, "hit_nfev_cap": True},
        max_nfev=1200, theta14=[0.0] * 14, admissible=True, inverse_ok=True)
    check("a status-0 fit at the cap is INVALID", not capped.valid, str(capped))
    check("the reason names status 0 explicitly",
          any("status 0" in f for f in capped.failures()), f"{capped.failures()}")
    check("the reason names the evaluation cap",
          any("cap" in f for f in capped.failures()))
    check("status 0 is documented as NOT a convergence criterion",
          "not a convergence criterion" in capped.termination_reason.lower(),
          capped.termination_reason)
    check("an invalid fit KEEPS its parameters and loss for debugging",
          capped.loss == 0.44 and capped.nfev == 1200 and capped.max_nfev == 1200)
    check("a table cell for an invalid fit reads invalid_fit, not a number",
          capped.display(0.9585) == "invalid_fit", capped.display(0.9585))
    check("a table cell for a valid fit reads the number",
          converged.display(0.9585).strip() == "0.9585", converged.display(0.9585))

    # cap inferred from nfev when the flag is absent -- plausible parameters are not evidence
    inferred = FV.from_least_squares("SD-D/M1", {"status": 0, "nfev": 1200, "loss": 0.1},
                                     max_nfev=1200, theta14=[0.0] * 14)
    check("the cap is inferred from nfev >= max_nfev even without the flag", not inferred.valid)
    check("a low loss does NOT rescue a capped fit", not inferred.valid and inferred.loss == 0.1)

    # every other failure mode
    for label, kw, diag in (
            ("non-finite loss", {}, {"status": 2, "nfev": 10, "loss": float("nan")}),
            ("non-finite params", {"theta14": [float("inf")] + [0.0] * 13},
             {"status": 2, "nfev": 10, "loss": 1.0}),
            ("inadmissible map", {"admissible": False}, {"status": 2, "nfev": 10, "loss": 1.0}),
            ("inverse failure", {"inverse_ok": False}, {"status": 2, "nfev": 10, "loss": 1.0}),
            ("nesting violated", {}, {"status": 2, "nfev": 10, "loss": 1.0,
                                      "nests_under_M0": False}),
            ("improper input (status -1)", {}, {"status": -1, "nfev": 10, "loss": 1.0}),
            ("missing status", {}, {"nfev": 10, "loss": 1.0})):
        v = FV.from_least_squares("X", diag, max_nfev=1200, **kw)
        check(f"{label} makes the fit invalid", not v.valid, f"{v.failures()}")

    wall = FV.from_least_squares("SD-D/M1", {"status": 2, "nfev": 400, "loss": 1.0,
                                            "over_wall_limit": True}, max_nfev=1200,
                                theta14=[0.0] * 14)
    check("a wall-clock overrun also counts as a cap", not wall.valid and wall.cap_kind == "wall_clock")

    nf = FV.not_fitted("PD-D/M0", "lattice did not validate")
    check("a deliberately unfitted candidate is invalid and says why",
          not nf.valid and "not fitted" in nf.termination_reason, nf.termination_reason)

    # the ONLY escape hatch
    verified = FV.from_least_squares(
        "SD-D/M0", {"status": 0, "nfev": 1200, "loss": 0.44, "hit_nfev_cap": True},
        max_nfev=1200, theta14=[0.0] * 14, convergence_verified=True)
    check("an explicitly re-verified capped fit can become valid again", verified.valid,
          "this is the only escape hatch, and no such procedure is defined as of 2026-07-29")

    # ------------------------------------------------------------------ 2. aggregation
    print(f"\n[2] AGGREGATION: rankings and contrasts ignore invalid candidates")
    cams = ["Left Camera", "Right Camera"]
    V = {c: {} for c in cams}
    V["Left Camera"]["B/M0"] = FV.from_least_squares("B/M0", {"status": 2, "nfev": 30, "loss": 1.0},
                                                     max_nfev=3000, theta14=[0.0] * 14)
    V["Right Camera"]["B/M0"] = FV.from_least_squares("B/M0", {"status": 2, "nfev": 34, "loss": 1.0},
                                                      max_nfev=3000, theta14=[0.0] * 14)
    # SD-D/M0 capped on BOTH cameras; SD-D/M1 capped on the RIGHT camera only
    V["Left Camera"]["SD-D/M0"] = capped
    V["Right Camera"]["SD-D/M0"] = capped
    V["Left Camera"]["SD-D/M1"] = FV.from_least_squares(
        "SD-D/M1", {"status": 2, "nfev": 391, "loss": 1.0}, max_nfev=1200, theta14=[0.0] * 14)
    V["Right Camera"]["SD-D/M1"] = capped
    order = ["B/M0", "SD-D/M0", "SD-D/M1"]
    check("a candidate valid on both cameras is usable",
          FV.candidate_valid(V, "B/M0", cams))
    check("a candidate capped on both cameras is unusable",
          not FV.candidate_valid(V, "SD-D/M0", cams))
    check("a candidate capped on ONE camera only is still unusable",
          not FV.candidate_valid(V, "SD-D/M1", cams),
          "a stereo measurement uses both cameras")
    check("valid_candidates returns only the usable ones",
          FV.valid_candidates(V, order, cams) == ["B/M0"],
          f"{FV.valid_candidates(V, order, cams)}")
    stats = {"B/M0": {"mae": 0.9540}, "SD-D/M0": {"mae": 0.9585}, "SD-D/M1": {"mae": 0.8000}}
    best, val = FV.best_by(V, stats, "mae", order, cams)
    check("best-candidate logic ignores invalid candidates even when they score better",
          best == "B/M0" and abs(val - 0.9540) < 1e-12,
          f"picked {best} at {val}; SD-D/M1's 0.8000 was invalid and ineligible")
    check("a paired contrast with a valid pair is available",
          FV.contrast_available(V, "B/M0", "B/M0", cams))
    check("a paired contrast becomes UNAVAILABLE if either member is invalid",
          not FV.contrast_available(V, "SD-D/M1", "B/M0", cams)
          and not FV.contrast_available(V, "B/M0", "SD-D/M0", cams))
    reason = FV.contrast_unavailable_reason(V, "SD-D/M1", "B/M0", cams)
    check("the unavailable contrast explains which member failed and why",
          "SD-D/M1 invalid" in reason and "cap" in reason, reason[:110])
    check("a candidate with no record at all is not silently treated as valid",
          not FV.candidate_valid(V, "PD-D/M1", cams))

    # ------------------------------------------------------------------ 3. schema round trip
    print(f"\n[3] SERIALISATION keeps the failure information")
    d = capped.to_dict()
    check("to_dict records valid=False and the failure list",
          d["valid"] is False and d["failures"] and d["schema"] == FV.SCHEMA)
    for k in ("optimizer_status", "nfev", "max_nfev", "cap_reached", "cap_kind", "finite_params",
              "finite_loss", "loss", "scaled_optimality", "inverse_ok", "admissible",
              "nests_under_M0", "convergence_verified", "termination_reason"):
        check(f"to_dict carries {k}", k in d)
    check("the dict is JSON-serialisable", isinstance(json.dumps(d), str))

    # ------------------------------------------------------------------ 4. the REAL audited fits
    print(f"\n[4] THE REAL AUDITED CAPPED FITS from the recorded artifact")
    # The pool-only artifact that overwrote the full one is the surviving record of these statuses.
    src = None
    for cand in ("xdoc_objectives_full.json", "xdoc_objectives.stale-pool-only.2026-07-29.json",
                 "xdoc_objectives.json"):
        p = os.path.join(OUT, cand)
        if os.path.exists(p):
            src = p
            break
    if src is None:
        check("a recorded artifact was found to replay", False, "no xdoc artifact present")
    else:
        raw = json.load(open(src))
        docs = raw.get("results", raw).get("documents", {})
        print(f"      replaying fit statuses from {os.path.basename(src)}")
        found, excluded = [], []
        for dk, doc in docs.items():
            for cam, fits in (doc.get("fits") or {}).items():
                for name, f in fits.items():
                    if name.startswith("_") or not isinstance(f, dict) or "status" not in f:
                        continue
                    cap = 1200 if name.startswith("SD-D/") else 3000
                    v = FV.from_least_squares(name, f, max_nfev=cap,
                                             theta14=[0.0] * 14)
                    if f.get("nfev") == cap and f.get("status") == 0:
                        found.append(f"{dk}/{cam}/{name}")
                        if not v.valid:
                            excluded.append(f"{dk}/{cam}/{name}")
                        print(f"        {dk:5} {cam:14} {name:9} nfev={f['nfev']} "
                              f"status={f['status']} -> "
                              f"{'EXCLUDED' if not v.valid else 'STILL REPORTED'}")
                    elif not v.valid:
                        print(f"        {dk:5} {cam:14} {name:9} also invalid: {v.failures()}")
        check("capped status-0 fits were found in the recorded artifact", bool(found),
              f"{len(found)} found")
        check("EVERY capped status-0 fit is now excluded",
              found and set(found) == set(excluded),
              f"{len(excluded)} of {len(found)} excluded")
        # the audit named these specifically for the pool document
        want = {"pool/Left Camera/SD-D/M0", "pool/Right Camera/SD-D/M0",
                "pool/Right Camera/SD-D/M1"}
        got = {f for f in found if f.startswith("pool/")}
        check("the pool capped fits the audit named are among them",
              want <= got or not any(f.startswith("pool/") for f in found),
              f"named {sorted(want)}; found {sorted(got)}")

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED")
    for f in FAIL:
        print(f"    FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                        # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
