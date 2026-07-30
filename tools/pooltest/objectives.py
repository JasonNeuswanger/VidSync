#!/usr/bin/env python3
"""The four distortion objectives, on a common interface, for M0 and M1.

  B   the current production objective: sum of squared orthogonal residuals of each STORED line
      about its own total-least-squares fit, in corrected coordinates, unweighted, counting a shared
      corner once per stored line incidence. The historical comparator, reproduced exactly.

  SD  unique-point block Sampson distance with Delaunay weights. Lines are explicit nuisance
      parameters. For observation i with corrected point U(x_i) and its one or two lines,
      F_i = [n_j . U(x_i) + d_j], G_i rows = n_j^T J_U(x_i), and the whitened block residual has
      squared norm a_i F_i^T (G_i G_i^T)^-1 F_i. Sigma_i = I this round.

  ED  the exact raw-coordinate errors-in-variables problem: minimize sum a_i |x_i - q_i|^2 subject to
      n_l . U(q_i) + d_l = 0 for every incidence. For a doubly constrained point, the corrected latent
      point is the intersection of its two corrected-space lines and q_i = U^-1 of that intersection,
      which satisfies both constraints exactly by construction. For a singly constrained point a
      latent coordinate along its corrected line is carried as a nuisance parameter.

  PD  the exact projective-lattice objective: each capture v gets its own homography H_v while all
      captures of a camera share one U. Residual x_vrc - U^-1(pi(H_v [c, r, 1])), raw-space.

DESIGN CHOICE, stated because it bounds what the comparison isolates. SD and ED use the SAME STORED
line incidences as B, not merged physical rows and columns. The legacy detector fragments one physical
row into several line records, and merging them would strengthen the constraint set at the same time
as changing the objective, confounding the two. So B, SD and ED differ only in (a) unique-point versus
per-incidence counting, (b) approximate versus exact geometry, (c) unweighted versus Delaunay
quadrature. PD is the objective that exploits full lattice structure.

Requires numpy and scipy. Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import time
from collections import defaultdict

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

HERE = os.path.dirname(os.path.abspath(__file__))


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
P5 = L("parity_step5")
LT = L("lattice")
SCALE14 = LT.SCALE14
ETA_SCALE = LT.ETA_SCALE
ETA_BOUND = LT.ETA_BOUND
MODELS = LT.MODELS
CENTRE = np.array([LT.FRAME_W / 2.0, LT.FRAME_H / 2.0])
PXSCALE = 1000.0                      # only used to keep homography coordinates O(1)


def default_base():
    """Production's own starting point: distortion centre at the frame centre, everything else zero.

    This matters more than it looks. A base of all zeros puts the distortion centre at the image
    ORIGIN rather than its middle, and from there even the production objective B fails to converge on
    perfectly consistent synthetic data -- it stalled with the centre at (323, 542) against a truth of
    (955, 535). Every objective was exactly zero at the truth throughout, so the symptom was purely
    this starting point. Anything calling fit() without a base gets production's start.
    """
    b = np.zeros(14)
    b[0] = (LT.FRAME_W / 2.0) / SCALE14[0]
    b[1] = (LT.FRAME_H / 2.0) / SCALE14[1]
    return b


# =============================================================== dataset assembly


class Dataset:
    """One camera's observations, selected and cross-referenced for the objectives.

    Selection reaches a fixed point: a line is kept only if at least `min_line_pts` selected
    observations lie on it (a 2-point line is exactly fittable and carries no information), and an
    observation is kept only if it retains at least `min_inc` incidences. Both counts are reported.
    """

    def __init__(self, caps, require_indexed=True, min_inc=2, min_line_pts=3, kappa=3.0,
                 single_component=True):
        self.caps = caps
        self.require_indexed = require_indexed
        self.min_inc = min_inc
        self.min_line_pts = min_line_pts

        sel = []
        for C in caps:
            m = np.ones(C.n, bool)
            if require_indexed:
                m &= C.indexed()
            sel.append(m)
        # One homography per capture can only describe ONE lattice. Index labels restart at (0, 0) in
        # every connected component, so two components of the same capture carry unrelated origins and
        # no single H can fit both. Restrict each capture to its largest indexed component and report
        # what that costs, rather than letting PD silently fit an incoherent index set.
        self.component_report = []
        if single_component:
            for ci, C in enumerate(caps):
                comps = {}
                for i in np.where(sel[ci])[0]:
                    comps[int(C.component[i])] = comps.get(int(C.component[i]), 0) + 1
                if not comps:
                    self.component_report.append({"kept": None, "counts": {}}); continue
                best = max(comps, key=lambda k: comps[k])
                dropped = sum(v for k, v in comps.items() if k != best)
                sel[ci] = sel[ci] & (C.component == best)
                self.component_report.append(
                    {"kept": best, "counts": dict(sorted(comps.items(), key=lambda z: -z[1])),
                     "dropped_observations": int(dropped)})

        # fixed point on (observations, lines)
        keep_line = [np.ones(len(C.lines), bool) for C in caps]
        for _ in range(50):
            changed = False
            for ci, C in enumerate(caps):
                cnt = np.zeros(len(C.lines), int)
                for li, ln in enumerate(C.lines):
                    cnt[li] = sum(1 for m in ln["members"] if sel[ci][m])
                nk = cnt >= min_line_pts
                if not np.array_equal(nk, keep_line[ci]):
                    keep_line[ci] = nk
                    changed = True
                ninc = np.array([sum(1 for li in C.inc[i] if keep_line[ci][li])
                                 for i in range(C.n)])
                ns = sel[ci] & (ninc >= min_inc)
                if not np.array_equal(ns, sel[ci]):
                    sel[ci] = ns
                    changed = True
            if not changed:
                break
        # Two stored line records with an identical selected member set are the SAME physical line.
        # Keeping both would put duplicated rows into every Sampson constraint block, making G_i G_i^T
        # rank deficient rather than merely ill-conditioned, and would make SD and ED sensitive to a
        # pure storage artifact. Deduplicate and report.
        self.merged_duplicate_lines = 0
        for ci, C in enumerate(caps):
            seen = {}
            for li, ln in enumerate(C.lines):
                if not keep_line[ci][li]:
                    continue
                key = frozenset(m for m in ln["members"] if sel[ci][m])
                if key in seen:
                    keep_line[ci][li] = False
                    self.merged_duplicate_lines += 1
                else:
                    seen[key] = li
        self.sel = sel
        self.keep_line = keep_line

        # flatten observations
        self.cap_of, self.xy, self.rc, self.obs_lines = [], [], [], []
        self.local = []
        gline = {}
        for ci, C in enumerate(caps):
            for i in np.where(sel[ci])[0]:
                self.cap_of.append(ci)
                self.xy.append(C.xy[i])
                self.rc.append(C.rc[i])
                self.local.append(C.local_scale[i])
                ls = []
                for li in C.inc[i]:
                    if not keep_line[ci][li]:
                        continue
                    key = (ci, li)
                    if key not in gline:
                        gline[key] = len(gline)
                    ls.append(gline[key])
                self.obs_lines.append(ls)
        self.xy = np.array(self.xy, float)
        self.rc = np.array(self.rc, float)
        self.cap_of = np.array(self.cap_of, int)
        self.local = np.array(self.local, float)
        self.gline = gline
        self.nline = len(gline)
        self.line_family = np.zeros(self.nline, int)
        for (ci, li), gi in gline.items():
            self.line_family[gi] = caps[ci].lines[li]["family"]

        # Delaunay weights over exactly the selected observations
        self.w, self.winfo = LT.delaunay_weights(caps, kappa=kappa, mask=sel)
        self.n = len(self.xy)
        self.ncap = len(caps)
        self.info = {
            "n_observations": self.n,
            "n_lines": self.nline,
            "per_capture": [int((self.cap_of == c).sum()) for c in range(self.ncap)],
            "incidence_counts": {k: int(v) for k, v in sorted(
                {c: sum(1 for l in self.obs_lines if len(l) == c)
                 for c in {len(l) for l in self.obs_lines}}.items())},
            "dropped_lines": int(sum((~k).sum() for k in keep_line)),
            "merged_duplicate_line_records": self.merged_duplicate_lines,
            "min_line_pts": min_line_pts, "min_inc": min_inc,
            "require_indexed": require_indexed,
            "single_component": single_component,
            "components": self.component_report,
            "weights": {k: v for k, v in self.winfo.items() if k != "owner"},
        }

        # normalized lattice coordinates per capture, for PD
        self.lat = np.zeros((self.n, 2))
        self.latinfo = []
        for c in range(self.ncap):
            m = self.cap_of == c
            if not m.any():
                self.latinfo.append(None); continue
            rc = self.rc[m]
            mu = rc.mean(axis=0)
            sd = rc.std(axis=0)
            sd = np.where(sd < 1e-9, 1.0, sd)
            self.lat[m] = (rc - mu) / sd
            self.latinfo.append({"mu": mu.tolist(), "sd": sd.tolist()})


# =============================================================== parameter packing


class Pack:
    """Layout of the free parameter vector: model block, then objective-specific nuisances."""

    def __init__(self, model, nline=0, ncap=0, nfree_t=0, objective="B", free=None):
        self.free = MODELS[model] if free is None else list(free)
        self.model = model
        self.nm = len(self.free)
        self.objective = objective
        self.nline = nline
        self.ncap = ncap
        self.nfree_t = nfree_t
        self.n = self.nm
        self.iline = self.n
        if objective in ("SD", "ED"):
            self.n += 2 * nline
        self.it = self.n
        if objective == "ED":
            self.n += nfree_t
        self.ih = self.n
        if objective == "PD":
            self.n += 8 * ncap

    def theta(self, p, base):
        th = np.asarray(base, float).copy()
        th[self.free] = p[:self.nm]
        return th * SCALE14

    def bounds(self, base):
        lo = np.full(self.n, -np.inf)
        hi = np.full(self.n, np.inf)
        for j, f in enumerate(self.free):
            if f == 13:
                lo[j] = -ETA_BOUND / ETA_SCALE
                hi[j] = +ETA_BOUND / ETA_SCALE
        return lo, hi


# =============================================================== the four objectives


def _line_nd(p, pk):
    """Line normals and offsets from (phi, e), with the offset measured from the frame centre."""
    ph = p[pk.iline:pk.iline + pk.nline]
    e = p[pk.iline + pk.nline:pk.iline + 2 * pk.nline]
    nvec = np.stack([np.cos(ph), np.sin(ph)], axis=1)
    return nvec, e


def resid_B(p, D, pk, base):
    """Production objective on the STORED representation, eta-aware, unweighted."""
    th = pk.theta(p, base)
    out = []
    for C in D.caps:
        u = LT.U(C.xy, th)
        for ln in C.lines:
            mem = ln["members"]
            if len(mem) < 3:
                continue
            P = u[mem]
            q = P - P.mean(axis=0)
            t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                                 float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            out.append(-q[:, 0] * math.sin(t) + q[:, 1] * math.cos(t))
    return np.concatenate(out) if out else np.zeros(1)


def _blocks(D):
    """Observations grouped by their number of incidences, for vectorized block algebra."""
    g = defaultdict(list)
    for i, ls in enumerate(D.obs_lines):
        g[len(ls)].append(i)
    return {k: np.array(v, int) for k, v in g.items()}


def resid_SD(p, D, pk, base, report=None):
    th = pk.theta(p, base)
    nvec, e = _line_nd(p, pk)
    u = LT.U(D.xy, th) - CENTRE
    J = LT.jac_U(D.xy, th)
    out = np.zeros(0)
    pieces = []
    worst = np.inf
    for m, idx in _blocks(D).items():
        if m == 0:
            continue
        li = np.array([D.obs_lines[i] for i in idx], int)          # (k, m)
        nn = nvec[li]                                              # (k, m, 2)
        Fi = np.einsum("kmj,kj->km", nn, u[idx]) - e[li]           # (k, m)
        Gi = np.einsum("kmj,kji->kmi", nn, J[idx])                 # (k, m, 2)
        GG = np.einsum("kmi,kni->kmn", Gi, Gi)                     # (k, m, m)
        ev = np.linalg.eigvalsh(GG)
        worst = min(worst, float(ev[:, 0].min()))
        Lc = np.linalg.cholesky(GG + 1e-12 * np.eye(m))
        z = np.linalg.solve(Lc, Fi[..., None])[..., 0]             # (k, m)
        pieces.append((np.sqrt(D.w[idx])[:, None] * z).ravel())
    if report is not None:
        report["min_block_eig"] = worst
    out = np.concatenate(pieces) if pieces else np.zeros(1)
    return out


def _intersect(n1, e1, n2, e2):
    det = n1[:, 0] * n2[:, 1] - n1[:, 1] * n2[:, 0]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    x = (e1 * n2[:, 1] - e2 * n1[:, 1]) / det
    y = (n1[:, 0] * e2 - n2[:, 0] * e1) / det
    return np.stack([x, y], axis=1)


def resid_ED(p, D, pk, base, report=None):
    """Exact raw-space EIV. q_i is the U^-1 preimage of the corrected-space constraint point."""
    th = pk.theta(p, base)
    nvec, e = _line_nd(p, pk)
    blocks = _blocks(D)
    qc = np.zeros((D.n, 2))
    ti = 0
    for m, idx in blocks.items():
        if m == 0:
            continue
        li = np.array([D.obs_lines[i] for i in idx], int)
        if m >= 2:
            qc[idx] = _intersect(nvec[li[:, 0]], e[li[:, 0]], nvec[li[:, 1]], e[li[:, 1]])
        else:
            g = li[:, 0]
            n1 = nvec[g]
            foot = n1 * e[g][:, None]
            tang = np.stack([-n1[:, 1], n1[:, 0]], axis=1)
            t = p[pk.it + ti:pk.it + ti + len(idx)]
            ti += len(idx)
            qc[idx] = foot + tang * t[:, None]
    q, conv, mx = LT.inv_U(qc + CENTRE, th)
    if report is not None:
        report["inv_max_residual"] = mx
        report["inv_all_converged"] = bool(conv.all())
    r = (D.xy - q) * np.sqrt(D.w)[:, None]
    return r.ravel()


def _apply_H(h, lat):
    """h is 8 parameters, h22 fixed to 1; lat is (n, 2) normalized lattice coordinates (c, r)."""
    H = np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])
    w = H[2, 0] * lat[:, 0] + H[2, 1] * lat[:, 1] + H[2, 2]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    return np.stack([(H[0, 0] * lat[:, 0] + H[0, 1] * lat[:, 1] + H[0, 2]) / w,
                     (H[1, 0] * lat[:, 0] + H[1, 1] * lat[:, 1] + H[1, 2]) / w], axis=1)


def resid_PD(p, D, pk, base, report=None):
    th = pk.theta(p, base)
    pred = np.zeros((D.n, 2))
    for c in range(D.ncap):
        m = D.cap_of == c
        if not m.any():
            continue
        h = p[pk.ih + 8 * c:pk.ih + 8 * c + 8]
        pred[m] = _apply_H(h, D.lat[m]) * PXSCALE + CENTRE
    q, conv, mx = LT.inv_U(pred, th)
    if report is not None:
        report["inv_max_residual"] = mx
        report["inv_all_converged"] = bool(conv.all())
    return ((D.xy - q) * np.sqrt(D.w)[:, None]).ravel()


RESID = {"B": resid_B, "SD": resid_SD, "ED": resid_ED, "PD": resid_PD}


# =============================================================== exact PD, fast path
#
# The SAME estimator, fitted point set, Delaunay weights and residual as resid_PD:
#
#     z_vi = pi(H_v s_vi),   q_vi = U_theta^-1(z_vi),   r_vi = sqrt(a_vi) (x_vi - q_vi)
#
# What changes is only how it is computed. resid_PD spends 87 percent of its time in LT.inv_U because
# that routine seeds Newton at q = z. In CORRECTED space z sits at up to twice the radius of the data
# (measured: 2069 px against 1015 px on Left), which is outside the annulus the seven-term radial
# polynomial was fitted over, and out there the polynomial runs away -- |U(z) - z| reaches 1.5e5 px and
# Newton converges LINEARLY at about 0.35 per step, taking 11 steps. Seeding at q = x instead starts
# 8 to 14 px from the answer, inside the annulus, and converges quadratically: measured 1e-2, 1e-6,
# 1e-13 over three steps with no point of either camera needing a fourth, at three different parameter
# states each. Combined with one shared kernel for U, J_U and dU/dtheta, and an analytic Jacobian that
# removes SciPy's hidden finite-difference passes, that is where the speedup comes from.


def _hartley(P):
    """Hartley normalization: centroid to the origin, mean distance from it to sqrt(2)."""
    P = np.asarray(P, float)
    mu = P.mean(axis=0)
    md = float(np.linalg.norm(P - mu, axis=1).mean())
    sc = math.sqrt(2.0) / md if md > 1e-12 else 1.0
    return np.array([[sc, 0.0, -sc * mu[0]], [0.0, sc, -sc * mu[1]], [0.0, 0.0, 1.0]])


def _solve2(J, rhs, det_floor=1e-10):
    """Batched 2x2 solve by the adjugate. J is (n, 2, 2); rhs is (n, 2) or (n, 2, m).

    Returns (solution, n_unsafe). A generic stacked np.linalg.solve is both slower here and hides a
    singular block behind an exception; the adjugate lets the caller SEE how many blocks were unsafe.
    """
    a = J[:, 0, 0]; b = J[:, 0, 1]; c = J[:, 1, 0]; d = J[:, 1, 1]
    det = a * d - b * c
    bad = ~np.isfinite(det) | (np.abs(det) < det_floor)
    nbad = int(bad.sum())
    if nbad:
        det = np.where(bad, det_floor, det)
    if rhs.ndim == 2:
        return np.stack([(d * rhs[:, 0] - b * rhs[:, 1]) / det,
                         (a * rhs[:, 1] - c * rhs[:, 0]) / det], axis=1), nbad
    dn = det[:, None]
    return np.stack([(d[:, None] * rhs[:, 0, :] - b[:, None] * rhs[:, 1, :]) / dn,
                     (a[:, None] * rhs[:, 1, :] - c[:, None] * rhs[:, 0, :]) / dn], axis=1), nbad


def u_kernel(x, th14, dtheta=None):
    """U, J_U and optionally dU/dtheta at x, from ONE pass of shared intermediates.

    Returns (U, J_U, dU) with dU of shape (n, 2, len(dtheta)) in RAW theta units, or None.

    U is written in exactly the association order of parity_step5.undistort_conjugated, so at equal
    parameters this agrees with LT.U bit-for-bit whenever eta != 0, and to round-off at eta = 0 where
    LT.U delegates to fitter.undistort's differently-associated spelling.

    dU/dtheta, all closed form:
      k_i    dB/dk_i = (xd s^i, yd s^i)
      p1     dB/dp1 = ((s + 2 xd^2) T, 2 xd yd T)
      p2     dB/dp2 = (2 xd yd T, (s + 2 yd^2) T)
      p3, p4 dB/dp3 = (Gx s, Gy s),  dB/dp4 = (Gx s^2, Gy s^2)
      centre U = c + A^-1 B(A(x - c)) gives dU/dc = I - J_U exactly, both occurrences of c included
      eta    with A = diag(e^eta, e^-eta), d(A^-1)/deta = -S A^-1 and dA/deta = S A for S = diag(1,-1),
             so dU/deta = -S A^-1 B + A^-1 J_B S (A(x - c)), i.e. the INPUT and OUTPUT dependence and
             the full centre dependence through the conjugation, not just one side of it.
    """
    x = np.atleast_2d(np.asarray(x, float))
    t = np.asarray(th14, float)
    ax = math.exp(t[13]); ay = 1.0 / ax
    xd = (x[:, 0] - t[0]) * ax
    yd = (x[:, 1] - t[1]) * ay
    s = xd * xd + yd * yd
    sp = np.empty((7, len(s)))                       # s^1 .. s^7, shared by R, R' and dU/dk
    acc = np.ones_like(s)
    for i in range(7):
        acc = acc * s
        sp[i] = acc
    R = np.ones_like(s); Rp = np.zeros_like(s)
    for i in range(7):
        k = t[2 + i]
        if k != 0.0:
            R = R + k * sp[i]
            Rp = Rp + (i + 1) * k * (sp[i - 1] if i else np.ones_like(s))
    p1, p2, p3, p4 = t[9], t[10], t[11], t[12]
    T = 1.0 + p3 * s + p4 * sp[1]
    Tp = p3 + 2.0 * p4 * s
    Gx = p1 * (s + 2.0 * xd * xd) + 2.0 * p2 * xd * yd
    Gy = 2.0 * p1 * xd * yd + p2 * (s + 2.0 * yd * yd)
    Bx = xd * R + Gx * T
    By = yd * R + Gy * T
    Uv = np.stack([t[0] + Bx / ax, t[1] + By / ay], axis=1)

    # J_B, then J_U = A^-1 J_B A
    jba = R + 2.0 * xd * xd * Rp + (6.0 * p1 * xd + 2.0 * p2 * yd) * T + 2.0 * xd * Gx * Tp
    jbb = 2.0 * xd * yd * Rp + (2.0 * p1 * yd + 2.0 * p2 * xd) * T + 2.0 * yd * Gx * Tp
    jbc = 2.0 * xd * yd * Rp + (2.0 * p1 * yd + 2.0 * p2 * xd) * T + 2.0 * xd * Gy * Tp
    jbd = R + 2.0 * yd * yd * Rp + (2.0 * p1 * xd + 6.0 * p2 * yd) * T + 2.0 * yd * Gy * Tp
    Ju = np.empty((len(x), 2, 2))
    Ju[:, 0, 0] = jba
    Ju[:, 0, 1] = jbb * ay / ax
    Ju[:, 1, 0] = jbc * ax / ay
    Ju[:, 1, 1] = jbd

    if dtheta is None:
        return Uv, Ju, None
    dU = np.zeros((len(x), 2, len(dtheta)))
    for j, ti in enumerate(dtheta):
        if ti == 0:                                   # centre x: dU/dc = I - J_U, first column
            dU[:, 0, j] = 1.0 - Ju[:, 0, 0]
            dU[:, 1, j] = -Ju[:, 1, 0]
        elif ti == 1:                                 # centre y: second column
            dU[:, 0, j] = -Ju[:, 0, 1]
            dU[:, 1, j] = 1.0 - Ju[:, 1, 1]
        elif 2 <= ti <= 8:                            # k_1 .. k_7
            dU[:, 0, j] = xd * sp[ti - 2] / ax
            dU[:, 1, j] = yd * sp[ti - 2] / ay
        elif ti == 9:                                 # p1
            dU[:, 0, j] = (s + 2.0 * xd * xd) * T / ax
            dU[:, 1, j] = 2.0 * xd * yd * T / ay
        elif ti == 10:                                # p2
            dU[:, 0, j] = 2.0 * xd * yd * T / ax
            dU[:, 1, j] = (s + 2.0 * yd * yd) * T / ay
        elif ti == 11:                                # p3
            dU[:, 0, j] = Gx * s / ax
            dU[:, 1, j] = Gy * s / ay
        elif ti == 12:                                # p4
            dU[:, 0, j] = Gx * sp[1] / ax
            dU[:, 1, j] = Gy * sp[1] / ay
        elif ti == 13:                                # conjugated eta, both sides plus the centre
            dU[:, 0, j] = (-Bx + jba * xd - jbb * yd) / ax
            dU[:, 1, j] = (By + jbc * xd - jbd * yd) / ay
        else:
            raise ValueError(f"theta index {ti} out of range")
    return Uv, Ju, dU


class PDExact:
    """The exact PD objective, Hartley-normalized homography chart, analytic Jacobian.

    Parameter vector p is [free model block] + [8 per capture], the 8 being the normalized homography
    read row-major with h33 fixed to 1:

        s_hat = T_s (r, c, 1),   z_hat = pi(H_hat s_hat),   z = T_x^-1 z_hat,   H = T_x^-1 H_hat T_s

    T_s comes from the integer lattice indices of each capture and T_x from that capture's raw observed
    points. Both are frozen at construction from the data and never depend on theta, so the chart is a
    fixed reparameterization and the objective stays a pure function of p.
    """

    def __init__(self, D, model, base=None, free=None, newton_steps=3, newton_max=6,
                 newton_tol=1e-9, w=None, zero_held=True):
        self.D = D
        self.model = model
        self.free = list(MODELS[model] if free is None else free)
        self.nm = len(self.free)
        self.ncap = D.ncap
        self.n = D.n
        self.npar = self.nm + 8 * self.ncap
        self.ih = self.nm
        self.newton_steps = newton_steps
        self.newton_max = newton_max
        self.newton_tol = newton_tol
        b = default_base() if base is None else np.asarray(base, float).copy()
        held = [j for j in range(14) if j not in set(self.free)]
        self._base = b
        # zero_held mirrors fit()'s flag. True means a reduced model's omitted terms are exactly zero.
        # False is the case where base carries values that must SURVIVE -- holding eta at a nonzero
        # value, or profiling nuisances at a fixed given map. Zeroing then would silently refit a
        # different model, which is how the first eta profile came out perfectly flat.
        self._held = held if zero_held else []
        self.zero_held = zero_held
        self.scl = SCALE14[self.free]                        # optimizer-coordinate chain rule
        # a_i. Delaunay area quadrature by default; w=1 gives the uniform-point-weight variant. The
        # weights are frozen per evaluator, so a map can be SCORED under weights it was not fitted to.
        self.w = np.asarray(D.w, float) if w is None else np.broadcast_to(
            np.asarray(w, float), (D.n,)).copy()
        self.sw = np.sqrt(self.w)                            # applied once per 2-D point block

        # frozen per-capture normalizations, and the normalized source points
        self.Ts, self.Tx, self.Txinv, self.Mx = [], [], [], []
        self.shat = np.zeros((D.n, 3))
        for c in range(self.ncap):
            m = D.cap_of == c
            if not m.any():
                self.Ts.append(np.eye(3)); self.Tx.append(np.eye(3))
                self.Txinv.append(np.eye(3)); self.Mx.append(np.eye(2)); continue
            Ts = _hartley(D.rc[m]); Tx = _hartley(D.xy[m])
            self.Ts.append(Ts); self.Tx.append(Tx)
            self.Txinv.append(np.linalg.inv(Tx))
            self.Mx.append(np.linalg.inv(Tx[:2, :2]))        # the block actually constructed
            src = np.concatenate([D.rc[m], np.ones((int(m.sum()), 1))], axis=1)
            self.shat[m] = src @ Ts.T
        self.capmask = [D.cap_of == c for c in range(self.ncap)]
        self.reset_counters()
        self._cache = {}

    # ------------------------------------------------------------------ counters
    def reset_counters(self):
        self.C = {"fun": 0, "jac": 0, "kernel": 0, "newton_steps": 0, "newton_fallbacks": 0,
                  "inverse_failures": 0, "unsafe_det": 0, "cache_hits": 0, "project": 0}
        self.T = {"inverse": 0.0, "jac_build": 0.0, "project": 0.0, "fun": 0.0, "jac": 0.0}
        self.worst_inverse = 0.0

    # ------------------------------------------------------------------ parameters
    def theta(self, p):
        th = np.asarray(self._base, float).copy()
        th[self._held] = 0.0
        th[self.free] = np.asarray(p, float)[:self.nm]
        return th * SCALE14

    def Hhat(self, p, c):
        h = np.asarray(p, float)[self.ih + 8 * c:self.ih + 8 * c + 8]
        return np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])

    def H_physical(self, p, c):
        """H mapping homogeneous lattice (r, c, 1) to CORRECTED pixels, scale-normalized by H33."""
        H = self.Txinv[c] @ self.Hhat(p, c) @ self.Ts[c]
        return H / H[2, 2] if abs(H[2, 2]) > 1e-30 else H

    def bounds(self):
        lo = np.full(self.npar, -np.inf); hi = np.full(self.npar, np.inf)
        for j, f in enumerate(self.free):
            if f == 13:
                lo[j] = -ETA_BOUND / ETA_SCALE
                hi[j] = +ETA_BOUND / ETA_SCALE
        return lo, hi

    # ------------------------------------------------------------------ chart conversion
    def hhat_from_physical(self, H, c):
        """The 8 normalized parameters representing a given physical H. Inverse of H_physical."""
        Hh = self.Tx[c] @ np.asarray(H, float) @ np.linalg.inv(self.Ts[c])
        return (Hh / Hh[2, 2]).ravel()[:8]

    def physical_from_old(self, h_old, c):
        """The physical H of resid_PD's chart: rc -> lat -> pi(H_old) -> * PXSCALE + CENTRE."""
        li = self.D.latinfo[c]
        mu = np.asarray(li["mu"], float); sd = np.asarray(li["sd"], float)
        S = np.array([[1.0 / sd[0], 0.0, -mu[0] / sd[0]],
                      [0.0, 1.0 / sd[1], -mu[1] / sd[1]], [0.0, 0.0, 1.0]])
        h = np.asarray(h_old, float)
        Ho = np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])
        K = np.array([[PXSCALE, 0.0, CENTRE[0]], [0.0, PXSCALE, CENTRE[1]], [0.0, 0.0, 1.0]])
        H = K @ Ho @ S
        return H / H[2, 2] if abs(H[2, 2]) > 1e-30 else H

    def p_from_old(self, p_old, pk):
        """Translate a resid_PD parameter vector into this chart at the SAME physical map."""
        p = np.zeros(self.npar)
        p[:self.nm] = np.asarray(p_old, float)[:pk.nm]
        for c in range(self.ncap):
            h_old = np.asarray(p_old, float)[pk.ih + 8 * c:pk.ih + 8 * c + 8]
            p[self.ih + 8 * c:self.ih + 8 * c + 8] = self.hhat_from_physical(
                self.physical_from_old(h_old, c), c)
        return p

    # ------------------------------------------------------------------ initialization
    def init_dlt(self, th14):
        """Normalized DLT per capture from the line-fit distortion parameters, in this chart."""
        u = LT.U(self.D.xy, np.asarray(th14, float))
        p = np.zeros(self.npar)
        p[:self.nm] = np.asarray(th14, float)[self.free] / SCALE14[self.free]
        for c in range(self.ncap):
            m = self.capmask[c]
            if not m.any():
                p[self.ih + 8 * c:self.ih + 8 * c + 8] = [1, 0, 0, 0, 1, 0, 0, 0]; continue
            A = self.shat[m]
            Bz = (np.concatenate([u[m], np.ones((int(m.sum()), 1))], axis=1) @ self.Tx[c].T)[:, :2]
            k = len(A)
            M = np.zeros((2 * k, 9))
            M[0::2, 0:3] = -A
            M[1::2, 3:6] = -A
            M[0::2, 6:9] = Bz[:, 0:1] * A
            M[1::2, 6:9] = Bz[:, 1:2] * A
            _, _, Vt = np.linalg.svd(M, full_matrices=False)
            Hh = Vt[-1].reshape(3, 3)
            if abs(Hh[2, 2]) < 1e-30:
                raise RuntimeError(f"capture {c}: DLT put the lattice centroid on the horizon, "
                                   f"so h33 = 1 is not a valid chart here")
            p[self.ih + 8 * c:self.ih + 8 * c + 8] = (Hh / Hh[2, 2]).ravel()[:8]
        return p

    # ------------------------------------------------------------------ the objective
    def project(self, p):
        """z = pi(H s) in corrected pixels, plus the pieces the h-derivative needs."""
        t0 = time.perf_counter()
        z = np.zeros((self.n, 2))
        zh = np.zeros((self.n, 2))
        w = np.zeros(self.n)
        for c in range(self.ncap):
            m = self.capmask[c]
            if not m.any():
                continue
            wv = self.shat[m] @ self.Hhat(p, c).T                  # (u, v, w)
            w[m] = wv[:, 2]
            zh[m] = wv[:, :2] / wv[:, 2:3]
            z[m] = (np.concatenate([zh[m], np.ones((int(m.sum()), 1))], axis=1)
                    @ self.Txinv[c].T)[:, :2]
        self.C["project"] += 1
        self.T["project"] += time.perf_counter() - t0
        return z, zh, w

    def _state(self, p):
        """Residual state at p, with the inverse solved to tolerance. Pure exact-value cache."""
        key = np.asarray(p, float).tobytes()
        hit = self._cache.get(key)
        if hit is not None:
            self.C["cache_hits"] += 1
            return hit
        th = self.theta(p)
        z, zh, wden = self.project(p)
        t0 = time.perf_counter()
        # deterministic inverse: always q0 = x, never a warm start from another iterate
        q = self.D.xy.copy()
        Uq, Ju, _ = u_kernel(q, th)
        self.C["kernel"] += 1
        nst = 0
        fell_back = False
        while True:
            r = Uq - z
            mx = float(np.abs(r).max())
            if nst >= self.newton_steps and mx < self.newton_tol:
                break
            if nst >= self.newton_max:
                self.C["inverse_failures"] += 1
                break
            if nst >= self.newton_steps and not fell_back:
                fell_back = True
                self.C["newton_fallbacks"] += 1
            dq, nb = _solve2(Ju, r)
            self.C["unsafe_det"] += nb
            q = q - dq
            nst += 1
            # U, J_U and later dU/dtheta are always recomputed at the FINAL updated q
            Uq, Ju, _ = u_kernel(q, th)
            self.C["kernel"] += 1
        self.C["newton_steps"] += nst
        self.worst_inverse = max(self.worst_inverse, mx)
        self.T["inverse"] += time.perf_counter() - t0
        st = {"p": np.asarray(p, float).copy(), "th": th, "z": z, "zh": zh, "wden": wden,
              "q": q, "Ju": Ju, "inv_res": mx, "newton_steps": nst, "fallback": fell_back,
              "r": ((self.D.xy - q) * self.sw[:, None]).ravel()}
        self._cache = {key: st}                                   # one exact iterate, no warm start
        return st

    def fun(self, p):
        t0 = time.perf_counter()
        st = self._state(p)
        self.C["fun"] += 1
        self.T["fun"] += time.perf_counter() - t0
        return st["r"]

    def jac(self, p):
        """Exact residual Jacobian by implicit differentiation of U(q) = z(H) at the converged q.

            dr/dtheta = +sqrt(a) J_U(q)^-1 dU/dtheta(q)
            dr/dh     = -sqrt(a) J_U(q)^-1 dz/dh

        The Newton iterations are NOT differentiated through: q is defined implicitly, and the
        dependence of J_U on q enters only the second derivatives.
        """
        t0 = time.perf_counter()
        st = self._state(p)
        th = st["th"]
        # recompute dU/dtheta at the FINAL q, alongside a fresh J_U from the same intermediates
        _, Ju, dU = u_kernel(st["q"], th, dtheta=self.free)
        self.C["kernel"] += 1
        t1 = time.perf_counter()
        J = np.zeros((2 * self.n, self.npar))
        if self.nm:
            dq, nb = _solve2(Ju, dU)                              # (n, 2, nm)
            self.C["unsafe_det"] += nb
            blk = dq * (self.sw[:, None, None] * self.scl[None, None, :])
            J[0::2, :self.nm] = blk[:, 0, :]
            J[1::2, :self.nm] = blk[:, 1, :]
        for c in range(self.ncap):
            m = self.capmask[c]
            if not m.any():
                continue
            sh = self.shat[m]; zh = st["zh"][m]; w = st["wden"][m]
            k = len(sh)
            dzh = np.zeros((k, 2, 8))                             # d z_hat / d h_hat
            s1, s2, s3 = sh[:, 0] / w, sh[:, 1] / w, sh[:, 2] / w
            dzh[:, 0, 0] = s1; dzh[:, 0, 1] = s2; dzh[:, 0, 2] = s3
            dzh[:, 1, 3] = s1; dzh[:, 1, 4] = s2; dzh[:, 1, 5] = s3
            dzh[:, 0, 6] = -zh[:, 0] * s1; dzh[:, 0, 7] = -zh[:, 0] * s2
            dzh[:, 1, 6] = -zh[:, 1] * s1; dzh[:, 1, 7] = -zh[:, 1] * s2
            dz = np.einsum("ij,kjm->kim", self.Mx[c], dzh)        # back through T_x^-1's 2x2 block
            dqh, nb = _solve2(Ju[m], dz)
            self.C["unsafe_det"] += nb
            blk = -dqh * self.sw[m][:, None, None]
            rows = np.where(m)[0]
            cols = slice(self.ih + 8 * c, self.ih + 8 * c + 8)
            J[2 * rows, cols] = blk[:, 0, :]
            J[2 * rows + 1, cols] = blk[:, 1, :]
        self.C["jac"] += 1
        self.T["jac_build"] += time.perf_counter() - t1
        self.T["jac"] += time.perf_counter() - t0
        return J

    def loss(self, p):
        r = self.fun(p)
        return float(r @ r)

    def horizon_report(self, p):
        """How close the fitted lattice points come to the projective horizon w = 0."""
        _, _, w = self.project(p)
        out = []
        for c in range(self.ncap):
            m = self.capmask[c]
            if not m.any():
                continue
            out.append({"capture": c, "w_min": float(np.abs(w[m]).min()),
                        "w_max": float(np.abs(w[m]).max()),
                        "sign_consistent": bool((w[m] > 0).all() or (w[m] < 0).all()),
                        "h33_valid": True})
        return out

    def projected_conditioning(self, p):
        """Singular values of the model block after the homography directions are projected out.

        The spectrum of (I - P_h) J_theta: the model sensitivity the nuisance homographies cannot
        absorb. Exact, because J is analytic.
        """
        J = self.jac(p)
        Jm = J[:, :self.nm].copy()
        Jn = J[:, self.nm:]
        if Jn.shape[1] and self.nm:
            Q, _ = np.linalg.qr(Jn)
            Jm = Jm - Q @ (Q.T @ Jm)
        if not self.nm:
            return {"sv": [], "sv_max": float("nan"), "sv_min": float("nan"),
                    "condition": float("nan")}
        sv = np.linalg.svd(Jm, compute_uv=False)
        return {"sv": [float(v) for v in sv], "sv_max": float(sv[0]), "sv_min": float(sv[-1]),
                "condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")}

    def param_uncertainty(self, p, j):
        """Linearized sd and profiled curvature of free parameter j, all other directions removed.

        Projects column j of the analytic Jacobian orthogonal to EVERY other column, model and
        homography alike. The profiled curvature of the loss is then 2 |v|^2 and the linearized
        standard error is s / |v|, with s^2 the residual variance. This is the honest uncertainty of a
        weakly identified parameter: it asks what is left of its sensitivity once everything else,
        including the projective nuisances, has adjusted.
        """
        J = self.jac(p)
        r = self.fun(p)
        col = J[:, j].copy()
        rest = np.delete(J, j, axis=1)
        Q, _ = np.linalg.qr(rest)
        v = col - Q @ (Q.T @ col)
        nv = float(np.linalg.norm(v))
        dof = max(len(r) - self.npar, 1)
        s2 = float(r @ r) / dof
        return {"projected_norm": nv, "curvature": 2.0 * nv ** 2,
                "sd_optimizer_units": (math.sqrt(s2) / nv) if nv > 0 else float("inf"),
                "sd_raw_units": (math.sqrt(s2) / nv * SCALE14[self.free[j]]) if nv > 0
                else float("inf"), "residual_variance": s2, "dof": dof}

    def fit(self, p0, max_nfev=200, x_scale=1.0, verbose=0, ftol=1e-14, xtol=1e-14, gtol=1e-12):
        lo, hi = self.bounds()
        t0 = time.time()
        res = least_squares(self.fun, np.clip(np.asarray(p0, float), lo, hi), jac=self.jac,
                            bounds=(lo, hi), method="trf", tr_solver="exact", x_scale=x_scale,
                            ftol=ftol, xtol=xtol, gtol=gtol, max_nfev=max_nfev, verbose=verbose)
        return res, time.time() - t0


