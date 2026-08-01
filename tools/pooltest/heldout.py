#!/usr/bin/env python3
"""THE shared observed-pixel held-out scorer and the deterministic fold families.

Frozen against corpus_freeze analysis_config_sha256 = 97fccf0e8d0caf66.

WHY OBSERVED PIXELS. Scoring in corrected space rewards a map merely for contracting the coordinate
system: shrink the undistorted image and every corrected-space residual shrinks with it, at no cost in
physical fidelity. So the primary criterion maps the prediction BACK through the fitted map and scores
in the original observed pixels, where a pixel means the same thing for every candidate:

    u_i = C(x_i)                     correct the TRAINING detections only
    H   = argmin |H(q_i) - u_i|      nuisance homography, TRAINING nodes only
    x_j = C^-1(H(q_j))               predict a HELD-OUT node, back in observed pixels
    r_j = |x_j - x_j^observed|

Corrected-space residuals are also returned, for diagnosis only.

FAIL CLOSED ON THE INVERSE. `lattice.inv_U` returns a per-point convergence mask. If any held-out
prediction fails to invert, the fold is marked invalid and reported; it is NEVER scored on the subset
that happened to converge, because dropping the hard points is exactly the bias this score exists to
avoid.

GAUGE CANONICALIZATION IS WHAT MAKES FOLDS ORDER-INDEPENDENT. Consensus indexing pins one observation
per component to (0, 0), and which observation that is depends on the observation numbering, which
follows the operator's record order. Raw indices are therefore NOT a stable fold key. `canonical_rc`
removes the whole gauge -- translation, axis swap and sign -- using image geometry alone, so the same
physical corner lands in the same fold no matter how the lines were clicked or stored.

NO CALIBRATION OPTIMIZATION IS NEEDED TO TEST ANY OF THIS. The scorer takes a map as an argument and
the folds take only lattice indices, so `test_heldout.py` exercises both against closed-form maps.
"""

import hashlib
import json

import numpy as np

import harness_import

LT = harness_import.load("lattice")

# ------------------------------------------------------------------ predeclared fold parameters
BLOCK_SIZE = 3          # contiguous BLOCK_SIZE x BLOCK_SIZE lattice blocks
N_BLOCK_FOLDS = 5       # interleaved so every fold is distributed across the frame
RING_DEPTH = 2          # outer-ring holdout: nodes within this many index steps of the lattice border
LINE_STRIDE = 4         # whole-line holdout: every LINE_STRIDE-th canonical row and column
# Eligibility, declared BEFORE fitting and applied identically to every estimator and model.
MIN_TRAIN = 40          # a homography needs 4; 40 keeps the nuisance fit from being the bottleneck
MIN_TEST = 8
MIN_TRAIN_SPAN = 3      # training nodes must span >= 3 distinct canonical rows AND columns
INVERSE_TOL_PX = 1e-6   # round-trip tolerance for a prediction to count as invertible


def canonical_rc(C, mask):
    """Gauge-free integer lattice indices for the selected observations of one capture.

    Removes the three gauge freedoms in a way that depends only on image geometry:

      AXIS ASSIGNMENT  whichever index axis correlates more strongly with image x becomes the column;
                       the other becomes the row. Ties (exactly equal |correlation|) go to the first
                       axis, which is deterministic because the comparison is on magnitudes.
      SIGN             each axis is flipped if needed so it increases with its image coordinate.
      TRANSLATION      each axis is shifted so its minimum is 0.

    None of these depends on record order, click direction, or which observation the solver happened
    to pin. Returns an integer array aligned with `np.where(mask)[0]`.
    """
    rc = np.asarray(C.rc[mask], float)
    xy = np.asarray(C.xy[mask], float)
    if len(rc) == 0:
        return np.zeros((0, 2), int)
    a = rc - rc.mean(axis=0)
    p = xy - xy.mean(axis=0)

    def corr(i, j):
        d = np.sqrt((a[:, i] ** 2).sum() * (p[:, j] ** 2).sum())
        return 0.0 if d < 1e-12 else float((a[:, i] * p[:, j]).sum() / d)

    # which lattice axis is the "column" (the one tracking image x)?
    col_axis = 0 if abs(corr(0, 0)) >= abs(corr(1, 0)) else 1
    row_axis = 1 - col_axis
    out = np.column_stack([rc[:, row_axis], rc[:, col_axis]])
    if corr(row_axis, 1) < 0:
        out[:, 0] = -out[:, 0]
    if corr(col_axis, 0) < 0:
        out[:, 1] = -out[:, 1]
    out = np.rint(out).astype(int)
    out[:, 0] -= out[:, 0].min()
    out[:, 1] -= out[:, 1].min()
    return out


