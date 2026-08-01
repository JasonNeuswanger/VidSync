#!/usr/bin/env python3
"""M1 identifiability, the plumbline gauge, and a candidate-comparable held-out score. ANALYSIS ONLY.

======================================================================================================
THE EXACT MAP AND PARAMETERIZATION

theta14 = (x0, y0, k1..k7, p1, p2, p3, p4, eta), indices 0..13. lattice.U implements

    U(x) = A^-1 B( A (x - c) ),      c = (x0, y0),      A = diag(e^eta, e^-eta),   det A = 1

with B the 13-parameter Brown-Conrady undistortion: radial R(s) = 1 + sum_i k_i s^i for i = 1..7 on
s = xd^2 + yd^2, plus the tangential term with p1, p2 and its own scaling T(s) = 1 + p3 s + p4 s^2.
The free set actually fitted is M0_FREE = (x0, y0, k1, k2, k3, k4, p1, p2) -- 8 parameters -- and
M1_FREE = M0_FREE + (eta), so 9. k5..k7 and p3, p4 are held at zero.

THE ANISOTROPY HAS ONE DEGREE OF FREEDOM, NOT TWO. Writing A = exp(S) with

    S = [[a, b], [b, -a]]

the implemented A = diag(e^eta, e^-eta) is exp(S) with a = eta and b IDENTICALLY ZERO. So:

    a = eta,   b = 0 by construction,   ||S||_F = sqrt(2 a^2 + 2 b^2) = |eta| sqrt(2),
    axial orientation = 0 deg (equivalently 90 deg), FIXED to the image axes.

The consequence matters for the earlier injection study. A scalar signed-eta injection IS the complete
sweep of this model's anisotropy space, because that space is one-dimensional. But it is NOT an
orientation-recovery study, and it cannot be: the model has no parameter that can place the anisotropy
axis anywhere other than along x/y. A physical anisotropy at 45 degrees is, in this parameterization,
exactly the b direction and is structurally inexpressible. `axis_sweep` below injects true anisotropy
at a range of orientations and measures what the eta-only model does with it.

======================================================================================================
THE GAUGE RESULT

The plumbline objective is a function only of the COLLINEARITY of the undistorted points. Any constant
invertible linear map takes straight lines to straight lines, so for fixed invertible M the sets
{U(x_i)} and {M U(x_i)} are collinear together. In this parameterization eta appears twice: as the outer
A^-1 and as the inner A. The outer factor is exactly such a constant map, therefore

    THE OUTER A^-1 IS AN EXACT GAUGE OF THE PLUMBLINE OBJECTIVE: it cannot change the straightness cost
    at all.

Hence eta influences the plumbline objective ONLY through the inner A, whose effect is to make the
radial argument elliptical. To first order in eta, with X = x - x0 and Y = y - y0,

    s = (X e^eta)^2 + (Y e^-eta)^2 = r^2 + 2 eta (X^2 - Y^2) + O(eta^2),   r^2 = X^2 + Y^2,

so the radial correction acquires a cos(2 phi) angular modulation. Purely radial terms are isotropic and
cannot produce cos(2 phi), which is what makes eta identifiable in principle. But the tangential terms
DO carry cos(2 phi) and sin(2 phi) content -- Gx = p1(3X^2 + Y^2) + 2 p2 X Y, Gy = 2 p1 X Y +
p2(X^2 + 3Y^2) -- so eta is structurally coupled to (p1, p2). `gauge_and_identifiability` measures that
coupling numerically on noiseless lines rather than asserting a conclusion from the algebra.

======================================================================================================
WHY THE OLD HELD-OUT SCORE WAS NOT CANDIDATE-COMPARABLE

The previous CV score was the RMS orthogonal deviation of the held-out line IN EACH CANDIDATE'S OWN
UNDISTORTED COORDINATES. Those coordinate systems differ between candidates by exactly the outer A^-1,
which compresses one image axis by e^-eta and expands the other by e^+eta. If a line's residual scatter
lies mainly along the compressed axis, the score falls for a reason that has nothing to do with fit
quality -- and since the outer factor is a pure gauge, straightness itself has not changed at all.
Normalizing by the frame diagonal does not help: it is one global constant applied to both candidates
and does not make the two metrics common. `old_score_bias` demonstrates the preference directly.

THE COMMON-SPACE SCORE. Nuisances are the held-out ideal line (2 parameters) and each observation's
unknown along-line coordinate t_i. The ideal line is forward-projected through the candidate model back
into the ORIGINAL DISTORTED PIXEL SPACE, and the loss is the sum of squared shortest distances there,
under the same assumed isotropic click covariance for both candidates:

    L = sum_i || raw_i - U^-1( p + t_i d ) ||^2 ,   minimized over (p, d, {t_i}),

which is the held-out raw-pixel negative log likelihood up to the additive constant of a common sigma.
Both candidates are scored in the same fixed pixel space, so no coordinate change can be rewarded.
"""

