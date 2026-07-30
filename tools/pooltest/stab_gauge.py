#!/usr/bin/env python3
"""Model-stability round, part 2: projective-gauge decomposition, conditioning, eta identifiability.

The plumbline objective's zero set is invariant under a 2D projective transformation of the
corrected output: if every line is straight after U, it is still straight after H o U for any
homography H. Raw map differences between two solutions therefore mix a component the objective
cannot see with a component it can. This separates them.

For each pair (U_A, U_B) an 8-degree-of-freedom homography H is fitted so that U_B(x) ~= H(U_A(x)),
by Hartley-normalized DLT followed by geometric (not algebraic) refinement, on a dense sample inside
the plumbline convex hull. The residual after H is the part of the disagreement that is NOT gauge.
Both directions are fitted and reported, so no conclusion rests on which map was called the
reference.

CAVEAT carried through the whole report: this decomposition says how much map disagreement is
projective. It does NOT say projective disagreement is harmless. Whether it is absorbed depends on
the refractive pipeline downstream -- the front homography is refitted, but the back surface is
refraction-corrected and the camera position is triangulated, so absorption is not automatic. Only
stab_metrics.py answers that.

Writes analysis-output/stab_gauge.json. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import ConvexHull

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_W, FRAME_H = 1920.0, 1080.0
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
nd = L("nodes")
kl = L("knownlength")
P2 = L("parity_step2")
P3 = L("parity_step3")
P5 = L("parity_step5")
DG = L("stab_degeneracy")
SCALE14 = P5.SCALE14
ETA_SCALE = P5.ETA_SCALE
PN = F.NAMES + ["eta"]


# --------------------------------------------------------------------------- homography machinery


def _norm_matrix(P):
    c = P.mean(axis=0)
    d = np.sqrt(((P - c) ** 2).sum(axis=1)).mean()
    s = math.sqrt(2.0) / max(d, 1e-12)
    return np.array([[s, 0.0, -s * c[0]], [0.0, s, -s * c[1]], [0.0, 0.0, 1.0]])


def apply_H(H, P):
    P = np.asarray(P, float)
    w = H[2, 0] * P[:, 0] + H[2, 1] * P[:, 1] + H[2, 2]
    return np.stack([(H[0, 0] * P[:, 0] + H[0, 1] * P[:, 1] + H[0, 2]) / w,
                     (H[1, 0] * P[:, 0] + H[1, 1] * P[:, 1] + H[1, 2]) / w], axis=1)


def fit_homography(A, B):
    """H minimizing the geometric error sum ||H(A) - B||^2, Hartley-normalized DLT then refined."""
    A = np.asarray(A, float); B = np.asarray(B, float)
    Ta, Tb = _norm_matrix(A), _norm_matrix(B)
    An = apply_H(Ta, A); Bn = apply_H(Tb, B)
    n = len(An)
    M = np.zeros((2 * n, 9))
    for i in range(n):
        x, y = An[i]; u, v = Bn[i]
        M[2 * i] = [-x, -y, -1, 0, 0, 0, u * x, u * y, u]
        M[2 * i + 1] = [0, 0, 0, -x, -y, -1, v * x, v * y, v]
    _, _, Vt = np.linalg.svd(M)
    Hn = Vt[-1].reshape(3, 3)
    H = np.linalg.inv(Tb) @ Hn @ Ta
    if abs(H[2, 2]) > 1e-30:
        H = H / H[2, 2]

    def res(h):
        Hh = np.append(h, 1.0).reshape(3, 3)
        return (apply_H(Hh, A) - B).ravel()

    r = least_squares(res, H.ravel()[:8], method="lm", xtol=1e-15, ftol=1e-15, max_nfev=20000)
    return np.append(r.x, 1.0).reshape(3, 3)


def describe_H(H):
    """Interpretable magnitudes. Not a unique physical decomposition, and not treated as one."""
    c = np.array([[FRAME_W / 2.0, FRAME_H / 2.0]])
    half = 0.5 * math.hypot(FRAME_W, FRAME_H)
    t = float(np.linalg.norm(apply_H(H, c) - c))
    # local affine behaviour at the image centre
    h = 1e-3
    j0 = (apply_H(H, c + [[h, 0]]) - apply_H(H, c - [[h, 0]]))[0] / (2 * h)
    j1 = (apply_H(H, c + [[0, h]]) - apply_H(H, c - [[0, h]]))[0] / (2 * h)
    J = np.stack([j0, j1], axis=1)
    sv = np.linalg.svd(J, compute_uv=False)
    aniso = float(sv[0] / sv[1]) if sv[1] > 0 else float("inf")
    mean_scale = float(math.sqrt(max(sv[0] * sv[1], 0.0)))
    G = J.T @ J
    cosang = G[0, 1] / math.sqrt(max(G[0, 0] * G[1, 1], 1e-300))
    shear = 90.0 - math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
    # genuinely projective strength: how much the homogeneous denominator varies over the frame
    proj = float(np.linalg.norm([H[2, 0], H[2, 1]]) * half)
    return {"centre_translation_px": t, "affine_mean_scale": mean_scale,
            "affine_anisotropy": aniso, "affine_shear_deg": shear,
            "projective_strength": proj}


def stats_disp(e):
    e = np.asarray(e, float)
    if e.size == 0:
        return {k: float("nan") for k in ("median", "rms", "p95", "max", "n")}
    return {"median": float(np.median(e)), "rms": float(math.sqrt((e ** 2).mean())),
            "p95": float(np.percentile(e, 95)), "max": float(e.max()), "n": int(e.size)}


def gauge_pair(th_a, th_b, fitpts, evalsets):
    """Fit H both ways on fitpts and report before/after displacement on every evaluation set."""
    A = P5.undistort14(fitpts, th_a); B = P5.undistort14(fitpts, th_b)
    H_ab = fit_homography(A, B)
    H_ba = fit_homography(B, A)
    out = {"H_ab": H_ab.tolist(), "H_ba": H_ba.tolist(),
           "describe_ab": describe_H(H_ab), "describe_ba": describe_H(H_ba), "sets": {}}
    for name, pts in evalsets.items():
        if len(pts) == 0:
            continue
        Ua = P5.undistort14(pts, th_a); Ub = P5.undistort14(pts, th_b)
        raw = np.hypot(*(Ua - Ub).T)
        adj = np.hypot(*(apply_H(H_ab, Ua) - Ub).T)
        adj_rev = np.hypot(*(apply_H(H_ba, Ub) - Ua).T)
        absorbed = 1.0 - float((adj ** 2).sum()) / max(float((raw ** 2).sum()), 1e-300)
        absorbed_rev = 1.0 - float((adj_rev ** 2).sum()) / max(float((raw ** 2).sum()), 1e-300)
        out["sets"][name] = {"raw": stats_disp(raw), "adjusted": stats_disp(adj),
                             "adjusted_reverse": stats_disp(adj_rev),
                             "fraction_absorbed": absorbed,
                             "fraction_absorbed_reverse": absorbed_rev}
    return out


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--fits", default=os.path.join(HERE, "analysis-output", "stab_fits.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "stab_gauge.json"))
    args = ap.parse_args()
    say = print
    t0 = time.time()

    say("=" * 104)
    say("MODEL-STABILITY ROUND, PART 2: PROJECTIVE GAUGE, CONDITIONING, ETA IDENTIFIABILITY")
    say("=" * 104)
    say("  The plumbline zero set is projectively invariant, so a homography of the corrected output")
    say("  is invisible to the objective. Raw map differences are decomposed accordingly. This does")
    say("  NOT establish that projective movement is harmless downstream; stab_metrics.py does that.")

    fits = json.load(open(args.fits))
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)
    ann = kl.load(args.vsd, CLIPS)
    out = {"pairs": {}, "conditioning": {}, "eta_profile": {}}

    for clip in CLIPS:
        lines, tcs, pk = P2.load_lines(args.vsd, clip)
        pl = F.Plumblines(lines)
        obj = P5.Obj14(pl)
        front = np.array([[p[0], p[1]] for p in nd.front_calibration_nodes(db, pk)], float)
        back = np.array([[p[0], p[1]] for p in nd.back_calibration_nodes(db, pk)], float)
        clicks = np.array([xy for d in ann["clicks"].values() for cl, xy in d.items()
                           if cl == clip], float)
        hull = ConvexHull(pl.xy)
        eqs = hull.equations

        def inside(P):
            v = np.asarray(P, float) @ eqs[:, :2].T + eqs[:, 2]
            return v.max(axis=1) <= 1e-9

        # dense well-distributed sample INSIDE the hull, for fitting and for evaluation
        gx, gy = np.meshgrid(np.linspace(0.0, FRAME_W, 90), np.linspace(0.0, FRAME_H, 60))
        allg = np.stack([gx.ravel(), gy.ravel()], axis=1)
        dense_in = allg[inside(allg)]
        gx2, gy2 = np.meshgrid(np.linspace(0.0, FRAME_W, 61), np.linspace(0.0, FRAME_H, 61))
        frame = np.stack([gx2.ravel(), gy2.ravel()], axis=1)
        fin = inside(frame)
        evalsets = {"plumbline points": pl.xy, "dense inside hull": dense_in,
                    "calibration nodes": np.vstack([front, back]),
                    "measurement clicks": clicks,
                    "full frame": frame,
                    "full frame outside hull (extrapolation)": frame[~fin]}
        say(f"\n{'=' * 104}")
        say(f"  {clip}   hull from {pl.n} plumbline points; homography fitted on "
            f"{len(dense_in)} dense in-hull samples")
        say(f"  full-frame grid {len(frame)} points, {int(fin.sum())} inside the hull, "
            f"{int((~fin).sum())} outside (extrapolation)")
        say(f"{'=' * 104}")

        def theta_of(model, idx):
            return np.array(fits["models"][model][clip][idx]["theta14"], float)

        def reps(model):
            """Admissible cluster representatives.

            Three filters, each stated because each removes something different:
              physical branch  -- excludes the collapsed and large-|eta| maps that stab_degeneracy
                                  identifies and that the shipped gate does not reject
              shipped gate     -- excludes what production itself would refuse to store
              within 2x of the best admissible SSE -- excludes gross convergence failures (SSE in
                                  the thousands) while KEEPING genuine alternative basins, which sit
                                  at 1.09x to 1.27x. Without this, "most separated endpoints" would
                                  just report the worst non-convergence in the battery.
            """
            cl = fits["models"][model]["clusters"][clip]
            eps = fits["models"][model][clip]
            ok = []
            for c in cl:
                ep = eps[c["representative"]]
                if DG.on_physical_branch(c["rms"], c["eta"]) and ep["gate_ok"]:
                    ok.append(c)
            if ok:
                b = min(c["sse"] for c in ok)
                keep = [c for c in ok if c["sse"] <= 2.0 * b]
            else:
                keep = []
            if len(keep) != len(cl):
                say(f"      [{model}: {len(cl) - len(keep)} of {len(cl)} cluster(s) excluded "
                    f"(off-branch, gate-rejected, or beyond 2x the best SSE)]")
            return [(c["index"], theta_of(model, c["representative"]), c["sse"]) for c in keep]

        def most_separated(model):
            r = reps(model)
            if len(r) < 2:
                return None
            best = None
            for a in range(len(r)):
                for b in range(a + 1, len(r)):
                    d = float(np.abs(P5.undistort14(frame, r[a][1])
                                     - P5.undistort14(frame, r[b][1])).max())
                    if best is None or d > best[0]:
                        best = (d, r[a], r[b])
            return best

        pairs = []
        pr = {m["model"]: m for m in
              json.load(open(os.path.join(HERE, "analysis-output",
                                          "parity_step5.json")))["rows"]}
        key = "theta14_L" if clip == CLIPS[0] else "theta14_R"
        th_app = np.array(pr["APP13"][key], float)
        th_pol = np.array(pr["POLISH13"][key], float)
        pairs.append(("APP13 vs POLISH13", th_app, th_pol))
        for model in ("FULL13", "M0", "M1", "F13eta"):
            ms = most_separated(model)
            if ms is None:
                say(f"\n    {model}: single endpoint cluster, no separated pair to decompose")
                continue
            pairs.append((f"{model}: most separated accepted endpoints "
                          f"(clusters {ms[1][0]} and {ms[2][0]}, SSE {ms[1][2]:.4f} vs "
                          f"{ms[2][2]:.4f})", ms[1][1], ms[2][1]))
        bm0 = min(reps("M0"), key=lambda z: z[2])[1]
        bm1 = min(reps("M1"), key=lambda z: z[2])[1]
        bfe = min(reps("F13eta"), key=lambda z: z[2])[1]
        pairs.append(("best M0 vs best M1", bm0, bm1))
        pairs.append(("best M1 vs best F13eta", bm1, bfe))

        out["pairs"][clip] = {}
        for label, ta, tb in pairs:
            g = gauge_pair(ta, tb, dense_in, evalsets)
            out["pairs"][clip][label] = g
            d = g["describe_ab"]
            say(f"\n    {label}")
            say(f"      fitted H: centre translation {d['centre_translation_px']:.3f} px, "
                f"affine mean scale {d['affine_mean_scale']:.6f}, anisotropy "
                f"{d['affine_anisotropy']:.6f}, shear {d['affine_shear_deg']:+.4f} deg, "
                f"projective strength {d['projective_strength']:.6f}")
            say(f"      {'evaluation set':40} {'raw med':>9} {'raw rms':>9} {'raw p95':>9} "
                f"{'raw max':>9} | {'adj med':>9} {'adj rms':>9} {'adj p95':>9} {'adj max':>9} "
                f"{'absorbed':>9}")
            for name, s in g["sets"].items():
                r, a = s["raw"], s["adjusted"]
                say(f"      {name:40} {r['median']:9.3f} {r['rms']:9.3f} {r['p95']:9.3f} "
                    f"{r['max']:9.3f} | {a['median']:9.3f} {a['rms']:9.3f} {a['p95']:9.3f} "
                    f"{a['max']:9.3f} {s['fraction_absorbed']:9.5f}")
            ab = g["sets"]["dense inside hull"]
            say(f"      direction check on the dense in-hull set: absorbed forward "
                f"{ab['fraction_absorbed']:.5f}, reverse {ab['fraction_absorbed_reverse']:.5f}; "
                f"adjusted rms forward {ab['adjusted']['rms']:.3f} px, reverse "
                f"{ab['adjusted_reverse']['rms']:.3f} px")

        # ------------------------------------------------------------------ conditioning
        say(f"\n    CONDITIONING at each model's endpoint clusters, scaled parameter coordinates")
        out["conditioning"][clip] = {}
        for model in ("M0", "M1", "FULL13", "F13eta"):
            free = fits["free_sets"][model]
            rows = []
            for ci, th, sse in reps(model):
                x = th / SCALE14
                J = obj.jac(x, free)
                sv = np.linalg.svd(J, compute_uv=False)
                _, _, Vt = np.linalg.svd(J, full_matrices=False)
                ranks = {f"{t:g}": int((sv > t * sv[0]).sum()) for t in (1e-3, 1e-6, 1e-9)}
                weakest = Vt[-1]
                comp = sorted(zip([PN[j] for j in free], weakest ** 2),
                              key=lambda z: -z[1])[:4]
                etashare = None
                if 13 in free:
                    ie = free.index(13)
                    # share of the eta basis direction living in the weakest k singular directions
                    etashare = {k: float((Vt[-k:, ie] ** 2).sum()) for k in (1, 2, 3)}
                rows.append({"cluster": ci, "sse": sse, "sv_max": float(sv[0]),
                             "sv_min": float(sv[-1]),
                             "condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf"),
                             "effective_rank": ranks, "nfree": len(free),
                             "weakest_composition": [(a, float(b)) for a, b in comp],
                             "eta_share_in_weakest": etashare,
                             "sv": [float(v) for v in sv]})
                say(f"      {model:8} cluster {ci}: sigma {sv[0]:.4e} .. {sv[-1]:.4e}, condition "
                    f"{rows[-1]['condition']:.4e}, effective rank "
                    f"{ranks['0.001']}/{ranks['1e-06']}/{ranks['1e-09']} of {len(free)} "
                    f"at 1e-3/1e-6/1e-9")
                say(f"      {'':8} weakest direction: " +
                    ", ".join(f"{a} {b:.3f}" for a, b in comp))
                if etashare is not None:
                    say(f"      {'':8} eta's share in the weakest 1/2/3 directions "
                        f"{etashare[1]:.4f}/{etashare[2]:.4f}/{etashare[3]:.4f}")
                if model == "F13eta":
                    k = th[2:9]
                    say(f"      {'':8} high-order terms k5,k6,k7 scaled "
                        f"{th[6] / SCALE14[6]:+.3f}, {th[7] / SCALE14[7]:+.3f}, "
                        f"{th[8] / SCALE14[8]:+.3f}; p3,p4 scaled "
                        f"{th[11] / SCALE14[11]:+.3f}, {th[12] / SCALE14[12]:+.3f}")
            out["conditioning"][clip][model] = rows

        # ------------------------------------------------------------------ eta profile
        say(f"\n    ETA IDENTIFIABILITY PROFILE  (all nuisance parameters reoptimized at fixed eta;")
        say(f"    descriptive dSSE widths only -- residuals within a line are correlated, so no")
        say(f"    likelihood-calibrated interval is claimed)")
        out["eta_profile"][clip] = {}
        for model in ("M1", "F13eta"):
            free = fits["free_sets"][model]
            nuis = [j for j in free if j != 13]
            best = min(reps(model), key=lambda z: z[2])
            xb = best[1] / SCALE14
            e0 = float(best[1][13])
            grid = sorted(set([0.0] + [round(e0 + d, 8) for d in
                                       (-0.010, -0.006, -0.004, -0.002, -0.001, 0.0,
                                        0.001, 0.002, 0.004, 0.006, 0.010)]))
            prof = []
            for e in grid:
                s = xb.copy(); s[13] = e / ETA_SCALE
                r = P5.fit14(obj, s, nuis, f"{model} eta fixed {e}")
                prof.append({"eta": e, "sse": r["sse"]})
            lo = min(p["sse"] for p in prof)
            out["eta_profile"][clip][model] = {"eta_hat": e0, "profile": prof, "min_sse": lo}
            say(f"      {model}: eta_hat {e0:+.7f}, profile minimum SSE {lo:.5f}")
            say(f"        " + "  ".join(f"{p['eta']:+.4f}:{p['sse'] - lo:.3f}" for p in prof))
            zero = [p for p in prof if p["eta"] == 0.0][0]
            say(f"        dSSE at eta = 0: {zero['sse'] - lo:.4f} px^2 "
                f"({100 * (zero['sse'] - lo) / max(lo, 1e-9):.2f}% of the minimum)")
            near = [p for p in prof if abs(p["eta"] - e0) <= 0.00201]
            if len(near) >= 3:
                gg = np.array([p["eta"] for p in near]); cc = np.array([p["sse"] for p in near])
                curv = float(np.polyfit(gg, cc, 2)[0] * 2)
                # eta offset at which SSE rises by 1% of the minimum, from the local quadratic
                w = math.sqrt(2.0 * 0.01 * lo / curv) if curv > 0 else float("nan")
                say(f"        local curvature d2SSE/deta2 {curv:.4e}; eta offset giving a 1% SSE "
                    f"rise {w:.6f}")
                out["eta_profile"][clip][model].update(curvature=curv, one_percent_halfwidth=w)

    db.close()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}   [{time.time() - t0:.0f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