def _eligible(C):
    """Observations usable at all: consistently indexed and in the largest indexed component."""
    ok = C.indexed()
    if not ok.any():
        return np.zeros(C.n, bool)
    comps = {}
    for i in np.where(ok)[0]:
        comps[int(C.component[i])] = comps.get(int(C.component[i]), 0) + 1
    best = max(comps, key=lambda k: (comps[k], -k))
    return ok & (C.component == best)


def folds_for_capture(C):
    """Every predeclared fold for one capture, as boolean held-out masks over C's observations.

    Fold membership is a pure function of the canonical lattice index, so it is identical for every
    estimator and every model, and unchanged by record or click order.
    """
    elig = _eligible(C)
    idx = np.where(elig)[0]
    out = []
    if len(idx) == 0:
        return out
    rc = canonical_rc(C, elig)
    r, c = rc[:, 0], rc[:, 1]

    # 1. spatially interleaved contiguous blocks
    bid = (r // BLOCK_SIZE) + (c // BLOCK_SIZE)
    for k in range(N_BLOCK_FOLDS):
        m = np.zeros(C.n, bool)
        m[idx[(bid % N_BLOCK_FOLDS) == k]] = True
        out.append(dict(family="block", name=f"block{k}", test=m))

    # 2. outer ring / corners: extrapolation beyond the central training support
    m = np.zeros(C.n, bool)
    m[idx[(r < r.min() + RING_DEPTH) | (r > r.max() - RING_DEPTH) |
          (c < c.min() + RING_DEPTH) | (c > c.max() - RING_DEPTH)]] = True
    out.append(dict(family="outer_ring", name="outer_ring", test=m))

    # 3. genuine whole-line holdouts: complete canonical rows, and complete canonical columns
    m = np.zeros(C.n, bool)
    m[idx[(r % LINE_STRIDE) == (r.min() % LINE_STRIDE)]] = True
    out.append(dict(family="whole_line", name="whole_rows", test=m))
    m = np.zeros(C.n, bool)
    m[idx[(c % LINE_STRIDE) == (c.min() % LINE_STRIDE)]] = True
    out.append(dict(family="whole_line", name="whole_cols", test=m))

    for f in out:
        f["train"] = elig & ~f["test"]
        f["eligible"], f["reason"] = _fold_eligible(C, f["train"], f["test"])
    return out


def _fold_eligible(C, train, test):
    if int(test.sum()) < MIN_TEST:
        return False, f"test {int(test.sum())} < {MIN_TEST}"
    if int(train.sum()) < MIN_TRAIN:
        return False, f"train {int(train.sum())} < {MIN_TRAIN}"
    trc = canonical_rc(C, train)
    if len(set(trc[:, 0].tolist())) < MIN_TRAIN_SPAN or len(set(trc[:, 1].tolist())) < MIN_TRAIN_SPAN:
        return False, "training nodes span too few canonical rows or columns"
    return True, "ok"


def dlt(src, dst):
    """Normalized DLT homography src -> dst. Returns None if degenerate."""
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    if len(src) < 4:
        return None

    def norm(P):
        ctr = P.mean(axis=0)
        s = np.sqrt(2) / max(np.sqrt(((P - ctr) ** 2).sum(axis=1)).mean(), 1e-12)
        return (P - ctr) * s, np.array([[s, 0, -s * ctr[0]], [0, s, -s * ctr[1]], [0, 0, 1.0]])
    A, Ts = norm(src)
    B, Td = norm(dst)
    M = []
    for (x, y), (u, v) in zip(A, B):
        M.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        M.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    try:
        _, s, Vt = np.linalg.svd(np.array(M, float))
    except np.linalg.LinAlgError:
        return None
    if s[-1] > 1e-8 * s[0] and len(src) == 4:
        pass
    H = np.linalg.inv(Td) @ Vt[-1].reshape(3, 3) @ Ts
    return H if np.all(np.isfinite(H)) else None


def apply_H(H, P):
    Q = np.column_stack([np.asarray(P, float), np.ones(len(P))]) @ H.T
    w = Q[:, 2]
    bad = np.abs(w) < 1e-12
    w = np.where(bad, 1.0, w)
    out = Q[:, :2] / w[:, None]
    out[bad] = np.nan
    return out


def score_fold(C, th14, train, test, rc_all=None):
    """The shared observed-pixel score for one map on one fold. Fails closed; never drops points.

    `th14` is the 14-parameter map; the zero vector is the uncorrected identity baseline.
    """
    elig = train | test
    rc = canonical_rc(C, elig) if rc_all is None else rc_all
    sel = np.where(elig)[0]
    pos = {int(i): k for k, i in enumerate(sel)}
    ti = [pos[int(i)] for i in np.where(train)[0]]
    hi = [pos[int(i)] for i in np.where(test)[0]]

    x_train, x_test = C.xy[train], C.xy[test]
    q_train, q_test = rc[ti][:, ::-1].astype(float), rc[hi][:, ::-1].astype(float)

    u_train = LT.U(x_train, th14)                      # correct TRAINING detections only
    if not np.all(np.isfinite(u_train)):
        return dict(valid=False, reason="non-finite corrected training points")
    H = dlt(q_train, u_train)                          # nuisance homography, TRAINING only
    if H is None:
        return dict(valid=False, reason="degenerate training homography")
    u_hat = apply_H(H, q_test)                         # predict held-out nodes in corrected space
    if not np.all(np.isfinite(u_hat)):
        return dict(valid=False, reason="non-finite held-out prediction")

    # back to observed pixels. Seed the Newton inverse from the RAW held-out prediction, never from a
    # corrected point (see the offline-fitter notes); then require every point to have converged.
    x_hat, conv, maxres = LT.inv_U(u_hat, th14)
    if not np.all(conv) or maxres > INVERSE_TOL_PX:
        return dict(valid=False, reason="inverse map failed to converge",
                    n_failed=int((~conv).sum()), inverse_max_residual=float(maxres))

    r_obs = np.hypot(*(x_hat - x_test).T)
    u_test = LT.U(x_test, th14)
    r_cor = np.hypot(*(u_hat - u_test).T)
    return dict(valid=True, n_train=int(train.sum()), n_test=int(test.sum()),
                obs_median=float(np.median(r_obs)), obs_rms=float(np.sqrt((r_obs ** 2).mean())),
                obs_p95=float(np.percentile(r_obs, 95)), obs_max=float(r_obs.max()),
                cor_median=float(np.median(r_cor)), cor_rms=float(np.sqrt((r_cor ** 2).mean())),
                inverse_max_residual=float(maxres))


def fold_manifest(caps_by_clip):
    """Deterministic hash of every fold's membership, keyed by canonical lattice index.

    Hashing the canonical INDICES rather than observation numbers is what lets the manifest be
    compared across runs and across estimators.
    """
    h = hashlib.sha256()
    summary = []
    for key in sorted(caps_by_clip):
        for ci, C in enumerate(caps_by_clip[key]):
            elig = _eligible(C)
            rc = canonical_rc(C, elig)
            pos = {int(i): k for k, i in enumerate(np.where(elig)[0])}
            for f in folds_for_capture(C):
                nodes = sorted(tuple(rc[pos[int(i)]]) for i in np.where(f["test"])[0])
                h.update(f"{key}|{ci}|{f['name']}|{f['eligible']}|".encode())
                for n in nodes:
                    h.update(f"{n[0]},{n[1]};".encode())
                summary.append(dict(clip=key, capture=ci, fold=f["name"], family=f["family"],
                                    n_test=int(f["test"].sum()), n_train=int(f["train"].sum()),
                                    eligible=bool(f["eligible"]), reason=f["reason"]))
    return h.hexdigest(), summary


CONFIG = dict(block_size=BLOCK_SIZE, n_block_folds=N_BLOCK_FOLDS, ring_depth=RING_DEPTH,
              line_stride=LINE_STRIDE, min_train=MIN_TRAIN, min_test=MIN_TEST,
              min_train_span=MIN_TRAIN_SPAN, inverse_tol_px=INVERSE_TOL_PX,
              score_space="observed pixels via C^-1", frozen_against="97fccf0e8d0caf66")
CONFIG_SHA256 = hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()
