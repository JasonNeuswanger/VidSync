#!/usr/bin/env python3
"""The provenance contract for EXPLICITLY REUSED SD-D distortion maps.

WHY THIS EXISTS, 2026-07-29 (revision 3). Revision 2 made `xdoc_objectives.py --sd-from` fail-closed
against an absent or mismatched record, but the identity it verified was too weak in five specific ways,
all of them confirmed from the code before this module was written:

  1. It INFERRED the observation view from `n_obs` alone -- `matches = [v for v, cnt in lv.items() if
     cnt == n]`. Two different point sets with the same cardinality were therefore indistinguishable.
  2. It ACCEPTED MISSING frame and coordinate-convention metadata: both tests were guarded by
     `if declared and local`, and the real `sd_real_full.json` records neither field, so both checks were
     dead on the only artifact ever reused.
  3. It accepted EITHER recognized view rather than the view actually requested. The request tuple was
     `(doc_key, sha, clip, name)` and carried no expected view at all, so a `min_inc=1` map verified
     against a caller that was going to use it as the `min_inc=2` map. `test_sd_reuse_failclosed.py`
     asserted that as intended behaviour.
  4. It identified the producing implementation ONLY by the manifest's analysis NAME
     (`if not src.get("analysis")`). A name is not a revision and not a code identity.
  5. Nothing tied a reused map to the exact bytes of the artifact it came from, so "the source fits did
     not change" could only be argued from modification times, which are not content evidence.

This module replaces that with an exact contract. Every explicitly reused SD-D map must present, and
match, all of:

    artifact_sha256            raw SHA-256 of the artifact FILE, computed at load time from the bytes
    doc_key, doc_sha256        document identity and source-document content hash
    clip, cal_pk, clip_pk      camera identity (ZVSCALIBRATION.Z_PK / ZVSVIDEOCLIP.Z_PK)
    candidate, model           model identity (SD-D/M0 or SD-D/M1)
    view_id                    EXPLICIT observation-view identity, never inferred from a count
    view_selector              the exact selection predicate, plus view_selector_id and its version
    n_obs, n_lines, n_captures the three counts
    pointset_sha256            deterministic canonical hash over every input field SD-D consumes
    ordered_pointset_sha256    the same records in dataset order, because block order affects execution
    frame                      [width, height] in pixels
    coordinate_convention      the pixel convention the coordinates are in
    model_parameterization     which 14-vector entries are free, and which map consumes them
    producer_revision          repository revision plus an explicit dirty flag
    producer_code_fingerprint  deterministic content fingerprint of the producing implementation files
    parameter_sha256           identity of the serialized map itself
    status                     convergence, invertibility, empirical admissibility, ranking eligibility

A Git commit alone is insufficient: the producing worktree WAS dirty (the real artifact records
`dirty: true, n_dirty_paths: 172`), so the commit does not determine the code that ran. Both the revision
and a per-file content fingerprint are required, and the fingerprint is what is actually compared. The
CURRENT worktree is never required to be clean -- that would make this harness unusable.

LEGACY ARTIFACTS. `sd_real_full.json` predates this contract and must NOT be rewritten to add metadata:
it is an established calibration artifact. Legacy provenance is supplied instead by a SIDECAR manifest
keyed by the artifact's exact content hash (`sd-provenance-sidecar/1`). A sidecar is accepted only when
its declared artifact hash equals the hash of the file being loaded, its metadata matches the requested
document/camera/model/view, and its counts, line count and point-set hash match inputs reconstructed
INDEPENDENTLY from the documents. Sidecar fields may only be populated from durable independent evidence
-- the originating run manifest, the recorded reproduction command, the stored per-file source hashes,
the repository state -- never by copying a guess out of the artifact being verified.

NOTHING HERE FITS ANYTHING. There is no optimizer, no solver and no import of one; the module builds
observation views and hashes them, and every verification path is a pure function.

Run with ~/.venvs/vidsync/bin/python. Consumed by xdoc_objectives.py and test_sd_provenance.py.
"""

import hashlib
import json
import os

import numpy as np

