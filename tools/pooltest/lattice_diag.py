#!/usr/bin/env python3
"""Why does lattice assembly fail? Localize index contradictions and attribute them to a cause.

The corpus inventory found four cameras of forty where the LARGEST connected component is
inconsistent, so `_recover_indices`'s fail-closed rule discards every observation in it:

    2016-06-17-1 Panguingue Right    1 contradiction  -> 247 observations lost
    2016-08-08-4 Panguingue Left     2 contradictions -> 526 observations lost
    2016-08-08-4 Panguingue Right    4 contradictions -> 523 observations lost
    2016-08-01-1 Clearwater Left    35 contradictions -> 397 observations lost

Fail-closed is right; component-granular fail-closed is too coarse. But before changing the
granularity we have to know WHAT contradicts, because if the cause is a systematic indexing defect
then dropping the offending edges would paper over it -- which is exactly what happened on
`2015-06-22-1 Clearwater`, where the data was blameless and the traversal canonicalization was wrong.

This script does not fit anything and does not modify the lattice code. It re-derives the adjacency
graph exactly as `_recover_indices` does, then for each contradicting edge reports the line it came
from, that line's geometry, and a verdict against these hypotheses:

  FAMILY      the line sits near the 45-degree family boundary, so it may be split into the wrong
              orientation family; its steps are then (0,1) where they should be (1,0), and every
              cycle through it accumulates the wrong index.
  SKIP        the gap passed UNIT_STEP_TOL but is really a multi-corner skip -- a missed detection
              whose gap ratio was flattened by foreshortening or by neighbouring skips.
  COLLISION   the edge touches an observation shared by two lines of the SAME family, or a corner
              whose exact-coordinate merge tied two lattice positions together.
  CYCLE       none of the above; the edge is locally ordinary and only disagrees globally.

Run directly for the report; `--all` sweeps the whole corpus rather than the four known failures.
"""

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict, deque

import numpy as np

import corpus
import harness_import

LT = harness_import.load("lattice")


def build_graph(C):
    """Re-derive the edge list of `_recover_indices`, keeping per-edge provenance.

    Must stay in step with `lattice._recover_indices`. It is re-derived rather than returned by that
    function so this diagnostic cannot change production behaviour by existing.
    """
    fam_dir = LT._family_reference_dirs(C)
    edges = []
    for li, ln in enumerate(C.lines):
        mem = ln["members"]
        if len(mem) < 2:
            continue
        # members were already oriented in place by _recover_indices during load_captures
        P = C.xy[mem]
        g = np.hypot(*np.diff(P, axis=0).T)
        for i, gi in enumerate(g):
            exp_gap = LT._expected_gap(g, i)
            ratio = gi / exp_gap if exp_gap > 0 else 1.0
            if abs(ratio - 1.0) > LT.UNIT_STEP_TOL:
                continue
            step = (0, 1) if ln["family"] == 0 else (1, 0)
            edges.append(dict(a=mem[i], b=mem[i + 1], step=step, line=li,
                              family=ln["family"], gap=float(gi), gap_ratio=float(ratio)))
    return edges, fam_dir


def contradicting_edges(C, edges):
    """Edges whose endpoints' propagated indices disagree with the edge's own step."""
    rc = C.rc_all if hasattr(C, "rc_all") else None
    if rc is None:
        # recompute the pre-masking BFS labels; C.rc has had unreliable components NaN-ed out
        n = C.n
        adj = defaultdict(list)
        for e in edges:
            adj[e["a"]].append((e["b"], e["step"]))
            adj[e["b"]].append((e["a"], (-e["step"][0], -e["step"][1])))
        rc = np.full((n, 2), np.nan)
        comp = np.full(n, -1, int)
        nc = 0
        for s in range(n):
            if comp[s] != -1:
                continue
            comp[s] = nc
            rc[s] = (0.0, 0.0)
            dq = deque([s])
            while dq:
                u = dq.popleft()
                for v, st in adj[u]:
                    if comp[v] == -1:
                        comp[v] = nc
                        rc[v] = rc[u] + np.array(st, float)
                        dq.append(v)
            nc += 1
        C.rc_all, C.comp_all = rc, comp
    bad = []
    for e in edges:
        d = rc[e["b"]] - rc[e["a"]]
        if not np.allclose(d, e["step"]):
            e = dict(e, observed_step=d.tolist())
            bad.append(e)
    return bad


