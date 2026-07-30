#!/usr/bin/env python3
"""THE one representation of "is this fit a usable scientific result?".

WHY THIS EXISTS. `xdoc_objectives.py` recorded `hit_nfev_cap` in its diagnostics, printed a
"HIT 1200-nfev cap" note next to the offending rows, and then put those same rows into the headline
MAE table, the fixed-baseline tail table, the strata table and the paired contrasts, formatted
identically to converged fits. SD-D/M0 on the pool test appears in the published summary at
MAE 0.9585 mm -- second best of seven candidates -- from a fit that stopped because it ran out of
function evaluations, with `status = 0`. SciPy uses `status = 0` for exactly one thing: the maximum
number of evaluations was reached. It is not a success code. A reader of the table had no way to know.

The rule this module enforces is FAIL CLOSED: a candidate is invalid unless it positively demonstrates
convergence. Plausible-looking parameters are not evidence of convergence; neither is a low loss, since
a capped optimizer stops wherever it happened to be. An invalid fit keeps its parameters and its whole
diagnostic record -- it is still the evidence for why SD-D is not production-ready -- but it does not
enter a reconstruction, a ranking, a tail, a stratum or a contrast.

The one escape hatch is `convergence_verified`: if a separate, explicit procedure re-runs a capped fit
to a real termination criterion and demonstrates it, that procedure sets the flag and the fit becomes
valid. No such procedure is defined as of 2026-07-29, so every capped fit is invalid.

Run with ~/.venvs/vidsync/bin/python.
"""

import dataclasses
import math

import numpy as np

SCHEMA = "fit-validity/1"

# scipy.optimize.least_squares termination codes. 0 is the ONLY one that is not a success.
SCIPY_STATUS = {
    -2: "objective evaluation raised",
    -1: "improper input parameters",
    0: "MAXIMUM NUMBER OF FUNCTION EVALUATIONS REACHED (not a convergence criterion)",
    1: "gtol satisfied: gradient is small",
    2: "ftol satisfied: cost change is small",
    3: "xtol satisfied: step is small",
    4: "ftol and xtol both satisfied",
}

INVALID_DISPLAY = "invalid_fit"


@dataclasses.dataclass
class FitValidity:
    """Every fact that bears on whether a fitted candidate may be reported as a result."""

    candidate: str
    optimizer_status: int = None
    nfev: int = None
    max_nfev: int = None
    cap_reached: bool = False
    cap_kind: str = None                 # "max_nfev", "wall_clock", or None
    finite_params: bool = True
    finite_loss: bool = True
    loss: float = None
    optimality: float = None             # scaled first-order optimality from least_squares
    inverse_ok: bool = True              # the eta-aware Newton inverse converged everywhere sampled
    admissible: bool = True              # lattice.admissible()["ok"]
    nests_under_M0: bool = None          # None where the check does not apply (e.g. B, M0 itself)
    convergence_verified: bool = False   # set ONLY by an explicit re-verification procedure
    fitted: bool = True                  # False when the objective was deliberately not fitted
    not_fitted_reason: str = None
    extra: dict = dataclasses.field(default_factory=dict)

    # ---- the rule -------------------------------------------------------------------------

    @property
    def termination_reason(self):
        if not self.fitted:
            return f"not fitted: {self.not_fitted_reason}"
        if self.optimizer_status is None:
            return "no optimizer status recorded"
        return SCIPY_STATUS.get(int(self.optimizer_status),
                                f"unknown status {self.optimizer_status}")

    def failures(self):
        """Every reason this fit is not reportable. Empty list means valid."""
        f = []
        if not self.fitted:
            f.append(f"not fitted ({self.not_fitted_reason})")
            return f
        if self.optimizer_status is None:
            f.append("optimizer status not recorded")
        elif int(self.optimizer_status) < 0:
            # -1 improper input, -2 objective raised. These are never excusable: no amount of
            # after-the-fact verification makes a fit that never ran properly into a result.
            f.append(f"optimizer status {int(self.optimizer_status)}: {self.termination_reason}")
        elif int(self.optimizer_status) == 0 and not self.convergence_verified:
            # SciPy status 0 means the evaluation ceiling was hit; it is the SAME fact as
            # `cap_reached`, so the one escape hatch has to excuse both or it excuses neither.
            f.append(f"optimizer status 0: {self.termination_reason}")
        if self.cap_reached and not self.convergence_verified:
            f.append(f"reached the {self.cap_kind or 'evaluation'} cap "
                     f"({self.nfev} of max_nfev {self.max_nfev}) with no separate "
                     f"convergence-verification procedure having passed")
        if not self.finite_params:
            f.append("non-finite fitted parameters")
        if not self.finite_loss:
            f.append("non-finite loss")
        if not self.inverse_ok:
            f.append("eta-aware inverse did not converge over the working domain")
        if not self.admissible:
            f.append("map is not admissible (production gate, eta bound, "
                     "Jacobian positivity or round trip failed)")
        if self.nests_under_M0 is False:
            f.append("M1 loss exceeds M0 loss: the nested model fitted WORSE, so the optimizer "
                     "did not find the M0 optimum inside the M1 family")
        return f

    @property
    def valid(self):
        return not self.failures()

    def display(self, value, fmt="{:9.4f}"):
        """A number for a valid fit, the literal `invalid_fit` marker for an invalid one.

        Tables call this instead of formatting the number directly, so an invalid candidate can never
        be rendered as a numerical scientific result.
        """
        if not self.valid:
            return INVALID_DISPLAY
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            return "NA"
        return fmt.format(value)

    def to_dict(self):
        return {"schema": SCHEMA, "candidate": self.candidate, "valid": self.valid,
                "failures": self.failures(), "termination_reason": self.termination_reason,
                "optimizer_status": None if self.optimizer_status is None
                else int(self.optimizer_status),
                "nfev": self.nfev, "max_nfev": self.max_nfev,
                "cap_reached": bool(self.cap_reached), "cap_kind": self.cap_kind,
                "finite_params": bool(self.finite_params), "finite_loss": bool(self.finite_loss),
                "loss": self.loss, "scaled_optimality": self.optimality,
                "inverse_ok": bool(self.inverse_ok), "admissible": bool(self.admissible),
                "nests_under_M0": self.nests_under_M0,
                "convergence_verified": bool(self.convergence_verified),
                "fitted": bool(self.fitted), "not_fitted_reason": self.not_fitted_reason,
                **({"extra": self.extra} if self.extra else {})}

    def __str__(self):
        return f"{self.candidate}: {'valid' if self.valid else 'INVALID -- ' + '; '.join(self.failures())}"