SCHEMA_VERSION = "sd-provenance/2"
SIDECAR_SCHEMA_VERSION = "sd-provenance-sidecar/1"
POINTSET_HASH_VERSION = "sd-pointset/1"
VIEW_SELECTOR_VERSION = "sd-view-selector/1"
CODE_FINGERPRINT_VERSION = "sd-code-fingerprint/1"
PARAMETER_HASH_VERSION = "sd-theta14/1"

HERE = os.path.dirname(os.path.abspath(__file__))

# The implementation files that determine an SD-D map. A producer may record hashes for more files than
# these (sd_real.py records eight); the fingerprint is taken over exactly this REQUIRED subset so that
# adding an unrelated file to a producer's `source_files` list cannot change the identity of a map.
SD_PRODUCER_CODE_FILES = ("lattice.py", "mapmetrics.py", "objectives.py", "sd_fast.py", "sd_real.py")

# The coordinate convention every observation in a view is in. Phrased as a CODE-VERIFIABLE fact rather
# than as an interpretation: `lattice.load_captures` selects ZVSSCREENPOINT.ZSCREENX/ZSCREENY and passes
# `float(x), float(y)` through with no flip, offset or normalization, so producer and consumer are reading
# the same field the same way. "Origin top-left, y down" is what VidSync's overlay stores, but that is an
# interpretation of the app rather than something a harness run can establish, so it is not what the
# contract compares. The convention is pinned by the producer code fingerprint.
COORDINATE_CONVENTION = ("raw ZVSSCREENPOINT.ZSCREENX/ZSCREENY pixels as stored, no transform applied "
                         "(lattice.load_captures)")


# =============================================================== canonical point-set hashing


def _f(x):
    """Exact, round-trippable, locale-free text for one float64.

    `float.hex()` is lossless in both directions, unlike any decimal format: two point sets that differ
    in the last bit of one coordinate produce different records here, and a value that survives a JSON
    round trip produces the same record. A `%.6f` style format -- which the ad hoc `sd_viewsens.obs_hash`
    used -- would quietly collide sub-micropixel differences.
    """
    return float(x).hex()


def _cap_identity(D, i):
    """Stable identity of the capture an observation belongs to.

    The integer in `D.cap_of` is a position in the caller's `caps` list, which is not semantic. The
    capture's timecode is, so it is used when available and the positional index is recorded explicitly
    as a fallback (marked, so the two can never be confused).
    """
    caps = getattr(D, "caps", None)
    ci = int(D.cap_of[i])
    if caps is not None and 0 <= ci < len(caps):
        tc = getattr(caps[ci], "timecode", None)
        if tc is not None:
            return f"tc={tc}"
    return f"capidx={ci}"


def line_fingerprints(D):
    """Content-derived identity for every line in the view, in global line-id order.

    WHY NOT THE LINE ID. `Dataset.gline` assigns global line ids in the order observations are visited,
    so the id of a physical line depends on construction order rather than on the line. A fingerprint
    over the line's own content -- its capture, its family and the exact coordinates of its selected
    members, sorted -- is stable under any renumbering and still distinguishes two genuinely different
    lines. The capture is included because two captures can legitimately contain the same coordinates.
    """
    members = [[] for _ in range(int(D.nline))]
    for i, ls in enumerate(D.obs_lines):
        for g in ls:
            members[int(g)].append(i)
    out = []
    for g in range(int(D.nline)):
        mem = members[g]
        cap = _cap_identity(D, mem[0]) if mem else "cap=none"
        rows = sorted(f"{_f(D.xy[i, 0])},{_f(D.xy[i, 1])}" for i in mem)
        h = hashlib.sha256()
        h.update(f"{POINTSET_HASH_VERSION}|line|{cap}|family={int(D.line_family[g])}"
                 f"|n_members={len(rows)}\n".encode())
        for r in rows:
            h.update((r + "\n").encode())
        out.append(h.hexdigest())
    return out


