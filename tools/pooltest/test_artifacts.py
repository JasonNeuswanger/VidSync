#!/usr/bin/env python3
"""Regression tests for scope-safe, atomic, self-describing artifacts.

The defect these cover: on 2026-07-29 a `--docs pool` run wrote `analysis-output/xdoc_objectives.json`,
destroying the complete three-document artifact and replacing it with a pool-only one that carried no
indication of being partial. Test 2 is that exact scenario.

Everything happens in a temporary directory. Nothing under analysis-output is read or written.
Run with ~/.venvs/vidsync/bin/python.
"""

import json
import os
import shutil
import sys
import tempfile
import traceback

import harness_import

harness_import.ensure_path()
import artifacts                                                             # noqa: E402

PASS, FAIL = [], []
ALL_DOCS = ["pool", "8mm", "mid"]
CANDS = ["stored", "B/M0", "B/M1", "PD-D/M0", "PD-D/M1", "SD-D/M0", "SD-D/M1"]


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def writer(tmp, docs, analysis="xdoc_objectives"):
    return artifacts.ArtifactWriter(
        analysis=analysis, script="xdoc_objectives.py", outdir=tmp,
        requested_documents=docs, all_documents=ALL_DOCS, requested_candidates=CANDS,
        objective_versions={"PD-D": "objectives.PDExact"},
        source_files=["artifacts.py"], repro_command="python xdoc_objectives.py --docs " + " ".join(docs))


def finish(W, docs, cands=None):
    for d in docs:
        W.document_started(d, sha256="0" * 64, doc_key=f"doc-{d}", node_source="vsd")
        for cam in ("Left Camera", "Right Camera"):
            for c in (cands or CANDS):
                W.candidate_validity(d, cam, c, {"valid": True, "candidate": c})
        W.document_completed(d, completed_candidates=cands or CANDS)


