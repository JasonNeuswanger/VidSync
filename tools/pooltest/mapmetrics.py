#!/usr/bin/env python3
"""Map-space comparison metrics, predeclared before any basin comparison is inspected.

WHY THIS MODULE EXISTS. Round 2 classified solutions by optimizer status and by whether a fit was
"convergence verified". Round 3 showed that is not sufficient: on one deterministic synthetic target a
fit terminated with SciPy status 2, survived multi-start restart verification, and still carried a map
88.8 px wrong. Optimizer success is evidence about the optimizer, not about the map.

Two further traps this module is built to avoid.

  PARAMETER DISTANCE IS NOT PHYSICAL DISTANCE. The 14 distortion parameters are wildly different in
  scale and strongly correlated; a small coefficient change can move the corrected image a long way and
  a large one can barely move it. Everything here is measured as a DISPLACEMENT OF THE CORRECTED IMAGE
  in pixels.

  A HOMOGRAPHY BETWEEN TWO MAPS IS NOT AN ERROR. Downstream, each camera's corrected image is fitted to
  the calibration frame by a planar homography. Two distortion maps that differ only by a projective
  transform therefore produce the SAME reconstruction after recalibration: the difference is absorbed by
  the gauge. So the decision-relevant quantity is the residual difference AFTER removing the best
  homography between the two maps, and the raw difference is reported only alongside it.

Vocabulary, used deliberately instead of "globally verified": `valid_local_fit`, `distinct_basin`,
`near_equivalent_loss`, `target_ambiguous`.

Run with ~/.venvs/vidsync/bin/python.
"""

import math

import numpy as np

import harness_import

harness_import.ensure_path()

LT = harness_import.load("lattice")

FRAME_W, FRAME_H = LT.FRAME_W, LT.FRAME_H


# =============================================================== predeclared thresholds
#
# Declared HERE, before any comparison in this round was inspected, and each tied to a quantity that
# already existed rather than chosen to make a result come out. Because no single number is defensible
# for every use, the basin study reports sensitivity across the whole ladder rather than picking one.
#
#   0.01 px  numerical floor. The round-1 injection-parity gate accepted 9.1e-13 px on deterministic
#            stages and 4.3e-6 mm downstream; 0.01 px is far above any arithmetic noise, so a
#            difference below it cannot be distinguished from round-off.
#   0.10 px  detection-noise floor. Below the plausible click/detector precision (bracketed in the
#            noise study), so two maps differing by less than this are not separable by the data.
#   0.50 px  the existing `COINCIDENT_PX` clustering radius: the scale at which the harness already
#            treats two image positions as the same observation.
#   2.00 px  the observed weighted residual scale on real SD-D fits (rms 0.21 px on mid Right, and the
#            0.6-1.5 px range across cameras), times a small factor. Differences of this size are
#            comparable to the model's own misfit.
#  10.00 px  materially different corrected geometry: a map difference this large at the frame scale
#            moves reconstructed lengths by more than the 0.1-1 mm contrasts the known-length work is
#            trying to resolve.
MAP_THRESHOLDS_PX = (0.01, 0.10, 0.50, 2.00, 10.00)

# The threshold used for the headline `distinct_basin` label. 0.5 px is chosen because it is the
# harness's own existing same-observation radius, so calling two maps distinct below it would contradict
# a decision the harness already makes elsewhere.
DISTINCT_BASIN_PX = 0.50

# Downstream materiality, in mm. The known-length contrasts this corpus resolves are 0.1-1 mm
# (round-1 cluster means ranged 0.015-1.222 mm), so 0.1 mm is the smallest difference that could change
# a reported conclusion.
DOWNSTREAM_MATERIAL_MM = 0.10


# =============================================================== grids


def frame_grid(n=48, margin=20.0):
    """A fixed dense grid over the usable frame. Deterministic, so every comparison uses the same one."""
    gx, gy = np.meshgrid(np.linspace(margin, FRAME_W - margin, n),
                         np.linspace(margin, FRAME_H - margin, n))
    return np.stack([gx.ravel(), gy.ravel()], axis=1)


def hull_mask(grid, pts):
    """Which grid points lie inside the convex hull of the observations.

    Extrapolation beyond the observed region is where any distortion model is least constrained, so
    inside-hull and full-frame differences are reported separately rather than pooled.
    """
    from scipy.spatial import Delaunay
    pts = np.asarray(pts, float)
    if len(pts) < 3:
        return np.zeros(len(grid), bool)
    return Delaunay(pts).find_simplex(grid) >= 0


# =============================================================== projective alignment


