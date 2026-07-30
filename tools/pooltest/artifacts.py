#!/usr/bin/env python3
"""Scope-safe, atomic, self-describing output for the authoritative harness scripts.

WHY THIS EXISTS. On 2026-07-29 a `--docs pool` run of `xdoc_objectives.py` wrote its single-document
results to `analysis-output/xdoc_objectives.json`, the same path the full three-document run uses. The
complete cross-document artifact was destroyed and replaced by a pool-only one carrying no indication
that it was partial. Everything downstream that read that file -- including the summary tables quoted
in CALIBRATION_REFERENCE_NOTES.md -- was silently reading one document's worth of a three-document
claim. Two independent defects made that possible:

  1. the filename did not depend on the scope, so a subset run aliased the full run; and
  2. the write was not atomic and not gated on success, so a partial or crashed run still produced a
     file that looked exactly like a finished one.

`ArtifactWriter` fixes both. The scope determines the filename, so a subset CANNOT occupy the full
run's name. The payload is written to a temporary file in the destination directory, validated by
re-reading it, and only then `os.replace`d into place -- so an interrupted run leaves any existing
artifact byte-identical. `complete` is set from whether every requested document and candidate actually
finished, never from a default argument.

PRIVACY. Manifests carry document KEYS (basenames) and SHA-256 hashes, never absolute paths: the
corpus lives under private field-site directory structures. Clicked screen coordinates, measurement
values and site names never enter the manifest.

Run with ~/.venvs/vidsync/bin/python.
"""

import json
import os
import platform
import subprocess
import sys
import tempfile
import time

SCHEMA_VERSION = "harness-artifact/1"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


# =============================================================== provenance helpers


def git_state():
    """Commit hash plus an explicit dirty flag. Never raises; records why if it could not look."""
    def g(*a):
        r = subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    commit = g("rev-parse", "HEAD")
    if commit is None:
        return {"available": False, "reason": "git rev-parse failed or not a repository"}
    status = g("status", "--porcelain")
    return {"available": True, "commit": commit, "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
            # A dirty tree is the normal state for this harness, so this is information, not a warning.
            "dirty": bool(status), "n_dirty_paths": len(status.splitlines()) if status else 0}


def interpreter_versions(extra_modules=()):
    """Interpreter and the versions of the libraries whose numerics affect results.

    The interpreter is identified by its VIRTUALENV NAME, not its absolute path: absolute paths here run
    through a home directory and, for the documents, through private field-site directory structures.
    `~/.venvs/vidsync` is the documented harness environment, so the name is what reproduces the run.
    """
    out = {"python": sys.version.split()[0],
           "virtualenv": os.path.basename(sys.prefix),
           "platform": platform.platform(), "machine": platform.machine()}
    for name in ("numpy", "scipy") + tuple(extra_modules):
        try:
            out[name] = __import__(name).__version__
        except Exception as e:                                               # noqa: BLE001
            out[name] = f"unavailable: {e}"
    return out


def file_sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def source_hashes(names):
    """SHA-256 of the harness source files a result actually depends on."""
    out = {}
    for n in names:
        p = n if os.path.isabs(n) else os.path.join(HERE, n)
        out[os.path.basename(p)] = file_sha256(p) if os.path.exists(p) else None
    return out


def safe_repro_command(argv=None):
    """A reproduction command with private paths reduced to safe keys.

    Any argument that names an existing file outside the repository -- which on this corpus means a
    .vsd under a private field-site directory -- is replaced by `<doc:KEY>`, where KEY is the basename
    without extension. The command therefore stays runnable by anyone who has the corpus in their own
    location, and the manifest never publishes where this machine keeps it.
    """
    argv = list(sys.argv if argv is None else argv)
    out = [f"~/.venvs/{os.path.basename(sys.prefix)}/bin/python"]
    for i, a in enumerate(argv):
        if i == 0:
            out.append(os.path.basename(a))
            continue
        if os.path.sep in a and not os.path.abspath(a).startswith(REPO + os.path.sep):
            out.append(f"<doc:{os.path.splitext(os.path.basename(a))[0]}>")
        else:
            out.append(a)
    return " ".join(out)


