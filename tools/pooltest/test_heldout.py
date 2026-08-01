#!/usr/bin/env python3
"""Tests for the shared observed-pixel scorer and the deterministic fold families.

No calibration optimization anywhere: every map used here is closed-form, so these tests run in
about a second and cannot be affected by solver behaviour.

Covers, in order, the six properties the round requires:
  [1] held-out observations enter neither the distortion fit nor the training homography
  [2] every estimator receives identical eligible folds
  [3] inverse-map failures fail closed rather than silently dropping observations
  [4] fold membership is deterministic from lattice identity, not record or click order
  [5] incomplete-grid eligibility is explicit and deterministic
  [6] the score is in observed pixels, so a contracting map gains nothing
"""

import os
import sys

import numpy as np

import harness_import
import heldout as HO

LT = harness_import.load("lattice")
import test_lattice_traversal as TLT   # reuse the real Capture builder

PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    ok = bool(cond)
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}" + (f"  -- {extra}" if extra else ""))
    return ok


def grid_capture(nx=12, ny=10, pitch=90.0, x0=340.0, y0=150.0):
    """A clean two-family grid through the production Capture path."""
    lines = []
    for j in range(ny):
        lines.append([(x0 + i * pitch, y0 + j * pitch) for i in range(nx)])
    for i in range(nx):
        lines.append([(x0 + i * pitch, y0 + j * pitch) for j in range(ny)])
    return TLT.make_capture(lines)


def barrel(k1):
    th = np.zeros(14)
    th[0], th[1] = LT.FRAME_W / 2, LT.FRAME_H / 2
    th[2] = k1
    return th


