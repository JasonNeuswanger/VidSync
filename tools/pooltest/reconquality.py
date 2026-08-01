#!/usr/bin/env python3
"""Reconstruction-quality metrics for coplanar known-coordinate targets. ANALYSIS ONLY.

Nothing here touches production undistortion, model defaults, selection policy or any .vsd. The module
computes metrics; `reconquality_run.py` drives it over documents.

THE ESTIMAND is the paired M1-minus-M0 change on IDENTICAL observations within one recording. Absolute
quality still matters, but ranges, spatial support, segment lengths and target placements differ so much
between recordings that raw errors are not comparable across them.

--------------------------------------------------------------------------------------------------
1. GLOBAL SCALE, and why rigid-Procrustes RMS is redundant

Let N be a cloud's known target coordinates (k, 2) and P its reconstructed 3D points (k, 3), both
mean-centred as Nc, Pc. Rectangular orthogonal Procrustes on A = Pc^T Nc = U S V^T (U is 3x2, V is 2x2)
gives R = U V^T (3x2, orthonormal columns) and

    s = tr(S) / ||Nc||_F^2 ,    E_sim^2 = ||Pc - s Nc R^T||_F^2 ,   E_rigid^2 = ||Pc - Nc R^T||_F^2 .

The cross term of E_rigid^2 is 2(s-1)[tr(S) - s||Nc||_F^2], which vanishes at that s, so exactly

    E_rigid^2 = E_sim^2 + (s-1)^2 * rho_q^2 ,   rho_q^2 = ||Nc||_F^2 = sum_i ||n_i - nbar||^2 .

`similarity_procrustes` returns both energies and rho_q and `verify_scale_identity` checks the identity
numerically, so rigid RMS carries no information beyond E_sim and s and is reported as a derived
quantity only.

REFLECTION IS NOT IDENTIFIABLE FOR A PLANAR SOURCE, and det R = +1 cannot be imposed meaningfully. A 3x2
R with orthonormal columns always completes to a proper rotation via r3 = r1 x r2, and an in-plane
reflection of the target composed with a flip of the plane normal is itself a proper 3D rotation. So the
usual det-correction is vacuous here. What IS testable is whether the data are better explained by a
reflected embedding: `similarity_procrustes` fits both R = U V^T and R = U diag(1,-1) V^T and reports
`reflection_gain`, the fractional reduction in residual the reflected fit would achieve. A large gain
means the target coordinates are mirrored relative to the digitization order.

--------------------------------------------------------------------------------------------------
2. SHAPE BANDS, and in what sense they are orthogonal

Work in the frame (r1, r2, n) with r1, r2 the columns of R and n = r1 x r2, origin at Pc's centroid.
The similarity residual d_i = Pc_i - s Nc_i R^T is expressed in that frame as three scalar fields over
the target coordinates: two TANGENTIAL components d_t1, d_t2 and one NORMAL component d_n.

Each field is regressed on the polynomial basis [1, u, v, u^2, uv, v^2] in the centred target
coordinates, ORTHONORMALIZED BY QR IN THAT ORDER. QR in that order is exactly the residualization the
quadratic terms need: column 4 onward is orthogonal to the constant and linear span, so a bowl reading
cannot be an artefact of an uncentred or tilted target. Because the projections are onto mutually
orthogonal subspaces of one inner-product space, the band energies sum EXACTLY to the total:

    E_sim^2 = sum over the three components of ( linear band + quadratic band + higher residual )

and `verify_band_identity` checks that numerically rather than asserting it. Bands:

    affine_beyond_similarity : tangential components on the LINEAR columns. At the Procrustes optimum
                               the residual's tangential linear part is already orthogonal to the scale
                               and in-plane-rotation directions, so this band is the 2 remaining
                               affine degrees of freedom and nothing else. `affine_purity` reports the
                               leaked scale and rotation coefficients, which should be ~0.
    normal_tilt              : normal component on the LINEAR columns. Also ~0 at the optimum, since
                               fitting R absorbs plane orientation. Reported as a check, not evidence.
    normal_quadratic         : normal component on the QUADRATIC columns, split into BOWL (the isotropic
                               part, trace of the fitted Hessian) and SADDLE (its deviatoric part).
    tangential_quadratic     : tangential components on the QUADRATIC columns, i.e. IN-PLANE warp. Kept
                               strictly separate from normal_quadratic.
    higher_residual          : everything the quadratic model does not explain.

The affine band is reported ONCE, as the singular values of the 2x2 affine-beyond-similarity matrix plus
its principal axis. Anisotropy and shear/nonorthogonality are alternative parameterizations of those
same two degrees of freedom, so reporting both would double-count.

--------------------------------------------------------------------------------------------------
3. LOCAL METRIC ACCURACY on a deterministic graph

Edges come from the KNOWN TARGET COORDINATES only, so the graph is identical for every candidate. The
step is inferred as the smallest positive coordinate difference that recurs, and edges are the target
deltas (step,0), (0,step), (step,step), (step,-step) -- lattice neighbours plus both cell diagonals.
Irregular or missing grids are handled explicitly: `lattice_edges` reports the inferred step, how many
points participate, and falls back to nothing (an empty graph, reported as such) rather than inventing
neighbours. Metrics are signed mean log(D/L), RMS log, p95 |log|, and the physical-unit equivalents.

These edges are NOT independent -- they share endpoints. Their value is bounded, interpretable leverage:
one bad point corrupts at most its own incident edges, whereas in the all-pairs set it corrupts n-1.

ALL-PAIRS results remain descriptive. The all-pairs loss used here is mean |D - L| over unordered pairs
of the raw Euclidean distances; that is NOT the same functional as Procrustes residual energy and no
identity between them is claimed.

--------------------------------------------------------------------------------------------------
4. HELD-OUT RIGID-TARGET REPROJECTION is the primary image-space metric

Genuine leave-one-point-out. For each eligible point: drop it and BOTH its clicks, fit the 6-dof target
pose (translation + rotation vector) to the remaining points' clicks through the candidate's complete
forward model, then forward-project the omitted target coordinate into both cameras and score against
its held-out clicks. No in-sample fit with a degrees-of-freedom multiplier is used anywhere.

Ordinary triangulate-and-reproject residual and ray-miss distance are INTERNAL-CONSISTENCY diagnostics:
they reuse the same clicks they are scored against. They are labelled as such and never presented as
external validation.
"""

