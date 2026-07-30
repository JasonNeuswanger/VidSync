#!/usr/bin/env python3
"""SD-D with an exact analytic Jacobian and attainable stopping criteria. SAME estimator.

WHAT THE DIAGNOSIS FOUND (sd_diag.py, 2026-07-29). The capped SD-D fits were not hard optimization
problems and were not slow because of the objective. Two separate things went wrong:

  1. UNREACHABLE TOLERANCES. `objectives.fit` passes ftol = xtol = gtol = 1e-14. For a cost of order
     1e2 in double precision a relative cost-change test at 1e-14 can essentially never fire, and the
     scaled-gradient norm on this problem plateaus around 1e-2, so gtol never fires either. Trust-region
     reflective therefore ground on to the evaluation cap while buying about 1e-9 relative loss per
     iteration. Pool Left M0 reached loss 118.56307981 after 1200 iterations; the same fit with
     ftol = 1e-8 stops after 28 iterations at 118.56318625. That is a 9e-7 RELATIVE difference. The
     fits had converged; `status = 0` was an artefact of the stopping rule, not a solver failure.

  2. INVISIBLE FINITE-DIFFERENCE TRAFFIC. 93% of all residual calls were SciPy's own
     finite-difference calls, which `res.nfev` does not report. Each Jacobian cost about 13 residual
     evaluations (9 dense model columns, which cannot share a finite-difference group, plus 4-5 groups
     for the ~136 line nuisance parameters after sparsity colouring). With njev almost equal to nfev,
     the true cost was about 13x the reported one.

WHAT THIS MODULE CHANGES, AND WHAT IT DOES NOT. The estimator is untouched:

    L = sum_i a_i F_i^T (G_i G_i^T)^-1 F_i

with one joint constraint block per unique observation carrying all of that observation's distinct line
memberships, one Delaunay spatial weight a_i per unique observation, singly constrained points using a
one-row block, and exact duplicate line records still deduplicated upstream in `objectives.Dataset`. The
Delaunay estimand, the selected observation set and the weights all come from the existing code and are
not recomputed here. No regularization is added, no weight is changed, no lattice constraint is
introduced, and no observation is added or dropped.

What changes is only how the derivative is obtained and when the optimizer is allowed to stop:

  * exact analytic derivatives for the 2*nline line nuisance parameters, including the derivative of
    the Cholesky factor;
  * exact complex-step derivatives for the model block (centre, k1..k4, p1, p2, eta), which is analytic
    to machine precision rather than a difference of nearby values;
  * one batched small-matrix inverse per Jacobian so every triangular solve becomes a matmul;
  * the unconditional `eigvalsh` in the reference residual, which is pure diagnostics and cost 20% of
    every call, moved off the hot path;
  * attainable tolerances, plus an explicit convergence-verification procedure (`verify_convergence`)
    that restarts from the reported solution and from perturbed starts and requires no material
    improvement. Only that procedure may set `convergence_verified` in `fitvalidity`.

DERIVATIVE OF THE RESIDUAL. Per observation i with m incidences, writing A = G G^T + eps I = L L^T and
z = L^-1 F, the residual is r = sqrt(a_i) z and

    dz = L^-1 dF - Phi(L^-1 dA L^-T) z,        Phi(W) = lower triangle of W with the diagonal halved.

That is the standard differential of a Cholesky factor: with X = L^-1 dL, L^-1 dA L^-T = X + X^T and X
is lower triangular, so X = Phi(W). Every quantity is m x m with m <= 4 here, so this is cheap.

Run with ~/.venvs/vidsync/bin/python.
"""

import copy
import math

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix

import harness_import

harness_import.ensure_path()

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")

CENTRE = OB.CENTRE
SCALE14 = OB.SCALE14