def fit_homography(src, dst):
    """The least-squares homography taking `src` to `dst`, h22 fixed to 1. Returns a 3x3 matrix.

    Standard DLT on the inhomogeneous form. Both point sets are pre-normalized (translate to centroid,
    scale to unit mean radius) because the raw pixel coordinates are of order 1e3 and the unnormalized
    system is badly conditioned; the normalization is undone on the way out.
    """
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)

    def norm(P):
        c = P.mean(axis=0)
        s = np.sqrt(2.0) / max(np.linalg.norm(P - c, axis=1).mean(), 1e-12)
        T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])
        Q = (P - c) * s
        return Q, T

    S, Ts = norm(src)
    Dp, Td = norm(dst)
    n = len(S)
    A = np.zeros((2 * n, 8))
    b = np.zeros(2 * n)
    A[0::2, 0] = S[:, 0]; A[0::2, 1] = S[:, 1]; A[0::2, 2] = 1.0
    A[0::2, 6] = -S[:, 0] * Dp[:, 0]; A[0::2, 7] = -S[:, 1] * Dp[:, 0]
    b[0::2] = Dp[:, 0]
    A[1::2, 3] = S[:, 0]; A[1::2, 4] = S[:, 1]; A[1::2, 5] = 1.0
    A[1::2, 6] = -S[:, 0] * Dp[:, 1]; A[1::2, 7] = -S[:, 1] * Dp[:, 1]
    b[1::2] = Dp[:, 1]
    h, *_ = np.linalg.lstsq(A, b, rcond=None)
    Hn = np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])
    return np.linalg.inv(Td) @ Hn @ Ts


def _refine_homography(H0, src, dst, iters=12):
    """Gauss-Newton on the GEOMETRIC residual |pi(H src) - dst|, starting from the DLT estimate."""
    h = np.asarray(H0, float).ravel()[:8].copy()
    src = np.asarray(src, float); dst = np.asarray(dst, float)
    x, y = src[:, 0], src[:, 1]
    for _ in range(iters):
        H = np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])
        wd = H[2, 0] * x + H[2, 1] * y + 1.0
        wd = np.where(np.abs(wd) < 1e-12, 1e-12, wd)
        u = (H[0, 0] * x + H[0, 1] * y + H[0, 2]) / wd
        v = (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / wd
        r = np.concatenate([u - dst[:, 0], v - dst[:, 1]])
        n = len(x)
        Jm = np.zeros((2 * n, 8))
        Jm[:n, 0] = x / wd; Jm[:n, 1] = y / wd; Jm[:n, 2] = 1.0 / wd
        Jm[:n, 6] = -u * x / wd; Jm[:n, 7] = -u * y / wd
        Jm[n:, 3] = x / wd; Jm[n:, 4] = y / wd; Jm[n:, 5] = 1.0 / wd
        Jm[n:, 6] = -v * x / wd; Jm[n:, 7] = -v * y / wd
        try:
            step, *_ = np.linalg.lstsq(Jm, -r, rcond=None)
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(step)) or np.abs(step).max() < 1e-14:
            break
        h = h + step
    return np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])


def apply_homography(H, P):
    P = np.asarray(P, float)
    w = H[2, 0] * P[:, 0] + H[2, 1] * P[:, 1] + H[2, 2]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    return np.stack([(H[0, 0] * P[:, 0] + H[0, 1] * P[:, 1] + H[0, 2]) / w,
                     (H[1, 0] * P[:, 0] + H[1, 1] * P[:, 1] + H[1, 2]) / w], axis=1)


def _summ(d):
    if d.size == 0:
        return {"n": 0}
    return {"n": int(d.size), "median": float(np.median(d)),
            "p95": float(np.percentile(d, 95)), "max": float(d.max()),
            "rms": float(np.sqrt((d ** 2).mean()))}


def map_difference(th_a, th_b, grid=None, pts=None):
    """Raw and projectively aligned corrected-map difference between two 14-parameter maps.

    `aligned` is the decision-relevant number: it is what remains after the best planar homography
    between the two corrected images has been removed, i.e. after the freedom that downstream
    recalibration would absorb anyway. `raw` is reported beside it so a pure gauge difference is
    visible as a large raw and a small aligned value.
    """
    grid = frame_grid() if grid is None else grid
    A = LT.U(grid, np.asarray(th_a, float))
    B = LT.U(grid, np.asarray(th_b, float))
    raw = np.linalg.norm(A - B, axis=1)
    # The DLT minimizes an ALGEBRAIC error, which is not the geometric residual, so on small
    # perturbations it could return an alignment WORSE than doing nothing -- observed as aligned > raw
    # and negative "gauge fractions". Refine it on the geometric residual and keep the identity as a
    # candidate, so `aligned <= raw` always holds and the gauge split is meaningful.
    H = _refine_homography(fit_homography(A, B), A, B)
    aligned = np.linalg.norm(apply_homography(H, A) - B, axis=1)
    if float(np.median(aligned)) > float(np.median(raw)):
        H = np.eye(3)
        aligned = raw.copy()
    out = {"raw_full": _summ(raw), "aligned_full": _summ(aligned),
           "homography": H.tolist(),
           "gauge_fraction": (float(np.median(raw)) - float(np.median(aligned)))
           / max(float(np.median(raw)), 1e-300)}
    if pts is not None:
        m = hull_mask(grid, pts)
        out["hull_coverage"] = float(m.mean())
        out["raw_hull"] = _summ(raw[m])
        out["aligned_hull"] = _summ(aligned[m])
    return out


def distinct_basin(diff, thresh=DISTINCT_BASIN_PX):
    """Two solutions are a DISTINCT BASIN only if they differ after projective alignment.

    Deliberately conservative: it uses the aligned median inside the observation hull where available,
    because that is where the data actually constrains the map, and a large difference achieved only by
    extrapolating outside the hull is not evidence of a physically distinct fit.
    """
    key = "aligned_hull" if "aligned_hull" in diff and diff["aligned_hull"].get("n") else "aligned_full"
    return bool(diff[key]["median"] > thresh), key