import math

import numpy as np
from scipy.optimize import least_squares

import harness_import

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")


def anisotropy_report(eta):
    """a, b, magnitude and axis for the implemented one-parameter anisotropy."""
    return {"a": float(eta), "b": 0.0, "b_is_structural_zero": True,
            "S_frobenius_norm": float(abs(eta) * math.sqrt(2.0)),
            "axis_deg": 0.0, "axis_is_fixed_to_image_axes": True,
            "degrees_of_freedom": 1,
            "note": "A = diag(e^eta, e^-eta) = exp(S) with S = [[eta,0],[0,-eta]]. The b (45-degree) "
                    "component of a general trace-free symmetric anisotropy is not representable."}


# ============================================================== gauge and identifiability


def synth_lines(theta_truth, n_lines=24, n_pts=12, margin=90.0, seed=7):
    """Noiseless lines that are exactly straight in the UNDISTORTED plane, spanning many orientations."""
    rng = np.random.default_rng(seed)
    W, H = LT.FRAME_W, LT.FRAME_H
    raws, ideals = [], []
    for li in range(n_lines):
        ang = math.pi * li / n_lines
        d = np.array([math.cos(ang), math.sin(ang)])
        c = np.array([W / 2, H / 2]) + rng.uniform(-0.35, 0.35, 2) * np.array([W, H])
        L = 0.45 * math.hypot(W, H)
        t = np.linspace(-L / 2, L / 2, n_pts)
        ideal = c[None, :] + np.outer(t, d)
        raw, conv, _ = LT.inv_U(ideal, np.asarray(theta_truth, float))
        if not np.all(conv):
            continue
        keep = ((raw[:, 0] > margin) & (raw[:, 0] < W - margin)
                & (raw[:, 1] > margin) & (raw[:, 1] < H - margin))
        if keep.sum() < 6:
            continue
        raws.append(raw[keep]); ideals.append(ideal[keep])
    return raws, ideals


def straightness_sse(raws, theta):
    """Sum of squared orthogonal deviations in the candidate's own undistorted plane (the OLD score)."""
    tot, n = 0.0, 0
    for r in raws:
        u = LT.U(r, np.asarray(theta, float))
        if not np.all(np.isfinite(u)):
            return float("inf"), 0
        A = u - u.mean(0)
        _, _, Vt = np.linalg.svd(A, full_matrices=False)
        dv = A @ Vt[-1]
        tot += float((dv ** 2).sum()); n += len(dv)
    return tot, n


