#!/usr/bin/env python3
"""Foundation for the new-objective rounds: unique lattice observations, indices, quadrature weights,
and the eta-aware map with its analytic Jacobian and inverse.

Nothing here is specific to one document. Everything takes a .vsd path and a clip name.

WHY THIS EXISTS. The production plumbline objective consumes stored LINE records and counts a shared
chessboard corner once per line it appears in. Physically a corner is ONE noisy 2-D observation
carrying TWO incidence constraints. This module recovers the unique observations, their integer
lattice indices, and area-based spatial weights, so objectives can be written on the physical data
rather than on the storage representation.

WHAT THE STORED DATA ACTUALLY IS, measured rather than assumed (see the audit report):

  * A shared corner is stored with BIT-IDENTICAL coordinates in both of its lines. Multiplicities are
    only 1 or 2, and every multiplicity-2 is cross-family. So matching is by exact coordinate and
    needs no tolerance; the nearest distinct pair of observations is reported as evidence.
  * Within a stored line, consecutive points ARE adjacent corners: the ratio of each gap to its
    neighbouring gaps on the same line is within 0.2 of 1.0 for 93 to 100 percent of gaps. So
    within-line adjacency is a reliable source of unit index steps.
  * Line-to-line offsets are NOT a reliable source of index steps. The legacy detector fragments one
    physical row into several line records (local offset-gap ratios as low as 0.19) and occasionally
    joins unrelated segments into one line (a 1649 px within-line jump on one Right-camera line). Any
    scheme that ranks lines by perpendicular offset and calls the rank an index is therefore wrong on
    this data. Indices here come from the adjacency GRAPH instead, which merges fragments
    automatically whenever a crossing line ties them together.

Run directly for the audit report on a document.
"""

import argparse
import importlib.util
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict, deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_W, FRAME_H = 1920.0, 1080.0
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")

# A within-line gap counts as a unit lattice step when its ratio to the neighbouring gaps on the same
# line is this close to 1. Chosen from the measured distribution, which is unimodal at 1.0 with 1st
# and 99th percentiles of 0.76 and 1.24 on the loosest capture, so 0.25 admits the whole mode and
# still rejects a 2x skip. Gaps outside it are NOT guessed at: the edge is dropped and reported.
UNIT_STEP_TOL = 0.25
# Two observations closer than this are treated as the same physical location for QUADRATURE ONLY.
# They remain separate data records; their shared area is divided between them.
COINCIDENT_PX = 0.5


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
P5 = L("parity_step5")
SCALE14 = P5.SCALE14
ETA_SCALE = P5.ETA_SCALE
ETA_BOUND = 0.05                      # |eta| <= 0.05, as specified for this round
M0_FREE = [0, 1, 2, 3, 4, 5, 9, 10]
M1_FREE = M0_FREE + [13]
MODELS = {"M0": M0_FREE, "M1": M1_FREE}


# =============================================================== the map, its Jacobian and inverse


def U(x, th14):
    """The eta-aware undistortion. Delegates to the parity-verified implementation at eta = 0."""
    return P5.undistort14(np.atleast_2d(np.asarray(x, float)), np.asarray(th14, float))


def jac_U(x, th14):
    """Analytic 2x2 Jacobian of U, stacked as (n, 2, 2).

    J_U = A^-1 J_B(A (x - c)) A with A = diag(e^eta, e^-eta), so J_U[i,j] = J_B[i,j] * a_j / a_i.
    J_B is undistortionJacobian (VSCalibration.mm:228) written vectorized. Verified against central
    differences in obj_synth.py.
    """
    x = np.atleast_2d(np.asarray(x, float))
    t = np.asarray(th14, float)
    ax = math.exp(t[13]); ay = 1.0 / ax
    xd = (x[:, 0] - t[0]) * ax
    yd = (x[:, 1] - t[1]) * ay
    s = xd * xd + yd * yd
    R = np.ones_like(s); Rp = np.zeros_like(s)
    for i, k in enumerate(t[2:9], start=1):
        R = R + k * s ** i
        Rp = Rp + i * k * s ** (i - 1)
    p1, p2, p3, p4 = t[9], t[10], t[11], t[12]
    T = 1.0 + p3 * s + p4 * s * s
    Tp = p3 + 2 * p4 * s
    Gx = p1 * (3 * xd * xd + yd * yd) + 2 * p2 * xd * yd
    Gy = 2 * p1 * xd * yd + p2 * (xd * xd + 3 * yd * yd)
    a = R + 2 * xd * xd * Rp + (6 * p1 * xd + 2 * p2 * yd) * T + 2 * xd * Gx * Tp
    b = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * yd * Gx * Tp
    c = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * xd * Gy * Tp
    d = R + 2 * yd * yd * Rp + (2 * p1 * xd + 6 * p2 * yd) * T + 2 * yd * Gy * Tp
    J = np.empty((len(x), 2, 2))
    J[:, 0, 0] = a
    J[:, 0, 1] = b * ay / ax
    J[:, 1, 0] = c * ax / ay
    J[:, 1, 1] = d
    return J


