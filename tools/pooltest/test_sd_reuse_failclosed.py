#!/usr/bin/env python3
"""Fail-closed tests for explicit SD-D artifact reuse, and for status/ranking eligibility.

WHAT IS BEING PROTECTED.

  1. `--sd-from` must never silently refit. The first version of the loader returned `None` for an
     unverifiable record and the caller quietly refit, producing a table with mixed provenance and no
     marker. `verify_sd_records` + `preflight_sd_reuse` now demand a verified record for every requested
     document/camera/model, collect every failure into one diagnostic, and abort before any optimizer is
     constructed. Refitting an ABSENT map requires the separate `--sd-refit-missing`; a present-but-
     mismatched or malformed record can never be refit around.
  2. An optimizer-converged but empirically INADMISSIBLE map stays diagnostic-only. pool/Right PD-D/M1 is
     the real case: it converged, inverts cleanly, and passes the weaker production gate, but fails the
     frozen `admissibility_v2` gate, so it must be excluded from every accepted ranking while remaining
     visible in labelled diagnostic rows.

UPDATED 2026-07-29 for the `sdprov` provenance contract (revision 3). Two things changed here, both
deliberately:

  * a request is now an `sdprov.reuse_request` naming the EXACT expected observation view and carrying the
    independently reconstructed identity of that view, so the fixtures carry complete provenance records
    instead of bare counts; and
  * the check that previously asserted "a DIFFERENT but legitimate view verifies and is labelled" is
    INVERTED. That behaviour was the hole: a valid map for the other recognized view was accepted for a
    caller that was about to use it as this view's map. It must now fail, and section [4] proves it does.

The exact-identity matrix -- canonical point-set hashing, producer-code fingerprinting, legacy sidecars --
lives in `test_sd_provenance.py`. This file keeps the fail-closed and ranking behaviour it always tested.

No optimizer is called anywhere in this file: the verifier is a pure function exercised with fixtures,
and the fitting entry points are replaced with tripwires that fail the test if anything touches them.

Run with ~/.venvs/vidsync/bin/python.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

import fitstatus as FS
import harness_import
import sdprov as SP

harness_import.ensure_path()
import xdoc_objectives as XD                                                  # noqa: E402

OB = harness_import.load("objectives")
SFmod = harness_import.load("sd_fast")

PASS, FAIL = [], []
HERE = os.path.dirname(os.path.abspath(__file__))
SHA = "a" * 64
SHA2 = "b" * 64
CLIPS = ("Left Camera", "Right Camera")
FITCALLS = []


def install_tripwire():
    def trip(name):
        def f(*a, **k):
            FITCALLS.append(name)
            raise AssertionError(f"{name} must not be called by these tests")
        return f
    OB.fit = trip("objectives.fit")
    OB.PDExact.fit = trip("objectives.PDExact.fit")
    SFmod.solve = trip("sd_fast.solve")
    SFmod.fit_sd = trip("sd_fast.fit_sd")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def theta(seed):
    rg = np.random.default_rng(seed)
    t = np.zeros(14)
    t[0], t[1] = 960.0 + rg.normal(0, 4), 540.0 + rg.normal(0, 4)
    t[2] = -1e-8
    t[13] = 0.004 * rg.normal()
    return t


# ---- the independently reconstructed identity of each camera's two observation views -------------
# The point-set hashes are fixtures, distinct per (camera, view): what matters here is that the
# verifier compares them, not what they hash. `test_sd_provenance.py` builds real ones from real
# observations and shows that two same-count views hash differently.
FRAME = [1920.0, 1080.0]
CODE_HASHES = {n: f"{i:064x}" for i, n in enumerate(SP.SD_PRODUCER_CODE_FILES, start=1)}
FP = SP.code_fingerprint(CODE_HASHES)
REVISION = {"commit": "c" * 40, "branch": "agent-dev", "dirty": True, "n_dirty_paths": 172}
STATUS_OK = {"optimizer_converged": True, "numerically_invertible": True,
             "empirically_admissible": True, "eligible_for_ranking": True}
ADM_OK = {"safe": True, "physically_plausible": True, "min_det": 1.0, "min_sigma": 1.0}
INV_OK = {"shipped_failures": 0, "max_roundtrip_px": 1e-13}
COUNTS = {("Left Camera", "min_inc2_indexed"): (309, 38, 1),
          ("Left Camera", "min_inc1_all_incidences"): (340, 41, 1),
          ("Right Camera", "min_inc2_indexed"): (318, 39, 1),
          ("Right Camera", "min_inc1_all_incidences"): (365, 43, 1)}


def expect(clip, view, model="M0"):
    # An unknown clip (the Left/Right crossover fixture uses "Middle Camera") gets a distinct identity
    # rather than an exception, so the crossover fails on the camera name as intended.
    n_obs, n_lines, ncap = COUNTS.get((clip, view), (309, 38, 1))
    stem = f"{clip}|{view}"
    return {"pointset_hash_version": SP.POINTSET_HASH_VERSION,
            "pointset_sha256": hashlib.sha256(f"points|{stem}".encode()).hexdigest(),
            "ordered_pointset_sha256": hashlib.sha256(f"ordered|{stem}".encode()).hexdigest(),
            "n_obs": n_obs, "n_lines": n_lines, "n_captures": ncap,
            "view_id": view, "view_selector": SP.VIEWS[view]["predicate"],
            "view_selector_id": SP.VIEWS[view]["view_selector_id"],
            "view_selector_version": SP.VIEW_SELECTOR_VERSION,
            "frame": list(FRAME), "coordinate_convention": SP.COORDINATE_CONVENTION,
            "model_parameterization": SP.model_parameterization(OB, model)}


def provenance(clip, view, model, th, sha=SHA, doc_key="mid", **over):
    exp = expect(clip, view, model)
    rec = {"schema_version": SP.SCHEMA_VERSION, "doc_key": doc_key, "doc_sha256": sha,
           "clip": clip, "cal_pk": 1, "clip_pk": 2,
           "candidate": f"SD-D/{model}", "model": model,
           "producer_revision": dict(REVISION), "producer_code_fingerprint": copy.deepcopy(FP),
           "parameter_sha256": SP.parameter_sha256(th), "status": dict(STATUS_OK)}
    rec.update({k: exp[k] for k in
                ("view_id", "view_selector", "view_selector_id", "view_selector_version",
                 "n_obs", "n_lines", "n_captures", "pointset_hash_version", "pointset_sha256",
                 "ordered_pointset_sha256", "frame", "coordinate_convention",
                 "model_parameterization")})
    rec.update(over)
    return rec


def requests(view_by_clip=None, sha=SHA, doc_key="mid"):
    """The four requested maps: two cameras x two models, each naming ONE expected view."""
    vb = view_by_clip or {c: "min_inc2_indexed" for c in CLIPS}
    out = []
    for c in CLIPS:
        for m in ("M0", "M1"):
            out.append(SP.reuse_request(doc_key, sha, c, f"SD-D/{m}", vb[c],
                                        expect(c, vb[c], m), cal_pk=1, clip_pk=2))
    return out


def artifact(cams, path, analysis="sd_real", manifest_hashes=None):
    """cams: [(cam_id, sha, clip, view_or_None, {model: (theta, completed)}, prov_overrides)]

    `view_or_None` is the view the embedded provenance CLAIMS. None omits provenance entirely, which is
    what a legacy artifact looks like.
    """
    R = {"cameras": {}}
    for cid, sha, clip, view, fits, over in cams:
        n_obs, n_lines, ncap = COUNTS.get((clip, view or "min_inc2_indexed"), (309, 38, 1))
        R["cameras"][cid] = {
            "document": cid.split("/")[0], "clip": clip, "doc_sha256": sha,
            "n_obs": n_obs, "n_lines": n_lines, "n_captures": ncap, "lattice_valid": True,
            "fits": {}}
        for m, (th, ok) in fits.items():
            f = {"theta14": list(map(float, th)), "loss": 1.0, "status": 2, "nfev": 7,
                 "eta": float(th[13]) if len(th) > 13 else None, "completed": ok,
                 "termination": "ftol", "init": "staged",
                 "adm_v2": dict(ADM_OK), "inverse": dict(INV_OK)}
            if view is not None:
                f["provenance"] = provenance(clip, view, m, th, sha=sha, **over)
            R["cameras"][cid]["fits"][f"SD-D/{m}"] = f
    with open(path, "w") as fh:
        json.dump({"manifest": {"analysis": analysis, "script": "sd_real.py",
                                "source_file_sha256": manifest_hashes
                                if manifest_hashes is not None else dict(CODE_HASHES),
                                "git": dict(REVISION), "started": "t"}, "results": R}, fh)
    return XD.load_sd_source(path, sidecar_paths=[])


V2 = "min_inc2_indexed"
V1 = "min_inc1_all_incidences"
REQ = requests()


def main():
    print("=" * 100)
    print("SD-D EXPLICIT-REUSE FAIL-CLOSED TESTS")
    print("=" * 100)
    install_tripwire()
    tmp = tempfile.mkdtemp(prefix="sdfc")

    print("\n[1] A complete, matching artifact verifies and is reused")
    good = artifact([("mid/Left", SHA, "Left Camera", V2,
                      {"M0": (theta(1), True), "M1": (theta(2), True)}, {}),
                     ("mid/Right", SHA, "Right Camera", V2,
                      {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                    os.path.join(tmp, "good.json"))
    usable, failures, refit = XD.verify_sd_records(good, REQ)
    check("all four requested maps verify", len(usable) == 4 and not failures and not refit,
          f"{failures}")
    check("each records WHICH view was REQUESTED, rather than one matched by count",
          all(v["view_verified"] == V2 for v in usable.values()),
          f"{[v.get('view_verified') for v in usable.values()]}")
    check("each is bound to the artifact's own content hash",
          all(v["artifact_sha256"] == good["artifact_sha256"] for v in usable.values()))
    check("each carries the producing implementation's code fingerprint",
          all(v["producer_code_sha256"] == FP["combined_sha256"] for v in usable.values()))

    print("\n[2] A MISSING map fails, and the fitting code is never touched")
    part = artifact([("mid/Left", SHA, "Left Camera", V2, {"M0": (theta(1), True)}, {}),
                     ("mid/Right", SHA, "Right Camera", V2,
                      {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                    os.path.join(tmp, "partial.json"))
    u2, f2, r2 = XD.verify_sd_records(part, REQ)
    check("the absent map is reported as a failure, not silently refit", len(f2) == 1 and not r2,
          f"{f2}")
    check("the error names the document, camera and model", "SD-D/M1" in f2[0] and "Left" in f2[0])
    check("the three present maps still verify", len(u2) == 3)
    check("no fitting entry point was called", not FITCALLS, f"{FITCALLS}")

    print("\n[3] A document / camera / model mismatch fails")
    wrongdoc = artifact([("mid/Left", SHA2, "Left Camera", V2,
                          {"M0": (theta(1), True), "M1": (theta(2), True)}, {}),
                         ("mid/Right", SHA2, "Right Camera", V2,
                          {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                        os.path.join(tmp, "wrongdoc.json"))
    _, f3, _ = XD.verify_sd_records(wrongdoc, REQ)
    check("a wrong document hash fails all four, never substituting another document's map",
          len(f3) == 4, f"{len(f3)} failures")
    swapped = artifact([("mid/Left", SHA, "Middle Camera", V2,
                         {"M0": (theta(1), True), "M1": (theta(2), True)}, {}),
                        ("mid/Right", SHA, "Right Camera", V2,
                         {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                       os.path.join(tmp, "swapped.json"))
    _, f3b, _ = XD.verify_sd_records(swapped, REQ)
    check("a wrong clip name fails, so a Left/Right crossover cannot happen", len(f3b) == 2,
          f"{f3b}")

    print("\n[4] The WRONG observation view now FAILS -- this is the revision-3 inversion")
    mixed = artifact([("mid/Left", SHA, "Left Camera", V1,          # valid map, but the OTHER view
                       {"M0": (theta(1), True), "M1": (theta(2), True)}, {}),
                      ("mid/Right", SHA, "Right Camera", V2,
                       {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                     os.path.join(tmp, "mixed.json"))
    u5, f5, _ = XD.verify_sd_records(mixed, REQ)                    # requests min_inc=2 everywhere
    check("a DIFFERENT but legitimate view is REJECTED, not accepted as the requested one",
          len(f5) == 2 and len(u5) == 2, f"{f5}")
    check("and the error names both the offered and the requested view",
          all(V1 in m and V2 in m and "is not the requested view" in m for m in f5), f"{f5[:1]}")
    check("the error also says the offered view is RECOGNIZED, so this is not 'unknown view'",
          all("a recognized view, but not the one requested" in m for m in f5))
    u_sym, f_sym, _ = XD.verify_sd_records(mixed, requests({"Left Camera": V1,
                                                            "Right Camera": V1}))
    check("requesting min_inc=1 everywhere flips it -- Left's two verify, Right's two fail, so the "
          "check is symmetric and not a blanket rejection",
          len(u_sym) == 2 and len(f_sym) == 2
          and all(k[1] == "Left Camera" for k in u_sym), f"{f_sym}")
    pts = artifact([("mid/Left", SHA, "Left Camera", V2,
                     {"M0": (theta(1), True), "M1": (theta(2), True)},
                     {"pointset_sha256": "9" * 64}),
                    ("mid/Right", SHA, "Right Camera", V2,
                     {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                   os.path.join(tmp, "points.json"))
    _, f5b, _ = XD.verify_sd_records(pts, REQ)
    check("the RIGHT view with the WRONG point-set hash fails, at identical counts",
          len(f5b) == 2 and "SAME observation count, DIFFERENT point set" in f5b[0], f"{f5b[:1]}")
    nl = artifact([("mid/Left", SHA, "Left Camera", V2,
                    {"M0": (theta(1), True), "M1": (theta(2), True)}, {"n_lines": 41}),
                   ("mid/Right", SHA, "Right Camera", V2,
                    {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                  os.path.join(tmp, "nlines.json"))
    _, f5c, _ = XD.verify_sd_records(nl, REQ)
    check("a wrong line count fails", len(f5c) == 2 and "n_lines" in f5c[0], f"{f5c[:1]}")
    badframe = artifact([("mid/Left", SHA, "Left Camera", V2,
                          {"M0": (theta(1), True), "M1": (theta(2), True)},
                          {"frame": [1280.0, 720.0]}),
                         ("mid/Right", SHA, "Right Camera", V2,
                          {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                        os.path.join(tmp, "badframe.json"))
    _, f7, _ = XD.verify_sd_records(badframe, REQ)
    check("a declared frame that differs from the local frame fails", len(f7) == 2
          and "frame" in f7[0], f"{f7[:1]}")
    conv = artifact([("mid/Left", SHA, "Left Camera", V2,
                      {"M0": (theta(1), True), "M1": (theta(2), True)},
                      {"coordinate_convention": "normalized [-1,1], y up"}),
                     ("mid/Right", SHA, "Right Camera", V2,
                      {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                    os.path.join(tmp, "conv.json"))
    _, f8, _ = XD.verify_sd_records(conv, REQ)
    check("a declared coordinate convention that differs fails", len(f8) == 2
          and "coordinate_convention" in f8[0], f"{f8[:1]}")

    print("\n[5] Malformed, incomplete and DUPLICATE records fail")
    incomplete = artifact([("mid/Left", SHA, "Left Camera", V2,
                            {"M0": (theta(1), False), "M1": (theta(2), True)}, {}),
                           ("mid/Right", SHA, "Right Camera", V2,
                            {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                          os.path.join(tmp, "incomplete.json"))
    _, f9, r9 = XD.verify_sd_records(incomplete, REQ)
    check("a record not marked completed fails", len(f9) == 1 and "not marked completed" in f9[0],
          f"{f9}")
    check("and --sd-refit-missing does NOT rescue it (it is corruption, not a gap)",
          len(XD.verify_sd_records(incomplete, REQ, refit_missing=True)[1]) == 1)
    nan = artifact([("mid/Left", SHA, "Left Camera", V2,
                     {"M0": (np.full(14, np.nan), True), "M1": (theta(2), True)}, {}),
                    ("mid/Right", SHA, "Right Camera", V2,
                     {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                   os.path.join(tmp, "nan.json"))
    _, f10, _ = XD.verify_sd_records(nan, REQ)
    check("a non-finite theta fails", len(f10) == 1 and "non-finite" in f10[0], f"{f10}")
    short = artifact([("mid/Left", SHA, "Left Camera", V2,
                       {"M0": (np.zeros(13), True), "M1": (theta(2), True)}, {}),
                      ("mid/Right", SHA, "Right Camera", V2,
                       {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                     os.path.join(tmp, "short.json"))
    _, f11, _ = XD.verify_sd_records(short, REQ)
    check("a 13-entry theta fails", len(f11) == 1 and "13 entries" in f11[0], f"{f11}")
    dup = artifact([("mid/Left", SHA, "Left Camera", V2,
                     {"M0": (theta(1), True), "M1": (theta(2), True)}, {}),
                    ("mid/LeftAgain", SHA, "Left Camera", V2,
                     {"M0": (theta(5), True), "M1": (theta(6), True)}, {}),
                    ("mid/Right", SHA, "Right Camera", V2,
                     {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                   os.path.join(tmp, "dup.json"))
    _, f12, _ = XD.verify_sd_records(dup, REQ)
    check("two artifact entries claiming the same camera and model fail as DUPLICATE",
          any("DUPLICATE" in m for m in f12), f"{f12[:2]}")
    legacy = artifact([("mid/Left", SHA, "Left Camera", None,
                        {"M0": (theta(1), True), "M1": (theta(2), True)}, {}),
                       ("mid/Right", SHA, "Right Camera", None,
                        {"M0": (theta(3), True), "M1": (theta(4), True)}, {})],
                      os.path.join(tmp, "noprov.json"))
    _, f13, _ = XD.verify_sd_records(legacy, REQ)
    check("an artifact with NO provenance and no sidecar is unverifiable and fails all four",
          len(f13) == 4 and "no verified sidecar" in f13[0], f"{f13[:1]}")
    check("an analysis NAME is no longer accepted as producer identity",
          legacy["analysis"] == "sd_real" and len(f13) == 4)

    print("\n[6] Refit fallback happens ONLY with the separate explicit option")
    u14, f14, r14 = XD.verify_sd_records(part, REQ, refit_missing=True)
    check("with --sd-refit-missing an ABSENT map becomes a recorded refit permission",
          not f14 and len(r14) == 1 and len(u14) == 3, f"{f14} / {r14}")
    check("without it the same artifact is a hard failure",
          len(XD.verify_sd_records(part, REQ)[1]) == 1)
    check("preflight raises SystemExit(3) on an unverifiable artifact", _preflight_exits(part))
    check("preflight returns normally when everything verifies", _preflight_ok(good))
    check("no fitting entry point was called by any of the above", not FITCALLS, f"{FITCALLS}")

    print("\n[7] Reused parameters give identical deterministic map evaluations")
    LT = harness_import.load("lattice")
    probes = np.array([[20.0, 20.0], [1900.0, 1060.0], [960.0, 540.0], [733.0, 411.0]])
    th_src = theta(1)
    before = LT.U(probes, th_src).copy()
    rec = XD.sd_from_source(good, SHA, "Left Camera", "SD-D/M0")
    after = LT.U(probes, np.asarray(rec["theta14"], float))
    check("theta survives the artifact round trip bit-for-bit",
          np.array_equal(np.asarray(rec["theta14"], float), th_src))
    check("and the map at four deterministic probes is bit-identical",
          np.array_equal(before, after),
          f"max |delta| {float(np.abs(before - after).max()):.3e} px")

    print("\n[8] A converged but empirically INADMISSIBLE map stays diagnostic-only")
    opt = {"status": 2, "nfev": 74, "termination": "ftol", "loss": 368.529, "hit_nfev_cap": False}
    inv = {"shipped_failures": 0, "max_roundtrip_px": 8.6e-13}
    bad = FS.camera_status("PD-D/M1", "pool/Right Camera", optimizer=opt,
                           adm_v2={"safe": False, "physically_plausible": False, "min_det": 0.9298,
                                   "min_sigma": 0.9462, "expansion_ratio": 1.7157},
                           inverse=inv, production_gate_ok=True, theta14=theta(9))
    check("it is recorded as converged", bad["optimizer_converged"])
    check("it is recorded as numerically invertible", bad["numerically_invertible"])
    check("it is recorded as passing the weaker PRODUCTION gate", bad["production_gate_ok"] is True)
    check("it is recorded as failing the FROZEN empirical gate", not bad["empirically_admissible"])
    check("so it is NOT eligible for ranking and IS diagnostic-only",
          not bad["eligible_for_ranking"] and bad["diagnostic_only"])
    check("and the reason is explicit", any("admissibility_v2" in r for r in bad["diagnostic_reasons"]),
          f"{bad['diagnostic_reasons']}")
    ok_st = FS.camera_status("PD-D/M0", "pool/Right Camera", optimizer=opt,
                             adm_v2={"safe": True, "physically_plausible": True, "min_det": 1.0,
                                     "min_sigma": 1.0, "expansion_ratio": 1.7},
                             inverse=inv, production_gate_ok=True, theta14=theta(10))
    doc = {"PD-D/M1": FS.document_status("PD-D/M1", {"Left Camera": ok_st, "Right Camera": bad}),
           "PD-D/M0": FS.document_status("PD-D/M0", {"Left Camera": ok_st, "Right Camera": ok_st})}
    check("one inadmissible camera makes the whole document candidate diagnostic-only",
          not doc["PD-D/M1"]["eligible_for_ranking"]
          and doc["PD-D/M1"]["n_cameras_eligible"] == 1)
    rk = FS.rank({"stored": 0.75, "PD-D/M0": 0.6535, "PD-D/M1": 0.6575}, doc)
    check("the inadmissible map is EXCLUDED from the accepted ranking even though its metric is better "
          "than the winner's runner-up",
          [r["candidate"] for r in rk["accepted_ranking"]] == ["PD-D/M0"], f"{rk['accepted_ranking']}")
    check("it is RETAINED as a labelled diagnostic row with its reason",
          len(rk["diagnostic_only_rows"]) == 1
          and rk["diagnostic_only_rows"][0]["candidate"] == "PD-D/M1"
          and rk["diagnostic_only_rows"][0]["excluded_reason"])
    check("the stored anchor is reported separately, not ranked as a fitted candidate",
          rk["reference_anchor"]["candidate"] == "stored"
          and "stored" not in [r["candidate"] for r in rk["accepted_ranking"]])
    check("a capped fit is also excluded", not FS.camera_status(
        "SD-D/M0", "x", optimizer={"status": 0, "nfev": 1200, "max_nfev": 1200},
        adm_v2={"safe": True, "physically_plausible": True}, inverse=inv,
        theta14=theta(11))["eligible_for_ranking"])
    check("an inverse failure is also excluded", not FS.camera_status(
        "SD-D/M0", "x", optimizer=opt, adm_v2={"safe": True, "physically_plausible": True},
        inverse={"shipped_failures": 3, "max_roundtrip_px": 1e-13},
        theta14=theta(12))["eligible_for_ranking"])

    print("\n[9] CLI: contradictory options are rejected; the real regeneration calls no optimizer")
    r = subprocess.run([sys.executable, os.path.join(HERE, "xdoc_objectives.py"),
                        "--sd-refit-missing", "--docs", "mid"],
                       capture_output=True, text=True)
    check("--sd-refit-missing without --sd-from exits non-zero", r.returncode != 0,
          f"rc={r.returncode}")
    check("and says why", "meaningless without --sd-from" in (r.stderr + r.stdout))
    r2 = subprocess.run([sys.executable, os.path.join(HERE, "xdoc_objectives.py"),
                         "--sd-sidecar", "/tmp/nope.json", "--docs", "mid"],
                        capture_output=True, text=True)
    check("--sd-sidecar without --sd-from exits non-zero too", r2.returncode != 0,
          f"rc={r2.returncode}")
    check("and says why", "meaningless without --sd-from" in (r2.stderr + r2.stdout))
    regen = os.path.join(HERE, "analysis-output", "correction-2026-07-29",
                         "sd_report_regen_full.json")
    if os.path.exists(regen):
        with open(regen) as fh:
            got = json.load(fh)
        att = got["results"]["optimizer_calls_attempted"]
        check("the stored regeneration artifact records ZERO attempted optimizer calls", att == [],
              f"{att}")
        check("and it reports no consistency problems", got["results"]["problems"] == [],
              f"{got['results']['problems']}")
        check("its sensitivity matrix has exactly 8 found cells and none missing or duplicated",
              got["results"]["viewsens_found_cells"] == 8
              and got["results"]["viewsens_expected_cells"] == 8
              and not got["results"]["viewsens_missing_cells"]
              and not got["results"]["viewsens_duplicate_cells"])
        check("pool/Right PD-D/M1 is recorded as diagnostic-only in the regenerated status",
              got["results"]["camera_status"]["pool|Right Camera|PD-D/M1"]["diagnostic_only"] is True)
        check("and it appears in no accepted ranking",
              all("PD-D/M1" not in [x["candidate"] for x in v["accepted_ranking"]]
                  for k, v in got["results"]["known_length_rankings"].items()
                  if k.startswith("pool")))
    else:
        print("        regeneration artifact absent; run sd_report_regen.py first")

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED; fitting entry points called: {len(FITCALLS)}")
    for f in FAIL:
        print(f"    FAILED: {f}")
    return 1 if (FAIL or FITCALLS) else 0


def _preflight_exits(src):
    try:
        XD.preflight_sd_reuse(lambda *a, **k: None, src, REQ)
        return False
    except SystemExit as e:
        return e.code == 3


def _preflight_ok(src):
    try:
        u, r = XD.preflight_sd_reuse(lambda *a, **k: None, src, REQ)
        return len(u) == 4 and not r
    except SystemExit:
        return False


if __name__ == "__main__":
    sys.exit(main())