import math

import numpy as np
from scipy.optimize import least_squares

import harness_import

LT = harness_import.load("lattice")
DS = harness_import.load("downstream")


# ============================================================== 1. global scale


def similarity_procrustes(N, P):
    """Similarity Procrustes of target coords N (k,2) onto reconstruction P (k,3). See module docstring."""
    N = np.asarray(N, float).reshape(len(N), -1)
    P = np.asarray(P, float).reshape(len(P), -1)
    Nc, Pc = N - N.mean(0), P - P.mean(0)
    rho_q2 = float((Nc ** 2).sum())
    A = Pc.T @ Nc
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    out = {}
    for tag, D in (("proper", np.eye(len(S))), ("reflected", np.diag([1.0] + [-1.0] * (len(S) - 1)))):
        R = U @ D @ Vt
        s = float((np.diag(D) * S).sum() / rho_q2) if rho_q2 > 0 else float("nan")
        Esim2 = float(((Pc - s * (Nc @ R.T)) ** 2).sum())
        out[tag] = {"R": R, "s": s, "Esim2": Esim2,
                    "Erigid2": float(((Pc - (Nc @ R.T)) ** 2).sum())}
    prop, refl = out["proper"], out["reflected"]
    gain = (1.0 - refl["Esim2"] / prop["Esim2"]) if prop["Esim2"] > 0 else 0.0
    k = len(N)
    return {"k": k, "R": prop["R"], "s": prop["s"], "s_minus_1": prop["s"] - 1.0,
            "log_s": float(math.log(prop["s"])) if prop["s"] > 0 else float("nan"),
            "Esim2": prop["Esim2"], "Erigid2": prop["Erigid2"], "rho_q2": rho_q2,
            "rms_sim_mm": float(math.sqrt(prop["Esim2"] / k)),
            "rms_rigid_mm": float(math.sqrt(prop["Erigid2"] / k)),
            "reflection_gain": float(gain),
            "reflection_suspected": bool(gain > 0.5),
            "centroid_N": N.mean(0), "centroid_P": P.mean(0)}


