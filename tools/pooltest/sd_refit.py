#!/usr/bin/env python3
"""Refit SD-D with the verified accelerated solver, on the three known-length documents.

CONDITIONAL. This runs only because `test_sd_fast.py` (89 gates) and `test_sd_nonlattice.py` (29 gates)
pass. It does NOT broaden the document suite, change production code, or promote anything.

Every candidate map is bound to its camera through `downstream.DistortionMap` and re-verified in
`downstream.build_calibration`, so a Left/Right swap cannot occur. Every SD-D fit carries its own
convergence verification, and `fitvalidity` decides what may be reported. Output goes through
`artifacts.ArtifactWriter`, so a partial run cannot occupy the full run's filename.

Writes analysis-output/sd_refit_<scope>.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import os
import sys
import time

import numpy as np

import artifacts
import fitvalidity as FV
import harness_import

harness_import.ensure_path()
import sd_fast as SF                                                         # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")
DS = harness_import.load("downstream")
kl = harness_import.load("knownlength")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
POOL = os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                        "2012-01-31_PoolTest_2026_Reanalysis.vsd")

DOCS = [
    {"key": "pool", "label": "2012 pool test (Sony Handycam)", "vsd": POOL,
     "types": kl.POOL_CONVENTIONAL_TYPES, "unit_mm": 1000.0},
    {"key": "8mm", "label": "2015-09-04-1 Clearwater (Rokinon 8 mm fisheye)",
     "vsd": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"), "types": None, "unit_mm": 1.0},
    {"key": "mid", "label": "2015-06-22-1 Clearwater (label '13 mm', UNVERIFIED)",
     "vsd": os.path.join(DM, "2015-06-22-1 Clearwater.vsd"), "types": None, "unit_mm": 1.0},
]
CANDIDATES = ["stored", "B/M0", "B/M1", "PD-D/M0", "PD-D/M1", "SD-D/M0", "SD-D/M1"]


def stats(err):
    e = np.abs(np.asarray(err, float)); s = np.asarray(err, float)
    if e.size == 0:
        return {"n": 0}
    return {"n": int(e.size), "mae": float(e.mean()),
            "rmse": float(np.sqrt((s ** 2).mean())), "med": float(np.median(e)),
            "bias": float(s.mean()), "p90": float(np.percentile(e, 90)), "max": float(e.max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--docs", nargs="*", default=["pool", "8mm", "mid"])
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    ALL = [d["key"] for d in DOCS]
    W = artifacts.ArtifactWriter(
        analysis="sd_refit", script=__file__, outdir=args.outdir,
        requested_documents=args.docs, all_documents=ALL, requested_candidates=CANDIDATES,
        objective_versions={
            "SD-D": f"sd_fast (analytic line Jacobian + complex-step model Jacobian), "
                    f"ftol={SF.FTOL:.0e} xtol={SF.XTOL:.0e} gtol={SF.GTOL:.0e} "
                    f"max_nfev={SF.MAX_NFEV}, multi-start polish and verify",
            "PD-D": "objectives.PDExact (exact projective lattice)",
            "B": "objectives.fit(B), legacy line ODR, unchanged",
            "distortion_map": "lattice.U -> parity_step5.undistort14 (14-parameter)"},
        source_files=["sd_refit.py", "sd_fast.py", "objectives.py", "lattice.py", "downstream.py",
                      "fitvalidity.py", "artifacts.py"],
        calibration_node_source="vsd (ZVSSCREENPOINT via nodes.py)")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R = {"documents": {}}
    say("=" * 108)
    say("SD-D REFIT WITH THE VERIFIED ACCELERATED SOLVER")
    say("=" * 108)
    say(f"  scope {W.document_scope} -> {W.basename('json')}")
    say(f"  SD-D tolerances ftol={SF.FTOL:.0e} xtol={SF.XTOL:.0e} gtol={SF.GTOL:.0e}, "
        f"cap {SF.MAX_NFEV}; every fit polished by multi-start and convergence-VERIFIED.")
    say(f"  Maps are camera-bound; build_calibration re-verifies. No production default changes.")

    for spec in DOCS:
        if spec["key"] not in args.docs:
            continue
        vsd = spec["vsd"]
        if not os.path.exists(vsd):
            W.document_failed(spec["key"], "document not found")
            continue
        say(f"\n{'=' * 108}\n  {spec['label']}\n{'=' * 108}")
        cals = DS.load_bound_cals(vsd)
        clips = sorted(cals)
        sha = cals[clips[0]]["identity"].doc_sha256
        say(f"  document SHA-256 {sha}")
        docR = R["documents"][spec["key"]] = {
            "label": spec["label"], "doc_key": DS.document_key(vsd), "doc_sha256": sha,
            "cameras": {c: cals[c]["identity"].to_dict() for c in clips}}
        W.document_started(spec["key"], sha256=sha, doc_key=DS.document_key(vsd),
                           node_source="vsd (ZVSSCREENPOINT)", label=spec["label"])

        D0 = kl.load(vsd, conventional_types=spec["types"], unit_mm=spec["unit_mm"])
        conv, clicks = D0["conventional"], D0["clicks"]
        say(f"  {len(conv)} conventional measurements in "
            f"{len({r['tc'] for r in conv})} timecode clusters")

        # ---- per camera: dataset selection, then fits
        maps_by_clip, validities, fitrec = {}, {}, {}
        for clip in clips:
            caps = LT.load_captures(vsd, clip)
            Dind = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
            lat_ok = Dind.n >= 20 and all(C.notes["index_contradictions"] == 0 for C in caps)
            Dsd = Dind if lat_ok else OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
            say(f"\n  {clip}   lattice validated: {lat_ok}")
            say(f"    SD-D fitted subset: {Dsd.n} observations, {Dsd.nline} lines, "
                f"{Dsd.ncap} capture(s)"
                f"{'' if lat_ok else '  [unique-observation fallback, require_indexed=False]'}")
            inc = np.array([len(l) for l in Dsd.obs_lines])
            say(f"    incidences: singly {int((inc == 1).sum())}, "
                f"multiply {int((inc >= 2).sum())}")
            wsum = float(Dsd.w.sum())
            say(f"    Delaunay weights: mean {Dsd.w.mean():.4f}, min {Dsd.w.min():.4f}, "
                f"max {Dsd.w.max():.4f}, total {wsum:.2f}, "
                f"duplicates merged {Dsd.info['merged_duplicate_line_records']}")
            maps_by_clip[clip], validities[clip], fitrec[clip] = {}, {}, {}
            pts = np.array([[x, y] for x, y, _, _ in cals[clip]["front"] + cals[clip]["back"]],
                           float)

            # legacy B and exact PD-D come from the existing code, unchanged
            for model in ("M0", "M1"):
                rb = OB.fit(Dsd, "B", model, warm=False, max_nfev=3000)
                maps_by_clip[clip][f"B/{model}"] = np.array(rb["theta14"], float)
                fitrec[clip][f"B/{model}"] = {k: rb[k] for k in
                                              ("loss", "nfev", "status", "optimality", "eta",
                                               "runtime_s")}
                validities[clip][f"B/{model}"] = FV.from_least_squares(
                    f"B/{model}", rb, max_nfev=3000, theta14=rb["theta14"])
            if lat_ok:
                for model in ("M0", "M1"):
                    ev = OB.PDExact(Dind, model)
                    thB = maps_by_clip[clip][f"B/{model}"]
                    res, wt = ev.fit(ev.init_dlt(thB))
                    th = ev.theta(res.x)
                    maps_by_clip[clip][f"PD-D/{model}"] = th
                    d = {"loss": float(2 * res.cost), "nfev": int(res.nfev),
                         "status": int(res.status), "optimality": float(res.optimality),
                         "eta": float(th[13]), "runtime_s": wt,
                         "inverse_failures": ev.C["inverse_failures"]}
                    fitrec[clip][f"PD-D/{model}"] = d
                    validities[clip][f"PD-D/{model}"] = FV.from_least_squares(
                        f"PD-D/{model}", d, max_nfev=200, theta14=th,
                        inverse_ok=(ev.C["inverse_failures"] == 0))
            else:
                for model in ("M0", "M1"):
                    validities[clip][f"PD-D/{model}"] = FV.not_fitted(
                        f"PD-D/{model}",
                        "lattice did not validate; PD remains inadmissible without an "
                        "independently validated lattice")

            # SD-D through the accelerated, verified solver
            say(f"    {'SD-D':9} {'stat':>5} {'nfev':>5} {'solve s':>8} {'total s':>8} "
                f"{'loss':>13} {'eta':>11} {'rounds':>7} {'verified':>9}")
            for model in ("M0", "M1"):
                r = SF.fit_sd(Dsd, model, verify=True, n_perturb=3)
                maps_by_clip[clip][f"SD-D/{model}"] = np.array(r["theta14"], float)
                c = r["convergence"]
                say(f"    {'SD-D/' + model:9} {r['status']:5d} {r['nfev']:5d} "
                    f"{r['solve_s']:8.3f} {r['total_s']:8.3f} {r['loss']:13.6f} "
                    f"{r['eta']:+11.7f} {c['n_rounds_used']:7d} {str(c['verified']):>9}")
                fitrec[clip][f"SD-D/{model}"] = {
                    k: r[k] for k in ("loss", "status", "nfev", "njev", "optimality", "eta",
                                      "solve_s", "total_s", "actual_residual_calls",
                                      "actual_jacobian_calls", "first_solve", "n_params",
                                      "n_model_params", "n_line_params", "n_residual_rows",
                                      "n_observations", "n_lines", "over_hard_limit")}
                fitrec[clip][f"SD-D/{model}"]["convergence"] = c
                validities[clip][f"SD-D/{model}"] = FV.from_least_squares(
                    f"SD-D/{model}", {"status": r["status"], "nfev": r["nfev"],
                                      "loss": r["loss"], "optimality": r["optimality"]},
                    max_nfev=r["max_nfev"], theta14=r["theta14"],
                    convergence_verified=r["convergence_verified"],
                    cap_kind="wall_clock" if r["over_hard_limit"] else None)
                if r["over_hard_limit"]:
                    say(f"      *** exceeded the {r['hard_limit_s']}s hard per-fit limit "
                        f"({r['total_s']:.2f}s) -- marked invalid ***")

            # nesting and admissibility complete every validity record
            for obj in ("B", "PD-D", "SD-D"):
                a, b = f"{obj}/M0", f"{obj}/M1"
                if a in fitrec[clip] and b in fitrec[clip]:
                    l0, l1 = fitrec[clip][a]["loss"], fitrec[clip][b]["loss"]
                    validities[clip][b].nests_under_M0 = bool(
                        l1 <= l0 + 1e-6 * max(abs(l0), 1.0))
            for k, th in maps_by_clip[clip].items():
                ad = LT.admissible(th, pts)
                validities[clip][k].admissible = bool(ad["ok"])
                validities[clip][k].inverse_ok = bool(
                    validities[clip][k].inverse_ok and ad["roundtrip_box_all_converged"]
                    and ad["roundtrip_box_px"] < 1e-9)
            validities[clip]["stored"] = FV.FitValidity(
                candidate="stored", optimizer_status=2, nfev=0, cap_reached=False,
                loss=float("nan"), finite_loss=True,
                extra={"note": "the stored ZVSCALIBRATION anchor is not a fit"})
            maps_by_clip[clip]["stored"] = np.concatenate([cals[clip]["dist"], [0.0]])

        docR["fits"] = fitrec
        docR["fit_validity"] = {c: {k: v.to_dict() for k, v in validities[c].items()}
                                for c in clips}
        for c in clips:
            for k, v in validities[c].items():
                W.candidate_validity(spec["key"], c, k, v.to_dict())
        inval = sorted({k for c in clips for k, v in validities[c].items() if not v.valid})
        say(f"\n  INVALID on this document (excluded from downstream and rankings): "
            f"{', '.join(inval) if inval else 'none'}")
        for k in inval:
            say(f"    {k}: {FV.invalid_reasons(validities, k, clips)}")

        # ---- downstream known-length, only for candidates valid on EVERY camera
        say(f"\n  DOWNSTREAM KNOWN-LENGTH (only fully valid candidates are reconstructed)")
        say(f"    {'candidate':10} {'n':>5} {'MAE':>9} {'RMSE':>9} {'med':>9} {'bias':>9} "
            f"{'p90':>9} {'max':>9}")
        S = {}
        for name in CANDIDATES:
            if name not in maps_by_clip[clips[0]]:
                continue
            if not FV.candidate_valid(validities, name, clips):
                say(f"    {name:10} {'unavailable':>9}  invalid fit: "
                    f"{FV.invalid_reasons(validities, name, clips)}")
                S[name] = {"valid": False, "reason": FV.invalid_reasons(validities, name, clips)}
                continue
            cams = {c: DS.build_calibration(
                cals[c], DS.DistortionMap.for_camera(maps_by_clip[c][name], cals[c],
                                                     name=f"{name}/{c}",
                                                     source="sd_refit this run"))
                    for c in clips}
            X = {}
            for pk in sorted({p for r in conv for p in r["pks"]}):
                obs = DS.observations(pk, cams, clicks)
                if len(obs) >= 2:
                    X[pk] = DS.triangulate_lm(obs)["X"]
            err = []
            for r in conv:
                a, b = r["pks"]
                if a in X and b in X:
                    d = float(np.linalg.norm(X[a] - X[b])) * spec["unit_mm"]
                    err.append(d - r["true"])
            s = stats(err)
            S[name] = {**s, "valid": True}
            say(f"    {name:10} {s['n']:5d} {s['mae']:9.4f} {s['rmse']:9.4f} {s['med']:9.4f} "
                f"{s['bias']:+9.4f} {s['p90']:9.4f} {s['max']:9.4f}")
        fitted = [n for n in CANDIDATES if n != "stored"]
        best, bv = FV.best_by(validities, {k: v for k, v in S.items() if v.get("valid")},
                              "mae", fitted, clips)
        say(f"    best VALID fitted candidate by MAE: {best} at "
            f"{bv:.4f} mm" if best else "    no fitted candidate is valid")
        docR["known_length"] = {"summary": S, "best_valid": {"candidate": best, "mae": bv}}
        W.document_completed(spec["key"], completed_candidates=sorted(maps_by_clip[clips[0]]))
        say(f"  [{time.time() - t00:.1f}s elapsed]")

    path = W.write(R)
    man = W.manifest()
    say(f"\n  scope {man['document_scope']}: completed {man['completed_documents']}, "
        f"complete={man['complete']}")
    say(f"  wrote {path}   [{time.time() - t00:.1f}s total]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