def profile_H(D, th14, w=None, max_nfev=200):
    """Exact PD with the distortion map HELD at th14 and only the homographies optimized.

    This is how a map is SCORED fairly under a weighting it was not fitted to: the homographies are
    nuisance parameters, so leaving them at another fit's values would charge the map for a projective
    misalignment rather than for its shape. free = [] means every theta entry comes from base and must
    survive, hence zero_held=False.

    Returns (loss, evaluator, p). The evaluator carries the residual state for diagnostics.
    """
    th14 = np.asarray(th14, float)
    ev = PDExact(D, "M1", base=th14 / SCALE14, free=[], w=w, zero_held=False)
    p0 = ev.init_dlt(th14)
    res, dt = ev.fit(p0, max_nfev=max_nfev)
    return float(2 * res.cost), ev, res.x


# =============================================================== initialization and sparsity


def init_lines(D, th):
    """Total-least-squares initial (phi, e) for every retained line, in corrected coordinates."""
    u = {}
    for ci, C in enumerate(D.caps):
        u[ci] = LT.U(C.xy, th) - CENTRE
    ph = np.zeros(D.nline); e = np.zeros(D.nline)
    for (ci, li), gi in D.gline.items():
        mem = [m for m in D.caps[ci].lines[li]["members"] if D.sel[ci][m]]
        P = u[ci][mem]
        cen = P.mean(axis=0)
        q = P - cen
        t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                             float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        nv = np.array([-math.sin(t), math.cos(t)])
        ph[gi] = math.atan2(nv[1], nv[0])
        e[gi] = float(nv @ cen)
    return ph, e