def verify_scale_identity(sp, tol=1e-8):
    """E_rigid^2 == E_sim^2 + (s-1)^2 rho_q^2, checked rather than assumed."""
    lhs = sp["Erigid2"]
    rhs = sp["Esim2"] + (sp["s"] - 1.0) ** 2 * sp["rho_q2"]
    denom = max(abs(lhs), 1e-30)
    return {"lhs": lhs, "rhs": rhs, "abs_err": abs(lhs - rhs),
            "rel_err": abs(lhs - rhs) / denom, "holds": bool(abs(lhs - rhs) / denom < tol)}


# ============================================================== 2. shape bands


def _poly_basis(uv):
    u, v = uv[:, 0], uv[:, 1]
    return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=1)


def shape_bands(N, P, sp=None):
    """Orthogonal band decomposition of the similarity residual. See module docstring section 2."""
    sp = sp or similarity_procrustes(N, P)
    N = np.asarray(N, float); P = np.asarray(P, float)
    Nc, Pc = N - N.mean(0), P - P.mean(0)
    R, s = sp["R"], sp["s"]
    r1, r2 = R[:, 0], R[:, 1]
    n = np.cross(r1, r2)
    n = n / (np.linalg.norm(n) or 1.0)
    d = Pc - s * (Nc @ R.T)                                   # (k,3) similarity residual
    comp = {"t1": d @ r1, "t2": d @ r2, "n": d @ n}            # scalar fields
    X = _poly_basis(Nc)
    Q, _ = np.linalg.qr(X)                                     # QR in [1,u,v,u2,uv,v2] order
    rank = np.linalg.matrix_rank(X)
    Q = Q[:, :rank]
    idx_const = [0] if rank > 0 else []
    idx_lin = [i for i in (1, 2) if i < rank]
    idx_quad = [i for i in (3, 4, 5) if i < rank]

    def energy(f, cols):
        if not cols:
            return 0.0, np.zeros_like(f)
        c = Q[:, cols].T @ f
        fit = Q[:, cols] @ c
        return float((c ** 2).sum()), fit

    bands, fits = {}, {}
    for name, f in comp.items():
        e_c, fc = energy(f, idx_const)
        e_l, fl = energy(f, idx_lin)
        e_q, fq = energy(f, idx_quad)
        resid = f - fc - fl - fq
        e_h = float((resid ** 2).sum())
        bands[name] = {"const": e_c, "linear": e_l, "quadratic": e_q, "higher": e_h,
                       "total": float((f ** 2).sum())}
        fits[name] = {"linear": fl, "quadratic": fq, "higher": resid}

    total = sp["Esim2"]
    out = {"total_Esim2": total,
           "affine_beyond_similarity": bands["t1"]["linear"] + bands["t2"]["linear"],
           "normal_tilt": bands["n"]["linear"],
           "normal_quadratic": bands["n"]["quadratic"],
           "tangential_quadratic": bands["t1"]["quadratic"] + bands["t2"]["quadratic"],
           "higher_residual": bands["t1"]["higher"] + bands["t2"]["higher"] + bands["n"]["higher"],
           "constant_leak": bands["t1"]["const"] + bands["t2"]["const"] + bands["n"]["const"],
           "per_component": bands}
    out["band_sum"] = (out["affine_beyond_similarity"] + out["normal_tilt"]
                       + out["normal_quadratic"] + out["tangential_quadratic"]
                       + out["higher_residual"] + out["constant_leak"])

    # ---- affine-beyond-similarity, reported ONCE as the 2x2 matrix's invariants
    G = np.linalg.pinv(np.stack([Nc[:, 0], Nc[:, 1]], axis=1))
    M = np.stack([G @ comp["t1"], G @ comp["t2"]], axis=0)      # (2,2): d_t = M @ (u,v)
    sym = 0.5 * (M + M.T); asym = 0.5 * (M - M.T)
    dev = sym - 0.5 * np.trace(sym) * np.eye(2)
    sv = np.linalg.svd(M, compute_uv=False)
    w, V = np.linalg.eigh(dev)
    out["affine"] = {
        "matrix": M.tolist(), "singular_values": sv.tolist(),
        "leaked_isotropic_scale": float(0.5 * np.trace(sym)),
        "leaked_rotation": float(asym[0, 1]),
        "anisotropy_magnitude": float(np.linalg.norm(dev, ord="fro")),
        "principal_axis_deg": float(math.degrees(math.atan2(V[1, -1], V[0, -1])) % 180.0),
        "note": "singular values and the deviatoric norm are the SAME two degrees of freedom as any "
                "anisotropy-plus-shear parameterization; they are not separate evidence"}
    out["affine_purity"] = {"isotropic_leak": out["affine"]["leaked_isotropic_scale"],
                            "rotation_leak": out["affine"]["leaked_rotation"]}

    # ---- normal quadratic: bowl (isotropic) versus saddle (deviatoric)
    Xq = np.stack([Nc[:, 0] ** 2, Nc[:, 0] * Nc[:, 1], Nc[:, 1] ** 2], axis=1)
    Xr = Xq - _poly_basis(Nc)[:, :3] @ np.linalg.pinv(_poly_basis(Nc)[:, :3]) @ Xq
    cq = np.linalg.pinv(Xr) @ comp["n"]
    H = np.array([[2 * cq[0], cq[1]], [cq[1], 2 * cq[2]]])
    devH = H - 0.5 * np.trace(H) * np.eye(2)
    wH, VH = np.linalg.eigh(devH)
    out["normal_curvature"] = {
        "hessian": H.tolist(),
        "bowl_mean_curvature": float(0.5 * np.trace(H)),
        "saddle_magnitude": float(np.linalg.norm(devH, ord="fro")),
        "saddle_axis_deg": float(math.degrees(math.atan2(VH[1, -1], VH[0, -1])) % 180.0),
        "basis": "quadratic columns residualized against [1,u,v] before fitting"}
    return out


