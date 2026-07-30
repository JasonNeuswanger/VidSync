#!/usr/bin/env python3
"""Deterministic start generation for SD-D basin search, in a physically conditioned basis.

WHY THIS MODULE REPLACES DIRECT COEFFICIENT SAMPLING. The first attempt drew Sobol points
independently in the raw monomial coefficients (k1..k4, p1, p2) over +-3x the symmetrized corpus
envelope. Every one of 16 proposals was rejected as inadmissible, so the search performed no
exploration at all. That is not a bounds-width problem and shrinking the box would not have fixed it:
the monomial coefficients of a radial polynomial are strongly correlated and span twenty orders of
magnitude (k1 ~ 1e-7 against k4 ~ 1e-26 on this corpus), so independent uniform draws in that basis
essentially never describe a real lens. The repair is to the SAMPLING GEOMETRY, and it is triggered
solely by zero admissibility, before any basin result existed.

THE BASIS. The radial part of the map is r -> r(1 + k1 s + k2 s^2 + k3 s^3 + k4 s^4) with s = r^2, so
the radial DISPLACEMENT at radius r is

    d(r) = r (k1 r^2 + k2 r^4 + k3 r^6 + k4 r^8) = sum_i k_i r^(2i+1).

Sampling d at four fixed radii instead of sampling k directly gives four comparably scaled, physically
interpretable quantities (pixels of radial displacement). The radii are Chebyshev-Gauss nodes mapped to
the normalized interval [0.3, 1.0] of the half-diagonal, which keeps them away from r = 0 where the
displacement carries almost no information about the high-order terms.

The transform is exact and full-rank, and it is done in NORMALIZED radius. Writing rho = r / RMAX and
kappa_i = k_i RMAX^(2i+1),

    d_j = sum_i kappa_i rho_j^(2i+1),      M'[j,i] = rho_j^(2i+1),      kappa = M'^-1 d,
    k_i = kappa_i / RMAX^(2i+1).

In raw radius that Vandermonde has condition number 9.3e19 -- the same ill-conditioning, merely moved.
In normalized radius it is 1.9e3, and a round trip on a real corpus map recovers k1..k4 to 8e-14
relative. `M'` is 4x4 with distinct positive nodes, hence invertible: no model degree of freedom is
removed and no combination of k1..k4 is unreachable. This changes ONLY the start distribution.

The other blocks stay dimensionless and frame-scaled: the centre in fractions of the frame, the
tangential terms by their INDUCED DISPLACEMENT near the frame edge rather than by raw coefficient
magnitude (per unit p1 that displacement is 2.6e6 px, so raw p1 magnitudes are meaningless to sample),
and eta at its declared model bound.

Run with ~/.venvs/vidsync/bin/python.
"""

import numpy as np
from scipy.stats import qmc

import harness_import
import mapmetrics as MM

harness_import.ensure_path()

LT = harness_import.load("lattice")

FRAME_W, FRAME_H = LT.FRAME_W, LT.FRAME_H
RMAX = float(np.hypot(FRAME_W / 2.0, FRAME_H / 2.0))

# Chebyshev-Gauss nodes on the normalized radial interval [0.3, 1.0] of the half-diagonal.
RHO_LO, RHO_HI, N_RAD = 0.30, 1.00, 4


def _cheb(a, b, n):
    j = np.arange(1, n + 1)
    return np.sort(0.5 * (a + b) + 0.5 * (b - a) * np.cos(np.pi * (2 * j - 1) / (2 * n)))


RHO = _cheb(RHO_LO, RHO_HI, N_RAD)
RAD_R = RHO * RMAX
MPRIME = np.stack([RHO ** (2 * i + 1) for i in (1, 2, 3, 4)], axis=1)
_RPOW = np.array([RMAX ** (2 * i + 1) for i in (1, 2, 3, 4)])