def inv_U(y, th14, iters=25, tol=1e-10, x0=None):
    """U^-1 by Newton with the analytic Jacobian. Returns (x, converged_mask, max_residual).

    The tolerance is absolute in pixels and deliberately NOT tighter than 1e-10. Coordinates here are
    of order 1e3, so double precision gives about 1e-13 of absolute resolution; asking for 1e-13 makes
    the break test unreachable and silently runs the full iteration cap on every call, which cost a
    factor of ten in every exact-objective evaluation before it was found. A step-size break is added
    for the same reason.
    """
    y = np.atleast_2d(np.asarray(y, float))
    x = y.copy() if x0 is None else np.array(x0, float, copy=True)
    for _ in range(iters):
        r = U(x, th14) - y
        m = np.abs(r).max()
        if m < tol:
            break
        J = jac_U(x, th14)
        det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
        det = np.where(np.abs(det) < 1e-14, 1e-14, det)
        dx = np.stack([(J[:, 1, 1] * r[:, 0] - J[:, 0, 1] * r[:, 1]) / det,
                       (-J[:, 1, 0] * r[:, 0] + J[:, 0, 0] * r[:, 1]) / det], axis=1)
        x = x - dx
        if np.abs(dx).max() < 1e-12:
            break
    res = np.abs(U(x, th14) - y).max(axis=1)
    return x, res < 1e-8, float(res.max())


def admissible(th14, pts, frame=(FRAME_W, FRAME_H), steps=40):
    """The corrected production checks, plus an explicit injectivity and invertibility audit of the
    FULL eta-aware map over the working domain.

    Returns a dict; `ok` is True only if the production gate passes on the Brown-Conrady core, |eta|
    is within bound, the eta-aware Jacobian determinant is strictly positive everywhere sampled
    (which with a connected domain gives local injectivity and, for this map family, invertibility),
    and the Newton round trip closes to better than 1e-9 px.
    """
    th14 = np.asarray(th14, float)
    pl = F.Plumblines([np.asarray(pts, float)])
    gr = F.gate_report(th14[:13], pl, 0.0, frame)
    lo, hi = np.asarray(pts, float).min(axis=0), np.asarray(pts, float).max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], steps + 1), np.linspace(lo[1], hi[1], steps + 1))
    box = np.stack([gx.ravel(), gy.ravel()], axis=1)
    fg = F.box_grid_xy(frame[0], frame[1], steps)
    out = {"gate_ok": bool(gr["ok"]), "R_scale": gr["radial_scale_ratio"],
           "min_det_core_box": gr["min_det_box"], "min_det_core_frame": gr["min_det_frame"],
           "eta": float(th14[13]),
           "eta_in_bound": bool(abs(th14[13]) <= ETA_BOUND + 1e-12)}
    for nm, g in (("box", box), ("frame", fg)):
        J = jac_U(g, th14)
        det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
        out[f"min_det_full_{nm}"] = float(np.nanmin(det))
        sv = np.linalg.svd(J, compute_uv=False)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"max_local_aniso_{nm}"] = float(np.nanmax(np.where(sv[:, 1] > 0,
                                                                    sv[:, 0] / sv[:, 1], np.inf)))
        back, conv, mx = inv_U(U(g, th14), th14)
        out[f"roundtrip_{nm}_px"] = float(np.abs(back - g).max())
        out[f"roundtrip_{nm}_forward_res"] = mx
        out[f"roundtrip_{nm}_all_converged"] = bool(conv.all())
    out["ok"] = bool(out["gate_ok"] and out["eta_in_bound"]
                     and out["min_det_full_box"] > 0.0
                     and out["roundtrip_box_px"] < 1e-9)
    return out