def verify_band_identity(sb, tol=1e-8):
    lhs, rhs = sb["total_Esim2"], sb["band_sum"]
    denom = max(abs(lhs), 1e-30)
    return {"lhs": lhs, "rhs": rhs, "abs_err": abs(lhs - rhs),
            "rel_err": abs(lhs - rhs) / denom, "holds": bool(abs(lhs - rhs) / denom < tol)}


# ============================================================== plane residuals


def plane_residuals(P, extent_mm):
    """Best-fit-plane signed residuals: a VIEW of the out-of-plane band, not an extra vote."""
    P = np.asarray(P, float)
    c = P.mean(0)
    _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    nrm = Vt[-1]
    d = (P - c) @ nrm
    a = np.abs(d)
    return {"signed": d.tolist(), "rms_mm": float(math.sqrt((d ** 2).mean())),
            "p95_abs_mm": float(np.percentile(a, 95)), "max_abs_mm": float(a.max()),
            "rms_over_extent": float(math.sqrt((d ** 2).mean()) / extent_mm) if extent_mm else
            float("nan"),
            "extent_mm": float(extent_mm)}


# ============================================================== 3. lattice graph


def lattice_edges(N, tol=1e-6):
    """Deterministic edge set from the KNOWN target coordinates: neighbours plus both cell diagonals."""
    N = np.asarray(N, float)
    k = len(N)
    diffs = []
    for i in range(k):
        for j in range(i + 1, k):
            diffs.append(np.abs(N[j] - N[i]))
    diffs = np.array(diffs) if diffs else np.zeros((0, 2))
    pos = diffs[diffs > tol] if diffs.size else np.zeros(0)
    if pos.size == 0:
        return {"step_mm": None, "edges": [], "n_points_used": 0,
                "rule": "no positive coordinate difference exists; empty graph reported rather than "
                        "inventing neighbours"}
    vals, counts = np.unique(np.round(pos, 6), return_counts=True)
    step = float(vals[0])
    for v, c in zip(vals, counts):
        if c >= max(2, 0.05 * len(pos)):
            step = float(v)
            break
    want = [(step, 0.0), (0.0, step), (step, step), (step, -step)]
    edges = []
    for i in range(k):
        for j in range(i + 1, k):
            dl = N[j] - N[i]
            for w in want:
                if abs(abs(dl[0]) - abs(w[0])) < tol and abs(abs(dl[1]) - abs(w[1])) < tol:
                    if abs(w[0]) > tol and abs(w[1]) > tol and (dl[0] * dl[1]) * (w[0] * w[1]) < 0:
                        continue
                    edges.append((i, j, float(np.linalg.norm(dl)),
                                  "diagonal" if abs(w[0]) > tol and abs(w[1]) > tol else "neighbour"))
                    break
    used = len({i for i, _, _, _ in edges} | {j for _, j, _, _ in edges})
    return {"step_mm": step, "edges": edges, "n_points_used": used, "n_edges": len(edges),
            "rule": f"target deltas (s,0),(0,s),(s,s),(s,-s) with s = {step:g} mm inferred as the "
                    f"smallest recurring positive coordinate difference"}