def gauge_check(theta, raws):
    """Numerically confirm the outer A^-1 is an exact gauge: drop it and the straightness cost is equal."""
    th = np.asarray(theta, float)
    eta = float(th[13])
    A_inv = np.diag([math.exp(-eta), math.exp(eta)])
    same = []
    for r in raws:
        u = LT.U(r, th)                                     # = A^-1 B(A(x-c))
        v = u @ np.linalg.inv(A_inv).T                      # undo the outer factor -> B(A(x-c))
        out = []
        for w in (u, v):
            Aw = w - w.mean(0)
            _, _, Vt = np.linalg.svd(Aw, full_matrices=False)
            dv = Aw @ Vt[-1]
            out.append(float(math.sqrt((dv ** 2).mean())))
        same.append((out[0], out[1]))
    a = np.array([s[0] for s in same]); b = np.array([s[1] for s in same])
    # Straightness is scale-covariant, so compare the RATIO across lines: a gauge gives a CONSTANT ratio.
    ratio = b / np.maximum(a, 1e-300)
    return {"n_lines": len(same),
            "collinearity_preserved": True,
            "rms_ratio_mean": float(ratio.mean()), "rms_ratio_sd": float(ratio.std()),
            "ratio_is_constant_across_lines": bool(ratio.std() / max(ratio.mean(), 1e-30) < 1e-6),
            "interpretation": "removing the outer A^-1 rescales every line's deviation by ONE common "
                              "factor, so it cannot change which candidate looks straighter: the outer "
                              "factor is an exact gauge of collinearity"}


def scaled_information(D, theta, model="M1"):
    """Dimensionless local information: singular values of the COLUMN-SCALED Jacobian.

    A raw J'J condition number on unscaled columns mixes pixels with per-pixel^2 coefficients and is not
    interpretable; each column is therefore normalized to unit Euclidean norm before the SVD.
    """
    fr = OB.MODELS[model]
    pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                 nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="B", free=fr)
    p0 = np.zeros(pk.n)
    p0[:pk.nm] = np.asarray(theta, float)[fr] / OB.SCALE14[fr]
    base = OB.default_base()

    def rr(p):
        return OB.resid_B(p, D, pk, base)
    r0 = rr(p0)
    J = np.zeros((len(r0), pk.nm))
    for j in range(pk.nm):
        h = 1e-6 * max(1.0, abs(p0[j]))
        pp = p0.copy(); pp[j] += h
        J[:, j] = (rr(pp) - r0) / h
    nrm = np.linalg.norm(J, axis=0)
    keep = nrm > 0
    Js = J[:, keep] / nrm[keep]
    sv = np.linalg.svd(Js, compute_uv=False)
    idx = [i for i, f in enumerate(np.array(fr)[keep]) if f == 13]
    ie = idx[0] if idx else None
    out = {"scaled_singular_values": sv.tolist(),
           "scaled_condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf"),
           "n_free_scaled": int(keep.sum()),
           "note": "columns normalized to unit norm before the SVD; the raw J'J condition number of the "
                   "unscaled parameterization is not reported because it is not interpretable"}
    if ie is not None:
        # eta's own identifiability: the norm of its column AFTER projecting out the other columns.
        Q, _ = np.linalg.qr(np.delete(Js, ie, axis=1))
        e = Js[:, ie]
        resid = e - Q @ (Q.T @ e)
        out["eta_partial_information_fraction"] = float(np.linalg.norm(resid) / max(
            np.linalg.norm(e), 1e-300))
        out["eta_collinearity_with_others"] = float(math.sqrt(max(
            0.0, 1.0 - out["eta_partial_information_fraction"] ** 2)))
    return out