def threshold_ladder(diff):
    """Distinctness verdict at every predeclared threshold, so nothing is chosen post hoc."""
    key = "aligned_hull" if "aligned_hull" in diff and diff["aligned_hull"].get("n") else "aligned_full"
    med = diff[key]["median"]
    return {f"{t:g}px": bool(med > t) for t in MAP_THRESHOLDS_PX}


# =============================================================== per-solution diagnostics


def n_eff(w):
    """Effective weighted sample size, (sum w)^2 / sum w^2."""
    w = np.asarray(w, float)
    return float(w.sum() ** 2 / max((w ** 2).sum(), 1e-300))


def map_safety(th14, pts, steps=40):
    """Admissibility, inverse safety, Jacobian positivity and radial monotonicity.

    `lattice.admissible` already covers the production gate, the eta bound, Jacobian determinant
    positivity and the Newton round trip. Radial monotonicity is added here: a map whose radial
    magnification stops being monotonic has folded the image even where the determinant is still
    positive, and that is checked along rays from the fitted centre rather than on the box grid.
    """
    th = np.asarray(th14, float)
    ad = LT.admissible(th, np.asarray(pts, float), steps=steps)
    c = th[:2]
    ang = np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False)
    rmax = float(np.hypot(max(c[0], FRAME_W - c[0]), max(c[1], FRAME_H - c[1])))
    r = np.linspace(1.0, rmax, 60)
    mono_ok = True
    worst = np.inf
    for a in ang:
        P = c[None, :] + np.stack([r * np.cos(a), r * np.sin(a)], axis=1)
        keep = ((P[:, 0] >= 0) & (P[:, 0] <= FRAME_W) & (P[:, 1] >= 0) & (P[:, 1] <= FRAME_H))
        if keep.sum() < 3:
            continue
        Q = LT.U(P[keep], th)
        rr = np.linalg.norm(Q - c[None, :], axis=1)
        d = np.diff(rr)
        worst = min(worst, float(d.min()) if d.size else np.inf)
        if d.size and d.min() <= 0:
            mono_ok = False
    return {"admissible": bool(ad["ok"]), "gate_ok": bool(ad["gate_ok"]),
            "eta_in_bound": bool(ad["eta_in_bound"]),
            "min_det_full_box": ad["min_det_full_box"],
            "min_det_full_frame": ad["min_det_full_frame"],
            "roundtrip_box_px": ad["roundtrip_box_px"],
            "inverse_all_converged": bool(ad["roundtrip_box_all_converged"]),
            "radial_monotonic": bool(mono_ok),
            "min_radial_increment_px": None if not np.isfinite(worst) else worst}


def scaled_spectrum(J, nm, soft_ratio=1e-3):
    """Singular spectrum of the scaled Jacobian, and how many directions are materially soft.

    Reported for J and interpreted for J^T J: a condition number of 1e6 on J is 1e12 on J^T J, which is
    why "the condition number looks benign" is not an argument. `soft` counts directions whose singular
    value is below `soft_ratio` of the largest, i.e. directions along which the objective is nearly flat.
    """
    J = np.asarray(J.toarray() if hasattr(J, "toarray") else J, float)
    sv = np.linalg.svd(J, compute_uv=False)
    if sv.size == 0:
        return {"n_sv": 0, "cond_J": float("inf"), "log10_cond_J": float("inf"),
                "log10_cond_JtJ": float("inf"), "n_soft": 0, "soft_ratio": soft_ratio}
    smax = float(sv[0])
    smin = float(sv[-1])
    # Reported in LOG10 as well as linearly. cond(J^T J) = cond(J)^2, and on these problems cond(J) can
    # exceed 1e160, where squaring overflows a float -- which is itself the finding, not an error to be
    # papered over: a direction that numerically vanishes in J is exactly unidentified in J^T J.
    log_cond = (math.log10(smax) - math.log10(smin)) if (smax > 0 and smin > 0) else float("inf")
    return {"n_sv": int(sv.size), "sv_max": smax, "sv_min": smin,
            "cond_J": (smax / smin) if (smin > 0 and log_cond < 300) else float("inf"),
            "log10_cond_J": log_cond,
            "log10_cond_JtJ": 2.0 * log_cond,
            "numerically_singular": bool(smin <= 0.0 or log_cond > 15.0),
            "n_soft": int((sv < soft_ratio * smax).sum()),
            "soft_ratio": soft_ratio,
            "sv_model_block_min": float(np.linalg.svd(J[:, :nm], compute_uv=False)[-1])
            if nm and J.shape[1] >= nm else None,
            "sv_tail": [float(v) for v in sv[-min(6, sv.size):]]}