def main():
    print("=" * 100)
    print("ARTIFACT SCOPE-SAFETY AND ATOMICITY REGRESSION TESTS")
    print("=" * 100)
    tmp = tempfile.mkdtemp(prefix="vidsync-artifact-test-")
    try:
        # ------------------------------------------------------------ 1. full artifact
        print(f"\n[1] FULL three-document artifact")
        W = writer(tmp, ALL_DOCS)
        finish(W, ALL_DOCS)
        p_full = W.write({"documents": {d: {"mae": 1.0} for d in ALL_DOCS}})
        full_bytes = open(p_full, "rb").read()
        a = json.load(open(p_full))
        check("full run is named xdoc_objectives_full.json",
              os.path.basename(p_full) == "xdoc_objectives_full.json", os.path.basename(p_full))
        check("manifest says complete", a["manifest"]["complete"] is True)
        check("scope recorded as 'full'", a["manifest"]["document_scope"] == "full")
        man = a["manifest"]
        required = ["schema_version", "analysis", "script", "complete", "document_scope",
                    "requested_documents", "completed_documents", "failed_documents",
                    "requested_candidates", "completed_candidates", "candidate_scope_complete",
                    "documents", "calibration_node_source", "objective_versions", "fit_validity",
                    "source_file_sha256", "git", "versions", "reproduction_command", "started",
                    "ended", "runtime_seconds"]
        missing = [k for k in required if k not in man]
        check("manifest carries every required field", not missing, f"missing {missing}")
        check("git commit and an explicit dirty flag are present",
              man["git"].get("available") and "commit" in man["git"] and "dirty" in man["git"],
              f"commit {str(man['git'].get('commit'))[:12]} dirty={man['git'].get('dirty')}")
        check("interpreter and numpy/scipy versions recorded",
              "python" in man["versions"] and "numpy" in man["versions"]
              and "scipy" in man["versions"])
        check("authoritative source hashes recorded",
              man["source_file_sha256"].get("artifacts.py") is not None)
        check("fit validity present for every candidate on every camera of every document",
              all(len(man["fit_validity"][d][cam]) == len(CANDS)
                  for d in ALL_DOCS for cam in ("Left Camera", "Right Camera")))
        check("reproduction command recorded", "xdoc_objectives.py --docs" in man["reproduction_command"])
        check("runtime and start/end times recorded",
              isinstance(man["runtime_seconds"], float) and man["started"] and man["ended"])
        blob = json.dumps(man)
        leaks = [s for s in ("Dropbox", "CloudStorage", "Chena", "Clearwater", "Drift Model",
                             "/Users/", os.path.expanduser("~")) if s in blob]
        check("manifest publishes no private or field-site paths", not leaks, f"leaked {leaks}")
        check("the interpreter is identified by virtualenv name, not an absolute path",
              man["versions"].get("virtualenv") and "python_executable" not in man["versions"],
              f"virtualenv={man['versions'].get('virtualenv')}")
        # and the sanitiser really does reduce a private .vsd argument to a safe key
        sanitised = artifacts.safe_repro_command(
            ["xdoc_objectives.py", "--vsd",
             "/Users/someone/Dropbox/Drift Model Project/2015-09-04-1 Clearwater.vsd"])
        check("a private document argument is reduced to a safe document key",
              "<doc:2015-09-04-1 Clearwater>" in sanitised and "Dropbox" not in sanitised,
              sanitised)

        # ------------------------------------------------------------ 2. pool-only cannot alias
        print(f"\n[2] POOL-ONLY run gets a DIFFERENT name and cannot overwrite the full artifact")
        W2 = writer(tmp, ["pool"])
        finish(W2, ["pool"])
        p_pool = W2.write({"documents": {"pool": {"mae": 2.0}}})
        check("pool-only run is named xdoc_objectives_pool.json",
              os.path.basename(p_pool) == "xdoc_objectives_pool.json", os.path.basename(p_pool))
        check("the two artifacts are different files", p_pool != p_full)
        check("the full artifact is untouched, byte for byte",
              open(p_full, "rb").read() == full_bytes)
        pa = json.load(open(p_pool))
        check("the pool-only manifest scope is 'pool', not 'full'",
              pa["manifest"]["document_scope"] == "pool")
        check("the pool-only artifact is still marked complete for its own scope",
              pa["manifest"]["complete"] is True
              and pa["manifest"]["requested_documents"] == ["pool"])

        # ------------------------------------------------------------ 3. interruption
        print(f"\n[3] SIMULATED INTERRUPTION leaves the prior full artifact byte-identical")
        before = open(p_full, "rb").read()
        W3 = writer(tmp, ALL_DOCS)
        finish(W3, ALL_DOCS)

        class Unserialisable:
            pass
        try:
            # artifacts._json_default falls through to float() and raises on an arbitrary object,
            # which is exactly the "payload could not be serialised" interruption case.
            W3.write({"documents": Unserialisable()})
            check("a non-serialisable payload raises rather than writing", False)
        except Exception:                                                    # noqa: BLE001
            check("a non-serialisable payload raises rather than writing", True)
        check("the full artifact is byte-identical after the failed write",
              open(p_full, "rb").read() == before)
        leftovers = [f for f in os.listdir(tmp) if f.startswith(".tmp-")]
        check("no temporary files are left behind", not leftovers, f"{leftovers}")
        # a genuine mid-run kill: nothing was written at all, so the old artifact still stands
        W3b = writer(tmp, ALL_DOCS)
        W3b.document_started("pool", sha256="0" * 64)
        check("a run killed before write() leaves the full artifact in place",
              open(p_full, "rb").read() == before)

        # ------------------------------------------------------------ 4. failed document
        print(f"\n[4] A FAILED document produces complete: false under a partial name")
        W4 = writer(tmp, ALL_DOCS)
        finish(W4, ["pool", "8mm"])
        W4.document_failed("mid", "document file not found")
        p4 = W4.write({"documents": {"pool": {}, "8mm": {}}})
        a4 = json.load(open(p4))
        check("the artifact is marked incomplete", a4["manifest"]["complete"] is False)
        check("it is named as partial and does NOT take the full name",
              os.path.basename(p4) == "xdoc_objectives_full_partial.json"
              and os.path.basename(p4) != "xdoc_objectives_full.json", os.path.basename(p4))
        check("the completed full artifact is still byte-identical",
              open(p_full, "rb").read() == before)
        check("the failure reason is recorded",
              a4["manifest"]["failed_documents"] == {"mid": "document file not found"})
        check("completed_documents lists only what really finished",
              sorted(a4["manifest"]["completed_documents"]) == ["8mm", "pool"])
        # a document that simply never completed (no explicit failure) is also incomplete
        W4b = writer(tmp, ALL_DOCS)
        finish(W4b, ["pool"])
        check("a document that never called document_completed makes the run incomplete",
              W4b.is_complete() is False)
        # an unknown document key must not silently shrink the scope into a 'full' claim
        W4c = writer(tmp, ["pool", "8mm", "mid", "typo"])
        finish(W4c, ALL_DOCS)
        check("an unknown requested document key forces incomplete",
              W4c.is_complete() is False and W4c.manifest()["unknown_documents_requested"] == ["typo"])

        # ------------------------------------------------------------ 5. filename agrees with manifest
        print(f"\n[5] The SCOPE IN THE FILENAME agrees with the manifest")
        for docs, expect in ((["pool"], "pool"), (["8mm"], "8mm"), (["mid"], "mid"),
                             (["pool", "8mm"], "pool-8mm"), (["8mm", "pool"], "pool-8mm"),
                             (ALL_DOCS, "full"), (["mid", "pool", "8mm"], "full")):
            Wx = writer(tmp, docs)
            finish(Wx, [d for d in ALL_DOCS if d in docs])
            px = Wx.write({"documents": {}})
            mx = json.load(open(px))["manifest"]
            nm = os.path.basename(px)
            check(f"scope {docs} -> {expect}",
                  mx["document_scope"] == expect and nm == f"xdoc_objectives_{expect}.json",
                  f"file {nm}, manifest {mx['document_scope']}")
        check("scope order is deterministic regardless of argument order",
              artifacts.scope_suffix(["8mm", "pool"], ALL_DOCS)
              == artifacts.scope_suffix(["pool", "8mm"], ALL_DOCS) == "pool-8mm")
        # candidate scope must also be visible and honest
        Wc = writer(tmp, ["pool"])
        finish(Wc, ["pool"], cands=["stored", "B/M0"])
        mc = Wc.manifest()
        check("a reduced candidate set is reported as such",
              mc["candidate_scope_complete"]["pool"] is False
              and sorted(mc["completed_candidates"]["pool"]) == ["B/M0", "stored"],
              f"scope_complete={mc['candidate_scope_complete']} "
              f"completed={mc['completed_candidates']}")
        check("requested candidates are recorded in full even when fewer completed",
              mc["requested_candidates"] == CANDS)

        # ------------------------------------------------------------ 6. no stale records survive
        print(f"\n[6] STALE candidate records cannot survive from a previous run")
        Ws = writer(tmp, ["pool"], analysis="stale_test")
        finish(Ws, ["pool"])
        p_a = Ws.write({"documents": {"pool": {"cands": CANDS}}})
        first = json.load(open(p_a))
        check("first run recorded all seven candidates",
              len(first["manifest"]["fit_validity"]["pool"]["Left Camera"]) == 7)
        # second run over the SAME name with fewer candidates -- the writer is a fresh object each
        # run and never merges, so nothing from the first run can leak into the second
        Ws2 = artifacts.ArtifactWriter(
            analysis="stale_test", script="xdoc_objectives.py", outdir=tmp,
            requested_documents=["pool"], all_documents=ALL_DOCS,
            requested_candidates=["stored", "B/M0"], source_files=["artifacts.py"])
        finish(Ws2, ["pool"], cands=["stored", "B/M0"])
        p_b = Ws2.write({"documents": {"pool": {"cands": ["stored", "B/M0"]}}})
        second = json.load(open(p_b))
        check("the rewritten artifact is a full replacement, not a merge",
              p_a == p_b
              and sorted(second["manifest"]["fit_validity"]["pool"]["Left Camera"])
              == ["B/M0", "stored"],
              f"{sorted(second['manifest']['fit_validity']['pool']['Left Camera'])}")
        check("no candidate from the first run remains in the results either",
              second["results"]["documents"]["pool"]["cands"] == ["stored", "B/M0"])
        check("the manifest's requested_candidates reflects THIS run, not the last one",
              second["manifest"]["requested_candidates"] == ["stored", "B/M0"])

        # ------------------------------------------------------------ 7. write_embedded
        print(f"\n[7] write_embedded preserves the {'{clip: ...}'} shape its readers expect")
        We = writer(tmp, ALL_DOCS, analysis="obj_pd_closure")
        finish(We, ALL_DOCS)
        pe = We.write_embedded({"Left Camera": {"weighting": {}}, "Right Camera": {}},
                               "obj_pd_closure.json")
        ae = json.load(open(pe))
        check("a complete run keeps the canonical name readers use",
              os.path.basename(pe) == "obj_pd_closure.json")
        check("top-level clip keys are preserved for existing readers",
              "Left Camera" in ae and "Right Camera" in ae)
        check("the manifest rides along under _manifest",
              ae["_manifest"]["complete"] is True)
        We2 = writer(tmp, ["pool"], analysis="obj_pd_closure")
        finish(We2, ["pool"])
        We2.document_failed("pool", "simulated failure")
        pe2 = We2.write_embedded({"Left Camera": {}}, "obj_pd_closure.json")
        check("an incomplete run does NOT take the canonical name",
              os.path.basename(pe2) != "obj_pd_closure.json", os.path.basename(pe2))
        check("the canonical artifact survives the incomplete run",
              json.load(open(pe))["_manifest"]["complete"] is True)

        print("\n" + "=" * 100)
        print(f"  {len(PASS)} passed, {len(FAIL)} FAILED")
        for f in FAIL:
            print(f"    FAILED: {f}")
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                        # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
