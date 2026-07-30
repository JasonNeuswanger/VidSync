#!/usr/bin/env python3
"""Tests for the EXACT provenance contract on explicitly reused SD-D maps (`sdprov`).

WHAT IS BEING PROTECTED. Revision 2's verifier established too little. Confirmed from the code before
these tests were written, it inferred the observation view from `n_obs` alone, accepted missing frame and
coordinate-convention metadata, accepted EITHER recognized view instead of the one the caller was about to
use, identified the producing implementation only by an analysis NAME, and never tied a reused map to the
bytes of the artifact it came from. Each of those is now a hard failure, and each has a test here.

THE CENTRAL CASE is `[2]`: two observation sets with IDENTICAL `n_obs` and identical line counts but one
coordinate moved. Under revision 2 that passed, because a count was the whole view check. Under the
canonical point-set hash it cannot.

NO OPTIMIZER EXISTS ANYWHERE NEAR THIS FILE. Every fitting entry point is replaced by a tripwire before
anything else runs, and the tripwire list is asserted empty at the end, so requirement 12 -- every
verification failure happens without invoking the optimizer -- is enforced rather than assumed.

Run with ~/.venvs/vidsync/bin/python.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

import harness_import
import sdprov as SP

harness_import.ensure_path()
import xdoc_objectives as XD                                                  # noqa: E402

OB = harness_import.load("objectives")
LT = harness_import.load("lattice")
SFmod = harness_import.load("sd_fast")
DS = harness_import.load("downstream")

PASS, FAIL, FITCALLS = [], [], []
HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ART = os.path.join(HERE, "analysis-output", "addendum-2026-07-29", "sd_real_full.json")
SHA_DOC = "d" * 64
CLIP = "Left Camera"
CAND = "SD-D/M0"


def install_tripwire():
    def trip(name):
        def f(*a, **k):
            FITCALLS.append(name)
            raise AssertionError(f"{name} must not be called by these tests")
        return f
    OB.fit = trip("objectives.fit")
    OB.PDExact.fit = trip("objectives.PDExact.fit")
    if hasattr(OB, "profile_H"):
        OB.profile_H = trip("objectives.profile_H")
    SFmod.solve = trip("sd_fast.solve")
    SFmod.fit_sd = trip("sd_fast.fit_sd")
    if hasattr(SFmod, "solve_staged"):
        SFmod.solve_staged = trip("sd_fast.solve_staged")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


# =============================================================== fixtures


class FakeCapture:
    def __init__(self, timecode):
        self.timecode = timecode


class FakeD:
    """The minimum an SD-D observation view is: coordinates, weights, line incidences, captures.

    Exactly the fields `sd_fast.SDFast` and `objectives.resid_SD` read, so hashing this hashes what the
    estimator actually consumed. Built by hand so the tests can vary ONE field at a time -- which is the
    only way to show that a same-count/different-coordinate pair is distinguished.
    """

    def __init__(self, xy, w, obs_lines, line_family, cap_of=None, timecodes=("0:00:00:01.0/30",)):
        self.xy = np.asarray(xy, float)
        self.w = np.asarray(w, float)
        self.obs_lines = [list(map(int, l)) for l in obs_lines]
        self.line_family = np.asarray(line_family, int)
        self.n = len(self.xy)
        self.nline = len(self.line_family)
        self.cap_of = np.zeros(self.n, int) if cap_of is None else np.asarray(cap_of, int)
        self.caps = [FakeCapture(t) for t in timecodes]
        self.ncap = len(self.caps)


def base_view(shift=0.0, n_lines=2):
    """Six observations on two crossing lines. `shift` moves ONE point by a fixed amount."""
    xy = [[100.0, 100.0], [200.0, 100.0], [300.0, 100.0],
          [100.0, 300.0], [200.0, 300.0], [300.0, 300.0]]
    xy[4] = [200.0 + shift, 300.0]
    w = [1.0, 0.9, 1.1, 1.0, 0.95, 1.05]
    if n_lines == 2:
        lines, fam = [[0], [0], [0], [1], [1], [1]], [0, 0]
    else:                                     # the same points, split across three line records
        lines, fam = [[0], [0], [2], [1], [1], [1]], [0, 0, 0]
    return FakeD(xy, w, lines, fam)


def expected_for(D, view_id, model="M0", frame=(1920.0, 1080.0),
                 convention=SP.COORDINATE_CONVENTION):
    """A `view_identity`-shaped expectation built from a FakeD, without touching a document."""
    out = dict(SP.pointset_digest(D))
    out.update({"view_id": view_id,
                "view_selector": SP.VIEWS[view_id]["predicate"],
                "view_selector_id": SP.VIEWS[view_id]["view_selector_id"],
                "view_selector_version": SP.VIEW_SELECTOR_VERSION,
                "frame": [float(frame[0]), float(frame[1])],
                "coordinate_convention": convention,
                "model_parameterization": SP.model_parameterization(OB, model)})
    return out


def theta(seed):
    rg = np.random.default_rng(seed)
    t = np.zeros(14)
    t[0], t[1] = 960.0 + rg.normal(0, 4), 540.0 + rg.normal(0, 4)
    t[2] = -1e-8
    t[13] = 0.004 * rg.normal()
    return t


CODE_HASHES = {n: f"{i:064x}" for i, n in enumerate(SP.SD_PRODUCER_CODE_FILES, start=1)}
FP = SP.code_fingerprint(CODE_HASHES)
REVISION = {"commit": "c" * 40, "branch": "agent-dev", "dirty": True, "n_dirty_paths": 172}
STATUS_OK = {"optimizer_converged": True, "numerically_invertible": True,
             "empirically_admissible": True, "eligible_for_ranking": True}
ADM_OK = {"safe": True, "physically_plausible": True, "min_det": 1.0, "min_sigma": 1.0}
INV_OK = {"shipped_failures": 0, "max_roundtrip_px": 1e-13}


def provenance(exp, th, *, view_id=None, doc_sha=SHA_DOC, clip=CLIP, cand=CAND, **over):
    """A COMPLETE provenance record that matches `exp`. Tests then break exactly one field."""
    rec = {"schema_version": SP.SCHEMA_VERSION,
           "doc_key": "mid", "doc_sha256": doc_sha, "clip": clip, "cal_pk": 1, "clip_pk": 2,
           "candidate": cand, "model": cand.split("/")[-1],
           "view_id": view_id or exp["view_id"],
           "view_selector": exp["view_selector"],
           "view_selector_id": exp["view_selector_id"],
           "view_selector_version": exp["view_selector_version"],
           "n_obs": exp["n_obs"], "n_lines": exp["n_lines"], "n_captures": exp["n_captures"],
           "pointset_hash_version": exp["pointset_hash_version"],
           "pointset_sha256": exp["pointset_sha256"],
           "ordered_pointset_sha256": exp["ordered_pointset_sha256"],
           "frame": exp["frame"], "coordinate_convention": exp["coordinate_convention"],
           "model_parameterization": exp["model_parameterization"],
           "producer_revision": dict(REVISION), "producer_code_fingerprint": copy.deepcopy(FP),
           "parameter_sha256": SP.parameter_sha256(th),
           "status": dict(STATUS_OK)}
    rec.update(over)
    return rec


def artifact(path, cams, *, analysis="sd_real", manifest_hashes=None):
    """An `sd_real`-shaped artifact. `cams` is [(cam_id, doc_sha, clip, n_obs, n_lines, n_cap, fits)]
    where fits maps candidate -> (theta, completed, provenance-or-None)."""
    R = {"cameras": {}}
    for cid, sha, clip, n_obs, n_lines, ncap, fits in cams:
        R["cameras"][cid] = {
            "document": cid.split("/")[0], "clip": clip, "doc_sha256": sha,
            "n_obs": n_obs, "n_lines": n_lines, "n_captures": ncap,
            "lattice_valid": True,
            "fits": {cand: {"theta14": list(map(float, th)), "loss": 1.0, "status": 2, "nfev": 7,
                            "eta": float(th[13]), "completed": ok, "termination": "ftol",
                            "init": "staged", "adm_v2": dict(ADM_OK), "inverse": dict(INV_OK),
                            **({"provenance": prov} if prov is not None else {})}
                     for cand, (th, ok, prov) in fits.items()}}
    with open(path, "w") as fh:
        json.dump({"manifest": {"analysis": analysis, "script": "sd_real.py",
                                "source_file_sha256": manifest_hashes
                                if manifest_hashes is not None else dict(CODE_HASHES),
                                "git": dict(REVISION), "started": "t"}, "results": R}, fh)
    return path


def sidecar(path, artifact_sha256, records, *, schema=SP.SIDECAR_SCHEMA_VERSION):
    with open(path, "w") as fh:
        json.dump({"schema_version": schema, "artifact_sha256": artifact_sha256,
                   "artifact_basename": "x.json", "records": records}, fh)
    return path


def one_request(exp, view_id=None, **over):
    r = SP.reuse_request("mid", SHA_DOC, CLIP, CAND, view_id or exp["view_id"], exp,
                         cal_pk=1, clip_pk=2)
    r.update(over)
    return r


# =============================================================== the tests


def main():
    print("=" * 108)
    print("SD-D EXPLICIT-REUSE PROVENANCE CONTRACT TESTS")
    print("=" * 108)
    install_tripwire()
    tmp = tempfile.mkdtemp(prefix="sdprov")
    th = theta(1)
    D = base_view()
    exp = expected_for(D, "min_inc2_indexed")

    print("\n[0] The canonical point-set hash distinguishes what a count cannot")
    Dsame = base_view(shift=0.25)
    esame = expected_for(Dsame, "min_inc2_indexed")
    check("two views with the SAME n_obs, n_lines and n_captures ...",
          (exp["n_obs"], exp["n_lines"], exp["n_captures"])
          == (esame["n_obs"], esame["n_lines"], esame["n_captures"]),
          f"{exp['n_obs']}/{exp['n_lines']}/{exp['n_captures']}")
    check("... but ONE coordinate moved by 0.25 px get DIFFERENT point-set hashes",
          exp["pointset_sha256"] != esame["pointset_sha256"],
          f"{exp['pointset_sha256'][:16]} vs {esame['pointset_sha256'][:16]}")
    Dw = base_view(); Dw.w[3] += 1e-12
    check("a 1e-12 change in ONE weight changes the hash (weights enter the residual as sqrt(w))",
          expected_for(Dw, "min_inc2_indexed")["pointset_sha256"] != exp["pointset_sha256"])
    D3 = base_view(n_lines=3)
    check("the same coordinates split across a different number of LINE records hash differently",
          expected_for(D3, "min_inc2_indexed")["pointset_sha256"] != exp["pointset_sha256"])
    perm = [5, 0, 3, 1, 4, 2]
    Dp = FakeD(D.xy[perm], D.w[perm], [D.obs_lines[i] for i in perm], D.line_family)
    ep = expected_for(Dp, "min_inc2_indexed")
    check("re-ORDERING the same observations leaves pointset_sha256 unchanged (a set is a set)",
          ep["pointset_sha256"] == exp["pointset_sha256"])
    check("but the ORDERED hash changes, so an execution-order difference is still recorded",
          ep["ordered_pointset_sha256"] != exp["ordered_pointset_sha256"])
    check("the hash is versioned", exp["pointset_hash_version"] == "sd-pointset/1")

    print("\n[1] A complete EMBEDDED provenance record matching the exact request succeeds")
    p1 = artifact(os.path.join(tmp, "a1.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                    {CAND: (th, True, provenance(exp, th))})])
    src = XD.load_sd_source(p1, sidecar_paths=[])
    u, f, r = XD.verify_sd_records(src, [one_request(exp)])
    check("it verifies", len(u) == 1 and not f and not r, f"{f}")
    got = list(u.values())[0]
    check("and the verified record names the requested view explicitly, not a matched count",
          got["view_verified"] == "min_inc2_indexed" and got["provenance_from"] == "embedded")
    check("and is bound to the artifact's own content hash",
          got["artifact_sha256"] == SP.file_sha256(p1))
    check("and records the producer code fingerprint",
          got["producer_code_sha256"] == FP["combined_sha256"])

    print("\n[2] SAME observation count, DIFFERENT point set -> FAILS (the revision-2 hole)")
    p2 = artifact(os.path.join(tmp, "a2.json"),
                  [("mid/Left", SHA_DOC, CLIP, esame["n_obs"], esame["n_lines"],
                    esame["n_captures"], {CAND: (th, True, provenance(esame, th))})])
    u2, f2, _ = XD.verify_sd_records(XD.load_sd_source(p2, sidecar_paths=[]), [one_request(exp)])
    check("a shifted-by-0.25px point set with identical counts is REJECTED", not u2 and len(f2) == 1,
          f"{f2}")
    check("and the error says so in as many words",
          "SAME observation count, DIFFERENT point set" in f2[0], f"{f2[0][:160]}")
    check("the count columns agree, so nothing but the hash could have caught it",
          "n_obs" not in f2[0])

    print("\n[3] Correct point set, WRONG line count -> FAILS")
    e3 = dict(exp); e3 = {**exp, "n_lines": exp["n_lines"] + 1}
    p3 = artifact(os.path.join(tmp, "a3.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], e3["n_lines"], exp["n_captures"],
                    {CAND: (th, True, provenance(e3, th))})])
    _, f3, _ = XD.verify_sd_records(XD.load_sd_source(p3, sidecar_paths=[]), [one_request(exp)])
    check("a record claiming one more line fails", len(f3) == 1 and "n_lines" in f3[0], f"{f3}")

    print("\n[4] A RECOGNIZED but NON-REQUESTED observation view -> FAILS")
    other = "min_inc1_all_incidences"
    eo = expected_for(D, other)
    p4 = artifact(os.path.join(tmp, "a4.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                    {CAND: (th, True, provenance(eo, th))})])
    _, f4, _ = XD.verify_sd_records(XD.load_sd_source(p4, sidecar_paths=[]),
                                    [one_request(exp)])            # requests min_inc2_indexed
    check("a perfectly valid min_inc=1 map fails when the min_inc=2 map was requested",
          len(f4) == 1 and "is not the requested view" in f4[0], f"{f4}")
    check("and the error says the offered view IS recognized, so the diagnosis is not 'unknown view'",
          "a recognized view, but not the one requested" in f4[0])
    check("the reverse direction fails too, so this is not one-sided",
          len(XD.verify_sd_records(XD.load_sd_source(p1, sidecar_paths=[]),
                                   [one_request(eo, view_id=other)])[1]) == 1)
    pv_nov = provenance(exp, th)
    for k in ("view_id", "view_selector", "view_selector_id"):
        pv_nov.pop(k)
    p4b = artifact(os.path.join(tmp, "a4b.json"),
                   [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                     {CAND: (th, True, pv_nov)})])
    _, f4b, _ = XD.verify_sd_records(XD.load_sd_source(p4b, sidecar_paths=[]), [one_request(exp)])
    check("an UNSPECIFIED view fails and is never inferred from the count",
          len(f4b) == 1 and "UNSPECIFIED" in f4b[0], f"{f4b}")

    print("\n[5] MISSING frame or coordinate metadata -> FAILS")
    for field, word in (("frame", "frame"), ("coordinate_convention", "coordinate_convention")):
        pv = provenance(exp, th)
        pv.pop(field)
        pth = artifact(os.path.join(tmp, f"a5_{field}.json"),
                       [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"],
                         exp["n_captures"], {CAND: (th, True, pv)})])
        _, f5, _ = XD.verify_sd_records(XD.load_sd_source(pth, sidecar_paths=[]),
                                        [one_request(exp)])
        check(f"a record with no {field} fails", len(f5) == 1 and word in f5[0], f"{f5}")

    print("\n[6] WRONG frame dimensions or WRONG coordinate convention -> FAILS")
    pv = provenance(exp, th, frame=[1280.0, 720.0])
    p6 = artifact(os.path.join(tmp, "a6.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                    {CAND: (th, True, pv)})])
    _, f6, _ = XD.verify_sd_records(XD.load_sd_source(p6, sidecar_paths=[]), [one_request(exp)])
    check("a 1280x720 frame against a 1920x1080 request fails",
          len(f6) == 1 and "frame" in f6[0] and "1280" in f6[0], f"{f6}")
    pv = provenance(exp, th, coordinate_convention="normalized [-1,1], y up")
    p6b = artifact(os.path.join(tmp, "a6b.json"),
                   [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                     {CAND: (th, True, pv)})])
    _, f6b, _ = XD.verify_sd_records(XD.load_sd_source(p6b, sidecar_paths=[]), [one_request(exp)])
    check("a different coordinate convention fails",
          len(f6b) == 1 and "coordinate_convention" in f6b[0], f"{f6b}")

    print("\n[7] MISSING or MISMATCHED producer revision / code fingerprint -> FAILS")
    cases = [
        ("no producer_revision at all", {"producer_revision": None}, "producer_revision"),
        ("a revision with no commit", {"producer_revision": {"dirty": True}},
         "producer_revision.commit"),
        ("a commit with no dirty flag", {"producer_revision": {"commit": "c" * 40}}, "dirty"),
        ("no code fingerprint at all", {"producer_code_fingerprint": None},
         "producer_code_fingerprint"),
    ]
    for label, over, word in cases:
        pv = provenance(exp, th, **over)
        if over.get("producer_revision") is None and "producer_revision" in over:
            pv.pop("producer_revision", None)
        if over.get("producer_code_fingerprint") is None and "producer_code_fingerprint" in over:
            pv.pop("producer_code_fingerprint", None)
        pth = artifact(os.path.join(tmp, f"a7_{abs(hash(label)) % 9999}.json"),
                       [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"],
                         exp["n_captures"], {CAND: (th, True, pv)})])
        _, f7, _ = XD.verify_sd_records(XD.load_sd_source(pth, sidecar_paths=[]),
                                        [one_request(exp)])
        check(f"{label} fails", len(f7) == 1 and word in f7[0], f"{f7}")
    fp_bad = copy.deepcopy(FP); fp_bad["combined_sha256"] = "0" * 64
    pv = provenance(exp, th, producer_code_fingerprint=fp_bad)
    p7 = artifact(os.path.join(tmp, "a7_self.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                    {CAND: (th, True, pv)})])
    _, f7a, _ = XD.verify_sd_records(XD.load_sd_source(p7, sidecar_paths=[]), [one_request(exp)])
    check("a fingerprint that does not match its OWN file hashes fails",
          len(f7a) == 1 and "does not match its own file hashes" in f7a[0], f"{f7a}")
    fp_short = SP.code_fingerprint({k: v for k, v in list(CODE_HASHES.items())[:2]})
    pv = provenance(exp, th, producer_code_fingerprint=fp_short)
    p7b = artifact(os.path.join(tmp, "a7_short.json"),
                   [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                     {CAND: (th, True, pv)})])
    _, f7b, _ = XD.verify_sd_records(XD.load_sd_source(p7b, sidecar_paths=[]), [one_request(exp)])
    check("a fingerprint missing a required implementation file fails",
          len(f7b) == 1 and "missing hashes" in f7b[0], f"{f7b}")
    off = dict(CODE_HASHES); off["sd_fast.py"] = "f" * 64
    p7c = artifact(os.path.join(tmp, "a7_off.json"),
                   [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                     {CAND: (th, True, provenance(exp, th))})], manifest_hashes=off)
    _, f7c, _ = XD.verify_sd_records(XD.load_sd_source(p7c, sidecar_paths=[]), [one_request(exp)])
    check("a fingerprint disagreeing with the producing manifest's own source hashes fails",
          len(f7c) == 1 and "disagrees with the producing manifest" in f7c[0], f"{f7c}")
    check("a DIRTY producing worktree is fine as long as the fingerprint is present",
          REVISION["dirty"] is True and not XD.verify_sd_records(
              XD.load_sd_source(p1, sidecar_paths=[]), [one_request(exp)])[1])

    print("\n[8] A LEGACY artifact with a complete, independently matching SIDECAR succeeds")
    p8 = artifact(os.path.join(tmp, "legacy.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                    {CAND: (th, True, None)})])                       # NO embedded provenance
    sha8 = SP.file_sha256(p8)
    sc8 = sidecar(os.path.join(tmp, "legacy.sidecar.json"), sha8, [provenance(exp, th)])
    u8, f8, _ = XD.verify_sd_records(XD.load_sd_source(p8, sidecar_paths=[sc8]),
                                     [one_request(exp)])
    check("the legacy artifact verifies through its sidecar", len(u8) == 1 and not f8, f"{f8}")
    check("and the record says the provenance came from the sidecar",
          list(u8.values())[0]["provenance_from"] == "sidecar")
    _, f8b, _ = XD.verify_sd_records(XD.load_sd_source(p8, sidecar_paths=[]), [one_request(exp)])
    check("the SAME legacy artifact WITHOUT the sidecar fails closed",
          len(f8b) == 1 and "NO embedded provenance and no verified sidecar" in f8b[0], f"{f8b}")
    check("the legacy artifact was not modified to make this work",
          SP.file_sha256(p8) == sha8)

    print("\n[9] An artifact whose content no longer matches its sidecar hash -> FAILS")
    with open(p8) as fh:
        blob = json.load(fh)
    blob["results"]["cameras"]["mid/Left"]["fits"][CAND]["loss"] = 999.0     # one byte-level change
    with open(p8, "w") as fh:
        json.dump(blob, fh)
    check("the artifact's hash really did change", SP.file_sha256(p8) != sha8)
    _, f9, _ = XD.verify_sd_records(XD.load_sd_source(p8, sidecar_paths=[sc8]), [one_request(exp)])
    check("the stale sidecar is not consulted and reuse fails closed", len(f9) == 1, f"{f9}")
    sc9 = sidecar(os.path.join(tmp, "wrongsha.json"), "e" * 64, [provenance(exp, th)])
    _, f9b, _ = XD.verify_sd_records(XD.load_sd_source(p1, sidecar_paths=[sc9]), [one_request(exp)])
    check("a sidecar whose declared artifact hash names other bytes is never used",
          len(f9b) == 0 or all("NO embedded" in m for m in f9b),
          f"{f9b}")
    p9 = artifact(os.path.join(tmp, "legacy2.json"),
                  [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                    {CAND: (th, True, None)})])
    _, f9c, _ = XD.verify_sd_records(XD.load_sd_source(p9, sidecar_paths=[sc9]), [one_request(exp)])
    check("and a legacy artifact 'covered' only by such a sidecar fails closed",
          len(f9c) == 1 and "no verified sidecar" in f9c[0], f"{f9c}")

    print("\n[10] MISSING, INCOMPLETE, DUPLICATE and CONFLICTING sidecar entries -> FAIL")
    sha9 = SP.file_sha256(p9)
    inc = provenance(exp, th); inc.pop("pointset_sha256"); inc.pop("model_parameterization")
    sc_inc = sidecar(os.path.join(tmp, "inc.json"), sha9, [inc])
    _, f10a, _ = XD.verify_sd_records(XD.load_sd_source(p9, sidecar_paths=[sc_inc]),
                                      [one_request(exp)])
    check("an incomplete sidecar record fails and names every missing field",
          len(f10a) == 1 and "INCOMPLETE" in f10a[0] and "pointset_sha256" in f10a[0]
          and "model_parameterization" in f10a[0], f"{f10a}")
    dup_a = sidecar(os.path.join(tmp, "dupA.json"), sha9, [provenance(exp, th)])
    dup_b = sidecar(os.path.join(tmp, "dupB.json"), sha9, [provenance(exp, th)])
    s10 = XD.load_sd_source(p9, sidecar_paths=[dup_a, dup_b])
    _, f10b, _ = XD.verify_sd_records(s10, [one_request(exp)])
    check("two sidecars asserting the same key are DUPLICATED and refused",
          any("DUPLICATED" in m for m in f10b), f"{f10b}")
    con_b = sidecar(os.path.join(tmp, "conB.json"), sha9,
                    [provenance(exp, th, view_id="min_inc1_all_incidences")])
    s10c = XD.load_sd_source(p9, sidecar_paths=[dup_a, con_b])
    _, f10c, _ = XD.verify_sd_records(s10c, [one_request(exp)])
    check("two sidecars disagreeing on the same key are CONFLICTING and refused",
          any("CONFLICTING" in m for m in f10c), f"{f10c}")
    check("and neither is used, so the map itself also fails",
          any("rejected at load time" in m for m in f10c), f"{f10c}")
    inside = sidecar(os.path.join(tmp, "insidedup.json"), sha9,
                     [provenance(exp, th), provenance(exp, th)])
    _, f10d, _ = XD.verify_sd_records(XD.load_sd_source(p9, sidecar_paths=[inside]),
                                      [one_request(exp)])
    check("a duplicate key WITHIN one sidecar file is refused",
          any("DUPLICATED" in m for m in f10d), f"{f10d}")
    bad_schema = sidecar(os.path.join(tmp, "badschema.json"), sha9, [provenance(exp, th)],
                         schema="sd-provenance-sidecar/0")
    _, f10e, _ = XD.verify_sd_records(XD.load_sd_source(p9, sidecar_paths=[bad_schema]),
                                      [one_request(exp)])
    check("an unversioned or wrongly versioned sidecar is refused",
          any("schema_version" in m for m in f10e), f"{f10e}")
    with open(os.path.join(tmp, "malformed.json"), "w") as fh:
        fh.write("{not json")
    _, f10f, _ = XD.verify_sd_records(
        XD.load_sd_source(p9, sidecar_paths=[os.path.join(tmp, "malformed.json")]),
        [one_request(exp)])
    check("a malformed sidecar is refused with a readable reason",
          any("not readable as JSON" in m for m in f10f), f"{f10f}")
    _, f10g, _ = XD.verify_sd_records(XD.load_sd_source(p9, sidecar_paths=[]), [one_request(exp)])
    check("a MISSING sidecar for a legacy artifact fails closed", len(f10g) == 1, f"{f10g}")

    print("\n[11] Reused parameters still give IDENTICAL deterministic map evaluations")
    probes = np.array([[20.0, 20.0], [1900.0, 1060.0], [960.0, 540.0], [733.0, 411.0],
                       [421.0, 909.0]])
    before = LT.U(probes, th).copy()
    src11 = XD.load_sd_source(p1, sidecar_paths=[])
    u11, f11, _ = XD.verify_sd_records(src11, [one_request(exp)])
    rec11 = XD.sd_from_source(src11, SHA_DOC, CLIP, CAND)
    after = LT.U(probes, np.asarray(rec11["theta14"], float))
    check("theta survives verification and the artifact round trip bit-for-bit",
          np.array_equal(np.asarray(rec11["theta14"], float), th))
    check("the parameter hash the contract checked is the hash of THAT theta",
          SP.parameter_sha256(rec11["theta14"]) == SP.parameter_sha256(th))
    check("and the map at five deterministic probes is bit-identical",
          np.array_equal(before, after),
          f"max |delta| {float(np.abs(before - after).max()):.3e} px")
    pv_bad = provenance(exp, th, parameter_sha256=SP.parameter_sha256(theta(2)))
    p11 = artifact(os.path.join(tmp, "a11.json"),
                   [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                     {CAND: (th, True, pv_bad)})])
    _, f11b, _ = XD.verify_sd_records(XD.load_sd_source(p11, sidecar_paths=[]), [one_request(exp)])
    check("a parameter hash that does not match the stored theta fails",
          len(f11b) == 1 and "parameter_sha256" in f11b[0], f"{f11b}")

    print("\n[12] Status must be present and must agree with the artifact's own evidence")
    pv = provenance(exp, th); pv["status"] = {"optimizer_converged": True}
    p12 = artifact(os.path.join(tmp, "a12.json"),
                   [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                     {CAND: (th, True, pv)})])
    _, f12, _ = XD.verify_sd_records(XD.load_sd_source(p12, sidecar_paths=[]), [one_request(exp)])
    check("an incomplete status block fails",
          len(f12) == 1 and "status is incomplete" in f12[0], f"{f12}")
    pv = provenance(exp, th)
    p12b = artifact(os.path.join(tmp, "a12b.json"),
                    [("mid/Left", SHA_DOC, CLIP, exp["n_obs"], exp["n_lines"], exp["n_captures"],
                      {CAND: (th, True, pv)})])
    with open(p12b) as fh:
        blob = json.load(fh)
    blob["results"]["cameras"]["mid/Left"]["fits"][CAND]["adm_v2"] = {
        "safe": False, "physically_plausible": False}
    with open(p12b, "w") as fh:
        json.dump(blob, fh)
    _, f12b, _ = XD.verify_sd_records(XD.load_sd_source(p12b, sidecar_paths=[]),
                                      [one_request(exp)])
    check("a status claiming the frozen gate passed when the artifact says it failed is refused",
          len(f12b) == 1 and "contradicts the artifact's own stored evidence" in f12b[0], f"{f12b}")

    print("\n[13] Fail-closed: preflight aborts, and NO optimizer was ever constructed")
    def preflight_exits(src_, reqs):
        try:
            XD.preflight_sd_reuse(lambda *a, **k: None, src_, reqs)
            return False
        except SystemExit as e:
            return e.code == 3
    check("preflight exits 3 on the same-count/different-points artifact",
          preflight_exits(XD.load_sd_source(p2, sidecar_paths=[]), [one_request(exp)]))
    check("preflight exits 3 on the wrong-but-recognized-view artifact",
          preflight_exits(XD.load_sd_source(p4, sidecar_paths=[]), [one_request(exp)]))
    check("preflight exits 3 on the legacy artifact with no sidecar",
          preflight_exits(XD.load_sd_source(p9, sidecar_paths=[]), [one_request(exp)]))
    check("preflight returns normally on the complete embedded record",
          XD.preflight_sd_reuse(lambda *a, **k: None, XD.load_sd_source(p1, sidecar_paths=[]),
                                [one_request(exp)])[0].__len__() == 1)
    check("NO fitting entry point was called by any check above", not FITCALLS, f"{FITCALLS}")

    print("\n[14] REAL artifact + REAL sidecar: 12 of 12 verify, still with no optimizer")
    if not os.path.exists(REAL_ART):
        print("        real artifact unavailable; skipping")
    else:
        rsrc = XD.load_sd_source(REAL_ART)
        check("the real sidecar loads with no problems", not rsrc["sidecar_problems"],
              f"{rsrc['sidecar_problems']}")
        check("it carries 12 entries, one per camera per model", len(rsrc["sidecars"]) == 12,
              f"{len(rsrc['sidecars'])}")
        check("the real artifact carries no embedded provenance (it predates the contract)",
              all(v.get("embedded_provenance") is None for v in rsrc["index"].values()))
        real_reqs, real_ok = [], True
        for spec in XD.DOCS:
            if not os.path.exists(spec["vsd"]):
                real_ok = False
                continue
            for clip, cal in sorted(DS.load_bound_cals(spec["vsd"]).items()):
                caps = LT.load_captures(spec["vsd"], clip)
                Dd = OB.Dataset(caps, **SP.VIEWS["min_inc2_indexed"]["kwargs"])
                pd_ok = bool(Dd.n >= 20
                             and all(C.notes["index_contradictions"] == 0 for C in caps))
                vw = "min_inc2_indexed" if pd_ok else "min_inc1_all_incidences"
                for m in ("M0", "M1"):
                    e = SP.view_identity(OB, caps, vw, m, frame=[LT.FRAME_W, LT.FRAME_H])
                    real_reqs.append(SP.reuse_request(
                        spec["key"], cal["identity"].doc_sha256, clip, f"SD-D/{m}", vw, e,
                        cal_pk=cal["identity"].cal_pk, clip_pk=cal["identity"].clip_pk))
        if not real_ok:
            print("        one or more documents unavailable; skipping the end-to-end check")
        else:
            ur, fr, rr = XD.verify_sd_records(rsrc, real_reqs)
            check("all 12 real maps verify against independently reconstructed inputs",
                  len(ur) == 12 and not fr and not rr, f"{fr}")
            check("every one is on the min_inc=2 view, requested explicitly",
                  {v["view_verified"] for v in ur.values()} == {"min_inc2_indexed"})
            check("every one carries a producer code fingerprint",
                  all(v["producer_code_sha256"] for v in ur.values()))
            check("the producing worktree is recorded as DIRTY, and that is not an error",
                  all((v["producer_revision"] or {}).get("dirty") is True for v in ur.values()))
            # the same real maps requested as the OTHER view must all fail
            wrong = [dict(r, expected_view="min_inc1_all_incidences") for r in real_reqs]
            _, fw, _ = XD.verify_sd_records(rsrc, wrong)
            check("requesting the min_inc=1 view instead rejects all 12 real maps", len(fw) == 12,
                  f"{len(fw)} failures")
            check("real-data verification called no optimizer", not FITCALLS, f"{FITCALLS}")

    print("\n[15] The prior suites still pass unchanged")
    for name in ("test_sd_map_reuse.py", "test_sd_reuse_failclosed.py", "test_fitvalidity.py"):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            print(f"        {name} absent; skipping")
            continue
        r = subprocess.run([sys.executable, p], capture_output=True, text=True)
        tail = [l for l in r.stdout.strip().splitlines() if "passed" in l]
        check(f"{name} exits 0", r.returncode == 0,
              (tail[-1].strip() if tail else r.stdout[-300:] + r.stderr[-300:]))

    print("\n" + "=" * 108)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED; fitting entry points called: {len(FITCALLS)}")
    for f in FAIL:
        print(f"    FAILED: {f}")
    return 1 if (FAIL or FITCALLS) else 0


if __name__ == "__main__":
    sys.exit(main())