# Stopping criteria chosen against the SCIENTIFIC scale, not against double precision.
#
# Near its optimum this objective is extremely flat: the diagnosis measured relative cost changes of
# about 1e-9 per iteration sustained over a thousand iterations. Any ftol tighter than roughly 1e-9
# therefore runs to the evaluation cap by construction, which is exactly what ftol = 1e-14 did. That is
# a property of the problem, not a solver defect, and loosening the tolerance is not an approximation:
# the loss here is of order 1e2 and the differences BETWEEN candidate models that this harness has to
# resolve are of order 1 to 30, so a relative cost change of 1e-8 (about 1e-6 absolute) is six orders
# of magnitude below anything scientifically meaningful.
#
# gtol is not the binding criterion either: the scaled-gradient norm plateaus near 1e-2 on this problem,
# so a tight gtol only guarantees the cap will be hit. Convergence is therefore VERIFIED separately by
# `verify_convergence` rather than asserted by the tolerance -- which is the whole point of keeping
# `fitvalidity.convergence_verified` a flag only an explicit procedure may set.
FTOL = 1e-8
XTOL = 1e-8
GTOL = 1e-8
MAX_NFEV = 300
CS_STEP = 1e-20            # complex step; exact to machine precision, no subtractive cancellation


# =============================================================== complex-safe map and Jacobian


def U_c(x, th):
    """`parity_step5.undistort_conjugated` with complex-safe arithmetic.

    The reference `lattice.U` delegates to `fitter.undistort` when eta is exactly zero, so that the
    eta = 0 nesting is bit-exact; that branch casts to float and would silently discard a complex
    perturbation. This always uses the conjugated form, whose analytic continuation into complex theta
    is what complex-step differentiation needs. The two forms agree to round-off at eta = 0 -- they are
    the same expression accumulated in a different order -- so derivatives from this function are
    derivatives of the reference residual to within round-off, which the gates verify against central
    differences rather than assume.
    """
    x = np.atleast_2d(x)
    ax = np.exp(th[13]); ay = 1.0 / ax
    xd = (x[:, 0] - th[0]) * ax
    yd = (x[:, 1] - th[1]) * ay
    s = xd * xd + yd * yd
    R = np.ones_like(s)
    sp = np.ones_like(s)
    for k in th[2:9]:
        sp = sp * s
        R = R + k * sp
    T = 1.0 + th[11] * s + th[12] * s * s
    ux = xd * R + (th[9] * (s + 2 * xd * xd) + 2 * th[10] * xd * yd) * T
    uy = yd * R + (2 * th[9] * xd * yd + th[10] * (s + 2 * yd * yd)) * T
    return np.stack([th[0] + ux / ax, th[1] + uy / ay], axis=1)


def jac_U_c(x, th):
    """`lattice.jac_U` with complex-safe arithmetic. Same expressions, no float cast, np.exp."""
    x = np.atleast_2d(x)
    ax = np.exp(th[13]); ay = 1.0 / ax
    xd = (x[:, 0] - th[0]) * ax
    yd = (x[:, 1] - th[1]) * ay
    s = xd * xd + yd * yd
    R = np.ones_like(s); Rp = np.zeros_like(s)
    for i, k in enumerate(th[2:9], start=1):
        R = R + k * s ** i
        Rp = Rp + i * k * s ** (i - 1)
    p1, p2, p3, p4 = th[9], th[10], th[11], th[12]
    T = 1.0 + p3 * s + p4 * s * s
    Tp = p3 + 2 * p4 * s
    Gx = p1 * (3 * xd * xd + yd * yd) + 2 * p2 * xd * yd
    Gy = 2 * p1 * xd * yd + p2 * (xd * xd + 3 * yd * yd)
    a = R + 2 * xd * xd * Rp + (6 * p1 * xd + 2 * p2 * yd) * T + 2 * xd * Gx * Tp
    b = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * yd * Gx * Tp
    c = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * xd * Gy * Tp
    d = R + 2 * yd * yd * Rp + (2 * p1 * xd + 6 * p2 * yd) * T + 2 * yd * Gy * Tp
    J = np.empty((x.shape[0], 2, 2), dtype=np.result_type(a, b, c, d))
    J[:, 0, 0] = a
    J[:, 0, 1] = b * ay / ax
    J[:, 1, 0] = c * ax / ay
    J[:, 1, 1] = d
    return J


def _phi(W):
    """Lower triangle with the diagonal halved, batched over the leading axis."""
    m = W.shape[-1]
    out = np.tril(W)
    idx = np.arange(m)
    out[..., idx, idx] = 0.5 * W[..., idx, idx]
    return out


# =============================================================== the evaluator


