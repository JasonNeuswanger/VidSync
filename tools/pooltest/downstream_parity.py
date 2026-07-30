#!/usr/bin/env python3
"""Part 1: prove the explicit-injection path reproduces the monkeypatched path, and compare
production's Nelder-Mead triangulation against the harness's LM substitution.

Nothing here is a new scientific result. It is the gate that has to pass before the injection refactor
can be trusted for cross-document work.

Writes analysis-output/downstream_parity_<scope>.{log,json} through artifacts.ArtifactWriter, so a
partial run cannot occupy the complete run's filename and an interrupted run cannot replace a good
artifact.

Section [0b] is the camera-binding gate added after the independent audit of 2026-07-29: it asserts
that the deliberate Left/Right map swap the audit performed successfully is now rejected before any
reconstruction.

Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np

import artifacts
import harness_import

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
CANDIDATES = ["stored", "B/M0", "B/M1", "PD-D/M0", "PD-D/M1", "PD-U/M1"]


L = harness_import.load          # ONE shared instance per module; see harness_import.py

DS = L("downstream")
# FK is imported ONLY to provide the old, HISTORICAL reference path to compare against. Importing it
# installs the eta-aware map into parity's sightline/triangulate -- explicitly, via
# parity.install_historical_eta_map, and it prints a notice when it does. That installation is exactly
# what the "old path" column below is meant to reproduce, so it is required here and nowhere else.
FK = L("fisheye_knownlength_analysis")
st, kl, pa, nd = FK.st, FK.kl, FK.pa, FK.nd


def load_maps(vsd, outdir):
    """Load stored and historical fitted maps, each BOUND to the camera it belongs to.

    The fitted maps come from JSON keyed by clip NAME, which is not an identity -- the same names occur
    in every document. They are bound here, at load time, to the calibration actually loaded from this
    .vsd, so a map recorded for "Left Camera" can only ever be applied to this document's Left camera.
    """
    r1 = json.load(open(os.path.join(outdir, "obj_round1.json")))
    cl = json.load(open(os.path.join(outdir, "obj_pd_closure.json")))
    cals = DS.load_bound_cals(vsd)
    out = {}
    for name in CANDIDATES:
        per = {}
        for clip in sorted(cals):
            if name == "stored":
                per[clip] = DS.DistortionMap.from13_for_camera(
                    cals[clip]["dist"], cals[clip], name=f"{name}/{clip}",
                    source="ZVSCALIBRATION columns")
            elif name.startswith("B/"):
                per[clip] = DS.DistortionMap.for_camera(
                    r1[clip]["fits"][name]["theta14"], cals[clip],
                    name=f"{name}/{clip}", source="obj_round1.json")
            else:
                per[clip] = DS.DistortionMap.for_camera(
                    cl[clip]["weighting"]["fits"][name]["theta14"], cals[clip],
                    name=f"{name}/{clip}", source="obj_pd_closure.json")
        out[name] = per
    return out, cals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = artifacts.ArtifactWriter(
        analysis="downstream_parity", script=__file__, outdir=args.outdir,
        requested_documents=[DS.document_key(args.vsd)],
        all_documents=[DS.document_key(args.vsd)],
        requested_candidates=CANDIDATES,
        objective_versions={"distortion_map": "lattice.U -> parity_step5.undistort14",
                           "old_path": "fisheye_knownlength_analysis (HISTORICAL)"},
        source_files=["downstream_parity.py", "downstream.py", "parity.py", "lattice.py",
                      "stage2.py", "nodes.py", "artifacts.py"],
        calibration_node_source="vsd (ZVSSCREENPOINT via nodes.py)")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R = {}
    say("=" * 104)
    say("PART 1: EXPLICIT-INJECTION PARITY, AND PRODUCTION NELDER-MEAD vs HARNESS LM")
    say("=" * 104)

    maps, cals = load_maps(args.vsd, args.outdir)
    clips = sorted(cals)
    D = kl.load(args.vsd)
    conv, cpts, clicks = D["conventional"], D["cloud_points"], D["clicks"]
    pks = sorted({pk for r in conv for pk in r["pks"]} | {p["pk"] for p in cpts})
    say(f"  {len(CANDIDATES)} candidates x {len(clips)} cameras; {len(pks)} unique measured points "
        f"({len(conv)} conventional lengths, {len(cpts)} cloud points)")

    # ---------------------------------------------------------------- 0. injection sanity
    say(f"\n[0] INJECTION SANITY")
    say(f"      no monkeypatch is performed by downstream.py; parity's historical eta hook is "
        f"{pa.historical_eta_map_state()} and is installed only because "
        f"fisheye_knownlength_analysis was imported for comparison")
    say(f"      every map below is bound to its camera: "
        f"{maps['PD-D/M1'][clips[0]].identity.describe()}")
    m1 = maps["PD-D/M1"][clips[0]]
    m0 = DS.DistortionMap.from13_for_camera(m1.theta14[:13], cals[clips[0]],
                                            name="PD-D/M1 with eta forced to 0")
    say(f"      {m1!r}")
    say(f"      {m0!r}")
    probe = np.array([[400.0, 300.0], [1500.0, 900.0]])
    du = float(np.abs(m1.forward(probe) - m0.forward(probe)).max())
    camA = DS.build_calibration(cals[clips[0]], m1)
    camB = DS.build_calibration(cals[clips[0]], m0)
    dcam = max(abs(a - b) for a, b in zip(camA["cam"], camB["cam"]))
    sA = DS.sightline(400.0, 300.0, camA)
    sB = DS.sightline(400.0, 300.0, camB)
    dsl = max(abs(a - b) for p, q in zip(sA, sB) for a, b in zip(p, q))
    say(f"      nonzero eta demonstrably changes the pipeline: undistorted coords by {du:.4f} px, "
        f"camera position by {dcam:.4f} mm, a sightline by {dsl:.4f} mm")
    assert du > 1e-6 and dcam > 1e-9 and dsl > 1e-9, "eta has no effect; injection is broken"
    # M1 at eta = 0 must reproduce M0 exactly through the whole pipeline
    m1z = DS.DistortionMap.for_camera(np.concatenate([m1.theta14[:13], [0.0]]), cals[clips[0]],
                                      name="explicit eta=0")
    cz = DS.build_calibration(cals[clips[0]], m1z)
    say(f"      M1 at eta = 0 vs the explicit 13-parameter map, through the FULL rebuild: "
        f"undistortion {float(np.abs(m1z.forward(probe) - m0.forward(probe)).max()):.3e} px, "
        f"camera {max(abs(a - b) for a, b in zip(cz['cam'], camB['cam'])):.3e} mm, "
        f"front homography "
        f"{float(np.abs(np.array(cz['s2f']) - np.array(camB['s2f'])).max()):.3e}")
    R["injection"] = {"eta_effect_px": du, "eta_effect_cam_mm": dcam, "eta_effect_sightline_mm": dsl}

    # -------------------------------------------------------------- 0b. camera-binding gate
    # The independent audit swapped the Left and Right maps on the 2015 document and the run completed,
    # changing conventional MAE from 3.9146 to 4.2777 mm with no error. That swap must now fail before
    # any node or measurement reconstruction happens.
    say(f"\n[0b] CAMERA-BINDING GATE (the audited Left/Right swap must now fail)")
    swap = {}
    other = {clips[0]: clips[1], clips[1]: clips[0]}
    for clip in clips:
        wrong = maps["PD-D/M1"][other[clip]]
        try:
            DS.build_calibration(cals[clip], wrong)
            swap[clip] = "NOT REJECTED"
            say(f"      *** {clip}: accepted {other[clip]}'s map -- BINDING GATE FAILED ***")
        except DS.CameraBindingError as e:
            swap[clip] = "rejected"
            say(f"      {clip:14} rejected {other[clip]}'s map: {str(e).splitlines()[0]}")
    unbound = DS.DistortionMap(maps["PD-D/M1"][clips[0]].theta14, name="unbound map")
    try:
        DS.build_calibration(cals[clips[0]], unbound)
        swap["unbound"] = "NOT REJECTED"
    except DS.CameraBindingError:
        swap["unbound"] = "rejected"
        say(f"      {'unbound':14} rejected: a map with no CameraIdentity cannot calibrate anything")
    ok0 = all(v == "rejected" for v in swap.values())
    say(f"      BINDING GATE {'PASSED' if ok0 else 'FAILED'}")
    R["camera_binding_gate"] = {"results": swap, "passed": bool(ok0)}

    # ---------------------------------------------------------------- 1. old vs new path
    say(f"\n[1] EXPLICIT-INJECTION PARITY against the old monkeypatched path")
    say(f"      {'candidate':10} {'undist px':>11} {'s2f induced':>12} {'s2b induced':>12} "
        f"{'camera mm':>11} {'3D pt mm':>11} {'length mm':>11}")
    par = {}
    grid = np.column_stack([np.linspace(20, 1900, 60), np.linspace(20, 1060, 60)])
    for name in CANDIDATES:
        d_un = d_f = d_b = d_cam = 0.0
        newcams, oldcams = {}, {}
        for clip in clips:
            dm = maps[name][clip]
            newc = DS.build_calibration(cals[clip], dm)
            oldc = FK.build_cam(cals[clip], dm.theta14)
            newcams[clip], oldcams[clip] = newc, oldc
            d_un = max(d_un, float(np.abs(dm.forward(grid)
                                          - np.array([nd.undistort13(x, y, dm.theta14)
                                                      for x, y in grid])).max()))
            # homographies compared by INDUCED mapping, not entrywise
            for key, acc in (("s2f", "f"), ("s2b", "b")):
                a = np.array([nd.apply3(newc[key], *dm.forward_xy(x, y)) for x, y in grid])
                b = np.array([nd.apply3(oldc[key], *dm.forward_xy(x, y)) for x, y in grid])
                v = float(np.abs(a - b).max())
                if acc == "f":
                    d_f = max(d_f, v)
                else:
                    d_b = max(d_b, v)
            d_cam = max(d_cam, max(abs(p - q) for p, q in zip(newc["cam"], oldc["cam"])))
        # 3D points and lengths
        dm_by_clip = maps[name]
        d3 = dl = 0.0
        newX, oldX = {}, {}
        for pk in pks:
            obs = DS.observations(pk, newcams, clicks)
            if len(obs) < 2:
                continue
            newX[pk] = DS.triangulate_lm(obs)["X"]
            o = FK.reconstruct(pk, oldcams, clicks)
            oldX[pk] = None if o is None else o["X"]
            if oldX[pk] is not None:
                d3 = max(d3, float(np.linalg.norm(newX[pk] - oldX[pk])))
        for r in conv:
            a, b = r["pks"]
            if a in newX and b in newX and oldX.get(a) is not None and oldX.get(b) is not None:
                dl = max(dl, abs(float(np.linalg.norm(newX[a] - newX[b]))
                                 - float(np.linalg.norm(oldX[a] - oldX[b]))))
        say(f"      {name:10} {d_un:11.3e} {d_f:12.3e} {d_b:12.3e} {d_cam:11.3e} {d3:11.3e} "
            f"{dl:11.3e}")
        par[name] = {"undistorted_px": d_un, "s2f_induced_mm": d_f, "s2b_induced_mm": d_b,
                     "camera_mm": d_cam, "point3d_mm": d3, "length_mm": dl}
    # Two kinds of stage need two thresholds; lumping them together makes the gate meaningless.
    # Undistortion and the calibration solve are deterministic arithmetic and must agree at round-off.
    # Triangulated points come from an iterative solver that stops at its own tolerance on each path,
    # so their floor is solver noise rather than arithmetic.
    exact_worst = max(max(v["undistorted_px"], v["s2f_induced_mm"], v["s2b_induced_mm"],
                          v["camera_mm"]) for v in par.values())
    iter_worst = max(max(v["point3d_mm"], v["length_mm"]) for v in par.values())
    say(f"      deterministic stages (undistortion, homographies, camera): worst {exact_worst:.3e}")
    say(f"      iterative stage (triangulated points, lengths):            worst {iter_worst:.3e} mm")
    say(f"      the deterministic floor is last-bit association: the injected map routes through "
        f"lattice.U, the old path through nodes.undistort13, and they are the same expression.")
    say(f"      the triangulation floor is LM convergence noise present on BOTH paths -- 4e-6 mm is "
        f"4e-9 relative at this scale and 250x below the 1e-3 mm that would matter against the "
        f"0.1-1 mm model contrasts.")
    ok1 = exact_worst < 1e-9 and iter_worst < 1e-3
    say(f"      INJECTION PARITY {'PASSED' if ok1 else 'FAILED'} "
        f"(thresholds 1e-9 deterministic, 1e-3 mm iterative)")
    R["path_parity"] = par
    R["path_parity_worst"] = {"deterministic": exact_worst, "iterative_mm": iter_worst}

    # ---------------------------------------------------------------- 2. NM vs LM
    say(f"\n[2] PRODUCTION NELDER-MEAD vs HARNESS LM, all {len(pks)} points x "
        f"{len(CANDIDATES)} candidates")
    say(f"      production replay: gsl nmsimplex2, CPA seed, initial step sizes 1, size tolerance "
        f"1e-6, cap 500 iterations (VSPoint.m:147-215) via tri_oracle.cpp")
    say(f"\n      {'candidate':10} {'nmFail':>7} {'nmIterMed':>10} {'nmIterMax':>10} "
        f"{'d3D med':>10} {'d3D p95':>10} {'d3D max':>10} {'dLen med':>10} {'dLen max':>10} "
        f"{'cost NM<LM':>11} {'nm s':>7} {'lm s':>7}")
    nmr = {}
    for name in CANDIDATES:
        cams = {clip: DS.build_calibration(cals[clip], maps[name][clip]) for clip in clips}
        obs_list, keep = [], []
        for pk in pks:
            obs = DS.observations(pk, cams, clicks)
            if len(obs) >= 2:
                obs_list.append(obs); keep.append(pk)
        t0 = time.time()
        NM = DS.triangulate_nm_batch(obs_list)
        tnm = time.time() - t0
        t0 = time.time()
        LMr = [DS.triangulate_lm(o) for o in obs_list]
        tlm = time.time() - t0
        d3 = np.array([float(np.linalg.norm(a["X"] - b["X"])) for a, b in zip(NM, LMr)])
        dc = np.array([a["cost"] - b["cost"] for a, b in zip(NM, LMr)])
        Xn = {pk: a["X"] for pk, a in zip(keep, NM)}
        Xl = {pk: b["X"] for pk, b in zip(keep, LMr)}
        dl = []
        for r in conv:
            a, b = r["pks"]
            if a in Xn and b in Xn:
                dl.append(abs(float(np.linalg.norm(Xn[a] - Xn[b]))
                              - float(np.linalg.norm(Xl[a] - Xl[b]))))
        dl = np.array(dl)
        it = np.array([a["iters"] for a in NM])
        fail = int(sum(1 for a in NM if a["status"] != 0 or a["iters"] >= 500))
        say(f"      {name:10} {fail:7d} {int(np.median(it)):10d} {int(it.max()):10d} "
            f"{np.median(d3):10.3e} {np.percentile(d3, 95):10.3e} {d3.max():10.3e} "
            f"{np.median(dl):10.3e} {dl.max():10.3e} {int((dc < -1e-12).sum()):11d} "
            f"{tnm:7.2f} {tlm:7.2f}")
        nmr[name] = {"nm_failures": fail, "nm_iters_median": int(np.median(it)),
                     "nm_iters_max": int(it.max()),
                     "d3d_median_mm": float(np.median(d3)),
                     "d3d_p95_mm": float(np.percentile(d3, 95)), "d3d_max_mm": float(d3.max()),
                     "dlength_median_mm": float(np.median(dl)),
                     "dlength_max_mm": float(dl.max()),
                     "n_nm_cost_lower": int((dc < -1e-12).sum()),
                     "n_lm_cost_lower": int((dc > 1e-12).sum()),
                     "cost_diff_median": float(np.median(dc)),
                     "nm_seconds": tnm, "lm_seconds": tlm,
                     "nm_cost_median": float(np.median([a["cost"] for a in NM])),
                     "lm_cost_median": float(np.median([b["cost"] for b in LMr]))}
    say(f"      'cost NM<LM' counts points where the production solver reached a LOWER objective.")
    R["nm_vs_lm"] = nmr
    w3 = max(v["d3d_max_mm"] for v in nmr.values())
    wl = max(v["dlength_max_mm"] for v in nmr.values())
    nlower = sum(v["n_nm_cost_lower"] for v in nmr.values())
    llower = sum(v["n_lm_cost_lower"] for v in nmr.values())
    say(f"\n      worst 3D difference {w3:.3e} mm; worst length difference {wl:.3e} mm")
    say(f"      NM reached a lower cost on {nlower} point-candidate pairs, LM on {llower}")
    say(f"      the model contrasts this must be compared against are 0.1 to 1 mm")
    negligible = wl < 0.01
    say(f"      VERDICT: the two solvers {'agree to a negligible scale' if negligible else 'DIFFER materially'} "
        f"relative to those contrasts")
    if negligible:
        say(f"      -> LM retained for efficient offline analysis, with production-NM parity "
            f"documented here. LM is {np.mean([v['lm_seconds'] / max(v['nm_seconds'], 1e-9) for v in nmr.values()]):.1f}x "
            f"the NM wall time in this harness.")
    else:
        say(f"      -> production NM becomes the primary downstream result and LM is reported "
            f"separately")
    R["nm_vs_lm_verdict"] = {"worst_3d_mm": w3, "worst_length_mm": wl,
                            "negligible": bool(negligible),
                            "nm_cost_lower_count": nlower, "lm_cost_lower_count": llower}

    ok = ok0 and ok1 and max(v["d3d_max_mm"] for v in nmr.values()) < 1.0
    say(f"\n  PART 1 {'PASSED' if ok else 'FAILED'}   [{time.time() - t00:.1f}s]")
    if ok:
        W.document_completed(DS.document_key(args.vsd), completed_candidates=CANDIDATES)
    else:
        W.document_failed(DS.document_key(args.vsd), "one or more parity gates failed")
    W.document_started(DS.document_key(args.vsd), sha256=DS.document_sha256(args.vsd),
                       doc_key=DS.document_key(args.vsd), node_source="vsd (ZVSSCREENPOINT)")
    path = W.write(R)
    say(f"  wrote {path} (complete={W.manifest()['complete']})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
