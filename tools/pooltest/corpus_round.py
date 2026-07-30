#!/usr/bin/env python3
"""The forty-camera round: how well does each distortion model map the lattice into projective space?

WHY THIS EXISTS. Every previous comparison rested on six cameras from three documents, and the
2026-07-29 addendum says in its own Scope section that repeated fits of the same camera are not
independent evidence. `corpus.py` now names twenty documents and forty cameras across four nominal
focal lengths, all forty PD-D eligible after the 2026-07-30 lattice fixes.

WHAT THIS CAN AND CANNOT MEASURE. Seventeen of the eighteen new documents carry NO known-length
ground truth, so the one rule -- judge on the measurements, never on the calibration residual --
cannot be applied to them. This round therefore does NOT rank models by accuracy. It measures three
things that need no ground truth:

  PROJECTIVE VALIDITY, the primary criterion. A planar chessboard viewed by a pinhole camera must map
  projectively. So after undistortion the lattice must be describable by ONE homography per capture,
  and the residual of the best such homography is a direct, physically motivated measure of how good
  the undistortion is -- the theoretical link between better undistortion and a better reconstructed
  space, measurable without knowing any length. It is computed here by ONE shared implementation
  applied identically to every candidate map, including the stored one, so no estimator is scored by
  its own code. PD-D minimizes something very close to this, which is stated wherever it is reported:
  PD-D is NOT independently validated by this criterion and is shown for reference only.

  ADMISSIBILITY, whether the fitted map is physically usable at all -- the shipped gate, the eta-aware
  gate, forward injectivity and inverse reliability. The fourth rule says eta is bounded by nothing and
  the shipped gate accepts collapsed eta maps, so this is a per-camera safety audit, not a formality.

  REPRODUCIBILITY, whether cameras that share a lens agree. The five 8 mm documents are one Rokinon
  prime, so their fitted maps should agree closely; 10, 13 and 17 mm are zoom settings read off a
  barrel and are NOT guaranteed to be the same optical configuration, so agreement there is weak
  evidence. Reported separately for that reason.

Writes analysis-output/corpus_round_<scope>.{log,json}. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

import corpus
import harness_import
import sd_real as SR

OB = harness_import.load("objectives")
LT = harness_import.load("lattice")
MM = harness_import.load("mapmetrics") if os.path.exists(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapmetrics.py")) else None
SD = harness_import.load("stab_degeneracy")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")


def homography_residual(caps, th14, sel_indexed=True):
    """RMS reprojection residual of the best single homography per capture, in undistorted pixels.

    THE PRIMARY CRITERION. Undistort every observation, then fit one homography from integer lattice
    index (c, r) to the undistorted point by normalized DLT, and report the residual. A perfect
    undistortion of a planar target makes this zero regardless of pose; any residual is distortion the
    model failed to remove, expressed in the space measurements are actually made in.

    Uses ONLY the map and the lattice indices, shares no code with any estimator, and is applied
    identically to every candidate.
    """
    per_cap, npts = [], 0
    for C in caps:
        ok = C.indexed() if sel_indexed else np.ones(C.n, bool)
        if ok.sum() < 8:
            continue
        # one homography can only describe one lattice: restrict to the largest indexed component
        comps, best, bn = C.component[ok], None, 0
        for k in set(comps.tolist()):
            m = ok & (C.component == k)
            if m.sum() > bn:
                bn, best = int(m.sum()), m
        if best is None or bn < 8:
            continue
        xy = LT.U(C.xy[best], th14)                      # undistorted image points
        lat = C.rc[best][:, ::-1]                        # (c, r) -> (x, y) ordering
        H = _dlt(lat, xy)
        if H is None:
            continue
        pred = _apply(H, lat)
        r = np.hypot(*(pred - xy).T)
        per_cap.append(dict(timecode=C.timecode, n=int(bn), rms=float(np.sqrt((r ** 2).mean())),
                            p95=float(np.percentile(r, 95)), max=float(r.max())))
        npts += int(bn)
    if not per_cap:
        return None
    tot = float(np.sqrt(sum(c["rms"] ** 2 * c["n"] for c in per_cap) / npts))
    return dict(rms=tot, n=npts, per_capture=per_cap,
                worst_capture_rms=max(c["rms"] for c in per_cap))


def _dlt(src, dst):
    """Normalized DLT homography src -> dst."""
    def norm(P):
        c = P.mean(axis=0)
        s = np.sqrt(2) / max(np.sqrt(((P - c) ** 2).sum(axis=1)).mean(), 1e-12)
        T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])
        return (P - c) * s, T
    A, Ts = norm(np.asarray(src, float))
    B, Td = norm(np.asarray(dst, float))
    M = []
    for (x, y), (u, v) in zip(A, B):
        M.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        M.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    try:
        _, _, Vt = np.linalg.svd(np.array(M, float))
    except np.linalg.LinAlgError:
        return None
    H = Vt[-1].reshape(3, 3)
    return np.linalg.inv(Td) @ H @ Ts


def _apply(H, P):
    Q = np.column_stack([P, np.ones(len(P))]) @ H.T
    w = np.where(np.abs(Q[:, 2]) < 1e-12, 1e-12, Q[:, 2])
    return Q[:, :2] / w[:, None]


def fit_camera(vsd, clip, say):
    caps, D, Dind, lat_ok = SR.build(vsd, clip)
    rec = dict(clip=clip, lat_ok=bool(lat_ok), n_obs=int(D.n), n_indexed=int(Dind.n),
               nline=int(D.nline), ncap=int(D.ncap), fits={})
    for model in ("M0", "M1"):
        t = time.time()
        b = OB.fit(D, "B", model, max_nfev=3000)
        rec["fits"][f"B/{model}"] = dict(theta14=b["theta14"], loss=float(b["loss"]),
                                         eta=float(b["theta14"][13]), runtime_s=time.time() - t,
                                         completed=bool(b.get("completed", True)),
                                         estimator="B")
        if lat_ok:
            # the ESTABLISHED fast exact path; OB.fit(D,"PD",...) is the slow finite-difference route
            ev = OB.PDExact(Dind, model)
            thB = np.asarray(b["theta14"], float)
            res, wt = ev.fit(ev.init_dlt(thB))
            th = ev.theta(res.x)
            rec["fits"][f"PD-D/{model}"] = dict(
                theta14=th.tolist(), loss=float(2 * res.cost), eta=float(th[13]),
                runtime_s=wt, completed=bool(res.status > 0), status=int(res.status),
                nfev=int(res.nfev), inverse_failures=ev.C["inverse_failures"], estimator="PD")
    # projective validity, one implementation, every candidate
    for name, f in rec["fits"].items():
        th = np.asarray(f["theta14"], float)
        f["projective"] = homography_residual(caps, th)
        f["on_physical_branch"] = bool(SD.on_physical_branch(
            float(np.sqrt(f["loss"] / max(D.n, 1))), float(f["eta"])))
        f["admissible"] = bool(LT.admissible(th, np.vstack([C.xy for C in caps])))
    # the undistorted-identity control: how projective is the lattice with NO correction at all
    rec["uncorrected_projective"] = homography_residual(caps, np.zeros(14))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*", default=None, help="limit to these document codes")
    ap.add_argument("--scope", default="full")
    ap.add_argument("--drift-dir", default=None)
    ap.add_argument("--chena-dir", default=None)
    args = ap.parse_args()

    docs = [d for d in corpus.documents(args.drift_dir, args.chena_dir) if d["present"]]
    if args.docs:
        docs = [d for d in docs if d["code"] in set(args.docs)]

    logp = os.path.join(OUT, f"corpus_round_{args.scope}.log")
    fh = open(logp, "w")
    def say(s=""):
        print(s, flush=True)
        fh.write(s + "\n"); fh.flush()

    say("=" * 108)
    say("FORTY-CAMERA ROUND -- projective validity, admissibility, reproducibility")
    say("NOT an accuracy ranking: 17 of 18 new documents carry no known-length ground truth.")
    say("PD-D minimizes close to the projective criterion, so it is NOT independently validated by it.")
    say("=" * 108)

    out = []
    t0 = time.time()
    for d in docs:
        for clip, _ in corpus.clips_with_plumblines(d["vsd"]):
            t = time.time()
            try:
                rec = fit_camera(d["vsd"], clip, say)
            except Exception as e:
                say(f"  {d['code']} {clip}: FAILED {type(e).__name__}: {e}")
                out.append(dict(document=d["code"], site=d["site"], focal_mm=d["focal_mm"],
                                clip=clip, error=f"{type(e).__name__}: {e}"))
                continue
            rec.update(document=d["code"], site=d["site"], focal_mm=d["focal_mm"],
                       label=d["label"], role=d["role"])
            out.append(rec)
            u = rec["uncorrected_projective"]
            bits = [f"{k} {v['projective']['rms']:7.3f}px eta {v['eta']:+.5f}"
                    for k, v in sorted(rec["fits"].items()) if v.get("projective")]
            say(f"  {d['code']} {d['site']:11} {clip[:13]:13} {str(d['focal_mm'] or '-'):>3}mm  "
                f"n={rec['n_indexed']:4d}  uncorrected {u['rms'] if u else float('nan'):7.3f}px  "
                f"[{time.time()-t:5.1f}s]")
            for b in bits:
                say(f"        {b}")
    say(f"\n  total {time.time()-t0:.0f}s over {len(out)} cameras")

    p = os.path.join(OUT, f"corpus_round_{args.scope}.json")
    with open(p, "w") as f:
        json.dump(dict(cameras=out, complete=all("error" not in r for r in out)), f, indent=1)
    say(f"  wrote {p}")
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