def init_t(D, th, ph, e):
    """Initial latent coordinates for singly constrained observations."""
    u = LT.U(D.xy, th) - CENTRE
    out = []
    for i, ls in enumerate(D.obs_lines):
        if len(ls) != 1:
            continue
        g = ls[0]
        nv = np.array([math.cos(ph[g]), math.sin(ph[g])])
        tang = np.array([-nv[1], nv[0]])
        out.append(float(tang @ u[i]))
    return np.array(out)


def init_H(D, th):
    """DLT initialization of one homography per capture, from normalized lattice to normalized
    corrected coordinates."""
    u = (LT.U(D.xy, th) - CENTRE) / PXSCALE
    hs = []
    for c in range(D.ncap):
        m = D.cap_of == c
        if not m.any():
            hs.append(np.array([1, 0, 0, 0, 1, 0, 0, 0], float)); continue
        A = D.lat[m]; B = u[m]
        M = np.zeros((2 * len(A), 9))
        for i in range(len(A)):
            x, y = A[i]; uu, vv = B[i]
            M[2 * i] = [-x, -y, -1, 0, 0, 0, uu * x, uu * y, uu]
            M[2 * i + 1] = [0, 0, 0, -x, -y, -1, vv * x, vv * y, vv]
        _, _, Vt = np.linalg.svd(M)
        Hm = Vt[-1].reshape(3, 3)
        if abs(Hm[2, 2]) > 1e-30:
            Hm = Hm / Hm[2, 2]
        hs.append(Hm.ravel()[:8])
    return np.concatenate(hs)