class SDFast:
    """Residual and exact Jacobian for SD-D on a fixed `objectives.Dataset`.

    `counts` records the ACTUAL number of residual and Jacobian evaluations, so reported timing can be
    reconciled against work done rather than against SciPy's `nfev`.
    """

    def __init__(self, D, pk, base, eps=1e-12):
        self.D = D
        self.pk = pk
        self.base = np.asarray(base, float).copy()
        self.eps = eps
        self.nline = pk.nline
        self.nm = pk.nm
        self.free = list(pk.free)
        # Static index structures, gathered once. `objectives.resid_SD` rebuilt these on every call at
        # 0.18 ms each; they cannot change during a fit because the selected observations cannot.
        self.groups = []
        row = 0
        for m, idx in OB._blocks(D).items():
            if m == 0:
                continue
            li = np.array([D.obs_lines[i] for i in idx], int)      # (k, m) line ids
            self.groups.append({"m": m, "idx": idx, "li": li, "row0": row,
                                "sw": np.sqrt(D.w[idx]), "k": len(idx)})
            row += m * len(idx)
        self.nres = row
        self.counts = {"residual": 0, "jacobian": 0}
        self._jac_rows, self._jac_cols = self._pattern()

    # ---- residual -----------------------------------------------------------------------

    def _state(self, p, want_jac=False):
        th = self.pk.theta(p, self.base)
        ph = p[self.pk.iline:self.pk.iline + self.nline]
        e = p[self.pk.iline + self.nline:self.pk.iline + 2 * self.nline]
        nvec = np.stack([np.cos(ph), np.sin(ph)], axis=1)
        u = LT.U(self.D.xy, th) - CENTRE
        J = LT.jac_U(self.D.xy, th)
        return th, ph, e, nvec, u, J

    def residual(self, p):
        """Identical arithmetic to `objectives.resid_SD`, without its unconditional eigvalsh."""
        self.counts["residual"] += 1
        th, ph, e, nvec, u, J = self._state(p)
        pieces = []
        for g in self.groups:
            m, idx, li = g["m"], g["idx"], g["li"]
            nn = nvec[li]
            Fi = np.einsum("kmj,kj->km", nn, u[idx]) - e[li]
            Gi = np.einsum("kmj,kji->kmi", nn, J[idx])
            GG = np.einsum("kmi,kni->kmn", Gi, Gi)
            Lc = np.linalg.cholesky(GG + self.eps * np.eye(m))
            z = np.linalg.solve(Lc, Fi[..., None])[..., 0]
            pieces.append((g["sw"][:, None] * z).ravel())
        return np.concatenate(pieces) if pieces else np.zeros(1)

    def loss(self, p):
        r = self.residual(p)
        return float(r @ r)

    # ---- Jacobian -----------------------------------------------------------------------

    def _pattern(self):
        """Row/column index arrays for the sparse Jacobian, in residual order."""
        rows, cols = [], []
        for g in self.groups:
            m, li, k, r0 = g["m"], g["li"], g["k"], g["row0"]
            rr = r0 + np.arange(k * m)
            for j in range(self.nm):                       # dense model block
                rows.append(rr); cols.append(np.full(k * m, j))
            for a in range(m):                             # this observation's a-th line
                lids = np.repeat(li[:, a], m)
                rows.append(rr); cols.append(self.pk.iline + lids)
                rows.append(rr); cols.append(self.pk.iline + self.nline + lids)
        return np.concatenate(rows), np.concatenate(cols)

    def jacobian(self, p):
        self.counts["jacobian"] += 1
        th, ph, e, nvec, u, J = self._state(p)
        nper = np.stack([-np.sin(ph), np.cos(ph)], axis=1)          # d nvec / d phi

        # --- model block: exact complex-step derivatives of u and of the map Jacobian.
        # One perturbed evaluation per free model parameter. This is the only place a step size
        # appears anywhere in the derivative, and complex-step has no subtractive cancellation, so
        # the result is exact to machine precision rather than accurate to sqrt(eps).
        thc = th.astype(complex)
        du = np.empty((self.nm, self.D.n, 2))
        dJ = np.empty((self.nm, self.D.n, 2, 2))
        for j, f in enumerate(self.free):
            t2 = thc.copy()
            t2[f] = t2[f] + 1j * CS_STEP
            # chain rule: p[j] is in scaled units, th[f] = p[j] * SCALE14[f]
            du[j] = (U_c(self.D.xy, t2).imag / CS_STEP) * SCALE14[f]
            dJ[j] = (jac_U_c(self.D.xy, t2).imag / CS_STEP) * SCALE14[f]

        # The block algebra below is VECTORIZED OVER THE PARAMETER AXIS. Written as one loop per
        # parameter it spent 9 of 11 ms in numpy call overhead on 2x2 matrices; batching the model
        # block into a single set of operations is what brings the Jacobian near the residual cost.
        vals = []
        for g in self.groups:
            m, idx, li, k = g["m"], g["idx"], g["li"], g["k"]
            sw = g["sw"]
            nn = nvec[li]                                            # (k, m, 2)
            npr = nper[li]                                           # (k, m, 2)
            u_g = u[idx]                                             # (k, 2)
            J_g = J[idx]                                             # (k, 2, 2)
            # Batched matmul rather than einsum throughout this function: c_einsum was 4.3 ms of the
            # 8.4 ms Jacobian on 2x2 blocks, where it cannot use the fast matmul path. The RESIDUAL
            # above deliberately still uses einsum, so that it stays bit-identical to the reference.
            Fi = (nn @ u_g[:, :, None])[:, :, 0] - e[li]              # (k, m)
            Gi = nn @ J_g                                            # (k, m, 2)
            GiT = np.swapaxes(Gi, -1, -2)
            GG = Gi @ GiT                                            # (k, m, m)
            Lc = np.linalg.cholesky(GG + self.eps * np.eye(m))
            Li = np.linalg.inv(Lc)                                   # one batched inverse per group
            LiT = np.swapaxes(Li, -1, -2)
            z = (Li @ Fi[:, :, None])[:, :, 0]                       # (k, m)
            zc = z[None, :, :, None]

            def dz_batched(dF, dA):
                """dz = L^-1 dF - Phi(L^-1 dA L^-T) z, batched over a leading parameter axis."""
                out = (Li[None] @ dF[..., None])[..., 0]
                if dA is not None:
                    W = (Li[None] @ dA) @ LiT[None]
                    out = out - (_phi(W) @ zc)[..., 0]
                return out

            # ---- model parameters, all at once: u and J both move, so every row of F and G moves
            dFm = (nn[None] @ du[:, idx, :][..., None])[..., 0]      # (nm, k, m)
            dGm = nn[None] @ dJ[:, idx]                              # (nm, k, m, 2)
            dAm = dGm @ GiT[None]                                    # (nm, k, m, m)
            dAm = dAm + np.swapaxes(dAm, 2, 3)
            dzm = dz_batched(dFm, dAm)                               # (nm, k, m)
            gvals = [(sw[:, None] * dzm[j]).ravel() for j in range(self.nm)]

            # ---- line parameters: only the a-th row of F and G moves, so these stay per-slot.
            # m is 1 or 2 on this corpus, so there is nothing to gain from batching them further.
            for a in range(m):
                # phi_a
                dF = np.zeros((1, k, m))
                dF[0, :, a] = (npr[:, a, :] * u_g).sum(axis=1)
                dGa = (npr[:, a, None, :] @ J_g)[:, 0, :]             # (k, 2)
                dA = np.zeros((1, k, m, m))
                dA[0, :, a, :] = (Gi @ dGa[:, :, None])[:, :, 0]
                dA = dA + np.swapaxes(dA, 2, 3)
                gvals.append((sw[:, None] * dz_batched(dF, dA)[0]).ravel())
                # e_a: F shifts by -1 in slot a, G is unaffected, so dA is exactly zero
                dF = np.zeros((1, k, m))
                dF[0, :, a] = -1.0
                gvals.append((sw[:, None] * dz_batched(dF, None)[0]).ravel())
            vals.append(gvals)

        # assemble in the same order the pattern was built
        flat = []
        for gv in vals:
            flat.extend(gv)
        return csr_matrix((np.concatenate(flat), (self._jac_rows, self._jac_cols)),
                          shape=(self.nres, self.pk.n))