# Tangential probe: 90% of the half-frame, where decentering shows most without being a corner.
_TX, _TY = 0.9 * FRAME_W / 2.0, 0.9 * FRAME_H / 2.0
_TS = _TX * _TX + _TY * _TY
TAN_SCALE = np.array([float(np.hypot(_TS + 2 * _TX * _TX, 2 * _TX * _TY)),
                      float(np.hypot(2 * _TX * _TY, _TS + 2 * _TY * _TY))])

ENVELOPE_FACTOR = 3.0            # the ORIGINAL +-3x symmetrized corpus-envelope rule, retained
CENTRE_FRAC = 0.10               # central 80% of the frame
PROPOSAL_CEILING = 4096
MIN_ACCEPT_RATE = 0.01


# =============================================================== exact transforms


def k_from_disp(d):
    """Radial displacements at RAD_R (px) -> k1..k4. Exact, full-rank."""
    return np.linalg.solve(MPRIME, np.asarray(d, float)) / _RPOW


def disp_from_k(k):
    """k1..k4 -> radial displacements at RAD_R (px). Inverse of `k_from_disp`."""
    return MPRIME @ (np.asarray(k, float) * _RPOW)


def p_from_tandisp(t):
    """Tangential induced displacements at the probe (px) -> p1, p2. Diagonal, exact."""
    return np.asarray(t, float) / TAN_SCALE


def tandisp_from_p(p):
    return np.asarray(p, float) * TAN_SCALE


def theta_from_profile(z, free):
    """Profile-space vector -> a 14-parameter map, with non-free entries exactly zero.

    z is [cx_frac, cy_frac, d1..d4, t1, t2, eta] in the conditioned basis.
    """
    th = np.zeros(14)
    th[0] = z[0] * FRAME_W
    th[1] = z[1] * FRAME_H
    th[2:6] = k_from_disp(z[2:6])
    th[9:11] = p_from_tandisp(z[6:8])
    th[13] = z[8]
    th[[j for j in range(14) if j not in set(free)]] = 0.0
    return th


def profile_from_theta(th):
    """A 14-parameter map -> profile-space vector. Inverse of `theta_from_profile`."""
    th = np.asarray(th, float)
    z = np.zeros(9)
    z[0] = th[0] / FRAME_W
    z[1] = th[1] / FRAME_H
    z[2:6] = disp_from_k(th[2:6])
    z[6:8] = tandisp_from_p(th[9:11])
    z[8] = th[13]
    return z


# =============================================================== bounds in profile space


def profile_bounds(corpus_thetas):
    """Sobol bounds in the conditioned basis, from the corpus, with the +-3x rule retained.

    Retaining +-3x is deliberate. The user-visible risk in this round is narrowing the domain until the
    answer looks tidy, so the width rule is unchanged from the failed attempt; only the BASIS changed.
    Broadness is then policed by the dense-grid admissibility check rather than by shrinking the box.
    """
    A = np.array([profile_from_theta(t) for t in corpus_thetas], float)
    lo = np.zeros(9); hi = np.zeros(9)
    lo[0], hi[0] = CENTRE_FRAC, 1.0 - CENTRE_FRAC
    lo[1], hi[1] = CENTRE_FRAC, 1.0 - CENTRE_FRAC
    for j in range(2, 8):
        m = float(np.abs(A[:, j]).max()) if A.size else 0.0
        m = m if m > 0 else 1.0
        lo[j], hi[j] = -ENVELOPE_FACTOR * m, ENVELOPE_FACTOR * m
    lo[8], hi[8] = -LT.ETA_BOUND, LT.ETA_BOUND
    return lo, hi, {
        "basis": "centre fraction of frame; radial displacement (px) at Chebyshev radii; "
                 "tangential induced displacement (px) at the 0.9 half-frame probe; eta",
        "chebyshev_rho": RHO.tolist(), "chebyshev_r_px": RAD_R.tolist(),
        "rho_interval": [RHO_LO, RHO_HI],
        "cond_Mprime_normalized": float(np.linalg.cond(MPRIME)),
        "cond_M_raw_radius": float(np.linalg.cond(
            np.stack([RAD_R ** (2 * i + 1) for i in (1, 2, 3, 4)], axis=1))),
        "tangential_px_per_unit_p": TAN_SCALE.tolist(),
        "envelope_factor": ENVELOPE_FACTOR,
        "centre_rule": f"central {100 * (1 - 2 * CENTRE_FRAC):.0f}% of frame",
        "n_corpus_maps": int(len(corpus_thetas)),
        "corpus_radial_disp_envelope_px": np.abs(A[:, 2:6]).max(axis=0).tolist() if A.size else None,
        "corpus_tangential_disp_envelope_px": np.abs(A[:, 6:8]).max(axis=0).tolist()
        if A.size else None,
    }