def canonical_records(D):
    """One canonical text record per observation, in DATASET order.

    Each record carries every field the SD-D residual consumes for that observation: the capture it
    belongs to, its coordinates, its Delaunay weight (entering the residual as sqrt(w), so it changes the
    fit), its incidence count, and the fingerprints of the lines it lies on. Nothing else in `Dataset`
    reaches `sd_fast.SDFast` or `objectives.resid_SD`; `rc`, `lat` and `local` are PD-D and ED inputs and
    are deliberately excluded so that an SD-D map is not invalidated by a field it never saw.
    """
    fps = line_fingerprints(D)
    recs = []
    for i in range(int(D.n)):
        keys = sorted(fps[int(g)] for g in D.obs_lines[i])
        recs.append(f"{_cap_identity(D, i)}|x={_f(D.xy[i, 0])}|y={_f(D.xy[i, 1])}"
                    f"|w={_f(D.w[i])}|n_inc={len(keys)}|lines={','.join(keys)}")
    return recs


def pointset_digest(D):
    """The versioned canonical point-set hash, plus the counts it is bound to.

    `pointset_sha256` is order-independent: records are sorted, because the identity of a point SET must
    not depend on the order the loader happened to visit observations in. `ordered_pointset_sha256` is
    the same records unsorted, recorded IN ADDITION because order does reach execution --
    `objectives._blocks` groups observations by incidence count in visit order, which fixes the residual
    row layout and therefore the exact floating-point summation order. Both are compared on reuse.
    """
    recs = canonical_records(D)
    header = (f"{POINTSET_HASH_VERSION}|n_obs={int(D.n)}|n_lines={int(D.nline)}"
              f"|n_captures={int(D.ncap)}\n")
    un = hashlib.sha256(header.encode())
    for r in sorted(recs):
        un.update((r + "\n").encode())
    od = hashlib.sha256((header + "ORDERED\n").encode())
    for r in recs:
        od.update((r + "\n").encode())
    ls = hashlib.sha256((header + "LINESET\n").encode())
    for fp in sorted(line_fingerprints(D)):
        ls.update((fp + "\n").encode())
    return {"pointset_hash_version": POINTSET_HASH_VERSION,
            "pointset_sha256": un.hexdigest(),
            "ordered_pointset_sha256": od.hexdigest(),
            "lineset_sha256": ls.hexdigest(),
            "n_obs": int(D.n), "n_lines": int(D.nline), "n_captures": int(D.ncap)}


def parameter_sha256(theta14):
    """Identity of the serialized map. Exact, so a JSON round trip is verifiable bit-for-bit."""
    th = np.asarray(theta14, float).ravel()
    body = ",".join(_f(v) for v in th)
    return hashlib.sha256(f"{PARAMETER_HASH_VERSION}|n={th.size}|{body}".encode()).hexdigest()


# =============================================================== observation views


# The two observation views SD-D is ever given, as EXPLICIT identities with exact selection predicates.
# Both contain only successfully lattice-indexed observations on an eligible document: all 340 Left and
# 365 Right source observations on 2015-06-22-1 were indexed, and the 309/318 subsets arise from the
# `min_inc=2` incidence filter, not from any indexing failure. The historical internal names are recorded
# so an older log can be read, but they are never used as identities.
VIEWS = {
    "min_inc2_indexed": {
        "view_selector_id": "sd-view/min_inc2_indexed@1",
        "kwargs": {"require_indexed": True, "min_inc": 2, "kappa": 3.0},
        "predicate": "OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)",
        "display_label": "min_inc=2 view (>=2 line incidences)",
        "internal_id_history": ["indexed", "Dind", "dsets[clip]"],
        "caller_branch": "sd_real.build if-branch / xdoc_objectives dsets[clip]; supplied when the "
                         "lattice-eligibility test PASSES",
    },
    "min_inc1_all_incidences": {
        "view_selector_id": "sd-view/min_inc1_all_incidences@1",
        "kwargs": {"require_indexed": False, "min_inc": 1, "kappa": 3.0},
        "predicate": "OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)",
        "display_label": "min_inc=1 view (all incidences kept)",
        "internal_id_history": ["fallback_raw", "Dline", "dlines[clip]"],
        "caller_branch": "sd_real.build else-branch / xdoc_objectives dlines[clip]; supplied when the "
                         "lattice-eligibility test FAILS",
        "note": "on an eligible document this still contains only successfully indexed observations; "
                "the name is historical and does not mean unindexed",
    },
}