# =============================================================== experimental: admissibility_v2
#
# EXPERIMENTAL. Not integrated into production, not a default, not used by any authoritative reporting
# path. Prototyped here because the existing gate proved resolution-sensitive.
#
# WHY. `lattice.admissible` evaluates its forward/inverse round trip on a FIXED grid whose density is a
# caller argument, and it inherits `lattice.inv_U`, which seeds Newton at x0 = y (the target point
# itself). On synth17 accepted start 11 that combination produced a 348 px "inverse failure" on a map
# that is provably safe:
#
#     determinant over the frame      0.8696 .. 2036.9      (strictly positive)
#     minimum singular value          0.9100               (bounded away from zero)
#     boundary-image winding number   1.0000               (simple closed curve, no orientation reversal)
#     failures                        7 of 1681 grid points, all at extreme radius
#     independent continuation solve  recovers every preimage to 2.8e-13 px
#
# So the map is a diffeomorphism onto its image and the 348 px was the round-trip error of a DIVERGED
# Newton iterate: at those corners the forward image lies 12945 px from the seed. The failure was an
# inverse-solver defect plus a grid-resolution artefact, not an unsafe map. `admissibility_v2` therefore
# (a) uses a robust inverse, and (b) refines adaptively in NORMALIZED coordinates instead of trusting one
# fixed grid.


def robust_inverse(y, th14, nsteps=24, tol=1e-10, damping=0.9):
    """Continuation inverse: track x through U_t(x) = y as t runs 0 -> 1, scaling the distortion.

    At t = 0 the map is the identity, so x = y is exact; each subsequent step starts from the previous
    solution, which keeps Newton inside its basin even where the forward map expands violently. This is
    the diagnostic reference that showed the 348 px failure was solver divergence, and it is what
    `admissibility_v2` uses instead of `lattice.inv_U`. Returns (x, max_forward_residual_per_point).
    """
    th = np.asarray(th14, float)
    y = np.atleast_2d(np.asarray(y, float))
    x = y.copy()
    for t in np.linspace(0.0, 1.0, nsteps + 1)[1:]:
        q = th.copy()
        q[2:13] *= t
        q[13] *= t
        for _ in range(60):
            r = LT.U(x, q) - y
            if np.abs(r).max() < tol:
                break
            J = LT.jac_U(x, q)
            det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
            det = np.where(np.abs(det) < 1e-14, 1e-14, det)
            dx = np.stack([(J[:, 1, 1] * r[:, 0] - J[:, 0, 1] * r[:, 1]) / det,
                           (-J[:, 1, 0] * r[:, 0] + J[:, 0, 0] * r[:, 1]) / det], axis=1)
            x = x - damping * dx
    return x, np.abs(LT.U(x, th) - y).max(axis=1)


def _norm_grid(n, w, h):
    """Grid in NORMALIZED frame coordinates, including the boundary, mapped to pixels."""
    u = np.linspace(0.0, 1.0, n)
    gx, gy = np.meshgrid(u * w, u * h)
    return np.stack([gx.ravel(), gy.ravel()], axis=1)