def edge_metrics(N, P, graph=None):
    graph = graph or lattice_edges(N)
    P = np.asarray(P, float)
    if not graph["edges"]:
        return {"n_edges": 0, "graph": graph}
    lg, ph = [], []
    per = []
    for i, j, L, kind in graph["edges"]:
        Dm = float(np.linalg.norm(P[j] - P[i]))
        lg.append(math.log(Dm / L)); ph.append(Dm - L)
        per.append({"i": i, "j": j, "kind": kind, "true_mm": L, "meas_mm": Dm,
                    "err_mm": Dm - L, "log_ratio": math.log(Dm / L)})
    lg = np.array(lg); ph = np.array(ph)
    return {"n_edges": len(lg), "graph": {k: v for k, v in graph.items() if k != "edges"},
            "signed_mean_log": float(lg.mean()), "rms_log": float(math.sqrt((lg ** 2).mean())),
            "p95_abs_log": float(np.percentile(np.abs(lg), 95)),
            "signed_mean_mm": float(ph.mean()), "rms_mm": float(math.sqrt((ph ** 2).mean())),
            "p95_abs_mm": float(np.percentile(np.abs(ph), 95)),
            "max_abs_mm": float(np.abs(ph).max()), "per_edge": per,
            "independence_note": "edges share endpoints and are NOT independent; the claim is bounded "
                                 "leverage (one bad point touches only its incident edges), not "
                                 "independence"}


def all_pairs_descriptive(N, P):
    """Descriptive only. Loss is mean |D - L| over unordered pairs of raw Euclidean distances."""
    N = np.asarray(N, float); P = np.asarray(P, float)
    e = []
    for i in range(len(N)):
        for j in range(i + 1, len(N)):
            L = float(np.linalg.norm(N[j] - N[i]))
            if L <= 0:
                continue
            e.append(float(np.linalg.norm(P[j] - P[i])) - L)
    e = np.array(e)
    return {"n_pairs": int(e.size), "mae_mm": float(np.abs(e).mean()) if e.size else float("nan"),
            "bias_mm": float(e.mean()) if e.size else float("nan"),
            "loss": "mean |D - L| over unordered pairs; NOT identical to Procrustes residual energy"}


# ============================================================== 4. held-out reprojection


def _rot(rv):
    th = float(np.linalg.norm(rv))
    if th < 1e-12:
        return np.eye(3)
    k = rv / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)


def _pose_world(p, N):
    """6-dof pose -> world points: X_i = t + u_i a1 + v_i a2 with (a1,a2) the first two rotation axes."""
    Rm = _rot(np.asarray(p[3:6], float))
    return np.asarray(p[0:3], float)[None, :] + N @ Rm[:, :2].T


def _corrected(cam, xy):
    return np.array(cam["dmap"].forward_xy(xy[0], xy[1]), float)