def build_view(OB, caps, view_id):
    """The Dataset for one named view. The kwargs come from `VIEWS`, so the predicate string cannot
    drift away from what is actually constructed."""
    if view_id not in VIEWS:
        raise KeyError(f"unknown observation view {view_id!r}; known: {sorted(VIEWS)}")
    return OB.Dataset(caps, **VIEWS[view_id]["kwargs"])


def model_parameterization(OB, model):
    """Exact parameterization identity for one model, derived from the code rather than restated."""
    free = list(int(j) for j in OB.MODELS[model])
    return (f"lattice14/theta14; model {model}; free={free}; "
            f"map=lattice.U (== parity_step5.undistort14)")


def view_identity(OB, caps, view_id, model, frame=None, convention=COORDINATE_CONVENTION):
    """Everything about the LOCAL, independently reconstructed inputs a reused map must match."""
    D = build_view(OB, caps, view_id)
    out = dict(pointset_digest(D))
    out.update({"view_id": view_id,
                "view_selector": VIEWS[view_id]["predicate"],
                "view_selector_id": VIEWS[view_id]["view_selector_id"],
                "view_selector_version": VIEW_SELECTOR_VERSION,
                "frame": [float(frame[0]), float(frame[1])] if frame else None,
                "coordinate_convention": convention,
                "model_parameterization": model_parameterization(OB, model)})
    return out


# =============================================================== producer code identity


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def code_fingerprint(file_hashes, required=SD_PRODUCER_CODE_FILES):
    """Deterministic content fingerprint of the producing implementation.

    `file_hashes` is a {basename: sha256} map -- exactly the shape `artifacts.source_hashes` produces and
    every harness manifest already stores, so a legacy artifact's own manifest is sufficient durable
    evidence for this field without re-deriving anything. The fingerprint is over the REQUIRED subset
    only, sorted, so it is independent of how many extra files a producer happened to list.

    This is what makes a dirty producing worktree verifiable: the commit says which tree was checked out,
    the fingerprint says what the files actually contained.
    """
    fh = {k: v for k, v in (file_hashes or {}).items()}
    missing = [n for n in required if not fh.get(n)]
    if missing:
        return {"version": CODE_FINGERPRINT_VERSION, "available": False,
                "required_files": list(required), "missing_files": missing,
                "combined_sha256": None, "files": {n: fh.get(n) for n in required}}
    body = "\n".join(f"{n}={fh[n]}" for n in sorted(required))
    return {"version": CODE_FINGERPRINT_VERSION, "available": True,
            "required_files": list(required), "missing_files": [],
            "files": {n: fh[n] for n in sorted(required)},
            "combined_sha256": hashlib.sha256(
                f"{CODE_FINGERPRINT_VERSION}\n{body}\n".encode()).hexdigest()}


def code_fingerprint_now(required=SD_PRODUCER_CODE_FILES, root=HERE):
    """The fingerprint of the CURRENT working copy. Diagnostic only -- never required to match, because
    the harness is expected to be dirty and to move on while old artifacts stay valid."""
    return code_fingerprint({n: (file_sha256(os.path.join(root, n))
                                 if os.path.exists(os.path.join(root, n)) else None)
                             for n in required}, required=required)


# =============================================================== the record contract


REQUIRED_RECORD_FIELDS = (
    "schema_version", "artifact_sha256", "doc_key", "doc_sha256", "clip", "candidate", "model",
    "view_id", "view_selector", "view_selector_id", "view_selector_version",
    "n_obs", "n_lines", "n_captures",
    "pointset_hash_version", "pointset_sha256", "ordered_pointset_sha256",
    "frame", "coordinate_convention", "model_parameterization",
    "producer_revision", "producer_code_fingerprint", "parameter_sha256", "status",
)

REQUIRED_STATUS_FIELDS = ("optimizer_converged", "numerically_invertible", "empirically_admissible",
                          "eligible_for_ranking")


