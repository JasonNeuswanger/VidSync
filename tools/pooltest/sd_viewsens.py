#!/usr/bin/env python3
"""Within-method INCIDENCE-FILTER (min_inc) view sensitivity for SD-D on 2015-06-22-1 Clearwater.

THE QUESTION. The caller chooses SD-D's observation view on a lattice-eligibility test: before the
lattice fix `2015-06-22-1 Clearwater` failed that test and SD-D received the `min_inc=1` view; after the
fix it passes and SD-D receives the `min_inc=2` view. This script holds everything else constant and
changes only the observation set, so the resulting map change is attributable to the view alone.

WHAT THE TWO VIEWS ARE NOT. This is NOT indexed-versus-unindexed data, and neither arm contains an
observation that failed to be indexed. On this document EVERY observation is successfully lattice-indexed
in both arms -- 340 of 340 on Left and 365 of 365 on Right, with zero index contradictions. The two views
differ in the INCIDENCE FILTER: `min_inc=1` keeps every observation, `min_inc=2` keeps only observations
carrying at least two line incidences, which removes 31 on Left and 47 on Right. Describing this as
"indexing sensitivity" would be wrong. The internal identifiers `fallback_raw` and `indexed` are retained
for provenance with the already-written artifact; DISPLAY_LABEL below is what reports should print.

WHAT IS HELD CONSTANT: the SD-D implementation (`sd_fast.SDFast`, the accelerated but residual-identical
form of `objectives.resid_SD`), the objective and its kappa = 3.0 weighting, the optimizer
(`sd_fast.solve`: trf, x_scale="jac", ftol = xtol = gtol = 1e-8, max_nfev = 300), the initialization
policy (staged-identity ladder for M0; M1 from its own fitted M0 with eta set to zero), and the
diagnostics. ONLY the Dataset selection differs.

THIS IS NOT A METHOD COMPARISON. It says nothing about whether SD-D, B or PD-D is better; it separates
"the estimator changed" from "the observations changed", which the earlier report conflated.

Writes analysis-output/<outdir>/sd_viewsens_mid.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

import artifacts
import harness_import
import mapmetrics as MM

harness_import.ensure_path()
import sd_fast as SF                                                          # noqa: E402
import sd_real as SR                                                          # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")
DS = harness_import.load("downstream")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
MID = [d for d in SR.DOCS if d["key"] == "mid"][0]
GRID = MM.frame_grid()
DIAG = SR.DIAG
_ex = np.minimum(GRID[:, 0], LT.FRAME_W - GRID[:, 0]) / LT.FRAME_W
_ey = np.minimum(GRID[:, 1], LT.FRAME_H - GRID[:, 1]) / LT.FRAME_H
_m = np.minimum(_ex, _ey)
REGION = {"corner": _m < 0.08, "edge": (_m >= 0.08) & (_m < 0.20), "central": _m >= 0.20}

# The two views, recovered from the actual execution paths rather than reconstructed by hand. The dict
# KEYS are historical internal identifiers, kept so the stored artifact stays readable; `display_label`
# and `canonical_name` are what any report must use, because the keys read as if one view were unindexed.
VIEWS = {
    "fallback_raw": {"require_indexed": False, "min_inc": 1, "kappa": 3.0,
                     "canonical_name": "min_inc1_all_incidences",
                     "display_label": "min_inc=1 view (all incidences kept)",
                     "predicate": "OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)",
                     "origin": "sd_real.build else-branch / xdoc_objectives dlines[clip]; the view the "
                               "caller supplies when the lattice-eligibility test FAILS",
                     "note": "contains only successfully indexed observations on this document; the "
                             "name is historical and does not mean unindexed"},
    "indexed": {"require_indexed": True, "min_inc": 2, "kappa": 3.0,
                "canonical_name": "min_inc2_indexed",
                "display_label": "min_inc=2 view (>=2 line incidences)",
                "predicate": "OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)",
                "origin": "sd_real.build if-branch / xdoc_objectives dsets[clip]; the view the caller "
                          "supplies when the lattice-eligibility test PASSES",
                "note": "differs from the other view ONLY by the min_inc incidence filter"},
}
DISPLAY_LABEL = {k: v["display_label"] for k, v in VIEWS.items()}


def obs_hash(D):
    """Digest of the exact observation set: coordinates, weights and line incidences, order-independent."""
    h = hashlib.sha256()
    rows = []
    for ci in range(D.ncap):
        pass
    for i in range(D.n):
        rows.append(f"{D.xy[i, 0]:.6f},{D.xy[i, 1]:.6f},{D.w[i]:.9e},"
                    f"{sorted(D.obs_lines[i]) if hasattr(D, 'obs_lines') else ''}")
    for r in sorted(rows):
        h.update(r.encode())
    return h.hexdigest()


def diagnostics(th, pts):
    a2 = MM.admissibility_v2(th)
    iv = MM.inverse_reliability(th, n_int=13, n_edge=80, unfavourable=False)
    cert = MM.certify_forward_injective(th, max_cells=800)
    pl = SR.init_metrics(th, pts)
    return {"admissibility_v2": {k: a2[k] for k in ("safe", "physically_plausible", "min_det",
                                                    "min_sigma", "roundtrip_px",
                                                    "expansion_ratio")},
            "forward_certificate": {"verdict": cert["verdict"], "cells": cert["cells_certified"]},
            "inverse": {"shipped_failures": iv["summary"]["shipped_total_failures"],
                        "max_roundtrip_px": max(iv[b]["shipped_max_roundtrip_px"]
                                                for b in ("interior", "edges", "corners"))},
            "displacement_jacobian": pl}


def pair_block(th_a, th_b, pts):
    d = MM.map_difference(th_a, th_b, grid=GRID, pts=pts)
    A = LT.U(GRID, np.asarray(th_a, float))
    B = LT.U(GRID, np.asarray(th_b, float))
    raw = np.linalg.norm(A - B, axis=1)
    al = np.linalg.norm(MM.apply_homography(np.asarray(d["homography"], float), A) - B, axis=1)
    reg = {rn: {"n": int(m.sum()), "raw_median": float(np.median(raw[m])),
                "raw_max": float(raw[m].max()),
                "aligned_median": float(np.median(al[m])),
                "aligned_p95": float(np.percentile(al[m], 95)),
                "aligned_max": float(al[m].max())} for rn, m in REGION.items()}
    return {"raw_hull": d.get("raw_hull"), "aligned_hull": d.get("aligned_hull"),
            "raw_full": d["raw_full"], "aligned_full": d["aligned_full"],
            "hull_coverage": d.get("hull_coverage"), "gauge_fraction": d["gauge_fraction"],
            "by_region": reg, "threshold_ladder": MM.threshold_ladder(d)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(OUT, "correction-2026-07-29"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = artifacts.ArtifactWriter(
        analysis="sd_viewsens", script=__file__, outdir=args.outdir,
        requested_documents=["mid"], all_documents=["mid"],
        requested_candidates=[f"SD-D/{m}::{v}" for v in VIEWS for m in ("M0", "M1")],
        objective_versions={"SD-D": "sd_fast.SDFast + sd_fast.solve, identical for both views",
                            "residuals": "sd_real.orthogonal_residuals"},
        source_files=["sd_viewsens.py", "sd_fast.py", "sd_real.py", "objectives.py", "lattice.py",
                      "mapmetrics.py", "artifacts.py"],
        calibration_node_source="not used: no downstream reconstruction here")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    say("=" * 118)
    say("SD-D INCIDENCE-FILTER (min_inc) VIEW SENSITIVITY, 2015-06-22-1 Clearwater -- "
        "WITHIN-METHOD experiment")
    say("=" * 118)
    say(f"  document {MID['vsd']}")
    say("  only the Dataset selection differs between the two arms; implementation, objective,")
    say("  weighting, optimizer, stopping rules and initialization policy are identical.")
    say("  BOTH arms contain only successfully lattice-indexed observations. The difference is the")
    say("  min_inc incidence filter, NOT whether indexing succeeded, and the experiment covers")
    say(f"  {len(VIEWS)} views x 2 models x 2 cameras = {len(VIEWS) * 4} fits in total.")
    R = {"views": VIEWS, "display_labels": DISPLAY_LABEL,
         "n_expected_fits": len(VIEWS) * 4,
         "all_observations_indexed": "on this document every observation in BOTH views is "
                                     "successfully lattice-indexed; the views differ only by "
                                     "the min_inc incidence filter",
         "cameras": {}}
    cals = DS.load_bound_cals(MID["vsd"])
    for clip in sorted(cals):
        cid = f"mid/{clip.split()[0]}"
        caps = LT.load_captures(MID["vsd"], clip)
        arms, ths = {}, {}
        say("")
        say(f"  {cid}")
        say(f"    {'view':14} {'n_obs':>6} {'lines':>6} {'n_eff':>8} {'obs sha256':18} {'rule'}")
        Ds = {}
        for vn, vc in VIEWS.items():
            D = OB.Dataset(caps, require_indexed=vc["require_indexed"], min_inc=vc["min_inc"],
                           kappa=vc["kappa"])
            Ds[vn] = D
            say(f"    {vn:14} {D.n:6d} {D.nline:6d} {MM.n_eff(D.w):8.1f} {obs_hash(D)[:16]:18} "
                f"require_indexed={vc['require_indexed']}, min_inc={vc['min_inc']}, "
                f"kappa={vc['kappa']}")
        # the common intersection, by coordinate, for the like-for-like residual comparison
        keys = {vn: {(round(float(p[0]), 6), round(float(p[1]), 6)) for p in Ds[vn].xy}
                for vn in VIEWS}
        common = set.intersection(*keys.values())
        say(f"    common observation intersection: {len(common)} of "
            + ", ".join(f"{vn} {len(keys[vn])}" for vn in VIEWS))
        sel_common = [np.array([(round(float(x), 6), round(float(y), 6)) in common
                                for x, y in C.xy]) for C in caps]

        say("")
        say(f"    {'fit':22} {'stat':>4} {'term':>10} {'nfev':>5} {'njev':>5} {'objective':>13} "
            f"{'opt':>9} {'eta':>11} {'s':>6} {'admV2':>6} {'invRT px':>9} {'maxDisp px':>10}")
        for vn in VIEWS:
            D = Ds[vn]
            F = SR.Fitter(D, "M0")
            r0 = F.staged()
            th0 = np.asarray(r0["theta14"], float)
            F1 = SR.Fitter(D, "M1")
            z = th0.copy(); z[13] = 0.0
            r1 = F1.fit(z, "fitted-M0-at-eta0")
            for model, r in (("M0", r0), ("M1", r1)):
                th = np.asarray(r["theta14"], float)
                ths[f"{model}::{vn}"] = th
                dg = diagnostics(th, D.xy)
                rec = {"view": vn, "model": model, "n_obs": int(D.n), "n_lines": int(D.nline),
                       "n_eff": MM.n_eff(D.w), "obs_sha256": obs_hash(D),
                       "init": r["init"], "loss": r["loss"], "status": r["status"],
                       "termination": r.get("termination"), "nfev": r["nfev"], "njev": r.get("njev"),
                       "optimality": r["optimality"], "runtime_s": r["runtime_s"],
                       "converged": bool(r["completed"]), "rescued": r.get("rescued"),
                       "eta": r["eta"], "hit_nfev_cap": bool(r["nfev"] >= 2 * SF.MAX_NFEV),
                       "objective_note": "SD-D's own Sampson cost; comparable only between these two "
                                         "SD-D arms, never across estimators"}
                rec.update(dg)
                arms[f"SD-D/{model}::{vn}"] = rec
                say(f"    {('SD-D/' + model + '::' + vn)[:22]:22} {rec['status']:4d} "
                    f"{str(rec['termination'])[:10]:>10} {rec['nfev']:5d} "
                    f"{(rec['njev'] or 0):5d} {rec['loss']:13.5f} {rec['optimality']:9.2e} "
                    f"{rec['eta']:+11.7f} {rec['runtime_s']:6.2f} "
                    f"{str(rec['admissibility_v2']['safe'])[:5]:>6} "
                    f"{rec['inverse']['max_roundtrip_px']:9.1e} "
                    f"{rec['displacement_jacobian']['max_disp_px']:10.1f}")

        # residuals: on each arm's native observations and on the common intersection
        say("")
        say(f"    orthogonal residual after correction, px "
            f"({'native = the arm own view; common = the intersection above'})")
        say(f"    {'fit':22} {'set':8} {'n':>6} {'median':>8} {'rms':>8} {'p95':>8} {'max':>8} "
            f"{'wRMS':>8} {'central':>8} {'edge':>8} {'corner':>8}")
        for k in sorted(arms):
            model, vn = k.split("::")[0].split("/")[1], k.split("::")[1]
            th = ths[f"{model}::{vn}"]
            wf = SR.balanced_weights_factory(caps, Ds[vn].sel)
            for sname, sel in (("native", Ds[vn].sel), ("common", sel_common)):
                rr = SR.orthogonal_residuals(caps, th, sel=sel, weights=wf)
                o, br = rr["overall"], rr["by_region"]
                arms[k].setdefault("residuals", {})[sname] = {
                    "n": o["n"], "median": o["median"], "rms": o["rms"], "p95": o["p95"],
                    "max": o["max"], "rms_over_diag": o["rms_norm"],
                    "weighted_rms": (rr["overall_weighted"] or {}).get("rms"),
                    "per_line_rms": rr["per_line_rms"],
                    "by_region": {kk: {"n": v["n"], "median": v["median"], "rms": v["rms"]}
                                  for kk, v in br.items()}}
                say(f"    {k[:22]:22} {sname:8} {o['n']:6d} {o['median']:8.4f} {o['rms']:8.4f} "
                    f"{o['p95']:8.4f} {o['max']:8.3f} "
                    f"{(rr['overall_weighted'] or {}).get('rms', float('nan')):8.4f} "
                    f"{br.get('central', {}).get('rms', float('nan')):8.4f} "
                    f"{br.get('edge', {}).get('rms', float('nan')):8.4f} "
                    f"{br.get('corner', {}).get('rms', float('nan')):8.4f}")

        # the sensitivity itself: same model, two views
        pts_common = np.array(sorted(common), float)
        pairs = {}
        say("")
        say("    VIEW SENSITIVITY: same model, min_inc=1 view vs min_inc=2 view (raw / aligned, px)")
        say(f"    {'model':6} {'scope':10} {'raw med':>9} {'raw max':>9} {'aln med':>9} "
            f"{'aln p95':>9} {'aln max':>9} {'gaugeFrac':>10}")
        for model in ("M0", "M1"):
            pb = pair_block(ths[f"{model}::fallback_raw"], ths[f"{model}::indexed"], pts_common)
            pairs[model] = pb
            for scope, blk in (("hull", pb["aligned_hull"]), ("full frame", pb["aligned_full"])):
                rawb = pb["raw_hull"] if scope == "hull" else pb["raw_full"]
                say(f"    {model:6} {scope:10} {rawb['median']:9.4f} {rawb['max']:9.4f} "
                    f"{blk['median']:9.4f} {blk['p95']:9.4f} {blk['max']:9.4f} "
                    f"{pb['gauge_fraction']:+10.3f}")
            for rn in ("central", "edge", "corner"):
                r = pb["by_region"][rn]
                say(f"    {model:6} {rn:10} {r['raw_median']:9.4f} {r['raw_max']:9.4f} "
                    f"{r['aligned_median']:9.4f} {r['aligned_p95']:9.4f} {r['aligned_max']:9.4f}")
        # and the M0 -> M1 step within each view, for scale comparison
        for vn in VIEWS:
            pairs[f"M0_vs_M1::{vn}"] = pair_block(ths[f"M0::{vn}"], ths[f"M1::{vn}"], pts_common)
        say("    for scale, the M0->M1 step within a single view (aligned median in hull, px): "
            + ", ".join(f"{vn} {pairs['M0_vs_M1::' + vn]['aligned_hull']['median']:.4f}"
                        for vn in VIEWS))
        R["cameras"][cid] = {"clip": clip, "doc_sha256": cals[clip]["identity"].doc_sha256,
                             "n_common_observations": len(common),
                             "arms": arms, "view_sensitivity": pairs,
                             "theta": {k: v.tolist() for k, v in ths.items()}}
    W.document_started("mid", doc_key="mid")
    W.document_completed("mid", completed_candidates=[f"SD-D/{m}::{v}"
                                                      for v in VIEWS for m in ("M0", "M1")])
    path = W.write(R)
    say("")
    say(f"  wrote {path}   [{time.time() - t0:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
