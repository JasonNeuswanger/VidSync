#!/usr/bin/env python3
"""Build a provenance SIDECAR for a LEGACY SD-D artifact, from durable independent evidence only.

WHY A SIDECAR. `analysis-output/addendum-2026-07-29/sd_real_full.json` is an established calibration
artifact. It records no observation view, no frame, no coordinate convention and no point-set hash,
because it predates the `sdprov` contract. Editing it to add those fields would change an authoritative
result file and would also be the wrong shape of fix: the added fields would be assertions written after
the fact by a different process. So the artifact is left BYTE-UNTOUCHED and its provenance is supplied
alongside it, in a manifest keyed by the artifact's exact SHA-256.

WHAT MAY GO IN. Only facts with durable, independent evidence. Concretely, per field:

  artifact_sha256            the bytes of the artifact, hashed here.
  doc_key, doc_sha256        the artifact's recorded camera identity, CROSS-CHECKED by recomputing the
  clip, cal_pk, clip_pk      document's SHA-256 and reloading its bound calibrations from the document.
  view_id                    NOT copied from the artifact -- it is not there. Derived from the producer's
                             own selection rule (`sd_real.build`: `D = Dind if lat_ok else Dline`,
                             pinned by the code fingerprint below) applied to the outcome the artifact
                             recorded (`lattice_valid`), and then CONFIRMED by requiring the
                             independently rebuilt view's observation and line counts to equal the
                             counts the artifact recorded. A disagreement aborts.
  n_obs, n_lines, n_captures rebuilt from the documents, and required to equal the artifact's.
  pointset_* hashes          computed from the rebuilt view. Nothing in the artifact to copy.
  frame                      `lattice.FRAME_W/FRAME_H`, confirmed against a RAW sqlite read of
                             min/max ZSCREENX/ZSCREENY (independent of lattice.load_captures).
  coordinate_convention      `sdprov.COORDINATE_CONVENTION`, a code-verifiable statement about the
                             reader that the producer code fingerprint pins.
  model_parameterization     derived from `objectives.MODELS`.
  producer_revision          the artifact manifest's own `git` block (commit, branch, dirty flag).
  producer_code_fingerprint  the artifact manifest's own `source_file_sha256` map -- per-file content
                             hashes recorded AT RUN TIME by the producing process. This is what makes the
                             dirty producing worktree (`dirty: true, n_dirty_paths: 172`) verifiable.
  parameter_sha256           hashed from the artifact's stored theta14.
  status                     RECOMPUTED with `fitstatus.camera_status` from the artifact's stored
                             optimizer, inverse-audit and frozen-gate numbers. Never copied as a claim.

If any required field cannot be established this script writes NOTHING and exits non-zero, so explicit
reuse then fails closed with an unverifiable-provenance error rather than being handed a guess.

NO OPTIMIZER. Every fitting entry point is tripwired before anything is read; this script builds
observation views and hashes them and never fits.

Writes <artifact>.provenance.json. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import os
import sqlite3
import sys
import time

import fitstatus as FS
import harness_import
import sdprov as SP

harness_import.ensure_path()

OB = harness_import.load("objectives")
LT = harness_import.load("lattice")
DS = harness_import.load("downstream")
SFmod = harness_import.load("sd_fast")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"

# The three established documents, keyed exactly as sd_real.py keys them.
DOCS = {
    "pool": os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                             "2012-01-31_PoolTest_2026_Reanalysis.vsd"),
    "8mm": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"),
    "mid": os.path.join(DM, "2015-06-22-1 Clearwater.vsd"),
}

# The producer's view-selection rule, quoted from sd_real.py so the derivation is auditable. The code
# fingerprint recorded in every sidecar record is what pins that this is the rule that ran.
PRODUCER_VIEW_RULE = ("sd_real.build: Dind = OB.Dataset(caps, require_indexed=True, min_inc=2, "
                      "kappa=3.0); lat_ok = Dind.n >= 20 and all(index_contradictions == 0); "
                      "D = Dind if lat_ok else OB.Dataset(caps, require_indexed=False, min_inc=1, "
                      "kappa=3.0). The artifact records the outcome as `lattice_valid`.")


class OptimizerCallForbidden(RuntimeError):
    pass


def install_tripwire():
    attempts = []

    def trip(name):
        def f(*a, **k):
            attempts.append(name)
            raise OptimizerCallForbidden(f"{name} was called while building a provenance sidecar")
        return f

    OB.fit = trip("objectives.fit")
    OB.PDExact.fit = trip("objectives.PDExact.fit")
    if hasattr(OB, "profile_H"):
        OB.profile_H = trip("objectives.profile_H")
    SFmod.solve = trip("sd_fast.solve")
    SFmod.fit_sd = trip("sd_fast.fit_sd")
    if hasattr(SFmod, "solve_staged"):
        SFmod.solve_staged = trip("sd_fast.solve_staged")
    return attempts


def raw_screen_bounds(vsd, clip):
    """min/max of the stored screen coordinates, read straight from sqlite.

    Independent of `lattice.load_captures`, so it is real evidence for the frame rather than a restatement
    of what the reader produced.
    """
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    try:
        pk = db.execute("SELECT c.Z_PK FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v "
                        "ON v.Z_PK = c.ZVIDEOCLIP WHERE v.ZCLIPNAME = ?", (clip,)).fetchone()[0]
        row = db.execute(
            "SELECT MIN(p.ZSCREENX), MAX(p.ZSCREENX), MIN(p.ZSCREENY), MAX(p.ZSCREENY) "
            "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK "
            "WHERE l.ZCALIBRATION = ?", (pk,)).fetchone()
    finally:
        db.close()
    return {"x_min": row[0], "x_max": row[1], "y_min": row[2], "y_max": row[3]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact",
                    default=os.path.join(OUT, "addendum-2026-07-29", "sd_real_full.json"))
    ap.add_argument("--out", default=None, help="defaults to <artifact>.provenance.json")
    ap.add_argument("--dry-run", action="store_true", help="report and validate, write nothing")
    args = ap.parse_args()
    attempts = install_tripwire()

    art_path = args.artifact
    out_path = args.out or (art_path + ".provenance.json")
    art_sha = SP.file_sha256(art_path)
    with open(art_path) as fh:
        art = json.load(fh)
    man, cams = art.get("manifest", {}), art.get("results", {}).get("cameras", {})

    print("=" * 112)
    print("LEGACY SD-D PROVENANCE SIDECAR BUILD -- durable independent evidence only, no optimizer")
    print("=" * 112)
    print(f"  artifact           {os.path.basename(art_path)}")
    print(f"  artifact sha256    {art_sha}")
    print(f"  producing analysis {man.get('analysis')} / {man.get('script')}")
    print(f"  reproduction       {man.get('reproduction_command')}")
    print(f"  producer git       {json.dumps(man.get('git'))}")

    # ---- producer code fingerprint, from the producing manifest's own per-file hashes
    fp = SP.code_fingerprint(man.get("source_file_sha256") or {})
    if not fp["available"]:
        print(f"\n  ABORT: the producing manifest records no hash for {fp['missing_files']}, so the "
              f"producing implementation cannot be fingerprinted. Nothing written.")
        return 2
    print(f"  producer code      {fp['combined_sha256']}  over {fp['required_files']}")
    git = man.get("git") or {}
    if not git.get("commit"):
        print("\n  ABORT: the producing manifest records no commit. Nothing written.")
        return 2
    if "dirty" not in git:
        print("\n  ABORT: the producing manifest does not say whether its worktree was dirty, so the "
              "commit cannot be interpreted. Nothing written.")
        return 2
    revision = {"commit": git["commit"], "branch": git.get("branch"), "dirty": bool(git.get("dirty")),
                "n_dirty_paths": git.get("n_dirty_paths"),
                "note": "the producing worktree was dirty, so the commit alone does not determine the "
                        "code that ran; producer_code_fingerprint does"}

    records, problems = [], []
    print(f"\n  {'camera':14} {'view (derived)':24} {'nObs':>5} {'nLin':>5} {'nCap':>4} "
          f"{'artObs':>6} {'artLin':>6}  pointset sha256")
    for cid in sorted(cams):
        rec = cams[cid]
        doc_key, clip = rec.get("document"), rec.get("clip")
        vsd = DOCS.get(doc_key)
        if not vsd or not os.path.exists(vsd):
            problems.append(f"{cid}: document {doc_key!r} unavailable, so its inputs cannot be "
                            f"reconstructed independently")
            continue
        # independent document identity
        doc_sha = DS.document_sha256(vsd)
        if doc_sha != rec.get("doc_sha256"):
            problems.append(f"{cid}: recomputed document SHA-256 {doc_sha[:12]} != the artifact's "
                            f"{str(rec.get('doc_sha256'))[:12]}")
            continue
        cals = DS.load_bound_cals(vsd)
        if clip not in cals:
            problems.append(f"{cid}: clip {clip!r} is not in the document")
            continue
        ident = cals[clip]["identity"]
        # view identity DERIVED from the producer's rule and the recorded outcome, then CONFIRMED
        lat_ok = rec.get("lattice_valid")
        if lat_ok is None:
            problems.append(f"{cid}: the artifact records no `lattice_valid`, so the producer's view "
                            f"branch cannot be established from durable evidence")
            continue
        view_id = "min_inc2_indexed" if bool(lat_ok) else "min_inc1_all_incidences"
        caps = LT.load_captures(vsd, clip)
        dig = SP.pointset_digest(SP.build_view(OB, caps, view_id))
        if (int(dig["n_obs"]) != int(rec.get("n_obs", -1))
                or int(dig["n_lines"]) != int(rec.get("n_lines", -1))
                or int(dig["n_captures"]) != int(rec.get("n_captures", -1))):
            problems.append(
                f"{cid}: the derived view {view_id} rebuilds to "
                f"{dig['n_obs']}/{dig['n_lines']}/{dig['n_captures']} observations/lines/captures but "
                f"the artifact recorded {rec.get('n_obs')}/{rec.get('n_lines')}/"
                f"{rec.get('n_captures')}; the view derivation is NOT confirmed")
            continue
        # frame, confirmed against a raw sqlite read
        b = raw_screen_bounds(vsd, clip)
        frame = [float(LT.FRAME_W), float(LT.FRAME_H)]
        if not (b["x_min"] is not None and 0.0 <= b["x_min"] and b["x_max"] <= frame[0]
                and 0.0 <= b["y_min"] and b["y_max"] <= frame[1]):
            problems.append(f"{cid}: raw stored screen coordinates {b} are not inside the "
                            f"{frame[0]:.0f}x{frame[1]:.0f} frame, so the frame is not confirmed")
            continue
        print(f"  {cid:14} {view_id:24} {dig['n_obs']:5d} {dig['n_lines']:5d} {dig['n_captures']:4d} "
              f"{rec.get('n_obs'):6d} {rec.get('n_lines'):6d}  {dig['pointset_sha256'][:24]}")
        for model in ("M0", "M1"):
            cand = f"SD-D/{model}"
            f = (rec.get("fits") or {}).get(cand)
            if f is None:
                problems.append(f"{cid}/{cand}: absent from the artifact")
                continue
            th = f.get("theta14")
            inv = f.get("inverse") or {}
            st = FS.camera_status(
                cand, f"{doc_key}/{clip}",
                optimizer={"status": f.get("status"), "nfev": f.get("nfev"), "max_nfev": 300,
                           "termination": f.get("termination"), "loss": f.get("loss"),
                           "optimality": f.get("optimality")},
                adm_v2=f.get("adm_v2"),
                inverse={"shipped_failures": inv.get("shipped_failures"),
                         "max_roundtrip_px": inv.get("max_roundtrip_px")},
                theta14=th)
            records.append({
                "schema_version": SP.SCHEMA_VERSION,
                "doc_key": doc_key, "doc_sha256": doc_sha,
                "clip": clip, "cal_pk": int(ident.cal_pk), "clip_pk": int(ident.clip_pk),
                "candidate": cand, "model": model,
                "view_id": view_id,
                "view_selector": SP.VIEWS[view_id]["predicate"],
                "view_selector_id": SP.VIEWS[view_id]["view_selector_id"],
                "view_selector_version": SP.VIEW_SELECTOR_VERSION,
                "n_obs": dig["n_obs"], "n_lines": dig["n_lines"], "n_captures": dig["n_captures"],
                "pointset_hash_version": dig["pointset_hash_version"],
                "pointset_sha256": dig["pointset_sha256"],
                "ordered_pointset_sha256": dig["ordered_pointset_sha256"],
                "lineset_sha256": dig["lineset_sha256"],
                "frame": frame,
                "coordinate_convention": SP.COORDINATE_CONVENTION,
                "model_parameterization": SP.model_parameterization(OB, model),
                "producer_revision": revision,
                "producer_code_fingerprint": fp,
                "parameter_sha256": SP.parameter_sha256(th),
                "status": {k: st[k] for k in SP.REQUIRED_STATUS_FIELDS},
                "status_evidence": {"recomputed_by": "fitstatus.camera_status from the artifact's own "
                                                     "optimizer, inverse-audit and frozen-gate records",
                                    "diagnostic_reasons": st["diagnostic_reasons"],
                                    "source_max_nfev": 300},
                "evidence": {
                    "view_id_from": PRODUCER_VIEW_RULE,
                    "view_id_confirmed_by": "independently rebuilding the view from the document and "
                                            "requiring its observation, line and capture counts to "
                                            "equal the counts the artifact recorded",
                    "counts_and_pointset_from": "rebuilt from the document via lattice.load_captures "
                                                "and objectives.Dataset at this view's kwargs",
                    "frame_from": f"lattice.FRAME_W/FRAME_H, confirmed against a raw sqlite read of "
                                  f"min/max ZSCREENX/ZSCREENY: {b}",
                    "coordinate_convention_from": "lattice.load_captures selects ZSCREENX/ZSCREENY and "
                                                  "applies no transform; pinned by "
                                                  "producer_code_fingerprint",
                    "producer_revision_from": "the producing artifact manifest's own `git` block",
                    "producer_code_fingerprint_from": "the producing artifact manifest's own "
                                                      "`source_file_sha256`, recorded at run time",
                    "parameter_sha256_from": "the artifact's stored theta14",
                    "document_identity_confirmed_by": "recomputing downstream.document_sha256 and "
                                                      "reloading the bound calibration identity",
                },
            })

    if problems:
        print(f"\n  ABORT: {len(problems)} field(s) could not be established from durable independent "
              f"evidence. NOTHING has been written, so explicit reuse fails closed:")
        for p in problems:
            print(f"    - {p}")
        return 3
    if attempts:
        print(f"\n  ABORT: an optimizer entry point was called: {attempts}")
        return 4

    doc = {"schema_version": SP.SIDECAR_SCHEMA_VERSION,
           "artifact_sha256": art_sha,
           "artifact_basename": os.path.basename(art_path),
           "built_by": "sd_sidecar_build.py",
           "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "builder_code_fingerprint": SP.code_fingerprint_now(),
           "policy": ("the described artifact is NEVER modified; this sidecar supplies the provenance "
                      "contract it predates, and every field is populated only from durable independent "
                      "evidence (the producing run manifest, the documents themselves, the recorded "
                      "repository state, or a recomputation from the artifact's stored numbers)"),
           "records": records}
    if args.dry_run:
        print(f"\n  DRY RUN: {len(records)} complete record(s) validated; nothing written.")
        return 0
    tmp = out_path + ".part"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1)
    os.replace(tmp, out_path)
    after = SP.file_sha256(art_path)
    print(f"\n  wrote {os.path.basename(out_path)} with {len(records)} record(s)")
    print(f"  sidecar sha256     {SP.file_sha256(out_path)}")
    print(f"  artifact sha256 AFTER writing the sidecar: {after}")
    if after != art_sha:
        print("  *** THE ARTIFACT CHANGED. Stop and investigate. ***")
        return 5
    print("  artifact is byte-unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
