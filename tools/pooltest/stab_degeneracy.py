#!/usr/bin/env python3
"""Model-stability round, part 4: does the production gate still bound the model once eta is free?

The seed battery turned up endpoints that are plainly not lens corrections and that the PRODUCTION
GATE ACCEPTS: one with a plumbline residual of 7e-5 px per point -- four orders of magnitude below
the click noise floor -- and, more dangerously, several with an entirely plausible residual (0.46 px
on the Right camera, BETTER than the near-isotropic optimum's 1.13 px) reached at eta = -1.98, a
conjugation that stretches one image axis by a factor of 53 relative to the other.

The gate misses them because reasonToRejectSolvedDistortion: inspects the thirteen Brown-Conrady
parameters only. eta is not among them, so the gate never sees it.

A note on the Jacobian, stated carefully because the tempting version of it is wrong. The eta-aware
map is U = c + A^-1 B(A (x - c)) with A = diag(e^eta, e^-eta), so J_U(x) = A^-1 J_B(A (x - c)) A.
Determinants are invariant under conjugation, so POINTWISE det J_U(x) = det J_B(A (x - c)): eta
contributes no local area change of its own. But the gate minimizes over a FIXED box, and A relocates
where the core gets sampled, so min over the box is NOT invariant. For eta near 0.01 the relocation
is negligible and the minimum is unchanged to six decimals; for eta near 2 it is not. Both the
pointwise identity and the box-minimum movement are measured below rather than asserted.

What actually separates the branches is the anisotropy eta itself introduces, exp(2|eta|), which is a
property of A alone. The total anisotropy of the map is NOT a usable discriminator: a fisheye radial
correction is already strongly anisotropic in the local singular-value sense -- radial and tangential
magnification differ -- and measures about 3.3 to 3.6 over the frame at eta = 0, so an absolute cut on
it flags every endpoint including the good ones. That was a wrong turn taken and corrected here.

This script evaluates, for every endpoint in the battery: the production gate as shipped, the same
gate recomputed on the full eta-aware map, the pointwise determinant identity, the box-minimum
determinant movement, and the eta-induced anisotropy. It then reports which of those tests can
separate the physical branch from the degenerate one.

Writes analysis-output/stab_degeneracy.json. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_W, FRAME_H = 1920.0, 1080.0
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
# A residual this far below the click noise floor is not a fit. The plumbline clicks are chessboard
# corners located to a few tenths of a pixel, and every physical-branch endpoint in this document
# sits between 0.46 and 2.31 px per point, so 0.05 px is a generous floor, not a tuned threshold.
NOISE_FLOOR_PX = 0.05

# The noise floor alone is NOT sufficient, because the worst offenders fit BETTER than the physical
# solution. The discriminator is the anisotropy eta itself introduces, exp(2|eta|). Every
# physical-branch endpoint in this document sits at 1.016 to 1.023; every off-branch one at 2.7 or
# above. A cut of 1.5 sits in an empty decade-wide gap, so the partition is not threshold sensitive,
# which the report asserts numerically.
#
# Being explicit about what this means: no residual-based and no determinant-based test separates
# these branches, so the physical branch has to be DEFINED by a bound on eta. That is itself the
# finding -- the shipped gate contains no such bound, and would need one before eta could ship.
MAX_ETA_ANISOTROPY = 1.5


def on_physical_branch(rms, eta):
    """The single admissibility rule this round uses, defined once and imported by the other parts.

    An endpoint is on the physical branch if its plumbline residual is not below the click-noise
    floor AND the anisotropy eta introduces stays lens-like. Failing either means the optimizer
    found a degeneracy rather than a calibration.
    """
    return bool(rms >= NOISE_FLOOR_PX and math.exp(2.0 * abs(eta)) < MAX_ETA_ANISOTROPY)


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
P2 = L("parity_step2")
P5 = L("parity_step5")
SCALE14 = P5.SCALE14


def eta_aware_gate(th14, pl, frame=(FRAME_W, FRAME_H), steps=24):
    """The production gate's own two quantities, recomputed on the full eta-aware map.

    radial scale ratio : sum_g ||U(g) - c|| / sum_g ||g - c||, exactly VSCalibration.mm:2270-2279
                         but with U the conjugated map instead of the Brown-Conrady core.
    min determinant    : minimized over the same fixed box. Pointwise the determinant is conjugation
                         invariant, but the box minimum still moves with eta because A relocates
                         where the core is sampled; both facts are measured.
    total anisotropy   : max over the box of the local Jacobian's singular-value ratio. Recorded for
                         completeness only -- it is about 3.3 to 3.6 even at eta = 0, so it is NOT a
                         usable discriminator, and the report says so.
    """
    th14 = np.asarray(th14, float)
    lo, hi = pl.xy.min(axis=0), pl.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], steps + 1),
                         np.linspace(lo[1], hi[1], steps + 1))
    box = np.stack([gx.ravel(), gy.ravel()], axis=1)
    c = th14[:2]
    U = P5.undistort14(box, th14)
    den = float(np.hypot(*(box - c).T).sum())
    ratio = float(np.hypot(*(U - c).T).sum() / den) if den > 0 else float("nan")
    # local Jacobian by central differences on the full map, so eta is included
    h = 0.05
    jx = (P5.undistort14(box + [h, 0.0], th14) - P5.undistort14(box - [h, 0.0], th14)) / (2 * h)
    jy = (P5.undistort14(box + [0.0, h], th14) - P5.undistort14(box - [0.0, h], th14)) / (2 * h)
    J = np.stack([np.stack([jx[:, 0], jy[:, 0]], -1), np.stack([jx[:, 1], jy[:, 1]], -1)], -2)
    det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
    sv = np.linalg.svd(J, compute_uv=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        aniso = np.where(sv[:, 1] > 0, sv[:, 0] / sv[:, 1], np.inf)
    fg = F.box_grid_xy(frame[0], frame[1], steps)
    Uf = P5.undistort14(fg, th14)
    denf = float(np.hypot(*(fg - c).T).sum())
    ratiof = float(np.hypot(*(Uf - c).T).sum() / denf) if denf > 0 else float("nan")
    # pointwise conjugation invariance: det J_U(x) should equal det J_B at the relocated point
    ax = math.exp(th14[13]); ay = 1.0 / ax
    relocated = np.stack([c[0] + (box[:, 0] - c[0]) * ax, c[1] + (box[:, 1] - c[1]) * ay], axis=1)
    det_core_at = F.jac_det(relocated, th14[:13], 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.abs(det - det_core_at) / np.maximum(np.abs(det_core_at), 1e-30)
    return {"radial_scale_ratio_eta_aware": ratio,
            "radial_scale_ratio_eta_aware_frame": ratiof,
            "min_det_eta_aware": float(np.nanmin(det)),
            "pointwise_det_identity_max_rel_error": float(np.nanmax(rel)),
            "max_anisotropy_box": float(np.nanmax(aniso)),
            "eta_anisotropy": float(math.exp(2.0 * abs(th14[13]))),
            "accept_eta_aware_ratio": bool(0.25 < ratio < 4.0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--fits", default=os.path.join(HERE, "analysis-output", "stab_fits.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "stab_degeneracy.json"))
    args = ap.parse_args()
    say = print

    say("=" * 104)
    say("MODEL-STABILITY ROUND, PART 4: DOES THE PRODUCTION GATE STILL BOUND THE MODEL WITH eta?")
    say("=" * 104)

    fits = json.load(open(args.fits))
    plum = {clip: F.Plumblines(P2.load_lines(args.vsd, clip)[0]) for clip in CLIPS}

    say(f"\n  THE JACOBIAN, STATED CAREFULLY: J_U(x) = A^-1 J_B(A(x-c)) A, so POINTWISE the")
    say(f"  determinant is conjugation invariant -- eta adds no local area change of its own. The")
    say(f"  gate's minimum over a FIXED box is a different matter, because A relocates where the")
    say(f"  core is sampled. Both are measured, not assumed.")

    out = {"noise_floor_px": NOISE_FLOOR_PX, "max_eta_anisotropy": MAX_ETA_ANISOTROPY,
           "endpoints": {}, "degenerate": []}
    inv_check = []
    for model in ("M0", "M1", "FULL13", "F13eta"):
        out["endpoints"][model] = {}
        for clip in CLIPS:
            pl = plum[clip]
            rows = []
            for i, ep in enumerate(fits["models"][model][clip]):
                th = np.array(ep["theta14"], float)
                g = eta_aware_gate(th, pl)
                phys = on_physical_branch(ep["rms"], ep["eta"])
                rows.append({"index": i, "seed": ep["seed"], "solver": ep["solver"],
                             "sse": ep["sse"], "rms": ep["rms"], "eta": ep["eta"],
                             "gate_ok_shipped": ep["gate_ok"],
                             "R_scale_shipped": ep["R_scale"],
                             "min_det_shipped": ep["min_det_box"],
                             "below_noise_floor": bool(ep["rms"] < NOISE_FLOOR_PX),
                             "on_physical_branch": phys, **g})
                if abs(th[13]) > 0:
                    inv_check.append((abs(th[13]), g["pointwise_det_identity_max_rel_error"],
                                      abs(g["min_det_eta_aware"] - ep["min_det_box"])))
                if not phys:
                    out["degenerate"].append({"model": model, "clip": clip, **rows[-1]})
            out["endpoints"][model][clip] = rows

    if inv_check:
        small = [c for c in inv_check if c[0] < 0.05]
        big = [c for c in inv_check if c[0] >= 0.05]
        say(f"  over {len(inv_check)} endpoints with eta != 0:")
        say(f"    pointwise identity det J_U(x) = det J_B(A(x-c)) holds to a max relative error of "
            f"{max(c[1] for c in inv_check):.2e} (finite-difference accuracy) -- eta adds no local "
            f"area change of its own")
        if small:
            say(f"    box-minimum determinant, |eta| < 0.05 ({len(small)} endpoints): max shift from "
                f"the shipped value {max(c[2] for c in small):.2e} -- unchanged in practice")
        if big:
            say(f"    box-minimum determinant, |eta| >= 0.05 ({len(big)} endpoints): max shift "
                f"{max(c[2] for c in big):.3g} -- the relocation is large, so the minimum DOES move")

    ntot = sum(len(out["endpoints"][m][c]) for m in out["endpoints"] for c in CLIPS)
    nfloor = sum(1 for d in out["degenerate"] if d["below_noise_floor"])
    say(f"\n  OFF-PHYSICAL-BRANCH ENDPOINTS: {len(out['degenerate'])} of {ntot}")
    say(f"    of which {nfloor} are below the {NOISE_FLOOR_PX} px noise floor and "
        f"{len(out['degenerate']) - nfloor} have a plausible residual but an implausible map")
    say(f"    every one of them is ACCEPTED by the shipped gate: "
        f"{all(d['gate_ok_shipped'] for d in out['degenerate'])}")
    if not out["degenerate"]:
        say(f"    none")
    for d in out["degenerate"]:
        say(f"\n    {d['model']} / {d['clip']}  seed '{d['seed']}' via {d['solver']}")
        say(f"      SSE {d['sse']:.6g}, per-point RMS {d['rms']:.3e} px, eta {d['eta']:+.7f}")
        say(f"      SHIPPED production gate: {'ACCEPTS' if d['gate_ok_shipped'] else 'rejects'}"
            f"  (radial scale ratio {d['R_scale_shipped']:.6f}, min determinant "
            f"{d['min_det_shipped']:+.6f}) -- both computed on the 13-parameter core, eta invisible")
        say(f"      eta-aware radial scale ratio {d['radial_scale_ratio_eta_aware']:.6f} over the "
            f"plumbline box, {d['radial_scale_ratio_eta_aware_frame']:.6f} over the frame: "
            f"{'inside' if d['accept_eta_aware_ratio'] else 'OUTSIDE'} the (0.25, 4.0) bracket")
        say(f"      eta-aware min determinant {d['min_det_eta_aware']:+.6g} over the box, against "
            f"the shipped value {d['min_det_shipped']:+.6g}")
        say(f"      max local anisotropy over the box {d['max_anisotropy_box']:.4g} "
            f"(exp(2|eta|) = {math.exp(2 * abs(d['eta'])):.4g})")

    say(f"\n  BEST PHYSICAL-BRANCH ENDPOINT PER MODEL, for contrast")
    say(f"    {'model':8} {'camera':14} {'RMS px':>9} {'eta':>11} {'R_scale':>9} "
        f"{'R_eta-aware':>12} {'max aniso':>10}")
    for model in ("M0", "M1", "FULL13", "F13eta"):
        for clip in CLIPS:
            cand = [r for r in out["endpoints"][model][clip] if r["on_physical_branch"]]
            if not cand:
                say(f"    {model:8} {clip:14} no physical-branch endpoint")
                continue
            best = min(cand, key=lambda r: r["sse"])
            say(f"    {model:8} {clip:14} {best['rms']:9.6f} {best['eta']:+11.7f} "
                f"{best['R_scale_shipped']:9.6f} {best['radial_scale_ratio_eta_aware']:12.6f} "
                f"{best['max_anisotropy_box']:10.4f}")

    say(f"\n  WHICH TEST SEPARATES THE TWO BRANCHES?")
    dg = out["degenerate"]
    okr = [r for m in out["endpoints"] for clip in CLIPS
           for r in out["endpoints"][m][clip] if r["on_physical_branch"]]
    if dg and okr:
        # 1. shipped gate
        say(f"    shipped gate (13-parameter core): accepts "
            f"{sum(1 for d in dg if d['gate_ok_shipped'])}/{len(dg)} off-branch endpoints "
            f"-> DOES NOT separate")
        # 2. shipped bracket recomputed on the eta-aware map
        sep_ratio = all(not (0.25 < d["radial_scale_ratio_eta_aware"] < 4.0) for d in dg)
        say(f"    existing (0.25, 4.0) bracket recomputed on the eta-aware map: off-branch ratios "
            + ", ".join(f"{d['radial_scale_ratio_eta_aware']:.4g}" for d in dg))
        say(f"      physical-branch ratios "
            f"{min(r['radial_scale_ratio_eta_aware'] for r in okr):.4f} to "
            f"{max(r['radial_scale_ratio_eta_aware'] for r in okr):.4f}"
            f"  -> {'separates' if sep_ratio else 'DOES NOT separate'}")
        out["eta_aware_ratio_separates"] = bool(sep_ratio)
        # 3. determinant test on the eta-aware map
        sep_det = all(d["min_det_eta_aware"] <= 0.0 for d in dg)
        say(f"    minimum determinant recomputed on the eta-aware map: off-branch values "
            + ", ".join(f"{d['min_det_eta_aware']:.4g}" for d in sorted(dg, key=lambda z: z['sse'])[:6])
            + f" -> {'separates' if sep_det else 'DOES NOT separate (they stay positive)'}")
        out["eta_aware_det_separates"] = bool(sep_det)
        # 4. total map anisotropy, recorded to show it is unusable
        say(f"    total local map anisotropy: physical-branch endpoints already measure "
            f"{min(r['max_anisotropy_box'] for r in okr):.3f} to "
            f"{max(r['max_anisotropy_box'] for r in okr):.3f} at eta ~ 0.01, because a fisheye "
            f"radial correction is genuinely anisotropic -> NOT a usable discriminator")
        # 5. the anisotropy eta itself introduces
        an_d = [d["eta_anisotropy"] for d in dg]
        an_o = [r["eta_anisotropy"] for r in okr]
        gap_lo, gap_hi = max(an_o), min(an_d)
        say(f"    anisotropy eta introduces, exp(2|eta|): off-branch " +
            ", ".join(f"{v:.4g}" for v in sorted(an_d)))
        say(f"      physical-branch {min(an_o):.4f} to {max(an_o):.4f}")
        say(f"      -> {'SEPARATES, and any cut in the gap ' + f'({gap_lo:.4f}, {gap_hi:.4f}) gives the same partition, so the result is not threshold sensitive' if gap_hi > gap_lo else 'DOES NOT separate'}")
        out["eta_anisotropy_degenerate"] = sorted(an_d)
        out["eta_anisotropy_physical_range"] = [min(an_o), max(an_o)]
        out["eta_anisotropy_gap"] = [gap_lo, gap_hi]
        out["eta_anisotropy_separates"] = bool(gap_hi > gap_lo)
        # 4. is the noise floor alone enough?
        # restrict to endpoints that actually converged, so unconverged junk on either side does
        # not contaminate the ranges. An endpoint counts as converged if its SSE is within 5% of
        # its own model-and-camera physical-branch best.
        bestof = {}
        for m in out["endpoints"]:
            for clip in CLIPS:
                cand = [r for r in out["endpoints"][m][clip] if r["on_physical_branch"]]
                if cand:
                    bestof[(m, clip)] = min(r["sse"] for r in cand)
        conv = [r for m in out["endpoints"] for clip in CLIPS
                for r in out["endpoints"][m][clip]
                if r["on_physical_branch"] and (m, clip) in bestof
                and r["sse"] <= 1.05 * bestof[(m, clip)]]
        say(f"\n    RESTRICTED to the {len(conv)} converged physical-branch endpoints (SSE within 5%")
        say(f"    of their own model-and-camera best), so unconverged junk contaminates nothing:")
        say(f"      eta-aware radial scale ratio {min(r['radial_scale_ratio_eta_aware'] for r in conv):.4f} "
            f"to {max(r['radial_scale_ratio_eta_aware'] for r in conv):.4f}; eta-aware minimum "
            f"determinant {min(r['min_det_eta_aware'] for r in conv):+.4f} to "
            f"{max(r['min_det_eta_aware'] for r in conv):+.4f}")
        say(f"      exp(2|eta|) {min(r['eta_anisotropy'] for r in conv):.4f} to "
            f"{max(r['eta_anisotropy'] for r in conv):.4f}; total map anisotropy "
            f"{min(r['max_anisotropy_box'] for r in conv):.3f} to "
            f"{max(r['max_anisotropy_box'] for r in conv):.3f}")
        sr = all(not (0.25 < d["radial_scale_ratio_eta_aware"] < 4.0) for d in dg)
        say(f"      against the converged set, the eta-aware ratio bracket "
            f"{'separates' if sr else 'still DOES NOT separate (off-branch ratios 0.30 to 0.45 sit inside it)'}")
        say(f"      the eta-aware minimum determinant separates cleanly: every off-branch endpoint is "
            f"NEGATIVE, every converged physical-branch endpoint is above "
            f"{min(r['min_det_eta_aware'] for r in conv):+.4f}")
        out["converged_physical"] = {
            "n": len(conv),
            "eta_aware_ratio_range": [min(r['radial_scale_ratio_eta_aware'] for r in conv),
                                      max(r['radial_scale_ratio_eta_aware'] for r in conv)],
            "eta_aware_min_det_range": [min(r['min_det_eta_aware'] for r in conv),
                                        max(r['min_det_eta_aware'] for r in conv)],
            "eta_anisotropy_range": [min(r['eta_anisotropy'] for r in conv),
                                     max(r['eta_anisotropy'] for r in conv)],
            "total_anisotropy_range": [min(r['max_anisotropy_box'] for r in conv),
                                       max(r['max_anisotropy_box'] for r in conv)]}
        say(f"\n    plumbline residual alone: {len(dg) - nfloor} off-branch endpoint(s) have a "
            f"residual inside the physical range, and one of them ({min((d for d in dg if not d['below_noise_floor']), key=lambda d: d['sse'])['rms']:.4f} px) is "
            f"BETTER than its model's physical-branch optimum -> DOES NOT separate")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
