#!/usr/bin/env python3
"""Regression tests for camera identity binding and eta propagation.

These are the tests the independent audit of 2026-07-29 would have failed. Its deliberate Left/Right
map swap on `2015-09-04-1 Clearwater.vsd` ran to completion and moved conventional MAE from 3.9146 mm
to 4.2777 mm without raising anything; test 2 below is that exact swap, and it must now raise
`CameraBindingError` before any node or measurement reconstruction.

Reads the three known-length documents read-only. Writes nothing.
Run with ~/.venvs/vidsync/bin/python.
"""

import os
import sys
import traceback

import numpy as np

import harness_import

harness_import.ensure_path()
import downstream as DS                                                      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
POOL = os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                        "2012-01-31_PoolTest_2026_Reanalysis.vsd")
FISHEYE = os.path.join(DM, "2015-09-04-1 Clearwater.vsd")
MID = os.path.join(DM, "2015-06-22-1 Clearwater.vsd")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def raises_binding(fn, *a, **k):
    """True if the call raises CameraBindingError. Any other exception is a test failure, not a pass."""
    try:
        fn(*a, **k)
    except DS.CameraBindingError as e:
        return True, str(e)
    except Exception as e:                                                   # noqa: BLE001
        return False, f"wrong exception {type(e).__name__}: {e}"
    return False, "no exception raised"