# =============================================================== construction from a fit record


def from_least_squares(candidate, diag, max_nfev=None, admissible=None, inverse_ok=None,
                       theta14=None, nests_under_M0=None, cap_kind=None,
                       convergence_verified=False):
    """Build a FitValidity from an `objectives.fit`-shaped diagnostic dict.

    `diag` is expected to carry `status`, `nfev`, `loss`, and optionally `optimality`. Anything absent
    is recorded as missing and counts AGAINST validity rather than being assumed benign.
    """
    nfev = diag.get("nfev")
    cap = diag.get("hit_nfev_cap")
    if cap is None and max_nfev is not None and nfev is not None:
        cap = int(nfev) >= int(max_nfev)
    over_wall = bool(diag.get("over_wall_limit"))
    loss = diag.get("loss")
    th = None if theta14 is None else np.asarray(theta14, float)
    return FitValidity(
        candidate=candidate,
        optimizer_status=diag.get("status"),
        nfev=None if nfev is None else int(nfev),
        max_nfev=None if max_nfev is None else int(max_nfev),
        cap_reached=bool(cap) or over_wall,
        cap_kind=cap_kind or ("max_nfev" if cap else ("wall_clock" if over_wall else None)),
        finite_params=True if th is None else bool(np.all(np.isfinite(th))),
        finite_loss=loss is not None and bool(np.isfinite(loss)),
        loss=None if loss is None else float(loss),
        optimality=diag.get("optimality"),
        inverse_ok=True if inverse_ok is None else bool(inverse_ok),
        admissible=True if admissible is None else bool(admissible),
        nests_under_M0=diag.get("nests_under_M0") if nests_under_M0 is None else nests_under_M0,
        convergence_verified=bool(convergence_verified),
        extra={k: diag[k] for k in ("wall_s", "min_block_eig", "projected_condition",
                                    "inverse_failures", "eta") if k in diag})


def not_fitted(candidate, reason):
    return FitValidity(candidate=candidate, fitted=False, not_fitted_reason=reason)


# =============================================================== aggregation helpers


def candidate_valid(validities, candidate, cameras=None):
    """A candidate is usable for a DOCUMENT only if it is valid on EVERY camera of that document.

    A stereo reconstruction uses both cameras, so one invalid camera invalidates the reconstruction.
    """
    cams = list(validities) if cameras is None else list(cameras)
    got = [validities[c][candidate] for c in cams if candidate in validities.get(c, {})]
    return bool(got) and len(got) == len(cams) and all(v.valid for v in got)


def valid_candidates(validities, order, cameras=None):
    return [c for c in order if candidate_valid(validities, c, cameras)]


def invalid_reasons(validities, candidate, cameras=None):
    """Per-camera failure reasons, for the diagnostic section of a report."""
    cams = list(validities) if cameras is None else list(cameras)
    out = {}
    for c in cams:
        v = validities.get(c, {}).get(candidate)
        if v is None:
            out[c] = ["no fit record"]
        elif not v.valid:
            out[c] = v.failures()
    return out


def best_by(validities, stats, key, order, cameras=None, lower_is_better=True):
    """The best VALID candidate by `stats[candidate][key]`. Invalid candidates are ignored entirely.

    Returns (name, value) or (None, None) if no candidate is valid.
    """
    ok = [c for c in valid_candidates(validities, order, cameras)
          if c in stats and stats[c].get(key) is not None
          and np.isfinite(stats[c][key])]
    if not ok:
        return None, None
    b = min(ok, key=lambda c: stats[c][key]) if lower_is_better \
        else max(ok, key=lambda c: stats[c][key])
    return b, stats[b][key]


def contrast_available(validities, a, b, cameras=None):
    """A paired contrast requires BOTH members valid; otherwise it is unavailable, not zero."""
    return candidate_valid(validities, a, cameras) and candidate_valid(validities, b, cameras)


def contrast_unavailable_reason(validities, a, b, cameras=None):
    bad = []
    for name in (a, b):
        if not candidate_valid(validities, name, cameras):
            bad.append(f"{name} invalid ({invalid_reasons(validities, name, cameras)})")
    return "; ".join(bad)