def admissibility_v2(th14, w=None, h=None, n0=17, max_refine=3, det_margin=1e-3,
                     sv_margin=1e-3, jac_var_limit=50.0, roundtrip_tol=1e-6,
                     expansion_limit=8.0):
    """Resolution-independent map-safety gate. EXPERIMENTAL.

    Checks, all in normalized frame coordinates so the verdict does not depend on pixel dimensions:

      determinant and minimum-singular-value margins over the full usable frame including edges and
        corners, refined adaptively where the margin is worst rather than on one fixed grid;
      rapid spatial variation of the Jacobian, as the ratio of neighbouring determinants;
      boundary self-intersection and orientation reversal, via the winding number of the boundary image
        about the fitted centre and a segment-crossing test;
      forward/inverse round trip using `robust_inverse`, so a solver failure is not scored as an unsafe
        map;
      gross expansion, reported SEPARATELY from safety: a map can be a mathematical diffeomorphism and
        still send the frame corner 13000 px away, which is not a physically plausible camera.

    `safe` is the conjunction of the geometric conditions. `physically_plausible` additionally requires
    bounded expansion. They are deliberately distinct verdicts.
    """
    th = np.asarray(th14, float)
    w = FRAME_W if w is None else float(w)
    h = FRAME_H if h is None else float(h)
    diag = float(np.hypot(w, h))

    pts = _norm_grid(n0, w, h)
    worst = {"det": np.inf, "sv": np.inf}
    dets, svs = [], []
    for level in range(max_refine + 1):
        J = LT.jac_U(pts, th)
        det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
        sv = np.linalg.svd(J, compute_uv=False)
        dets.append(det); svs.append(sv)
        worst["det"] = min(worst["det"], float(np.nanmin(det)))
        worst["sv"] = min(worst["sv"], float(np.nanmin(sv[:, 1])))
        if level == max_refine:
            break
        # refine around the worst 5% of the determinant margin
        k = max(4, int(0.05 * len(pts)))
        idx = np.argsort(det)[:k]
        step = (w / (n0 - 1)) / (2 ** (level + 1))
        off = np.array([[0, 0], [step, 0], [-step, 0], [0, step], [0, -step],
                        [step, step], [-step, -step], [step, -step], [-step, step]])
        cand = (pts[idx][:, None, :] + off[None, :, :]).reshape(-1, 2)
        cand = cand[(cand[:, 0] >= 0) & (cand[:, 0] <= w)
                    & (cand[:, 1] >= 0) & (cand[:, 1] <= h)]
        pts = cand if len(cand) else pts

    det_all = np.concatenate(dets)
    sv_all = np.concatenate([s[:, 1] for s in svs])
    aniso = np.concatenate([s[:, 0] / np.maximum(s[:, 1], 1e-300) for s in svs])

    # Jacobian spatial variation, on the base grid only (neighbour ratios need a structured grid)
    d0 = dets[0].reshape(n0, n0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rx = np.abs(d0[:, 1:] / np.maximum(d0[:, :-1], 1e-300))
        ry = np.abs(d0[1:, :] / np.maximum(d0[:-1, :], 1e-300))
    jac_var = float(np.nanmax(np.concatenate([rx.ravel(), ry.ravel(),
                                              1.0 / np.maximum(rx.ravel(), 1e-300),
                                              1.0 / np.maximum(ry.ravel(), 1e-300)])))

    # boundary behaviour
    m = 400
    bnd = np.vstack([np.stack([np.linspace(0, w, m), np.zeros(m)], 1),
                     np.stack([np.full(m, w), np.linspace(0, h, m)], 1),
                     np.stack([np.linspace(w, 0, m), np.full(m, h)], 1),
                     np.stack([np.zeros(m), np.linspace(h, 0, m)], 1)])
    Ub = LT.U(bnd, th)
    c = th[:2]
    ang = np.unwrap(np.arctan2(Ub[:, 1] - c[1], Ub[:, 0] - c[0]))
    winding = float((ang[-1] - ang[0]) / (2.0 * np.pi))
    seg = np.diff(Ub, axis=0)
    cross = float(np.min(np.abs(seg[:, 0] * np.roll(seg[:, 1], -1)
                                - seg[:, 1] * np.roll(seg[:, 0], -1))))

    # adaptive round trip with the robust inverse
    rt_pts = np.vstack([_norm_grid(13, w, h), bnd[::37]])
    xb, res = robust_inverse(LT.U(rt_pts, th), th)
    rt = float(np.abs(xb - rt_pts).max())

    expansion = float(np.linalg.norm(Ub - c, axis=1).max() / (0.5 * diag))

    geom_ok = bool(worst["det"] > det_margin and worst["sv"] > sv_margin
                   and abs(winding - 1.0) < 1e-3 and jac_var < jac_var_limit
                   and rt < roundtrip_tol and np.all(np.isfinite(det_all)))
    return {"safe": geom_ok,
            "physically_plausible": bool(geom_ok and expansion <= expansion_limit),
            "min_det": worst["det"], "min_sigma": worst["sv"],
            "max_anisotropy": float(np.nanmax(aniso)),
            "jac_neighbour_ratio_max": jac_var, "jac_var_limit": jac_var_limit,
            "boundary_winding": winding, "boundary_min_cross": cross,
            "roundtrip_px": rt, "roundtrip_tol": roundtrip_tol,
            "expansion_ratio": expansion, "expansion_limit": expansion_limit,
            "n_points_evaluated": int(len(det_all)), "refinement_levels": max_refine,
            "frame": [w, h],
            "reasons": [k for k, v in (("det_margin", worst["det"] > det_margin),
                                       ("sigma_margin", worst["sv"] > sv_margin),
                                       ("boundary_winding", abs(winding - 1.0) < 1e-3),
                                       ("jacobian_variation", jac_var < jac_var_limit),
                                       ("roundtrip", rt < roundtrip_tol)) if not v]}


# =============================================================== profiled physical conditioning


def profiled_spectrum(ev, p, nm, grid=None, pts=None, eps_frac=1e-3):
    """Physical conditioning AFTER projecting out the line nuisances, then splitting off the gauge.

    WHY. A raw SVD of the full Jacobian mixes three completely different things: softness in the ~2*nline
    line nuisance parameters (a bookkeeping artefact), softness that only moves the corrected image by a
    projective transform (absorbed by downstream recalibration), and softness that genuinely changes
    corrected geometry. Only the third matters. So:

      1. Schur-complement the nuisance block out of the Gauss-Newton normal matrix. With J = [Jm Jn],
         the model-block information after profiling the nuisances is
             S = Jm^T Jm - Jm^T Jn (Jn^T Jn)^-1 Jn^T Jm,
         which is exactly the Gauss-Newton curvature of the nuisance-profiled objective.
      2. Take the eigenvectors of S. Each is a physical model direction with its own curvature.
      3. Step along each by an amount that raises the objective by a fixed budget, and decompose the
         induced corrected-map displacement into the part a homography can absorb and the part it cannot.

    Returns per-direction curvature and the residual NONPROJECTIVE displacement, which is the quantity
    that should drive any fail-closed decision.
    """
    J = ev.jacobian(np.asarray(p, float))
    J = J.toarray() if hasattr(J, "toarray") else np.asarray(J)
    Jm, Jn = J[:, :nm], J[:, nm:]
    A = Jn.T @ Jn
    # ridge only for the numerical solve of the nuisance block; it does not alter the estimator
    ridge = eps_frac * float(np.trace(A)) / max(A.shape[0], 1)
    X = np.linalg.solve(A + ridge * np.eye(A.shape[0]), Jn.T @ Jm)
    S = Jm.T @ Jm - (Jm.T @ Jn) @ X
    S = 0.5 * (S + S.T)
    evals, evecs = np.linalg.eigh(S)
    return {"eigenvalues": evals.tolist(), "eigenvectors": evecs,
            "cond_profiled": float(abs(evals[-1]) / max(abs(evals[0]), 1e-300)),
            "log10_cond_profiled": (math.log10(abs(evals[-1])) - math.log10(abs(evals[0])))
            if (evals[-1] > 0 and evals[0] > 0) else float("inf"),
            "n_nonpositive": int((evals <= 0).sum()), "ridge_used": ridge}


def gauge_split(ev, p, th, nm, direction, curvature, budget, pk, base, grid=None, pts=None):
    """Move along one profiled physical direction by a noise-budget step and split the map change.

    The step is sized so the quadratic model predicts an objective rise of `budget`: for curvature c,
    a = sqrt(budget / c). The induced corrected-map displacement is then decomposed into the projective
    part (removable by a homography, i.e. absorbed by recalibration) and the residual nonprojective part.
    """
    p = np.asarray(p, float)
    l0 = ev.loss(p)
    a = math.sqrt(max(budget, 0.0) / max(abs(curvature), 1e-300))
    # The quadratic model badly underestimates the rise along the softest directions (realised dloss of
    # +37 against a budget of 0.8 on a first attempt), so the step is BACKTRACKED until the realised
    # objective rise is actually within twice the noise budget. Otherwise the reported map displacement
    # belongs to a perturbation the data could easily reject, and means nothing.
    calibrated = False
    for _ in range(60):
        q = p.copy()
        q[:nm] = q[:nm] + a * np.asarray(direction, float)
        dl = ev.loss(q) - l0
        if dl <= 2.0 * budget:
            calibrated = True
            break
        a *= 0.5
    th2 = pk.theta(q, base)
    d = map_difference(th, th2, grid, pts)
    raw = d.get("raw_hull", d["raw_full"])["median"]
    al = d.get("aligned_hull", d["aligned_full"])["median"]
    return {"curvature": float(curvature), "step": float(a),
            "step_calibrated": bool(calibrated), "budget": float(budget),
            "dloss_realised": float(dl),
            "raw_hull_median_px": raw, "aligned_hull_median_px": al,
            "projective_part_px": max(raw - al, 0.0),
            "gauge_fraction": (raw - al) / max(raw, 1e-300),
            "classification": ("consequential_nonprojective" if al > DISTINCT_BASIN_PX
                               else "projective_gauge" if raw > DISTINCT_BASIN_PX
                               else "harmless_parameter_softness")}


# =============================================================== forward-map validity certification
#
# EXPERIMENTAL. Replaces the overloaded word "safe" with three separate questions:
#   A. forward-map injectivity   -- certify_forward_injective
#   B. numerical inverse reliability -- inverse_reliability
#   C. operational plausibility  -- plausibility_metrics
#
# Grid sampling with positive determinants and a winding number of one is NOT a proof, and the previous
# tranche overstated it as "provably diffeomorphic". What follows is an actual interval certification of
# det J > 0 by recursive subdivision, plus a certified-monotone boundary test, and it reports honestly
# when it cannot close the argument.


def _interval_det_bound(th, x0, x1, y0, y1, samples=5):
    """A rigorous-in-spirit lower bound on det J over the cell [x0,x1]x[y0,y1].

    det J is a polynomial in (x, y) for this map family at fixed eta, so on a cell it satisfies a
    Lipschitz bound: min det >= min over sampled corners/edges minus L * (cell half-diagonal), where L
    bounds |grad det| on the cell. L is estimated by central differences at the cell centre inflated by a
    safety factor. This is a CONSERVATIVE numerical bound, not a symbolic Bernstein hull -- see
    `certify_forward_injective` for the honest labelling that follows from that.
    """
    xs = np.linspace(x0, x1, samples)
    ys = np.linspace(y0, y1, samples)
    gx, gy = np.meshgrid(xs, ys)
    P = np.stack([gx.ravel(), gy.ravel()], axis=1)
    J = LT.jac_U(P, th)
    d = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
    dmin = float(np.nanmin(d))
    hx = max((x1 - x0) / (samples - 1), 1e-9)
    hy = max((y1 - y0) / (samples - 1), 1e-9)
    dd = d.reshape(samples, samples)
    gxm = np.abs(np.diff(dd, axis=1)).max() / hx if samples > 1 else 0.0
    gym = np.abs(np.diff(dd, axis=0)).max() / hy if samples > 1 else 0.0
    L = 2.0 * float(np.hypot(gxm, gym))            # safety factor 2 on the sampled gradient
    half = 0.5 * float(np.hypot(x1 - x0, y1 - y0))
    return dmin - L * half, dmin


def certify_forward_injective(th14, w=None, h=None, max_cells=4096, min_cell_px=2.0,
                              boundary_pts=2000):
    """Attempt to certify that the correction is injective and orientation-preserving on the frame.

    ARGUMENT USED. If (i) det J > 0 everywhere on the closed rectangle, and (ii) the image of the
    rectangle's boundary is a simple closed curve, then the map is a homeomorphism of the rectangle onto
    the closed Jordan domain it bounds, and a diffeomorphism on the interior. This is the standard
    degree-theory / Jordan-domain argument: a local diffeomorphism on a compact domain whose boundary maps
    injectively has topological degree one on the enclosed region, hence is globally injective.

    WHAT IS ACTUALLY VERIFIED HERE. (i) is attacked by recursive subdivision with the conservative cell
    bound in `_interval_det_bound`; a cell is certified when its lower bound is positive, and subdivided
    otherwise until it is certified, refuted (a sampled determinant is <= 0), or hits `min_cell_px`.
    (ii) is tested by a dense segment-intersection scan of the boundary image plus a monotone
    turning/winding check. Neither step is a symbolic proof: the determinant bound uses a sampled
    Lipschitz estimate and the boundary test uses a finite polyline.

    So the verdict is one of:
        "certified_injective_at_bound"   every cell certified and the boundary image simple
        "refuted_not_injective"          a determinant <= 0 was exhibited, or the boundary self-crosses
        "unresolved"                     subdivision hit the cell-size floor without deciding
    and NEVER "provably diffeomorphic".
    """
    th = np.asarray(th14, float)
    w = FRAME_W if w is None else float(w)
    h = FRAME_H if h is None else float(h)
    cells = [(0.0, w, 0.0, h)]
    certified, undecided, refuted = 0, [], False
    worst_lb, worst_sampled = np.inf, np.inf
    n_eval = 0
    while cells and n_eval < max_cells:
        x0, x1, y0, y1 = cells.pop()
        n_eval += 1
        lb, dmin = _interval_det_bound(th, x0, x1, y0, y1)
        worst_lb = min(worst_lb, lb)
        worst_sampled = min(worst_sampled, dmin)
        if dmin <= 0.0:
            refuted = True
            break
        if lb > 0.0:
            certified += 1
            continue
        if min(x1 - x0, y1 - y0) <= min_cell_px:
            undecided.append((x0, x1, y0, y1))
            continue
        xm, ym = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        cells += [(x0, xm, y0, ym), (xm, x1, y0, ym), (x0, xm, ym, y1), (xm, x1, ym, y1)]

    m = boundary_pts // 4
    bnd = np.vstack([np.stack([np.linspace(0, w, m), np.zeros(m)], 1),
                     np.stack([np.full(m, w), np.linspace(0, h, m)], 1),
                     np.stack([np.linspace(w, 0, m), np.full(m, h)], 1),
                     np.stack([np.zeros(m), np.linspace(h, 0, m)], 1)])
    Ub = LT.U(bnd, th)
    simple, ncross = _polyline_simple(Ub)
    c = th[:2]
    ang = np.unwrap(np.arctan2(Ub[:, 1] - c[1], Ub[:, 0] - c[0]))
    winding = float((ang[-1] - ang[0]) / (2.0 * np.pi))

    if refuted or not simple:
        verdict = "refuted_not_injective"
    elif not undecided and cells == [] and n_eval < max_cells:
        verdict = "certified_injective_at_bound"
    else:
        verdict = "unresolved"
    return {"verdict": verdict, "cells_evaluated": n_eval, "cells_certified": certified,
            "cells_undecided": len(undecided), "det_refuted": bool(refuted),
            "worst_cell_lower_bound": None if not np.isfinite(worst_lb) else worst_lb,
            "worst_sampled_det": None if not np.isfinite(worst_sampled) else worst_sampled,
            "boundary_simple": bool(simple), "boundary_self_crossings": int(ncross),
            "boundary_winding": winding, "min_cell_px": min_cell_px,
            "argument": "det J > 0 on the closed rectangle plus an injective boundary image implies "
                        "a homeomorphism onto the enclosed Jordan domain (degree-one argument); "
                        "both premises are checked NUMERICALLY here, so the label is "
                        "'certified at the stated bound', not a symbolic proof"}


def _polyline_simple(P, stride=1):
    """Segment-intersection scan for self-crossing of a closed polyline. Returns (is_simple, count)."""
    P = np.asarray(P, float)
    n = len(P)
    A = P[:-1]; B = P[1:]
    cross = 0

    def x2(a, b):
        """2-D cross product. numpy 2 removed the 2-vector form of np.cross."""
        return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]

    def seg_int(p1, p2, p3, p4):
        d1 = x2(p4 - p3, p1 - p3); d2 = x2(p4 - p3, p2 - p3)
        d3 = x2(p2 - p1, p3 - p1); d4 = x2(p2 - p1, p4 - p1)
        return (d1 * d2 < 0) & (d3 * d4 < 0)

    for i in range(0, len(A), stride):
        j0 = i + 2
        if j0 >= len(A):
            continue
        hits = seg_int(A[i], B[i], A[j0:], B[j0:])
        if i == 0:
            hits = hits[:-1]                       # the closing segment legitimately touches the first
        cross += int(np.count_nonzero(hits))
    return cross == 0, cross


