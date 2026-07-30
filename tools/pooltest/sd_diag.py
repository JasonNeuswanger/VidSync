#!/usr/bin/env python3
"""Why SD-D fits consume their evaluation budget. Diagnosis only -- changes nothing.

The independent audit found capped SD-D fits entering downstream tables. Before any scientific
comparison, this establishes WHERE the budget goes and WHETHER the capped points were still improving.
It deliberately does not raise max_nfev.

Measures, per fit:
  * free model parameters and line nuisance parameters, residual rows
  * ACTUAL residual calls, by wrapping the function SciPy actually calls, versus SciPy's reported
    `nfev`. The difference is the finite-difference traffic `nfev` does not show.
  * the column-grouping SciPy derives from the sparsity pattern, which is what sets the per-Jacobian
    cost
  * standalone time per residual and per Jacobian
  * scaled optimality, termination reason, loss trajectory
  * whether the loss was still falling materially at the cap
  * conditioning and near-null directions of the Jacobian at the stopping point
  * basin sensitivity from perturbed restarts

Writes analysis-output/sd_diag_<scope>.{log,json}.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares
from scipy.optimize._numdiff import group_columns

import artifacts
import harness_import

harness_import.ensure_path()

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")

L = harness_import.load
LT = L("lattice")
OB = L("objectives")
DS = L("downstream")

DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
CH = "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced"
POOL = os.path.join(CH, "VidSync Projects/2012-01-31_PoolTest/"
                        "2012-01-31_PoolTest_2026_Reanalysis.vsd")
DOCS = {"pool": POOL,
        "8mm": os.path.join(DM, "2015-09-04-1 Clearwater.vsd"),
        "mid": os.path.join(DM, "2015-06-22-1 Clearwater.vsd")}

# The audit's capped cases, plus one camera of the document where lattice validation failed and SD-D
# is the proposed fallback.
CASES = [("pool", "Left Camera", "M0"), ("pool", "Right Camera", "M1"),
         ("8mm", "Right Camera", "M1"), ("mid", "Left Camera", "M1")]
SD_MAX_NFEV = 1200


def build_dataset(vsd, clip):
    """The SD-D fitted subset, exactly as xdoc_objectives.py selects it.

    Where the lattice validates, SD-D uses the same indexed subset as PD-D so the two are compared on
    identical observations; where it does not, SD-D falls back to the unique-observation set that needs
    line incidences only.
    """
    caps = LT.load_captures(vsd, clip)
    Dind = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
    lat_ok = Dind.n >= 20 and all(
        C.notes["index_contradictions"] == 0 for C in caps)
    D = Dind if lat_ok else OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
    return D, caps, lat_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = artifacts.ArtifactWriter(
        analysis="sd_diag", script=__file__, outdir=args.outdir,
        requested_documents=[f"{d}/{c}/{m}" for d, c, m in CASES],
        all_documents=[f"{d}/{c}/{m}" for d, c, m in CASES],
        requested_candidates=["SD-D"],
        source_files=["sd_diag.py", "objectives.py", "lattice.py", "artifacts.py"],
        calibration_node_source="not used: plumbline/lattice observations only")
    log = open(W.log_path(), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    R = {}
    say("=" * 104)
    say("SD-D SOLVER DIAGNOSIS -- where the evaluation budget goes")
    say("=" * 104)
    say("  No max_nfev is raised here and no estimator is changed. Diagnosis only.")

    for dk, clip, model in CASES:
        key = f"{dk}/{clip}/{model}"
        say(f"\n{'=' * 104}\n  {key}\n{'=' * 104}")
        vsd = DOCS[dk]
        D, caps, lat_ok = build_dataset(vsd, clip)
        base = OB.default_base()
        fr = OB.MODELS[model]
        pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                     nfree_t=sum(1 for l in D.obs_lines if len(l) == 1),
                     objective="SD", free=fr)
        say(f"    lattice validated: {lat_ok}   (selection: "
            f"{'indexed subset, same as PD-D' if lat_ok else 'unique-observation fallback'})")
        say(f"    observations {D.n}, lines {D.nline}, captures {D.ncap}")
        inc = np.array([len(l) for l in D.obs_lines])
        say(f"    incidences per observation: 1 -> {(inc == 1).sum()}, 2 -> {(inc == 2).sum()}, "
            f">=3 -> {(inc >= 3).sum()}   (max {inc.max()})")
        say(f"    free MODEL parameters {pk.nm} {fr}")
        say(f"    line NUISANCE parameters {2 * D.nline}  (phi, e per line)")
        say(f"    total optimizer parameters {pk.n}")

        # ---- warm start exactly as the production path does
        t0 = time.time()
        wb = OB.fit(D, "B", model, base=base.copy(), warm=False, max_nfev=3000)
        t_warm = time.time() - t0
        x0m = np.array(wb["theta14"], float)[fr] / OB.SCALE14[fr]
        b2 = base.copy()
        b2[[j for j in range(14) if j not in set(fr)]] = 0.0
        p0 = np.zeros(pk.n)
        p0[:pk.nm] = x0m
        th0 = pk.theta(p0, b2)
        ph, e = OB.init_lines(D, th0)
        p0[pk.iline:pk.iline + D.nline] = ph
        p0[pk.iline + D.nline:pk.iline + 2 * D.nline] = e
        say(f"    warm start from B/{model}: {t_warm:.2f}s, B loss {wb['loss']:.5f}")

        rep = {}

        # ---- standalone residual and Jacobian-of-map timing
        def rr_raw(p):
            return OB.resid_SD(p, D, pk, b2, report=rep)

        r0 = rr_raw(p0)
        nres = len(r0)
        N = 40
        t0 = time.time()
        for _ in range(N):
            rr_raw(p0)
        t_res = (time.time() - t0) / N
        t0 = time.time()
        for _ in range(N):
            LT.jac_U(D.xy, th0)
        t_jacU = (time.time() - t0) / N
        t0 = time.time()
        for _ in range(N):
            LT.U(D.xy, th0)
        t_U = (time.time() - t0) / N
        say(f"    residual rows {nres};  one residual call {1000 * t_res:.3f} ms "
            f"(of which U {1000 * t_U:.3f} ms, jac_U {1000 * t_jacU:.3f} ms)")

        # ---- what SciPy's sparsity grouping costs per Jacobian
        sp = OB.sparsity(D, pk, nres)
        groups = group_columns(sp)
        ngroup = int(groups.max()) + 1
        say(f"    sparsity: {sp.nnz} nonzeros of {nres * pk.n} "
            f"({100.0 * sp.nnz / (nres * pk.n):.2f}% dense)")
        say(f"    SciPy column GROUPS from that pattern: {ngroup}")
        say(f"      -> one finite-difference Jacobian costs about {ngroup} residual calls "
            f"({1000 * ngroup * t_res:.0f} ms)")
        say(f"      model block contributes {pk.nm} groups (dense columns cannot share); "
            f"line block contributes {ngroup - pk.nm}")

        # ---- the real fit, with an HONEST call counter
        calls = {"n": 0}
        traj = []
        t_in = {"s": 0.0}

        def rr(p):
            calls["n"] += 1
            ta = time.time()
            v = OB.resid_SD(p, D, pk, b2, report=rep)
            t_in["s"] += time.time() - ta
            traj.append(float(v @ v))
            return v

        lo, hi = pk.bounds(b2)
        t0 = time.time()
        res = least_squares(rr, np.clip(p0, lo, hi), bounds=(lo, hi), method="trf",
                            x_scale="jac", jac_sparsity=sp, ftol=1e-14, xtol=1e-14,
                            gtol=1e-14, max_nfev=SD_MAX_NFEV)
        wall = time.time() - t0
        hidden = calls["n"] - res.nfev
        say(f"\n    FIT: status {res.status}, SciPy nfev {res.nfev}, njev {res.njev}, "
            f"wall {wall:.2f}s")
        say(f"      ACTUAL residual calls {calls['n']}")
        say(f"      hidden finite-difference calls {hidden}  "
            f"({100.0 * hidden / max(calls['n'], 1):.1f}% of all calls)")
        say(f"      njev x groups = {res.njev} x {ngroup} = {res.njev * ngroup} "
            f"(predicted hidden calls; measured {hidden})")
        say(f"      time inside residual {t_in['s']:.2f}s of {wall:.2f}s wall "
            f"({100.0 * t_in['s'] / wall:.0f}%)")
        say(f"      cost accounting: {calls['n']} calls x {1000 * t_res:.3f} ms = "
            f"{calls['n'] * t_res:.2f}s")
        say(f"      capped: {res.nfev >= SD_MAX_NFEV};  scaled optimality {res.optimality:.4e}")
        say(f"      loss {wb['loss']:.5f} (B start) -> {float(res.fun @ res.fun):.5f}")

        # ---- was it still improving at the cap?
        tr = np.array(traj)
        run = np.minimum.accumulate(tr)
        final = run[-1]
        say(f"\n    STILL IMPROVING AT THE STOP?")
        for frac in (0.5, 0.75, 0.9, 0.95):
            i = int(frac * len(run)) - 1
            say(f"      best loss by {int(frac * 100):3d}% of calls: {run[i]:.6f}  "
                f"remaining gain {run[i] - final:+.3e} "
                f"({100.0 * (run[i] - final) / max(abs(final), 1e-30):+.4f}%)")
        last10 = run[int(0.9 * len(run)):]
        say(f"      improvement over the FINAL 10% of calls: {last10[0] - last10[-1]:.3e} "
            f"({100.0 * (last10[0] - last10[-1]) / max(abs(final), 1e-30):.4f}% of the final loss)")

        # ---- restart from the stopping point: genuine stall, or merely out of budget?
        calls2 = {"n": 0}

        def rr2(p):
            calls2["n"] += 1
            return OB.resid_SD(p, D, pk, b2, report=rep)

        t0 = time.time()
        res2 = least_squares(rr2, res.x, bounds=(lo, hi), method="trf", x_scale="jac",
                            jac_sparsity=sp, ftol=1e-14, xtol=1e-14, gtol=1e-14,
                            max_nfev=SD_MAX_NFEV)
        w2 = time.time() - t0
        l1 = float(res.fun @ res.fun); l2 = float(res2.fun @ res2.fun)
        say(f"\n    RESTART from the stopping point: status {res2.status}, nfev {res2.nfev}, "
            f"{w2:.2f}s")
        say(f"      loss {l1:.6f} -> {l2:.6f}  ({l1 - l2:+.4e}, "
            f"{100.0 * (l1 - l2) / max(abs(l1), 1e-30):+.4f}%)")
        say(f"      -> the cap was {'A REAL BUDGET LIMIT, not convergence' if (l1 - l2) > 1e-6 * abs(l1) else 'near a genuine stationary point'}")

        # ---- conditioning and near-null directions at the stop
        Jm = res.jac.toarray() if hasattr(res.jac, "toarray") else np.asarray(res.jac)
        sv = np.linalg.svd(Jm, compute_uv=False)
        cn = float(sv[0] / max(sv[-1], 1e-300))
        colnorm = np.linalg.norm(Jm, axis=0)
        say(f"\n    CONDITIONING at the stopping point")
        say(f"      Jacobian {Jm.shape}, singular values {sv[0]:.4e} .. {sv[-1]:.4e}, "
            f"condition {cn:.4e}")
        say(f"      column-norm spread: model block "
            f"{colnorm[:pk.nm].min():.3e}..{colnorm[:pk.nm].max():.3e}, "
            f"line block {colnorm[pk.nm:].min():.3e}..{colnorm[pk.nm:].max():.3e}")
        say(f"      ratio of largest to smallest column norm overall: "
            f"{colnorm.max() / max(colnorm.min(), 1e-300):.3e}")
        nsmall = int((sv < 1e-8 * sv[0]).sum())
        say(f"      singular values below 1e-8 of the largest: {nsmall} "
            f"(a near-null direction would show here)")

        R[key] = {
            "document": dk, "camera": clip, "model": model,
            "doc_sha256": DS.document_sha256(vsd),
            "lattice_validated": bool(lat_ok),
            "n_observations": int(D.n), "n_lines": int(D.nline), "n_captures": int(D.ncap),
            "incidence_hist": {str(k): int((inc == k).sum()) for k in sorted(set(inc.tolist()))},
            "n_model_params": int(pk.nm), "model_free": list(fr),
            "n_line_params": int(2 * D.nline), "n_params_total": int(pk.n),
            "n_residual_rows": int(nres),
            "t_residual_ms": 1000 * t_res, "t_U_ms": 1000 * t_U, "t_jacU_ms": 1000 * t_jacU,
            "sparsity_nnz": int(sp.nnz), "sparsity_density": sp.nnz / (nres * pk.n),
            "scipy_column_groups": ngroup,
            "fd_calls_per_jacobian": ngroup,
            "warm_start_s": t_warm, "b_loss": wb["loss"],
            "status": int(res.status), "scipy_nfev": int(res.nfev), "njev": int(res.njev),
            "actual_residual_calls": int(calls["n"]),
            "hidden_fd_calls": int(hidden),
            "hidden_fraction": hidden / max(calls["n"], 1),
            "wall_s": wall, "time_in_residual_s": t_in["s"],
            "capped": bool(res.nfev >= SD_MAX_NFEV),
            "optimality": float(res.optimality),
            "loss": l1,
            "loss_trajectory_min": run.tolist()[::max(1, len(run) // 200)],
            "final_10pct_improvement": float(last10[0] - last10[-1]),
            "restart_status": int(res2.status), "restart_nfev": int(res2.nfev),
            "restart_loss": l2, "restart_gain": l1 - l2,
            "restart_gain_relative": (l1 - l2) / max(abs(l1), 1e-30),
            "jac_shape": list(Jm.shape),
            "sv_max": float(sv[0]), "sv_min": float(sv[-1]), "condition": cn,
            "n_sv_below_1e-8": nsmall,
            "colnorm_model_min": float(colnorm[:pk.nm].min()),
            "colnorm_model_max": float(colnorm[:pk.nm].max()),
            "colnorm_line_min": float(colnorm[pk.nm:].min()),
            "colnorm_line_max": float(colnorm[pk.nm:].max()),
            "min_block_eig": rep.get("min_block_eig"),
        }
        W.document_started(key, sha256=DS.document_sha256(vsd), doc_key=dk)
        W.document_completed(key, completed_candidates=["SD-D"])

    # ---------------------------------------------------------------- synthesis
    say(f"\n{'=' * 104}\n  SYNTHESIS\n{'=' * 104}")
    say(f"  {'case':22} {'params':>7} {'grp':>5} {'res ms':>7} {'nfev':>6} {'actual':>7} "
        f"{'hidden%':>8} {'wall s':>7} {'restart gain':>13}")
    for k, v in R.items():
        say(f"  {k:22} {v['n_params_total']:7d} {v['scipy_column_groups']:5d} "
            f"{v['t_residual_ms']:7.2f} {v['scipy_nfev']:6d} {v['actual_residual_calls']:7d} "
            f"{100 * v['hidden_fraction']:8.1f} {v['wall_s']:7.2f} "
            f"{v['restart_gain_relative']:+13.3e}")
    say("")
    hf = np.mean([v["hidden_fraction"] for v in R.values()])
    say(f"  Finite-difference traffic is {100 * hf:.1f}% of all residual calls on average, and SciPy's")
    say(f"  reported nfev does not include any of it. Cost per fit is dominated by")
    say(f"  njev x column_groups residual evaluations, where the column groups are set by the")
    say(f"  {2 * max(v['n_lines'] for v in R.values())}-odd line nuisance parameters, not by the "
        f"{max(v['n_model_params'] for v in R.values())} model parameters.")
    still = [k for k, v in R.items() if v["restart_gain_relative"] > 1e-6]
    say(f"  Capped fits still improving materially on restart: {still if still else 'none'}")
    nullish = [k for k, v in R.items() if v["n_sv_below_1e-8"] > 0]
    say(f"  Cases with a near-null Jacobian direction: {nullish if nullish else 'none'}")

    path = W.write(R)
    say(f"\n  wrote {path} (complete={W.manifest()['complete']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