# =============================================================== fit and convergence verification


def dedup_view(D):
    """A shallow view of `D` whose captures expose only the line records `D` RETAINED.

    WHY. `objectives.Dataset` deduplicates exact duplicate line records for SD/ED/PD -- two stored
    records with an identical selected member set are the same physical line -- but `resid_B` iterates
    `C.lines` directly and so does NOT. Measured on 119 jittered synthetic points, adding one duplicate
    record gives B 14 extra residual rows and moves its fitted centre by 4.37 px.

    SD's estimator is exactly invariant to that duplicate (verified in test_sd_fast.py: bit-identical
    residual and objective at a common parameter point). But SD is WARM-STARTED from B, so a duplicate
    still moved SD's starting point and therefore its reported optimum, by about 0.2 px of centre on a
    shallow objective. Building the warm start on the deduplicated view makes SD duplicate-invariant
    end to end without touching B itself, which remains the untouched legacy compatibility option.

    This changes only the starting point, never the objective.
    """
    caps = []
    for ci, C in enumerate(D.caps):
        keep = D.keep_line[ci]
        C2 = copy.copy(C)                                  # shallow: xy and inc are shared, not copied
        C2.lines = [ln for li, ln in enumerate(C.lines) if keep[li]]
        caps.append(C2)
    D2 = copy.copy(D)
    D2.caps = caps
    return D2