# =============================================================== observation extraction


class Capture:
    """One plumbline capture frame of one camera: unique observations, incidences, lattice indices."""

    def __init__(self, clip, timecode):
        self.clip = clip
        self.timecode = timecode
        self.xy = None            # (n, 2) unique raw observations
        self.lines = []           # list of dicts: family, member observation indices in order
        self.inc = []             # per observation: list of line ids
        self.rc = None            # (n, 2) integer lattice indices, or nan where unavailable
        self.component = None     # connected-component id per observation
        self.local_scale = None   # per observation: local lattice edge length in px
        self.notes = {}

    # ---- convenience masks
    @property
    def n(self):
        return 0 if self.xy is None else len(self.xy)

    def n_constraints(self):
        return np.array([len(v) for v in self.inc], int)

    def indexed(self):
        return np.isfinite(self.rc).all(axis=1)

    def doubly(self):
        return self.n_constraints() >= 2


def _family_split(linepts):
    """Assign each line to one of two families by its raw total-least-squares direction.

    Raw direction is adequate: distortion bends a line but does not rotate it by anything close to
    the 45 degrees that would move it between families, and the measured family angles are 80 to 94
    degrees apart on this data.
    """
    angs, dirs = [], []
    for P in linepts:
        q = P - P.mean(axis=0)
        th = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        angs.append(math.degrees(th) % 180.0)
        dirs.append(np.array([math.cos(th), math.sin(th)]))
    z = np.exp(2j * np.radians(angs))
    ref = math.degrees(np.angle(z.mean())) / 2.0 % 180.0
    fam = [0 if min(abs(a - ref), 180.0 - abs(a - ref)) < 45.0 else 1 for a in angs]
    return fam, np.array(angs), dirs, ref


def load_captures(vsd, clip):
    """Every plumbline capture of one camera, as Capture objects with unique observations."""
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    pk = db.execute("SELECT c.Z_PK FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v "
                    "ON v.Z_PK = c.ZVIDEOCLIP WHERE v.ZCLIPNAME = ?", (clip,)).fetchone()[0]
    raw, tc = defaultdict(list), {}
    for t, ln, x, y in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY FROM ZVSDISTORTIONLINE l "
            "JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
            "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
        if x is not None and y is not None:
            raw[ln].append((float(x), float(y)))
            tc[ln] = t
    db.close()

    bycap = defaultdict(list)
    for ln in sorted(raw):
        bycap[tc[ln]].append(ln)

    caps = []
    for cap in sorted(bycap):
        lids = bycap[cap]
        C = Capture(clip, cap)
        linepts = [np.array(raw[ln], float) for ln in lids]
        fam, angs, dirs, ref = _family_split(linepts)

        # unique observations by EXACT coordinate; validated by the nearest-distinct-pair distance
        idx_of = {}
        pts = []
        for P in linepts:
            for p in P:
                k = (p[0], p[1])
                if k not in idx_of:
                    idx_of[k] = len(pts)
                    pts.append(k)
        C.xy = np.array(pts, float)
        C.inc = [[] for _ in pts]
        for li, (ln, P) in enumerate(zip(lids, linepts)):
            members = [idx_of[(p[0], p[1])] for p in P]
            C.lines.append({"id": int(ln), "family": fam[li], "angle": float(angs[li]),
                            "members": members, "stored": len(members)})
            for m in members:
                C.inc[m].append(li)

        # storage-level diagnostics
        mult = Counter(len(v) for v in C.inc)
        crossfam = sum(1 for v in C.inc if len(v) == 2 and
                       C.lines[v[0]]["family"] != C.lines[v[1]]["family"])
        samefam = sum(1 for v in C.inc if len(v) >= 2 and
                      len({C.lines[i]["family"] for i in v}) == 1)
        # nearest distinct pair, the evidence that exact matching is safe
        from scipy.spatial import cKDTree
        d, _ = cKDTree(C.xy).query(C.xy, k=2)
        C.notes.update(family_ref_angle=ref, n_lines=len(C.lines),
                       n_famA=sum(1 for f in fam if f == 0),
                       n_famB=sum(1 for f in fam if f == 1),
                       stored_incidences=int(sum(len(l["members"]) for l in C.lines)),
                       unique_observations=len(pts),
                       multiplicity=dict(sorted(mult.items())),
                       cross_family_pairs=crossfam, same_family_duplicates=samefam,
                       nearest_distinct_pair_px=float(d[:, 1].min()),
                       matching="exact coordinate equality; no tolerance used")
        _recover_indices(C)
        _local_scale(C)
        caps.append(C)
    return caps


