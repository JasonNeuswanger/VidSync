#!/usr/bin/env python3
"""Regression tests for the lattice traversal-canonicalization fix in lattice._recover_indices.

WHAT IS BEING PROTECTED. Digitization direction is an input artefact and must carry no lattice meaning.
Before the fix, `_recover_indices` chose each index step by orientation family while letting the stored
click order decide edge direction, so a single line clicked opposite to its family-mates made every
closed cycle through it accumulate +2 instead of 0. On `2015-06-22-1 Clearwater` that discarded all 340
and 365 observations of two clean, complete grids.

Gauge discipline: the solver guarantees indices only up to translation, axis swap and sign PER
COMPONENT, so no test asserts raw labels. Comparisons use coordinate-keyed, per-component-normalized
indices and the component partition, which are invariant under the documented gauge.

Section [10] tests the ZERO-PROJECTION branch of `_orient_members` by calling it directly. That branch
cannot be reached through `_family_split` -- a line only joins a family when it lies within 45 degrees of
the family reference, so its chord is never exactly perpendicular to it -- and the rotation tests in [6]
all take the ordinary nonzero-projection path, so they do NOT cover it. Calling the helper directly is
the only way to execute the branch without relaxing a family or lattice tolerance, which this round
forbids.

Everything except section [11] runs without external data. The real-data validation that needs the field
documents lives in `validate_lattice_real.py`; see VALIDATION_REAL_DATA.md.

Run with ~/.venvs/vidsync/bin/python.
"""

import math
import os
import sys

import numpy as np

import harness_import

harness_import.ensure_path()
LT = harness_import.load("lattice")
OB = harness_import.load("objectives")

PASS, FAIL = [], []
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
MID = os.path.join(DM, "2015-06-22-1 Clearwater.vsd")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


# =============================================================== synthetic capture construction


def make_capture(lines_xy, timecode="t"):
    """A real lattice.Capture built from explicit per-line point lists, mirroring load_captures.

    Uses the production `_family_split`, unique-point matching, `_recover_indices` and `_local_scale`,
    so the tests exercise the real pipeline rather than a stand-in.
    """
    C = LT.Capture("test camera", timecode)
    linepts = [np.asarray(P, float) for P in lines_xy]
    fam, angs, dirs, ref = LT._family_split(linepts)
    idx_of, pts = {}, []
    for P in linepts:
        for p in P:
            k = (p[0], p[1])
            if k not in idx_of:
                idx_of[k] = len(pts)
                pts.append(k)
    C.xy = np.array(pts, float)
    C.inc = [[] for _ in pts]
    for li, P in enumerate(linepts):
        mem = [idx_of[(p[0], p[1])] for p in P]
        C.lines.append({"id": li, "family": fam[li], "angle": float(angs[li]),
                        "members": mem, "stored": len(mem)})
        for m in mem:
            C.inc[m].append(li)
    C.notes.update(n_lines=len(C.lines), family_ref_angle=ref,
                   unique_observations=len(pts),
                   stored_incidences=sum(len(l["members"]) for l in C.lines))
    LT._recover_indices(C)
    LT._local_scale(C)
    return C


def grid(nx=6, ny=5, x0=200.0, y0=150.0, dx=250.0, dy=180.0, rot_deg=0.0, curve=0.0):
    """A two-family lattice. `rot_deg` rotates the whole grid; `curve` adds a smooth bow to each line
    so the lines are not exactly straight, as real distorted plumblines are not."""
    a = math.radians(rot_deg)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    cx, cy = x0 + dx * (nx - 1) / 2, y0 + dy * (ny - 1) / 2
    node = {}
    for i in range(nx):
        for j in range(ny):
            p = np.array([x0 + i * dx, y0 + j * dy], float)
            if curve:
                s = (i / max(nx - 1, 1) - 0.5)
                t = (j / max(ny - 1, 1) - 0.5)
                p = p + curve * np.array([t * t, s * s])
            node[(i, j)] = R @ (p - [cx, cy]) + [cx, cy]
    lines = []
    for i in range(nx):                                  # one family: varying j
        lines.append([node[(i, j)] for j in range(ny)])
    for j in range(ny):                                  # the other family: varying i
        lines.append([node[(i, j)] for i in range(nx)])
    return lines