def make(D, model, base=None, free=None, zero_held=True):
    """Build (SDFast, p0, bounds) with a duplicate-invariant B warm start."""
    base = OB.default_base() if base is None else np.asarray(base, float).copy()
    fr = OB.MODELS[model] if free is None else list(free)
    wb = OB.fit(dedup_view(D), "B", model, base=base.copy(), warm=False, max_nfev=3000, free=fr,
                zero_held=zero_held)
    b2 = base.copy()
    if zero_held:
        b2[[j for j in range(14) if j not in set(fr)]] = 0.0
    pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                 nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="SD", free=fr)
    p0 = np.zeros(pk.n)
    p0[:pk.nm] = np.array(wb["theta14"], float)[fr] / SCALE14[fr]
    th0 = pk.theta(p0, b2)
    ph, e = OB.init_lines(D, th0)
    p0[pk.iline:pk.iline + D.nline] = ph
    p0[pk.iline + D.nline:pk.iline + 2 * D.nline] = e
    ev = SDFast(D, pk, b2)
    lo, hi = pk.bounds(b2)
    return ev, np.clip(p0, lo, hi), (lo, hi), wb


def solve(ev, p0, bounds, max_nfev=MAX_NFEV, ftol=FTOL, xtol=XTOL, gtol=GTOL):
    return least_squares(ev.residual, p0, jac=ev.jacobian, bounds=bounds, method="trf",
                         x_scale="jac", ftol=ftol, xtol=xtol, gtol=gtol, max_nfev=max_nfev)


def polish_and_verify(ev, res, bounds, n_perturb=3, rel_tol=1e-6, seed=20260729,
                      max_nfev=MAX_NFEV, max_rounds=4):
    """THE explicit convergence-verification procedure. Nothing else may set `convergence_verified`.

    This is a MULTI-START WITH VERIFICATION, not a tolerance relaxation. A first version only checked
    the reported solution, and on three of eight real fits a perturbed restart reached a loss about
    1e-6 lower. The honest response is to ACCEPT the better point, not to widen the threshold until the
    worse one passes. So each round restarts plainly from the current best and from `n_perturb`
    perturbed model blocks, keeps the best result, and stops when a whole round fails to improve by more
    than `rel_tol` relatively. Because every continuing round must improve by more than `rel_tol` and
    the loss is bounded below, this terminates.

    Convergence is declared only if all of:

      1. the ACCEPTED solution terminated on a real convergence criterion, not the evaluation cap;
      2. the final round found no material improvement, which means a plain restart is stable AND no
         perturbed start beat it -- the only check here able to detect a second basin;
      3. the round budget was not exhausted while still improving.

    "Material" is RELATIVE to the achieved loss, since the loss scale differs by orders of magnitude
    between cameras. Returns (accepted_result, info).
    """
    rng = np.random.default_rng(seed)
    best = res
    lbest = float(res.fun @ res.fun)
    l_first = lbest
    rounds = []
    stable = False
    for rnd in range(max_rounds):
        cands = [("plain restart", solve(ev, best.x, bounds, max_nfev=max_nfev))]
        for i in range(n_perturb):
            q = np.array(best.x, float).copy()
            # perturb only the model block; the optimizer re-derives the line nuisances from it
            q[:ev.nm] = q[:ev.nm] * (1.0 + 0.05 * rng.standard_normal(ev.nm))
            cands.append((f"perturbed {i}",
                          solve(ev, np.clip(q, bounds[0], bounds[1]), bounds, max_nfev=max_nfev)))
        losses = [(float(r.fun @ r.fun), nm, r) for nm, r in cands]
        lmin, which, rmin = min(losses, key=lambda t: t[0])
        gain = (lbest - lmin) / max(abs(lbest), 1e-300)
        rounds.append({"round": rnd, "best_before": lbest, "best_after": min(lbest, lmin),
                       "source_of_best": which, "gain_relative": gain,
                       "candidates": [{"source": nm, "loss": l, "status": int(r.status)}
                                      for l, nm, r in losses]})
        if gain <= rel_tol:
            stable = True
            break
        best, lbest = rmin, lmin
    info = {"rel_tol": rel_tol, "rounds": rounds, "n_rounds_used": len(rounds),
            "max_rounds": max_rounds, "stable_final_round": bool(stable),
            "loss": float(best.fun @ best.fun), "status": int(best.status),
            "terminated_on_criterion": int(best.status) > 0,
            "scaled_optimality": float(best.optimality),
            "final_round_gain_relative": rounds[-1]["gain_relative"] if rounds else 0.0,
            "first_solve_loss": l_first,
            "improved_over_first_solve_relative":
                (l_first - float(best.fun @ best.fun)) / max(abs(l_first), 1e-300)}
    info["verified"] = bool(info["terminated_on_criterion"] and stable)
    return best, info


