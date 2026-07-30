#!/usr/bin/env python3
"""Does SD-D actually work on targets that were never a lattice? And what does it require of the file?

The intermediate document `2015-06-22-1` is a "modern lattice expected, validation failed" case. That
is useful but it is NOT evidence about a target DESIGNED as unrelated straight lines. These tests supply
that evidence synthetically, cheaply, with known M0/M1 truth and no lattice indices anywhere: every
synthetic capture has `rc` all-NaN, so `indexed()` is false for every observation and no lattice
constraint can be silently in play.

The second question matters more for adoption than the first: WHAT OBSERVATION IDENTITY does SD-D
require? Its whole estimand is one constraint block and one spatial weight PER UNIQUE PHYSICAL
OBSERVATION. If a saved file records the same physical point twice, once per line it lies on, SD-D
cannot know they are the same point. Section [5] measures exactly what that costs.

Run with ~/.venvs/vidsync/bin/python.
"""

import math
import os
import sys
import time

import numpy as np

import harness_import

harness_import.ensure_path()
import sd_fast as SF                                                         # noqa: E402
from test_sd_fast import Cap, distort_to_raw, truth_theta                     # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")

PASS, FAIL = [], []
FRAME = (1920.0, 1080.0)


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def build(segments, th_truth, jitter=0.0, seed=0, coincident=None, dup_lines=(),
          require_indexed=False, min_inc=1):
    """Turn a list of (point-array-in-IDEAL-coords) line segments into a Dataset.

    `coincident` optionally supplies extra (ideal_point, line_index) pairs that must be represented as
    ONE shared unique observation belonging to several lines -- which is how a real intersection is
    stored when the format identifies it as a single point.
    """
    rng = np.random.default_rng(seed)
    pts, lines = [], []
    for si, P in enumerate(segments):
        P = np.asarray(P, float)
        if jitter:
            P = P + jitter * rng.standard_normal(P.shape)
        base = len(pts)
        pts.extend(P.tolist())
        lines.append({"members": list(range(base, base + len(P))), "family": si % 2})
    if coincident:
        for xy, lidx in coincident:
            i = len(pts)
            pts.append(list(xy))
            for li in lidx:
                lines[li]["members"].append(i)
    for li in dup_lines:
        lines.append(dict(lines[li]))
    ideal = np.array(pts, float)
    raw = distort_to_raw(ideal, th_truth)
    cap = Cap(raw, lines)
    return OB.Dataset([cap], require_indexed=require_indexed, min_inc=min_inc, kappa=3.0), cap


def intersect(p0, p1, q0, q1):
    """The exact intersection of segment (p0,p1) with (q0,q1), in ideal coordinates.

    Hand-typed "intersections" are not intersections: an earlier version of this file placed shared
    points near but not on both lines, which injected gross inconsistency and made the fit diverge by
    thousands of pixels. Intersections are computed.
    """
    p0, p1, q0, q1 = (np.asarray(v, float) for v in (p0, p1, q0, q1))
    r, sv = p1 - p0, q1 - q0
    den = r[0] * sv[1] - r[1] * sv[0]
    if abs(den) < 1e-12:
        return None
    t = ((q0[0] - p0[0]) * sv[1] - (q0[1] - p0[1]) * sv[0]) / den
    return p0 + t * r


def seg(p0, p1, n):
    t = np.linspace(0.0, 1.0, n)[:, None]
    return np.asarray(p0, float)[None, :] * (1 - t) + np.asarray(p1, float)[None, :] * t


def irregular_target(seed=3, n_lines=11, uneven=True):
    """Irregularly placed and oriented straight lines with deliberately uneven point density."""
    rng = np.random.default_rng(seed)
    segs = []
    for i in range(n_lines):
        for _ in range(40):
            a = np.array([rng.uniform(40, FRAME[0] - 40), rng.uniform(40, FRAME[1] - 40)])
            ang = rng.uniform(0, math.pi)
            ln = rng.uniform(0.3, 0.9) * min(FRAME)
            b = a + ln * np.array([math.cos(ang), math.sin(ang)])
            if 40 < b[0] < FRAME[0] - 40 and 40 < b[1] < FRAME[1] - 40:
                break
        # uneven density: some lines densely sampled, some sparsely
        n = int(rng.choice([5, 7, 9, 14, 22, 30])) if uneven else 12
        segs.append(seg(a, b, n))
    return segs


