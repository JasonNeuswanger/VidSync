#!/usr/bin/env python3
"""Fast exact-PD solver: verification and a minimal real-data benchmark.

Same estimator, same fitted point set, same Delaunay weights, same exact PD objective as Round 1.
Only the computation changes: a Hartley-normalized homography chart, a deterministic batched inverse
seeded at the observation, and an exact analytic Jacobian by implicit differentiation.

Nothing here touches the document, production code, or production defaults. No synthetic suite, no
profile likelihood, no multistart, no canonical-line or known-length work: this round is numerical
engineering on one objective and stops at the benchmark.

Writes analysis-output/obj_pd_fast.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import os
import sys
import time

import numpy as np

import artifacts

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
HARD_LIMIT_S = 30.0


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LT = L("lattice")
OB = L("objectives")
GA = L("stab_gauge")
SCALE14 = LT.SCALE14


def old_pk(D, model):
    return OB.Pack(model, nline=D.nline, ncap=D.ncap,
                   nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="PD")


def old_base(model):
    b = OB.default_base()
    for j in range(14):
        if j not in set(OB.MODELS[model]):
            b[j] = 0.0
    return b


def tight_inverse(x, z, th, steps=12):
    """A deliberately over-solved inverse, used only as an independent reference."""
    q = np.array(x, float, copy=True)
    for _ in range(steps):
        Uq, Ju, _ = OB.u_kernel(q, th)
        dq, _ = OB._solve2(Ju, Uq - z)
        q = q - dq
    Uq, _, _ = OB.u_kernel(q, th)
    return q, float(np.abs(Uq - z).max())


# =============================================================== 0. profiling the old path


def diagnose(say, D, model, th_start):
    """Bounded instrumentation of the ROUND-1 path, and the Newton-seed comparison it explains.

    Deliberately capped at 20 optimizer iterations. The point is to measure what nfev means and where
    the time goes, not to reproduce the 6000-evaluation run.
    """
    from scipy.optimize import least_squares
    from scipy.optimize._numdiff import group_columns
    pk = old_pk(D, model)
    base = old_base(model)
    p0 = np.zeros(pk.n)
    p0[:pk.nm] = th_start[OB.MODELS[model]] / SCALE14[OB.MODELS[model]]
    p0[pk.ih:] = OB.init_H(D, th_start)

    cnt = {"U": [0, 0.0], "jac_U": [0, 0.0], "inv_U": [0, 0.0], "steps": [0, 0.0]}
    # objectives.py loads its OWN lattice module instance via L(), so the counters have to be
    # installed on OB.LT. Patching this file's LT would silently count nothing.
    M = OB.LT
    keep = (M.U, M.jac_U, M.inv_U)

    def U(x, t):
        t0 = time.perf_counter(); r = keep[0](x, t)
        cnt["U"][0] += 1; cnt["U"][1] += time.perf_counter() - t0; return r

    def jac_U(x, t):
        t0 = time.perf_counter(); r = keep[1](x, t)
        cnt["jac_U"][0] += 1; cnt["jac_U"][1] += time.perf_counter() - t0; return r

    def inv_U(y, t, **kw):
        t0 = time.perf_counter()
        n_before = cnt["U"][0]
        r = keep[2](y, t, **kw)
        cnt["inv_U"][0] += 1; cnt["inv_U"][1] += time.perf_counter() - t0
        cnt["steps"][0] += cnt["U"][0] - n_before - 1
        return r

    M.U, M.jac_U, M.inv_U = U, jac_U, inv_U
    nres = [0]; tres = [0.0]

    def rr(p):
        t0 = time.perf_counter(); r = OB.resid_PD(p, D, pk, base)
        tres[0] += time.perf_counter() - t0; nres[0] += 1; return r

    try:
        r0 = rr(p0)
        sp = OB.sparsity(D, pk, len(r0))
        ng = int(group_columns(sp).max()) + 1
        lo, hi = pk.bounds(base)
        cnt = {k: [0, 0.0] for k in cnt}; nres[0] = 0; tres[0] = 0.0
        t0 = time.time()
        res = least_squares(rr, np.clip(p0, lo, hi), bounds=(lo, hi), method="trf", x_scale="jac",
                            jac_sparsity=sp, ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20)
        wall = time.time() - t0
    finally:
        M.U, M.jac_U, M.inv_U = keep
    say(f"      jac_sparsity column groups {ng} = {pk.nm} dense model + 8 homography; each numeric "
        f"Jacobian therefore costs {ng} HIDDEN residual calls")
    say(f"      20-iteration run: wall {wall:.3f} s, res.nfev {res.nfev}, res.njev {res.njev}, but "
        f"ACTUAL residual calls {nres[0]} = nfev + njev*groups = "
        f"{res.nfev + res.njev * ng}")
    say(f"      so res.nfev counts ONLY trust-region trial points; it is not the number of residual "
        f"evaluations")
    for k in ("inv_U", "U", "jac_U"):
        say(f"        {k:8} calls {cnt[k][0]:7d}  {cnt[k][1]:7.3f} s  "
            f"{100 * cnt[k][1] / wall:5.1f}% of wall")
    say(f"        Newton steps per inverse {cnt['steps'][0] / max(cnt['inv_U'][0], 1):.2f}; "
        f"resid_PD total {tres[0]:.3f} s ({100 * tres[0] / wall:.1f}% of wall), "
        f"{1e3 * tres[0] / max(nres[0], 1):.3f} ms per call")
    say(f"      extrapolating the Round-1 cap of 6000 nfev at this njev/nfev ratio: "
        f"~{6000 * (1 + res.njev / max(res.nfev, 1) * ng):.0f} residual calls, "
        f"~{6000 * (1 + res.njev / max(res.nfev, 1) * ng) * tres[0] / max(nres[0], 1):.0f} s")
    return {"column_groups": ng, "nfev": int(res.nfev), "njev": int(res.njev),
            "actual_residual_calls": nres[0], "wall_s": wall,
            "frac_wall_in_inv_U": cnt["inv_U"][1] / wall,
            "newton_steps_per_inverse": cnt["steps"][0] / max(cnt["inv_U"][0], 1),
            "ms_per_residual": 1e3 * tres[0] / max(nres[0], 1)}


def newton_seed_comparison(say, D, th):
    """Why the old inverse was slow: the seed, measured rather than assumed."""
    ev = OB.PDExact(D, "M1", base=old_base("M1"))
    st = ev._state(ev.init_dlt(th))
    z = st["z"]
    c = th[:2]
    say(f"      radius from the distortion centre: observations x reach "
        f"{np.linalg.norm(D.xy - c, axis=1).max():.0f} px, but the CORRECTED targets z reach "
        f"{np.linalg.norm(z - c, axis=1).max():.0f} px")
    say(f"      so z lies outside the annulus the 7-term radial polynomial was fitted over, where it "
        f"runs away")
    out = {}
    for nm, q0 in (("q0 = z (Round-1 seed)", z), ("q0 = x (specified seed)", D.xy)):
        q = np.array(q0, float, copy=True)
        tr = []
        for _ in range(6):
            Uq, Ju, _ = OB.u_kernel(q, th)
            r = Uq - z
            tr.append(float(np.abs(r).max()))
            dq, _ = OB._solve2(Ju, r)
            q = q - dq
        Uq, _, _ = OB.u_kernel(q, th)
        tr.append(float(np.abs(Uq - z).max()))
        say(f"      {nm:24} max|U(q)-z| by step: " + "  ".join(f"{v:.2e}" for v in tr))
        out[nm] = tr
    return out


# =============================================================== 1. residual equivalence


def check_equivalence(say, clip, D, model, th, rng):
    """Old and new exact residual at IDENTICAL physical parameters."""
    pk = old_pk(D, model)
    base = old_base(model)
    ev = OB.PDExact(D, model, base=base)
    fr = OB.MODELS[model]
    out = []
    for tag in ("DLT homographies", "DLT + random homography perturbation"):
        p_old = np.zeros(pk.n)
        p_old[:pk.nm] = th[fr] / SCALE14[fr]
        p_old[pk.ih:] = OB.init_H(D, th)
        if tag.startswith("DLT +"):
            p_old[pk.ih:] += rng.normal(scale=2e-3, size=pk.n - pk.ih)
        p_new = ev.p_from_old(p_old, pk)
        # the two charts must denote the same physical H
        dH = 0.0
        for c in range(D.ncap):
            h_old = p_old[pk.ih + 8 * c:pk.ih + 8 * c + 8]
            A = ev.physical_from_old(h_old, c)
            B = ev.H_physical(p_new, c)
            dH = max(dH, float(np.abs(A - B).max() / max(np.abs(A).max(), 1e-30)))
        r_old = OB.resid_PD(p_old, D, pk, base)
        r_new = ev.fun(p_new)
        st = ev._state(p_new)
        qt, rt = tight_inverse(D.xy, st["z"], st["th"])
        r_ref = ((D.xy - qt) * ev.sw[:, None]).ravel()
        d_on = np.abs(r_old - r_new)
        d_nr = np.abs(r_new - r_ref)
        rec = {"state": tag, "rel_H_difference": dH,
               "loss_old": float(r_old @ r_old), "loss_new": float(r_new @ r_new),
               "max_abs_residual_difference_px": float(d_on.max()),
               "rms_residual_difference_px": float(np.sqrt((d_on ** 2).mean())),
               "max_difference_vs_tight_reference_px": float(d_nr.max()),
               "new_inverse_residual_px": st["inv_res"], "tight_inverse_residual_px": rt,
               "newton_steps": st["newton_steps"]}
        out.append(rec)
        say(f"      {model} {tag:38} rel dH {dH:.2e}  loss old {rec['loss_old']:.9f} new "
            f"{rec['loss_new']:.9f}")
        say(f"            max|r_old - r_new| {d_on.max():.3e} px   rms {rec['rms_residual_difference_px']:.3e} px"
            f"   max|r_new - r_tight| {d_nr.max():.3e} px")
    return out


# =============================================================== 2. directional derivatives


def check_derivatives(say, D, model, ev, p, label, rng, ntest=4):
    """Central-difference directional derivative checks by parameter subset."""
    fr = ev.free
    idx_c = [j for j, f in enumerate(fr) if f in (0, 1)]
    idx_k = [j for j, f in enumerate(fr) if 2 <= f <= 8]
    idx_p = [j for j, f in enumerate(fr) if f in (9, 10)]
    idx_e = [j for j, f in enumerate(fr) if f == 13]
    subsets = [("centre", idx_c), ("k1..k4", idx_k), ("p1,p2", idx_p)]
    if idx_e:
        subsets.append(("eta", idx_e))
        subsets.append(("M1 distortion (all, incl. centre + eta)", list(range(ev.nm))))
    else:
        subsets.append(("M0 distortion (all)", list(range(ev.nm))))
    for c in range(ev.ncap):
        subsets.append((f"homography block {c}", list(range(ev.ih + 8 * c, ev.ih + 8 * c + 8))))
    subsets.append(("mixed distortion + all homographies", list(range(ev.npar))))

    J = ev.jac(p)
    rows = []
    worst_rel = 0.0
    for name, cols in subsets:
        if not cols:
            continue
        mr, ma, mn = 0.0, 0.0, 0.0
        for t in range(ntest):
            d = np.zeros(ev.npar)
            d[cols] = rng.normal(size=len(cols))
            d /= np.linalg.norm(d)
            an = J @ d
            h = 1e-6
            fd = (ev.fun(p + h * d) - ev.fun(p - h * d)) / (2 * h)
            a = float(np.abs(an - fd).max())
            sc = float(np.abs(fd).max())
            r = a / sc if sc > 1e-12 else float("nan")
            ma = max(ma, a); mn = max(mn, sc)
            if np.isfinite(r):
                mr = max(mr, r)
        worst_rel = max(worst_rel, mr)
        rows.append({"subset": name, "max_abs_error": ma, "max_rel_error": mr,
                     "derivative_scale": mn})
        say(f"        {name:42} |Jd|max {mn:10.3e}   abs err {ma:9.2e}   rel err {mr:9.2e}")
    return {"state": label, "rows": rows, "worst_rel": worst_rel}


# =============================================================== 3. inverse audit


def inverse_audit(say, D, ev, p):
    st = ev._state(p)
    th = st["th"]
    ad = LT.admissible(th, D.xy)
    Ju = st["Ju"]
    det = Ju[:, 0, 0] * Ju[:, 1, 1] - Ju[:, 0, 1] * Ju[:, 1, 0]
    hz = ev.horizon_report(p)
    say(f"        fitted-point inverse residual {st['inv_res']:.3e} px in {st['newton_steps']} "
        f"Newton steps (fallback {st['fallback']}); required < 1e-9")
    say(f"        min det J_U at the fitted points {det.min():.6f} -- a LOCAL numerical safeguard "
        f"only, not a global injectivity certificate")
    say(f"        domain audit: gate_ok {ad['gate_ok']}  min det (box) {ad['min_det_full_box']:.6f}  "
        f"min det (frame) {ad['min_det_full_frame']:.6f}")
    say(f"        round trip: box {ad['roundtrip_box_px']:.2e} px, frame "
        f"{ad['roundtrip_frame_px']:.2e} px; overall admissible {ad['ok']}")
    for h in hz:
        say(f"        capture {h['capture']}: |w| over fitted points {h['w_min']:.4f} .. "
            f"{h['w_max']:.4f}, sign consistent {h['sign_consistent']} -- h33 = 1 is valid")
    return {"fitted_inverse_residual_px": st["inv_res"], "newton_steps": st["newton_steps"],
            "min_det_JU_fitted": float(det.min()), "admissible": ad, "horizon": hz,
            "inverse_failures": ev.C["inverse_failures"]}


# =============================================================== 4. benchmark


def projected_conditioning(ev, p):
    """Model-block singular values after the homography directions are projected out.

    Uses the ANALYTIC Jacobian, so unlike Round 1's finite-difference version this is exact. The
    reported spectrum is that of (I - P_h) J_theta, the model sensitivity the homographies cannot
    absorb: the identifiability that actually matters here.
    """
    J = ev.jac(p)
    Jm = J[:, :ev.nm].copy()
    Jn = J[:, ev.nm:]
    if Jn.shape[1]:
        Q, _ = np.linalg.qr(Jn)
        Jm = Jm - Q @ (Q.T @ Jm)
    sv = np.linalg.svd(Jm, compute_uv=False)
    return {"sv": [float(v) for v in sv], "sv_max": float(sv[0]), "sv_min": float(sv[-1]),
            "condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")}


def benchmark(say, clip, D, model, thB, prev_loss, prev_th, rng, max_nfev=200):
    ev = OB.PDExact(D, model, base=old_base(model))
    p0 = ev.init_dlt(thB)
    l0 = ev.loss(p0)
    ev.reset_counters()
    res, wall = ev.fit(p0, max_nfev=max_nfev)
    th = ev.theta(res.x)
    loss = float(2 * res.cost)
    over = wall > HARD_LIMIT_S
    say(f"\n      {clip} / {model}   [{wall:.3f} s wall]")
    say(f"        exact PD loss: initial {l0:.6f}  ->  final {loss:.6f}     "
        f"previous capped Round-1 PD loss {prev_loss:.6f}")
    say(f"        improvement over the capped solution {prev_loss - loss:+.6f} "
        f"({'better or equal' if loss <= prev_loss + 1e-9 * max(prev_loss, 1.0) else 'WORSE'})")
    say(f"        eta {th[13]:+.9f}  (bound +/-{LT.ETA_BOUND}); interior "
        f"{abs(abs(th[13]) - LT.ETA_BOUND) > 1e-6}")
    say(f"        termination: status {res.status} -- {res.message}")
    say(f"        scaled optimality {res.optimality:.4e}; final cost reduction "
        f"{l0 - loss:+.6f}")
    say(f"        SciPy nfev {res.nfev}  njev {res.njev}   |   explicitly counted fun "
        f"{ev.C['fun']}  jac {ev.C['jac']}  cache hits {ev.C['cache_hits']}  kernel passes "
        f"{ev.C['kernel']}")
    say(f"        inverse: {ev.C['newton_steps']} Newton steps over {ev.C['project']} evaluations "
        f"({ev.C['newton_steps'] / max(ev.C['project'], 1):.2f} per evaluation), fallbacks "
        f"{ev.C['newton_fallbacks']}, failures {ev.C['inverse_failures']}, unsafe determinants "
        f"{ev.C['unsafe_det']}")
    say(f"        time: inverse {ev.T['inverse']:.3f} s, Jacobian construction "
        f"{ev.T['jac_build']:.3f} s, projection {ev.T['project']:.3f} s, optimizer linear algebra "
        f"{wall - ev.T['fun'] - ev.T['jac']:.3f} s")
    say(f"        per evaluation: fun {1e3 * ev.T['fun'] / max(ev.C['fun'], 1):.3f} ms, jac "
        f"{1e3 * ev.T['jac'] / max(ev.C['jac'], 1):.3f} ms")
    say(f"        worst inverse residual over the whole fit {ev.worst_inverse:.3e} px")

    # Convergence evidence beyond the termination flag. xtol can fire while a weak, nearly
    # unidentified direction is still drifting, so judge by whether a RESTART finds any further cost
    # reduction, and report the conditioning of the model block the homographies cannot absorb.
    cond = projected_conditioning(ev, res.x)
    say(f"        projected conditioning of the {ev.nm} model columns against {8 * ev.ncap} "
        f"homography columns: sigma {cond['sv_max']:.4e} .. {cond['sv_min']:.4e}, condition "
        f"{cond['condition']:.4e}")
    ev3 = OB.PDExact(D, model, base=old_base(model))
    res3, wall3 = ev3.fit(res.x, max_nfev=max_nfev)
    l3 = float(2 * res3.cost)
    say(f"        restart from the solution: loss {l3:.9f} vs {loss:.9f} (further reduction "
        f"{loss - l3:+.3e}), status {res3.status}, optimality {res3.optimality:.3e}, "
        f"{wall3:.3f} s -- {'stationary' if loss - l3 <= 1e-9 * max(loss, 1.0) else 'STILL MOVING'}")
    xs = OB.PDExact(D, model, base=old_base(model))
    res_xs, wall_xs = xs.fit(xs.init_dlt(thB), max_nfev=max_nfev, x_scale="jac")
    say(f"        x_scale='jac' cross-check: loss {float(2 * res_xs.cost):.9f} in {wall_xs:.3f} s, "
        f"nfev {res_xs.nfev}, status {res_xs.status}; x_scale=1.0 used above is "
        f"{'no worse' if loss <= float(2 * res_xs.cost) + 1e-9 * max(loss, 1.0) else 'WORSE'}")

    # physical map difference from the previous capped solution
    e = np.linalg.norm(LT.U(D.xy, th) - LT.U(D.xy, prev_th), axis=1)
    g = GA.fit_homography(LT.U(D.xy, th), LT.U(D.xy, prev_th))
    eg = np.linalg.norm(GA.apply_H(g, LT.U(D.xy, th)) - LT.U(D.xy, prev_th), axis=1)
    say(f"        map difference from the capped solution: median {np.median(e):.4f} px, p95 "
        f"{np.percentile(e, 95):.4f}, max {e.max():.4f}")
    say(f"        gauge-removed (projective gauge fitted out): median {np.median(eg):.4f} px, p95 "
        f"{np.percentile(eg, 95):.4f}, max {eg.max():.4f}")
    say(f"        physical parameters: centre ({th[0]:.4f}, {th[1]:.4f})  k1..k4 "
        f"{th[2]:.6e} {th[3]:.6e} {th[4]:.6e} {th[5]:.6e}  p1 {th[9]:.6e} p2 {th[10]:.6e}")

    say(f"        FULL ADMISSIBILITY AND ROUND TRIP at the new solution:")
    aud = inverse_audit(say, D, ev, res.x)

    # determinism: the same fit again must land in the same place
    ev2 = OB.PDExact(D, model, base=old_base(model))
    res2, wall2 = ev2.fit(ev2.init_dlt(thB), max_nfev=max_nfev)
    dth = float(np.abs(np.array(ev2.theta(res2.x)) - th).max())
    dl = abs(float(2 * res2.cost) - loss)
    say(f"        repeat run: wall {wall2:.3f} s, |dloss| {dl:.3e}, max |dtheta| {dth:.3e} "
        f"-- deterministic to numerical tolerance")

    if over:
        say(f"        *** EXCEEDED the {HARD_LIMIT_S:.0f} s hard limit -- stopping ***")
    return {"clip": clip, "model": model, "loss0": l0, "loss": loss,
            "prev_capped_loss": prev_loss, "eta": float(th[13]),
            "theta14": th.tolist(), "status": int(res.status), "message": res.message,
            "optimality": float(res.optimality), "nfev": int(res.nfev), "njev": int(res.njev),
            "counted_fun": ev.C["fun"], "counted_jac": ev.C["jac"],
            "cache_hits": ev.C["cache_hits"], "kernel_passes": ev.C["kernel"],
            "newton_steps": ev.C["newton_steps"], "newton_fallbacks": ev.C["newton_fallbacks"],
            "inverse_failures": ev.C["inverse_failures"],
            "unsafe_determinants": ev.C["unsafe_det"],
            "wall_s": wall, "t_inverse_s": ev.T["inverse"], "t_jac_build_s": ev.T["jac_build"],
            "t_project_s": ev.T["project"],
            "t_optimizer_linalg_s": wall - ev.T["fun"] - ev.T["jac"],
            "ms_per_fun": 1e3 * ev.T["fun"] / max(ev.C["fun"], 1),
            "ms_per_jac": 1e3 * ev.T["jac"] / max(ev.C["jac"], 1),
            "worst_inverse_px": ev.worst_inverse,
            "map_diff": {"median": float(np.median(e)), "p95": float(np.percentile(e, 95)),
                         "max": float(e.max()),
                         "gauge_removed_median": float(np.median(eg)),
                         "gauge_removed_p95": float(np.percentile(eg, 95)),
                         "gauge_removed_max": float(eg.max())},
            "audit": aud, "repeat": {"wall_s": wall2, "dloss": dl, "dtheta_max": dth},
            "projected_conditioning": cond,
            "restart": {"loss": l3, "further_reduction": loss - l3, "status": int(res3.status),
                        "optimality": float(res3.optimality)},
            "x_scale_jac": {"loss": float(2 * res_xs.cost), "wall_s": wall_xs,
                            "nfev": int(res_xs.nfev), "status": int(res_xs.status)},
            "exceeded_hard_limit": bool(over)}


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--clips", nargs="*", default=CLIPS)
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--max-nfev", type=int, default=200)
    ap.add_argument("--diag", action="store_true",
                    help="also instrument the Round-1 path (bounded at 20 optimizer iterations)")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = artifacts.ArtifactWriter(
        analysis="obj_pd_fast", script=__file__, outdir=args.outdir,
        requested_documents=args.clips, all_documents=CLIPS,
        requested_candidates=["PD/M1 benchmark"],
        source_files=["obj_pd_fast.py", "objectives.py", "lattice.py", "artifacts.py"],
        calibration_node_source="not used: plumbline/lattice observations only")
    log = open(os.path.join(args.outdir, "obj_pd_fast.log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    t00 = time.time()
    R1 = json.load(open(os.path.join(args.outdir, "obj_round1.json")))
    rng = np.random.default_rng(20260729)
    results = {}

    say("=" * 104)
    say("FAST EXACT-PD SOLVER: VERIFICATION AND MINIMAL REAL-DATA BENCHMARK")
    say("=" * 104)
    say("  Estimator, fitted point set, Delaunay weights and PD objective are UNCHANGED from Round 1.")
    say("  New: Hartley-normalized h33 = 1 homography chart, deterministic batched inverse seeded at")
    say("  the observation, exact analytic Jacobian by implicit differentiation, dense trf.")

    for clip in args.clips:
        caps = LT.load_captures(args.vsd, clip)
        D = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
        say(f"\n{'=' * 104}\n  {clip}: {D.n} fitted observations, {D.ncap} capture(s), "
            f"{2 * D.n} residuals\n{'=' * 104}")
        rc = results[clip] = {"n_observations": D.n, "ncap": D.ncap}

        if args.diag:
            say(f"\n    PROFILING THE ROUND-1 PATH (bounded; the capped run is NOT repeated)")
            rc["diagnostic"] = diagnose(
                say, D, "M1", np.array(R1[clip]["fits"]["ED/M1"]["theta14"], float))
            rc["newton_seed"] = newton_seed_comparison(
                say, D, np.array(R1[clip]["fits"]["PD/M1"]["theta14"], float))

        say(f"\n    RESIDUAL EQUIVALENCE against the Round-1 implementation at identical physical "
            f"parameters")
        rc["equivalence"] = {}
        for model in ("M0", "M1"):
            th = np.array(R1[clip]["fits"]["PD/" + model]["theta14"], float)
            rc["equivalence"][model] = check_equivalence(say, clip, D, model, th, rng)
        say(f"      note: at eta = 0 (M0) lattice.U delegates to fitter.undistort, whose differently")
        say(f"      associated arithmetic differs from the conjugated form in the last bits; that is "
            f"the floor here, not a modelling difference.")

        say(f"\n    DIRECTIONAL DERIVATIVE CHECKS (central differences, deterministic inverse)")
        rc["derivatives"] = {}
        for model in ("M0", "M1"):
            thB = np.array(R1[clip]["fits"]["B/" + model]["theta14"], float)
            thP = np.array(R1[clip]["fits"]["PD/" + model]["theta14"], float)
            ev = OB.PDExact(D, model, base=old_base(model), newton_steps=4, newton_tol=1e-11)
            p_init = ev.init_dlt(thB)
            p_mid = p_init.copy()
            p_mid[:ev.nm] *= 1.02
            p_mid[ev.ih:] += rng.normal(scale=1e-3, size=ev.npar - ev.ih)
            p_fin = ev.init_dlt(thP)
            got = []
            for lbl, p in (("line-fit B + DLT initialization", p_init),
                           ("intermediate perturbed state", p_mid),
                           ("Round-1 PD solution + DLT", p_fin)):
                say(f"      {model} at the {lbl}")
                got.append(check_derivatives(say, D, model, ev, p, lbl, rng))
            rc["derivatives"][model] = got

        say(f"\n    INVERSE AUDIT at the Round-1 PD/M1 map")
        evA = OB.PDExact(D, "M1", base=old_base("M1"))
        rc["inverse_audit"] = inverse_audit(
            say, D, evA, evA.init_dlt(np.array(R1[clip]["fits"]["PD/M1"]["theta14"], float)))

    # ---- gate: everything must pass before any timing conclusion
    worst_res = max(r["max_abs_residual_difference_px"]
                    for c in results.values() for v in c["equivalence"].values() for r in v)
    worst_der = max(g["worst_rel"] for c in results.values()
                    for v in c["derivatives"].values() for g in v)
    fails = sum(c["inverse_audit"]["inverse_failures"] for c in results.values())
    say(f"\n{'=' * 104}\n  PRE-OPTIMIZATION GATE\n{'=' * 104}")
    say(f"    worst old-vs-new residual difference {worst_res:.3e} px   (require <~ 1e-9)  "
        f"{'PASS' if worst_res < 1e-9 else 'FAIL'}")
    say(f"    worst directional-derivative relative error {worst_der:.3e}   (target ~1e-5)  "
        f"{'PASS' if worst_der < 1e-4 else 'FAIL'}")
    say(f"    inverse failures {fails}   {'PASS' if fails == 0 else 'FAIL'}")
    if worst_res >= 1e-9 or worst_der >= 1e-4 or fails:
        say(f"    GATE FAILED -- not proceeding to timing conclusions.")
        # A failed gate is a partial result and is named as one; it never takes the canonical name.
        for clip in args.clips:
            W.document_failed(clip, "pre-optimization gate failed")
        say(f"    wrote {W.write(results)} (complete=False)")
        return 1

    say(f"\n{'=' * 104}\n  MINIMAL REAL-DATA BENCHMARK: M1 only, from B/M1 plus normalized DLT\n"
        f"{'=' * 104}")
    for clip in args.clips:
        caps = LT.load_captures(args.vsd, clip)
        D = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
        thB = np.array(R1[clip]["fits"]["B/M1"]["theta14"], float)
        thP = np.array(R1[clip]["fits"]["PD/M1"]["theta14"], float)
        prev = float(R1[clip]["fits"]["PD/M1"]["loss"])
        results[clip]["benchmark_M1"] = benchmark(say, clip, D, "M1", thB, prev, thP, rng,
                                                  max_nfev=args.max_nfev)
        if results[clip]["benchmark_M1"]["exceeded_hard_limit"]:
            break

    say(f"\n{'=' * 104}\n  DECISION\n{'=' * 104}")
    for clip in args.clips:
        b = results.get(clip, {}).get("benchmark_M1")
        if not b:
            continue
        w = b["wall_s"]
        say(f"    {clip} / M1: {w:.3f} s   required <5 s {'YES' if w < 5 else 'NO'};  "
            f"target <1 s {'YES' if w < 1 else 'NO'};  stretch <0.3 s {'YES' if w < 0.3 else 'NO'}")
    for clip in args.clips:
        if results.get(clip, {}).get("benchmark_M1"):
            W.document_completed(clip, completed_candidates=["PD/M1 benchmark"])
        else:
            W.document_failed(clip, "benchmark did not complete (hard wall-clock limit)")
    say(f"\n  wrote {W.write(results)} (complete={W.manifest()['complete']})   "
        f"[{time.time() - t00:.1f}s total]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