def scope_suffix(requested, full_set):
    """The filename component that makes a subset run unable to alias the full run.

    `full` is used ONLY when the request covers every known member -- never inferred from a default
    argument value, because that is precisely how the pool-only run came to be named like a full one.
    A subset is named by its sorted members so the name is deterministic and reproducible.
    """
    req = [k for k in full_set if k in set(requested)]
    if set(req) == set(full_set):
        return "full"
    if not req:
        return "empty"
    return "-".join(req)


# =============================================================== the writer


class ArtifactWriter:
    """Builds one machine-readable artifact with a complete manifest, and writes it atomically.

    Typical use:

        W = artifacts.ArtifactWriter(
                analysis="xdoc_objectives", script=__file__, outdir=OUT,
                requested_documents=args.docs, all_documents=[d["key"] for d in DOCS],
                requested_candidates=CANDIDATES,
                objective_versions={"PD-D": OB.VERSION, ...},
                source_files=["downstream.py", "objectives.py", "lattice.py"],
                repro_command=...)
        ...
        W.document_started("pool", sha256=..., node_source="vsd")
        W.candidate_validity("pool", "Left Camera", "SD-D/M0", validity.to_dict())
        W.document_completed("pool")
        ...
        path = W.write({"documents": ...})            # complete only if all of the above finished
    """

    def __init__(self, analysis, script, outdir, requested_documents, all_documents,
                 requested_candidates, objective_versions=None, source_files=(),
                 repro_command=None, extra_modules=(), schema_version=SCHEMA_VERSION,
                 calibration_node_source=None):
        self.analysis = analysis
        self.script = os.path.basename(script)
        self.outdir = outdir
        self.all_documents = list(all_documents)
        self.requested_documents = [d for d in self.all_documents if d in set(requested_documents)]
        self.unknown_documents = sorted(set(requested_documents) - set(self.all_documents))
        self.requested_candidates = list(requested_candidates)
        self.completed_documents = []
        self.failed_documents = {}
        self.completed_candidates = {}
        self.documents_meta = {}
        self.validity = {}
        self.objective_versions = dict(objective_versions or {})
        self.source_files = list(source_files)
        self.repro_command = repro_command or safe_repro_command()
        self.extra_modules = tuple(extra_modules)
        self.schema_version = schema_version
        self.calibration_node_source = calibration_node_source
        self.notes = []
        self.t_start = time.time()
        self.t_start_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.t_start))

    # ---- scope bookkeeping ----------------------------------------------------------------

    def document_started(self, key, sha256=None, doc_key=None, node_source=None, label=None):
        self.documents_meta[key] = {"doc_key": doc_key, "doc_sha256": sha256,
                                    "calibration_node_source": node_source, "label": label,
                                    "status": "started"}

    def document_completed(self, key, completed_candidates=None):
        if key not in self.completed_documents:
            self.completed_documents.append(key)
        self.documents_meta.setdefault(key, {})["status"] = "completed"
        if completed_candidates is not None:
            self.completed_candidates[key] = list(completed_candidates)

    def document_failed(self, key, reason):
        self.failed_documents[key] = str(reason)
        self.documents_meta.setdefault(key, {})["status"] = f"failed: {reason}"

    def candidate_validity(self, doc, camera, candidate, validity_dict):
        """Fit validity for one candidate on one camera. Required for EVERY candidate attempted."""
        self.validity.setdefault(doc, {}).setdefault(camera, {})[candidate] = validity_dict

    def note(self, text):
        self.notes.append(str(text))

    # ---- naming --------------------------------------------------------------------------

    @property
    def document_scope(self):
        return scope_suffix(self.requested_documents, self.all_documents)

    def basename(self, ext="json"):
        return f"{self.analysis}_{self.document_scope}.{ext}"

    def path(self, ext="json"):
        return os.path.join(self.outdir, self.basename(ext))

    def log_path(self):
        """Logs may stream, so they are NOT atomic -- but they are still scope-named."""
        return self.path("log")

    # ---- completeness --------------------------------------------------------------------

    def is_complete(self):
        """True only if every requested document finished and every one reported its candidates.

        Deliberately conservative: an unknown document key in the request, a failed document, or a
        document that never called `document_completed` all make the artifact incomplete.
        """
        if self.unknown_documents or self.failed_documents:
            return False
        if set(self.completed_documents) != set(self.requested_documents):
            return False
        return bool(self.requested_documents)

    def manifest(self):
        end = time.time()
        return {
            "schema_version": self.schema_version,
            "analysis": self.analysis,
            "script": self.script,
            "complete": self.is_complete(),
            "document_scope": self.document_scope,
            "requested_documents": self.requested_documents,
            "completed_documents": sorted(self.completed_documents),
            "failed_documents": self.failed_documents,
            "unknown_documents_requested": self.unknown_documents,
            "requested_candidates": self.requested_candidates,
            "completed_candidates": self.completed_candidates,
            "candidate_scope_complete": {
                d: sorted(self.completed_candidates.get(d, [])) == sorted(self.requested_candidates)
                for d in self.requested_documents},
            "documents": self.documents_meta,
            "calibration_node_source": self.calibration_node_source,
            "objective_versions": self.objective_versions,
            "fit_validity": self.validity,
            "source_file_sha256": source_hashes(self.source_files),
            "git": git_state(),
            "versions": interpreter_versions(self.extra_modules),
            "reproduction_command": self.repro_command,
            "started": self.t_start_iso,
            "ended": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(end)),
            "runtime_seconds": round(end - self.t_start, 3),
            "notes": self.notes,
        }

    # ---- atomic write --------------------------------------------------------------------

    def write(self, results, ext="json"):
        """Write `{manifest, results}` atomically. Returns the final path.

        An incomplete run is written under a `_partial` name with `complete: false` so its evidence
        survives without ever occupying the canonical name.
        """
        man = self.manifest()
        payload = {"manifest": man, "results": results}
        name = self.basename(ext)
        if not man["complete"]:
            name = f"{self.analysis}_{self.document_scope}_partial.{ext}"
        return atomic_write_json(os.path.join(self.outdir, name), payload)


    def write_embedded(self, results, canonical_basename, ext="json"):
        """For artifacts that OTHER scripts already load by a fixed name and by top-level key.

        `obj_pd_closure.json` is read by `downstream_parity.py` as `{clip: {...}}`, so wrapping it in
        `{manifest, results}` would break that reader. Here the manifest goes in under the reserved
        `_manifest` key -- the shape is preserved, the provenance is still present, the write is still
        atomic, and a scope-incomplete run still CANNOT occupy the canonical name: it goes to
        `<analysis>_<scope>_partial.<ext>` instead.
        """
        man = self.manifest()
        out = dict(results)
        out["_manifest"] = man
        if man["complete"]:
            return atomic_write_json(os.path.join(self.outdir, canonical_basename), out)
        return atomic_write_json(
            os.path.join(self.outdir, f"{self.analysis}_{self.document_scope}_partial.{ext}"), out)


def atomic_write_json(path, payload):
    """Serialise, write to a temp file in the SAME directory, re-read to validate, then rename.

    Same-directory temp matters: `os.replace` is only atomic within a filesystem. Validation by
    re-reading catches a truncated or non-serialisable payload BEFORE it can replace a good artifact.
    """
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    # Serialise first: if this raises, the existing artifact has not been touched at all.
    text = json.dumps(payload, indent=1, default=_json_default)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-" + os.path.basename(path) + ".", suffix=".part")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp) as f:                     # validate the bytes that will become the artifact
            json.load(f)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:                                                        # noqa: BLE001
        pass
    if isinstance(o, set):
        return sorted(o, key=str)
    return float(o)


def read_artifact(path):
    """Load an artifact and refuse to treat an incomplete one as a result by accident."""
    with open(path) as f:
        a = json.load(f)
    man = a.get("manifest")
    if man is None:
        return {"manifest": {"schema_version": "pre-manifest", "complete": None}, "results": a,
                "legacy": True}
    return a
