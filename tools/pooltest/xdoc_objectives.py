#!/usr/bin/env python3
"""Part 2: PD-D and the proposed modern SD-D line fallback across the known-length documents.

Three documents spanning distortion regimes, the mild-distortion pool test first because it is the
negative control that previously showed freely fitted eta to be HARMFUL. Every candidate goes through
the explicit-injection downstream path in downstream.py -- no monkeypatch, no stale stored geometry.

Candidates per camera: the stored anchor, B/M0, B/M1 (legacy line ODR), PD-D/M0, PD-D/M1 (exact
projective lattice), SD-D/M0, SD-D/M1 (unique-observation block Sampson, the proposed non-lattice
fallback, which deliberately ignores lattice projectivity).

TWO INTEGRITY FIXES, 2026-07-29, after independent audit.

  Scope-safe atomic output. This script used to write `analysis-output/xdoc_objectives.json`
  unconditionally, so `--docs pool` overwrote the complete three-document artifact with a pool-only one
  that carried no sign of being partial. Output now goes through `artifacts.ArtifactWriter`: the
  filename carries the document scope (`xdoc_objectives_full.json` versus
  `xdoc_objectives_pool.json`), the write is atomic, and `complete` reflects whether every requested
  document and candidate actually finished.

  Invalid fits fail closed. Capped SD-D fits used to appear in the headline MAE table, the tails, the
  strata and the paired contrasts, formatted like converged results. `fitvalidity` now decides what may
  be reported; invalid candidates keep their full diagnostic record but are excluded from every
  reported number, from `--best` selection and from contrasts, and their table cells read `invalid_fit`.
  `--allow-invalid` re-enables them for exploration only, and says so loudly on every table.

Writes analysis-output/xdoc_objectives_<scope>.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

import numpy as np

import artifacts
import fitstatus as FS
import fitvalidity as FV
import harness_import
import sdprov as SP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
POOL = os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                        "2012-01-31_PoolTest_2026_Reanalysis.vsd")
CALXML = os.path.join(CH, "Papers/2010 3D Video Methods/2012 Pool Test - 2016 Cal%s.xml")
SD_MAX_NFEV = 1200            # ~30 s at the measured 40 ms/nfev; the per-fit ceiling is 60 s
SD_SOURCE_MAX_NFEV = 300      # sd_fast.MAX_NFEV: the cap that applied to a REUSED SD-D fit
SD_WALL_LIMIT = 60.0


L = harness_import.load          # ONE shared instance per module; see harness_import.py

DS = L("downstream")
LT = L("lattice")
OB = L("objectives")
kl = L("knownlength")
st = L("stage2")
nd = L("nodes")

# Distortion regime is characterised EMPIRICALLY below, because no document stores lens or focal
# metadata: ZVSVIDEOCLIP has only clipName/fileName/syncOffset/windowFrame. The "13 mm" label on
# 2015-06-22-1 exists only in harness script comments and is not verifiable from the file.
DOCS = [
    {"key": "pool", "label": "2012 pool test (Sony Handycam)", "vsd": POOL,
     "types": kl.POOL_CONVENTIONAL_TYPES, "unit_mm": 1000.0, "calxml": True},
    {"key": "8mm", "label": "2015-09-04-1 Clearwater (Rokinon 8 mm fisheye)",
     "vsd": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"), "types": None, "unit_mm": 1.0,
     "calxml": False},
    {"key": "mid", "label": "2015-06-22-1 Clearwater (label '13 mm', UNVERIFIED)",
     "vsd": os.path.join(DM, "2015-06-22-1 Clearwater.vsd"), "types": None, "unit_mm": 1.0,
     "calxml": False},
]
OBJMODELS = [("B", "M0"), ("B", "M1"), ("PD-D", "M0"), ("PD-D", "M1"), ("SD-D", "M0"),
             ("SD-D", "M1")]
CONTRASTS = [("B/M1", "B/M0"), ("PD-D/M0", "B/M0"), ("PD-D/M1", "PD-D/M0"), ("PD-D/M1", "B/M1"),
             ("SD-D/M0", "B/M0"), ("SD-D/M1", "SD-D/M0"), ("SD-D/M1", "PD-D/M1")]


def stats(err):
    e = np.abs(np.asarray(err, float)); s = np.asarray(err, float)
    if e.size == 0:
        return {"n": 0}
    return {"n": int(e.size), "mae": float(e.mean()), "rmse": float(math.sqrt((s ** 2).mean())),
            "med": float(np.median(e)), "bias": float(s.mean()),
            "p90": float(np.percentile(e, 90)), "p95": float(np.percentile(e, 95)),
            "max": float(e.max())}


def cluster_effect(rows_a, rows_b, keyf, groupf):
    """Paired change in |error|, summarised at the CLUSTER level (timecode), not per measurement."""
    a = {keyf(r): r for r in rows_a}
    b = {keyf(r): r for r in rows_b}
    keys = sorted(set(a) & set(b), key=str)
    if not keys:
        return {}
    per = defaultdict(list)
    for k in keys:
        per[groupf(a[k])].append(abs(a[k]["err"]) - abs(b[k]["err"]))
    cl = np.array([np.mean(v) for v in per.values()])
    d = np.array([abs(a[k]["err"]) - abs(b[k]["err"]) for k in keys])
    se = float(cl.std(ddof=1) / math.sqrt(len(cl))) if len(cl) > 1 else float("nan")
    return {"n_measurements": len(keys), "n_clusters": len(cl),
            "mean_d_abs_err": float(d.mean()), "median_d_abs_err": float(np.median(d)),
            "cluster_mean": float(cl.mean()), "cluster_se": se,
            "cluster_ci95": [float(cl.mean() - 1.96 * se), float(cl.mean() + 1.96 * se)]
            if len(cl) > 1 else None,
            "clusters_improved": int((cl < 0).sum()), "improved": int((d < 0).sum())}


# =============================================================== lattice validation


def lattice_report(say, caps, clip):
    rows = []
    for C in caps:
        N = C.notes
        ok = C.indexed()
        span = [0, 0]
        if ok.any():
            r = C.rc[ok, 0]; c = C.rc[ok, 1]
            span = [int(r.max() - r.min() + 1), int(c.max() - c.min() + 1)]
        xy = C.xy[ok] if ok.any() else C.xy
        rows.append({
            "clip": clip, "timecode": C.timecode, "lines": N["n_lines"],
            "stored_incidences": N["stored_incidences"],
            "unique_observations": N["unique_observations"],
            "components": N["n_components"], "largest_component": N["largest_component"],
            "reliably_indexed": N["reliably_indexed"],
            "contradictions": N["index_contradictions"],
            "ambiguous_gaps_dropped": N["dropped_nonunit_edges"],
            "unit_step_edges": N["unit_step_edges"],
            "coverage_largest": (N["largest_component"] / max(N["unique_observations"], 1)),
            "index_span": span,
            "screen_span_px": [float(xy[:, 0].max() - xy[:, 0].min()),
                              float(xy[:, 1].max() - xy[:, 1].min())] if len(xy) else [0.0, 0.0]})
        say(f"        {C.timecode!r}: {N['n_lines']} lines, {N['stored_incidences']} stored "
            f"incidences -> {N['unique_observations']} unique; components {N['n_components']} "
            f"(largest {N['largest_component']}, {100 * rows[-1]['coverage_largest']:.1f}%)")
        say(f"          indexed {N['reliably_indexed']}, contradictions "
            f"{N['index_contradictions']}, ambiguous gaps dropped "
            f"{N['dropped_nonunit_edges']} of {N['dropped_nonunit_edges'] + N['unit_step_edges']}; "
            f"index span {span[0]}x{span[1]}, screen span "
            f"{rows[-1]['screen_span_px'][0]:.0f}x{rows[-1]['screen_span_px'][1]:.0f} px")
    return rows


# =============================================================== fits


def _stamp_embedded(prov, artifact_sha256):
    """Bind an embedded provenance record to the bytes it was read from, by containment.

    A producer cannot write the hash of the file it is writing into that file, so an embedded record
    normally omits `artifact_sha256` and the loader supplies the hash it computed. A record that DOES
    declare one is left alone, so a copied-in record naming a different artifact still fails verification.
    """
    if not isinstance(prov, dict):
        return prov
    out = dict(prov)
    if not out.get("artifact_sha256"):
        out["artifact_sha256"] = artifact_sha256
        out["artifact_binding"] = "embedded (contained in the hashed bytes)"
    return out


def load_sd_source(path, sidecar_paths=None):
    """Index an `sd_real`-shaped artifact by (doc_sha256, clip) for SD-D map REUSE, not refitting.

    WHY THIS EXISTS, 2026-07-29. This script used to refit SD-D itself, through
    `objectives.fit(..., "SD", ...)` with ftol = xtol = gtol = 1e-14 and a 1200-evaluation cap. Those
    tolerances are unreachable on this objective by construction (see the `sd_fast` module docstring:
    the relative cost change plateaus near 1e-9 per iteration), so that path ALWAYS ran to the cap and
    was ALWAYS ruled a non-convergent, therefore invalid, fit -- which is why SD-D never once appeared in
    a known-length table. Meanwhile `sd_real.py` had already produced converged SD-D maps for the same
    cameras with the same estimator, using `sd_fast` (analytic sparse Jacobian, calibrated tolerances,
    multistart). Refitting was never mathematically necessary: `sd_fast`'s residual is verified
    BIT-IDENTICAL to `objectives.resid_SD` at a common parameter point (test_sd_fast.py), and the
    known-length path consumes only a 14-parameter map. So the map is loaded instead of re-derived.

    FAIL-CLOSED, revised 2026-07-29 (revision 2). The first version of this loader returned `None` for a
    record it could not verify, and the caller then quietly refit -- so an incomplete or mismatched
    artifact produced a table with MIXED provenance and no marker. That is now impossible: when
    `--sd-from` is given, `preflight_sd_reuse` demands a verified record for EVERY requested
    document/camera/model before any optimizer is constructed, collects every failure into one
    diagnostic, and aborts with a non-zero exit. Refitting what is missing is still a legitimate
    workflow but requires the separate, conspicuous `--sd-refit-missing`, which is rejected unless
    `--sd-from` is also given.

    EXACT PROVENANCE, revision 3 (2026-07-29). Revision 2's identity check was too weak: it inferred the
    observation view from `n_obs`, accepted missing frame and coordinate-convention metadata, accepted
    EITHER recognized view rather than the one the caller was about to use, identified the producing
    implementation only by the manifest's analysis NAME, and never bound a reused map to the bytes of the
    artifact it came from. `sdprov` now defines the full contract and this loader supplies its inputs:

      * `artifact_sha256` is computed HERE from the file's bytes, so every record is tied to exactly the
        artifact that was read -- no modification time is consulted anywhere;
      * a producer that embeds an `sdprov` record per fit (`fits[name]["provenance"]`) is used directly;
      * an established artifact that predates the contract -- `sd_real_full.json` does, recording no
        view, no frame and no coordinate convention -- is NOT rewritten. Its provenance comes from a
        SIDECAR manifest keyed by the artifact's content hash, loaded by `sdprov.load_sidecars`.
    """
    with open(path) as fh:
        art = json.load(fh)
    man, res = art.get("manifest", {}), art.get("results", {})
    artifact_sha256 = SP.file_sha256(path)
    idx, dup = {}, {}
    for cid, rec in res.get("cameras", {}).items():
        for name in ("SD-D/M0", "SD-D/M1"):
            f = rec.get("fits", {}).get(name)
            if f is None:
                continue
            key = (rec.get("doc_sha256"), rec.get("clip"), name)
            entry = {
                "theta14": f.get("theta14"), "loss": f.get("loss"), "status": f.get("status"),
                "nfev": f.get("nfev"), "eta": f.get("eta"), "completed": f.get("completed"),
                "termination": f.get("termination"), "init": f.get("init"),
                "adm_v2": f.get("adm_v2"), "inverse": f.get("inverse"),
                "source_camera_id": cid,
                # Counts as the SOURCE recorded them. Kept for the diagnostic only: a count NEVER
                # establishes which observation view a map was fitted on (revision 2's central defect).
                "n_obs": rec.get("n_obs"), "n_lines": rec.get("n_lines"),
                "n_captures": rec.get("n_captures"),
                "identity": rec.get("identity"),
                # An `sdprov` record embedded by a contract-aware producer, if any. Embedded provenance
                # cannot state the hash of the file containing it, so the binding to the bytes is by
                # CONTAINMENT: the loader stamps the hash it computed. A record that declares a
                # different artifact hash is claiming to describe other bytes and still fails.
                "embedded_provenance": _stamp_embedded(f.get("provenance") or rec.get("provenance"),
                                                       artifact_sha256),
            }
            if key in idx:
                dup.setdefault(key, [idx[key]["source_camera_id"]]).append(cid)
            idx[key] = entry
    paths = list(sidecar_paths) if sidecar_paths else SP.default_sidecar_paths(path)
    present = [p for p in paths if os.path.exists(p)]
    sidecars, sidecar_problems = SP.load_sidecars(present)
    return {"path": path, "artifact_sha256": artifact_sha256,
            "analysis": man.get("analysis"), "script": man.get("script"),
            "source_sha256": man.get("source_file_sha256", {}), "git": man.get("git"),
            "started": man.get("started"), "index": idx, "duplicates": dup,
            "sidecars": sidecars, "sidecar_problems": sidecar_problems,
            "sidecar_paths": present, "sidecar_paths_requested": paths,
            "declared_solver": man.get("objective_versions", {}).get("SD-D"),
            "solver": "sd_fast.solve (analytic sparse Jacobian, ftol=xtol=gtol=1e-8, max_nfev=300, "
                      "rescue at 600), multistart with best-by-objective selection"}


# The authoritative observation-view registry -- canonical ids, selector ids, exact kwargs and predicate
# strings -- is `sdprov.VIEWS`. It is NOT restated here: revision 2 kept a local `SD_VIEWS` dict of
# predicate strings that could drift away from the kwargs actually used to build a Dataset. Both views
# contain the SAME successfully indexed observations on an eligible document: all 340 Left and 365 Right
# source observations on 2015-06-22-1 were lattice-indexed, and the 309/318 subsets arise from the
# `min_inc=2` incidence filter, not from an indexing failure. See CORRECTION_2026-07-29_SD_PATHS.md
# sections 4 and 7.


def _artifact_status(rec, candidate, camera):
    """The five explicit states recomputed from the ARTIFACT'S OWN stored evidence, no map evaluated.

    This is the independent yardstick a declared status block is checked against, so a sidecar cannot
    assert that a map converged, inverts and passes the frozen gate when the artifact's own numbers say
    otherwise. The cap is the SOURCE fit's (`sd_fast`'s 300), never this script's 1200.
    """
    inv = rec.get("inverse") or {}
    return FS.camera_status(
        candidate, camera,
        optimizer={"status": rec.get("status"), "nfev": rec.get("nfev"),
                   "max_nfev": SD_SOURCE_MAX_NFEV, "termination": rec.get("termination"),
                   "loss": rec.get("loss")},
        adm_v2=rec.get("adm_v2"),
        inverse={"shipped_failures": inv.get("shipped_failures"),
                 "max_roundtrip_px": inv.get("max_roundtrip_px")},
        theta14=rec.get("theta14"))


def verify_sd_records(src, requested, refit_missing=False):
    """Verify every requested SD-D map against an artifact. Returns (usable, failures, refit).

    `requested` is a list of `sdprov.reuse_request` dicts. Each one names the EXACT expected observation
    view and carries `expected`, an `sdprov.view_identity` computed from inputs reconstructed
    independently from the documents -- counts, line count, frame, coordinate convention, model
    parameterization and the canonical point-set hash. The artifact does not get to choose which view it
    supplied: a valid map for the OTHER recognized view fails, because it is not the map this caller is
    about to use.

    Pure and side-effect free, so the tests exercise it with fixtures and no optimizer exists anywhere
    near it. Every failure is collected; nothing short-circuits, so one run reports all of them.
    `refit_missing` downgrades ABSENT-record failures to a recorded refit permission -- and only those:
    a present-but-mismatched record is always a hard failure, because that is corruption, not a gap.
    """
    usable, failures, refit = {}, [], []
    if src is None:
        return usable, ["no artifact supplied"], refit
    for m in src.get("sidecar_problems") or []:
        failures.append(m)
    for key, cams in (src.get("duplicates") or {}).items():
        failures.append(f"{key[0][:12]}/{key[1]}/{key[2]}: DUPLICATE records in the artifact from "
                        f"camera entries {cams}; refusing to choose between them")
    art_sha = src.get("artifact_sha256")
    if not art_sha:
        failures.append("the artifact's own content hash was not computed, so no record can be bound "
                        "to the bytes that were read")
    for req in requested:
        sha, clip, name, tag = req["doc_sha256"], req["clip"], req["candidate"], req["tag"]
        rec = src["index"].get((sha, clip, name))
        if rec is None:
            near = [k for k in src["index"] if k[2] == name and (k[0] == sha or k[1] == clip)]
            msg = (f"{tag}: NO record for (doc_sha256 {sha[:12]}, clip {clip!r}); "
                   f"artifact has {len(src['index'])} records"
                   + (f", nearest by one field: {near}" if near else ""))
            (refit if refit_missing else failures).append(msg)
            continue
        bad = []
        if not rec.get("completed"):
            bad.append(f"source fit is not marked completed (status {rec.get('status')!r}, "
                       f"termination {rec.get('termination')!r})")
        th = np.asarray(rec.get("theta14") if rec.get("theta14") is not None else [], float).ravel()
        if th.shape != (14,):
            bad.append(f"theta has {th.size} entries, expected 14")
        elif not np.all(np.isfinite(th)):
            bad.append("theta contains a non-finite value")

        # Provenance: embedded if the producer wrote it, otherwise a sidecar keyed by the artifact's
        # exact content hash. There is no third path -- missing provenance is never accepted.
        prov, prov_from = rec.get("embedded_provenance"), "embedded"
        if prov is None:
            prov = (src.get("sidecars") or {}).get((art_sha, sha, clip, name))
            prov_from = "sidecar"
        if prov is None:
            n_sc = len(src.get("sidecars") or {})
            bad.append(f"NO embedded provenance and no verified sidecar entry for artifact "
                       f"{(art_sha or '?')[:12]} (sidecars loaded: {n_sc} entr{'y' if n_sc == 1 else 'ies'}"
                       f" from {[os.path.basename(p) for p in src.get('sidecar_paths') or []]}); "
                       f"explicit reuse fails closed")
        else:
            bad += SP.verify_record(
                prov, dict(req, theta14=rec.get("theta14")), art_sha,
                manifest_source_hashes=src.get("source_sha256"),
                recomputed_status=(_artifact_status(rec, name, f"{req['doc_key']}/{clip}")
                                   if th.shape == (14,) else None))
        if bad:
            failures.append(f"{tag}: " + "; ".join(bad))
        else:
            rec = dict(rec)
            rec["view_verified"] = req["expected_view"]
            rec["provenance_from"] = prov_from
            rec["provenance"] = prov
            rec["artifact_sha256"] = art_sha
            rec["pointset_sha256"] = req["expected"]["pointset_sha256"]
            rec["producer_code_sha256"] = (prov.get("producer_code_fingerprint")
                                           or {}).get("combined_sha256")
            rec["producer_revision"] = prov.get("producer_revision")
            usable[(sha, clip, name)] = rec
    return usable, failures, refit


def preflight_sd_reuse(say, src, requested, refit_missing=False):
    """Abort BEFORE any optimizer exists if explicit artifact reuse cannot be fully satisfied."""
    usable, failures, refit = verify_sd_records(src, requested, refit_missing=refit_missing)
    say("")
    say(f"  SD-D ARTIFACT REUSE PREFLIGHT: {len(requested)} requested map(s) from {src['path']}")
    say(f"    artifact sha256 {src.get('artifact_sha256')}")
    say(f"    provenance contract {SP.SCHEMA_VERSION}; point-set hash {SP.POINTSET_HASH_VERSION}; "
        f"view selector {SP.VIEW_SELECTOR_VERSION}; code fingerprint {SP.CODE_FINGERPRINT_VERSION}")
    for p in src.get("sidecar_paths") or []:
        say(f"    sidecar {os.path.basename(p)} sha256 {SP.file_sha256(p)}")
    for k in sorted(usable, key=str):
        r = usable[k]
        say(f"    ok    {k[1]:14} {k[2]:8} view {r.get('view_verified')} "
            f"(requested explicitly), n_obs {r.get('n_obs')}, points "
            f"{(r.get('pointset_sha256') or '')[:16]}, code "
            f"{(r.get('producer_code_sha256') or '')[:16]}, provenance {r.get('provenance_from')}, "
            f"term {r.get('termination')}, nfev {r.get('nfev')}, source {r.get('source_camera_id')}")
    for m in refit:
        say(f"    REFIT {m}   [permitted only because --sd-refit-missing was given]")
    for m in failures:
        say(f"    FAIL  {m}")
    if failures:
        say("")
        say(f"  ABORTING: {len(failures)} SD-D map(s) could not be verified. Explicit --sd-from reuse is "
            f"fail-closed: no optimizer has been constructed and nothing has been refitted. Fix the "
            f"artifact or its sidecar, or pass --sd-refit-missing to refit ABSENT maps only (mismatched "
            f"or malformed records can never be refit around).")
        raise SystemExit(3)
    say(f"    all {len(usable)} requested map(s) verified against the exact requested view, point set, "
        f"frame, coordinate convention and producer code fingerprint"
        + (f"; {len(refit)} absent map(s) will be refit because --sd-refit-missing was given" if refit
           else "; nothing will be refitted"))
    return usable, refit


def sd_from_source(src, doc_sha256, clip, name):
    """The verified SD-D record for one camera and model, or None if the artifact has none.

    By the time this is reached in explicit reuse mode, `preflight_sd_reuse` has already guaranteed that
    every requested record exists and verifies, so a `None` here can only mean the operator passed
    `--sd-refit-missing` for a deliberately absent map.
    """
    if src is None:
        return None
    rec = src["index"].get((doc_sha256, clip, name))
    if rec is None:
        return None
    if not rec.get("completed"):
        raise RuntimeError(f"{name} in {src['path']} is not marked completed; refusing to reuse it")
    th = np.asarray(rec["theta14"], float)
    if th.shape != (14,) or not np.all(np.isfinite(th)):
        raise RuntimeError(f"{name} in {src['path']} has a non-finite or misshaped theta")
    return rec


def fit_candidates(say, D, Dline, caps, clip, pd_ok, sd_src=None, doc_sha256=None):
    """B, PD-D and SD-D at M0 and M1. Returns {name: theta14}, diagnostics, and FitValidity records.

    `pd_ok` says whether the lattice validated. When it did not, PD-D is NOT fitted -- forcing a
    projective lattice onto data that has no consistent index set would manufacture a number rather
    than measure one -- and SD-D falls back to `Dline`, the unique-observation set that needs line
    incidences only. Where the lattice DOES validate, SD-D deliberately uses the same indexed subset as
    PD-D so the two are compared on identical observations.

    `sd_src` (from `--sd-from`) makes SD-D EVALUATED rather than refitted: see `load_sd_source`. The
    default remains a local refit, so no historical behaviour changes unless the flag is passed.
    """
    out, diag = {}, {}
    Dsd = D if pd_ok else Dline
    # B first: it supplies the initialization every other objective uses. B reads the STORED line
    # records directly, so it is unaffected by which selection the dataset carries.
    for model in ("M0", "M1"):
        t0 = time.time()
        r = OB.fit(Dsd, "B", model, warm=False, max_nfev=3000)
        out[f"B/{model}"] = np.array(r["theta14"], float)
        diag[f"B/{model}"] = {"loss": r["loss"], "nfev": r["nfev"], "status": r["status"],
                              "eta": r["eta"], "wall_s": time.time() - t0,
                              "objective_note": "loss is B's own line-ODR cost, not comparable "
                                                "across objectives"}
    for model in ("M0", "M1"):
        thB = out[f"B/{model}"]
        fr = OB.MODELS[model]
        if pd_ok:
            t0 = time.time()
            ev = OB.PDExact(D, model)
            res, w = ev.fit(ev.init_dlt(thB))
            th = ev.theta(res.x)
            out[f"PD-D/{model}"] = th
            cond = ev.projected_conditioning(res.x)
            diag[f"PD-D/{model}"] = {"loss": float(2 * res.cost), "nfev": int(res.nfev),
                                     "status": int(res.status), "eta": float(th[13]), "wall_s": w,
                                     "optimality": float(res.optimality),
                                     "projected_condition": cond["condition"],
                                     "inverse_failures": ev.C["inverse_failures"]}
        # SD-D. Either the established converged map is EVALUATED (--sd-from) or it is refit locally.
        rec = sd_from_source(sd_src, doc_sha256, clip, f"SD-D/{model}")
        if rec is not None:
            thS = np.asarray(rec["theta14"], float)
            out[f"SD-D/{model}"] = thS
            diag[f"SD-D/{model}"] = {
                "loss": rec["loss"], "nfev": rec["nfev"], "status": rec["status"],
                "eta": rec["eta"], "wall_s": 0.0, "hit_nfev_cap": False, "over_wall_limit": False,
                "min_block_eig": None,
                "objective_note": "loss is SD-D's own Sampson cost from the source fit, not "
                                  "comparable across objectives",
                "source": {"artifact": sd_src["path"], "analysis": sd_src["analysis"],
                           "solver": sd_src["solver"], "init": rec["init"],
                           "termination": rec["termination"],
                           "source_camera_id": rec["source_camera_id"],
                           "adm_v2_safe": (rec.get("adm_v2") or {}).get("safe"),
                           "source_inverse": rec.get("inverse")},
                "evaluated_not_refitted": True}
            say(f"        SD-D/{model} EVALUATED from {os.path.basename(sd_src['path'])} "
                f"({rec['source_camera_id']}, init {rec['init']}, term {rec['termination']}, "
                f"nfev {rec['nfev']}) -- not refitted here")
        else:
            # Capped and timed; if it overruns, say so.
            t0 = time.time()
            rS = OB.fit(Dsd, "SD", model, x0_model=thB[fr] / OB.SCALE14[fr], warm=False,
                        max_nfev=SD_MAX_NFEV)
            w2 = time.time() - t0
            thS = np.array(rS["theta14"], float)
            out[f"SD-D/{model}"] = thS
            diag[f"SD-D/{model}"] = {"loss": rS["loss"], "nfev": rS["nfev"], "status": rS["status"],
                                     "eta": rS["eta"], "wall_s": w2,
                                     "hit_nfev_cap": bool(rS["nfev"] >= SD_MAX_NFEV),
                                     "over_wall_limit": bool(w2 > SD_WALL_LIMIT),
                                     "min_block_eig": rS["report"].get("min_block_eig"),
                                     "evaluated_not_refitted": False}
            if w2 > SD_WALL_LIMIT:
                say(f"        *** SD-D/{model} took {w2:.1f}s, over the {SD_WALL_LIMIT:.0f}s per-fit "
                    f"limit; reported as-is, not re-optimized ***")
    # nesting check on the fitted objectives that support it
    for obj in (("PD-D", "SD-D") if pd_ok else ("SD-D",)):
        l0 = diag[f"{obj}/M0"]["loss"]; l1 = diag[f"{obj}/M1"]["loss"]
        diag[f"{obj}/M1"]["nests_under_M0"] = bool(l1 <= l0 + 1e-6 * max(abs(l0), 1.0))
    if not pd_ok:
        say(f"        PD-D NOT FITTED: the lattice did not validate, so there is no consistent index "
            f"set for a projective homography. SD-D used the {Dsd.n}-observation unique-point set "
            f"(require_indexed=False, min_inc=1) instead of the empty indexed subset.")

    # ---- validity, decided here from the optimizer's own termination facts -------------------
    # Admissibility and the inverse audit are added later in main(), where the calibration node
    # points are in scope. Everything the optimizer knows is recorded now.
    val = {}
    for k, d in diag.items():
        cap = SD_MAX_NFEV if k.startswith("SD-D/") else 3000 if k.startswith("B/") else None
        if d.get("evaluated_not_refitted"):
            # The cap that applied is the SOURCE fit's, not this script's; `hit_nfev_cap` is already
            # recorded as False from the source record, so validity is decided on the source's facts.
            cap = SD_SOURCE_MAX_NFEV
        val[k] = FV.from_least_squares(k, d, max_nfev=cap, theta14=out[k])
    for obj in ("PD-D",):
        for model in ("M0", "M1"):
            if not pd_ok:
                val[f"{obj}/{model}"] = FV.not_fitted(
                    f"{obj}/{model}", "lattice did not validate; no consistent projective index set")

    say(f"        {'fit':10} {'ownLoss':>14} {'nfev':>6} {'stat':>5} {'eta':>11} {'wall s':>8}  "
        f"{'valid':>6}  note")
    for k in [k for k in ["B/M0", "B/M1", "PD-D/M0", "PD-D/M1", "SD-D/M0", "SD-D/M1"] if k in diag]:
        d = diag[k]
        v = val[k]
        note = "; ".join(v.failures())
        say(f"        {k:10} {d['loss']:14.5f} {d['nfev']:6d} {d['status']:5d} {d['eta']:+11.7f} "
            f"{d['wall_s']:8.2f}  {'ok' if v.valid else 'INVALID':>6}  {note}")
    return out, diag, val


# =============================================================== line-record audit


def line_audit(say, caps, D):
    """Exactly the defects the fallback must disclose rather than silently absorb."""
    frag = 0
    jumps = []
    dup = D.info["merged_duplicate_line_records"]
    fams = defaultdict(int)
    for ci, C in enumerate(caps):
        for li, ln in enumerate(C.lines):
            mem = ln["members"]
            fams[ln["family"]] += 1
            if len(mem) < 2:
                continue
            P = C.xy[mem]
            g = np.hypot(*np.diff(P, axis=0).T)
            med = float(np.median(g))
            big = g[g > 5.0 * max(med, 1e-9)]
            if len(big):
                jumps.append((ci, li, float(big.max()), med))
        frag += sum(1 for ln in C.lines if len(ln["members"]) < 5)
    say(f"        stored line records: {sum(len(C.lines) for C in caps)}; short/fragmented "
        f"(<5 points) {frag}; duplicate records merged {dup}")
    say(f"        family balance (directional coverage): {dict(fams)}")
    if jumps:
        say(f"        large within-line jumps (>5x the line's median gap): {len(jumps)}; worst "
            f"{max(j[2] for j in jumps):.0f} px against a median gap of "
            f"{[j[3] for j in jumps][int(np.argmax([j[2] for j in jumps]))]:.0f} px")
        say(f"          these are candidate IMPLAUSIBLE JOINS. SD-D cannot repair a false line "
            f"membership; it can only be told about it.")
    else:
        say(f"        large within-line jumps: none")
    only_one = len(fams) < 2
    if only_one:
        say(f"        *** only one line orientation present: the distortion centre is weakly "
            f"identified transverse to it ***")
    return {"n_line_records": int(sum(len(C.lines) for C in caps)), "fragmented_lt5": int(frag),
            "duplicates_merged": int(dup), "family_counts": {str(k): v for k, v in fams.items()},
            "large_jumps": [{"capture": j[0], "line": j[1], "jump_px": j[2], "median_gap_px": j[3]}
                            for j in jumps],
            "single_orientation": bool(only_one)}


# =============================================================== downstream


def parse_calxml(tag):
    s = open(CALXML % tag, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'<videoClip name="([^"]+)">(.*?)</videoClip>', s, re.S):
        clip, blk = m.group(1), m.group(2)
        d = {}
        for nm, t in (("front", "frontCalibrationPoints"), ("back", "backCalibrationPoints")):
            seg = re.search("<" + t + ">(.*?)</" + t + ">", blk, re.S).group(1)
            d[nm] = [(float(a["x"]), float(a["y"]), float(a["worldHcoord"]), float(a["worldVcoord"]))
                     for a in (dict(re.findall(r'(\w+)="([^"]*)"', mm.group(1)))
                               for mm in re.finditer(r"<screenpoint ([^>]*)></screenpoint>", seg))]
        out[clip] = d
    return out


def run_downstream(say, cals, maps, conv, clicks, unit_mm, label, validities=None,
                   allow_invalid=False):
    """Rebuild every candidate and measure. Returns {name: rows}, {name: calib diagnostics}.

    A candidate whose fit is invalid on ANY camera is NOT reconstructed: a stereo measurement uses both
    cameras, so one unconverged camera makes the triangulated point meaningless. Its calibration
    diagnostics are still produced and kept, because those are the evidence for the failure.
    """
    rows, cdiag = {}, {}
    clips = sorted(cals)
    for name, per in maps.items():
        cams = {}
        for clip in clips:
            # per[clip] is already bound to clips[clip]'s camera; build_calibration re-verifies.
            cams[clip] = DS.build_calibration(cals[clip], per[clip])
        cdiag[name] = {clip: DS.node_residuals(cals[clip], cams[clip])
                       for clip in clips}
        for clip in sorted(cals):
            cdiag[name][clip]["camPLD"] = cams[clip]["camPLD"]
            cdiag[name][clip]["cam"] = list(cams[clip]["cam"])
            ad = LT.admissible(per[clip].theta14,
                               np.array([[x, y] for x, y, _, _ in cals[clip]["front"]
                                         + cals[clip]["back"]], float))
            cdiag[name][clip]["admissible"] = bool(ad["ok"])
            cdiag[name][clip]["min_det_frame"] = ad["min_det_full_frame"]
            cdiag[name][clip]["identity"] = cams[clip]["identity"].to_dict()
        # Fail closed: an invalid candidate contributes diagnostics but no measurements.
        if validities is not None and name != "stored":
            bad = FV.invalid_reasons(validities, name, clips)
            if bad and not allow_invalid:
                say(f"        {name:10} EXCLUDED from measurements -- invalid fit: {bad}")
                cdiag[name]["_excluded_invalid"] = bad
                continue
            if bad and allow_invalid:
                say(f"        {name:10} *** INVALID FIT INCLUDED because --allow-invalid was passed; "
                    f"NOT a scientific result: {bad} ***")
        X = {}
        need = sorted({pk for r in conv for pk in r["pks"]})
        for pk in need:
            obs = DS.observations(pk, cams, clicks)
            if len(obs) < 2:
                continue
            X[pk] = DS.triangulate_lm(obs)["X"]
        rr = []
        for r in conv:
            a, b = r["pks"]
            if a not in X or b not in X:
                continue
            d = float(np.linalg.norm(X[a] - X[b])) * unit_mm
            obsa = DS.observations(a, cams, clicks)
            da = DS.point_diagnostics(obsa, X[a])
            obsb = DS.observations(b, cams, clicks)
            dbg = DS.point_diagnostics(obsb, X[b])
            rr.append({"event": r["event"], "obj": r["obj"], "tc": r["tc"], "true": r["true"],
                       "meas": d, "err": d - r["true"],
                       "pct": 100.0 * (d - r["true"]) / r["true"],
                       "radius": max(da["radius"], dbg["radius"]),
                       "edge": min(da["edge"], dbg["edge"]),
                       "camdist": 0.5 * (da["camdist"] + dbg["camdist"]) * unit_mm})
        rows[name] = rr
    return rows, cdiag


def report_known_length(say, rows, cdiag, clips, label, R, tag, validities=None,
                        allow_invalid=False):
    """The headline table. Invalid candidates occupy a row but never a number.

    Every candidate that was attempted is listed, so nothing disappears silently; an invalid one shows
    `invalid_fit` in each metric column and its reason underneath. Rankings, tails, strata and
    contrasts are computed over valid candidates only.
    """
    order = ["stored"] + [f"{o}/{m}" for o, m in OBJMODELS]

    def ok(name):
        if allow_invalid or validities is None or name == "stored":
            return True
        return FV.candidate_valid(validities, name, clips)

    reportable = [n for n in order if n in rows and ok(n)]
    say(f"\n      KNOWN-LENGTH RESULTS -- {label}")
    if allow_invalid:
        say(f"        *** --allow-invalid IS SET: rows below may come from UNCONVERGED fits and are "
            f"NOT scientific results ***")
    say(f"        {'candidate':10} {'n':>5} {'MAE':>9} {'RMSE':>9} {'med':>9} {'bias':>9} "
        f"{'p90':>9} {'max':>9} {'frontRMS':>9}")
    S, invalid_notes = {}, {}
    for name in order:
        if name not in rows and (validities is None or name == "stored"):
            continue
        if not ok(name):
            v = validities.get(clips[0], {}).get(name)
            invalid_notes[name] = FV.invalid_reasons(validities, name, clips)
            marker = FV.INVALID_DISPLAY
            say(f"        {name:10} {marker:>5} {marker:>9} {marker:>9} {marker:>9} {marker:>9} "
                f"{marker:>9} {marker:>9} {marker:>9}")
            S[name] = {"valid": False, "reason": invalid_notes[name],
                       "excluded_from_ranking": True}
            continue
        if name not in rows:
            continue
        s = stats([r["err"] for r in rows[name]])
        fr = float(np.mean([cdiag[name][c]["front_rms"] for c in clips]))
        S[name] = {**s, "front_rms": fr, "valid": True}
        say(f"        {name:10} {s['n']:5d} {s['mae']:9.4f} {s['rmse']:9.4f} {s['med']:9.4f} "
            f"{s['bias']:+9.4f} {s['p90']:9.4f} {s['max']:9.4f} {fr:9.4f}")
    for name, why in invalid_notes.items():
        say(f"          {name}: excluded from every reported number -- {why}")

    best, bestv = (None, None)
    if validities is not None and not allow_invalid:
        best, bestv = FV.best_by(validities, {k: v for k, v in S.items() if v.get("valid")},
                                 "mae", [n for n in order if n != "stored"], clips)
    if best:
        say(f"        BEST VALID fitted candidate by MAE: {best} at {bestv:.4f} mm "
            f"(invalid candidates are not eligible)")
    R.setdefault("best_valid", {})[tag] = {"candidate": best, "mae": bestv}

    base = rows.get("B/M0") if ok("B/M0") else None
    if base:
        say(f"\n        FIXED-BASELINE UPPER TAILS (worst 10% and 20% under B/M0, same "
            f"measurements for every candidate)")
        srt = sorted(base, key=lambda r: -abs(r["err"]))
        for frac in (0.10, 0.20):
            k = max(1, int(round(frac * len(srt))))
            idx = {r["event"] for r in srt[:k]}
            say(f"          worst {int(frac * 100):3d}% (n {k:4d}): " + "  ".join(
                f"{n} {np.mean([abs(r['err']) for r in rows[n] if r['event'] in idx]):8.3f}"
                for n in reportable))
            R.setdefault("tails", {})[f"{tag} worst {int(frac*100)}%"] = {
                "n": k, "mae": {n: float(np.mean([abs(r["err"]) for r in rows[n]
                                                  if r["event"] in idx]))
                                for n in reportable},
                "excluded_invalid": sorted(invalid_notes)}
    say(f"\n        CLUSTERED PAIRED CONTRASTS (replication unit = measurement timecode)")
    say(f"        {'contrast':22} {'nMeas':>6} {'nClus':>6} {'mean d|err|':>12} "
        f"{'clusterMean':>12} {'cluster 95% CI':>26} {'clusImp':>8}")
    C = {}
    for a, b in CONTRASTS:
        # A paired contrast is UNAVAILABLE if either member is invalid; it is not zero and not
        # silently dropped, because "SD-D/M1 minus PD-D/M1" was quoted as a result.
        if not (ok(a) and ok(b)):
            why = FV.contrast_unavailable_reason(validities, a, b, clips)
            say(f"        {a + ' - ' + b:22} {'unavailable':>6}  {why}")
            C[f"{a} minus {b}"] = {"available": False, "reason": why}
            continue
        if a not in rows or b not in rows:
            continue
        e = cluster_effect(rows[a], rows[b], lambda r: r["event"], lambda r: r["tc"])
        if not e:
            continue
        C[f"{a} minus {b}"] = {**e, "available": True}
        ci = e["cluster_ci95"]
        cis = f"[{ci[0]:+8.4f}, {ci[1]:+8.4f}]" if ci else "n/a"
        say(f"        {a + ' - ' + b:22} {e['n_measurements']:6d} {e['n_clusters']:6d} "
            f"{e['mean_d_abs_err']:+12.4f} {e['cluster_mean']:+12.4f} {cis:>26} "
            f"{e['clusters_improved']}/{e['n_clusters']:<4}")
    say(f"        negative means the first candidate has smaller absolute error")
    R.setdefault("known_length", {})[tag] = {"summary": S, "contrasts": C,
                                             "reportable_candidates": reportable,
                                             "invalid_candidates": sorted(invalid_notes),
                                             "allow_invalid": bool(allow_invalid)}
    return S, C


def report_strata(say, rows, tag, R, validities=None, clips=None, allow_invalid=False):
    base = rows.get("B/M0")
    if not base:
        return
    order = [n for n in ["stored"] + [f"{o}/{m}" for o, m in OBJMODELS] if n in rows]
    if validities is not None and not allow_invalid:
        order = [n for n in order
                 if n == "stored" or FV.candidate_valid(validities, n, clips)]
    say(f"\n        PRESPECIFIED STRATA (thresholds from B/M0 geometry only), MAE by candidate")
    out = {}
    for gname, gkey, hi in (("camera distance", "camdist", True),
                            ("image radius", "radius", True),
                            ("screen edge (closest)", "edge", False),
                            ("true length", "true", True)):
        v = np.array([r[gkey] for r in base], float)
        thr = np.percentile(v, 75 if hi else 25)
        idx = {r["event"] for r in base if (r[gkey] >= thr if hi else r[gkey] <= thr)}
        say(f"          {gname:22} thr {thr:9.2f} n {len(idx):4d}  " + "  ".join(
            f"{n} {np.mean([abs(r['err']) for r in rows[n] if r['event'] in idx]):7.3f}"
            for n in order))
        out[gname] = {"threshold": float(thr), "n": len(idx),
                      "mae": {n: float(np.mean([abs(r["err"]) for r in rows[n]
                                                if r["event"] in idx])) for n in order}}
    R.setdefault("strata", {})[tag] = out


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--docs", nargs="*", default=["pool", "8mm", "mid"])
    ap.add_argument("--sd-from", default=None,
                    help="path to an sd_real-shaped artifact whose converged SD-D maps are EVALUATED "
                         "instead of refitting SD-D here. FAIL-CLOSED: every requested SD-D map must "
                         "present a COMPLETE provenance record (sdprov contract: artifact content "
                         "hash, document and camera identity, the SPECIFICALLY REQUESTED observation "
                         "view, the canonical point-set hash, line count, frame, coordinate "
                         "convention, model parameterization, producer revision AND producer-code "
                         "fingerprint, parameter identity and status) that matches inputs "
                         "reconstructed independently from the documents, or the run aborts with exit "
                         "3 before any optimizer is constructed (see preflight_sd_reuse)")
    ap.add_argument("--sd-sidecar", action="append", default=None, metavar="PATH",
                    help="provenance sidecar for a LEGACY artifact that predates the sdprov contract "
                         "(sd_real_full.json records no view, frame or coordinate convention). The "
                         "sidecar is keyed by the artifact's exact SHA-256 and must carry the complete "
                         "contract; established artifacts are never rewritten to add metadata. "
                         "Repeatable. Defaults to <artifact>.provenance.json when it exists")
    ap.add_argument("--sd-refit-missing", action="store_true",
                    help="ONLY with --sd-from: permit refitting SD-D maps that are ABSENT from the "
                         "artifact. Present-but-mismatched or malformed records still abort. Mixes "
                         "provenance in one table, so it is off by default and announced loudly")
    ap.add_argument("--allow-invalid", action="store_true",
                    help="EXPLORATION ONLY: report candidates whose fits did not converge. Every "
                         "table is labelled and the artifact records that this was set.")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    if args.sd_refit_missing and not args.sd_from:
        ap.error("--sd-refit-missing is meaningless without --sd-from; refusing an ambiguous "
                 "combination (without --sd-from every SD-D map is fitted here anyway)")
    if args.sd_sidecar and not args.sd_from:
        ap.error("--sd-sidecar is meaningless without --sd-from; a provenance sidecar describes an "
                 "artifact that is being reused, and refusing this combination keeps the flags "
                 "unambiguous")
    sd_src = load_sd_source(args.sd_from, sidecar_paths=args.sd_sidecar) if args.sd_from else None

    ALL_DOCS = [d["key"] for d in DOCS]
    CANDIDATES = ["stored"] + [f"{o}/{m}" for o, m in OBJMODELS]
    W = artifacts.ArtifactWriter(
        analysis="xdoc_objectives", script=__file__, outdir=args.outdir,
        requested_documents=args.docs, all_documents=ALL_DOCS,
        requested_candidates=CANDIDATES,
        objective_versions={"objectives": "B/SD/ED/PD as of downstream injection refactor",
                           "PD-D": "objectives.PDExact (exact projective lattice)",
                           "SD-D": (f"EVALUATED from {args.sd_from} ({sd_src['solver']})"
                                    if sd_src else
                                    f"objectives.fit(SD), max_nfev={SD_MAX_NFEV}"),
                           "SD-D_source_manifest": (
                               {"artifact": os.path.basename(sd_src["path"]),
                                "artifact_sha256": sd_src["artifact_sha256"],
                                "analysis": sd_src["analysis"],
                                "started": sd_src["started"], "git": sd_src["git"],
                                "source_file_sha256": sd_src["source_sha256"],
                                "producer_code_fingerprint":
                                    SP.code_fingerprint(sd_src["source_sha256"]),
                                "provenance_schema": SP.SCHEMA_VERSION,
                                "sidecars": {os.path.basename(p): SP.file_sha256(p)
                                             for p in sd_src.get("sidecar_paths") or []}}
                               if sd_src else None),
                           "distortion_map": "lattice.U -> parity_step5.undistort14 (14-parameter)"},
        source_files=["xdoc_objectives.py", "downstream.py", "objectives.py", "lattice.py",
                      "stage2.py", "nodes.py", "knownlength.py", "fitvalidity.py", "artifacts.py",
                      "sdprov.py", "fitstatus.py"],
        extra_modules=(),
        calibration_node_source="ZVSSCREENPOINT via nodes.py, plus 2016 Cal A/B XML on the pool test")
    if args.allow_invalid:
        W.note("--allow-invalid was set: results may include UNCONVERGED fits and are exploratory")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R = {"documents": {}}
    say("=" * 108)
    say("PART 2: PD-D AND THE MODERN SD-D LINE FALLBACK ACROSS KNOWN-LENGTH DOCUMENTS")
    say("=" * 108)
    say(f"  document scope: {W.document_scope}   ->   {W.basename('json')}")
    say("  Explicit-injection downstream path throughout (downstream.py). No monkeypatch, no stale")
    say("  stored downstream geometry. SD-D deliberately ignores lattice projectivity.")
    say("  Every distortion map is BOUND to its (document SHA-256, ZVSCALIBRATION.Z_PK) camera and")
    say("  re-verified in build_calibration. Capped fits are INVALID and excluded from all reported")
    say("  numbers unless --allow-invalid is passed.")
    if W.unknown_documents:
        say(f"  *** unknown document keys requested and ignored: {W.unknown_documents}; the artifact "
            f"will be marked incomplete ***")
    say("\n  LENS METADATA: no document stores lens or focal length. ZVSVIDEOCLIP carries only")
    say("  clipName, fileName, syncOffset and windowFrame. The '13 mm' label on 2015-06-22-1 comes")
    say("  from harness script comments only and is NOT verifiable from the file, so distortion")
    say("  regime is characterised empirically below instead of by lens name.")

    # ---- explicit SD-D artifact reuse is verified for EVERY requested map before any optimizer
    # exists. This runs ahead of the document loop on purpose: a mismatch found halfway through would
    # already have produced fitted maps for the earlier documents, i.e. exactly the mixed-provenance
    # table this is meant to prevent.
    reuse = None
    if sd_src is not None:
        requested = []
        for spec in DOCS:
            if spec["key"] not in args.docs or not os.path.exists(spec["vsd"]):
                continue
            for clip, cal in sorted(DS.load_bound_cals(spec["vsd"]).items()):
                sha = cal["identity"].doc_sha256
                caps = LT.load_captures(spec["vsd"], clip)
                # Which view SD-D is about to be given, decided HERE by exactly the predicate the
                # document loop uses (`Dd.n >= 20` and no index contradictions), so the request names one
                # specific view rather than a set of acceptable ones. `expected` is the independently
                # reconstructed identity of that view: counts, line count, frame, coordinate convention,
                # model parameterization and the canonical point-set hash.
                Dd = OB.Dataset(caps, **SP.VIEWS["min_inc2_indexed"]["kwargs"])
                pd_ok = bool(Dd.n >= 20
                             and all(C.notes["index_contradictions"] == 0 for C in caps))
                want_view = "min_inc2_indexed" if pd_ok else "min_inc1_all_incidences"
                for model in ("M0", "M1"):
                    exp = SP.view_identity(OB, caps, want_view, model,
                                           frame=[LT.FRAME_W, LT.FRAME_H])
                    requested.append(SP.reuse_request(
                        spec["key"], sha, clip, f"SD-D/{model}", want_view, exp,
                        cal_pk=cal["identity"].cal_pk, clip_pk=cal["identity"].clip_pk))
        usable, refit = preflight_sd_reuse(say, sd_src, requested,
                                           refit_missing=args.sd_refit_missing)
        reuse = {"artifact": sd_src["path"], "artifact_sha256": sd_src["artifact_sha256"],
                 "n_requested": len(requested),
                 "n_verified": len(usable), "n_permitted_refit": len(refit),
                 "refit_missing_flag": bool(args.sd_refit_missing),
                 "provenance_schema": SP.SCHEMA_VERSION,
                 "sidecar_schema": SP.SIDECAR_SCHEMA_VERSION,
                 "pointset_hash_version": SP.POINTSET_HASH_VERSION,
                 "view_selector_version": SP.VIEW_SELECTOR_VERSION,
                 "code_fingerprint_version": SP.CODE_FINGERPRINT_VERSION,
                 "sidecars": {os.path.basename(p): SP.file_sha256(p)
                              for p in sd_src.get("sidecar_paths") or []},
                 "verifier_code_fingerprint_now": SP.code_fingerprint_now(),
                 "views": {k: SP.VIEWS[k] for k in SP.VIEWS},
                 "requested": [{"tag": r["tag"], "expected_view": r["expected_view"],
                                "n_obs": r["expected"]["n_obs"],
                                "n_lines": r["expected"]["n_lines"],
                                "pointset_sha256": r["expected"]["pointset_sha256"],
                                "ordered_pointset_sha256":
                                    r["expected"]["ordered_pointset_sha256"],
                                "frame": r["expected"]["frame"],
                                "coordinate_convention": r["expected"]["coordinate_convention"]}
                               for r in requested],
                 "verified": {f"{k[0][:12]}/{k[1]}/{k[2]}":
                              {"view_verified": v.get("view_verified"), "n_obs": v.get("n_obs"),
                               "pointset_sha256": v.get("pointset_sha256"),
                               "producer_code_sha256": v.get("producer_code_sha256"),
                               "producer_revision": v.get("producer_revision"),
                               "provenance_from": v.get("provenance_from"),
                               "termination": v.get("termination"), "nfev": v.get("nfev"),
                               "source_camera_id": v.get("source_camera_id")}
                              for k, v in usable.items()},
                 "permitted_refit": refit}
        if args.sd_refit_missing:
            say("  *** --sd-refit-missing IS ACTIVE: any absent SD-D map will be refitted here, so this "
                "artifact may contain MIXED provenance. Every affected fit records "
                "evaluated_not_refitted=false. ***")
        R["sd_reuse"] = reuse

    for spec in DOCS:
        if spec["key"] not in args.docs:
            continue
        vsd = spec["vsd"]
        if not os.path.exists(vsd):
            say(f"\n  *** {spec['label']}: file not found, skipped ***")
            W.document_failed(spec["key"], "document file not found")
            continue
        say(f"\n{'=' * 108}\n  {spec['label']}\n  {os.path.basename(vsd)}\n{'=' * 108}")
        # Bound load: every calibration carries its CameraIdentity, so build_calibration can verify.
        cals = DS.load_bound_cals(vsd)
        clips = sorted(cals)
        doc_sha = cals[clips[0]]["identity"].doc_sha256
        docR = R["documents"][spec["key"]] = {
            "label": spec["label"], "doc_key": DS.document_key(vsd), "doc_sha256": doc_sha,
            "cameras": {c: cals[c]["identity"].to_dict() for c in clips}}
        W.document_started(spec["key"], sha256=doc_sha, doc_key=DS.document_key(vsd),
                           node_source="vsd (ZVSSCREENPOINT)", label=spec["label"])
        say(f"    document SHA-256 {doc_sha}")
        for c in clips:
            say(f"      {c:14} cal_pk={cals[c]['identity'].cal_pk} "
                f"clip_pk={cals[c]['identity'].clip_pk}")
        D0 = kl.load(vsd, conventional_types=spec["types"], unit_mm=spec["unit_mm"])
        conv, clicks = D0["conventional"], D0["clicks"]
        say(f"    world unit x{spec['unit_mm']:.0f} = mm; {len(conv)} conventional measurements in "
            f"{len({r['tc'] for r in conv})} timecode clusters; loader exclusions "
            f"{len(D0['exclusions'])}")
        docR["n_conventional"] = len(conv)
        docR["n_clusters"] = len({r["tc"] for r in conv})

        # ---- lattice validation and empirical distortion regime, per camera
        say(f"\n    LATTICE VALIDATION per camera and capture")
        lat, dsets, dlines, capsets, pdok = {}, {}, {}, {}, {}
        for clip in clips:
            say(f"      {clip}")
            caps = LT.load_captures(vsd, clip)
            capsets[clip] = caps
            lat[clip] = lattice_report(say, caps, clip)
            Dd = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
            dsets[clip] = Dd
            dlines[clip] = OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
            ok = Dd.n >= 20 and all(r.get("contradictions", 0) == 0 for r in lat[clip])
            say(f"        fitted subset {Dd.n} observations, {Dd.nline} lines, {Dd.ncap} capture(s); "
                f"exact PD-D admissible: {ok}")
            if not ok:
                say(f"        *** PD-D not admissible here; that failure is itself fallback-design "
                    f"evidence and PD is NOT forced onto this data ***")
            pdok[clip] = bool(ok)
            say(f"        non-lattice unique-point set for SD-D fallback: "
                f"{dlines[clip].n} observations, {dlines[clip].nline} lines")
            lat[clip].append({"pd_admissible": bool(ok)})
        docR["lattice"] = lat
        # empirical distortion strength: how far the stored map moves a corner-ish pixel
        reg = {}
        for clip in clips:
            th = np.zeros(14); th[:13] = cals[clip]["dist"]
            probe = np.array([[1900.0, 1060.0], [960.0, 540.0]])
            u = LT.U(probe, th)
            reg[clip] = float(np.linalg.norm(u[0] - probe[0]))
        say(f"\n    EMPIRICAL DISTORTION REGIME (stored map displacement at the far corner): "
            + ", ".join(f"{c} {v:.1f} px" for c, v in reg.items()))
        docR["corner_displacement_px"] = reg

        # ---- fits
        say(f"\n    OBJECTIVE FITS")
        maps_by_clip = {}
        fitdiag = {}
        validities = {}
        for clip in clips:
            say(f"      {clip}")
            th, dg, vv = fit_candidates(say, dsets[clip], dlines[clip], capsets[clip], clip,
                                        pdok[clip] and all(pdok.get(c, False) for c in clips[:1]),
                                        sd_src=sd_src, doc_sha256=docR["doc_sha256"])
            maps_by_clip[clip] = th
            fitdiag[clip] = dg
            validities[clip] = vv
            say(f"      line-record audit ({clip})")
            dg["_line_audit"] = line_audit(say, capsets[clip], dsets[clip])
        docR["fits"] = {c: {k: v for k, v in fitdiag[c].items()} for c in clips}

        # ---- complete each validity record with admissibility and the eta-aware inverse audit
        for clip in clips:
            pts = np.array([[x, y] for x, y, _, _ in cals[clip]["front"] + cals[clip]["back"]],
                           float)
            for k, v in validities[clip].items():
                if not v.fitted or k not in maps_by_clip[clip]:
                    continue
                ad = LT.admissible(maps_by_clip[clip][k], pts)
                v.admissible = bool(ad["ok"])
                v.inverse_ok = bool(ad["roundtrip_box_all_converged"]
                                    and ad["roundtrip_box_px"] < 1e-9)
                v.extra["min_det_full_frame"] = ad["min_det_full_frame"]
        docR["fit_validity"] = {c: {k: v.to_dict() for k, v in validities[c].items()}
                                for c in clips}
        for clip in clips:
            for k, v in validities[clip].items():
                W.candidate_validity(spec["key"], clip, k, v.to_dict())
        inval = sorted({k for c in clips for k, v in validities[c].items() if not v.valid})
        if inval:
            say(f"\n    INVALID FITS on this document (excluded from every reported number): "
                f"{', '.join(inval)}")
            for k in inval:
                say(f"      {k}: {FV.invalid_reasons(validities, k, clips)}")

        # ---- assemble candidate maps, each BOUND to the camera it was fitted for
        def make_maps(cal_source):
            """Bind every map to `cal_source[clip]`'s CameraIdentity.

            Binding here rather than at use time is what makes a Left/Right swap impossible: the map
            objects themselves know which camera they came from, and build_calibration re-checks.
            """
            m = {}
            m["stored"] = {c: DS.DistortionMap.from13_for_camera(
                cals[c]["dist"], cal_source[c], name=f"stored/{c}",
                source="ZVSCALIBRATION stored columns") for c in clips}
            for obj, model in OBJMODELS:
                k = f"{obj}/{model}"
                if not all(k in maps_by_clip[c] for c in clips):
                    continue
                m[k] = {c: DS.DistortionMap.for_camera(
                    maps_by_clip[c][k], cal_source[c], name=f"{k}/{c}",
                    source="fitted this run") for c in clips}
            return m

        # ---- downstream, one or two node placements
        placements = [("vsd nodes", cals)]
        if spec["calxml"]:
            for tagx in ("A", "B"):
                try:
                    X = parse_calxml(tagx)
                    # Same cameras, different NODE CLICKS: the CameraIdentity is carried through
                    # unchanged (it identifies the camera, not the node placement), and the node
                    # source is recorded separately so the manifest can distinguish the placements.
                    cc = {c: {**cals[c], "front": X[c]["front"], "back": X[c]["back"],
                              "node_source": f"2016 Cal {tagx} XML"}
                          for c in clips if c in X}
                    if len(cc) == len(clips):
                        placements.append((f"Cal {tagx} (XML nodes)", cc))
                except Exception as e:                                      # noqa: BLE001
                    say(f"    Cal {tagx} XML unusable: {e}")
        # Cal A turns out to be the SAME node set as the stored .vsd placement, merely listed in a
        # different order, so it is not an independent placement and reproduces "vsd nodes" exactly.
        # Verified order-insensitively rather than inferred from the identical results.
        for pname, pcals in placements:
            dupe = ""
            if pname != "vsd nodes":
                same = all(sorted(map(tuple, np.round(np.array(cals[c][side], float), 4).tolist()))
                           == sorted(map(tuple, np.round(np.array(pcals[c][side], float),
                                                        4).tolist()))
                           for c in clips for side in ("front", "back"))
                dupe = ("  [SAME NODE SET as the stored placement, reordered -- not an independent "
                        "placement]" if same else "  [genuinely different placement]")
            say(f"\n    ---- node placement: {pname} "
                f"({len(pcals[clips[0]]['front'])} front, {len(pcals[clips[0]]['back'])} back "
                f"nodes){dupe}")
            maps = make_maps(pcals)          # bound to THIS placement's calibration dicts
            rows, cdiag = run_downstream(say, pcals, maps, conv, clicks, spec["unit_mm"], pname,
                                         validities=validities, allow_invalid=args.allow_invalid)
            tag = f"{spec['key']}/{pname}"
            report_known_length(say, rows, cdiag, clips, f"{spec['label']} | {pname}", R, tag,
                                validities=validities, allow_invalid=args.allow_invalid)
            report_strata(say, rows, tag, R, validities=validities, clips=clips,
                          allow_invalid=args.allow_invalid)
            docR.setdefault("calibration_diagnostics", {})[pname] = cdiag
            docR.setdefault("placements", []).append(pname)
        # Only now is the document finished. A crash above leaves it out of completed_documents, so
        # the artifact is written as `_partial` with complete: false and cannot alias a full run.
        W.document_completed(spec["key"], completed_candidates=sorted(maps))
        say(f"\n    [{time.time() - t00:.1f}s elapsed]")

    path = W.write(R)
    man = W.manifest()
    say(f"\n  scope {man['document_scope']}: requested {man['requested_documents']}, completed "
        f"{man['completed_documents']}, complete={man['complete']}")
    say(f"  wrote {path}   [{time.time() - t00:.1f}s total]")
    if not man["complete"]:
        say(f"  *** THIS ARTIFACT IS NOT COMPLETE and is named accordingly; it must not be quoted as "
            f"the canonical result ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
