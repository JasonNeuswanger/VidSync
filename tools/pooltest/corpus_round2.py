#!/usr/bin/env python3
"""Reduced round: full-sample geometric adequacy, SD-D, corrected diagnostics, consistency, transfer.

SCOPE AND HONEST FRAMING, per the 2026-07-30 revised specification. Node-level calibration holdout was
dropped deliberately: production calibrates on the complete dense grid, M0 and M1 are low-dimensional
smooth models, and withholding nodes would measure performance under deliberately degraded calibration
rather than the intended application. NOTHING here is out-of-sample. Every residual reported is a
FULL-SAMPLE, method-neutral geometric-adequacy measure, and is labelled as such.

  * B/M1 vs B/M0 on projective residual is OBJECTIVE-independent (B minimizes line ODR) but NOT
    data-independent.
  * PD-D's projective residual is close to its own fitting objective and is WEAKER evidence.
  * Consistent improvement across independently calibrated clips is replication, not validation.
  * None of this establishes downstream stereo accuracy or identifies eta's physical mechanism.

STRATA are the five frozen nominal optical configurations. Rig position and document membership are
descriptive provenance and never group, pool, pair or stratify anything.

No established estimator code is modified and no fold-specific calibration is performed.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

import corpus
import corpus_freeze as CF
import harness_import
import heldout as HO
import sd_real as SR

OB = harness_import.load("objectives")
LT = harness_import.load("lattice")
SF = harness_import.load("sd_fast")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
GRID = None


def frame_grid(step=60):
    global GRID
    if GRID is None:
        xs = np.arange(step / 2, LT.FRAME_W, step)
        ys = np.arange(step / 2, LT.FRAME_H, step)
        X, Y = np.meshgrid(xs, ys)
        GRID = np.column_stack([X.ravel(), Y.ravel()])
    return GRID


def physical_diagnostics(th14):
    """Estimator-neutral map diagnostics. Uses NO native objective value of any kind.

    The earlier round passed sqrt(loss/n) to `on_physical_branch`, but that quantity is on a different
    scale for B (line ODR), PD-D (projective lattice) and SD-D (block Sampson), so gate results derived
    from it were not comparable across estimators. Everything below is a property of the MAP on a fixed
    frame grid and is therefore directly comparable.
    """
    P = frame_grid()
    d = dict(finite_params=bool(np.all(np.isfinite(th14))))
    U = LT.U(P, th14)
    d["finite_predictions"] = bool(np.all(np.isfinite(U)))
    if not (d["finite_params"] and d["finite_predictions"]):
        return dict(d, usable=False)
    J = LT.jac_U(P, th14)
    det = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
    sv = np.linalg.svd(J, compute_uv=False)
    cond = sv[:, 0] / np.maximum(sv[:, 1], 1e-300)
    inv, conv, maxres = LT.inv_U(U, th14)
    rt = np.hypot(*(inv - P).T)
    disp = U - P
    r = np.hypot(*(P - np.array([th14[0], th14[1]])).T)
    dr = np.hypot(*disp.T)
    d.update(min_det=float(det.min()), max_det=float(det.max()),
             det_sign_changes=bool(det.min() <= 0 <= det.max()),
             max_condition=float(cond.max()), min_singular=float(sv[:, 1].min()),
             max_singular=float(sv[:, 0].max()),
             inverse_all_converged=bool(np.all(conv)),
             inverse_failures=int((~conv).sum()),
             inverse_max_residual_px=float(maxres),
             roundtrip_max_px=float(rt.max()), roundtrip_median_px=float(np.median(rt)),
             displacement_median_px=float(np.median(dr)), displacement_max_px=float(dr.max()),
             displacement_at_max_radius_px=float(dr[np.argmax(r)]),
             expansion=float(np.sqrt(max(det.max(), 0.0))),
             contraction=float(np.sqrt(max(det.min(), 0.0))))
    # physical branch, judged on MAP behaviour alone: orientation-preserving, invertible, bounded
    d["on_physical_branch_map"] = bool(det.min() > 0 and np.all(conv)
                                       and d["max_condition"] < 10.0
                                       and d["roundtrip_max_px"] < 1e-6)
    d["gate_admissible"] = bool(LT.admissible(th14, P))
    d["usable"] = True
    return d


def projective_residual(caps, th14):
    """Shared FULL-SAMPLE observed-pixel projective residual, all eligible observations.

    One homography per capture from canonical lattice index to CORRECTED points; the prediction is
    mapped back through C^-1 and scored in observed pixels. Fails closed on inverse failure.
    """
    tot, npts, per = [], 0, []
    for C in caps:
        elig = HO._eligible(C)
        if elig.sum() < 8:
            continue
        s = HO.score_fold(C, th14, elig, elig)   # train == test: FULL-SAMPLE, by construction
        if not s["valid"]:
            return dict(valid=False, reason=s.get("reason"), timecode=C.timecode)
        per.append(dict(timecode=C.timecode, n=s["n_test"], obs_rms=s["obs_rms"],
                        obs_median=s["obs_median"], obs_p95=s["obs_p95"], cor_rms=s["cor_rms"]))
        tot.append(s["obs_rms"] ** 2 * s["n_test"])
        npts += s["n_test"]
    if not per:
        return dict(valid=False, reason="no eligible capture")
    return dict(valid=True, n=npts, obs_rms=float(np.sqrt(sum(tot) / npts)),
                obs_median=float(np.median([p["obs_median"] for p in per])),
                obs_p95=float(np.max([p["obs_p95"] for p in per])),
                cor_rms=float(np.median([p["cor_rms"] for p in per])), per_capture=per)


def fit_clip(vsd, clip):
    caps, D, Dind, lat_ok = SR.build(vsd, clip)
    fits = {}
    for model in ("M0", "M1"):
        b = OB.fit(D, "B", model, max_nfev=3000)
        fits[f"B/{model}"] = dict(theta14=b["theta14"], eta=float(b["theta14"][13]),
                                  estimator="B", mode="full-grid")
        if lat_ok:
            ev = OB.PDExact(Dind, model)
            res, wt = ev.fit(ev.init_dlt(np.asarray(b["theta14"], float)))
            th = ev.theta(res.x)
            fits[f"PD-D/{model}"] = dict(theta14=th.tolist(), eta=float(th[13]),
                                         estimator="PD-D", mode="full-grid",
                                         converged=bool(res.status > 0))
        # SD-D, MATCHED: exactly the observations PD-D sees (indexed, min_inc=2)
        try:
            F = SR.Fitter(Dind if lat_ok else D, model)
            r = F.staged()
            fits[f"SD-D-matched/{model}"] = dict(theta14=r["theta14"], eta=float(r["eta"]),
                                                 estimator="SD-D", mode="matched",
                                                 converged=bool(r["completed"]),
                                                 n_obs=int((Dind if lat_ok else D).n))
        except Exception as e:
            fits[f"SD-D-matched/{model}"] = dict(error=f"{type(e).__name__}: {e}")
        # SD-D, OPERATIONAL FALLBACK: the production non-lattice view. Lattice identities are
        # withheld from the estimator and retained externally for scoring only.
        try:
            Dfb = OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)
            F = SR.Fitter(Dfb, model)
            r = F.staged()
            fits[f"SD-D-fallback/{model}"] = dict(theta14=r["theta14"], eta=float(r["eta"]),
                                                  estimator="SD-D", mode="fallback",
                                                  converged=bool(r["completed"]),
                                                  n_obs=int(Dfb.n), nline=int(Dfb.nline))
        except Exception as e:
            fits[f"SD-D-fallback/{model}"] = dict(error=f"{type(e).__name__}: {e}")
    for k, f in fits.items():
        if "error" in f:
            continue
        th = np.asarray(f["theta14"], float)
        f["projective_full_sample"] = projective_residual(caps, th)
        f["diagnostics"] = physical_diagnostics(th)
    return caps, fits, dict(lat_ok=bool(lat_ok), n_full=int(D.n), n_indexed=int(Dind.n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="full")
    ap.add_argument("--docs", nargs="*", default=None)
    args = ap.parse_args()
    fh = open(os.path.join(OUT, f"corpus_round2_{args.scope}.log"), "w")

    def say(s=""):
        print(s, flush=True)
        fh.write(s + "\n")
        fh.flush()

    frz = json.load(open(os.path.join(OUT, "corpus_freeze.json")))
    cfg_by_clip = {(c["document"], c["clip"]): c for c in frz["clips"]}
    say("=" * 104)
    say("REDUCED ROUND -- FULL-SAMPLE geometric adequacy. NOTHING HERE IS OUT OF SAMPLE.")
    say(f"freeze {frz['analysis_config_sha256'][:16]}   scorer {HO.CONFIG_SHA256[:16]}")
    say("Strata = 5 nominal optical configurations. Rig position and document are provenance only.")
    say("=" * 104)

    docs = [d for d in corpus.documents() if d["present"]]
    if args.docs:
        docs = [d for d in docs if d["code"] in set(args.docs)]

    results, maps = [], {}
    t0 = time.time()
    for d in docs:
        for clip, _ in corpus.clips_with_plumblines(d["vsd"]):
            t = time.time()
            caps, fits, info = fit_clip(d["vsd"], clip)
            key = (d["code"], clip)
            meta = cfg_by_clip.get(key, {})
            rec = dict(document=d["code"], clip=clip, config=meta.get("config"),
                       rig_position=meta.get("rig_position"), info=info,
                       fits={k: {kk: vv for kk, vv in v.items() if kk != "per_capture"}
                             for k, v in fits.items()})
            results.append(rec)
            maps[f"{d['code']}|{clip}"] = {k: v.get("theta14") for k, v in fits.items()
                                           if "theta14" in v}
            got = {k: (v["projective_full_sample"]["obs_rms"]
                       if v.get("projective_full_sample", {}).get("valid") else None)
                   for k, v in fits.items()}
            say(f"  {d['code']} {clip[:13]:13} {str(meta.get('config'))[:34]:34} [{time.time()-t:5.1f}s]")
            for k in sorted(got):
                e = fits[k].get("eta")
                say(f"        {k:22} obs_rms {('%8.3f' % got[k]) if got[k] is not None else '  FAILED'}"
                    f"  eta {e:+.5f}" if e is not None else f"        {k:22} {fits[k].get('error','')}")
    say(f"\n  {len(results)} clips in {time.time()-t0:.0f}s")

    p = os.path.join(OUT, f"corpus_round2_{args.scope}.json")
    json.dump(dict(freeze=frz["analysis_config_sha256"], scorer=HO.CONFIG_SHA256,
                   clips=results, maps=maps), open(p, "w"), indent=1)
    say(f"  wrote {p}")
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