def reuse_request(doc_key, doc_sha256, clip, candidate, expected_view, expected, *,
                  cal_pk=None, clip_pk=None):
    """One explicit reuse request. `expected` is a `view_identity` result for the REQUESTED view.

    The expected view is part of the REQUEST, not something the artifact gets to choose. That is the
    whole point of revision 3: an artifact holding a perfectly valid map for the other recognized view
    must fail, because it is not the map this caller is about to use.
    """
    model = candidate.split("/")[-1]
    return {"doc_key": doc_key, "doc_sha256": doc_sha256, "clip": clip, "candidate": candidate,
            "model": model, "cal_pk": cal_pk, "clip_pk": clip_pk,
            "expected_view": expected_view, "expected": dict(expected),
            "tag": f"{doc_key}/{clip}/{candidate}"}


# =============================================================== sidecars


def sidecar_key(rec):
    return (rec.get("doc_sha256"), rec.get("clip"), rec.get("candidate"))


def load_sidecars(paths):
    """Index sidecar manifests by (artifact_sha256, doc_sha256, clip, candidate).

    Returns `(index, problems)`. Lookup is deterministic: the artifact's own content hash is the primary
    key, so a sidecar written for a different artifact can never be consulted. Malformed, incomplete,
    duplicated and CONFLICTING entries are all rejected here rather than at use time, and every rejection
    is described. A duplicate key with byte-identical content is still refused: two sidecars asserting the
    same thing are two things to keep in sync, and silently preferring one is how provenance rots.
    """
    index, problems, seen = {}, [], {}
    for p in sorted(set(paths or ())):
        if not os.path.exists(p):
            problems.append(f"sidecar {os.path.basename(p)}: file does not exist")
            continue
        try:
            with open(p) as fh:
                doc = json.load(fh)
        except Exception as e:                                               # noqa: BLE001
            problems.append(f"sidecar {os.path.basename(p)}: not readable as JSON ({e})")
            continue
        if not isinstance(doc, dict):
            problems.append(f"sidecar {os.path.basename(p)}: top level is not an object")
            continue
        sv = doc.get("schema_version")
        if sv != SIDECAR_SCHEMA_VERSION:
            problems.append(f"sidecar {os.path.basename(p)}: schema_version {sv!r} is not "
                            f"{SIDECAR_SCHEMA_VERSION!r}")
            continue
        art = doc.get("artifact_sha256")
        if not isinstance(art, str) or len(art) != 64:
            problems.append(f"sidecar {os.path.basename(p)}: artifact_sha256 {art!r} is not a "
                            f"64-character hex digest")
            continue
        recs = doc.get("records")
        if not isinstance(recs, list) or not recs:
            problems.append(f"sidecar {os.path.basename(p)}: `records` is missing or empty")
            continue
        for rec in recs:
            if not isinstance(rec, dict):
                problems.append(f"sidecar {os.path.basename(p)}: a record is not an object")
                continue
            r = dict(rec)
            r.setdefault("schema_version", SCHEMA_VERSION)
            r["artifact_sha256"] = art
            r["_sidecar"] = os.path.basename(p)
            k = (art,) + sidecar_key(r)
            if None in k[1:]:
                problems.append(f"sidecar {os.path.basename(p)}: a record does not identify "
                                f"(doc_sha256, clip, candidate): got {k[1:]}")
                continue
            if k in index:
                same = _comparable(index[k]) == _comparable(r)
                problems.append(
                    f"sidecar entry {k[1][:12]}/{k[2]}/{k[3]} for artifact {art[:12]} is "
                    f"{'DUPLICATED' if same else 'CONFLICTING'} between "
                    f"{seen[k]} and {os.path.basename(p)}; refusing to choose between them")
                index[k] = {"_rejected": True}
                continue
            index[k], seen[k] = r, os.path.basename(p)
    return index, problems


def _comparable(rec):
    return json.dumps({k: v for k, v in rec.items() if k != "_sidecar"}, sort_keys=True, default=str)


def default_sidecar_paths(artifact_path):
    """The conventional sidecar location for an artifact: `<artifact>.provenance.json`."""
    return [artifact_path + ".provenance.json"]


# =============================================================== verification


def _mismatch(field, got, want):
    return f"{field}: artifact/sidecar says {got!r}, request requires {want!r}"