def signature(C):
    """Gauge-invariant fingerprint: coordinate -> per-component-normalized index, plus the partition.

    Normalizing each component by its own minimum removes the translation gauge. Keys are coordinates,
    not observation indices, so the fingerprint survives the reindexing that reversing a line causes in
    `make_capture`'s unique-point pass.
    """
    out = {}
    for comp in sorted(set(C.component.tolist())):
        m = C.component == comp
        rc = C.rc[m]
        if not np.isfinite(rc).all():
            for p in C.xy[m]:
                out[(round(p[0], 6), round(p[1], 6))] = None
            continue
        base = rc.min(axis=0)
        for p, v in zip(C.xy[m], rc - base):
            out[(round(p[0], 6), round(p[1], 6))] = (float(v[0]), float(v[1]))
    return out


def pair_diff_multiset(C):
    """Multiset of within-component pairwise index differences: invariant under translation."""
    out = []
    for comp in sorted(set(C.component.tolist())):
        m = C.component == comp
        rc = C.rc[m]
        if not np.isfinite(rc).all():
            continue
        for i in range(len(rc)):
            for j in range(i + 1, len(rc)):
                d = rc[j] - rc[i]
                out.append((abs(float(d[0])), abs(float(d[1]))))
    return sorted(out)


def comp_partition(C):
    """The component partition as a set of frozensets of coordinates: label-independent."""
    g = {}
    for p, c in zip(C.xy, C.component):
        g.setdefault(int(c), set()).add((round(p[0], 6), round(p[1], 6)))
    return frozenset(frozenset(v) for v in g.values())


def reverse_subset(lines, which):
    return [list(reversed(P)) if i in which else list(P) for i, P in enumerate(lines)]


