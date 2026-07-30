#!/usr/bin/env python3
"""Are the SD-D synthetic failures bad optimization paths, or competitive line-objective solutions?

Round 3 left exactly one question. Two exact synthetic targets produced admissible, locally stable,
restart-verified SD-D solutions carrying 88-359 px of map error while an exact zero-residual solution
existed. Either the optimizer failed to find the truth basin (an initialization problem), or the line
observations genuinely fail to distinguish those maps (structural ambiguity). Those have opposite
consequences for whether SD-D can ever be a fallback.

This script answers it on `synth11` and `synth17` only, using the FROZEN accepted starts already stored
in analysis-output/sd_sampler_pilot_full.json. It does not resample, does not touch the sampling bounds
or basis, does not use rejected proposals, does not remove the production gate from start admissibility,
does not touch real documents, and does not run legacy B.

WHAT IS MEASURED, AND WHY NOT PARAMETER DISTANCE. Solutions are clustered by PROJECTIVELY ALIGNED
corrected-map behaviour (see mapmetrics.py). Two maps differing only by a homography are equivalent
after downstream planar recalibration, so the decision-relevant quantity is what survives removing the
best homography between them. Parameter distance is not used for clustering at all.

Modes:
    --exact   the frozen-start basin search on both synthetics (default)
    --noise   the bounded noise-competition experiment, which requires --exact to have run first

Writes analysis-output/sd_basins_<scope>.{log,json} and sd_basins_noise_<scope>.{log,json}.
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
import mapmetrics as MM

harness_import.ensure_path()
import sd_fast as SF                                                          # noqa: E402
import test_sd_fast as T                                                      # noqa: E402
import test_sd_nonlattice as NL                                               # noqa: E402

LT = harness_import.load("lattice")
OB = harness_import.load("objectives")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
PILOT = os.path.join(OUT, "sd_sampler_pilot_full.json")

# The two round-3 failures. Layout seed -> the synthetic target; truth eta 0.026 as in round 3.
SYNTH = {"synth11": 11, "synth17": 17}
TRUTH_ETA = 0.026

# Empirical residual-scale bracket, NOT an established detector-noise estimate. Taken from the M1
# weighted Sampson residual scale sqrt(loss/n) measured across all six real cameras in round 2, which
# spanned 0.211-0.304 px and which also contains model misfit, so it bounds click noise from above.
NOISE_SIGMAS = (0.10, 0.20, 0.30)

# PREREGISTERED RESCUE RULE, declared before the corrected rerun. Applied SYMMETRICALLY to every fit
# that terminates with status <= 0, regardless of which start it came from or whether rescuing it would
# help or hurt any hypothesis: exactly one retry from the IDENTICAL initial state with twice the
# evaluation limit. The original result is preserved alongside. If the retry also fails the replicate is
# left UNRESOLVED; it is never credited to whichever competitor happened to converge.
RESCUE = {"retries": 1, "max_nfev_multiplier": 2, "identical_initial_state": True,
          "applied_to": "every fit with status <= 0", "on_failure": "replicate left unresolved"}

# The five mutually exclusive outcomes for a paired basin comparison. "Unresolved" exists precisely so a
# capped competitor is never mistaken for a loss.
BASIN_OUTCOMES = ("truth_equivalent_wins", "consequentially_wrong_wins", "completed_but_tied",
                  "unresolved_optimization_failed", "invalid_no_comparison_possible")
TIE_REL = 1e-3          # |dloss| / max(|loss|) below this is a tie, not a win


def _scaled(th):
    return np.asarray(th, float) / SF.SCALE14


# =============================================================== one problem


class Case:
    def __init__(self, label, D, truth, model="M1"):
        self.label = label
        self.D = D
        self.truth = np.asarray(truth, float)
        self.model = model
        self.free = OB.MODELS[model]
        self.base = OB.default_base()
        self.base[[j for j in range(14) if j not in set(self.free)]] = 0.0
        self.pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                          nfree_t=sum(1 for l in D.obs_lines if len(l) == 1),
                          objective="SD", free=self.free)
        self.ev = SF.SDFast(D, self.pk, self.base)
        self.bounds = self.pk.bounds(self.base)
        self.pts = D.xy
        self.grid = MM.frame_grid()

    def p_from_theta(self, th14, pk=None, base=None):
        """Parameter vector at model block `th14`, line nuisances initialized identically for every
        start so no start gains an advantage from a different nuisance treatment."""
        pk = self.pk if pk is None else pk
        base = self.base if base is None else base
        p = np.zeros(pk.n)
        p[:pk.nm] = np.asarray(th14, float)[pk.free] / SF.SCALE14[pk.free]
        th0 = pk.theta(p, base)
        ph, e = OB.init_lines(self.D, th0)
        p[pk.iline:pk.iline + self.D.nline] = ph
        p[pk.iline + self.D.nline:pk.iline + 2 * self.D.nline] = e
        lo, hi = pk.bounds(base)
        return np.clip(p, lo, hi)

    def run(self, th_start, label):
        p0 = self.p_from_theta(th_start)
        c0 = dict(self.ev.counts)
        t0 = time.time()
        res = SF.solve(self.ev, p0, self.bounds)
        dt = time.time() - t0
        return self._record(res, label, dt, c0)

    def _record(self, res, label, dt, c0):
        th = self.pk.theta(res.x, self.base)
        loss = float(res.fun @ res.fun)
        return {"start_label": label, "theta14": th.tolist(), "loss": loss,
                "loss_per_mass": loss / max(float(self.D.w.sum()), 1e-300),
                "status": int(res.status), "optimality": float(res.optimality),
                "nfev": int(res.nfev), "njev": int(res.njev),
                "residual_calls": self.ev.counts["residual"] - c0["residual"],
                "jacobian_calls": self.ev.counts["jacobian"] - c0["jacobian"],
                "solve_s": dt, "p": res.x.tolist()}

    def run_with_rescue(self, th_start, label, rescue=True):
        """One fit, plus the preregistered symmetric rescue retry if it terminated on the cap."""
        first = self.run(th_start, label)
        out = dict(first)
        out["rescued"] = False
        out["first_attempt"] = {k: first[k] for k in ("loss", "status", "nfev", "njev",
                                                     "optimality", "solve_s")}
        if rescue and first["status"] <= 0:
            p0 = self.p_from_theta(th_start)
            c0 = dict(self.ev.counts)
            t0 = time.time()
            r2 = SF.solve(self.ev, p0, self.bounds,
                          max_nfev=RESCUE["max_nfev_multiplier"] * SF.MAX_NFEV)
            rec = self._record(r2, label + "+rescue", time.time() - t0, c0)
            out.update({k: rec[k] for k in ("theta14", "loss", "status", "optimality", "nfev",
                                            "njev", "solve_s", "p")})
            out["rescued"] = True
        return out

    def staged(self):
        """The documented nested non-lattice initialization ladder.

        Uses NO truth and NO lattice information. It starts from the identity map -- centre at the frame
        centre, every coefficient zero -- and frees parameters in nested groups, each stage optimizing
        the COMPLETE unchanged SD-D objective over the whole dataset with the not-yet-freed parameters
        HELD at the previous stage's values (not zeroed):

            stage 1   centre + k1                     low-order radial structure only
            stage 2   + k2, k3, k4, p1, p2            higher-order radial and decentering  (= M0)
            stage 3   + eta                            the full M1 family

        Line nuisances are free at every stage. The reported final fit is a full-M1 optimization of the
        unchanged objective, so the ladder changes only where the optimizer starts.
        """
        ladder = [[0, 1, 2], [0, 1, 2, 3, 4, 5, 9, 10], list(self.free)]
        th = np.zeros(14)
        th[0], th[1] = LT.FRAME_W / 2.0, LT.FRAME_H / 2.0
        stages = []
        res = None
        for si, fr in enumerate(ladder):
            base = _scaled(th)
            pk = OB.Pack(self.model, nline=self.D.nline, ncap=self.D.ncap,
                         nfree_t=sum(1 for l in self.D.obs_lines if len(l) == 1),
                         objective="SD", free=fr)
            ev = SF.SDFast(self.D, pk, base)
            p0 = self.p_from_theta(th, pk=pk, base=base)
            lo, hi = pk.bounds(base)
            t0 = time.time()
            res = SF.solve(ev, p0, (lo, hi))
            th = pk.theta(res.x, base)
            stages.append({"stage": si + 1, "free": fr, "loss": float(res.fun @ res.fun),
                           "status": int(res.status), "nfev": int(res.nfev),
                           "solve_s": time.time() - t0})
        # final record on the canonical evaluator so it is comparable with every other start
        out = self.run(th, "staged-ladder")
        out["staged_stages"] = stages
        return out


def build_case(name, sigma=0.0, rep=0):
    """The synthetic target, optionally with coordinate noise added to the RAW observations.

    Noise is applied AFTER distortion, because detection noise lives in the raw image, and the Dataset
    is then rebuilt from the noisy points so that local scale, Delaunay weights and line nuisance
    initialization all see exactly what a noisy real capture would present.
    """
    seed = SYNTH[name]
    th = T.truth_theta("M1", TRUTH_ETA)
    segs = NL.irregular_target(seed=seed)
    pts, lines = [], []
    for si, P in enumerate(segs):
        P = np.asarray(P, float)
        base = len(pts)
        pts.extend(P.tolist())
        lines.append({"members": list(range(base, base + len(P))), "family": si % 2})
    raw = T.distort_to_raw(np.array(pts, float), th)
    if sigma > 0:
        rng = np.random.default_rng(1000 * SYNTH[name] + int(round(sigma * 1000)) * 10 + rep)
        raw = raw + sigma * rng.standard_normal(raw.shape)
    cap = T.Cap(raw, lines)
    D = OB.Dataset([cap], require_indexed=False, min_inc=1, kappa=3.0)
    return Case(f"{name}/M1", D, th)


# =============================================================== clustering and analysis


def cluster(sols, case, thresh=MM.DISTINCT_BASIN_PX):
    """Greedy single-link clustering on the aligned in-hull median map difference."""
    reps, groups = [], []
    for s in sorted(sols, key=lambda x: x["loss"]):
        for gi, r in enumerate(reps):
            d = MM.map_difference(r["theta14"], s["theta14"], case.grid, case.pts)
            if not MM.distinct_basin(d, thresh)[0]:
                groups[gi].append(s)
                break
        else:
            reps.append(s)
            groups.append([s])
    return reps, groups


def barrier(case, a, b, n=13):
    """Objective along the model-block path between two basins, line nuisances REOPTIMIZED.

    A straight line through all parameters including nuisances is not a barrier calculation: it reports
    a barrier that is really just badly chosen nuisances. Here only the model block is interpolated; at
    each step the line nuisances are re-initialized and then relaxed with the model block held fixed.
    """
    tha = np.asarray(a["theta14"], float)
    thb = np.asarray(b["theta14"], float)
    prof = []
    for t in np.linspace(0.0, 1.0, n):
        th = (1 - t) * tha + t * thb
        base = _scaled(th)
        pk = OB.Pack(case.model, nline=case.D.nline, ncap=case.D.ncap,
                     nfree_t=sum(1 for l in case.D.obs_lines if len(l) == 1),
                     objective="SD", free=[])
        ev = SF.SDFast(case.D, pk, base)
        p = case.p_from_theta(th, pk=pk, base=base)
        lo, hi = pk.bounds(base)
        r = SF.solve(ev, p, (lo, hi), max_nfev=60)
        prof.append({"t": float(t), "loss": float(r.fun @ r.fun)})
    ends = min(prof[0]["loss"], prof[-1]["loss"])
    peak = max(x["loss"] for x in prof)
    interior = max(x["loss"] for x in prof[1:-1]) if n > 2 else peak
    return {"profile": prof, "endpoint_min": ends, "path_peak": peak,
            "interior_peak": interior,
            "barrier_above_lower_endpoint": interior - ends,
            "barrier_relative": (interior - ends) / max(abs(ends), 1e-300),
            "monotone_descent": bool(interior <= max(prof[0]["loss"], prof[-1]["loss"]) + 1e-12)}


def soft_probe(case, sol, noise_loss, n_dir=3):
    """Step along the softest scaled-Jacobian directions by a noise-scale objective change.

    The question is not whether the objective is flat somewhere -- it always is -- but whether the flat
    directions move the corrected map AFTER projective alignment. Each step is sized so the quadratic
    model predicts an objective rise of about `noise_loss`, an amount the data could not resolve, and
    the result is classified as projective gauge, harmless parameter softness, or consequential
    nonprojective softness.
    """
    p = np.asarray(sol["p"], float)
    Jd = case.ev.jacobian(p)
    Jd = Jd.toarray() if hasattr(Jd, "toarray") else np.asarray(Jd)
    _, sv, Vt = np.linalg.svd(Jd, full_matrices=False)
    out = []
    for k in range(1, min(n_dir, Vt.shape[0]) + 1):
        v = Vt[-k]
        s = float(sv[-k])
        # The quadratic model predicts a rise of (s*a)^2, so a = sqrt(budget)/s. For a numerically
        # singular direction s ~ 1e-13 that formula demands a step of ~1e13, which is meaningless: the
        # first attempt produced dloss = 2e26 and a classification derived from it would have been
        # nonsense. So the step is capped relative to the parameter vector's own norm and then
        # BACKTRACKED until the realised dloss is actually near the noise budget. A direction whose
        # smallest tried step still overshoots is reported as `step_uncalibrated`, not classified.
        a0 = math.sqrt(max(noise_loss, 0.0)) / max(s, 1e-300)
        a0 = min(a0, 0.25 * max(float(np.linalg.norm(p)), 1.0))
        best = None
        for sign in (+1.0, -1.0):
            a, rec = a0, None
            for _ in range(40):
                q = np.clip(p + sign * a * v, case.bounds[0], case.bounds[1])
                dl = case.ev.loss(q) - sol["loss"]
                if dl <= 2.0 * noise_loss or a < 1e-12 * a0:
                    th = case.pk.theta(q, case.base)
                    d = MM.map_difference(sol["theta14"], th, case.grid, case.pts)
                    al = d.get("aligned_hull", d["aligned_full"])["median"]
                    rw = d.get("raw_hull", d["raw_full"])["median"]
                    calibrated = dl <= 2.0 * noise_loss
                    rec = {"dir_from_end": k, "sv": s, "step": float(sign * a),
                           "dloss": dl, "noise_budget": noise_loss,
                           "step_calibrated": bool(calibrated),
                           "raw_hull_median_px": rw, "aligned_hull_median_px": al,
                           "gauge_fraction": d["gauge_fraction"],
                           "classification": (
                               "step_uncalibrated" if not calibrated else
                               "consequential_nonprojective" if al > MM.DISTINCT_BASIN_PX else
                               "projective_gauge" if rw > MM.DISTINCT_BASIN_PX else
                               "harmless_parameter_softness")}
                    break
                a *= 0.5
            if rec is not None and (best is None
                                    or (rec["step_calibrated"], rec["aligned_hull_median_px"])
                                    > (best["step_calibrated"], best["aligned_hull_median_px"])):
                best = rec
        if best is not None:
            out.append(best)
    return out


def vs_truth(case, th):
    d = MM.map_difference(case.truth, th, case.grid, case.pts)
    return {"aligned_hull_p95": d.get("aligned_hull", d["aligned_full"])["p95"],
            "aligned_hull_median": d.get("aligned_hull", d["aligned_full"])["median"],
            "aligned_hull_p95": d.get("aligned_hull", d["aligned_full"])["p95"],
            "aligned_hull_max": d.get("aligned_hull", d["aligned_full"])["max"],
            "aligned_full_median": d["aligned_full"]["median"],
            "aligned_full_p95": d["aligned_full"]["p95"],
            "aligned_full_max": d["aligned_full"]["max"],
            "raw_hull_median": d.get("raw_hull", d["raw_full"])["median"],
            "raw_full_median": d["raw_full"]["median"],
            "gauge_fraction": d["gauge_fraction"],
            "hull_coverage": d.get("hull_coverage"),
            "ladder": MM.threshold_ladder(d)}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0.0)) / den
    return (max(0.0, c - h), min(1.0, c + h))


# =============================================================== exact-data search


def run_exact(args, say, W):
    frozen = json.load(open(PILOT))
    R = {"pilot_artifact_sha256": artifacts.file_sha256(PILOT),
         "distinct_basin_px": MM.DISTINCT_BASIN_PX,
         "thresholds_px": list(MM.MAP_THRESHOLDS_PX), "cases": {}}
    for name in SYNTH:
        acc = frozen["results"]["cases"][name]["accepted_starts"]
        case = build_case(name)
        say(f"\n{'=' * 104}\n  {case.label}  (exact data, {case.D.n} observations, "
            f"{case.D.nline} lines)\n{'=' * 104}")
        neff = MM.n_eff(case.D.w)
        say(f"  weight mass {case.D.w.sum():.1f}, n_eff {neff:.1f} "
            f"({100 * neff / case.D.n:.1f}% of n), params {case.pk.n}")
        say(f"  {len(acc)} frozen ordinary starts, used unchanged")

        sols = []
        for s in acc:
            sols.append(case.run(np.asarray(s["theta14"], float), f"sobol{s['index']}"))
        ordinary = {s["start_label"] for s in sols}

        # default initialization = SF.fit_sd's warm start from B on the deduplicated view
        wb = OB.fit(SF.dedup_view(case.D), "B", case.model, base=case.base.copy(), warm=False,
                    max_nfev=3000, free=case.free)
        thB = np.asarray(wb["theta14"], float)
        d_default = case.run(thB, "default-init-B")
        sols.append(d_default)
        ordinary.add("default-init-B")
        # previous SD-D solution: the result the default path produced in rounds 2-3
        sols.append(case.run(np.asarray(d_default["theta14"], float), "previous-SD-D"))
        ordinary.add("previous-SD-D")
        # M0 embedded in M1 at eta = 0
        z = thB.copy(); z[13] = 0.0
        sols.append(case.run(z, "M0-embedded-eta0"))
        ordinary.add("M0-embedded-eta0")
        # the staged non-lattice ladder
        st = case.staged()
        sols.append(st)
        ordinary.add("staged-ladder")
        say(f"  staged ladder stages: " + ", ".join(
            f"s{x['stage']} loss {x['loss']:.4e} ({x['nfev']} nfev)" for x in st["staged_stages"]))
        # truth: DIAGNOSTIC CONTROL ONLY, excluded from the operational denominator
        sols.append(case.run(case.truth, "control:truth"))

        for s in sols:
            s["safety"] = MM.map_safety(s["theta14"], case.pts, steps=20)
            s["spectrum"] = MM.scaled_spectrum(case.ev.jacobian(np.asarray(s["p"], float)),
                                               case.pk.nm)
            s["vs_truth"] = vs_truth(case, s["theta14"])
            s["valid_local_fit"] = bool(s["status"] > 0 and s["safety"]["admissible"])
        keep = [s for s in sols if s["valid_local_fit"]]
        say(f"  {len(keep)} of {len(sols)} finished solutions are admissible valid_local_fit")

        reps, groups = cluster(keep, case)
        best = reps[0]
        say(f"\n  DISTINCT BASINS (aligned in-hull median > {MM.DISTINCT_BASIN_PX} px): {len(reps)}")
        say(f"    {'#':>2} {'n':>3} {'loss':>13} {'loss/mass':>11} {'dLoss vs best':>14} "
            f"{'stat':>4} {'opt':>9} {'lg10cJtJ':>10} {'soft':>4} {'alignTruth':>11} "
            f"{'rawTruth':>10} {'gate':>5} {'mono':>5}")
        for gi, (r, g) in enumerate(zip(reps, groups)):
            vt = r["vs_truth"]
            say(f"    {gi:2d} {len(g):3d} {r['loss']:13.6e} {r['loss_per_mass']:11.4e} "
                f"{r['loss'] - best['loss']:14.6e} {r['status']:4d} {r['optimality']:9.2e} "
                f"{r["spectrum"]["log10_cond_JtJ"]:10.2f} {r['spectrum']['n_soft']:4d} "
                f"{vt['aligned_hull_median']:11.4f} {vt['raw_hull_median']:10.4f} "
                f"{str(r['safety']['gate_ok'])[:5]:>5} "
                f"{str(r['safety']['radial_monotonic'])[:5]:>5}")
            rr = case.run(r["theta14"], f"recheck{gi}")
            dd = MM.map_difference(r["theta14"], rr["theta14"], case.grid, case.pts)
            r["_cluster"] = {"index": gi, "n_members": len(g),
                             "members": [x["start_label"] for x in g],
                             "dloss_vs_best": r["loss"] - best["loss"]}
            r["_recheck"] = {"loss": rr["loss"], "dloss": rr["loss"] - r["loss"],
                             "aligned_move_px":
                                 dd.get("aligned_hull", dd["aligned_full"])["median"],
                             "improved": bool(rr["loss"] < r["loss"] - 1e-6 * abs(r["loss"]))}
            say(f"       members: {', '.join(x['start_label'] for x in g)}")
            say(f"       restart: loss {rr['loss']:.6e} (dloss {rr['loss'] - r['loss']:+.2e}), "
                f"moved {r['_recheck']['aligned_move_px']:.4f} px, "
                f"improved={r['_recheck']['improved']}")

        # truth-equivalent identification and operational recovery rate
        te = [gi for gi, r in enumerate(reps)
              if r["vs_truth"]["aligned_hull_median"] <= MM.DISTINCT_BASIN_PX]
        say(f"\n  truth-equivalent basin index: {te if te else 'NONE FOUND'}")
        fb = [s for s in keep if s["start_label"] in ordinary]
        rec = [s for s in fb if s["vs_truth"]["aligned_hull_median"] <= MM.DISTINCT_BASIN_PX]
        ci = wilson(len(rec), len(fb))
        say(f"  OPERATIONAL RECOVERY (frozen ordinary starts + default + previous + M0-embedded + "
            f"staged; truth EXCLUDED): {len(rec)}/{len(fb)} = "
            f"{100.0 * len(rec) / max(len(fb), 1):.1f}% [{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]%")
        for nm in ("default-init-B", "previous-SD-D", "M0-embedded-eta0", "staged-ladder"):
            m = [s for s in sols if s["start_label"] == nm]
            if m:
                say(f"    {nm:18} loss {m[0]['loss']:.6e}, aligned-vs-truth "
                    f"{m[0]['vs_truth']['aligned_hull_median']:9.4f} px, "
                    f"truth-equivalent={m[0]['vs_truth']['aligned_hull_median'] <= MM.DISTINCT_BASIN_PX}")
        ctl = [s for s in sols if s["start_label"] == "control:truth"][0]
        say(f"    control:truth      loss {ctl['loss']:.6e}, aligned-vs-truth "
            f"{ctl['vs_truth']['aligned_hull_median']:9.4f} px  (diagnostic only)")

        # barrier between truth-equivalent and the most loss-competitive consequential wrong basin
        bars, probes = {}, {}
        wrong = [(gi, r) for gi, r in enumerate(reps)
                 if r["vs_truth"]["aligned_hull_median"] > MM.DISTINCT_BASIN_PX]
        if te and wrong:
            ti = te[0]
            wi, wr = sorted(wrong, key=lambda t: t[1]["loss"])[0]
            say(f"\n  BARRIER truth-equivalent basin {ti} <-> most competitive wrong basin {wi}")
            b = barrier(case, reps[ti], wr)
            bars[f"{ti}->{wi}"] = b
            say(f"    endpoint min {b['endpoint_min']:.6e}, interior peak {b['interior_peak']:.6e}, "
                f"barrier {b['barrier_above_lower_endpoint']:.6e} "
                f"({b['barrier_relative']:+.3e} relative), monotone={b['monotone_descent']}")
        nl = (0.20 ** 2) * MM.n_eff(case.D.w)
        say(f"\n  SOFT-DIRECTION PROBE at basin 0, budget {nl:.4f} "
            f"(0.20 px per effective observation)")
        for tgt, lab in ([(reps[te[0]], f"basin{te[0]}(truth-equiv)")] if te else []) + \
                        [(reps[0], "basin0(lowest loss)")]:
            pr = soft_probe(case, tgt, nl)
            probes[lab] = pr
            for x in pr:
                say(f"    {lab} soft#{x['dir_from_end']} sv {x['sv']:.3e}: dloss {x['dloss']:+.3e}, "
                    f"raw {x['raw_hull_median_px']:8.4f} px, aligned "
                    f"{x['aligned_hull_median_px']:8.4f} px -> {x['classification']}")

        R["cases"][case.label] = {
            "n_observations": int(case.D.n), "n_lines": int(case.D.nline),
            "n_params": int(case.pk.n), "weight_mass": float(case.D.w.sum()), "n_eff": neff,
            "n_frozen_starts": len(acc),
            "n_solutions": len(sols), "n_valid_local_fit": len(keep),
            "n_distinct_basins": len(reps),
            "truth_equivalent_basins": te,
            "operational_recovery": {"k": len(rec), "n": len(fb), "ci95": list(ci),
                                     "excluded_controls": ["control:truth"]},
            "basins": [{k: v for k, v in r.items() if k != "p"} for r in reps],
            "all_solutions": [{k: v for k, v in s.items() if k not in ("p", "spectrum")}
                              for s in sols],
            "barriers": bars, "soft_directions": probes,
        }
        W.document_started(case.label, doc_key=name)
        W.document_completed(case.label, completed_candidates=["frozen-sobol", "controls",
                                                              "staged"])
    return R


# =============================================================== noise competition


def run_noise(args, say, W):
    exact = json.load(open(os.path.join(OUT, "sd_basins_full.json")))["results"]
    R = {"sigmas": list(NOISE_SIGMAS), "n_replicates": args.reps,
         "noise_note": "empirical residual-scale bracket from round-2 M1 fits (0.211-0.304 px), "
                       "NOT an established detector-noise estimate",
         "exact_artifact_sha256": artifacts.file_sha256(
             os.path.join(OUT, "sd_basins_full.json")), "cases": {}}
    for name in args.noise_cases:
        lab = f"{name}/M1"
        ex = exact["cases"][lab]
        te = ex["truth_equivalent_basins"]
        reps = ex["basins"]
        starts = {}
        if te:
            starts["truth-equiv-basin"] = reps[te[0]]["theta14"]
        wrong = sorted([r for gi, r in enumerate(reps)
                        if gi not in te and r["vs_truth"]["aligned_hull_median"]
                        > MM.DISTINCT_BASIN_PX], key=lambda r: r["loss"])[:2]
        for i, r in enumerate(wrong):
            starts[f"wrong-basin-{i}"] = r["theta14"]
        say(f"\n{'=' * 104}\n  NOISE COMPETITION: {lab}\n{'=' * 104}")
        say(f"  representatives carried forward: {list(starts)}")
        say(f"  plus the staged non-lattice ladder, refitted on every replicate")
        rows = []
        for sg in NOISE_SIGMAS:
            for rep in range(args.reps):
                case = build_case(name, sigma=sg, rep=rep)
                got = {}
                for k, th in starts.items():
                    got[k] = case.run_with_rescue(np.asarray(th, float), k)
                st_ = case.staged()
                if st_["status"] <= 0:
                    st_ = case.run_with_rescue(np.asarray(st_["theta14"], float), "staged-ladder")
                    st_["from_staged_ladder"] = True
                got["staged-ladder"] = st_
                for k, s in got.items():
                    s["vs_truth"] = vs_truth(case, s["theta14"])
                    s["gate_v1"] = MM.map_safety(s["theta14"], case.pts, steps=20)
                    s["adm_v2"] = MM.admissibility_v2(s["theta14"])
                    s["completed"] = bool(s["status"] > 0)
                    s["admissible"] = bool(s["adm_v2"]["safe"])
                    s["eligible"] = bool(s["completed"] and s["admissible"])
                order = sorted(got.items(), key=lambda kv: kv[1]["loss"])
                winner = order[0][0]
                MAT = 2.0
                al = {k: v["vs_truth"]["aligned_hull_median"] for k, v in got.items()}
                # ---- 1. DIAGNOSTIC BASIN COMPETITION. Defined ONLY between the exact-data
                # truth-equivalent representative and a genuine wrong-basin representative. It is not
                # defined at all when no wrong-basin representative exists, and a capped competitor
                # yields "unresolved", never a win for the other side.
                A, B = "truth-equiv-basin", "wrong-basin-0"
                if A not in got or B not in got:
                    outcome = "invalid_no_comparison_possible"
                    gap = None
                elif not (got[A]["eligible"] and got[B]["eligible"]):
                    outcome = "unresolved_optimization_failed"
                    gap = None
                else:
                    gap = got[B]["loss"] - got[A]["loss"]
                    scale = max(abs(got[A]["loss"]), abs(got[B]["loss"]), 1e-300)
                    if abs(gap) / scale < TIE_REL:
                        outcome = "completed_but_tied"
                    elif gap > 0:
                        outcome = ("truth_equivalent_wins" if al[A] <= MAT
                                   else "consequentially_wrong_wins")
                    else:
                        outcome = ("consequentially_wrong_wins" if al[B] > MAT
                                   else "truth_equivalent_wins")
                row = {"sigma": sg, "replicate": rep, "lowest_loss_start": winner,
                       "materiality_px": MAT, "tie_rel": TIE_REL,
                       "basin_outcome": outcome, "basin_loss_gap_wrong_minus_truth": gap,
                       # ---- 2. OPERATIONAL RECOVERY: what the frozen staged procedure returned
                       "operational_completed": got["staged-ladder"]["completed"],
                       "operational_admissible": got["staged-ladder"]["admissible"],
                       "operational_aligned_hull_median": al["staged-ladder"],
                       "operational_within_materiality": bool(al["staged-ladder"] <= MAT),
                       "operational_rescued": bool(got["staged-ladder"].get("rescued", False)),
                       # ---- 3. PHYSICAL ACCEPTABILITY of every returned map
                       "losses": {k: v["loss"] for k, v in got.items()},
                       "status": {k: v["status"] for k, v in got.items()},
                       "optimality": {k: v["optimality"] for k, v in got.items()},
                       "nfev": {k: v["nfev"] for k, v in got.items()},
                       "njev": {k: v["njev"] for k, v in got.items()},
                       "solve_s": {k: v["solve_s"] for k, v in got.items()},
                       "rescued": {k: bool(v.get("rescued", False)) for k, v in got.items()},
                       "completed": {k: v["completed"] for k, v in got.items()},
                       "gate_v1_admissible": {k: v["gate_v1"]["admissible"] for k, v in got.items()},
                       "adm_v2_safe": {k: v["adm_v2"]["safe"] for k, v in got.items()},
                       "adm_v2_plausible": {k: v["adm_v2"]["physically_plausible"]
                                            for k, v in got.items()},
                       "adm_v2_roundtrip_px": {k: v["adm_v2"]["roundtrip_px"]
                                               for k, v in got.items()},
                       "adm_v2_expansion": {k: v["adm_v2"]["expansion_ratio"]
                                            for k, v in got.items()},
                       "aligned_hull_median": al,
                       "aligned_hull_p95": {k: v["vs_truth"]["aligned_hull_p95"]
                                            for k, v in got.items()},
                       "aligned_hull_max": {k: v["vs_truth"]["aligned_hull_max"]
                                            for k, v in got.items()},
                       "aligned_full_median": {k: v["vs_truth"]["aligned_full_median"]
                                               for k, v in got.items()},
                       "aligned_full_p95": {k: v["vs_truth"]["aligned_full_p95"]
                                            for k, v in got.items()},
                       "aligned_full_max": {k: v["vs_truth"]["aligned_full_max"]
                                            for k, v in got.items()},
                       "raw_hull_median": {k: v["vs_truth"]["raw_hull_median"]
                                           for k, v in got.items()},
                       "raw_full_median": {k: v["vs_truth"]["raw_full_median"]
                                           for k, v in got.items()},
                       "downstream_error": None,   # undefined: these synthetics have no stereo pair
                       "n_observations": int(case.D.n)}
                rows.append(row)
                say(f"  sigma {sg:.2f} rep {rep}: lowest loss {winner:20} "
                    f"basin_outcome={outcome:32} "
                    f"gap {'n/a' if gap is None else '%+.4f' % gap}  "
                    f"operational aligned {al['staged-ladder']:.3f} px")
                for k, s in order:
                    say(f"      {k:20} loss {s['loss']:12.5f}  aligned-vs-truth "
                        f"{s['vs_truth']['aligned_hull_median']:9.4f} px  "
                        f"materially_wrong={s['vs_truth']['aligned_hull_median'] > MAT}  "
                        f"completed={s['completed']} admV2={s['admissible']}  "
                        f"eligible={s['eligible']}")
        nrep = len(rows)
        # ---- PER-NOISE-LEVEL ACCOUNTING. Levels are analysed separately and never pooled.
        per = {}
        say(f"\n  (1) DIAGNOSTIC BASIN COMPETITION -- resolved pairs only. A competitor that hit the")
        say(f"      evaluation cap even after the rescue retry makes the replicate UNRESOLVED; it is")
        say(f"      never credited as a win to the side that happened to converge.")
        say(f"    {'sigma':>6} {'truth':>6} {'wrong':>6} {'tied':>5} {'unres':>6} {'invalid':>8} "
            f"{'RESOLVED N':>11}  wrong-wins rate [95% CI]")
        for sg in NOISE_SIGMAS:
            sub = [r for r in rows if r["sigma"] == sg]
            b = {o: sum(1 for r in sub if r["basin_outcome"] == o) for o in BASIN_OUTCOMES}
            den = (b["truth_equivalent_wins"] + b["consequentially_wrong_wins"]
                   + b["completed_but_tied"])
            ci = wilson(b["consequentially_wrong_wins"], den) if den else (0.0, 1.0)
            rate = (f"{b['consequentially_wrong_wins']}/{den} "
                    f"[{100 * ci[0]:.0f}, {100 * ci[1]:.0f}]%") if den else "UNDEFINED (N=0)"
            say(f"    {sg:6.2f} {b['truth_equivalent_wins']:6d} "
                f"{b['consequentially_wrong_wins']:6d} {b['completed_but_tied']:5d} "
                f"{b['unresolved_optimization_failed']:6d} "
                f"{b['invalid_no_comparison_possible']:8d} {den:11d}  {rate}")
            gaps = [r["basin_loss_gap_wrong_minus_truth"] for r in sub
                    if r["basin_loss_gap_wrong_minus_truth"] is not None]
            o = {"n": len(sub),
                 "completed": sum(1 for r in sub if r["operational_completed"]),
                 "admissible": sum(1 for r in sub if r["operational_admissible"]),
                 "within_materiality": sum(1 for r in sub
                                           if r["operational_within_materiality"]),
                 "rescued": sum(1 for r in sub if r["operational_rescued"]),
                 "aligned_hull_median": [r["operational_aligned_hull_median"] for r in sub],
                 "aligned_hull_p95": [r["aligned_hull_p95"]["staged-ladder"] for r in sub],
                 "aligned_hull_max": [r["aligned_hull_max"]["staged-ladder"] for r in sub],
                 "aligned_full_median": [r["aligned_full_median"]["staged-ladder"] for r in sub],
                 "aligned_full_max": [r["aligned_full_max"]["staged-ladder"] for r in sub],
                 "raw_hull_median": [r["raw_hull_median"]["staged-ladder"] for r in sub]}
            o["within_materiality_ci95"] = list(wilson(o["within_materiality"], o["n"]))
            per[str(sg)] = {"basin": b, "resolved_denominator": den,
                            "wrong_wins_ci95": list(ci), "loss_gaps_resolved": gaps,
                            "operational": o,
                            "fits_total": sum(len(r["status"]) for r in sub),
                            "fits_capped_before_rescue":
                                sum(1 for r in sub for k in r["status"]
                                    if r["nfev"][k] >= SF.MAX_NFEV and not r["rescued"][k]),
                            "fits_rescued": sum(1 for r in sub for k in r["rescued"]
                                                if r["rescued"][k]),
                            "fits_not_completed": sum(1 for r in sub for k in r["completed"]
                                                      if not r["completed"][k]),
                            "gate_v1_rejections": sum(1 for r in sub
                                                      for k in r["gate_v1_admissible"]
                                                      if not r["gate_v1_admissible"][k]),
                            "adm_v2_unsafe": sum(1 for r in sub for k in r["adm_v2_safe"]
                                                 if not r["adm_v2_safe"][k]),
                            "adm_v2_implausible": sum(1 for r in sub for k in r["adm_v2_plausible"]
                                                      if not r["adm_v2_plausible"][k])}
        say(f"\n  (2) OPERATIONAL RECOVERY -- frozen staged initializer + fixed restart policy, "
            f"no truth-derived start")
        say(f"    {'sigma':>6} {'n':>4} {'completed':>10} {'admissible':>11} {'within 2px':>21} "
            f"{'rescued':>8}  aligned-hull med/p95/max px")
        for sg in NOISE_SIGMAS:
            o = per[str(sg)]["operational"]
            say(f"    {sg:6.2f} {o['n']:4d} {o['completed']:10d} {o['admissible']:11d} "
                f"{o['within_materiality']:2d}/{o['n']} "
                f"[{100 * o['within_materiality_ci95'][0]:3.0f},"
                f"{100 * o['within_materiality_ci95'][1]:3.0f}]% {o['rescued']:8d}  "
                f"{np.median(o['aligned_hull_median']):6.2f} / "
                f"{np.median(o['aligned_hull_p95']):6.2f} / {max(o['aligned_hull_max']):8.2f}")
        say(f"\n  (3) FITS, RESCUES AND SAFETY GATES over all fits at each level")
        say(f"    {'sigma':>6} {'fits':>5} {'notCompleted':>13} {'rescued':>8} {'gateV1rej':>10} "
            f"{'admV2unsafe':>12} {'admV2implaus':>13}")
        for sg in NOISE_SIGMAS:
            v = per[str(sg)]
            say(f"    {sg:6.2f} {v['fits_total']:5d} {v['fits_not_completed']:13d} "
                f"{v['fits_rescued']:8d} {v['gate_v1_rejections']:10d} {v['adm_v2_unsafe']:12d} "
                f"{v['adm_v2_implausible']:13d}")
        # Withdrawn: the previous run reported "0/20 wrong wins" and "2/20 wrong wins" with a
        # denominator of 20, but a paired basin comparison requires BOTH competitors to complete and be
        # admissible. The corrected accounting above reports resolved denominators explicitly, and for
        # synth11 there is no wrong-basin representative at all, so basin competition is undefined there
        # rather than 0-for-20.
        tot = {o: sum(1 for r in rows if r["basin_outcome"] == o) for o in BASIN_OUTCOMES}
        say(f"\n  ACROSS ALL LEVELS (listed for completeness; the per-level tables above are the "
            f"result -- levels are not pooled for inference)")
        for o in BASIN_OUTCOMES:
            say(f"    {o:34} {tot[o]:4d} of {len(rows)}")
        # Every attempted fit and every failure is preserved here, per replicate and per start. An
        # earlier patch dropped this assignment, so a completed run wrote empty `cases` -- the tables
        # were printed to the log but the machine-readable record was lost.
        R["cases"][lab] = {"rows": rows, "n_replicates": len(rows), "per_sigma": per,
                           "rescue_rule": RESCUE,
                           "basin_outcome_categories": list(BASIN_OUTCOMES),
                           "across_all_levels_counts": tot,
                           "note": "levels are analysed separately; the across-all-levels counts are "
                                   "listed for completeness and are not pooled for inference"}
        W.document_started(lab, doc_key=name)
        W.document_completed(lab, completed_candidates=[f"sigma x{len(NOISE_SIGMAS)}",
                                                        f"reps x{args.reps}"])
    return R


# =============================================================== frozen operational procedure
#
# FROZEN 2026-07-30, before the benchmark was generated. Hashed in the artifact. No case-specific
# initial states, no manual selection among solutions, no truth- or lattice-derived starts, and no
# change after examining any holdout.
OPERATIONAL = {
    "id": "staged-nonlattice-v1",
    "ladder": [[0, 1, 2], [0, 1, 2, 3, 4, 5, 9, 10], "MODELS[model]"],
    "stage_start": "identity map: centre at frame centre, every coefficient zero",
    "held_parameters": "held at the previous stage's values, not zeroed (zero_held=False semantics)",
    "line_nuisances": "free at every stage, initialized by total-least-squares on corrected points",
    "final_fit": "full unchanged SD-D objective over the complete dataset",
    "solver": {"ftol": SF.FTOL, "xtol": SF.XTOL, "gtol": SF.GTOL, "max_nfev": SF.MAX_NFEV},
    "restart_set": {"n": 2, "rule": "plain restart from the staged solution, then one restart from "
                                    "the staged solution with the model block scaled by 1.02 "
                                    "(deterministic, no randomness), accept the lower loss"},
    "admissibility": "mapmetrics.admissibility_v2 (experimental), safe AND physically_plausible",
    "uses_truth": False, "uses_lattice": False,
}


def operational_fit(case):
    """The FROZEN operational procedure: staged ladder plus the fixed 2-element restart set."""
    cands = [case.staged()]
    th = np.asarray(cands[0]["theta14"], float).copy()
    cands.append(case.run(th, "op-restart-0"))
    th2 = th.copy()
    th2[case.free] = th2[case.free] * 1.02
    cands.append(case.run(th2, "op-restart-1"))
    best = min(cands, key=lambda r: r["loss"])
    best = dict(best)
    best["operational_candidates"] = [{"label": c["start_label"], "loss": c["loss"],
                                       "status": c["status"]} for c in cands]
    return best


# =============================================================== pre-registered benchmark design


BENCH_FACTORS = {
    "resolution": [(1920.0, 1080.0), (1280.0, 960.0), (3840.0, 2160.0), (1440.0, 1080.0)],
    "distortion_strength": ["mild", "moderate", "strong"],
    "radial_sign": ["barrel", "pincushion"],
    "centre_offset": ["centered", "offset"],
    "tangential": ["none", "small", "large"],
    "truth_model": ["M0", "M1"],
    "misspecification": ["none", "out_of_model"],
    "geometry": ["orthogonal2", "diverse3plus", "irregular", "near_parallel"],
    "coverage": ["central", "broad", "asymmetric", "poor_edge"],
    "segment_length": ["short", "long", "mixed"],
    "fragmentation": ["none", "fragmented_missing"],
    "intersections": ["shared", "separate_incidences", "none"],
    "constraint_mix": ["mostly_single", "mostly_multi", "mixed"],
    "density": ["uniform", "uneven", "redundant_local", "expanded_support"],
    "duplicates": ["none", "duplicate_records", "missing_records"],
    "noise_anisotropy": ["isotropic", "anisotropic"],
    "gross_errors": ["none", "few_outliers"],
    "membership_errors": ["none", "wrong_membership"],
    "lattice_indexing": ["not_applicable", "valid", "missing", "erroneous"],
}


def benchmark_design(n_dev=24, n_hold=32, seed=20260730):
    """Maximin fractional-factorial design over BENCH_FACTORS, split by GEOMETRY FAMILY.

    Not a Cartesian product: the factor space is ~4e8 cells. Cells are drawn by maximin selection on
    normalized Hamming distance so the design is spread rather than clustered, then split so that no
    geometry family appears in both development and holdout -- splitting only by noise replicate would
    let close variants of the same layout leak across the boundary.
    """
    rng = np.random.default_rng(seed)
    keys = sorted(BENCH_FACTORS)
    pool = []
    for _ in range(4000):
        pool.append({k: BENCH_FACTORS[k][int(rng.integers(len(BENCH_FACTORS[k])))] for k in keys})
    chosen = [pool[0]]
    while len(chosen) < n_dev + n_hold:
        best, bd = None, -1
        for c in pool:
            d = min(sum(1 for k in keys if c[k] != s[k]) for s in chosen)
            if d > bd:
                best, bd = c, d
        chosen.append(best)
        pool.remove(best)
    fam = sorted({c["geometry"] for c in chosen})
    dev_fams = set(fam[: max(1, len(fam) // 2)])
    dev = [c for c in chosen if c["geometry"] in dev_fams][:n_dev]
    hold = [c for c in chosen if c["geometry"] not in dev_fams][:n_hold]
    return {"development": dev, "holdout": hold, "seed": seed,
            "factors": {k: [list(v) if isinstance(v, tuple) else v for v in BENCH_FACTORS[k]]
                        for k in keys},
            "dev_geometry_families": sorted(dev_fams),
            "hold_geometry_families": sorted(set(fam) - dev_fams),
            "n_dev": len(dev), "n_hold": len(hold), "replicates_per_cell": 3,
            "sentinels_excluded": ["synth11", "synth17", "pool", "8mm", "mid"]}




# =============================================================== replacement benchmarks (v2)
#
# The v1 manifest (sha256 3b7b56098eae36a15817a3d911dd0d8f3d352644a99079d0f7406004d0e9556d) is
# PRESERVED but RETIRED FOR EXECUTION: it split development from holdout BY GEOMETRY FAMILY, so
# geometry class was perfectly confounded with split (development got diverse3plus and irregular,
# holdout got near_parallel and orthogonal2). Any holdout result from it would have measured geometry
# class, not generalization. It is not deleted or overwritten.
#
# v2 replaces it with TWO benchmarks. Neither is fitted in this tranche.

GEOM_CLASSES = ("orthogonal2", "diverse3plus", "irregular", "near_parallel")
RESOLUTIONS = {"1920x1080": (1920.0, 1080.0), "1280x960": (1280.0, 960.0),
               "2560x1440": (2560.0, 1440.0), "1440x1080": (1440.0, 1080.0)}
CLEAN_FACTORS = {
    "geometry": list(GEOM_CLASSES),
    "resolution": list(RESOLUTIONS),
    "distortion_strength": ["mild", "moderate", "strong"],
    "radial_family": ["barrel", "pincushion"],
    "centre": ["centered", "offset"],
    "truth_model": ["M0", "M1"],
    "coverage": ["central", "broad", "asymmetric", "weak_edge"],
    "intersections": ["shared", "separate_incidences", "none"],
    "density": ["uniform", "uneven"],
    "noise_anisotropy": ["isotropic", "anisotropic"],
}
CORRUPTIONS = ["duplicate_records", "missing_records", "gross_coordinate_errors",
               "wrong_membership", "lattice_index_omission", "lattice_index_error",
               "out_of_model_distortion"]
NOISE_SIGMA_BENCH = 0.20


def _truth_for(cell, rng):
    """Generating map for a cell. Strength is set in NORMALIZED radial displacement, so it means the
    same thing at every resolution."""
    w, h = RESOLUTIONS[cell["resolution"]]
    rmax = float(np.hypot(w / 2, h / 2))
    frac = {"mild": 0.02, "moderate": 0.08, "strong": 0.20}[cell["distortion_strength"]]
    sign = 1.0 if cell["radial_family"] == "barrel" else -1.0
    th = np.zeros(14)
    if cell["centre"] == "centered":
        th[0], th[1] = w / 2, h / 2
    else:
        th[0], th[1] = w / 2 + 0.12 * w, h / 2 - 0.10 * h
    # k1 chosen so the radial displacement at rmax equals frac * rmax
    th[2] = sign * frac / (rmax ** 2)
    th[3] = sign * 0.10 * frac / (rmax ** 4)
    th[9] = 1e-6 * sign
    th[10] = -6e-7 * sign
    if cell["truth_model"] == "M1":
        th[13] = 0.026
    return th


def _layout(cell, family_seed):
    """Segments in IDEAL coordinates for one layout family. `family_seed` is disjoint across subsets."""
    w, h = RESOLUTIONS[cell["resolution"]]
    rng = np.random.default_rng(family_seed)
    cov = cell["coverage"]
    if cov == "central":
        box = (0.30 * w, 0.70 * w, 0.30 * h, 0.70 * h)
    elif cov == "broad":
        box = (0.06 * w, 0.94 * w, 0.06 * h, 0.94 * h)
    elif cov == "asymmetric":
        box = (0.05 * w, 0.55 * w, 0.05 * h, 0.95 * h)
    else:                                     # weak_edge
        box = (0.18 * w, 0.82 * w, 0.18 * h, 0.82 * h)
    x0, x1, y0, y1 = box

    def ln(a, b, n):
        t = np.linspace(0, 1, n)[:, None]
        return np.asarray(a, float)[None] * (1 - t) + np.asarray(b, float)[None] * t

    npts = 13
    segs = []
    if cell["geometry"] == "orthogonal2":
        for i in range(5):
            yy = y0 + (y1 - y0) * (i + 0.5) / 5
            segs.append(ln((x0, yy), (x1, yy), npts))
        for i in range(5):
            xx = x0 + (x1 - x0) * (i + 0.5) / 5
            segs.append(ln((xx, y0), (xx, y1), npts))
    elif cell["geometry"] == "diverse3plus":
        for ang in (0.0, 45.0, 90.0, 135.0, 22.5, 67.5):
            for k in range(2):
                a = math.radians(ang)
                cx = x0 + (x1 - x0) * (0.3 + 0.4 * k)
                cy = y0 + (y1 - y0) * (0.3 + 0.4 * k)
                L = 0.42 * min(x1 - x0, y1 - y0)
                segs.append(ln((cx - L * math.cos(a), cy - L * math.sin(a)),
                               (cx + L * math.cos(a), cy + L * math.sin(a)), npts))
    elif cell["geometry"] == "irregular":
        for _ in range(11):
            for _ in range(60):
                a = np.array([rng.uniform(x0, x1), rng.uniform(y0, y1)])
                an = rng.uniform(0, math.pi)
                L = rng.uniform(0.30, 0.85) * min(x1 - x0, y1 - y0)
                b = a + L * np.array([math.cos(an), math.sin(an)])
                if x0 <= b[0] <= x1 and y0 <= b[1] <= y1:
                    break
            segs.append(ln(a, b, npts))
    else:                                     # near_parallel
        base = rng.uniform(0, math.pi)
        for i in range(10):
            a0 = base + math.radians(rng.uniform(-6, 6))
            off = (i - 4.5) / 5.0
            cx = 0.5 * (x0 + x1) + off * 0.42 * (x1 - x0) * math.sin(base)
            cy = 0.5 * (y0 + y1) - off * 0.42 * (y1 - y0) * math.cos(base)
            L = 0.45 * min(x1 - x0, y1 - y0)
            segs.append(ln((cx - L * math.cos(a0), cy - L * math.sin(a0)),
                           (cx + L * math.cos(a0), cy + L * math.sin(a0)), npts))
    if cell["density"] == "uneven":
        out = []
        for i, P in enumerate(segs):
            k = 5 if i % 3 == 0 else (npts if i % 3 == 1 else 22)
            out.append(ln(P[0], P[-1], k))
        segs = out
    return segs


def _intersection_spec(segs, mode, w, h):
    """Computed intersections, represented as declared. Returns (shared_list, separate_list)."""
    if mode == "none":
        return [], []
    ends = [(np.asarray(P)[0], np.asarray(P)[-1]) for P in segs]
    pts = []
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            q = NL.intersect(*ends[i], *ends[j])
            if q is None:
                continue
            if 0.04 * w < q[0] < 0.96 * w and 0.04 * h < q[1] < 0.96 * h:
                pts.append((tuple(q), [i, j]))
    pts = pts[:12]
    if mode == "shared":
        return pts, []
    return [], pts                        # separate_incidences: one record per line


def build_bench_dataset(cell, replicate, corruption=None):
    """Deterministic dataset for one (cell, replicate). Returns a dict with everything needed to audit."""
    w, h = RESOLUTIONS[cell["resolution"]]
    th = _truth_for(cell, None)
    segs = _layout(cell, cell["family_seed"])
    shared, separate = _intersection_spec(segs, cell["intersections"], w, h)
    pts, lines = [], []
    for si, P in enumerate(segs):
        P = np.asarray(P, float)
        b = len(pts)
        pts.extend(P.tolist())
        lines.append({"members": list(range(b, b + len(P))), "family": si % 2})
    for xy, li in shared:                     # ONE observation on several lines
        i = len(pts); pts.append(list(xy))
        for l in li:
            lines[l]["members"].append(i)
    for xy, li in separate:                   # one observation PER line, coincident
        for l in li:
            i = len(pts); pts.append(list(xy))
            lines[l]["members"].append(i)
    ideal = np.array(pts, float)
    raw_clean = T.distort_to_raw(ideal, th)
    extra = {}
    if corruption == "out_of_model_distortion":
        # a small non-Brown-Conrady term the model cannot represent
        c = th[:2]
        d = raw_clean - c[None]
        r = np.linalg.norm(d, axis=1, keepdims=True)
        ang = np.arctan2(d[:, 1], d[:, 0])[:, None]
        raw_clean = raw_clean + 0.9 * np.cos(3 * ang) * (r / max(w, h)) * np.ones((1, 2))
        extra["out_of_model_amplitude_px"] = 0.9
    rng = np.random.default_rng(hash((cell["cell_id"], replicate)) % (2 ** 32))
    sx = NOISE_SIGMA_BENCH
    sy = NOISE_SIGMA_BENCH if cell["noise_anisotropy"] == "isotropic" else 0.5 * NOISE_SIGMA_BENCH
    noise = np.stack([sx * rng.standard_normal(len(raw_clean)),
                      sy * rng.standard_normal(len(raw_clean))], axis=1)
    raw = raw_clean + noise
    if corruption == "gross_coordinate_errors":
        k = max(1, int(0.02 * len(raw)))
        idx = np.random.default_rng(7 + replicate).choice(len(raw), k, replace=False)
        raw[idx] += 25.0
        extra["gross_error_indices"] = idx.tolist()
    if corruption == "duplicate_records":
        lines = lines + [dict(lines[0]), dict(lines[1])]
        extra["duplicated_line_indices"] = [0, 1]
    if corruption == "missing_records":
        extra["removed_line_indices"] = [2]
        lines = [l for i, l in enumerate(lines) if i != 2]
    if corruption == "wrong_membership":
        lines = [dict(l) for l in lines]
        if len(lines) >= 2 and len(lines[0]["members"]) > 3:
            moved = lines[0]["members"].pop()
            lines[1]["members"].append(moved)
            extra["moved_observation"] = int(moved)
    cap = T.Cap(raw, lines)
    if corruption in ("lattice_index_omission", "lattice_index_error"):
        rc = np.full((len(raw), 2), np.nan)
        for li, l in enumerate(lines[:5]):
            for k2, m in enumerate(l["members"]):
                rc[m] = (li, k2)
        if corruption == "lattice_index_error" and len(raw) > 6:
            rc[3] = (99, 99)
            extra["corrupted_index_at"] = 3
        cap.rc = rc
    D = OB.Dataset([cap], require_indexed=False, min_inc=1, kappa=3.0)
    return {"dataset": D, "cap": cap, "truth": th, "ideal": ideal, "raw_clean": raw_clean,
            "raw": raw, "noise": noise, "frame": (w, h), "lines": lines,
            "shared": shared, "separate": separate, "sigma_xy": (sx, sy),
            "corruption": corruption, "extra": extra}


def _maximin_cells(factors, n, seed, forced=None, pool_size=3000):
    rng = np.random.default_rng(seed)
    keys = sorted(factors)
    pool = [{k: factors[k][int(rng.integers(len(factors[k])))] for k in keys}
            for _ in range(pool_size)]
    chosen = list(forced or [])
    if not chosen:
        chosen = [pool.pop(0)]
    while len(chosen) < n and pool:
        best, bd = None, -1
        for c in pool:
            d = min(sum(1 for k in keys if c[k] != s[k]) for s in chosen)
            if d > bd:
                best, bd = c, d
        chosen.append(best); pool.remove(best)
    return chosen[:n]


def design_clean(n_dev=20, n_hold=20, seed=20260731):
    """Benchmark A. EVERY geometry class appears in BOTH subsets; layout families are disjoint."""
    out = {}
    for subset, base, n in (("development", 100000, n_dev), ("holdout", 900000, n_hold)):
        per = max(1, n // len(GEOM_CLASSES))
        cells = []
        for gi, g in enumerate(GEOM_CLASSES):
            f = {k: v for k, v in CLEAN_FACTORS.items() if k != "geometry"}
            sub = _maximin_cells(f, per, seed + 17 * gi + (0 if subset == "development" else 1))
            for j, c in enumerate(sub):
                c = dict(c); c["geometry"] = g; c["subset"] = subset
                # layout family ids are disjoint by construction between subsets
                c["layout_family_id"] = f"{g}-{subset[:3]}-{j}"
                c["family_seed"] = base + 1000 * gi + j
                c["cell_id"] = f"A-{subset[:3]}-{g}-{j}"
                cells.append(c)
        out[subset] = cells
    return out


def design_corruption(clean, n_base=4, seed=20260732):
    """Benchmark B. One corruption at a time on selected clean bases, paired with the clean case."""
    out = {}
    for subset in ("development", "holdout"):
        bases = [c for c in clean[subset]
                 if c["geometry"] in ("orthogonal2", "diverse3plus", "irregular", "near_parallel")]
        bases = bases[:n_base]
        cells = []
        for b in bases:
            cells.append({**b, "corruption": None,
                          "cell_id": b["cell_id"] + "-B-clean", "benchmark": "B"})
            for cr in CORRUPTIONS:
                cells.append({**b, "corruption": cr,
                              "cell_id": b["cell_id"] + "-B-" + cr, "benchmark": "B"})
        out[subset] = cells
    return out




def validate_generator(clean, corrupt, say):
    """Every check the brief requires, run BEFORE the manifests are hashed.

    Validation cases are diagnostics only and are never counted as benchmark outcomes.
    """
    ok, fail = [], []

    def chk(name, cond, detail=""):
        (ok if cond else fail).append(name)
        say(f"    [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")

    # determinism
    a = build_bench_dataset(clean["development"][0], 0)
    b = build_bench_dataset(clean["development"][0], 0)
    chk("deterministic reproduction from manifest + seed",
        np.array_equal(a["raw"], b["raw"]) and np.array_equal(a["truth"], b["truth"]))
    c = build_bench_dataset(clean["development"][0], 1)
    chk("different replicate gives different noise, same truth and same clean geometry",
        (not np.array_equal(a["raw"], c["raw"])) and np.array_equal(a["truth"], c["truth"])
        and np.array_equal(a["raw_clean"], c["raw_clean"]))

    # layout-family leakage
    dev_f = {x["layout_family_id"] for x in clean["development"]}
    hol_f = {x["layout_family_id"] for x in clean["holdout"]}
    dev_s = {x["family_seed"] for x in clean["development"]}
    hol_s = {x["family_seed"] for x in clean["holdout"]}
    chk("no layout_family_id crosses the split", not (dev_f & hol_f),
        f"{len(dev_f)} dev, {len(hol_f)} holdout families, overlap {len(dev_f & hol_f)}")
    chk("no family_seed crosses the split", not (dev_s & hol_s))
    chk("every geometry class present in BOTH subsets",
        {x["geometry"] for x in clean["development"]} == set(GEOM_CLASSES)
        == {x["geometry"] for x in clean["holdout"]})

    # generating maps satisfy their declared validity class
    bad = []
    for cell in clean["development"][:6] + clean["holdout"][:6]:
        th = _truth_for(cell, None)
        w, h = RESOLUTIONS[cell["resolution"]]
        cert = MM.certify_forward_injective(th, w=w, h=h, max_cells=600)
        if cert["verdict"] == "refuted_not_injective":
            bad.append((cell["cell_id"], cert["verdict"]))
    chk("sampled generating maps are not refuted as non-injective", not bad, f"{bad}")

    # noiseless observations lie exactly on their generating lines
    worst = 0.0
    for cell in clean["development"][:4]:
        d = build_bench_dataset(cell, 0)
        idl = d["ideal"]
        for l in d["lines"]:
            P = idl[l["members"]]
            if len(P) < 3:
                continue
            q = P - P.mean(axis=0)
            _, sv, _ = np.linalg.svd(q, full_matrices=False)
            worst = max(worst, float(sv[-1]))
    chk("noiseless ideal observations are exactly collinear per line", worst < 1e-8,
        f"worst off-line singular value {worst:.3e} px")

    # forward/inverse consistency of the ideal->raw construction
    d = build_bench_dataset(clean["development"][0], 0)
    chk("distort_to_raw round-trips: U(raw_clean) == ideal",
        float(np.abs(LT.U(d["raw_clean"], d["truth"]) - d["ideal"]).max()) < 1e-6,
        f"max {float(np.abs(LT.U(d['raw_clean'], d['truth']) - d['ideal']).max()):.3e} px")

    # realized noise covariance matches the request
    rows = []
    for cell in clean["development"]:
        if cell["noise_anisotropy"] not in ("isotropic", "anisotropic"):
            continue
        acc = []
        for r in range(6):
            acc.append(build_bench_dataset(cell, r)["noise"])
        N = np.vstack(acc)
        rows.append((cell["noise_anisotropy"], N.std(axis=0)))
    iso = np.array([r[1] for r in rows if r[0] == "isotropic"])
    ani = np.array([r[1] for r in rows if r[0] == "anisotropic"])
    chk("isotropic cells realize sx ~ sy ~ requested sigma",
        len(iso) and abs(iso[:, 0].mean() - NOISE_SIGMA_BENCH) < 0.03
        and abs(iso[:, 1].mean() - NOISE_SIGMA_BENCH) < 0.03,
        f"mean sx {iso[:, 0].mean():.4f}, sy {iso[:, 1].mean():.4f}, requested {NOISE_SIGMA_BENCH}"
        if len(iso) else "no isotropic cells")
    chk("anisotropic cells realize sy/sx ~ 0.5",
        len(ani) and abs((ani[:, 1] / ani[:, 0]).mean() - 0.5) < 0.06,
        f"mean sy/sx {(ani[:, 1] / ani[:, 0]).mean():.4f}" if len(ani) else "none")

    # intersections represented as declared
    for mode in ("shared", "separate_incidences", "none"):
        cs = [c for c in clean["development"] if c["intersections"] == mode]
        if not cs:
            say(f"    [note] no development cell with intersections={mode}")
            continue
        d = build_bench_dataset(cs[0], 0)
        inc = np.array([len(l) for l in d["dataset"].obs_lines])
        if mode == "shared":
            chk("shared intersections give multiply-constrained observations",
                int((inc >= 2).sum()) > 0, f"{int((inc >= 2).sum())} of {d['dataset'].n}")
        elif mode == "separate_incidences":
            nc = d["dataset"].winfo["n_coincident_clusters"]
            chk("separate incidences give coincident clusters, not shared observations",
                nc > 0, f"{nc} coincident clusters")
        else:
            chk("intersections=none declares no shared points", not d["shared"] and not d["separate"])

    # density and coverage realized quantitatively
    du = [c for c in clean["development"] if c["density"] == "uniform"]
    dv = [c for c in clean["development"] if c["density"] == "uneven"]
    if du and dv:
        cu = build_bench_dataset(du[0], 0)["dataset"]
        cv = build_bench_dataset(dv[0], 0)["dataset"]
        pu = np.array([len(l["members"]) for l in build_bench_dataset(du[0], 0)["lines"]])
        pv = np.array([len(l["members"]) for l in build_bench_dataset(dv[0], 0)["lines"]])
        chk("uneven density realizes a wider per-line point spread than uniform",
            pv.std() > pu.std(), f"uniform std {pu.std():.2f}, uneven std {pv.std():.2f}")
    cc = [c for c in clean["development"] if c["coverage"] == "central"]
    cb = [c for c in clean["development"] if c["coverage"] == "broad"]
    if cc and cb:
        Dc = build_bench_dataset(cc[0], 0); Db = build_bench_dataset(cb[0], 0)
        wc, hc = Dc["frame"]; wb2, hb2 = Db["frame"]
        # numpy 2 removed ndarray.ptp()
        sc = (np.ptp(Dc["raw"][:, 0]) / wc) * (np.ptp(Dc["raw"][:, 1]) / hc)
        sb = (np.ptp(Db["raw"][:, 0]) / wb2) * (np.ptp(Db["raw"][:, 1]) / hb2)
        chk("broad coverage spans more normalized frame area than central",
            sb > sc, f"central {sc:.3f}, broad {sb:.3f}")

    # corruptions affect only their declared component
    base = corrupt["development"][0]
    cl = build_bench_dataset(base, 0, corruption=None)
    for cr in CORRUPTIONS:
        d = build_bench_dataset(base, 0, corruption=cr)
        if cr == "duplicate_records":
            chk(f"{cr}: only line records change",
                len(d["lines"]) > len(cl["lines"]) and np.array_equal(d["raw"], cl["raw"]))
            chk(f"{cr}: Dataset deduplicates and reports it",
                d["dataset"].info["merged_duplicate_line_records"] >= 1)
        elif cr == "missing_records":
            chk(f"{cr}: only line records change",
                len(d["lines"]) < len(cl["lines"]) and np.array_equal(d["raw"], cl["raw"]))
        elif cr == "gross_coordinate_errors":
            n_diff = int((np.abs(d["raw"] - cl["raw"]) > 1e-9).any(axis=1).sum())
            chk(f"{cr}: only a small subset of coordinates change",
                0 < n_diff <= max(1, int(0.05 * len(cl["raw"]))) and len(d["lines"]) == len(cl["lines"]),
                f"{n_diff} of {len(cl['raw'])} observations perturbed")
        elif cr == "wrong_membership":
            chk(f"{cr}: coordinates unchanged, membership changed",
                np.array_equal(d["raw"], cl["raw"]) and d["lines"] != cl["lines"])
        elif cr == "out_of_model_distortion":
            chk(f"{cr}: coordinates change, memberships do not",
                (not np.array_equal(d["raw"], cl["raw"])) and len(d["lines"]) == len(cl["lines"]))
        elif cr.startswith("lattice_index"):
            fin = np.isfinite(d["cap"].rc).all(axis=1)
            chk(f"{cr}: lattice indices are populated for a subset",
                fin.any() and np.array_equal(d["raw"], cl["raw"]),
                f"{int(fin.sum())} of {len(d['raw'])} indexed")

    # valid indexing passes and erroneous indexing fails, independently
    dv2 = build_bench_dataset(base, 0, corruption="lattice_index_omission")
    de2 = build_bench_dataset(base, 0, corruption="lattice_index_error")
    fin_v = np.isfinite(dv2["cap"].rc).all(axis=1).sum()
    bad_e = (de2["cap"].rc[de2["extra"].get("corrupted_index_at", 0)] == 99).all()
    chk("omission case yields a partially indexed capture", fin_v > 0, f"{int(fin_v)} indexed")
    chk("error case injects a detectably wrong index", bool(bad_e))

    # normalized <-> pixel round trip
    w, h = RESOLUTIONS["1920x1080"]
    g = MM._norm_grid(9, w, h)
    chk("normalized/pixel grid spans exactly [0,w]x[0,h]",
        abs(g[:, 0].min()) < 1e-9 and abs(g[:, 0].max() - w) < 1e-9
        and abs(g[:, 1].max() - h) < 1e-9)

    # evaluation-domain consistency
    d = build_bench_dataset(clean["development"][0], 0)
    w, h = d["frame"]
    gm = MM.frame_grid()
    hull = MM.hull_mask(gm, d["dataset"].xy)
    chk("observation hull is a strict subset of the usable frame grid",
        0.0 < hull.mean() < 1.0, f"hull covers {100 * hull.mean():.1f}% of the frame grid")
    return ok, fail


def split_balance(clean, say):
    """Balance tables, standardized differences, and split association per factor."""
    keys = [k for k in sorted(CLEAN_FACTORS)]
    dev, hol = clean["development"], clean["holdout"]
    say(f"    {'factor':20} {'level':22} {'dev':>5} {'hold':>5} {'devFrac':>8} {'holdFrac':>9} {'stdDiff':>8}")
    audit = {}
    worst = 0.0
    for k in keys:
        levels = sorted({c[k] for c in dev} | {c[k] for c in hol})
        audit[k] = {}
        for lv in levels:
            a = sum(1 for c in dev if c[k] == lv); b = sum(1 for c in hol if c[k] == lv)
            pa, pb = a / max(len(dev), 1), b / max(len(hol), 1)
            pooled = math.sqrt(max((pa * (1 - pa) + pb * (1 - pb)) / 2.0, 1e-12))
            sd = (pa - pb) / pooled
            worst = max(worst, abs(sd))
            audit[k][str(lv)] = {"dev": a, "hold": b, "dev_frac": pa, "hold_frac": pb,
                                 "std_diff": sd}
            say(f"    {k:20} {str(lv):22} {a:5d} {b:5d} {pa:8.3f} {pb:9.3f} {sd:+8.3f}")
    # Cramer's V of each factor against the split
    assoc = {}
    for k in keys:
        levels = sorted({c[k] for c in dev + hol})
        tab = np.array([[sum(1 for c in dev if c[k] == lv) for lv in levels],
                        [sum(1 for c in hol if c[k] == lv) for lv in levels]], float)
        n = tab.sum()
        if n == 0 or tab.shape[1] < 2:
            assoc[k] = 0.0; continue
        exp = np.outer(tab.sum(1), tab.sum(0)) / n
        chi2 = float(np.nansum((tab - exp) ** 2 / np.where(exp > 0, exp, np.nan)))
        assoc[k] = float(math.sqrt(chi2 / (n * (min(tab.shape) - 1))))
    return {"balance": audit, "cramers_v_vs_split": assoc,
            "max_abs_std_diff": worst,
            "max_cramers_v": max(assoc.values()) if assoc else 0.0}


def run_prereg(args, say, W):
    """Retire the v1 manifest, build and VALIDATE the v2 benchmarks, hash everything. No fitting."""
    import hashlib

    def h(o):
        return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()

    # ---- retire v1
    v1 = benchmark_design()
    v1h = h(v1)
    say(f"\n[6] RETIRED BENCHMARK v1 -- PRESERVED, NOT EXECUTABLE")
    say(f"    sha256 {v1h}")
    say(f"    development geometry families: {v1['dev_geometry_families']}")
    say(f"    holdout geometry families:     {v1['hold_geometry_families']}")
    say(f"    RETIREMENT REASON: geometry class is perfectly confounded with the split. Each geometry")
    say(f"    family appears in exactly one subset, so any holdout result would have measured geometry")
    say(f"    class rather than generalization. Preserved for provenance; never executed.")

    # ---- v2
    clean = design_clean()
    corrupt = design_corruption(clean)
    say(f"\n[7] REPLACEMENT BENCHMARK A -- clean/noisy generalization")
    say(f"    {len(clean['development'])} development cells, {len(clean['holdout'])} holdout cells, "
        f"3 deterministic replicates each")
    say(f"    every geometry class in BOTH subsets: {sorted(GEOM_CLASSES)}")
    say(f"    layout families disjoint by construction (distinct family_seed ranges)")
    say(f"    no gross outliers, no membership errors, no duplicate/missing records, no index "
        f"corruption, no misspecification")
    say(f"\n    REPLACEMENT BENCHMARK B -- corruption / refusal challenge")
    say(f"    {len(corrupt['development'])} development cells, {len(corrupt['holdout'])} holdout cells")
    say(f"    one corruption at a time on {len(CORRUPTIONS)} corruption types, each paired with its "
        f"uncorrupted base")
    say(f"    corruptions: {CORRUPTIONS}")

    say(f"\n[8] SPLIT-BALANCE AND LEAKAGE AUDIT (benchmark A)")
    bal = split_balance(clean, say)
    say(f"    worst |standardized difference| across all factor levels: {bal['max_abs_std_diff']:.3f}")
    say(f"    worst Cramer's V of any factor against the split:        {bal['max_cramers_v']:.3f}")
    say(f"    (0 would be perfect balance; 1 would be the v1 confounding that was retired)")

    say(f"\n[9] GENERATOR VALIDATION (diagnostics only; never counted as benchmark outcomes)")
    okv, failv = validate_generator(clean, corrupt, say)
    say(f"    {len(okv)} checks passed, {len(failv)} FAILED")
    if failv:
        say(f"    FAILURES: {failv}")

    # ---- pilot runtime on DISPOSABLE layouts not in either benchmark
    say(f"\n[11] RUNTIME PILOT on disposable layouts excluded from both benchmarks")
    disp = dict(clean["development"][0])
    disp.update({"cell_id": "DISPOSABLE-pilot", "family_seed": 424242,
                 "layout_family_id": "disposable"})
    d = build_bench_dataset(disp, 0)
    case = Case("pilot/M1", d["dataset"], d["truth"])
    t0 = time.time(); op = operational_fit(case); t_op = time.time() - t0
    t0 = time.time(); MM.admissibility_v2(op["theta14"]); t_a2 = time.time() - t0
    t0 = time.time(); MM.certify_forward_injective(op["theta14"], max_cells=600); t_ct = time.time() - t0
    t0 = time.time(); MM.inverse_reliability(op["theta14"]); t_iv = time.time() - t0
    t0 = time.time()
    OB.fit(SF.dedup_view(d["dataset"]), "B", "M1", base=case.base.copy(), warm=False, max_nfev=3000)
    t_b = time.time() - t0
    RESCUE_OVERHEAD = 1.35        # measured share of fits needing the rescue retry, rounded up
    per = RESCUE_OVERHEAD * 2 * t_op + 2 * (t_a2 + t_ct + t_iv) + RESCUE_OVERHEAD * 2 * t_b
    say(f"    operational SD-D fit (staged + 2 restarts)   {t_op:6.2f} s")
    say(f"    admissibility_v2                             {t_a2:6.3f} s")
    say(f"    forward-injectivity certification            {t_ct:6.3f} s")
    say(f"    inverse-reliability suite                    {t_iv:6.3f} s")
    say(f"    legacy B fit                                 {t_b:6.3f} s")
    say(f"    per cell-replicate (SD-D M0+M1, B M0+M1, safety x2, {RESCUE_OVERHEAD:.2f} rescue "
        f"overhead): {per:.2f} s")
    nA_dev = len(clean["development"]) * 3
    nA_hol = len(clean["holdout"]) * 3
    nB_dev = len(corrupt["development"]) * 3
    nB_hol = len(corrupt["holdout"]) * 3
    say(f"    projected development (A {nA_dev} + B {nB_dev} datasets): "
        f"{per * (nA_dev + nB_dev) / 60:.1f} min")
    say(f"    projected one-shot holdout (A {nA_hol} datasets):          {per * nA_hol / 60:.1f} min")
    say(f"    projected corruption holdout (B {nB_hol} datasets):        {per * nB_hol / 60:.1f} min")
    say(f"    projected TOTAL if executed in one tranche: "
        f"{per * (nA_dev + nB_dev + nA_hol + nB_hol) / 60:.1f} min")
    say(f"    CHECKPOINTING: development and holdout are separate scoped artifacts written by "
        f"separate invocations. Holdout cells are not generated in the development run at all, so a "
        f"development checkpoint cannot expose a holdout outcome.")

    hashes = {"benchmark_v1_retired": v1h,
              "benchmark_A_clean": h(clean), "benchmark_B_corruption": h(corrupt),
              "clean_factor_levels": h(CLEAN_FACTORS), "corruption_types": h(CORRUPTIONS),
              "layout_family_assignment": h({s2: [c["layout_family_id"] for c in v]
                                             for s2, v in clean.items()}),
              "split_assignment": h({s2: [c["cell_id"] for c in v] for s2, v in clean.items()}),
              "family_seeds": h({s2: [c["family_seed"] for c in v] for s2, v in clean.items()}),
              "ground_truth_maps": h({c["cell_id"]: _truth_for(c, None).tolist()
                                      for v in clean.values() for c in v}),
              "evaluation_domains": h({"frame_grid_n": 48, "frame_grid_margin_px": 20.0,
                                       "hull_from": "observation convex hull",
                                       "resolutions": RESOLUTIONS}),
              "noise_model": h({"sigma_px": NOISE_SIGMA_BENCH, "anisotropic_ratio": 0.5,
                                "applied_to": "raw coordinates after distortion"}),
              "materiality_metrics": h({"thresholds_px": list(MM.MAP_THRESHOLDS_PX),
                                        "distinct_basin_px": MM.DISTINCT_BASIN_PX,
                                        "downstream_material_mm": MM.DOWNSTREAM_MATERIAL_MM}),
              "operational_initializer": h(OPERATIONAL),
              "rescue_rule": h(RESCUE),
              "generator_code_sd_basins": artifacts.file_sha256("sd_basins.py"),
              "metrics_code_mapmetrics": artifacts.file_sha256("mapmetrics.py"),
              "solver_code_sd_fast": artifacts.file_sha256("sd_fast.py")}
    say(f"\n[10] FROZEN HASHES")
    for k, v in hashes.items():
        say(f"    {k:34} {v}")
    for lab in ("benchmark_v2", ):
        W.document_started(lab, doc_key="benchmark")
        W.document_completed(lab, completed_candidates=["design", "validation", "hashes"])
    return {"v1_retired": {"design": v1, "sha256": v1h,
                           "retirement_reason": "geometry class perfectly confounded with split"},
            "benchmark_A_clean": clean, "benchmark_B_corruption": corrupt,
            "split_balance": bal,
            "generator_validation": {"passed": okv, "failed": failv,
                                     "n_passed": len(okv), "n_failed": len(failv)},
            "runtime_pilot": {"t_operational_s": t_op, "t_adm_v2_s": t_a2,
                              "t_certify_s": t_ct, "t_inverse_s": t_iv, "t_B_s": t_b,
                              "rescue_overhead": RESCUE_OVERHEAD, "per_cell_replicate_s": per,
                              "n_A_dev": nA_dev, "n_A_hold": nA_hol,
                              "n_B_dev": nB_dev, "n_B_hold": nB_hol,
                              "projected_dev_min": per * (nA_dev + nB_dev) / 60,
                              "projected_hold_A_min": per * nA_hol / 60,
                              "projected_hold_B_min": per * nB_hol / 60},
            "hashes": hashes, "executed_any_fit_on_benchmark": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--noise", action="store_true")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--noise-cases", nargs="*", default=["synth17"])
    ap.add_argument("--prereg", action="store_true",
                    help="freeze the operational procedure, pre-register the benchmark, pilot cost")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    mode = ("sd_bench_prereg" if args.prereg
            else "sd_basins_noise" if args.noise else "sd_basins")
    docs = (["benchmark_v2"] if args.prereg
            else [f"{n}/M1" for n in args.noise_cases] if args.noise
            else [f"{n}/M1" for n in SYNTH])
    W = artifacts.ArtifactWriter(
        analysis=mode, script=__file__, outdir=args.outdir,
        requested_documents=docs, all_documents=docs,
        requested_candidates=(["design", "validation", "hashes"] if args.prereg
                              else ["frozen-sobol", "controls", "staged"] if not args.noise
                              else [f"sigma x{len(NOISE_SIGMAS)}", f"reps x{args.reps}"]),
        objective_versions={"SD-D": "sd_fast, unchanged estimator",
                           "starts": "FROZEN from sd_sampler_pilot_full.json, unchanged",
                           "metrics": "mapmetrics projectively aligned map difference"},
        source_files=["sd_basins.py", "sd_fast.py", "startgen.py", "mapmetrics.py",
                      "objectives.py", "lattice.py", "test_sd_fast.py",
                      "test_sd_nonlattice.py", "artifacts.py"],
        calibration_node_source="not used: synthetic line observations only")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t0 = time.time()
    say("=" * 104)
    say("SD-D SYNTHETIC BASINS: initialization failure or competitive line-objective solutions?")
    say("=" * 104)
    say(f"  mode: {'NOISE COMPETITION' if args.noise else 'EXACT-DATA BASIN SEARCH'}")
    say(f"  starts are FROZEN from {os.path.basename(PILOT)}; sampler bounds, basis and the")
    say(f"  production-gate start filter are all unchanged, and no proposal was resampled.")
    if args.prereg:
        R = run_prereg(args, say, W)
    else:
        R = run_noise(args, say, W) if args.noise else run_exact(args, say, W)
    path = W.write(R)
    say(f"\n  wrote {path} (complete={W.manifest()['complete']})  [{time.time() - t0:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