def sparsity(D, pk, nres):
    """Jacobian sparsity. Model parameters are dense; a line or homography parameter touches only its
    own observations. This is what keeps the exact objectives practically usable."""
    S = lil_matrix((nres, pk.n), dtype=int)
    S[:, :pk.nm] = 1
    if pk.objective in ("SD", "ED"):
        # residual rows: SD is grouped by block size, ED is 2 per observation in order
        if pk.objective == "ED":
            for i, ls in enumerate(D.obs_lines):
                for g in ls:
                    S[2 * i, pk.iline + g] = 1
                    S[2 * i, pk.iline + pk.nline + g] = 1
                    S[2 * i + 1, pk.iline + g] = 1
                    S[2 * i + 1, pk.iline + pk.nline + g] = 1
            ti = 0
            for i, ls in enumerate(D.obs_lines):
                if len(ls) == 1:
                    S[2 * i, pk.it + ti] = 1
                    S[2 * i + 1, pk.it + ti] = 1
                    ti += 1
        else:
            row = 0
            for m, idx in _blocks(D).items():
                if m == 0:
                    continue
                for i in idx:
                    for _ in range(m):
                        for g in D.obs_lines[i]:
                            S[row, pk.iline + g] = 1
                            S[row, pk.iline + pk.nline + g] = 1
                        row += 1
    if pk.objective == "PD":
        for i in range(D.n):
            c = D.cap_of[i]
            S[2 * i, pk.ih + 8 * c:pk.ih + 8 * c + 8] = 1
            S[2 * i + 1, pk.ih + 8 * c:pk.ih + 8 * c + 8] = 1
    return S.tocsr()