# =============================================================== rejection sampling


def _reject_reason(saf):
    """Which admissibility condition failed. Rejections are categorised, not just counted."""
    if not saf["eta_in_bound"]:
        return "eta_out_of_bound"
    if not saf["gate_ok"]:
        return "production_gate"
    if saf["min_det_full_box"] is not None and saf["min_det_full_box"] <= 0.0:
        return "jacobian_det_nonpositive"
    if not saf["inverse_all_converged"]:
        return "inverse_did_not_converge"
    if saf["roundtrip_box_px"] >= 1e-9:
        return "roundtrip_too_large"
    if not saf["radial_monotonic"]:
        return "radial_not_monotonic"
    return "other"


def generate(n_target, free, pts, corpus_thetas, seed, ceiling=PROPOSAL_CEILING,
             min_accept=MIN_ACCEPT_RATE, safety_steps=12):
    """Deterministic Sobol proposals in profile space until `n_target` ADMISSIBLE starts are found.

    Rejected proposals do NOT count toward the target. Returns (accepted, stats); `stats["usable"]` is
    False if the acceptance rate fell below `min_accept` or the target could not be filled within
    `ceiling` proposals -- in which case the caller must report the domain as unusable rather than
    narrowing it again.
    """
    lo, hi, rule = profile_bounds(corpus_thetas)
    sob = qmc.Sobol(d=9, scramble=True, seed=seed)
    accepted, reasons = [], {}
    proposals = 0
    batch = max(32, 2 * n_target)
    while len(accepted) < n_target and proposals < ceiling:
        Z = qmc.scale(sob.random(batch), lo, hi)
        for z in Z:
            if len(accepted) >= n_target or proposals >= ceiling:
                break
            proposals += 1
            th = theta_from_profile(z, free)
            saf = MM.map_safety(th, pts, steps=safety_steps)
            if saf["admissible"] and saf["radial_monotonic"]:
                accepted.append({"index": len(accepted), "proposal": proposals,
                                 "z_profile": z.tolist(), "theta14": th.tolist(),
                                 "radial_disp_px": disp_from_k(th[2:6]).tolist(),
                                 "tangential_disp_px": tandisp_from_p(th[9:11]).tolist()})
            else:
                r = _reject_reason(saf)
                reasons[r] = reasons.get(r, 0) + 1
    rate = len(accepted) / max(proposals, 1)
    stats = {"seed": seed, "n_target": n_target, "n_accepted": len(accepted),
             "n_rejected": proposals - len(accepted), "n_proposals": proposals,
             "acceptance_rate": rate, "ceiling": ceiling, "min_accept_rate": min_accept,
             "rejection_reasons": reasons,
             "target_filled": len(accepted) >= n_target,
             "usable": bool(len(accepted) >= n_target and rate >= min_accept),
             "bounds_lo": lo.tolist(), "bounds_hi": hi.tolist(), "rule": rule,
             "transformation": "profile basis: see startgen module docstring"}
    return accepted, stats