def _family_reference_dirs(C):
    """A deterministic unit direction per orientation family, independent of digitization.

    The direction is the circular mean of the family's line angles on the DOUBLED angle (angles are
    axes, defined mod 180 degrees), which is the same construction `_family_split` uses for its global
    reference. Contributions are summed in sorted order so the mean does not depend on the order lines
    happen to be stored in.

    SIGN RULE. A mod-180 axis has no intrinsic sign, so one is imposed: the DOMINANT COORDINATE of the
    reference vector is required to be positive. The tie |ux| == |uy| -- an axis at exactly 45 or 135
    degrees -- is broken deterministically in favour of the x coordinate. This replaces the obvious but
    unusable rule `ux + uy >= 0`, which is degenerate precisely at 135 degrees: there ux + uy is zero to
    round-off, so its sign is decided by floating-point noise and the canonical direction can flip
    between otherwise identical inputs.
    """
    out = {}
    for fam in (0, 1):
        angs = sorted(float(ln["angle"]) for ln in C.lines if ln["family"] == fam)
        if not angs:
            continue
        z = sorted((math.cos(2 * math.radians(a)), math.sin(2 * math.radians(a))) for a in angs)
        cx = sum(t[0] for t in z)
        cy = sum(t[1] for t in z)
        if cx == 0.0 and cy == 0.0:                 # antipodal cancellation: fall back to the median
            ref = angs[len(angs) // 2]
        else:
            ref = math.degrees(math.atan2(cy, cx)) / 2.0 % 180.0
        u = np.array([math.cos(math.radians(ref)), math.sin(math.radians(ref))], float)
        k = 0 if abs(u[0]) >= abs(u[1]) else 1      # dominant coordinate; ties go to x
        if u[k] < 0.0:
            u = -u
        out[fam] = u
    return out


def _orient_members(xy, mem, u):
    """Canonical traversal for one line's member sequence. Returns (members, degenerate).

    THE REQUIRED INVARIANT is C(P) == C(reverse(P)): the canonical sequence may not depend on the order
    the points were stored in, because that order is the operator's click direction and carries no
    lattice meaning.

    Nonzero projection onto the family reference `u` is the ordinary case: the sign of the endpoint chord
    flips under reversal, so flipping on a negative sign is already invariant.

    Zero projection means the chord is exactly perpendicular to `u`. That cannot happen for a line
    genuinely inside its family's 45-degree window, so this branch is unreachable from real data, but it
    must still be invariant rather than merely deterministic. An earlier version broke the tie on the
    stored line id, which is NOT invariant: reversing the points preserves both the zero projection and
    the id, so `flip` evaluated the same either way and the two inputs canonicalized to opposite
    sequences. The tie is now broken by a lexicographic comparison of the two ENDPOINT COORDINATES, which
    depends only on the unordered endpoint pair and is therefore invariant by construction.

    If the endpoints are identical no direction exists at all, so the line is reported DEGENERATE and the
    caller drops it rather than inventing an orientation from stored order.
    """
    p0 = np.asarray(xy[mem[0]], float)
    p1 = np.asarray(xy[mem[-1]], float)
    span = float((p1 - p0) @ np.asarray(u, float))
    if span > 0.0:
        return list(mem), False
    if span < 0.0:
        return list(mem)[::-1], False
    if p0[0] == p1[0] and p0[1] == p1[1]:
        return list(mem), True
    return (list(mem), False) if (p0[0], p0[1]) < (p1[0], p1[1]) else (list(mem)[::-1], False)


def _recover_indices(C):
    """Integer lattice indices from the within-line adjacency graph.

    Each consecutive pair along a family-A line is an edge changing the column index by one and
    leaving the row index alone; along a family-B line, the reverse. A gap whose ratio to its
    neighbouring gaps on the same line is not within UNIT_STEP_TOL of 1 is NOT interpreted: the edge
    is dropped and counted, because guessing a multi-step there is exactly the silent inference this
    round forbids.

    DIGITIZATION DIRECTION CARRIES NO LATTICE MEANING AND IS CANONICALIZED BEFORE PROPAGATION. The
    order in which an operator clicked along a line is an input artefact: the same physical line clicked
    bottom-to-top or top-to-bottom is the same line. But the index step below is chosen by FAMILY, so if
    one line is stored opposite to its family-mates then walking a closed cycle through it accumulates
    +2 instead of 0, and every cycle through that line reports a contradiction. On
    `2015-06-22-1 Clearwater` exactly one line per family per camera was clicked in the opposite
    direction, which produced 32 contradictions of 611 edges on the Left camera and 36 of 644 on the
    Right. Because the graph was a single connected component, that component was marked unreliable and
    ALL 340 / 365 observations were discarded, taking the indexed subset to zero and making the document
    ineligible for PD-D. The data was not defective in any way.

    Each line's member sequence is therefore oriented to agree with its family's deterministic reference
    direction (see `_family_reference_dirs`) by `_orient_members` before any edge is emitted, and that
    helper is invariant under reversal of the stored sequence in every branch it handles. The sequence is
    REVERSED, never re-sorted: stored order is already monotone along the line, and re-sorting by a
    projection would risk reordering a strongly curved distorted line. A count of any line whose order is
    not monotone in the family projection is recorded rather than silently repaired, and a line with no
    recoverable direction at all is dropped and counted in `degenerate_direction_lines`.

    Indices are then propagated by breadth-first search over each connected component, and EVERY
    edge is re-checked against the assignment afterwards. Surviving contradictions mean the graph is
    not a consistent lattice; they are counted and their component is marked unreliable.

    Labels are only defined up to translation, axis swap and sign per component. A homography absorbs
    any affine relabelling of (c, r), so this gauge freedom is harmless to the projective objective;
    what matters is that steps are unit, which the construction guarantees.
    """
    n = C.n
    adj = [[] for _ in range(n)]
    dropped = 0
    kept = 0
    fam_dir = _family_reference_dirs(C)
    reversed_lines, nonmonotone, degenerate_lines = [], [], []
    for li, ln in enumerate(C.lines):
        mem = ln["members"]
        if len(mem) < 2:
            continue
        u = fam_dir.get(ln["family"])
        if u is not None:
            oriented, degenerate = _orient_members(C.xy, mem, u)
            if degenerate:
                # No traversal direction exists (coincident endpoints). Emit no edges: guessing an
                # orientation here would reintroduce exactly the click-order dependence being removed.
                degenerate_lines.append(li)
                continue
            if oriented != list(mem):
                reversed_lines.append(li)
            mem = oriented
            ln["members"] = mem
            tt = C.xy[mem] @ u
            if not np.all(np.diff(tt) > 0):
                nonmonotone.append(li)
        P = C.xy[mem]
        g = np.hypot(*np.diff(P, axis=0).T)
        for i, gi in enumerate(g):
            nb = [g[j] for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < len(g)]
            ratio = gi / np.median(nb) if nb else 1.0
            if abs(ratio - 1.0) > UNIT_STEP_TOL:
                dropped += 1
                continue
            kept += 1
            # family A varies the column index, family B the row index
            step = (0, 1) if ln["family"] == 0 else (1, 0)
            adj[mem[i]].append((mem[i + 1], step, li))
            adj[mem[i + 1]].append((mem[i], (-step[0], -step[1]), li))

    rc = np.full((n, 2), np.nan)
    comp = np.full(n, -1, int)
    ncomp = 0
    for s in range(n):
        if comp[s] != -1:
            continue
        comp[s] = ncomp
        rc[s] = (0.0, 0.0)
        dq = deque([s])
        while dq:
            u = dq.popleft()
            for v, st, _ in adj[u]:
                if comp[v] == -1:
                    comp[v] = ncomp
                    rc[v] = rc[u] + np.array(st, float)
                    dq.append(v)
        ncomp += 1

    contradictions = 0
    bad_comps = set()
    for u in range(n):
        for v, st, _ in adj[u]:
            if not np.allclose(rc[v] - rc[u], st):
                contradictions += 1
                bad_comps.add(comp[u])
    contradictions //= 2

    sizes = Counter(comp.tolist())
    C.rc = rc
    C.component = comp
    C.notes.update(
        unit_step_edges=kept, dropped_nonunit_edges=dropped,
        unit_step_tolerance=UNIT_STEP_TOL,
        family_reference_dirs={str(k): v.tolist() for k, v in fam_dir.items()},
        traversal_canonicalized_lines=sorted(reversed_lines),
        n_traversal_canonicalized=len(reversed_lines),
        nonmonotone_member_order=sorted(nonmonotone),
        degenerate_direction_lines=sorted(degenerate_lines),
        n_components=ncomp,
        component_sizes=dict(sorted(sizes.items(), key=lambda z: -z[1])),
        largest_component=max(sizes.values()) if sizes else 0,
        index_contradictions=contradictions,
        inconsistent_components=sorted(bad_comps),
        isolated_observations=int(sum(1 for k, v in sizes.items() if v == 1)))
    # reliable = in the largest consistent component, which is what the projective lattice needs
    ok_comps = {k for k, v in sizes.items() if v >= 4 and k not in bad_comps}
    C.notes["reliable_components"] = sorted(ok_comps)
    keep = np.array([c in ok_comps for c in comp])
    rc2 = rc.copy()
    rc2[~keep] = np.nan
    C.rc = rc2
    C.notes["reliably_indexed"] = int(keep.sum())


def _local_scale(C):
    """Local lattice edge length per observation: the median unit-step gap of its own lines.

    This is the scale the Delaunay triangle filter is derived from, so the filter is set by the
    observed lattice, not by any residual-correlation length.
    """
    per = [[] for _ in range(C.n)]
    for ln in C.lines:
        mem = ln["members"]
        if len(mem) < 2:
            continue
        P = C.xy[mem]
        g = np.hypot(*np.diff(P, axis=0).T)
        med = float(np.median(g))
        for i, m in enumerate(mem):
            loc = [g[j] for j in (i - 1, i) if 0 <= j < len(g)]
            per[m].append(float(np.median(loc)) if loc else med)
    glob = float(np.median([v for s in per for v in s])) if any(per) else 1.0
    C.local_scale = np.array([np.median(s) if s else glob for s in per], float)


# =============================================================== pooled Delaunay quadrature


def delaunay_weights(caps, kappa=3.0, coincident_px=COINCIDENT_PX, mask=None):
    """Mass-lumped Delaunay weights over the POOLED raw observations of one camera.

    a_i = (1/3) sum over incident retained triangles of the triangle area, then normalized to mean 1.

    Pooling is for spatial quadrature only: observations stay separate records with their own
    capture. Because pooling makes triangles smaller where captures overlap, a region's total mass
    tends to its area regardless of how many captures cover it and regardless of point density, which
    is the intended behaviour. Exactly coincident observations from different captures would break the
    triangulation, so observations within `coincident_px` are clustered, the cluster is triangulated
    once, and its mass is divided equally among its members -- dividing local area rather than
    multiplying influence.

    Triangles whose longest edge exceeds `kappa` times the local lattice edge scale are dropped, so
    genuinely unsupported holes are not bridged. The scale comes from the observed lattice.
    """
    from scipy.spatial import Delaunay, cKDTree
    pts, scale, owner = [], [], []
    for ci, C in enumerate(caps):
        sel = np.ones(C.n, bool) if mask is None else np.asarray(mask[ci], bool)
        for i in np.where(sel)[0]:
            pts.append(C.xy[i]); scale.append(C.local_scale[i]); owner.append((ci, i))
    P = np.array(pts, float)
    scale = np.array(scale, float)
    if len(P) < 3:
        return np.ones(len(P)), {"n": len(P), "degenerate": True}

    # cluster coincident observations
    tree = cKDTree(P)
    groups = tree.query_ball_tree(tree, coincident_px)
    cid = np.full(len(P), -1, int)
    ng = 0
    for i in range(len(P)):
        if cid[i] != -1:
            continue
        stack = [i]
        cid[i] = ng
        while stack:
            u = stack.pop()
            for v in groups[u]:
                if cid[v] == -1:
                    cid[v] = ng
                    stack.append(v)
        ng += 1
    cpts = np.array([P[cid == g].mean(axis=0) for g in range(ng)])
    cscale = np.array([scale[cid == g].mean() for g in range(ng)])
    csize = np.array([(cid == g).sum() for g in range(ng)])

    tri = Delaunay(cpts)
    area = np.zeros(ng)
    kept = dropped = 0
    for t in tri.simplices:
        A, B, Cc = cpts[t]
        e = max(np.linalg.norm(A - B), np.linalg.norm(B - Cc), np.linalg.norm(Cc - A))
        if e > kappa * float(np.median(cscale[t])):
            dropped += 1
            continue
        kept += 1
        ar = abs((B[0] - A[0]) * (Cc[1] - A[1]) - (Cc[0] - A[0]) * (B[1] - A[1])) / 2.0
        area[t] += ar / 3.0
    # divide each cluster's mass among its coincident members
    w = np.array([area[cid[i]] / csize[cid[i]] for i in range(len(P))])
    zero = int((w <= 0).sum())
    unnormalized_mass = float(w.sum())        # total retained quadrature area, px^2, before mean-1
    if w.sum() > 0:
        w = w * (len(w) / w.sum())
    info = {"n": len(P), "n_clusters": ng, "n_coincident_clusters": int((csize > 1).sum()),
            "unnormalized_mass_px2": unnormalized_mass,
            "triangles_kept": kept, "triangles_dropped": dropped, "kappa": kappa,
            "coincident_px": coincident_px,
            "zero_weight_observations": zero,
            "weight_min": float(w.min()), "weight_max": float(w.max()),
            "weight_median": float(np.median(w)),
            "weight_p05": float(np.percentile(w, 5)), "weight_p95": float(np.percentile(w, 95)),
            "owner": owner}
    return w, info


# =============================================================== diagonals


def diagonal_families(C, min_points=5, min_span_px=100.0, restrict=None):
    """Zero-weight holdout families r - c = k and r + c = k, from reliable indices only.

    Grouped by CONNECTED COMPONENT as well as by k. Index labels are produced by a breadth-first
    search that starts each component at its own (0, 0), so labels are comparable only within a
    component; pooling a diagonal across components mixes points with unrelated origins and produced a
    meaningless holdout residual of about 260 px for every candidate map before this was caught.

    `restrict` optionally limits the members to a boolean mask of observations, so the holdout can be
    reported over exactly the fitted subset.
    """
    out = []
    ok = C.indexed()
    if restrict is not None:
        ok = ok & np.asarray(restrict, bool)
    rc = C.rc
    for kind, key in (("r-c", lambda r, c: r - c), ("r+c", lambda r, c: r + c)):
        groups = defaultdict(list)
        for i in np.where(ok)[0]:
            groups[(int(C.component[i]), int(key(rc[i, 0], rc[i, 1])))].append(i)
        for (comp, k), mem in sorted(groups.items()):
            if len(mem) < min_points:
                continue
            Pk = C.xy[mem]
            q = Pk - Pk.mean(axis=0)
            th = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                                  float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            t = q[:, 0] * math.cos(th) + q[:, 1] * math.sin(th)
            span = float(t.max() - t.min())
            out.append({"kind": kind, "k": k, "component": comp, "members": mem,
                        "n": len(mem), "span_px": span,
                        "adequate": bool(span >= min_span_px)})
    return out


# =============================================================== audit report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--clips", nargs="*", default=["Left Camera", "Right Camera"])
    args = ap.parse_args()
    say = print
    say("=" * 104)
    say("LATTICE OBSERVATION AUDIT")
    say("=" * 104)
    say(f"  document {os.path.basename(args.vsd)}")

    for clip in args.clips:
        caps = load_captures(args.vsd, clip)
        say(f"\n{'=' * 104}\n  {clip}: {len(caps)} capture frame(s)\n{'=' * 104}")
        for C in caps:
            N = C.notes
            nc = C.n_constraints()
            say(f"\n  capture {C.timecode!r}")
            say(f"    lines {N['n_lines']} = {N['n_famA']} family A + {N['n_famB']} family B "
                f"(family reference angle {N['family_ref_angle']:.1f} deg)")
            say(f"    stored point incidences {N['stored_incidences']}; unique observations "
                f"{N['unique_observations']}")
            say(f"    multiplicity distribution {N['multiplicity']}; cross-family pairs "
                f"{N['cross_family_pairs']}; same-family duplicates {N['same_family_duplicates']}")
            say(f"    constraints per observation: two {int((nc == 2).sum())}, one "
                f"{int((nc == 1).sum())}, more than two {int((nc > 2).sum())}")
            say(f"    matching: {N['matching']}; nearest DISTINCT pair "
                f"{N['nearest_distinct_pair_px']:.4f} px, so exact equality cannot merge two "
                f"different corners")
            say(f"    adjacency edges: {N['unit_step_edges']} accepted as unit steps, "
                f"{N['dropped_nonunit_edges']} dropped as non-unit or ambiguous "
                f"(tolerance {N['unit_step_tolerance']})")
            say(f"    components {N['n_components']} (largest {N['largest_component']}, isolated "
                f"{N['isolated_observations']}); sizes "
                f"{list(N['component_sizes'].values())[:8]}")
            say(f"    index contradictions after propagation {N['index_contradictions']}; "
                f"inconsistent components {N['inconsistent_components']}")
            say(f"    reliably indexed observations {N['reliably_indexed']} of "
                f"{N['unique_observations']}")
            ok = C.indexed()
            both = ok & (nc >= 2)
            say(f"    reliably indexed AND doubly constrained: {int(both.sum())} "
                f"(the common subset for objective comparison)")
            if ok.any():
                r = C.rc[ok, 0]; c = C.rc[ok, 1]
                say(f"      index extent r {int(r.min())}..{int(r.max())}, c {int(c.min())}"
                    f"..{int(c.max())}; occupancy "
                    f"{ok.sum() / ((r.max() - r.min() + 1) * (c.max() - c.min() + 1)):.3f} "
                    f"of the bounding lattice, so missing corners are the norm")
            dg = diagonal_families(C)
            adq = [d for d in dg if d["adequate"]]
            say(f"    diagonal holdout families with >=5 points: {len(dg)} "
                f"({len(adq)} also spanning >=100 px)")
        # pooled weights for the camera
        w, info = delaunay_weights(caps)
        say(f"\n  pooled Delaunay quadrature over {info['n']} observations from "
            f"{len(caps)} capture(s)")
        say(f"    clusters {info['n_clusters']} ({info['n_coincident_clusters']} containing "
            f"coincident observations from different captures)")
        say(f"    triangles kept {info['triangles_kept']}, dropped as unsupported "
            f"{info['triangles_dropped']} (kappa {info['kappa']} x local lattice edge)")
        say(f"    weights normalized to mean 1: min {info['weight_min']:.4f}, p5 "
            f"{info['weight_p05']:.4f}, median {info['weight_median']:.4f}, p95 "
            f"{info['weight_p95']:.4f}, max {info['weight_max']:.4f}; zero-weight "
            f"{info['zero_weight_observations']}")
        for k in (2.0, 4.0):
            w2, i2 = delaunay_weights(caps, kappa=k)
            rel = float(np.abs(w2 - w).max() / max(w.max(), 1e-12))
            say(f"    sensitivity: kappa {k} keeps {i2['triangles_kept']} triangles "
                f"(vs {info['triangles_kept']}), max weight change {rel:.4f} of the max weight")
    return 0


if __name__ == "__main__":
    sys.exit(main())