# =============================================================== the fit driver


def fit(D, objective, model, base=None, x0_model=None, verbose=0, max_nfev=3000, warm=True,
        free=None, zero_held=True):
    """Fit `model` under `objective`. Returns a dict with theta14, loss, timing and diagnostics.

    `warm` warm-starts the model block from a B fit of the same data. That is not cosmetic. From an
    undistorted start the corrected points are still strongly curved, the total-least-squares line
    initialization is therefore far from any optimum, and SD and ED both stalled at a loss of 2.66 on
    exactly consistent synthetic data where the true minimum is 1e-24. B costs a tenth of a second and
    lands in the right neighbourhood, after which the exact objectives converge quickly.
    """
    base = default_base() if base is None else np.asarray(base, float).copy()
    if warm and objective != "B" and x0_model is None:
        wb = fit(D, "B", model, base=base, warm=False, max_nfev=max_nfev, free=free,
                 zero_held=zero_held)
        fr = MODELS[model] if free is None else list(free)
        x0_model = np.array(wb["theta14"], float)[fr] / SCALE14[fr]
    fr = MODELS[model] if free is None else list(free)
    held = [j for j in range(14) if j not in set(fr)]
    if zero_held:
        # A reduced model means the omitted terms are exactly zero. But holding eta at a fixed
        # NONZERO value for a profile also arrives here with 13 held, and zeroing it would silently
        # refit the eta = 0 model at every grid point -- which is exactly how the first attempt at an
        # eta profile came out perfectly flat. zero_held=False is the profile case.
        base[held] = 0.0
    pk = Pack(model, nline=D.nline, ncap=D.ncap,
              nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective=objective, free=fr)
    p0 = np.zeros(pk.n)
    p0[:pk.nm] = base[fr] if x0_model is None else np.asarray(x0_model, float)
    th0 = pk.theta(p0, base)
    if objective in ("SD", "ED"):
        ph, e = init_lines(D, th0)
        p0[pk.iline:pk.iline + pk.nline] = ph
        p0[pk.iline + pk.nline:pk.iline + 2 * pk.nline] = e
        if objective == "ED" and pk.nfree_t:
            p0[pk.it:pk.it + pk.nfree_t] = init_t(D, th0, ph, e)
    if objective == "PD":
        p0[pk.ih:] = init_H(D, th0)

    rep = {}
    fn = RESID[objective]

    def rr(p):
        return fn(p, D, pk, base, **({"report": rep} if objective != "B" else {}))

    r0 = rr(p0)
    lo, hi = pk.bounds(base)
    sp = sparsity(D, pk, len(r0)) if objective != "B" else None
    t0 = time.time()
    res = least_squares(rr, np.clip(p0, lo, hi), bounds=(lo, hi), method="trf", x_scale="jac",
                        jac_sparsity=sp, ftol=1e-14, xtol=1e-14, gtol=1e-14,
                        max_nfev=max_nfev, verbose=verbose)
    dt = time.time() - t0
    th = pk.theta(res.x, base)
    r = rr(res.x)
    return {"objective": objective, "model": model, "theta14": th.tolist(),
            "p": res.x.tolist(), "pack": pk, "loss0": float(r0 @ r0), "loss": float(r @ r),
            "nres": len(r), "nparam": pk.n, "status": int(res.status),
            "optimality": float(res.optimality), "nfev": int(res.nfev),
            "runtime_s": dt, "eta": float(th[13]), "report": dict(rep),
            "warm_started": bool(warm and objective != "B"),
            "at_eta_bound": bool(13 in fr and abs(abs(th[13]) - ETA_BOUND) < 1e-9)}