def heldout_reprojection(N, clicks_by_index, cams, clips, seed_P=None):
    """Genuine LOPO rigid-target reprojection. See module docstring section 4.

    `clicks_by_index[i][clip]` is the raw click for target point i in that camera. Returns per-point
    held-out image residuals in raw pixels and in corrected pixels, decomposed radially/tangentially
    about each camera's distortion centre and along the local epipolar curve where computable.
    """
    N = np.asarray(N, float)
    k = len(N)
    eligible = [i for i in range(k) if all(c in clicks_by_index[i] for c in clips)]

    def resid_pose(p, use):
        X = _pose_world(p, N[use])
        out = []
        for a, i in enumerate(use):
            for c in clips:
                pr = DS.reproject(X[a], cams[c])
                obs = _corrected(cams[c], clicks_by_index[i][c])
                out += [1e3, 1e3] if pr is None else [pr[0] - obs[0], pr[1] - obs[1]]
        return np.array(out)

    def seed(use):
        if seed_P is not None:
            sp = similarity_procrustes(N[use], np.asarray(seed_P)[use])
            R = sp["R"]
            r3 = np.cross(R[:, 0], R[:, 1])
            M = np.stack([R[:, 0], R[:, 1], r3 / (np.linalg.norm(r3) or 1.0)], axis=1)
            w, V = np.linalg.eig(M)
            ax = np.real(V[:, np.argmin(np.abs(w - 1))])
            ax = ax / (np.linalg.norm(ax) or 1.0)
            ang = math.acos(max(-1.0, min(1.0, (np.trace(M) - 1) / 2)))
            t = np.asarray(seed_P)[use].mean(0) - (N[use].mean(0) @ M[:, :2].T)
            return np.concatenate([t, ax * ang])
        return np.zeros(6)

    rows = []
    for i in eligible:
        use = [j for j in eligible if j != i]
        if len(use) < 4:
            continue
        r = least_squares(resid_pose, seed(use), args=(use,), method="lm",
                          xtol=1e-12, ftol=1e-12, max_nfev=8000)
        X_out = _pose_world(r.x, N[[i]])[0]
        rec = {"index": i, "pose_cost": float(r.cost), "pose_nfev": int(r.nfev),
               "n_pose_points": len(use), "cameras": {}}
        for c in clips:
            pr = DS.reproject(X_out, cams[c])
            if pr is None:
                continue
            obs_c = _corrected(cams[c], clicks_by_index[i][c])
            dc = np.array([pr[0] - obs_c[0], pr[1] - obs_c[1]], float)
            raw, conv, _ = cams[c]["dmap"].inverse(np.array([pr]))
            obs_raw = np.asarray(clicks_by_index[i][c], float)
            dr = (raw[0] - obs_raw) if bool(np.all(conv)) else np.array([np.nan, np.nan])
            ctr = np.asarray(cams[c]["dmap"].centre, float)
            rv = obs_raw - ctr
            rn = np.linalg.norm(rv)
            rhat = rv / rn if rn > 0 else np.array([1.0, 0.0])
            that = np.array([-rhat[1], rhat[0]])
            ep = _epipolar_tangent(X_out, cams, clips, c, obs_raw)
            rec["cameras"][c] = {
                "px_raw": [float(v) for v in dr], "px_raw_norm": float(np.linalg.norm(dr)),
                "px_corrected": [float(v) for v in dc],
                "px_corrected_norm": float(np.linalg.norm(dc)),
                "radial_px": float(dr @ rhat) if np.all(np.isfinite(dr)) else float("nan"),
                "tangential_px": float(dr @ that) if np.all(np.isfinite(dr)) else float("nan"),
                "epipolar_tangent_px": (float(dr @ ep) if ep is not None
                                        and np.all(np.isfinite(dr)) else float("nan")),
                "epipolar_normal_px": (float(dr @ np.array([-ep[1], ep[0]]))
                                       if ep is not None and np.all(np.isfinite(dr))
                                       else float("nan")),
                "inverse_converged": bool(np.all(conv)),
                "image_radius_px": float(rn)}
        rows.append(rec)
    per_cam = {}
    for c in clips:
        v = np.array([r["cameras"][c]["px_raw_norm"] for r in rows if c in r["cameras"]
                      and np.isfinite(r["cameras"][c]["px_raw_norm"])])
        per_cam[c] = ({"n": int(v.size), "rms_px": float(math.sqrt((v ** 2).mean())),
                       "p95_px": float(np.percentile(v, 95)), "max_px": float(v.max()),
                       "median_px": float(np.median(v))} if v.size else {"n": 0})
    return {"n_eligible": len(eligible), "n_scored": len(rows), "per_camera": per_cam,
            "per_point": rows,
            "method": "leave-one-point-out: the point and BOTH its clicks are withheld, the 6-dof "
                      "target pose is refit from the remaining points through the candidate's complete "
                      "forward model, and the withheld coordinate is forward-projected and scored. No "
                      "in-sample fit with a dof multiplier is used."}


