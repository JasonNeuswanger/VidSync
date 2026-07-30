#!/usr/bin/env python3
"""Regression tests for SD-D map REUSE in xdoc_objectives (`--sd-from`).

WHAT IS BEING PROTECTED. `xdoc_objectives.py` used to refit SD-D locally with
`objectives.fit(..., "SD", ...)` at ftol = xtol = gtol = 1e-14 and a 1200-evaluation cap. Those
tolerances are unreachable on this objective, so the fit ALWAYS hit the cap, was always ruled
non-convergent, and SD-D therefore never appeared in a single known-length number -- while `sd_real.py`
had already produced converged SD-D maps for the same cameras with the same estimator. `--sd-from` makes
the script EVALUATE those maps instead. Three things must then hold:

  1. the loader is fail-closed -- a hash/clip mismatch, an incomplete fit or a non-finite theta must
     raise rather than silently substitute some other camera's map;
  2. the reused theta reaches the downstream calibration BIT-UNCHANGED, and the map evaluated at
     deterministic test points is bit-identical before and after the known-length path builds its
     calibration (evaluating a map must not recalibrate it);
  3. validity accounting follows the SOURCE fit's facts, not this script's cap.

Test [4] needs the real pool document and skips itself when it is absent. Everything else is synthetic.

Run with ~/.venvs/vidsync/bin/python.
"""

import json
import os
import sys
import tempfile

import numpy as np

import harness_import

harness_import.ensure_path()
import xdoc_objectives as XD                                                  # noqa: E402

LT = harness_import.load("lattice")
DS = harness_import.load("downstream")

PASS, FAIL = [], []
CH = os.environ.get("VIDSYNC_CHENA_PROJECTS",
                    os.path.expanduser("~/Library/CloudStorage/Dropbox/Chena Project Synced"))
POOL = os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                        "2012-01-31_PoolTest_2026_Reanalysis.vsd")

# Deterministic probe points: frame corners, centre, and three off-axis pixels. Fixed here so the
# before/after comparison cannot be influenced by anything the pipeline does.
PROBES = np.array([[20.0, 20.0], [1900.0, 20.0], [20.0, 1060.0], [1900.0, 1060.0],
                   [960.0, 540.0], [1337.0, 271.0], [421.0, 909.0]])


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def fake_theta(seed):
    rg = np.random.default_rng(seed)
    th = np.zeros(14)
    th[0], th[1] = 960.0 + rg.normal(0, 5), 540.0 + rg.normal(0, 5)
    th[2] = -1.0e-8 * (1.0 + 0.1 * rg.normal())
    th[9] = 1e-9 * rg.normal()
    th[13] = 0.004 * rg.normal()
    return th


def fake_artifact(path, cameras):
    """An `sd_real`-shaped artifact. `cameras` is [(cam_id, doc_sha256, clip, {name: (theta, ok)})]."""
    R = {"cameras": {}}
    for cid, sha, clip, fits in cameras:
        R["cameras"][cid] = {
            "document": cid.split("/")[0], "clip": clip, "doc_sha256": sha,
            "fits": {name: {"theta14": list(map(float, th)), "loss": 12.5, "status": 2,
                            "nfev": 9, "eta": float(th[13]), "completed": bool(ok),
                            "termination": "ftol", "init": "staged-identity",
                            "adm_v2": {"safe": True}, "inverse": {"shipped_failures": 0}}
                     for name, (th, ok) in fits.items()}}
    with open(path, "w") as fh:
        json.dump({"manifest": {"analysis": "sd_real", "script": "sd_real.py",
                                "source_file_sha256": {"sd_real.py": "deadbeef"},
                                "git": {"head": "test"}, "started": "test"},
                   "results": R}, fh)
    return path