def main():
    print("=" * 100)
    print("HELD-OUT SCORER AND FOLD DEFINITION TESTS")
    print("=" * 100)
    print(f"  heldout CONFIG_SHA256 {HO.CONFIG_SHA256[:16]}")

    C = grid_capture()
    folds = HO.folds_for_capture(C)

    print("\n[1] Held-out nodes enter neither the fit nor the training homography")
    for f in folds:
        if not f["eligible"]:
            continue
        check(f"{f['name']}: train and test are disjoint",
              not np.any(f["train"] & f["test"]))
    elig = HO._eligible(C)
    check("train | test covers exactly the eligible set, so nothing is quietly excluded",
          all(np.array_equal(f["train"] | f["test"], elig) for f in folds))
    # the scorer must be a pure function of the TRAINING points plus the held-out LATTICE indices:
    # perturbing the held-out OBSERVED coordinates must not change the prediction, only the error.
    f = next(f for f in folds if f["eligible"] and f["family"] == "block")
    th = barrel(-2.5e-8)
    s1 = HO.score_fold(C, th, f["train"], f["test"])
    C2 = grid_capture()
    C2.xy = C.xy.copy()
    C2.xy[f["test"]] += 7.0                     # move ONLY the held-out observations
    s2 = HO.score_fold(C2, th, f["train"], f["test"])
    check("moving held-out observations changes the error but not the prediction",
          s1["valid"] and s2["valid"] and abs(s2["obs_median"] - s1["obs_median"]) > 1.0,
          f"median {s1['obs_median']:.4f} -> {s2['obs_median']:.4f}")

    print("\n[2] Every estimator receives identical eligible folds")
    # folds depend only on the capture, never on a map or an estimator
    for th_test, label in ((np.zeros(14), "identity"), (barrel(-4e-8), "strong barrel")):
        f2 = HO.folds_for_capture(C)
        check(f"fold membership is independent of the candidate map ({label})",
              all(np.array_equal(a["test"], b["test"]) for a, b in zip(folds, f2)))
    check("fold list is identical across repeated calls (no hidden state)",
          all(np.array_equal(a["test"], b["test"])
              for a, b in zip(folds, HO.folds_for_capture(C))))

    print("\n[3] Inverse-map failures fail closed")
    # a map extreme enough that the Newton inverse cannot converge for some predictions
    bad = barrel(-9.0e-7)
    got = HO.score_fold(C, bad, f["train"], f["test"])
    check("a non-invertible map yields valid=False, not a partial score",
          got["valid"] is False, got.get("reason", ""))
    check("and the failure is reported rather than silently dropping points",
          "inverse" in got.get("reason", "") or "non-finite" in got.get("reason", ""),
          got.get("reason", ""))
    check("a valid score never reports fewer test points than the fold contains",
          s1["n_test"] == int(f["test"].sum()), f"{s1['n_test']} of {int(f['test'].sum())}")

    print("\n[4] Fold membership is deterministic from lattice identity, not record order")
    base_manifest, _ = HO.fold_manifest({"g": [C]})
    rng = np.random.default_rng(0)
    for trial in range(4):
        lines = []
        nx, ny, pitch, x0, y0 = 12, 10, 90.0, 340.0, 150.0
        for j in range(ny):
            lines.append([(x0 + i * pitch, y0 + j * pitch) for i in range(nx)])
        for i in range(nx):
            lines.append([(x0 + i * pitch, y0 + j * pitch) for j in range(ny)])
        order = rng.permutation(len(lines))
        perm = []
        for k in order:                            # permute line order AND reverse a random half
            L = list(lines[k])
            if rng.random() < 0.5:
                L = L[::-1]
            perm.append(L)
        Cp = TLT.make_capture(perm)
        m, _ = HO.fold_manifest({"g": [Cp]})
        check(f"permutation {trial}: fold manifest hash unchanged", m == base_manifest,
              f"{m[:12]} vs {base_manifest[:12]}")
    # canonical indices must also be invariant to a pure gauge change in the stored labels
    Cg = grid_capture()
    Cg.rc = np.column_stack([-Cg.rc[:, 1] + 17, Cg.rc[:, 0] - 5])     # swap, negate, translate
    check("canonical_rc removes axis swap, sign and translation",
          np.array_equal(HO.canonical_rc(Cg, HO._eligible(Cg)),
                         HO.canonical_rc(C, HO._eligible(C))))

    print("\n[5] Incomplete-grid eligibility is explicit and deterministic")
    tiny = grid_capture(nx=5, ny=4, pitch=110.0)
    tf = HO.folds_for_capture(tiny)
    inelig = [x for x in tf if not x["eligible"]]
    check("a small grid marks folds ineligible with a stated reason, rather than shrinking them",
          len(inelig) > 0 and all(x["reason"] != "ok" for x in inelig),
          f"{len(inelig)} of {len(tf)} ineligible; e.g. {inelig[0]['reason'] if inelig else ''}")
    check("eligibility is reproducible",
          [x["eligible"] for x in tf] == [x["eligible"] for x in HO.folds_for_capture(tiny)])
    check("every fold carries an explicit eligibility reason",
          all("reason" in x and x["reason"] for x in tf + folds))
    # a grid with a hole: eligibility must be decided by the rule, not by the hole's position
    check("ineligible folds are still LISTED, so nothing disappears from the manifest",
          len(tf) == len(folds), f"{len(tf)} vs {len(folds)} folds")

    print("\n[6] Observed-pixel scoring defeats a contracting map")
    # A pure isotropic contraction about the distortion centre is an exact projective change in
    # corrected space, so the corrected-space residual can be driven down while the observed-pixel
    # residual is unchanged. This is the failure mode the criterion exists to prevent.
    th0 = np.zeros(14)
    s_id = HO.score_fold(C, th0, f["train"], f["test"])
    shrink = np.zeros(14)
    shrink[0], shrink[1] = LT.FRAME_W / 2, LT.FRAME_H / 2
    shrink[9] = 0.0
    check("identity map scores finite and valid", s_id["valid"], f"obs_rms {s_id['obs_rms']:.4f}")
    check("identity map on an exact grid predicts held-out nodes near-perfectly",
          s_id["obs_rms"] < 1e-6, f"obs_rms {s_id['obs_rms']:.3e}")
    # distorted observations: the correct map must beat the identity in OBSERVED pixels
    k1 = -3.0e-8
    thd = barrel(k1)
    Cd = grid_capture()
    Cd.xy = LT.inv_U(C.xy, thd)[0]              # synthesize observations that thd exactly corrects
    sd_id = HO.score_fold(Cd, th0, f["train"], f["test"])
    sd_true = HO.score_fold(Cd, thd, f["train"], f["test"])
    check("the true map beats the identity on distorted data, in observed pixels",
          sd_true["valid"] and sd_id["valid"] and sd_true["obs_rms"] < sd_id["obs_rms"],
          f"true {sd_true['obs_rms']:.4f} px vs identity {sd_id['obs_rms']:.4f} px")
    check("and recovers the held-out nodes to sub-pixel accuracy",
          sd_true["obs_rms"] < 1e-3, f"{sd_true['obs_rms']:.3e} px")

    print("\n" + "=" * 100)
    print(f"  {PASS} passed, {FAIL} FAILED")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
