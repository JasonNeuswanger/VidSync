#!/usr/bin/env python3
"""First offline round for the new distortion objectives: real fits on both Clearwater clips.

Fits M0 and M1 under B, SD, ED and PD on the common reliably-indexed, doubly-constrained subset, adds
a labelled secondary ED run that also uses singly-constrained observations, then evaluates every
fitted map with the SAME external diagnostics so that no objective is judged by the residual it
defined.

Nothing here touches the document, production code, or production defaults. No known-length or
point-cloud analysis is run: that is the next round.

Writes analysis-output/obj_round1.{log,json} plus weight/support and residual plots.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sys
import time

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
CLIPS = ["Left Camera", "Right Camera"]
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LT = L("lattice")
OB = L("objectives")
SY = L("obj_synth")
GA = L("stab_gauge")
SCALE14 = LT.SCALE14
OBJS = ["B", "SD", "ED", "PD"]


# =============================================================== evaluation diagnostics


def line_rms_stored(caps, th14):
    """The current transformed-space line RMS over the STORED representation: the historical number."""
    tot, n = 0.0, 0
    for C in caps:
        u = LT.U(C.xy, th14)
        for ln in C.lines:
            mem = ln["members"]
            if len(mem) < 3:
                continue
            P = u[mem]
            q = P - P.mean(axis=0)
            t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                                 float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            r = -q[:, 0] * math.sin(t) + q[:, 1] * math.cos(t)
            tot += float(r @ r); n += len(r)
    return math.sqrt(tot / n) if n else float("nan")


def raw_line_distance(D, th14):
    """Unique-point raw distance to the fitted row/column feasible set, lines re-profiled at th14."""
    _, p = OB.loss_at(D, "ED", "M0" if th14[13] == 0.0 else "M1", th14)
    pk = OB.Pack("M0" if th14[13] == 0.0 else "M1", nline=D.nline, ncap=D.ncap,
                 nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="ED")
    r = OB.resid_ED(np.asarray(p), D, pk, np.asarray(th14) / SCALE14).reshape(-1, 2)
    dw = np.linalg.norm(r, axis=1)                          # already sqrt(a)-weighted
    dun = dw / np.sqrt(D.w)
    return {"unweighted_rms": float(np.sqrt((dun ** 2).mean())),
            "unweighted_median": float(np.median(dun)),
            "weighted_rms": float(np.sqrt((dw ** 2).mean())),
            "per_obs": dun}


def raw_lattice_residual(D, th14):
    """Raw projective-lattice residual with one H_v per capture PROFILED at the given map."""
    model = "M0" if th14[13] == 0.0 else "M1"
    _, p = OB.loss_at(D, "PD", model, th14)
    pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                 nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="PD")
    r = OB.resid_PD(np.asarray(p), D, pk, np.asarray(th14) / SCALE14).reshape(-1, 2)
    dw = np.linalg.norm(r, axis=1)
    dun = dw / np.sqrt(D.w)
    return {"unweighted_rms": float(np.sqrt((dun ** 2).mean())),
            "unweighted_median": float(np.median(dun)),
            "weighted_rms": float(np.sqrt((dw ** 2).mean())),
            "per_obs": dun, "p": np.asarray(p)}


def diagonal_holdout(caps, th14, D=None, sel=None):
    """Zero-weight diagonal families. Two readings, both reported:

    corrected-space straightness  -- orthogonal residual about each family's own fitted line
    raw projective prediction     -- for PD, the residual of the observed corner against the point the
                                     capture's PROFILED homography predicts for its lattice index. This
                                     is not tautological: the homography is fitted to all indexed
                                     corners, not to the diagonal, and the comparison is in raw pixels.
    """
    out = {"families": 0, "points": 0, "rms": float("nan"), "max": float("nan"),
            "per_capture": []}
    allr = []
    for ci, C in enumerate(caps):
        fams = [f for f in LT.diagonal_families(
            C, restrict=None if sel is None else sel[ci]) if f["adequate"]]
        u = LT.U(C.xy, th14)
        rr = []
        for f in fams:
            P = u[f["members"]]
            q = P - P.mean(axis=0)
            t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                                 float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            rr.append(-q[:, 0] * math.sin(t) + q[:, 1] * math.cos(t))
        if rr:
            v = np.concatenate(rr)
            allr.append(v)
            out["per_capture"].append(
                {"timecode": C.timecode, "families": len(fams), "points": int(len(v)),
                 "rms": float(np.sqrt((v ** 2).mean())), "max": float(np.abs(v).max()),
                 "span_median_px": float(np.median([f["span_px"] for f in fams])),
                 "n_median": float(np.median([f["n"] for f in fams]))})
            out["families"] += len(fams)
    if allr:
        v = np.concatenate(allr)
        out["points"] = int(len(v))
        out["rms"] = float(np.sqrt((v ** 2).mean()))
        out["max"] = float(np.abs(v).max())
    return out


def radial_tangential(D, th14, per_obs_vec):
    """Radial and tangential RMS of the raw residual, and first three angular harmonics."""
    c = np.asarray(th14)[:2]
    d = D.xy - c
    r = np.hypot(d[:, 0], d[:, 1])
    ph = np.arctan2(d[:, 1], d[:, 0])
    v = per_obs_vec
    rad = (v[:, 0] * d[:, 0] + v[:, 1] * d[:, 1]) / np.maximum(r, 1e-9)
    tan = (-v[:, 0] * d[:, 1] + v[:, 1] * d[:, 0]) / np.maximum(r, 1e-9)
    out = {"radial_rms": float(np.sqrt((rad ** 2).mean())),
           "tangential_rms": float(np.sqrt((tan ** 2).mean()))}
    for m in (1, 2, 3):
        for nm, y in (("rad", rad), ("tan", tan)):
            cc = float(2.0 * (y * np.cos(m * ph)).mean())
            ss = float(2.0 * (y * np.sin(m * ph)).mean())
            out[f"{nm}_m{m}_amp"] = float(math.hypot(cc, ss))
    return out


def projected_conditioning(D, objective, model, th14):
    """Singular values of the model-block Jacobian after the nuisance directions are projected out.

    J is split into model columns J_m and nuisance columns J_n (lines, latent coordinates, or
    homographies). The reported spectrum is that of (I - P_n) J_m, the part of the model sensitivity
    the nuisances cannot absorb. This is the identifiability that matters.
    """
    base = np.asarray(th14, float) / SCALE14
    pk = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                 nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective=objective)
    _, p = OB.loss_at(D, objective, model, th14)
    p = np.asarray(p, float)
    fn = OB.RESID[objective]

    def rr(q):
        return fn(q, D, pk, base)

    r0 = rr(p)
    J = np.zeros((len(r0), pk.n))
    for j in range(pk.n):
        h = 1e-6 * max(1.0, abs(p[j]))
        a = p.copy(); a[j] += h
        b = p.copy(); b[j] -= h
        J[:, j] = (rr(a) - rr(b)) / (2 * h)
    Jm = J[:, :pk.nm]
    Jn = J[:, pk.nm:]
    if Jn.shape[1] > 0:
        Q, _ = np.linalg.qr(Jn)
        Jm = Jm - Q @ (Q.T @ Jm)
    sv = np.linalg.svd(Jm, compute_uv=False)
    return {"sv": [float(v) for v in sv], "sv_max": float(sv[0]), "sv_min": float(sv[-1]),
            "condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf"),
            "n_model": pk.nm, "n_nuisance": int(Jn.shape[1])}


def map_differences(P, ths, labels):
    """Max and percentile map differences between fitted maps over the informed region."""
    out = {}
    for i in range(len(ths)):
        for j in range(i + 1, len(ths)):
            e = np.linalg.norm(LT.U(P, ths[i]) - LT.U(P, ths[j]), axis=1)
            g = GA.fit_homography(LT.U(P, ths[i]), LT.U(P, ths[j]))
            eg = np.linalg.norm(GA.apply_H(g, LT.U(P, ths[i])) - LT.U(P, ths[j]), axis=1)
            out[f"{labels[i]} vs {labels[j]}"] = {
                "median": float(np.median(e)), "p95": float(np.percentile(e, 95)),
                "max": float(e.max()),
                "gauge_removed_median": float(np.median(eg)),
                "gauge_removed_p95": float(np.percentile(eg, 95)),
                "gauge_removed_max": float(eg.max())}
    return out


# =============================================================== plots


def plot_weights(clip, caps, D, path):
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    sc = ax[0].scatter(D.xy[:, 0], D.xy[:, 1], c=D.w, s=16, cmap="viridis")
    ax[0].set_title(f"{clip}: Delaunay quadrature weight (mean 1)")
    ax[0].invert_yaxis(); ax[0].set_aspect("equal")
    plt.colorbar(sc, ax=ax[0])
    for c in range(D.ncap):
        m = D.cap_of == c
        ax[1].scatter(D.xy[m, 0], D.xy[m, 1], s=14, label=f"capture {c}: {int(m.sum())} obs")
    ax[1].set_title(f"{clip}: support by capture")
    ax[1].invert_yaxis(); ax[1].set_aspect("equal"); ax[1].legend(fontsize=8)
    ax[0].set_xlim(0, LT.FRAME_W); ax[1].set_xlim(0, LT.FRAME_W)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def plot_residuals(clip, D, per, labels, path):
    k = len(per)
    fig, ax = plt.subplots(1, k, figsize=(5.0 * k, 4.6))
    ax = np.atleast_1d(ax)
    vmax = max(float(np.percentile(v, 98)) for v in per)
    for i, (v, lb) in enumerate(zip(per, labels)):
        sc = ax[i].scatter(D.xy[:, 0], D.xy[:, 1], c=v, s=16, cmap="magma", vmin=0, vmax=vmax)
        ax[i].set_title(f"{clip} {lb}\nraw residual px (rms {np.sqrt((v ** 2).mean()):.3f})",
                        fontsize=9)
        ax[i].invert_yaxis(); ax[i].set_aspect("equal"); ax[i].set_xlim(0, LT.FRAME_W)
        plt.colorbar(sc, ax=ax[i])
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


# =============================================================== main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--clips", nargs="*", default=CLIPS)
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    say = print
    t00 = time.time()

    say("=" * 104)
    say("NEW-OBJECTIVE ROUND 1: REAL FITS ON BOTH CLEARWATER CLIPS")
    say("=" * 104)
    say("  B = current production objective, SD = unique-point block Sampson with Delaunay weights,")
    say("  ED = exact raw-space line errors-in-variables, PD = exact projective-lattice objective.")
    say("  Common subset: reliably indexed AND doubly constrained. eta bounded to |eta| <= 0.05.")

    results = {}
    for clip in args.clips:
        caps = LT.load_captures(args.vsd, clip)
        D = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
        Dall = OB.Dataset(caps, require_indexed=True, min_inc=1, kappa=3.0)
        say(f"\n{'=' * 104}\n  {clip}\n{'=' * 104}")
        for ci, cr in enumerate(D.info["components"]):
            if cr.get("kept") is not None:
                say(f"    capture {ci}: indexed components present {cr['counts']}; kept component "
                    f"{cr['kept']}, dropped {cr['dropped_observations']} observation(s) in smaller "
                    f"components so that one homography describes one lattice")
        say(f"    captures {len(caps)}; common subset {D.n} observations "
            f"({D.info['per_capture']} per capture), {D.nline} lines, incidence counts "
            f"{D.info['incidence_counts']}")
        say(f"    lines dropped for having under {D.info['min_line_pts']} selected points: "
            f"{D.info['dropped_lines']}; duplicate line records merged: "
            f"{D.info['merged_duplicate_line_records']}")
        say(f"    ED secondary set (singly constrained admitted): {Dall.n} observations, "
            f"incidence counts {Dall.info['incidence_counts']}")
        w = D.info["weights"]
        say(f"    Delaunay weights: {w['triangles_kept']} triangles kept, {w['triangles_dropped']} "
            f"dropped, min {w['weight_min']:.4f} median {w['weight_median']:.4f} max "
            f"{w['weight_max']:.4f}")
        plot_weights(clip, caps, D, os.path.join(args.outdir,
                                                 f"obj_round1_weights_{clip.split()[0]}.png"))

        fits, ths = {}, {}
        say(f"\n    FITS   {'obj':4} {'model':6} {'loss':>13} {'nres':>6} {'npar':>5} "
            f"{'nfev':>6} {'status':>7} {'eta':>11} {'runtime s':>10}")
        for obj in OBJS:
            for model in ("M0", "M1"):
                # PD is warm-started from ED rather than from B. Both are raw-space objectives, so ED
                # lands far closer to PD's optimum than B does; from B, PD M1 was still moving after
                # 3000 evaluations. This changes only the path, and the embedded-M0 and profile checks
                # below verify the endpoint independently.
                x0 = None
                if obj == "PD" and ("ED", model) in ths:
                    x0 = ths[("ED", model)][OB.MODELS[model]] / SCALE14[OB.MODELS[model]]
                r = OB.fit(D, obj, model, x0_model=x0,
                           max_nfev=(6000 if obj == "PD" else 3000))
                th = np.array(r["theta14"], float)
                fits[(obj, model)] = r
                ths[(obj, model)] = th
                say(f"           {obj:4} {model:6} {r['loss']:13.6f} {r['nres']:6d} "
                    f"{r['nparam']:5d} {r['nfev']:6d} {r['status']:7d} {th[13]:+11.7f} "
                    f"{r['runtime_s']:10.2f}")

        # ---- embedded-M0 check and eta behaviour
        say(f"\n    M1 AGAINST ITS EMBEDDED M0 SOLUTION (same objective, eta forced to zero)")
        for obj in OBJS:
            th0 = ths[(obj, "M0")].copy()
            emb, _ = OB.loss_at(D, obj, "M1", th0)
            l1 = fits[(obj, "M1")]["loss"]
            ok = l1 <= emb + 1e-9 * max(emb, 1.0)
            say(f"      {obj:4} embedded M0 loss {emb:13.6f}; optimized M1 {l1:13.6f}; "
                f"nesting holds {ok}; gain {emb - l1:+.6f}")
            fits[(obj, "M1")]["embedded_M0_loss"] = emb
            fits[(obj, "M1")]["nesting_ok"] = bool(ok)

        say(f"\n    eta PROFILE (all other free parameters and all nuisances reoptimized)")
        prof = {}
        for obj in OBJS:
            e0 = float(ths[(obj, "M1")][13])
            grid = sorted({round(v, 6) for v in
                           [0.0, e0] + [e0 + d for d in (-0.006, -0.003, -0.0015, 0.0015,
                                                         0.003, 0.006)]
                           if abs(v) <= LT.ETA_BOUND})
            row = []
            for e in grid:
                thq = ths[(obj, "M1")].copy(); thq[13] = e
                base = thq / SCALE14
                # eta is HELD at e, not zeroed: free set is M0's, zero_held is False
                rq = OB.fit(D, obj, "M1", base=base, free=OB.MODELS["M0"], zero_held=False,
                            x0_model=base[OB.MODELS["M0"]], warm=False, max_nfev=2500)
                assert abs(np.array(rq["theta14"], float)[13] - e) < 1e-12, "eta moved"
                row.append((e, rq["loss"]))
            lo = min(v for _, v in row)
            prof[obj] = row
            say(f"      {obj:4} " + "  ".join(f"{e:+.4f}:{v - lo:.4f}" for e, v in row))
            nconv = sum(1 for _, v in row if not np.isfinite(v))
            say(f"           free optimum {e0:+.7f}; at the |eta| bound "
                f"{fits[(obj, 'M1')]['at_eta_bound']}; dLoss at eta=0 "
                f"{[v for e, v in row if e == 0.0][0] - lo:.4f}")

        # ---- conditioning
        say(f"\n    PROJECTED CONDITIONING of the model block after nuisance directions removed")
        cond = {}
        for obj in OBJS:
            for model in ("M0", "M1"):
                c = projected_conditioning(D, obj, model, ths[(obj, model)])
                cond[(obj, model)] = c
                say(f"      {obj:4} {model:6} {c['n_model']} model vs {c['n_nuisance']} nuisance "
                    f"columns; sigma {c['sv_max']:.4e} .. {c['sv_min']:.4e}, condition "
                    f"{c['condition']:.4e}")

        # ---- ED secondary with singly constrained observations
        say(f"\n    ED SECONDARY RESULT, singly constrained observations admitted "
            f"(clearly labelled, not the primary comparison)")
        sec = {}
        for model in ("M0", "M1"):
            r = OB.fit(Dall, "ED", model)
            sec[model] = r
            d = float(np.median(np.linalg.norm(
                LT.U(D.xy, np.array(r["theta14"], float)) - LT.U(D.xy, ths[("ED", model)]),
                axis=1)))
            say(f"      ED-all {model}: {Dall.n} observations, loss {r['loss']:.6f}, eta "
                f"{r['eta']:+.7f}, runtime {r['runtime_s']:.2f} s; median map difference from the "
                f"primary ED fit {d:.4f} px")

        # ---- common external diagnostics
        say(f"\n    COMMON EXTERNAL DIAGNOSTICS (every map judged by the same measures)")
        say(f"      {'obj/model':11} {'storedLineRMS':>14} {'rawLine rms':>12} {'rawLine med':>12} "
            f"{'lattice rms':>12} {'diag rms':>9} {'radial':>8} {'tang':>8} {'minDet':>8} "
            f"{'roundtrip':>10}")
        ev = {}
        for obj in OBJS:
            for model in ("M0", "M1"):
                th = ths[(obj, model)]
                lr = line_rms_stored(caps, th)
                rl = raw_line_distance(D, th)
                rlat = raw_lattice_residual(D, th)
                dg = diagonal_holdout(caps, th, sel=D.sel)
                pkD = OB.Pack(model, nline=D.nline, ncap=D.ncap,
                              nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="ED")
                _, pE = OB.loss_at(D, "ED", model, th)
                vec = OB.resid_ED(np.asarray(pE), D, pkD, th / SCALE14).reshape(-1, 2)
                vec = vec / np.sqrt(D.w)[:, None]
                rt = radial_tangential(D, th, vec)
                ad = LT.admissible(th, D.xy)
                ev[(obj, model)] = {"stored_line_rms": lr, "raw_line": {k: v for k, v in rl.items()
                                                                        if k != "per_obs"},
                                    "raw_lattice": {k: v for k, v in rlat.items()
                                                    if k not in ("per_obs", "p")},
                                    "diagonal": dg, "radial_tangential": rt,
                                    "admissible": ad,
                                    "per_obs_line": rl["per_obs"],
                                    "per_obs_lattice": rlat["per_obs"]}
                say(f"      {obj + '/' + model:11} {lr:14.5f} {rl['unweighted_rms']:12.4f} "
                    f"{rl['unweighted_median']:12.4f} {rlat['unweighted_rms']:12.4f} "
                    f"{dg['rms']:9.4f} {rt['radial_rms']:8.4f} {rt['tangential_rms']:8.4f} "
                    f"{ad['min_det_full_frame']:8.4f} {ad['roundtrip_frame_px']:10.1e}")
        say(f"      note: 'storedLineRMS' is B's own metric and 'rawLine' is close to ED's own, so")
        say(f"      neither is independent validation of the objective that defines it. The "
            f"zero-weight diagonal column and the lattice column are the cross-objective ones.")

        say(f"\n    PER-CAPTURE RAW LINE RESIDUAL (rms px, unweighted)")
        for obj in OBJS:
            for model in ("M0", "M1"):
                v = ev[(obj, model)]["per_obs_line"]
                per = [float(np.sqrt((v[D.cap_of == c] ** 2).mean())) for c in range(D.ncap)]
                say(f"      {obj + '/' + model:11} " + "  ".join(f"cap{c} {p:.4f}"
                                                                 for c, p in enumerate(per)))

        say(f"\n    DIAGONAL HOLDOUT DETAIL (zero weight in every fit)")
        for obj in OBJS:
            for model in ("M0", "M1"):
                dg = ev[(obj, model)]["diagonal"]
                s = "; ".join(f"{p['timecode']}: {p['families']} fams / {p['points']} pts, rms "
                              f"{p['rms']:.4f}, max {p['max']:.3f}, median span "
                              f"{p['span_median_px']:.0f} px"
                              for p in dg["per_capture"])
                say(f"      {obj + '/' + model:11} {s}")

        say(f"\n    MAP DIFFERENCES BETWEEN OBJECTIVES over the informed region "
            f"(px; raw and after removing the projective gauge)")
        for model in ("M0", "M1"):
            lab = [f"{o}" for o in OBJS]
            md = map_differences(D.xy, [ths[(o, model)] for o in OBJS], lab)
            for k, v in md.items():
                say(f"      {model} {k:12} median {v['median']:8.3f} p95 {v['p95']:8.3f} max "
                    f"{v['max']:8.3f} | gauge-removed median {v['gauge_removed_median']:7.3f} "
                    f"p95 {v['gauge_removed_p95']:7.3f}")
            ev[("mapdiff", model)] = md

        plot_residuals(clip, D, [ev[(o, "M1")]["per_obs_line"] for o in OBJS], OBJS,
                       os.path.join(args.outdir, f"obj_round1_resid_{clip.split()[0]}.png"))

        results[clip] = {
            "dataset": D.info, "dataset_all": Dall.info,
            "captures": [{"timecode": C.timecode, **{k: v for k, v in C.notes.items()}}
                         for C in caps],
            "fits": {f"{o}/{m}": {k: v for k, v in fits[(o, m)].items()
                                  if k not in ("pack", "p")} for o in OBJS for m in ("M0", "M1")},
            "eta_profile": {o: prof[o] for o in OBJS},
            "conditioning": {f"{o}/{m}": cond[(o, m)] for o in OBJS for m in ("M0", "M1")},
            "ed_secondary": {m: {k: v for k, v in sec[m].items() if k not in ("pack", "p")}
                             for m in ("M0", "M1")},
            "evaluation": {f"{o}/{m}": {k: v for k, v in ev[(o, m)].items()
                                        if not k.startswith("per_obs")}
                           for o in OBJS for m in ("M0", "M1")},
            "map_differences": {m: ev[("mapdiff", m)] for m in ("M0", "M1")},
        }

    with open(os.path.join(args.outdir, "obj_round1.json"), "w") as fh:
        json.dump(results, fh, indent=1, default=float)
    say(f"\n  wrote {os.path.join(args.outdir, 'obj_round1.json')} and plots   "
        f"[{time.time() - t00:.0f}s total]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