def _epipolar_tangent(X, cams, clips, cam_key, obs_raw, delta=None):
    """Local tangent of this camera's image curve traced by depth along the OTHER camera's sightline."""
    others = [c for c in clips if c != cam_key]
    if not others:
        return None
    o = others[0]
    try:
        p, q = DS.sightline(*np.asarray(obs_raw, float)[:2], cams[o]) if False else (None, None)
    except Exception:                                                        # noqa: BLE001
        pass
    # Move X along the ray from the other camera's centre through X, and see how this camera's image
    # coordinate responds. That curve is the epipolar curve for a non-pinhole forward model.
    C = np.asarray(cams[o]["cam"], float)
    v = np.asarray(X, float) - C
    nv = np.linalg.norm(v)
    if nv == 0:
        return None
    v = v / nv
    h = delta or max(1e-3, 1e-4 * nv)
    a, b = DS.reproject(np.asarray(X) - h * v, cams[cam_key]), \
        DS.reproject(np.asarray(X) + h * v, cams[cam_key])
    if a is None or b is None:
        return None
    ra, ca, _ = cams[cam_key]["dmap"].inverse(np.array([a]))
    rb, cb, _ = cams[cam_key]["dmap"].inverse(np.array([b]))
    if not (np.all(ca) and np.all(cb)):
        return None
    d = rb[0] - ra[0]
    n = np.linalg.norm(d)
    return (d / n) if n > 0 else None


def internal_consistency(clicks_by_index, cams, clips, eligible):
    """Triangulate-and-reproject residual and ray-miss. INTERNAL DIAGNOSTIC, not external validation."""
    rows = []
    for i in eligible:
        obs = [(cams[c], clicks_by_index[i][c]) for c in clips if c in clicks_by_index[i]]
        if len(obs) < 2:
            continue
        t = DS.triangulate_lm(obs)
        rows.append({"index": i, "X": t["X"].tolist(), "reproject_rms_px": float(t["rep"]),
                     "ray_miss_mm": float(t["pld"])})
    rp = np.array([r["reproject_rms_px"] for r in rows])
    rm = np.array([r["ray_miss_mm"] for r in rows])
    return {"per_point": rows,
            "reproject_rms_px": {"median": float(np.median(rp)), "max": float(rp.max())}
            if rp.size else {},
            "ray_miss_mm": {"median": float(np.median(rm)), "max": float(rm.max())}
            if rm.size else {},
            "label": "INTERNAL CONSISTENCY ONLY: these reuse the very clicks they are scored against, "
                     "so they cannot validate the model externally. The held-out rigid-target "
                     "prediction is the primary image-space metric."}


# ============================================================== per-cloud panel


def cloud_panel(N, P, clicks_by_index=None, cams=None, clips=None, do_heldout=True):
    """Every primary metric for one cloud under one candidate."""
    N = np.asarray(N, float); P = np.asarray(P, float)
    sp = similarity_procrustes(N, P)
    sb = shape_bands(N, P, sp)
    extent = float(np.linalg.norm(N.max(0) - N.min(0)))
    panel = {
        "k": len(N),
        "scale": {"s": sp["s"], "s_minus_1": sp["s_minus_1"], "log_s": sp["log_s"],
                  "reflection_gain": sp["reflection_gain"],
                  "reflection_suspected": sp["reflection_suspected"]},
        "shape": {"rms_sim_mm": sp["rms_sim_mm"], "Esim2": sp["Esim2"],
                  "rms_rigid_mm_derived": sp["rms_rigid_mm"],
                  "bands": {k: v for k, v in sb.items()
                            if k in ("affine_beyond_similarity", "normal_tilt", "normal_quadratic",
                                     "tangential_quadratic", "higher_residual", "constant_leak",
                                     "band_sum", "total_Esim2")},
                  "affine": sb["affine"], "normal_curvature": sb["normal_curvature"],
                  "affine_purity": sb["affine_purity"]},
        "plane": plane_residuals(P, extent),
        "edges": edge_metrics(N, P),
        "all_pairs_descriptive": all_pairs_descriptive(N, P),
        "identities": {"scale": verify_scale_identity(sp), "bands": verify_band_identity(sb)},
        "target_extent_mm": extent}
    if do_heldout and clicks_by_index is not None and cams is not None:
        panel["heldout"] = heldout_reprojection(N, clicks_by_index, cams, clips, seed_P=P)
        panel["internal_consistency"] = internal_consistency(
            clicks_by_index, cams, clips, list(range(len(N))))
    return panel