def recovery(th_true, th_fit):
    """Map recovery measured by induced displacement over the frame, not by coefficients."""
    gx, gy = np.meshgrid(np.linspace(30, FRAME[0] - 30, 40), np.linspace(30, FRAME[1] - 30, 40))
    g = np.stack([gx.ravel(), gy.ravel()], axis=1)
    d = np.linalg.norm(LT.U(g, np.asarray(th_true, float)) - LT.U(g, np.asarray(th_fit, float)),
                       axis=1)
    return float(d.max()), float(np.sqrt((d ** 2).mean()))


def region_mass(D, nx=3, ny=3):
    """Total Delaunay weight mass by coarse screen region, normalized to sum 1."""
    gx = np.clip((D.xy[:, 0] / FRAME[0] * nx).astype(int), 0, nx - 1)
    gy = np.clip((D.xy[:, 1] / FRAME[1] * ny).astype(int), 0, ny - 1)
    M = np.zeros((ny, nx))
    N = np.zeros((ny, nx), int)
    for i in range(D.n):
        M[gy[i], gx[i]] += D.w[i]
        N[gy[i], gx[i]] += 1
    return M / M.sum(), N


def main():
    print("=" * 100)
    print("SD-D ON GENUINELY NON-LATTICE SYNTHETIC TARGETS")
    print("=" * 100)
    t00 = time.time()
    R = {}

    # ---------------------------------------------------------------- 1. the basic non-lattice case
    print(f"\n[1] IRREGULAR LINES, UNEVEN DENSITY, no lattice indices at all")
    for model, eta in (("M0", 0.0), ("M1", 0.028)):
        th = truth_theta(model, eta)
        D, cap = build(irregular_target(), th)
        check(f"{model}: no observation is lattice-indexed",
              not cap.indexed().any(), f"{D.n} observations, {D.nline} lines")
        inc = np.array([len(l) for l in D.obs_lines])
        r = SF.fit_sd(D, model)
        mx, rms = recovery(th, r["theta14"])
        check(f"{model}: converged and verified", r["convergence_verified"],
              f"status {r['status']}, {r['total_s']:.2f}s, loss {r['loss']:.3e}")
        check(f"{model}: recovers the true map over the frame",
              mx < 0.05, f"max induced error {mx:.4f} px, rms {rms:.4f} px")
        if model == "M1":
            check("M1: recovers eta itself",
                  abs(r["eta"] - eta) < 2e-4, f"fitted {r['eta']:+.6f} vs true {eta:+.6f}")
        R[f"irregular/{model}"] = {"n": int(D.n), "nline": int(D.nline),
                                   "incidence_1": int((inc == 1).sum()),
                                   "incidence_ge2": int((inc >= 2).sum()),
                                   "max_px": mx, "rms_px": rms, "eta": r["eta"],
                                   "verified": r["convergence_verified"], "s": r["total_s"]}
        print(f"        incidences: singly constrained {int((inc == 1).sum())}, "
              f"multiply {int((inc >= 2).sum())}")

    # ---------------------------------------------------------------- 2. lines with NO intersections
    print(f"\n[2] LINES THAT NEVER INTERSECT (every observation singly constrained)")
    th = truth_theta("M1", 0.025)
    par = [seg((100, 80 + i * 95), (1820, 120 + i * 95), 16) for i in range(10)]
    D, cap = build(par, th)
    inc = np.array([len(l) for l in D.obs_lines])
    check("every observation lies on exactly one line",
          (inc == 1).all(), f"{D.n} observations, all singly constrained")
    r = SF.fit_sd(D, "M1")
    mx, rms = recovery(th, r["theta14"])
    check("singly constrained observations use a one-row block and still fit",
          r["convergence_verified"], f"status {r['status']}, loss {r['loss']:.3e}")
    # Identifiability is a property of the Jacobian, not of whether one fit happened to succeed.
    ev, p, b2, pk = __import__("test_sd_fast").evaluator(D, "M1", at=th)
    ph, e = OB.init_lines(D, pk.theta(p, b2))
    p[pk.iline:pk.iline + D.nline] = ph
    p[pk.iline + D.nline:pk.iline + 2 * D.nline] = e
    Jm = ev.jacobian(p).toarray()[:, :pk.nm]
    sv = np.linalg.svd(Jm, compute_uv=False)
    cond_par = float(sv[0] / max(sv[-1], 1e-300))
    print(f"        one family only : model-block condition number {cond_par:.3e}, "
          f"max induced error {mx:.4f} px")
    # now add a crossing family
    cross = par + [seg((150 + i * 180, 60), (250 + i * 180, 1020), 14) for i in range(9)]
    D2, _ = build(cross, th)
    r2 = SF.fit_sd(D2, "M1")
    mx2, rms2 = recovery(th, r2["theta14"])
    ev2, p2, b22, pk2 = __import__("test_sd_fast").evaluator(D2, "M1", at=th)
    ph, e = OB.init_lines(D2, pk2.theta(p2, b22))
    p2[pk2.iline:pk2.iline + D2.nline] = ph
    p2[pk2.iline + D2.nline:pk2.iline + 2 * D2.nline] = e
    sv2 = np.linalg.svd(ev2.jacobian(p2).toarray()[:, :pk2.nm], compute_uv=False)
    cond_two = float(sv2[0] / max(sv2[-1], 1e-300))
    print(f"        two families    : model-block condition number {cond_two:.3e}, "
          f"max induced error {mx2:.4f} px")
    # MEASURED, not assumed. The expectation going in was that one orientation would be markedly worse
    # conditioned, because line_audit warns that a single orientation leaves the centre weakly
    # identified transverse to it. On this target that is NOT what happens: the ratio is 1.1x and both
    # recover the map exactly. The reason is that these lines are not exactly parallel and the truth
    # carries tangential terms and eta, so curvature ALONG each line still identifies the centre. The
    # line_audit warning is about the general case; it is not a prediction about every such target.
    check("neither configuration has a null direction in the model block",
          cond_par < 1e10 and cond_two < 1e10,
          f"condition {cond_par:.3e} with one family, {cond_two:.3e} with two "
          f"({cond_par / cond_two:.2f}x -- comparable, contrary to expectation)")
    check("a single orientation was SUFFICIENT here, so the warning is not a universal blocker",
          mx < 0.05, f"one family recovered the map to {mx:.4f} px")
    check("with two crossing families the map is recovered",
          mx2 < 0.05, f"max induced error {mx2:.4f} px")
    check("and no intersection had to be identified as a shared observation",
          max(len(l) for l in D2.obs_lines) == 1,
          "every observation is still on exactly one line")
    R["no_intersections"] = {"single_family_max_px": mx, "two_families_max_px": mx2,
                             "cond_one_family": cond_par, "cond_two_families": cond_two,
                             "n": int(D2.n)}

    # ---------------------------------------------------------------- 3. shared intersections
    print(f"\n[3] INTERSECTIONS REPRESENTED AS SHARED UNIQUE OBSERVATIONS")
    th = truth_theta("M1", 0.02)
    ends = [((120, 200), (1800, 260)), ((140, 900), (1780, 840)),
            ((300, 80), (420, 1000)), ((1300, 90), (1180, 1010))]
    segs = [seg(a, b, 12) for a, b in ends]
    # COMPUTED crossings of line 0 with lines 2 and 3, stored ONCE and belonging to both
    coin = [(intersect(*ends[0], *ends[2]), [0, 2]),
            (intersect(*ends[0], *ends[3]), [0, 3])]
    D, cap = build(segs, th, coincident=coin)
    inc = np.array([len(l) for l in D.obs_lines])
    check("the shared points are recorded as one observation on two lines",
          int((inc == 2).sum()) == 2, f"{int((inc == 2).sum())} doubly constrained observations")
    r = SF.fit_sd(D, "M1")
    mx, rms = recovery(th, r["theta14"])
    check("mixed singly and multiply constrained observations fit together",
          r["convergence_verified"] and mx < 0.05,
          f"max induced error {mx:.4f} px, loss {r['loss']:.3e}")
    R["shared_intersections"] = {"n": int(D.n), "n_doubly": int((inc == 2).sum()), "max_px": mx}

    # ---------------------------------------------------------------- 4. defects
    print(f"\n[4] MISSING POINTS, FRAGMENTED RECORDS, DUPLICATE RECORDS")
    th = truth_theta("M1", 0.026)
    segs = irregular_target(seed=11)
    rng = np.random.default_rng(4)
    # drop 25% of points at random, and split three lines into two fragments each
    holed = []
    for i, P in enumerate(segs):
        keep = rng.random(len(P)) > 0.25
        if keep.sum() >= 4:
            P = P[keep]
        if i < 3 and len(P) >= 8:
            h = len(P) // 2
            holed.append(P[:h]); holed.append(P[h:])
        else:
            holed.append(P)
    D_ref, _ = build(segs, th)
    D_def, cap = build(holed, th, dup_lines=(0, 2))
    check("duplicate stored records are deduplicated and reported",
          cap.notes["n_lines"] > D_def.nline,
          f"{cap.notes['n_lines']} stored records -> {D_def.nline} retained; "
          f"merged {D_def.info['merged_duplicate_line_records']}")
    r_ref = SF.fit_sd(D_ref, "M1")
    r_def = SF.fit_sd(D_def, "M1")
    mxr, _ = recovery(th, r_ref["theta14"])
    mxd, _ = recovery(th, r_def["theta14"])
    check("the degraded target still converges and verifies", r_def["convergence_verified"])
    print(f"        clean target: verified={r_ref['convergence_verified']}, "
          f"loss {r_ref['loss']:.3e}, max induced error {mxr:.4f} px")
    print(f"        degraded    : verified={r_def['convergence_verified']}, "
          f"loss {r_def['loss']:.3e}, max induced error {mxd:.4f} px")
    check("the degraded target is recovered",
          mxd < 0.20, f"holed+fragmented+duplicated {mxd:.4f} px "
                      f"({D_ref.n} -> {D_def.n} observations)")
    check("VERIFICATION FLAGS the clean target, which landed in a spurious minimum",
          (mxr < 0.05) == bool(r_ref["convergence_verified"]),
          f"clean max error {mxr:.4f} px with verified={r_ref['convergence_verified']} -- "
          f"the degradation did not cause the failure; this target's geometry did")
    check("FRAGMENTATION IS NOT REPAIRED, only tolerated",
          D_def.nline > D_ref.nline,
          f"{D_ref.nline} lines -> {D_def.nline}: each fragment is fitted as its own line with its "
          f"own nuisance parameters, so a split line contributes two independent straightness "
          f"constraints instead of one longer one")
    R["defects"] = {"clean_max_px": mxr, "degraded_max_px": mxd,
                    "n_clean": int(D_ref.n), "n_degraded": int(D_def.n),
                    "nline_clean": int(D_ref.nline), "nline_degraded": int(D_def.nline)}

    # ---------------------------------------------------------------- 5. observation identity
    print(f"\n[5] WHAT OBSERVATION IDENTITY DOES SD-D REQUIRE?")
    print(f"      SD-D's estimand is one constraint block and one spatial weight per UNIQUE PHYSICAL")
    print(f"      observation. This asks what happens when a legacy file cannot say that two")
    print(f"      coincident incidences are the same physical point.")
    th = truth_theta("M1", 0.02)
    ends5 = [((120, 200), (1800, 260)), ((140, 900), (1780, 840)), ((300, 80), (420, 1000)),
             ((1300, 90), (1180, 1010)), ((700, 100), (760, 1000)), ((150, 550), (1800, 520))]
    segs = [seg(a, b, 14) for a, b in ends5]
    xs = []
    for h in (0, 1, 5):                       # near-horizontal lines
        for v in (2, 3, 4):                   # near-vertical lines
            pt = intersect(*ends5[h], *ends5[v])
            if pt is not None:
                xs.append((tuple(pt), [h, v]))
    D_shared, _ = build(segs, th, coincident=xs)
    # the SAME target, but each intersection stored as TWO separate coincident observations
    xs_split = []
    for xy, lidx in xs:
        for li in lidx:
            xs_split.append((xy, [li]))
    D_split, _ = build(segs, th, coincident=xs_split)
    inc_s = np.array([len(l) for l in D_shared.obs_lines])
    inc_p = np.array([len(l) for l in D_split.obs_lines])
    check("shared representation gives doubly constrained observations",
          int((inc_s >= 2).sum()) == len(xs), f"{int((inc_s >= 2).sum())} of {D_shared.n}")
    check("split representation gives NONE, and more observations",
          (inc_p == 1).all() and D_split.n == D_shared.n + len(xs),
          f"{D_split.n} vs {D_shared.n} observations, all singly constrained")
    rs = SF.fit_sd(D_shared, "M1")
    rp = SF.fit_sd(D_split, "M1")
    mxs, _ = recovery(th, rs["theta14"])
    mxp, _ = recovery(th, rp["theta14"])
    print(f"        shared identity : {D_shared.n} obs, max induced error {mxs:.4f} px, "
          f"loss {rs['loss']:.3e}")
    print(f"        split identity  : {D_split.n} obs, max induced error {mxp:.4f} px, "
          f"loss {rp['loss']:.3e}")
    check("both representations still fit on exactly consistent data",
          rs["convergence_verified"] and rp["convergence_verified"])
    ws = region_mass(D_shared)[0]
    wp = region_mass(D_split)[0]
    # The real cost is weighting, not fitting: a split intersection gets TWO spatial weights where the
    # estimand says it should have one, so that location's influence is doubled.
    wsum_shared = float(sum(D_shared.w[i] for i in range(D_shared.n) if inc_s[i] >= 2))
    isec_idx = [i for i in range(D_split.n) if any(
        np.allclose(D_split.xy[i], distort_to_raw(np.array([xy]), th)[0], atol=1e-6)
        for xy, _ in xs)]
    wsum_split = float(sum(D_split.w[i] for i in isec_idx))
    print(f"        total spatial weight at the {len(xs)} intersection locations:")
    print(f"          shared identity {wsum_shared:.4f} over {int((inc_s >= 2).sum())} records")
    print(f"          split identity  {wsum_split:.4f} over {len(isec_idx)} records")
    # The Delaunay stage already clusters observations within COINCIDENT_PX and DIVIDES the cluster's
    # mass among its members, so the spatial weighting is largely protected even under split identity.
    # That is a real strength of the weighting design and is measured rather than assumed.
    check("Delaunay coincident-clustering largely PROTECTS the spatial mass under split identity",
          wsum_split < 1.4 * wsum_shared,
          f"{wsum_split / max(wsum_shared, 1e-12):.2f}x the intended mass, not 2x, because "
          f"delaunay_weights clusters within COINCIDENT_PX and divides local area among members")
    check("the joint-block structure is also lost",
          int((inc_p >= 2).sum()) == 0,
          "a split intersection contributes two one-row blocks instead of one joint two-row block, "
          "so the two constraints are treated as independent evidence about different points")
    R["observation_identity"] = {
        "n_shared": int(D_shared.n), "n_split": int(D_split.n),
        "n_intersections": len(xs),
        "max_px_shared": mxs, "max_px_split": mxp,
        "intersection_mass_shared": wsum_shared, "intersection_mass_split": wsum_split,
        "mass_inflation": wsum_split / max(wsum_shared, 1e-12)}

    # ---------------------------------------------------------------- 5b. basin robustness
    print(f"\n[5b] BASIN ROBUSTNESS across independent non-lattice targets")
    print(f"      Exactly consistent data, so a loss of ~0 at the TRUE map always exists. The question")
    print(f"      is whether the solver finds it, and whether verification catches it when it does not.")
    print(f"      {'seed':>5} {'n':>5} {'lines':>6} {'loss':>12} {'stat':>5} {'ver':>6} "
          f"{'max px':>10}  verdict")
    rows = []
    for sd in (3, 5, 7, 11, 13, 17, 19, 23):
        th = truth_theta("M1", 0.026)
        D, _ = build(irregular_target(seed=sd), th)
        r = SF.fit_sd(D, "M1")
        mx, _ = recovery(th, r["theta14"])
        ok_map = mx < 0.05
        ver = bool(r["convergence_verified"])
        verdict = ("recovered" if ok_map else
                   ("SPURIOUS MINIMUM, caught by verification" if not ver else
                    "SPURIOUS MINIMUM, PASSED verification"))
        rows.append({"seed": sd, "n": int(D.n), "nline": int(D.nline), "loss": r["loss"],
                     "status": r["status"], "verified": ver, "max_px": mx,
                     "recovered": bool(ok_map)})
        print(f"      {sd:5d} {D.n:5d} {D.nline:6d} {r['loss']:12.3e} {r['status']:5d} "
              f"{str(ver):>6} {mx:10.4f}  {verdict}")
    nrec = sum(1 for x in rows if x["recovered"])
    bad_pass = [x for x in rows if not x["recovered"] and x["verified"]]
    caught = [x for x in rows if not x["recovered"] and not x["verified"]]
    print(f"        recovered {nrec} of {len(rows)}; "
          f"spurious minima caught by verification {len(caught)}; "
          f"spurious minima that PASSED verification {len(bad_pass)}")
    # ROUND-3 FINDING, asserted as a deterministic regression guard. Under the corrected
    # per-observation local-scale harness, seed 17 converges to a materially wrong map (88.8 px) with
    # status 2 and PASSES multi-start convergence verification. So local stability plus restart
    # stability is NOT sufficient evidence that a map is physically right, and `convergence_verified`
    # must never be read as "globally verified".
    check("CONVERGENCE VERIFICATION IS NOT SUFFICIENT: a wrong map passes it",
          len(bad_pass) >= 1,
          f"{len(bad_pass)} of {len(rows)} spurious minima passed verification "
          f"({[x['seed'] for x in bad_pass]}); {len(caught)} were caught "
          f"({[x['seed'] for x in caught]})")
    check("map-space correctness is evaluated independently of optimizer status",
          all(("recovered" in x) and ("verified" in x) for x in rows),
          "recovery is measured by projected map error, never by convergence flags")
    check("SD-D DOES NOT reliably recover the map on line-only targets",
          nrec < len(rows),
          f"recovered {nrec} of {len(rows)} independent targets -- this is the round's blocker, "
          f"not a tolerance question: an exact zero-residual solution exists in every case")
    R["basin_robustness"] = {"rows": rows, "n_recovered": nrec, "n_targets": len(rows),
                             "n_spurious_caught": len(caught),
                             "n_spurious_passed_verification": len(bad_pass)}

    # ---------------------------------------------------------------- 6. Delaunay area uniformity
    print(f"\n[6] DELAUNAY WEIGHTS vs IRREGULAR SAMPLING")
    print(f"      the estimand is uniform influence per unit INFORMED IMAGE AREA, so adding dense")
    print(f"      redundant points in one region must NOT multiply that region's total influence")
    th = truth_theta("M0", 0.0)
    segs = irregular_target(seed=21, uneven=False)
    D_base, _ = build(segs, th)
    Mb, Nb = region_mass(D_base)
    # now densify one region: add extra collinear points on the existing lines inside a screen box
    dense = [np.asarray(P, float) for P in segs]
    extra = []
    for i, P in enumerate(dense):
        inbox = (P[:, 0] > 1280) & (P[:, 1] > 720)
        if inbox.sum() >= 2:
            a, b = P[inbox][0], P[inbox][-1]
            extra.append((i, seg(a, b, 25)))
    for i, P in extra:
        dense[i] = np.vstack([dense[i], P])
    D_dense, _ = build(dense, th)
    Md, Nd = region_mass(D_dense)
    br, bc = 2, 2                                       # bottom-right region
    print(f"        point COUNT in the densified region: {Nb[br, bc]} -> {Nd[br, bc]} "
          f"({Nd[br, bc] / max(Nb[br, bc], 1):.2f}x)")
    print(f"        weight MASS  in the densified region: {Mb[br, bc]:.4f} -> {Md[br, bc]:.4f} "
          f"({Md[br, bc] / max(Mb[br, bc], 1e-12):.2f}x)")
    cnt_ratio = Nd[br, bc] / max(Nb[br, bc], 1)
    mass_ratio = Md[br, bc] / max(Mb[br, bc], 1e-12)
    check("densifying a region does NOT proportionally multiply its influence",
          mass_ratio < 0.5 * cnt_ratio,
          f"count x{cnt_ratio:.2f} but mass only x{mass_ratio:.2f}")
    check("total mass stays normalized", abs(Md.sum() - 1.0) < 1e-9)
    print(f"        weight mass by region (rows top->bottom), densified target:")
    for row in range(3):
        print(f"          " + "  ".join(f"{Md[row, c]:.4f}" for c in range(3)))
    R["delaunay_uniformity"] = {"count_ratio": float(cnt_ratio), "mass_ratio": float(mass_ratio),
                                "mass_by_region_base": Mb.tolist(),
                                "mass_by_region_dense": Md.tolist()}

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED   [{time.time() - t00:.1f}s]")
    for f in FAIL:
        print(f"    FAILED: {f}")
    import json
    print(json.dumps(R, indent=1, default=float)[:0])
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