def main():
    print("=" * 100)
    print("SD-D MAP REUSE REGRESSION TESTS (xdoc_objectives --sd-from)")
    print("=" * 100)
    tmp = tempfile.mkdtemp(prefix="sdreuse")
    thA0, thA1 = fake_theta(1), fake_theta(2)
    thB0 = fake_theta(3)
    art = fake_artifact(os.path.join(tmp, "sd_real_full.json"), [
        ("pool/Left", "sha_pool", "Left Camera", {"SD-D/M0": (thA0, True), "SD-D/M1": (thA1, True)}),
        ("pool/Right", "sha_pool", "Right Camera", {"SD-D/M0": (thB0, True)}),
        ("8mm/Left", "sha_8mm", "Left Camera", {"SD-D/M0": (fake_theta(4), False)}),
    ])

    print("\n[1] The loader indexes by (document hash, clip, candidate)")
    src = XD.load_sd_source(art)
    check("all four records indexed", len(src["index"]) == 4, f"{sorted(src['index'])}")
    check("source provenance carried (analysis, script hashes, git, solver)",
          src["analysis"] == "sd_real" and "sd_real.py" in src["source_sha256"]
          and src["git"] == {"head": "test"} and "sd_fast" in src["solver"])
    r = XD.sd_from_source(src, "sha_pool", "Left Camera", "SD-D/M0")
    check("the right record comes back", np.array_equal(np.asarray(r["theta14"], float), thA0))
    check("and it is bit-identical to the artifact, not merely close",
          all(a == b for a, b in zip(r["theta14"], thA0.tolist())))

    print("\n[2] The loader is FAIL-CLOSED against substitution")
    check("a wrong document hash yields None, never another camera's map",
          XD.sd_from_source(src, "sha_WRONG", "Left Camera", "SD-D/M0") is None)
    check("a wrong clip yields None (no Left/Right crossover)",
          XD.sd_from_source(src, "sha_pool", "Middle Camera", "SD-D/M0") is None)
    check("an absent model yields None, so the caller refits rather than guessing",
          XD.sd_from_source(src, "sha_pool", "Right Camera", "SD-D/M1") is None)
    try:
        XD.sd_from_source(src, "sha_8mm", "Left Camera", "SD-D/M0")
        ok = False
    except RuntimeError as e:
        ok = "not marked completed" in str(e)
    check("a record that is not marked completed RAISES rather than being reused", ok)
    bad = fake_artifact(os.path.join(tmp, "bad.json"),
                        [("pool/Left", "sha_pool", "Left Camera",
                          {"SD-D/M0": (np.full(14, np.nan), True)})])
    try:
        XD.sd_from_source(XD.load_sd_source(bad), "sha_pool", "Left Camera", "SD-D/M0")
        ok2 = False
    except RuntimeError as e:
        ok2 = "non-finite" in str(e)
    check("a non-finite theta RAISES", ok2)
    check("no source at all is a no-op (default refit path is untouched)",
          XD.sd_from_source(None, "sha_pool", "Left Camera", "SD-D/M0") is None)

    print("\n[3] Validity accounting uses the SOURCE fit's cap, not this script's")
    check("the reused cap is sd_fast's 300, not the local 1200",
          XD.SD_SOURCE_MAX_NFEV == 300 and XD.SD_MAX_NFEV == 1200,
          f"{XD.SD_SOURCE_MAX_NFEV} vs {XD.SD_MAX_NFEV}")
    import fitvalidity as FV
    d_eval = {"loss": 12.5, "status": 2, "nfev": 9, "hit_nfev_cap": False,
              "evaluated_not_refitted": True}
    v = FV.from_least_squares("SD-D/M0", d_eval, max_nfev=XD.SD_SOURCE_MAX_NFEV, theta14=thA0)
    check("a converged reused fit is valid", v.valid, f"{v.failures()}")
    d_cap = {"loss": 12.5, "status": 0, "nfev": 1200, "hit_nfev_cap": True}
    v2 = FV.from_least_squares("SD-D/M0", d_cap, max_nfev=XD.SD_MAX_NFEV, theta14=thA0)
    check("a capped local fit is still INVALID (a cap is not convergence)", not v2.valid,
          f"{v2.failures()}")
    check("and its failure names the cap", any("cap" in f or "MAXIMUM" in f.upper()
                                               for f in v2.failures()), f"{v2.failures()}")

    print("\n[4] REAL DATA: evaluating a reused map through the known-length path does not alter it")
    if not os.path.exists(POOL):
        print("        pool document unavailable; skipping")
    else:
        cals = DS.load_bound_cals(POOL)
        clip = sorted(cals)[0]
        th = fake_theta(11)
        before = LT.U(PROBES, th).copy()
        dmap = DS.DistortionMap.for_camera(th, cals[clip], name="SD-D/M0 (reused)")
        cam = DS.build_calibration(cals[clip], dmap)
        after = LT.U(PROBES, np.asarray(dmap.theta14, float))
        check("theta reaching build_calibration is bit-identical to the artifact's",
              np.array_equal(np.asarray(dmap.theta14, float), th))
        check("the map at seven deterministic probes is BIT-identical before and after",
              np.array_equal(before, after),
              f"max |delta| {float(np.abs(before - after).max()):.3e} px")
        check("build_calibration did not write back a re-estimated distortion",
              np.array_equal(np.asarray(dmap.theta14, float), th))
        check("and it produced a usable camera (so the check is not vacuous)",
              cam is not None and "cam" in cam)
        nr = DS.node_residuals(cals[clip], cam)
        check("node residuals computed from the reused map, map still unchanged",
              nr is not None and np.array_equal(np.asarray(dmap.theta14, float), th))

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED")
    for f in FAIL:
        print(f"    FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