def verify_record(rec, req, artifact_sha256, *, manifest_source_hashes=None,
                  recomputed_status=None):
    """Verify ONE provenance record against ONE request. Returns a list of problems (empty == verified).

    Pure. Collects every problem instead of stopping at the first, so one run reports the whole truth
    about a record. `manifest_source_hashes` is the producing manifest's own {file: sha256} map, used as
    an independent cross-check on the declared code fingerprint. `recomputed_status` is a
    `fitstatus.camera_status`-shaped dict derived from the artifact's stored evidence, used to catch a
    sidecar that declares a status the artifact's own numbers do not support.
    """
    bad = []
    if not isinstance(rec, dict):
        return ["provenance record is not an object"]
    if rec.get("_rejected"):
        return ["provenance record was rejected at load time (duplicated or conflicting sidecar entry)"]

    missing = [f for f in REQUIRED_RECORD_FIELDS if rec.get(f) in (None, "", [], {})]
    if missing:
        bad.append(f"provenance is INCOMPLETE; missing or empty: {', '.join(missing)}")

    if rec.get("schema_version") not in (None, SCHEMA_VERSION):
        bad.append(f"schema_version {rec.get('schema_version')!r} is not {SCHEMA_VERSION!r}")

    # ---- artifact identity: the record must be about the bytes actually loaded
    if rec.get("artifact_sha256") and rec["artifact_sha256"] != artifact_sha256:
        bad.append(f"artifact hash mismatch: provenance describes {rec['artifact_sha256'][:16]} but the "
                   f"file loaded hashes to {artifact_sha256[:16]}")

    # ---- document, camera, model identity
    for field, want in (("doc_key", req.get("doc_key")), ("doc_sha256", req["doc_sha256"]),
                        ("clip", req["clip"]), ("candidate", req["candidate"]),
                        ("model", req["model"])):
        if want is None:
            continue
        got = rec.get(field)
        if got is not None and got != want:
            bad.append(_mismatch(field, got, want))
    for field in ("cal_pk", "clip_pk"):
        want = req.get(field)
        got = rec.get(field)
        if want is not None and got is not None and int(got) != int(want):
            bad.append(_mismatch(field, got, want))

    exp = req["expected"]

    # ---- the SPECIFICALLY REQUESTED view, by identity and by selection definition
    vid = rec.get("view_id")
    if vid is None:
        bad.append("no view_id: the observation view is UNSPECIFIED and may not be inferred")
    elif vid != req["expected_view"]:
        other = " (a recognized view, but not the one requested)" if vid in VIEWS else ""
        bad.append(f"view_id {vid!r} is not the requested view {req['expected_view']!r}{other}")
    if rec.get("view_selector") and rec["view_selector"] != exp["view_selector"]:
        bad.append(_mismatch("view_selector", rec["view_selector"], exp["view_selector"]))
    if rec.get("view_selector_id") and rec["view_selector_id"] != exp["view_selector_id"]:
        bad.append(_mismatch("view_selector_id", rec["view_selector_id"], exp["view_selector_id"]))
    if rec.get("view_selector_version") not in (None, VIEW_SELECTOR_VERSION):
        bad.append(f"view_selector_version {rec.get('view_selector_version')!r} is not "
                   f"{VIEW_SELECTOR_VERSION!r}")

    # ---- counts, line count, and the point-set hash. The counts are checked for a readable diagnostic;
    # the hash is what actually decides, so equal counts over different points cannot pass.
    for field in ("n_obs", "n_lines", "n_captures"):
        got, want = rec.get(field), exp.get(field)
        if got is not None and want is not None and int(got) != int(want):
            bad.append(_mismatch(field, int(got), int(want)))
    if rec.get("pointset_hash_version") not in (None, POINTSET_HASH_VERSION):
        bad.append(f"pointset_hash_version {rec.get('pointset_hash_version')!r} is not "
                   f"{POINTSET_HASH_VERSION!r}, so its digest is not comparable")
    for field in ("pointset_sha256", "ordered_pointset_sha256"):
        got, want = rec.get(field), exp.get(field)
        if got and want and got != want:
            same_n = rec.get("n_obs") is not None and int(rec["n_obs"] or -1) == int(exp["n_obs"])
            bad.append(f"{field} mismatch: {got[:16]} != independently reconstructed {want[:16]}"
                       + (" -- SAME observation count, DIFFERENT point set" if same_n else ""))

    # ---- frame and coordinate convention: required, never optional
    fr, wfr = rec.get("frame"), exp.get("frame")
    if fr is None:
        bad.append("no frame metadata: frame width and height are required")
    elif wfr is not None and [float(v) for v in fr] != [float(v) for v in wfr]:
        bad.append(_mismatch("frame", list(fr), list(wfr)))
    cv, wcv = rec.get("coordinate_convention"), exp.get("coordinate_convention")
    if cv is None:
        bad.append("no coordinate_convention: the pixel convention is required")
    elif wcv is not None and cv != wcv:
        bad.append(_mismatch("coordinate_convention", cv, wcv))

    # ---- model parameterization
    mp, wmp = rec.get("model_parameterization"), exp.get("model_parameterization")
    if mp and wmp and mp != wmp:
        bad.append(_mismatch("model_parameterization", mp, wmp))

    # ---- producer revision and code fingerprint. A commit alone is explicitly insufficient.
    prv = rec.get("producer_revision")
    if not isinstance(prv, dict) or not prv.get("commit"):
        bad.append("no producer_revision.commit: the producing repository revision is unrecorded")
    elif "dirty" not in prv:
        bad.append("producer_revision does not state whether the producing worktree was dirty, so the "
                   "commit cannot be interpreted")
    cf = rec.get("producer_code_fingerprint")
    if not isinstance(cf, dict):
        bad.append("no producer_code_fingerprint: the producing implementation is unidentified")
    else:
        if cf.get("version") != CODE_FINGERPRINT_VERSION:
            bad.append(f"producer_code_fingerprint.version {cf.get('version')!r} is not "
                       f"{CODE_FINGERPRINT_VERSION!r}")
        files = cf.get("files") or {}
        recomputed = code_fingerprint(files)
        if not recomputed["available"]:
            bad.append("producer_code_fingerprint is missing hashes for "
                       f"{recomputed['missing_files']}, so it cannot be verified")
        elif not cf.get("combined_sha256"):
            bad.append("producer_code_fingerprint has no combined_sha256")
        elif cf["combined_sha256"] != recomputed["combined_sha256"]:
            bad.append(f"producer_code_fingerprint.combined_sha256 {cf['combined_sha256'][:16]} does "
                       f"not match its own file hashes ({recomputed['combined_sha256'][:16]})")
        if manifest_source_hashes:
            off = sorted(n for n, h in files.items()
                         if manifest_source_hashes.get(n) and manifest_source_hashes[n] != h)
            if off:
                bad.append(f"producer_code_fingerprint disagrees with the producing manifest's own "
                           f"source_file_sha256 for {off}")

    # ---- the serialized map itself
    ph = rec.get("parameter_sha256")
    th = req.get("theta14")
    if ph and th is not None:
        actual = parameter_sha256(th)
        if ph != actual:
            bad.append(f"parameter_sha256 {ph[:16]} does not match the loaded theta ({actual[:16]})")

    # ---- status: present, internally consistent, and consistent with the artifact's own evidence
    st = rec.get("status")
    if not isinstance(st, dict):
        bad.append("no status block: convergence, invertibility, admissibility and ranking "
                   "eligibility are unrecorded")
    else:
        absent = [f for f in REQUIRED_STATUS_FIELDS if st.get(f) is None]
        if absent:
            bad.append(f"status is incomplete; missing: {', '.join(absent)}")
        if st.get("optimizer_converged") is False:
            bad.append("status records the source fit as NOT converged; refusing to reuse it")
        if st.get("numerically_invertible") is False:
            bad.append("status records the source map as NOT numerically invertible; refusing to "
                       "reuse it")
        if recomputed_status is not None:
            off = [f for f in REQUIRED_STATUS_FIELDS
                   if st.get(f) is not None
                   and bool(st[f]) != bool(recomputed_status.get(f))]
            if off:
                bad.append(f"declared status contradicts the artifact's own stored evidence for "
                           f"{off} (recomputed via fitstatus from the artifact's optimizer, inverse "
                           f"and frozen-gate records)")
    return bad