def inverse_reliability(th14, w=None, h=None, n_int=25, n_edge=200, unfavourable=True):
    """B. Is the NUMERICAL inverse reliable on this map? Independent of forward validity.

    Compares the shipped `lattice.inv_U` against the continuation reference over dense interior points,
    edges and corners, and (optionally) from deliberately unfavourable Newton seeds. A failure here on a
    map that passes forward certification is an INVERSE-SOLVER failure, not evidence of folding.
    """
    th = np.asarray(th14, float)
    w = FRAME_W if w is None else float(w)
    h = FRAME_H if h is None else float(h)
    inter = _norm_grid(n_int, w, h)
    m = n_edge // 4
    edge = np.vstack([np.stack([np.linspace(0, w, m), np.zeros(m)], 1),
                      np.stack([np.full(m, w), np.linspace(0, h, m)], 1),
                      np.stack([np.linspace(w, 0, m), np.full(m, h)], 1),
                      np.stack([np.zeros(m), np.linspace(h, 0, m)], 1)])
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], float)
    out = {}
    for name, P in (("interior", inter), ("edges", edge), ("corners", corners)):
        Y = LT.U(P, th)
        back, conv, _ = LT.inv_U(Y, th)
        err = np.abs(back - P).max(axis=1)
        ref, rres = robust_inverse(Y, th)
        rerr = np.abs(ref - P).max(axis=1)
        out[name] = {"n": int(len(P)),
                     "shipped_failures": int((err > 1e-6).sum()),
                     "shipped_failure_rate": float((err > 1e-6).mean()),
                     "shipped_max_roundtrip_px": float(err.max()),
                     "reference_failures": int((rerr > 1e-6).sum()),
                     "reference_max_roundtrip_px": float(rerr.max()),
                     "reference_max_forward_residual_px": float(rres.max())}
        if name == "interior" and (err > 1e-6).any():
            bad = P[err > 1e-6]
            out[name]["failure_radius_px"] = [float(np.linalg.norm(bad - th[:2], axis=1).min()),
                                              float(np.linalg.norm(bad - th[:2], axis=1).max())]
    if unfavourable:
        # seed Newton at the far corner regardless of the target: deliberately hostile
        Y = LT.U(inter[:100], th)
        x0 = np.tile(np.array([[w, h]], float), (len(Y), 1))
        back, conv, _ = LT.inv_U(Y, th, x0=x0)
        err = np.abs(back - inter[:100]).max(axis=1)
        out["unfavourable_seed"] = {"n": int(len(Y)),
                                    "shipped_failures": int((err > 1e-6).sum()),
                                    "shipped_max_roundtrip_px": float(err.max())}
    tot = sum(v["shipped_failures"] for k, v in out.items())
    out["summary"] = {"shipped_total_failures": int(tot),
                      "reference_total_failures": int(sum(v.get("reference_failures", 0)
                                                          for v in out.values()
                                                          if isinstance(v, dict))),
                      "verdict": "inverse_reliable" if tot == 0 else "inverse_solver_unreliable"}
    return out


