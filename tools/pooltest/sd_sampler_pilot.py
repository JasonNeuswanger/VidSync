#!/usr/bin/env python3
"""Sampler-only acceptance pilot. No optimization, no basin claims.

Answers one question before any compute is spent on fitting: does the repaired profile-basis start
generator produce admissible starts at a usable rate? The previous monomial-coefficient sampler accepted
0 of 16, so the basin search performed no exploration. The gate here is the one the brief specifies:
fill the requested count within 4096 proposals AND keep acceptance at or above 1%, otherwise report the
domain as unusable rather than narrowing it again.

Writes analysis-output/sd_sampler_pilot_<scope>.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

import artifacts
import harness_import
import startgen as SG

harness_import.ensure_path()
import test_sd_fast as T                                                      # noqa: E402
import test_sd_nonlattice as NL                                               # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")
DS = harness_import.load("downstream")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
DOCS = {"pool": os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                                 "2012-01-31_PoolTest_2026_Reanalysis.vsd"),
        "8mm": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"),
        "mid": os.path.join(DM, "2015-06-22-1 Clearwater.vsd")}
SOBOL_SEED = 20260730
SYNTH_SEEDS = [11, 17]


def corpus():
    """The stored calibrations of all six cameras, as 14-vectors.

    Only the six STORED maps are available as full parameter vectors: the round-2 refit artifact records
    per-fit diagnostics but not `theta14`, so the fitted solutions cannot contribute to the envelope
    here. That is a limitation of the existing artifact, stated rather than worked around, and it makes
    the envelope narrower than it could be -- which the +-3x factor partly offsets.
    """
    ths = []
    for key, vsd in DOCS.items():
        if os.path.exists(vsd):
            for clip, c in DS.load_bound_cals(vsd).items():
                ths.append(np.concatenate([c["dist"], [0.0]]))
    return ths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--starts", type=int, default=16)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    cases = []
    for sd in SYNTH_SEEDS:
        th = T.truth_theta("M1", 0.026)
        D, _ = NL.build(NL.irregular_target(seed=sd), th)
        cases.append((f"synth{sd}", D, OB.MODELS["M1"]))
    for key, clip, ri, mi in (("pool", "Left Camera", True, 2),
                              ("8mm", "Right Camera", True, 2),
                              ("mid", "Right Camera", False, 1)):
        if not os.path.exists(DOCS[key]):
            continue
        caps = LT.load_captures(DOCS[key], clip)
        D = OB.Dataset(caps, require_indexed=ri, min_inc=mi, kappa=3.0)
        cases.append((f"{key}/{clip.split()[0]}", D, OB.MODELS["M1"]))

    W = artifacts.ArtifactWriter(
        analysis="sd_sampler_pilot", script=__file__, outdir=args.outdir,
        requested_documents=[c[0] for c in cases], all_documents=[c[0] for c in cases],
        requested_candidates=[f"admissible starts x{args.starts}"],
        objective_versions={"start_basis": "startgen profile basis (Chebyshev radial displacement)"},
        source_files=["sd_sampler_pilot.py", "startgen.py", "mapmetrics.py", "lattice.py",
                      "artifacts.py"],
        calibration_node_source="not used: sampler geometry only")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    cps = corpus()
    lo, hi, rule = SG.profile_bounds(cps)
    say("=" * 104)
    say("SAMPLER-ONLY ACCEPTANCE PILOT -- repaired profile-basis start generator")
    say("=" * 104)
    say(f"  PRIOR FAILURE: independent Sobol in raw monomial k1..k4/p1/p2 over +-3x the corpus")
    say(f"  envelope accepted 0 of 16 proposals. Preserved as")
    say(f"  analysis-output/sd_basins_full.FAILED-monomial-sampler-pilot.log")
    say(f"\n  REPAIR: sample radial DISPLACEMENT at four Chebyshev radii instead of k1..k4.")
    say(f"    rho nodes        {np.round(SG.RHO, 4).tolist()} on {rule['rho_interval']}")
    say(f"    radii (px)       {np.round(SG.RAD_R, 1).tolist()}")
    say(f"    cond(M) raw      {rule['cond_M_raw_radius']:.3e}")
    say(f"    cond(M') normed  {rule['cond_Mprime_normalized']:.3e}   <- the transform actually used")
    say(f"    transform is exact and full-rank: no model degree of freedom is removed")
    say(f"  bounds rule: {rule['centre_rule']}; radial/tangential +-{rule['envelope_factor']:g}x the")
    say(f"    symmetrized corpus envelope IN THIS BASIS (width rule unchanged from the failed run);")
    say(f"    eta +-{LT.ETA_BOUND}")
    say(f"  corpus maps used: {rule['n_corpus_maps']} (stored calibrations of all six cameras)")
    say(f"    radial displacement envelope (px)     {np.round(rule['corpus_radial_disp_envelope_px'], 2).tolist()}")
    say(f"    tangential displacement envelope (px) {np.round(rule['corpus_tangential_disp_envelope_px'], 2).tolist()}")
    say(f"    tangential px per unit p1, p2         {np.round(rule['tangential_px_per_unit_p'], 1).tolist()}")

    R = {"rule": rule, "sobol_seed": SOBOL_SEED, "n_target": args.starts, "cases": {}}
    say(f"\n  {'case':16} {'target':>7} {'accept':>7} {'reject':>7} {'proposals':>10} "
        f"{'rate':>8} {'usable':>7}  top rejection reasons")
    allok = True
    for label, D, free in cases:
        acc, st = SG.generate(args.starts, free, D.xy, cps, SOBOL_SEED)
        top = sorted(st["rejection_reasons"].items(), key=lambda kv: -kv[1])[:3]
        say(f"  {label:16} {st['n_target']:7d} {st['n_accepted']:7d} {st['n_rejected']:7d} "
            f"{st['n_proposals']:10d} {100 * st['acceptance_rate']:7.2f}% "
            f"{str(st['usable']):>7}  {', '.join(f'{k}={v}' for k, v in top)}")
        R["cases"][label] = {"stats": {k: v for k, v in st.items()
                                       if k not in ("bounds_lo", "bounds_hi", "rule")},
                             "accepted_starts": acc,
                             "n_observations": int(D.n), "n_lines": int(D.nline)}
        allok = allok and st["usable"]
        W.document_started(label, doc_key=label.split("/")[0])
        W.document_completed(label, completed_candidates=[f"admissible starts x{args.starts}"])

    say(f"\n  VERDICT: {'the repaired sampler is USABLE on every case' if allok else 'the revised search domain is STILL UNUSABLE on at least one case'}")
    if not allok:
        say(f"  Per the brief, the domain is reported unusable rather than narrowed again.")
    R["all_usable"] = bool(allok)
    path = W.write(R)
    say(f"  wrote {path}   [{time.time() - t0:.1f}s]")
    return 0 if allok else 2


if __name__ == "__main__":
    sys.exit(main())