def profile_consistency(D, theta_m1, n=9):
    """Refit the 8 M0 parameters at fixed eta on a grid, and CHECK the profile reproduces the M1 loss.

    A profile whose value at eta = eta_hat disagrees with the M1 fit's own loss is a computational
    inconsistency, not a finding, and negative curvature there would be a symptom of it. This routine
    reports the discrepancy explicitly so "non-convex at the optimum" can be diagnosed rather than
    asserted.
    """
    th = np.asarray(theta_m1, float)
    e0 = float(th[13])
    span = max(2e-3, abs(e0) * 0.6)
    grid = np.sort(np.concatenate([np.linspace(e0 - span, e0 + span, n), [e0]]))
    rows = []
    for e in grid:
        base = OB.default_base()
        base[13] = float(e)
        r = OB.fit(D, "B", "M0", base=base, warm=False, max_nfev=2000, zero_held=False)
        rows.append({"eta": float(e), "loss": float(r["loss"]), "status": int(r["status"])})
    at = [r for r in rows if abs(r["eta"] - e0) < 1e-15]
    # the M1 fit's own loss at its optimum, for the consistency comparison
    fr = OB.MODELS["M1"]
    r1 = OB.fit(D, "B", "M1", x0_model=th[fr] / OB.SCALE14[fr], warm=False, max_nfev=3000)
    l1 = float(r1["loss"])
    lo = at[0]["loss"] if at else float("nan")
    ls = np.array([r["loss"] for r in rows]); gs = np.array([r["eta"] for r in rows])
    c = np.polyfit(gs, ls, 2)
    argmin = float(gs[int(np.argmin(ls))])
    return {"grid": rows, "eta_hat": e0, "profile_loss_at_eta_hat": lo, "m1_fit_loss": l1,
            "profile_minus_m1_loss": lo - l1,
            "profile_reproduces_m1_loss": bool(abs(lo - l1) <= 1e-6 * max(abs(l1), 1.0)),
            "quadratic_curvature": float(2 * c[0]),
            "grid_argmin_eta": argmin,
            "argmin_at_eta_hat": bool(abs(argmin - e0) <= (gs[1] - gs[0]) * 0.51),
            "diagnosis": ("consistent: the profile reproduces the M1 loss at eta_hat and is minimized "
                          "there" if (abs(lo - l1) <= 1e-6 * max(abs(l1), 1.0)
                                     and abs(argmin - e0) <= (gs[1] - gs[0]) * 0.51)
                          else "INCONSISTENT: the eta-profile does not reproduce the M1 fit at "
                               "eta_hat, so any curvature sign read off it is a computational artefact "
                               "and not a statement about the objective")}


# ============================================================== common-space score


def common_space_sse(raw, theta, sigma_px=1.0, seed_line=None):
    """Held-out raw-pixel loss: nuisance ideal line plus per-point along-line coordinates.

    Minimizes sum_i || raw_i - U^-1( p + t_i d ) ||^2 over the line (p, d) and all t_i. Scored in the
    ORIGINAL distorted pixel space, identically for every candidate, so no candidate-induced coordinate
    change can be rewarded. Returns the SSE and the equivalent per-point RMS in raw pixels; dividing by
    2 sigma^2 gives the negative log likelihood up to a constant common to both candidates.
    """
    raw = np.asarray(raw, float)
    th = np.asarray(theta, float)
    k = len(raw)
    u = LT.U(raw, th)
    if not np.all(np.isfinite(u)):
        return {"sse": float("inf"), "rms_px": float("inf"), "converged": False}
    c0 = u.mean(0)
    A = u - c0
    _, _, Vt = np.linalg.svd(A, full_matrices=False)
    d0 = Vt[0]
    t0 = A @ d0
    p0 = np.concatenate([c0, [math.atan2(d0[1], d0[0])], t0])

    def resid(p):
        c = p[0:2]; ang = p[2]; t = p[3:]
        d = np.array([math.cos(ang), math.sin(ang)])
        ideal = c[None, :] + np.outer(t, d)
        back, conv, _ = LT.inv_U(ideal, th)
        if not np.all(conv) or not np.all(np.isfinite(back)):
            return np.full(2 * k, 1e6)
        return (back - raw).ravel()

    r = least_squares(resid, p0, method="lm", xtol=1e-12, ftol=1e-12, max_nfev=20000)
    v = resid(r.x)
    sse = float(v @ v)
    return {"sse": sse, "rms_px": float(math.sqrt(sse / k)), "converged": bool(r.status > 0),
            "nfev": int(r.nfev), "nll_up_to_constant": sse / (2.0 * sigma_px ** 2),
            "space": "original distorted pixels, identical for every candidate"}