def classify(C, e, fam_dir, same_family_obs, line_gaps):
    """A verdict for one contradicting edge. Ordered most specific first."""
    ln = C.lines[e["line"]]
    ang = float(ln["angle"])
    reasons = []
    # FAMILY: how close is this line to the boundary between the two family references?
    if len(fam_dir) == 2:
        a0 = math.degrees(math.atan2(fam_dir[0][1], fam_dir[0][0])) % 180.0
        a1 = math.degrees(math.atan2(fam_dir[1][1], fam_dir[1][0])) % 180.0
        d0 = min((ang - a0) % 180.0, (a0 - ang) % 180.0)
        d1 = min((ang - a1) % 180.0, (a1 - ang) % 180.0)
        margin = abs(d0 - d1)
        if margin < 20.0:
            reasons.append(("FAMILY", f"angle {ang:.1f} deg is {d0:.1f}/{d1:.1f} from the two family "
                                      f"references; margin only {margin:.1f} deg"))
    else:
        margin = float("nan")
    # SKIP: the gap is large relative to the whole line, not just its immediate neighbours
    gl = line_gaps[e["line"]]
    med_line = float(np.median(gl)) if len(gl) else e["gap"]
    line_ratio = e["gap"] / med_line if med_line else 1.0
    if line_ratio > 1.0 + LT.UNIT_STEP_TOL:
        reasons.append(("SKIP", f"gap {e['gap']:.1f} px is {line_ratio:.2f}x the line median "
                                f"{med_line:.1f} px though only {e['gap_ratio']:.2f}x its neighbours"))
    # COLLISION: an endpoint shared by two lines of the same family
    for m in (e["a"], e["b"]):
        if m in same_family_obs:
            reasons.append(("COLLISION", f"observation {m} is shared by same-family lines "
                                         f"{same_family_obs[m]}"))
            break
    if not reasons:
        reasons.append(("CYCLE", f"locally ordinary: gap ratio {e['gap_ratio']:.2f}, "
                                 f"line-median ratio {line_ratio:.2f}, family margin {margin:.1f} deg"))
    return reasons


def analyze(vsd, clip, verbose=True):
    caps = LT.load_captures(vsd, clip)
    recs = []
    for C in caps:
        edges, fam_dir = build_graph(C)
        bad = contradicting_edges(C, edges)
        # observations touched by two or more lines of one family
        byobs = defaultdict(list)
        for li, ln in enumerate(C.lines):
            for m in ln["members"]:
                byobs[m].append(li)
        same_family_obs = {m: ls for m, ls in byobs.items() if len(ls) >= 2 and
                           len({C.lines[i]["family"] for i in ls}) == 1}
        line_gaps = {}
        for li, ln in enumerate(C.lines):
            P = C.xy[ln["members"]]
            line_gaps[li] = np.hypot(*np.diff(P, axis=0).T) if len(P) > 1 else np.array([])

        per_line = Counter(e["line"] for e in bad)
        verdicts = Counter()
        detail = []
        for e in bad:
            rs = classify(C, e, fam_dir, same_family_obs, line_gaps)
            verdicts[rs[0][0]] += 1
            detail.append(dict(edge=e, reasons=[list(r) for r in rs]))

        rec = dict(clip=clip, timecode=C.timecode, n_obs=C.n, n_edges=len(edges),
                   n_contradicting=len(bad), lines_involved=len(per_line),
                   per_line={str(k): v for k, v in per_line.most_common()},
                   verdicts=dict(verdicts), detail=detail,
                   n_lines=C.notes["n_lines"], reliably_indexed=int(C.notes["reliably_indexed"]),
                   largest_component=C.notes["largest_component"])
        recs.append(rec)

        if verbose:
            print(f"\n  {clip} @ {C.timecode}")
            print(f"    {C.n} observations, {len(edges)} unit-step edges, "
                  f"{len(bad)} contradicting ({len(per_line)} lines of {C.notes['n_lines']} involved)")
            if bad:
                print(f"    verdicts: {dict(verdicts)}")
                for li, k in per_line.most_common():
                    ln = C.lines[li]
                    print(f"      line {li:3d}  family {ln['family']}  angle {ln['angle']:6.1f} deg  "
                          f"{ln['stored']:3d} points  {k} contradicting edge(s)")
                for d in detail[:8]:
                    e = d["edge"]
                    print(f"      edge line {e['line']:3d} obs {e['a']}->{e['b']} "
                          f"step {e['step']} observed {[round(v, 1) for v in e['observed_step']]}")
                    for tag, why in d["reasons"]:
                        print(f"         {tag:10} {why}")
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="sweep the whole corpus, not just failures")
    ap.add_argument("--json", default=None)
    ap.add_argument("--drift-dir", default=None)
    ap.add_argument("--chena-dir", default=None)
    args = ap.parse_args()

    docs = corpus.documents(args.drift_dir, args.chena_dir)
    bykey = {f"{d['code']} {d['site']}": d for d in docs}
    FAILURES = [("2016-06-17-1 Panguingue", "Right Camera"),
                ("2016-08-08-4 Panguingue", "Left Camera"),
                ("2016-08-08-4 Panguingue", "Right Camera"),
                ("2016-08-01-1 Clearwater", "Left Camera")]

    targets = []
    if args.all:
        for d in docs:
            if d["present"]:
                for clip, _ in corpus.clips_with_plumblines(d["vsd"]):
                    targets.append((f"{d['code']} {d['site']}", clip))
    else:
        targets = FAILURES

    print("=" * 100)
    print("LATTICE CONTRADICTION DIAGNOSIS")
    print("=" * 100)

    out = []
    for name, clip in targets:
        d = bykey.get(name)
        if d is None or not d["present"]:
            print(f"  ABSENT: {name}")
            continue
        for rec in analyze(d["vsd"], clip, verbose=not args.all or True):
            rec["document"] = name
            out.append(rec)

    print("\n  TOTALS")
    tv = Counter()
    for r in out:
        tv.update(r["verdicts"])
    print(f"    cameras examined {len({(r['document'], r['clip']) for r in out})}, "
          f"contradicting edges {sum(r['n_contradicting'] for r in out)}")
    print(f"    verdicts {dict(tv)}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=1)
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