def fit_sd(D, model, base=None, free=None, zero_held=True, max_nfev=MAX_NFEV, verify=True,
           n_perturb=3, hard_limit_s=5.0):
    """One SD-D fit with the accelerated solver, plus its convergence verification.

    `hard_limit_s` is reported, not enforced mid-solve: SciPy offers no wall-clock callback for `trf`,
    and killing a fit part way would leave an unusable state. It is recorded so the caller can reject.
    """
    import time
    ev, p0, bounds, wb = make(D, model, base=base, free=free, zero_held=zero_held)
    t0 = time.time()
    res = solve(ev, p0, bounds, max_nfev=max_nfev)
    t_solve = time.time() - t0
    calls_solve = dict(ev.counts)
    first = {"nfev": int(res.nfev), "njev": int(res.njev), "status": int(res.status),
             "loss": float(res.fun @ res.fun), "optimality": float(res.optimality)}
    ver = None
    if verify:
        # The ACCEPTED solution is the polished one, so what gets reported is what was verified.
        res, ver = polish_and_verify(ev, res, bounds, n_perturb=n_perturb, max_nfev=max_nfev)
    t_total = time.time() - t0
    th = ev.pk.theta(res.x, ev.base)
    return {"objective": "SD", "model": model, "theta14": th.tolist(), "p": res.x.tolist(),
            "loss": float(res.fun @ res.fun), "status": int(res.status),
            "optimality": float(res.optimality), "nfev": int(res.nfev), "njev": int(res.njev),
            "solve_s": t_solve, "total_s": t_total,
            "over_hard_limit": bool(t_total > hard_limit_s), "hard_limit_s": hard_limit_s,
            # First-solve counters, which are the ones that reconcile against SciPy's own nfev/njev.
            # `nfev`/`njev` below belong to the ACCEPTED (polished) result, so they are deliberately
            # reported separately rather than being compared with these.
            "first_solve": first,
            "actual_residual_calls": calls_solve["residual"],
            "actual_jacobian_calls": calls_solve["jacobian"],
            "total_residual_calls_incl_verification": ev.counts["residual"],
            "total_jacobian_calls_incl_verification": ev.counts["jacobian"],
            "n_params": int(ev.pk.n), "n_model_params": int(ev.nm),
            "n_line_params": int(2 * ev.nline), "n_residual_rows": int(ev.nres),
            "n_observations": int(D.n), "n_lines": int(D.nline), "n_captures": int(D.ncap),
            "eta": float(th[13]), "b_loss": wb["loss"], "b_theta14": wb["theta14"],
            "ftol": FTOL, "xtol": XTOL, "gtol": GTOL, "max_nfev": max_nfev,
            "convergence": ver,
            "convergence_verified": bool(ver["verified"]) if ver else False,
            "solver": "sd_fast: analytic line Jacobian + complex-step model Jacobian"}