def old_score_bias(theta_m0, eta_probe=0.01, n_lines=24, seed=11):
    """Does the OLD score prefer a det-1 anisotropic transform under an M0 truth? And does the new one?

    The probe map is the M0 truth with eta set to `eta_probe`. Under an M0 truth the probe is WRONG, so a
    candidate-comparable score must not prefer it.
    """
    th0 = np.asarray(theta_m0, float).copy(); th0[13] = 0.0
    thp = th0.copy(); thp[13] = float(eta_probe)
    rng = np.random.default_rng(seed)
    raws, _ = synth_lines(th0, n_lines=n_lines, seed=seed)
    # Anisotropic click noise, heavier along the axis the probe compresses, which is the situation the
    # old score is vulnerable to. Isotropic noise is also run for contrast.
    out = {}
    for tag, cov in (("anisotropic_noise_2x_in_y", np.array([0.15, 0.60])),
                     ("isotropic_noise", np.array([0.35, 0.35]))):
        noisy = [r + rng.normal(0.0, 1.0, r.shape) * cov[None, :] for r in raws]
        old0, n0 = straightness_sse(noisy, th0)
        oldp, _ = straightness_sse(noisy, thp)
        new0 = sum(common_space_sse(r, th0)["sse"] for r in noisy)
        newp = sum(common_space_sse(r, thp)["sse"] for r in noisy)
        out[tag] = {
            "old_score_M0": math.sqrt(old0 / n0), "old_score_probe": math.sqrt(oldp / n0),
            "old_prefers_probe": bool(oldp < old0),
            "old_relative_change": float((oldp - old0) / old0),
            "new_score_M0_rms_px": math.sqrt(new0 / n0),
            "new_score_probe_rms_px": math.sqrt(newp / n0),
            "new_prefers_probe": bool(newp < new0),
            "new_relative_change": float((newp - new0) / new0)}
    out["eta_probe"] = float(eta_probe)
    out["truth"] = "M0 (eta = 0)"
    return out


def axis_sweep(theta_m0, mag=0.01, angles_deg=(0, 15, 30, 45, 60, 75, 90), n_lines=28, seed=13):
    """Inject a TWO-dof anisotropy at several orientations and see what the eta-only model recovers.

    The injected transform is exp(S) with S = mag * [[cos 2u, sin 2u], [sin 2u, -cos 2u]], applied where
    the model's own A sits (inside, on x - c). At u = 0 this is exactly the model's own eta direction; at
    u = 45 deg it is the pure b direction, which the model cannot represent at all.
    """
    th0 = np.asarray(theta_m0, float).copy(); th0[13] = 0.0
    W, H = LT.FRAME_W, LT.FRAME_H
    res = []
    for u in angles_deg:
        t = math.radians(u)
        S = mag * np.array([[math.cos(2 * t), math.sin(2 * t)],
                            [math.sin(2 * t), -math.cos(2 * t)]])
        # exp(S) for trace-free symmetric S with ||S|| = mag: exp(S) = cosh(mag) I + sinh(mag) S/mag
        Aexp = math.cosh(mag) * np.eye(2) + (math.sinh(mag) / mag) * S
        raws, ideals = [], []
        rng = np.random.default_rng(seed + u)
        for li in range(n_lines):
            ang = math.pi * li / n_lines
            d = np.array([math.cos(ang), math.sin(ang)])
            c = np.array([W / 2, H / 2]) + rng.uniform(-0.3, 0.3, 2) * np.array([W, H])
            tt = np.linspace(-0.22 * math.hypot(W, H), 0.22 * math.hypot(W, H), 12)
            ideal = c[None, :] + np.outer(tt, d)
            # invert the truth map U_t(x) = Aexp^-1 B(Aexp (x - c0)) by Newton on the composite
            xy = ideal.copy()
            for _ in range(60):
                z = (xy - th0[:2]) @ Aexp.T
                Bz = LT.U(z + th0[:2], th0)               # B applied about the same centre
                cur = (Bz - th0[:2]) @ np.linalg.inv(Aexp).T + th0[:2]
                err = cur - ideal
                if np.max(np.abs(err)) < 1e-9:
                    break
                xy = xy - err
            keep = ((xy[:, 0] > 90) & (xy[:, 0] < W - 90) & (xy[:, 1] > 90) & (xy[:, 1] < H - 90))
            if keep.sum() >= 6:
                raws.append(xy[keep])
        if not raws:
            res.append({"angle_deg": u, "error": "no usable lines"}); continue
        caps = _fake_caps(raws)
        D = OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
        r0 = OB.fit(D, "B", "M0", warm=False, max_nfev=3000)
        fr = OB.MODELS["M1"]
        x0 = np.array(r0["theta14"], float); x0[13] = 0.0
        r1 = OB.fit(D, "B", "M1", x0_model=x0[fr] / OB.SCALE14[fr], warm=False, max_nfev=3000)
        res.append({"angle_deg": u, "injected_magnitude": mag,
                    "true_a": float(mag * math.cos(2 * t)), "true_b": float(mag * math.sin(2 * t)),
                    "eta_hat": float(r1["eta"]),
                    "loss_M0": float(r0["loss"]), "loss_M1": float(r1["loss"]),
                    "loss_reduction_frac": float(1.0 - r1["loss"] / max(r0["loss"], 1e-300)),
                    "n_lines": len(raws)})
    return {"cases": res, "magnitude": mag,
            "note": "eta can only represent the a component. At 45 degrees the truth is pure b, which "
                    "the model cannot express, so eta_hat there measures leakage, not recovery."}