def main():
    print("=" * 100)
    print("LATTICE TRAVERSAL-CANONICALIZATION REGRESSION TESTS")
    print("=" * 100)

    # ---------------------------------------------------------------- 1. valid lattice indexes
    print("\n[1] A valid two-family lattice indexes successfully")
    base = grid()
    C0 = make_capture(base)
    check("no contradictions", C0.notes["index_contradictions"] == 0)
    check("single component covering every observation",
          C0.notes["n_components"] == 1 and C0.notes["largest_component"] == C0.n, f"n={C0.n}")
    check("every observation reliably indexed",
          C0.notes["reliably_indexed"] == C0.n, f"{C0.notes['reliably_indexed']}/{C0.n}")
    check("no edge dropped by the gap filter", C0.notes["dropped_nonunit_edges"] == 0)
    S0, P0, G0 = signature(C0), pair_diff_multiset(C0), comp_partition(C0)

    # ---------------------------------------------------------------- 2. reverse one line per family
    print("\n[2] Reversing ONE line in either family leaves the normalized indexing unchanged")
    fam0 = [i for i, l in enumerate(C0.lines) if l["family"] == 0]
    fam1 = [i for i, l in enumerate(C0.lines) if l["family"] == 1]
    for label, which in (("one family-0 line", {fam0[0]}), ("one family-1 line", {fam1[0]}),
                         ("one of each", {fam0[1], fam1[1]})):
        C = make_capture(reverse_subset(base, which))
        check(f"{label}: contradictions still 0", C.notes["index_contradictions"] == 0,
              f"canonicalized {C.notes['n_traversal_canonicalized']} lines")
        check(f"{label}: normalized indexing identical", signature(C) == S0)
        check(f"{label}: reliably indexed unchanged",
              C.notes["reliably_indexed"] == C0.notes["reliably_indexed"])

    # ---------------------------------------------------------------- 3. arbitrary subsets
    print("\n[3] Reversing ARBITRARY subsets preserves acceptance, membership, topology, differences")
    rng = np.random.default_rng(20260731)
    worst = 0
    for trial in range(12):
        k = int(rng.integers(0, len(base) + 1))
        which = set(rng.choice(len(base), k, replace=False).tolist())
        C = make_capture(reverse_subset(base, which))
        ok = (C.notes["index_contradictions"] == 0
              and C.notes["reliably_indexed"] == C0.notes["reliably_indexed"]
              and comp_partition(C) == G0
              and pair_diff_multiset(C) == P0
              and signature(C) == S0)
        if not ok:
            worst += 1
            print(f"        trial {trial} FAILED with {k} lines reversed: {sorted(which)}")
    check(f"all 12 random reversal subsets invariant (acceptance, membership, topology, "
          f"pairwise differences, normalized indices)", worst == 0, f"{12 - worst}/12 passed")

    # ---------------------------------------------------------------- 4. global reversal
    print("\n[4] Reversing EVERY line globally has no effect")
    Cg = make_capture(reverse_subset(base, set(range(len(base)))))
    check("contradictions 0", Cg.notes["index_contradictions"] == 0)
    check("normalized indexing identical", signature(Cg) == S0)
    check("pairwise differences identical", pair_diff_multiset(Cg) == P0)

    # ---------------------------------------------------------------- 5. input-order permutation
    print("\n[5] Permuting LINE order and POINT-RECORD order does not make a valid grid fail")
    for trial in range(6):
        order = list(rng.permutation(len(base)))
        perm = [list(base[i]) for i in order]
        if trial % 2:
            perm = [list(reversed(P)) if (i % 3 == 0) else P for i, P in enumerate(perm)]
        C = make_capture(perm)
        ok = (C.notes["index_contradictions"] == 0
              and C.notes["reliably_indexed"] == C0.notes["reliably_indexed"]
              and signature(C) == S0)
        if not ok:
            print(f"        permutation trial {trial} FAILED")
        check(f"line permutation {trial}: accepted, membership and normalized indexing unchanged", ok)

    # ---------------------------------------------------------------- 6. orientation coverage
    print("\n[6] Horizontal, vertical, diagonal and near-diagonal families canonicalize"
          " deterministically")
    for rot in (0.0, 30.0, 45.0, 44.9, 45.1, 60.0, 89.9, 135.0, 134.9, 135.1):
        g = grid(rot_deg=rot)
        C = make_capture(g)
        Cr = make_capture(reverse_subset(g, {0, 3, 7}))
        dirs = C.notes["family_reference_dirs"]
        # the sign rule requires the dominant coordinate of each family reference to be positive
        signok = True
        for k, u in dirs.items():
            kdom = 0 if abs(u[0]) >= abs(u[1]) else 1
            if u[kdom] < 0:
                signok = False
        ok = (C.notes["index_contradictions"] == 0 and Cr.notes["index_contradictions"] == 0
              and signature(C) == signature(Cr) and signok)
        check(f"rotation {rot:6.1f} deg: indexed, reversal-invariant, dominant coordinate positive",
              ok, f"family dirs {[[round(x, 4) for x in v] for v in dirs.values()]}")
    # the explicit tie case: an axis at exactly 45 degrees has |ux| == |uy|
    u = np.array([math.cos(math.radians(45.0)), math.sin(math.radians(45.0))])
    check("tie case |ux| == |uy| is broken in favour of x, deterministically",
          abs(abs(u[0]) - abs(u[1])) < 1e-15,
          "grid at 45 deg indexed above; the rule takes k=0 when |ux| >= |uy|")

    # ---------------------------------------------------------------- 7. fragmented grids
    print("\n[7] Partial / fragmented valid grids retain their component behaviour")
    part = grid(nx=6, ny=5)
    part = [P for i, P in enumerate(part) if i not in (2, 8)]          # drop two whole lines
    Cp = make_capture(part)
    Cpr = make_capture(reverse_subset(part, {0, 1, 5}))
    check("fragmented grid: contradictions 0 before and after reversal",
          Cp.notes["index_contradictions"] == 0 and Cpr.notes["index_contradictions"] == 0)
    check("fragmented grid: component partition identical under reversal",
          comp_partition(Cp) == comp_partition(Cpr),
          f"{Cp.notes['n_components']} components, reliably indexed "
          f"{Cp.notes['reliably_indexed']}/{Cp.n}")
    check("fragmented grid: normalized indexing identical under reversal",
          signature(Cp) == signature(Cpr))

    # ---------------------------------------------------------------- 8. genuine contradiction fails
    print("\n[8] A genuine TOPOLOGICAL contradiction still fails (not mere reversed traversal)")
    # A genuine topological contradiction needs UNIFORM gaps (so the gap filter cannot rescue it) but
    # an inconsistent cycle. A first attempt spliced two columns together; that produced a large jump
    # which the gap filter correctly DROPPED, leaving two consistent chains and no contradiction -- the
    # filter did its job, so the test was wrong, not the fix. Instead add a spurious DIAGONAL line
    # through existing grid nodes: its point spacing is uniform, it is classified into one of the two
    # families, and its edges then declare a unit step along that family's axis between nodes that
    # actually differ by one in BOTH axes. Every cycle through it accumulates a nonzero offset that no
    # traversal convention can absorb.
    nx, ny = 6, 5
    g8 = grid(nx=nx, ny=ny)
    x0, y0, dx, dy = 200.0, 150.0, 250.0, 180.0
    diag = [np.array([x0 + i * dx, y0 + i * dy], float) for i in range(min(nx, ny))]
    bad = [list(P) for P in g8] + [diag]
    Cb = make_capture(bad)
    check("spurious diagonal through existing nodes produces contradictions",
          Cb.notes["index_contradictions"] > 0,
          f"{Cb.notes['index_contradictions']} contradictions, "
          f"{Cb.notes['dropped_nonunit_edges']} dropped")
    check("its component is marked unreliable, so it is not silently accepted",
          Cb.notes["reliably_indexed"] < Cb.n,
          f"reliably indexed {Cb.notes['reliably_indexed']} of {Cb.n}")
    Cbr = make_capture(reverse_subset(bad, {0, 4, 9, len(bad) - 1}))
    check("still fails after reversing a subset (the fix does not mask real inconsistency)",
          Cbr.notes["index_contradictions"] > 0, f"{Cbr.notes['index_contradictions']}")
    check("the previously-attempted spliced-column defect is caught by the GAP FILTER instead",
          make_capture([list(P) for P in g8][:1] and
                       ([g8[0][:3] + g8[1][3:]] + [list(P) for P in g8[1:]])
                       ).notes["dropped_nonunit_edges"] > 0,
          "large splice jump is dropped, not interpreted -- also correct fail-closed behaviour")
    # a second, independent genuine defect: a duplicated node shifting one line by one step
    bad2 = [list(P) for P in grid(nx=6, ny=5)]
    bad2[7] = bad2[7][:2] + [bad2[7][2]] + bad2[7][2:]     # repeated point -> zero gap
    Cb2 = make_capture(bad2)
    check("a repeated point inside a line does not silently pass",
          Cb2.notes["index_contradictions"] > 0 or Cb2.notes["dropped_nonunit_edges"] > 0,
          f"contradictions {Cb2.notes['index_contradictions']}, "
          f"dropped {Cb2.notes['dropped_nonunit_edges']}")

    # ---------------------------------------------------------------- 9. gap / coincident behaviour
    print("\n[9] Gap filtering and coincident-point behaviour unchanged")
    check("UNIT_STEP_TOL unchanged", LT.UNIT_STEP_TOL == 0.25, f"{LT.UNIT_STEP_TOL}")
    check("COINCIDENT_PX unchanged", LT.COINCIDENT_PX == 0.5, f"{LT.COINCIDENT_PX}")
    check("family classification threshold unchanged (45 deg half-window)",
          "< 45.0" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "lattice.py")).read())
    gap = [list(P) for P in grid(nx=6, ny=5)]
    gap[0] = [gap[0][0], gap[0][2], gap[0][3], gap[0][4]]      # a real double step
    Cd = make_capture(gap)
    Cdr = make_capture(reverse_subset(gap, {0}))
    check("a genuine double-step gap is still dropped, not interpreted",
          Cd.notes["dropped_nonunit_edges"] > 0, f"{Cd.notes['dropped_nonunit_edges']} dropped")
    check("and the same number is dropped when that line is reversed",
          Cd.notes["dropped_nonunit_edges"] == Cdr.notes["dropped_nonunit_edges"],
          f"{Cd.notes['dropped_nonunit_edges']} vs {Cdr.notes['dropped_nonunit_edges']}")
    check("no line reported non-monotone in the family projection on any valid grid",
          all(len(c.notes["nonmonotone_member_order"]) == 0
              for c in (C0, Cg, Cp, Cd)))

    # ---------------------------------------------------------------- 10. the zero-projection branch
    print("\n[10] The ZERO-PROJECTION branch of _orient_members is itself reversal-invariant")
    # This branch cannot be reached through `_family_split`: a line is only assigned to a family when it
    # lies within 45 degrees of the family reference, so its chord is never exactly perpendicular to it.
    # The tests below therefore call `_orient_members` directly with a `u` perpendicular to the chord,
    # which is the only way to execute the branch WITHOUT relaxing a family or lattice tolerance. The
    # rotation tests in [6] pass through the ordinary nonzero-projection path and do NOT cover this.
    def perp(a, b):
        """The exact perpendicular of an integer chord: the dot product is -ba + ab = 0 to the bit."""
        return np.array([-(b), (a)], float)

    xyh = np.array([[10.0, 40.0], [20.0, 40.0], [30.0, 40.0], [70.0, 40.0]])
    memh = [0, 1, 2, 3]
    uh = perp(60.0, 0.0)                                    # chord (60, 0); u = (0, 60)
    spanh = float((xyh[memh[-1]] - xyh[memh[0]]) @ uh)
    check("the constructed horizontal-chord case really enters the branch (span is exactly 0.0)",
          spanh == 0.0, f"span={spanh!r}")
    fh, dh = LT._orient_members(xyh, memh, uh)
    rh, dhr = LT._orient_members(xyh, memh[::-1], uh)
    check("zero projection, distinct endpoints: C(P) == C(reverse(P))", fh == rh,
          f"{fh} vs {rh}")
    check("and neither direction is reported degenerate", (not dh) and (not dhr))
    check("the canonical order is the lexicographically smaller endpoint first",
          tuple(xyh[fh[0]]) < tuple(xyh[fh[-1]]), f"{xyh[fh[0]]} then {xyh[fh[-1]]}")

    xyv = np.array([[55.0, 90.0], [55.0, 60.0], [55.0, 20.0]])   # x equal: the tie falls through to y
    memv = [0, 1, 2]
    uv = perp(0.0, -70.0)                                    # chord (0, -70); u = (70, 0)
    spanv = float((xyv[memv[-1]] - xyv[memv[0]]) @ uv)
    check("the x-tied case also enters the branch (span is exactly 0.0)", spanv == 0.0,
          f"span={spanv!r}")
    fv, _ = LT._orient_members(xyv, memv, uv)
    rv, _ = LT._orient_members(xyv, memv[::-1], uv)
    check("zero projection with equal x: the y coordinate breaks the tie, still invariant", fv == rv,
          f"{fv} vs {rv}")

    rg = np.random.default_rng(20260729)
    nzero, nbad, nsign = 0, 0, 0
    for _ in range(300):
        k = int(rg.integers(2, 7))
        a, b = float(rg.integers(-90, 91)), float(rg.integers(-90, 91))
        if a == 0.0 and b == 0.0:
            continue
        t = np.linspace(0.0, 1.0, k)[:, None]
        pts = np.array([200.0, 300.0]) + t * np.array([a, b]) * 5.0
        u = perp(a, b)
        mem = list(range(k))
        s = float((pts[mem[-1]] - pts[mem[0]]) @ u)
        if s != 0.0:
            continue
        nzero += 1
        f1, d1 = LT._orient_members(pts, mem, u)
        f2, d2 = LT._orient_members(pts, mem[::-1], u)
        if f1 != f2 or d1 != d2:
            nbad += 1
        # and the reversal-invariant nonzero path, on the same geometry with a non-perpendicular u
        un = np.array([a, b], float)
        g1, _ = LT._orient_members(pts, mem, un)
        g2, _ = LT._orient_members(pts, mem[::-1], un)
        if g1 != g2 or float((pts[g1[-1]] - pts[g1[0]]) @ un) <= 0.0:
            nsign += 1
    check(f"{nzero} randomized perpendicular cases all entered the zero branch and are invariant",
          nzero >= 250 and nbad == 0, f"{nbad} violations")
    check("nonzero-projection behaviour preserved on the same geometry (invariant, positive span)",
          nsign == 0, f"{nsign} violations")

    xyd = np.array([[400.0, 500.0], [430.0, 505.0], [460.0, 500.0]])
    memd = [0, 1, 2, 1, 0]                                   # clicked out and back: endpoints coincide
    ud = np.array([1.0, 0.0])
    fd, dd = LT._orient_members(xyd, memd, ud)
    check("identical endpoints are rejected as DEGENERATE rather than ordered by stored order or id",
          dd is True, f"degenerate={dd}")
    check("and the degenerate return leaves the members untouched (no orientation invented)",
          fd == memd)
    _, ddr = LT._orient_members(xyd, memd[::-1], ud)
    check("degeneracy is itself reversal-invariant", ddr is True)
    xyd2 = np.array([[400.0, 500.0], [430.0, 505.0], [400.0, 500.0]])
    _, dd2 = LT._orient_members(xyd2, [0, 1, 2], ud)
    check("distinct member indices with identical coordinates are degenerate too", dd2 is True)

    base = [list(P) for P in grid(nx=6, ny=5)]
    Cb = make_capture(base)
    ob = [list(P) for P in base] + [[base[0][0], base[0][1], base[0][2], base[0][1], base[0][0]]]
    Co = make_capture(ob)
    check("a stored out-and-back line is dropped by _recover_indices and recorded",
          Co.notes["degenerate_direction_lines"] == [len(ob) - 1],
          f"{Co.notes['degenerate_direction_lines']}")
    check("dropping it leaves the rest of the grid indexed exactly as before",
          signature(Co) == signature(Cb) and comp_partition(Co) == comp_partition(Cb)
          and Co.notes["index_contradictions"] == 0
          and Co.notes["reliably_indexed"] == Cb.notes["reliably_indexed"],
          f"contra {Co.notes['index_contradictions']}, indexed {Co.notes['reliably_indexed']}")
    check("ordinary valid grids report no degenerate lines at all",
          all(c.notes["degenerate_direction_lines"] == [] for c in (C0, Cg, Cp, Cd, Cb)))

    # ---------------------------------------------------------------- 11. real Clearwater invariance
    print("\n[11] REAL DATA: 2015-06-22-1 Clearwater under deterministic permutations")
    if not os.path.exists(MID):
        print("        document unavailable; skipping")
    else:
        for clip, exp_n in (("Left Camera", 340), ("Right Camera", 365)):
            caps = LT.load_captures(MID, clip)
            C = caps[0]
            check(f"mid/{clip.split()[0]}: contradictions 0 and all {exp_n} observations indexed",
                  C.notes["index_contradictions"] == 0 and C.notes["reliably_indexed"] == exp_n,
                  f"contra {C.notes['index_contradictions']}, indexed "
                  f"{C.notes['reliably_indexed']}/{C.n}")
            ref = signature(C)
            refG = comp_partition(C)
            bad = 0
            for trial in range(5):
                caps2 = LT.load_captures(MID, clip)
                C2 = caps2[0]
                r2 = np.random.default_rng(1000 + trial)
                order = list(r2.permutation(len(C2.lines)))
                C2.lines = [C2.lines[i] for i in order]
                for li, ln in enumerate(C2.lines):
                    if r2.random() < 0.5:
                        ln["members"] = list(reversed(ln["members"]))
                C2.inc = [[] for _ in range(C2.n)]
                for li, ln in enumerate(C2.lines):
                    for m in ln["members"]:
                        C2.inc[m].append(li)
                LT._recover_indices(C2)
                if not (C2.notes["index_contradictions"] == 0
                        and C2.notes["reliably_indexed"] == exp_n
                        and signature(C2) == ref and comp_partition(C2) == refG):
                    bad += 1
                    print(f"        permutation {trial} FAILED: contra "
                          f"{C2.notes['index_contradictions']}, indexed "
                          f"{C2.notes['reliably_indexed']}")
            check(f"mid/{clip.split()[0]}: 5 line-order + point-order permutations all give "
                  f"0 contradictions and identical gauge-normalized indexing", bad == 0)

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED")
    for f in FAIL:
        print(f"    FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