def main():
    print("=" * 100)
    print("CAMERA BINDING AND ETA PROPAGATION REGRESSION TESTS")
    print("=" * 100)

    fcals = DS.load_bound_cals(FISHEYE)
    pcals = DS.load_bound_cals(POOL)
    fclips = sorted(fcals)
    pclips = sorted(pcals)
    print(f"\n  {os.path.basename(FISHEYE)}  doc {fcals[fclips[0]]['identity'].doc_sha256[:16]}")
    for c in fclips:
        print(f"    {c:14} cal_pk={fcals[c]['identity'].cal_pk} "
              f"clip_pk={fcals[c]['identity'].clip_pk}")
    print(f"  {os.path.basename(POOL)}  doc {pcals[pclips[0]]['identity'].doc_sha256[:16]}")
    for c in pclips:
        print(f"    {c:14} cal_pk={pcals[c]['identity'].cal_pk} "
              f"clip_pk={pcals[c]['identity'].clip_pk}")

    # The premise of the whole design: clip NAME and cal_pk are each non-identifying on their own.
    print(f"\n[identity premise] clip names and primary keys are not identities")
    check("the same clip names occur in both documents",
          set(fclips) == set(pclips), f"{fclips}")
    check("cal_pk values collide across documents",
          {fcals[c]['identity'].cal_pk for c in fclips}
          == {pcals[c]['identity'].cal_pk for c in pclips}, "both documents use {1, 2}")
    check("the label-to-cal_pk mapping is INVERTED between the two documents",
          fcals["Left Camera"]["identity"].cal_pk != pcals["Left Camera"]["identity"].cal_pk,
          f"fisheye Left is cal_pk {fcals['Left Camera']['identity'].cal_pk}, "
          f"pool Left is cal_pk {pcals['Left Camera']['identity'].cal_pk}")
    mcals = DS.load_bound_cals(MID)
    allcams = list(fcals.values()) + list(pcals.values()) + list(mcals.values())
    check("(doc_sha256, cal_pk) is unique across all six cameras of the three documents",
          len({c["identity"].token for c in allcams}) == len(allcams) == 6,
          f"{len(allcams)} cameras, {len({c['identity'].token for c in allcams})} distinct tokens")
    check("clip_name is NOT part of the identity token",
          DS.CameraIdentity("h", "k", 1, 1, "Left Camera").token
          == DS.CameraIdentity("h", "k", 1, 1, "Right Camera").token,
          "a relabelling cannot make two different cameras compare equal, nor mask a real one")

    # ------------------------------------------------------------------ 1. correct bindings
    print(f"\n[1] CORRECT Left and Right bindings build and reconstruct")
    th = {c: np.concatenate([fcals[c]["dist"], [0.03]]) for c in fclips}
    good = {c: DS.DistortionMap.for_camera(th[c], fcals[c], name=f"M1/{c}") for c in fclips}
    cams = {}
    for c in fclips:
        cams[c] = DS.build_calibration(fcals[c], good[c])
    check("both cameras calibrate under their own maps", len(cams) == 2)
    check("the built calibration carries the camera identity",
          all(cams[c]["identity"].matches(fcals[c]["identity"]) for c in fclips))
    check("sightline reads the map from the calibration, not an argument",
          all(np.all(np.isfinite(np.array(DS.sightline(600.0, 400.0, cams[c])))) for c in fclips))

    # ------------------------------------------------------------------ 2. the audited swap
    print(f"\n[2] THE AUDITED Left/Right SWAP must now fail")
    a, b = fclips[0], fclips[1]
    okA, msgA = raises_binding(DS.build_calibration, fcals[a], good[b])
    check(f"{a} refuses {b}'s map", okA, msgA.splitlines()[0] if okA else msgA)
    okB, msgB = raises_binding(DS.build_calibration, fcals[b], good[a])
    check(f"{b} refuses {a}'s map", okB, msgB.splitlines()[0] if okB else msgB)
    check("the error names the swap as a same-document Left/Right swap",
          okA and "Left/Right swap" in msgA)
    check("the error explains that clip names are not identities",
          okA and "not an identity" in msgA)
    okU, msgU = raises_binding(DS.build_calibration, fcals[a],
                               DS.DistortionMap(th[a], name="unbound"))
    check("an UNBOUND map is refused too (fail closed)", okU, msgU)
    okS, msgS = raises_binding(DS.build_calibration, {**fcals[a], "identity": None}, good[a])
    check("a calibration loaded WITHOUT identity is refused", okS,
          msgS.splitlines()[0] if okS else msgS)

    # ------------------------------------------------------------------ 3. cross-document map
    print(f"\n[3] A map from ANOTHER DOCUMENT must fail")
    pool_map = DS.DistortionMap.for_camera(
        np.concatenate([pcals["Left Camera"]["dist"], [0.0]]), pcals["Left Camera"],
        name="pool Left")
    okX, msgX = raises_binding(DS.build_calibration, fcals["Left Camera"], pool_map)
    check("the fisheye Left camera refuses the pool Left map", okX,
          msgX.splitlines()[0] if okX else msgX)
    check("the error identifies it as a different document",
          okX and "another .vsd" in msgX)
    # and the reverse direction
    okY, _ = raises_binding(DS.build_calibration, pcals["Left Camera"], good["Left Camera"])
    check("the pool Left camera refuses the fisheye Left map", okY)

    # ------------------------------------------------------------------ 4. M0 and M1
    print(f"\n[4] M0 and M1 both bind, and the model is inferred from eta")
    m0 = DS.DistortionMap.from13_for_camera(fcals[a]["dist"], fcals[a], name="M0")
    m1 = DS.DistortionMap.for_camera(np.concatenate([fcals[a]["dist"], [0.05]]), fcals[a],
                                     name="M1")
    check("from13 gives model M0 and eta exactly 0", m0.model == "M0" and m0.eta == 0.0)
    check("a nonzero 14th entry gives model M1", m1.model == "M1" and m1.eta == 0.05)
    c0 = DS.build_calibration(fcals[a], m0)
    c1 = DS.build_calibration(fcals[a], m1)
    check("M0 and M1 both calibrate", c0 is not None and c1 is not None)
    check("M0 and M1 give DIFFERENT camera positions (eta is not being ignored)",
          max(abs(x - y) for x, y in zip(c0["cam"], c1["cam"])) > 1e-9,
          f"{max(abs(x - y) for x, y in zip(c0['cam'], c1['cam'])):.6e}")
    okM, _ = raises_binding(DS.build_calibration, fcals[b], m1)
    check("an M1 map is refused by the sibling camera just like M0", okM)

    # ------------------------------------------------------------------ 5. stored historical maps
    print(f"\n[5] STORED historical full-parameter maps bind and are refused when swapped")
    stored = {c: DS.DistortionMap.from13_for_camera(fcals[c]["dist"], fcals[c],
                                                   name=f"stored/{c}",
                                                   source="ZVSCALIBRATION columns") for c in fclips}
    check("the 13 stored parameters load as a bound eta=0 map",
          all(s.eta == 0.0 and s.identity is not None for s in stored.values()))
    check("stored maps have the full 13 shipped parameters, unmodified",
          all(np.array_equal(stored[c].theta14[:13], np.asarray(fcals[c]["dist"], float))
              for c in fclips))
    scam = DS.build_calibration(fcals[a], stored[a])
    check("a stored map calibrates its own camera", scam is not None)
    okH, _ = raises_binding(DS.build_calibration, fcals[a], stored[b])
    check("a stored map is refused by the sibling camera", okH)
    # binding a JSON-loaded map by clip name only, the way downstream_parity does
    reb = DS.DistortionMap(np.concatenate([fcals[a]["dist"], [0.0]]),
                           name="from JSON keyed by clip name").bound_to(fcals[a])
    check("an unbound historical map can be bound explicitly with .bound_to",
          reb.identity.matches(fcals[a]["identity"]))
    okR, msgR = raises_binding(reb.bound_to, fcals[b])
    check("an already-bound map cannot be silently re-bound elsewhere", okR,
          msgR.splitlines()[0] if okR else msgR)

    # ------------------------------------------------------------------ 6. eta = 0 equivalence
    print(f"\n[6] eta = 0 EQUIVALENCE through the full rebuild")
    probe = np.array([[400.0, 300.0], [1500.0, 900.0], [960.0, 540.0], [30.0, 1050.0]])
    m1zero = DS.DistortionMap.for_camera(np.concatenate([fcals[a]["dist"], [0.0]]), fcals[a],
                                         name="explicit eta=0")
    dmap_px = float(np.abs(m1zero.forward(probe) - m0.forward(probe)).max())
    czero = DS.build_calibration(fcals[a], m1zero)
    dcam = max(abs(x - y) for x, y in zip(czero["cam"], c0["cam"]))
    ds2f = float(np.abs(np.array(czero["s2f"]) - np.array(c0["s2f"])).max())
    dsl = max(abs(x - y) for p, q in zip(DS.sightline(700.0, 500.0, czero),
                                         DS.sightline(700.0, 500.0, c0))
              for x, y in zip(p, q))
    check("the 14-parameter map at eta=0 equals the 13-parameter map exactly",
          dmap_px == 0.0, f"max |dU| = {dmap_px:.3e} px")
    check("camera position identical at eta=0", dcam == 0.0, f"{dcam:.3e}")
    check("front homography identical at eta=0", ds2f == 0.0, f"{ds2f:.3e}")
    check("sightline identical at eta=0", dsl == 0.0, f"{dsl:.3e}")

    # ------------------------------------------------------------------ 7. nonzero eta propagates
    print(f"\n[7] NONZERO eta reaches the measurement sightline")
    mEta = DS.DistortionMap.for_camera(np.concatenate([fcals[a]["dist"], [0.04]]), fcals[a],
                                       name="eta=0.04")
    cEta = DS.build_calibration(fcals[a], mEta)
    dU = float(np.abs(mEta.forward(probe) - m0.forward(probe)).max())
    dC = max(abs(x - y) for x, y in zip(cEta["cam"], c0["cam"]))
    dS = max(abs(x - y) for p, q in zip(DS.sightline(700.0, 500.0, cEta),
                                        DS.sightline(700.0, 500.0, c0))
             for x, y in zip(p, q))
    check("eta changes the undistorted coordinates", dU > 1e-6, f"{dU:.4f} px")
    check("eta changes the rebuilt camera position", dC > 1e-9, f"{dC:.6f}")
    check("eta changes the measurement SIGHTLINE (the audited silent-drop path)",
          dS > 1e-9, f"{dS:.6f}")
    # the whole point: this cannot be defeated by degrading the object to 13 numbers
    dropped = False
    try:
        np.asarray(mEta)
    except TypeError:
        dropped = True
    check("np.asarray() on a nonzero-eta map REFUSES rather than dropping eta", dropped)
    for label, fn in (("iteration", lambda: list(mEta)), ("slicing", lambda: mEta[:13])):
        try:
            fn()
            check(f"{label} on a map refuses", False)
        except TypeError:
            check(f"{label} on a map refuses", True)
    t13, e = mEta.theta13_and_eta()
    check("theta13_and_eta() splits explicitly and keeps eta",
          len(t13) == 13 and e == 0.04)

    # ------------------------------------------------------------------ 8. the experiment escape hatch
    print(f"\n[8] DELIBERATE cross-camera transfer requires an explicit written reason")
    for bad in (None, True, "why not", ""):
        try:
            good[a].rebind_for_cross_camera_experiment(fcals[b], bad)
            check(f"reason {bad!r} is rejected", False)
        except ValueError:
            check(f"reason {bad!r} is rejected", True)
    xf = good[a].rebind_for_cross_camera_experiment(
        fcals[b], reason="reproducing the independent audit's deliberate Left/Right swap to confirm "
                         "the magnitude of the error it caused")
    cx = DS.build_calibration(fcals[b], xf)
    check("a properly justified cross-camera transfer is allowed", cx is not None)
    check("the transferred map is labelled as an experiment in its name",
          "CROSS-CAMERA EXPERIMENT" in xf.name)
    check("the transferred map records the reason in its provenance",
          "CROSS-CAMERA REBIND" in (xf.source or "") and "audit" in (xf.source or ""))
    check("the swapped calibration really is different from the correct one",
          max(abs(x - y) for x, y in zip(cx["cam"], cams[b]["cam"])) > 1e-9,
          f"{max(abs(x - y) for x, y in zip(cx['cam'], cams[b]['cam'])):.6f}")

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED")
    if FAIL:
        for f in FAIL:
            print(f"    FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                        # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