class _C:
    pass


def _fake_caps(raws):
    """Wrap a list of point arrays as a single synthetic Capture with one line per array."""
    C = _C()
    C.clip = "synthetic"
    C.timecode = "synthetic"
    xy = np.vstack(raws)
    C.xy = xy
    C.lines, C.inc = [], [[] for _ in range(len(xy))]
    o = 0
    for li, r in enumerate(raws):
        mem = list(range(o, o + len(r)))
        C.lines.append({"family": li % 2, "members": mem})
        for m in mem:
            C.inc[m].append(li)
        o += len(r)
    C.rc = np.full((len(xy), 2), np.nan)
    C.component = np.zeros(len(xy), int)
    C.local_scale = np.ones(len(xy))
    C.notes = {"n_lines": len(raws), "stored_incidences": len(xy), "unique_observations": len(xy),
               "index_contradictions": 0, "reliably_indexed": 0, "dropped_nonunit_edges": 0,
               "n_components": 1}
    C.n = len(xy)

    def indexed():
        return np.zeros(len(xy), bool)
    C.indexed = indexed

    def n_constraints():
        return np.array([len(i) for i in C.inc])
    C.n_constraints = n_constraints
    return [C]


def gauge_and_identifiability(theta_truth, n_lines=28, seed=5):
    """Noiseless multi-orientation lines: can M0 absorb a true eta, and is the gauge claim numerically true?"""
    raws, _ = synth_lines(theta_truth, n_lines=n_lines, seed=seed)
    caps = _fake_caps(raws)
    D = OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
    r0 = OB.fit(D, "B", "M0", warm=False, max_nfev=4000)
    fr = OB.MODELS["M1"]
    x0 = np.array(r0["theta14"], float); x0[13] = 0.0
    r1 = OB.fit(D, "B", "M1", x0_model=x0[fr] / OB.SCALE14[fr], warm=False, max_nfev=4000)
    return {"eta_true": float(np.asarray(theta_truth, float)[13]),
            "n_lines_used": len(raws),
            "M0_loss": float(r0["loss"]), "M1_loss": float(r1["loss"]),
            "eta_hat": float(r1["eta"]),
            "eta_recovery_error": float(r1["eta"] - np.asarray(theta_truth, float)[13]),
            "M0_can_absorb_fraction": float(1.0 - r1["loss"] / max(r0["loss"], 1e-300)),
            "M0_residual_rms_px": float(math.sqrt(r0["loss"] / max(D.n, 1))),
            "gauge": gauge_check(theta_truth, raws),
            "scaled_information": scaled_information(D, np.array(r1["theta14"], float))}