def plausibility_metrics(th14, w=None, h=None, n=41):
    """C. Continuous descriptors of how extreme the correction is. NO pass/fail verdict is implied."""
    th = np.asarray(th14, float)
    w = FRAME_W if w is None else float(w)
    h = FRAME_H if h is None else float(h)
    diag = float(np.hypot(w, h))
    g = _norm_grid(n, w, h)
    J = LT.jac_U(g, th)
    sv = np.linalg.svd(J, compute_uv=False)
    m = 400
    bnd = np.vstack([np.stack([np.linspace(0, w, m), np.zeros(m)], 1),
                     np.stack([np.full(m, w), np.linspace(0, h, m)], 1),
                     np.stack([np.linspace(w, 0, m), np.full(m, h)], 1),
                     np.stack([np.zeros(m), np.linspace(h, 0, m)], 1)])
    Ub = LT.U(bnd, th)
    bw = float(Ub[:, 0].max() - Ub[:, 0].min())
    bh = float(Ub[:, 1].max() - Ub[:, 1].min())
    x, y = Ub[:, 0], Ub[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    Ug = LT.U(g, th)
    outside = float((((Ug[:, 0] < 0) | (Ug[:, 0] > w) | (Ug[:, 1] < 0) | (Ug[:, 1] > h)).mean()))
    disp = np.linalg.norm(Ug - g, axis=1)
    return {"mapped_boundary_width_px": bw, "mapped_boundary_height_px": bh,
            "mapped_boundary_width_ratio": bw / w, "mapped_boundary_height_ratio": bh / h,
            "mapped_area_ratio": area / (w * h),
            "sigma_min": float(np.nanmin(sv[:, 1])), "sigma_max": float(np.nanmax(sv[:, 0])),
            "max_anisotropy": float(np.nanmax(sv[:, 0] / np.maximum(sv[:, 1], 1e-300))),
            "max_displacement_over_diagonal": float(disp.max() / diag),
            "median_displacement_over_diagonal": float(np.median(disp) / diag),
            "expansion_max_over_half_diagonal":
                float(np.linalg.norm(Ub - th[:2], axis=1).max() / (0.5 * diag)),
            "fraction_mapped_outside_frame": outside,
            "frame": [w, h],
            "note": "descriptive only; no plausibility threshold is applied or implied here"}