def loss_at(D, objective, model, th14, base=None, profile=True):
    """Objective value at a GIVEN map, with nuisances re-profiled (so the map is judged fairly)."""
    base = np.asarray(th14, float) / SCALE14
    pk = Pack(model, nline=D.nline, ncap=D.ncap,
              nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective=objective)
    p0 = np.zeros(pk.n)
    p0[:pk.nm] = base[MODELS[model]]
    th0 = np.asarray(th14, float)
    if objective in ("SD", "ED"):
        ph, e = init_lines(D, th0)
        p0[pk.iline:pk.iline + pk.nline] = ph
        p0[pk.iline + pk.nline:pk.iline + 2 * pk.nline] = e
        if objective == "ED" and pk.nfree_t:
            p0[pk.it:pk.it + pk.nfree_t] = init_t(D, th0, ph, e)
    if objective == "PD":
        p0[pk.ih:] = init_H(D, th0)
    fn = RESID[objective]
    rep = {}

    def rr(p):
        return fn(p, D, pk, base, **({"report": rep} if objective != "B" else {}))

    if not profile or objective == "B":
        r = rr(p0)
        return float(r @ r), p0
    nuis = np.arange(pk.nm, pk.n)
    if len(nuis) == 0:
        r = rr(p0)
        return float(r @ r), p0

    def rn(q):
        p = p0.copy(); p[nuis] = q
        return fn(p, D, pk, base, **({"report": rep} if objective != "B" else {}))

    res = least_squares(rn, p0[nuis], method="trf", x_scale="jac",
                        jac_sparsity=sparsity(D, pk, len(rr(p0)))[:, nuis],
                        ftol=1e-12, xtol=1e-12, gtol=1e-12)
    p = p0.copy(); p[nuis] = res.x
    r = rr(p)
    return float(r @ r), p
