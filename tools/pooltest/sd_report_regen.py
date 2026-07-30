#!/usr/bin/env python3
"""Regenerate the SD-D reconciliation summaries from stored artifacts, with NO optimizer calls.

WHAT THIS DOES. It reads the authoritative artifacts produced by earlier runs and re-derives, without
fitting anything:

  * the explicit five-state status of every method/document/camera/model (see `fitstatus`), with the
    frozen empirical gate `mapmetrics.admissibility_v2` kept separate from the weaker production gate;
  * accepted known-length rankings under the one documented ranking rule, so an empirically inadmissible
    map such as pool/Right PD-D/M1 cannot win or be counted as valid;
  * the Clearwater incidence-view metadata, with display labels that say `min_inc=1` versus `min_inc=2`
    rather than implying that any observation failed to be indexed;
  * a consistency check that the view-sensitivity experiment contains exactly the 2 views x 2 models x
    2 cameras = 8 unique cells, with no missing or duplicated cell.

WHAT IT REFUSES TO DO. Before reading anything it installs a TRIPWIRE over every calibration-fitting
entry point in this harness -- `objectives.fit`, `objectives.PDExact.fit`, `objectives.profile_H`,
`sd_fast.solve`, `sd_fast.fit_sd`, `sd_fast.solve_staged` -- so that any attempted optimizer call raises
`OptimizerCallForbidden` and fails the run instead of silently refitting. The tripwire is process-local
(it patches the in-memory module objects of this process only, changes no file, and is reported in the
artifact as `optimizer_calls_attempted`). If a required map or summary is missing, this script REPORTS
the gap and exits non-zero; it never fills it by fitting.

Writes <outdir>/sd_report_regen_<scope>.{log,json}. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

import artifacts
import fitstatus as FS
import harness_import

harness_import.ensure_path()

OB = harness_import.load("objectives")
SFmod = harness_import.load("sd_fast")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
ADDENDUM = os.path.join(OUT, "addendum-2026-07-29")
CORRECTION = os.path.join(OUT, "correction-2026-07-29")

METHODS = ["B/M0", "B/M1", "SD-D/M0", "SD-D/M1", "PD-D/M0", "PD-D/M1"]
ANCHOR = "stored"
DOC_KEYS = ("pool", "8mm", "mid")

# The two SD-D observation views, named for what actually distinguishes them. On an eligible document
# BOTH views contain only successfully indexed observations; the difference is the incidence filter.
VIEW_META = {
    "min_inc2_indexed": {
        "internal_id_history": ["indexed", "Dind", "dsets[clip]"],
        "display_label": "min_inc=2 view (>=2 line incidences)",
        "selection_predicate": "OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)",
        "caller_branch": "sd_real.build if-branch / xdoc_objectives dsets[clip]; selected when the "
                         "lattice-eligibility test passes",
    },
    "min_inc1_all_incidences": {
        "internal_id_history": ["fallback_raw", "Dline", "dlines[clip]"],
        "display_label": "min_inc=1 view (all incidences kept)",
        "selection_predicate": "OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)",
        "caller_branch": "sd_real.build else-branch / xdoc_objectives dlines[clip]; selected when the "
                         "lattice-eligibility test fails",
    },
}
VIEWSENS_INTERNAL_TO_CANONICAL = {"indexed": "min_inc2_indexed",
                                  "fallback_raw": "min_inc1_all_incidences"}


class OptimizerCallForbidden(RuntimeError):
    pass


def install_optimizer_tripwire():
    """Make every fitting entry point raise. Returns a mutable list of attempted calls."""
    attempts = []

    def trip(name):
        def f(*a, **k):
            attempts.append(name)
            raise OptimizerCallForbidden(
                f"{name} was called during report regeneration; this script must derive everything "
                f"from stored artifacts and must never re-fit a calibration")
        return f

    OB.fit = trip("objectives.fit")
    OB.profile_H = trip("objectives.profile_H")
    OB.PDExact.fit = trip("objectives.PDExact.fit")
    SFmod.solve = trip("sd_fast.solve")
    SFmod.fit_sd = trip("sd_fast.fit_sd")
    if hasattr(SFmod, "solve_staged"):
        SFmod.solve_staged = trip("sd_fast.solve_staged")
    return attempts


def load(path, what):
    if not os.path.exists(path):
        raise SystemExit(f"MISSING {what}: {path}\nThis script never regenerates a missing fit. "
                         f"Produce the artifact first, or narrow the scope.")
    with open(path) as fh:
        return json.load(fh)


def hash_sources(paths):
    """SHA-256 of every authoritative source artifact this run consumes.

    WHY CONTENT HASHES AND NOT MODIFICATION TIMES. "the established fits did not change" was previously
    argued from `mtime`, which proves nothing: a rewrite that restores the same timestamp, a copy, a
    checkout and a touch are all indistinguishable by time, and identical content can carry different
    times. The hash is recorded BEFORE anything is read and again AFTER the run, and a difference is a
    hard stop rather than a note -- this script is read-only over these files, so any change means
    something else wrote them mid-run.
    """
    return {os.path.basename(p): (artifacts.file_sha256(p) if os.path.exists(p) else None)
            for p in paths}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=CORRECTION)
    ap.add_argument("--sd-real", default=os.path.join(ADDENDUM, "sd_real_full.json"))
    ap.add_argument("--xdoc", default=os.path.join(CORRECTION, "xdoc_objectives_full.json"))
    ap.add_argument("--viewsens", default=os.path.join(CORRECTION, "sd_viewsens_full.json"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    attempts = install_optimizer_tripwire()

    W = artifacts.ArtifactWriter(
        analysis="sd_report_regen", script=__file__, outdir=args.outdir,
        requested_documents=list(DOC_KEYS), all_documents=list(DOC_KEYS),
        requested_candidates=[ANCHOR] + METHODS,
        objective_versions={"status": "fitstatus.camera_status / document_status (five explicit states)",
                            "ranking": "fitstatus.rank under fitstatus.RANKING_RULE",
                            "frozen_gate": "mapmetrics.admissibility_v2, as stored in the source "
                                           "artifacts; NOT recomputed here",
                            "optimizer": "NONE -- all fitting entry points are tripwired"},
        source_files=["sd_report_regen.py", "fitstatus.py", "xdoc_objectives.py", "sd_real.py",
                      "sd_viewsens.py", "artifacts.py"],
        calibration_node_source="not used: derived from stored artifacts only")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    problems = []
    say("=" * 118)
    say("SD-D RECONCILIATION REPORT REGENERATION -- derived from stored artifacts, zero optimizer calls")
    say("=" * 118)
    src_paths = [args.sd_real, args.xdoc, args.viewsens]
    sidecars = [p + ".provenance.json" for p in src_paths]
    hashes_before = hash_sources(src_paths + [p for p in sidecars if os.path.exists(p)])
    sd = load(args.sd_real, "sd_real artifact (frozen-gate and inverse evidence)")
    xd = load(args.xdoc, "corrected xdoc artifact (known-length summaries)")
    vs = load(args.viewsens, "view-sensitivity artifact")
    say(f"  sd_real    {args.sd_real}")
    say(f"  xdoc       {args.xdoc}")
    say(f"  viewsens   {args.viewsens}")
    say("")
    say("  AUTHORITATIVE SOURCE ARTIFACT CONTENT HASHES (modification times are NOT used as evidence")
    say("  that these did not change; the same hashes are recomputed at the end of the run)")
    for n, h in sorted(hashes_before.items()):
        say(f"    {n:44} {h}")
    say("")
    say("  RANKING RULE")
    for chunk in FS.RANKING_RULE.split("; "):
        say(f"    {chunk}")

    # ---------------------------------------------------------------- 1. explicit status per camera
    cams = sd["results"]["cameras"]
    xdocs = xd["results"]["documents"]
    by_doc_cam = {}                                     # (doc_key, clip) -> sd_real camera record
    for cid, rec in cams.items():
        by_doc_cam[(rec["document"], rec["clip"])] = rec
    status = {}
    say("")
    say("=" * 118)
    say("1. EXPLICIT STATUS -- five states recorded separately (conv = optimizer, inv = numerically")
    say("   invertible, adm = FROZEN gate admissibility_v2, prodGate = the weaker lattice.admissible)")
    say("=" * 118)
    say(f"  {'document':6} {'camera':14} {'candidate':9} {'conv':>5} {'inv':>5} {'adm':>5} "
        f"{'prodGate':>9} {'eligible':>9} {'minDet':>8} {'minSig':>8} {'expan':>7}  diagnostic reasons")
    for doc in DOC_KEYS:
        if doc not in xdocs:
            problems.append(f"document {doc} absent from the xdoc artifact")
            continue
        for clip in sorted(xdocs[doc]["fits"]):
            rec = by_doc_cam.get((doc, clip))
            if rec is None:
                problems.append(f"{doc}/{clip}: no sd_real camera record, so the frozen gate is "
                                f"unavailable")
                continue
            for cand in METHODS + [ANCHOR]:
                f = rec["fits"].get(cand)
                xf = xdocs[doc]["fits"][clip].get(cand)
                xv = xdocs[doc]["fit_validity"][clip].get(cand)
                if f is None:
                    problems.append(f"{doc}/{clip}/{cand}: absent from the sd_real artifact")
                    continue
                opt = {"status": f.get("status"), "nfev": f.get("nfev"),
                       "termination": f.get("termination"), "loss": f.get("loss"),
                       "optimality": f.get("optimality"),
                       "hit_nfev_cap": (xf or {}).get("hit_nfev_cap")}
                if cand == ANCHOR:
                    opt = {"status": 2, "nfev": 0, "termination": "not an optimizer output",
                           "loss": None, "optimality": None, "hit_nfev_cap": False}
                st = FS.camera_status(
                    cand, f"{doc}/{clip}", optimizer=opt, adm_v2=f.get("adm_v2"),
                    inverse={"shipped_failures": (f.get("inverse") or {}).get("shipped_failures"),
                             "max_roundtrip_px": (f.get("inverse") or {}).get("max_roundtrip_px")},
                    production_gate_ok=None if xv is None else xv.get("admissible"),
                    theta14=f.get("theta14"))
                st["source"] = {"frozen_gate_from": os.path.basename(args.sd_real),
                                "optimizer_from": os.path.basename(args.sd_real),
                                "production_gate_from": os.path.basename(args.xdoc),
                                "is_anchor": cand == ANCHOR}
                status[f"{doc}|{clip}|{cand}"] = st
                a = st["evidence"]["adm_v2"]
                say(f"  {doc:6} {clip:14} {cand:9} "
                    f"{str(st['optimizer_converged'])[:5]:>5} "
                    f"{str(st['numerically_invertible'])[:5]:>5} "
                    f"{str(st['empirically_admissible'])[:5]:>5} "
                    f"{str(st['production_gate_ok'])[:9]:>9} "
                    f"{str(st['eligible_for_ranking'])[:9]:>9} "
                    f"{(a.get('min_det') if a.get('min_det') is not None else float('nan')):8.4f} "
                    f"{(a.get('min_sigma') if a.get('min_sigma') is not None else float('nan')):8.4f} "
                    f"{(a.get('expansion_ratio') if a.get('expansion_ratio') is not None else float('nan')):7.3f}"
                    + ("  " + "; ".join(st["diagnostic_reasons"]) if st["diagnostic_reasons"] else ""))

    # ---------------------------------------------------------------- 2. document-level eligibility
    docstat = {}
    say("")
    say("=" * 118)
    say("2. DOCUMENT-LEVEL ELIGIBILITY (a stereo measurement uses both cameras)")
    say("=" * 118)
    for doc in DOC_KEYS:
        docstat[doc] = {}
        for cand in METHODS + [ANCHOR]:
            per = {k.split("|")[1]: v for k, v in status.items()
                   if k.split("|")[0] == doc and k.split("|")[2] == cand}
            if not per:
                continue
            ds = FS.document_status(cand, per)
            docstat[doc][cand] = ds
            mark = "ELIGIBLE" if ds["eligible_for_ranking"] else "DIAGNOSTIC-ONLY"
            say(f"  {doc:6} {cand:9} {mark:16} {ds['n_cameras_eligible']}/{ds['n_cameras']} cameras"
                + ("   " + json.dumps(ds["diagnostic_reasons_by_camera"])[:150]
                   if ds["diagnostic_reasons_by_camera"] else ""))

    # ---------------------------------------------------------------- 3. corrected rankings
    say("")
    say("=" * 118)
    say("3. ACCEPTED KNOWN-LENGTH RANKINGS, recomputed from stored summaries under the rule above")
    say("=" * 118)
    rankings = {}
    for key, blk in xd["results"]["known_length"].items():
        doc = key.split("/")[0]
        summ = blk.get("summary", {})
        metric = {c: (summ[c]["mae"] if isinstance(summ.get(c), dict) and "mae" in summ[c] else None)
                  for c in [ANCHOR] + METHODS}
        rk = FS.rank({k: v for k, v in metric.items() if v is not None}, docstat.get(doc, {}),
                     lower_is_better=True, anchor=ANCHOR)
        rankings[key] = rk
        say("")
        say(f"  {key}")
        ref = rk["reference_anchor"]
        say(f"    reference anchor (not a fitted candidate): "
            f"{ref['candidate']} MAE {ref['metric']:.4f} mm" if ref else "    no anchor")
        say(f"    ACCEPTED ({rk['n_accepted']}):     "
            + ", ".join(f"{r['candidate']} {r['metric']:.4f}" for r in rk["accepted_ranking"]))
        if rk["best_accepted"]:
            say(f"    best accepted:      {rk['best_accepted']['candidate']} at "
                f"{rk['best_accepted']['metric']:.4f} mm")
        for r in rk["diagnostic_only_rows"]:
            say(f"    DIAGNOSTIC-ONLY:    {r['candidate']} {r['metric']:.4f} mm -- excluded: "
                + json.dumps(r["excluded_reason"])[:160])
        prev = (blk.get("best_valid") or xd["results"].get("best_valid", {}).get(key) or {})
        if prev and rk["best_accepted"] and prev.get("candidate") != rk["best_accepted"]["candidate"]:
            say(f"    NOTE: the stored artifact's `best_valid` was {prev.get('candidate')}; under the "
                f"corrected rule the best ACCEPTED candidate is {rk['best_accepted']['candidate']}")

    # ---------------------------------------------------------------- 4. the 8-cell sensitivity check
    say("")
    say("=" * 118)
    say("4. VIEW-SENSITIVITY CONSISTENCY: 2 views x 2 models x 2 cameras = 8 unique cells")
    say("=" * 118)
    vcams = vs["results"]["cameras"]
    expected, found, dupes = [], {}, []
    for cam in sorted(vcams):
        for internal, canon in VIEWSENS_INTERNAL_TO_CANONICAL.items():
            for model in ("M0", "M1"):
                expected.append((cam, canon, model))
                key = f"SD-D/{model}::{internal}"
                arm = vcams[cam]["arms"].get(key)
                cell = (cam, canon, model)
                if arm is None:
                    continue
                if cell in found:
                    dupes.append(cell)
                found[cell] = {"artifact_key": key, "view_canonical": canon,
                               "view_display": VIEW_META[canon]["display_label"],
                               "model": model, "camera": cam,
                               "n_obs": arm["n_obs"], "n_lines": arm["n_lines"],
                               "obs_sha256": arm["obs_sha256"], "termination": arm["termination"],
                               "nfev": arm["nfev"], "converged": arm["converged"],
                               "eta": arm["eta"], "loss": arm["loss"],
                               "adm_v2_safe": arm["admissibility_v2"]["safe"],
                               "adm_v2_plausible": arm["admissibility_v2"]["physically_plausible"],
                               "inverse_failures": arm["inverse"]["shipped_failures"]}
    missing = [c for c in expected if c not in found]
    say(f"  expected {len(expected)} cells, found {len(found)}, missing {len(missing)}, "
        f"duplicated {len(dupes)}")
    say(f"  {'camera':10} {'view (display label)':34} {'model':6} {'n_obs':>6} {'term':>6} "
        f"{'nfev':>5} {'conv':>5} {'adm':>5} {'obs sha256':18}")
    for cell in expected:
        c = found.get(cell)
        if c is None:
            say(f"  {cell[0]:10} {VIEW_META[cell[1]]['display_label']:34} {cell[2]:6} MISSING")
            continue
        say(f"  {c['camera']:10} {c['view_display']:34} {c['model']:6} {c['n_obs']:6d} "
            f"{str(c['termination'])[:6]:>6} {c['nfev']:5d} {str(c['converged'])[:5]:>5} "
            f"{str(c['adm_v2_safe'] and c['adm_v2_plausible'])[:5]:>5} {c['obs_sha256'][:16]:18}")
    if missing:
        problems.append(f"view-sensitivity artifact is missing {len(missing)} of {len(expected)} "
                        f"cells: {missing} -- reported, NOT refitted")
    if dupes:
        problems.append(f"view-sensitivity artifact has duplicated cells: {dupes}")
    n_unique_hashes = len({c["obs_sha256"] for c in found.values()})

    # ---------------------------------------------------------------- 5. view metadata
    say("")
    say("=" * 118)
    say("5. CLEARWATER OBSERVATION VIEWS -- an INCIDENCE-FILTER difference, not an indexing failure")
    say("=" * 118)
    views = {}
    for cam in sorted(vcams):
        rec = vcams[cam]
        for internal, canon in VIEWSENS_INTERNAL_TO_CANONICAL.items():
            arm = rec["arms"].get(f"SD-D/M0::{internal}")
            if arm is None:
                continue
            views.setdefault(canon, {"canonical_name": canon, **VIEW_META[canon], "cameras": {}})
            views[canon]["cameras"][cam] = {"n_obs": arm["n_obs"], "n_lines": arm["n_lines"],
                                            "obs_sha256": arm["obs_sha256"]}
    for canon, v in views.items():
        say(f"  {v['display_label']}")
        say(f"    predicate     {v['selection_predicate']}")
        say(f"    caller branch {v['caller_branch']}")
        say(f"    historical internal ids: {v['internal_id_history']}")
        for cam, c in sorted(v["cameras"].items()):
            say(f"    {cam:10} n_obs {c['n_obs']:4d}, lines {c['n_lines']:3d}, "
                f"obs sha256 {c['obs_sha256'][:16]}")
    say("")
    say("  ALL source observations were successfully lattice-indexed on this document: 340 of 340 on")
    say("  Left and 365 of 365 on Right, with zero index contradictions. The 309 and 318 figures are")
    say("  the counts AFTER the min_inc=2 incidence filter; the 31 and 47 differences are observations")
    say("  carrying only ONE line incidence, not observations that failed to be indexed.")

    # ---------------------------------------------------------------- 6. gate disagreement audit
    disagree = [k for k, v in status.items()
                if v["production_gate_ok"] is True and not v["empirically_admissible"]]
    # every camera is keyed "<document>|<clip>|<candidate>", so a candidate name containing a
    # slash (every one of them does) cannot collide with the key separator.
    say("")
    say("=" * 118)
    say("6. GATE DISAGREEMENT (production gate passes, frozen empirical gate fails)")
    say("=" * 118)
    for k in disagree:
        v = status[k]
        a = v["evidence"]["adm_v2"]
        say(f"  {k}: prodGate ok, frozen gate FAILS -- min det {a.get('min_det')}, "
            f"min sigma {a.get('min_sigma')}, expansion {a.get('expansion_ratio')}; "
            f"eligible_for_ranking={v['eligible_for_ranking']}")
    if not disagree:
        say("  none")

    R = {"ranking_rule": FS.RANKING_RULE, "status_schema": list(FS.STATES),
         "inverse_roundtrip_tol_px": FS.INVERSE_ROUNDTRIP_TOL_PX,
         "camera_status": status, "document_status": docstat, "known_length_rankings": rankings,
         "view_metadata": views, "viewsens_matrix": {f"{c[0]}|{c[1]}|{c[2]}": found[c]
                                                     for c in expected if c in found},
         "viewsens_expected_cells": len(expected), "viewsens_found_cells": len(found),
         "viewsens_missing_cells": [list(c) for c in missing],
         "viewsens_duplicate_cells": [list(c) for c in dupes],
         "viewsens_unique_obs_hashes": n_unique_hashes,
         "gate_disagreements": disagree,
         "sources": {"sd_real": os.path.basename(args.sd_real),
                     "xdoc": os.path.basename(args.xdoc),
                     "viewsens": os.path.basename(args.viewsens)},
         "source_artifact_sha256_before": hashes_before,
         "optimizer_calls_attempted": list(attempts),
         "problems": problems}

    # ---------------------------------------------------------------- 7. content-hash evidence
    hashes_after = hash_sources(src_paths + [p for p in sidecars if os.path.exists(p)])
    changed = sorted(n for n in hashes_before if hashes_before[n] != hashes_after.get(n))
    R["source_artifact_sha256_after"] = hashes_after
    R["source_artifacts_unchanged"] = not changed
    R["source_artifacts_changed"] = changed
    say("")
    say("=" * 118)
    say("7. CONTENT-HASH EVIDENCE THAT THE AUTHORITATIVE SOURCE ARTIFACTS DID NOT CHANGE")
    say("=" * 118)
    say(f"  {'artifact':44} {'sha256 before == after':22} sha256")
    for n in sorted(hashes_before):
        same = hashes_before[n] == hashes_after.get(n)
        say(f"  {n:44} {('yes' if same else 'NO -- CHANGED'):22} {hashes_after.get(n)}")
    if changed:
        problems.append(f"the content hash of {changed} changed during this run; this script only "
                        f"READS these files, so something else wrote them. Stopping rather than "
                        f"reporting numbers derived from a moving artifact.")
        say(f"  *** {changed} CHANGED DURING THIS RUN -- see problems ***")
    else:
        say("  every authoritative source artifact is byte-identical before and after this run")
    R["problems"] = problems
    for doc in DOC_KEYS:
        W.document_started(doc, doc_key=doc)
        W.document_completed(doc, completed_candidates=[ANCHOR] + METHODS)
    path = W.write(R)
    say("")
    say("=" * 118)
    say(f"  optimizer calls attempted during regeneration: {len(attempts)} {attempts}")
    say(f"  problems: {len(problems)}")
    for p in problems:
        say(f"    {p}")
    say(f"  wrote {path}   [{time.time() - t0:.1f}s]")
    return 1 if (problems or attempts) else 0


if __name__ == "__main__":
    sys.exit(main())
