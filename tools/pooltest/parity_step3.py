#!/usr/bin/env python3
"""Step 3 of the solver-parity audit: replay, restart, and controlled multistart on the full 13.

Everything here optimizes the objective verified in Step 2 -- the plain sum of squared
orthogonal-regression residuals over every plumbline of the calibration, with no weighting, no
normalization, and NO penalty term. That is what production minimizes; production applies its
acceptance gate afterwards as an accept/reject on the finished solution, so the gate is reported at
every endpoint but never shapes the search. Parameters are carried in production's own scaled units
(VSCalibration.h SCALE_FACTOR_*), so the search space is production's search space.

  A  application replay      plumb_oracle nmsimplex2 from production's own start, step sizes,
                             tolerance and iteration cap. Does it reach APP13?
  B  stored-solution restart the same production-equivalent solver started AT APP13, and a robust
                             trust-region + Nelder-Mead solver started at APP13.
  C  controlled multistart   APP13, the production start, the gated offline full-13 route, scaled
                             perturbations of APP13, and the best lower-order solution embedded with
                             omitted terms exactly zero.

Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import json
import math
import os
import sqlite3
import subprocess
import sys

import numpy as np
from scipy.optimize import least_squares, minimize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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
SCALE = F.SCALE
PNAMES = F.NAMES

# The lower-order model in production's own parameterization: centre, k1..k4, p1, p2 free, the rest
# held at exactly zero. This is M0 expressed inside the 13-parameter vector.
M0_FREE = [0, 1, 2, 3, 4, 5, 9, 10]
FULL13 = list(range(13))


# --------------------------------------------------------------------------- objective


class Obj:
    """The verified production objective, in production's scaled parameter units."""

    def __init__(self, pl):
        self.pl = pl
        self.nev = 0

    def theta(self, x):
        return np.asarray(x, float) * SCALE

    def resid(self, x):
        self.nev += 1
        return self.pl.residuals(self.theta(x))

    def sse(self, x):
        r = self.resid(x)
        return float(r @ r)

    def grad(self, x, h=1e-7):
        """Central-difference gradient of SSE in scaled units, and its relative size."""
        g = np.zeros(len(x))
        for j in range(len(x)):
            a = np.array(x, float); a[j] += h
            b = np.array(x, float); b[j] -= h
            g[j] = (self.sse(a) - self.sse(b)) / (2 * h)
        return g

    def jac(self, x, free, h=1e-7):
        J = []
        for j in free:
            a = np.array(x, float); a[j] += h
            b = np.array(x, float); b[j] -= h
            J.append((self.resid(a) - self.resid(b)) / (2 * h))
        return np.array(J).T


def robust_solve(obj, x0, free, label, rounds=6, require_held_zero=True):
    """Trust-region least squares on the residual vector, alternated with Nelder-Mead, repeated
    until neither can improve. No bounds and no penalty: this is the bare production objective.

    x_scale="jac" matters here. The residual Jacobian's condition number at these solutions is
    around 1e8, so a fixed unit scaling leaves the trust region badly shaped and the solver stalls
    early; that stall is easily mistaken for a distinct local basin.
    """
    x = np.asarray(x0, float).copy()
    free = np.asarray(free)
    held = [j for j in range(len(x)) if j not in set(free.tolist())]
    sse = obj.sse(x)
    status, opt, nfev, ls_rounds, nm_gain = -1, float("nan"), 0, 0, 0.0

    def rr(w, base):
        y = base.copy(); y[free] = w
        return obj.resid(y)

    def f(w, base):
        y = base.copy(); y[free] = w
        return obj.sse(y)

    for _ in range(rounds):
        improved = False
        r = least_squares(rr, x[free], args=(x,), method="trf", x_scale="jac",
                          ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=60000)
        cand = x.copy(); cand[free] = r.x
        c = obj.sse(cand)
        nfev += int(r.nfev); ls_rounds += 1
        status, opt = int(r.status), float(r.optimality)
        if c < sse - 1e-12 * max(sse, 1.0):
            x, sse, improved = cand, c, True
        nm = minimize(f, x[free], args=(x,), method="Nelder-Mead",
                      options={"maxiter": 40000, "maxfev": 40000, "xatol": 1e-12,
                               "fatol": 1e-14, "adaptive": True})
        if nm.fun < sse - 1e-12 * max(sse, 1.0):
            cand = x.copy(); cand[free] = nm.x
            nm_gain += sse - float(nm.fun)
            x, sse, improved = cand, float(nm.fun), True
        if not improved:
            break
    # Held parameters must not move. Normally they are held at exactly zero, which is what a reduced
    # model means; require_held_zero=False allows holding one at a fixed NONZERO value, which is what
    # a profile likelihood over eta needs. Either way the values must be unchanged from the seed.
    if held:
        assert np.all(x[held] == np.asarray(x0, float)[held]), "held parameter drifted"
        if require_held_zero:
            assert np.all(x[held] == 0.0), "held parameter is not zero"
    return {"label": label, "x": x, "sse": sse, "ls_status": status, "optimality": opt,
            "nfev": nfev, "rounds": ls_rounds, "nm_gain": nm_gain}


# --------------------------------------------------------------------------- displacement


def displacements(theta_a, theta_b, supports):
    out = {}
    for name, pts in supports.items():
        A = F.undistort(pts, theta_a, 0.0)
        B = F.undistort(pts, theta_b, 0.0)
        e = np.hypot(*(A - B).T)
        out[name] = (float(e.max()), float(np.median(e)),
                     float(np.sqrt((e * e).mean())))
    return out


def report_endpoint(say, obj, pl, res, theta_app, supports, frame=(FRAME_W, FRAME_H)):
    th = obj.theta(res["x"])
    rms = math.sqrt(res["sse"] / pl.n)
    gr = F.gate_report(th, pl, 0.0, frame)
    g = obj.grad(res["x"])
    d = displacements(theta_app, th, supports)
    say(f"      {res['label']:34} SSE {res['sse']:12.6f}  RMS {rms:9.6f} px  "
        f"status {res['ls_status']:>4}  |grad| {np.linalg.norm(g):.3e}  opt {res['optimality']:.2e}")
    say(f"        gate {'ok  ' if gr['ok'] else 'FAIL'}  R_scale {gr['radial_scale_ratio']:.6f}  "
        f"minDet box {gr['min_det_box']:+.6f}  frame {gr['min_det_frame']:+.6f}  "
        f"warn {'yes' if gr['frame_warning'] else 'no'}")
    say(f"        map displacement vs APP13 (max/median/rms px): " +
        "  ".join(f"{k} {v[0]:.3f}/{v[1]:.3f}/{v[2]:.3f}" for k, v in d.items()))
    return {"label": res["label"], "theta": th.tolist(), "sse": res["sse"], "rms": rms,
            "gate_ok": bool(gr["ok"]), "R_scale": gr["radial_scale_ratio"],
            "min_det_box": gr["min_det_box"], "min_det_frame": gr["min_det_frame"],
            "grad_norm": float(np.linalg.norm(g)), "displacement": d,
            "ls_status": res["ls_status"], "x_scaled": res["x"].tolist()}


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    ap.add_argument("--out", default=os.path.join(HERE, "analysis-output", "parity_step3.json"))
    args = ap.parse_args()
    say = print

    say("=" * 100)
    say("STEP 3  REPLAY AND POLISH THE FULL 13-PARAMETER SOLVE")
    say("=" * 100)
    say("  objective: the Step-2-verified production objective, unpenalized, in production's")
    say("  scaled units. The gate is evaluated at every endpoint but never shapes the search,")
    say("  exactly as in calculateDistortionCorrection.")

    app = P2.load_app13(args.vsd)
    ann = kl.load(args.vsd, CLIPS)
    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)
    results = {}

    for clip in CLIPS:
        theta_app = app[clip]["theta"]
        pk = app[clip]["pk"]
        lines, tcs, _ = P2.load_lines(args.vsd, clip)
        pl = F.Plumblines(lines)
        obj = Obj(pl)
        x_app = theta_app / SCALE
        sse_app = obj.sse(x_app)

        front = np.array([[p[0], p[1]] for p in nd.front_calibration_nodes(db, pk)], float)
        back = np.array([[p[0], p[1]] for p in nd.back_calibration_nodes(db, pk)], float)
        clicks = np.array([xy for d in ann["clicks"].values() for cl, xy in d.items()
                           if cl == clip], float)
        gx, gy = np.meshgrid(np.linspace(0.0, FRAME_W, 61), np.linspace(0.0, FRAME_H, 61))
        supports = {"plumb": pl.xy, "nodes": np.vstack([front, back]),
                    "clicks": clicks, "frame": np.stack([gx.ravel(), gy.ravel()], axis=1)}

        say(f"\n{'=' * 100}")
        say(f"  {clip}   {pl.nlines} lines, {pl.n} points, {len(set(tcs))} timecode(s)")
        say(f"  APP13 objective SSE {sse_app:.6f} px^2, RMS {math.sqrt(sse_app / pl.n):.6f} px")
        say(f"{'=' * 100}")

        # ------------------------------------------------------------------ A. replay
        say(f"\n    A. APPLICATION REPLAY  gsl nmsimplex2, start (w/2, h/2, 0...0), step sizes")
        say(f"       (0.001, 0.001, 25 x 11), stop at simplex size < 1e-10, cap 10000 iterations")
        rep = P2.run_oracle("solve", np.zeros(13), lines, use_prod_start=1)
        th_rep = rep["SOLVED"]
        grp = F.gate_report(th_rep, pl, 0.0, (FRAME_W, FRAME_H))
        say(f"       iterations {rep['ITERS']}, terminal simplex size {rep['SIMPLEXSIZE']:.3e}, "
            f"gsl status {rep['STATUS']} "
            f"({'converged on size' if rep['STATUS'] == 0 else 'hit the iteration cap'})")
        say(f"       initial SSE {rep['INITIALSSE']:.6f} -> final SSE {rep['FINALSSE']:.6f}")
        say(f"       replay per-point residual {rep['REMAININGPERPOINT']:.12f} px")
        say(f"       APP13  per-point residual {app[clip]['perpoint']:.12f} px  "
            f"(difference {rep['REMAININGPERPOINT'] - app[clip]['perpoint']:+.3e} px)")
        say(f"       replay reduction {rep['REDUCTION']:.12f}")
        rel = np.abs(th_rep - theta_app) / np.maximum(np.abs(theta_app), 1e-300)
        say(f"       coefficient agreement with APP13: max relative {rel.max():.3e} "
            f"(worst {PNAMES[int(np.argmax(rel))]}), max scaled-unit "
            f"{np.abs((th_rep - theta_app) / SCALE).max():.3e}")
        drep = displacements(theta_app, th_rep, supports)
        say(f"       map displacement replay vs APP13 (max/median/rms px): " +
            "  ".join(f"{k} {v[0]:.3e}/{v[1]:.3e}/{v[2]:.3e}" for k, v in drep.items()))
        say(f"       replay gate: ok {grp['ok']}, R_scale {grp['radial_scale_ratio']:.6f}")
        replay_ok = bool(max(v[0] for v in drep.values()) < 1e-3)
        say(f"       REPLAY REPRODUCES APP13 TO BETTER THAN 1e-3 px ANYWHERE IN FRAME: {replay_ok}")

        # How much of any replay/APP13 gap is the solver's own sensitivity rather than a real
        # difference of solution? Nelder-Mead on a nearly flat landscape is chaotic: perturb the
        # start by an amount far below any physically meaningful quantity and see where it lands.
        say(f"\n       replay sensitivity: the same production-equivalent solve from starts nudged")
        say(f"       by a relative epsilon in the centre only, all other coefficients still zero")
        sens = []
        for eps in (1e-12, 1e-9, 1e-6):
            for sgn in (+1, -1):
                st = np.zeros(13)
                st[0] = (FRAME_W / 2.0) * (1.0 + sgn * eps)
                st[1] = (FRAME_H / 2.0) * (1.0 - sgn * eps)
                rs = P2.run_oracle("solve", st, lines, use_prod_start=0)
                dd = displacements(th_rep, rs["SOLVED"], supports)
                sens.append((eps, sgn, rs["FINALSSE"], rs["ITERS"], dd["frame"][0],
                             dd["plumb"][0]))
        for eps, sgn, s, it, dfr, dpl in sens:
            say(f"         start epsilon {sgn * eps:+.0e}: SSE {s:12.6f} ({it:5d} iters), "
                f"map vs replay max {dpl:8.4f} px on plumblines, {dfr:9.4f} px over the frame")
        ssev = np.array([s for _, _, s, _, _, _ in sens] + [rep["FINALSSE"]])
        mapv = np.array([d for _, _, _, _, d, _ in sens])
        say(f"         SSE spread over these {len(ssev)} nominally identical solves "
            f"{ssev.min():.6f} to {ssev.max():.6f} (range {ssev.max() - ssev.min():.6f} px^2)")
        say(f"         map spread up to {mapv.max():.4f} px over the frame")
        say(f"         APP13 sits at SSE {sse_app:.6f}; that is "
            f"{'INSIDE' if ssev.min() - 1e-9 <= sse_app <= ssev.max() + 1e-9 else 'OUTSIDE'} "
            f"the spread this solver produces from indistinguishable starts")

        # ------------------------------------------------------------------ B. restart
        say(f"\n    B. STORED-SOLUTION RESTART  is APP13 stationary?")
        rst = P2.run_oracle("solve", theta_app, lines, use_prod_start=0)
        th_rst = rst["SOLVED"]
        say(f"       production-equivalent nmsimplex2 restarted AT APP13:")
        say(f"         iterations {rst['ITERS']}, simplex size {rst['SIMPLEXSIZE']:.3e}, "
            f"status {rst['STATUS']}")
        say(f"         SSE {sse_app:.6f} -> {rst['FINALSSE']:.6f} "
            f"(change {rst['FINALSSE'] - sse_app:+.6f}, "
            f"{100 * (1 - rst['FINALSSE'] / sse_app):+.3f}%)")
        say(f"         per-point residual {rst['REMAININGPERPOINT']:.6f} px vs APP13 "
            f"{app[clip]['perpoint']:.6f} px")
        drst = displacements(theta_app, th_rst, supports)
        say(f"         map displacement vs APP13 (max/median/rms px): " +
            "  ".join(f"{k} {v[0]:.3f}/{v[1]:.3f}/{v[2]:.3f}" for k, v in drst.items()))
        gr_rst = F.gate_report(th_rst, pl, 0.0, (FRAME_W, FRAME_H))
        say(f"         gate ok {gr_rst['ok']}, R_scale {gr_rst['radial_scale_ratio']:.6f}, "
            f"minDet box {gr_rst['min_det_box']:+.6f}")

        g_app = obj.grad(x_app)
        J_app = obj.jac(x_app, FULL13)
        sv = np.linalg.svd(J_app, compute_uv=False)
        say(f"       stationarity diagnostics at APP13 (scaled units):")
        say(f"         |grad SSE| {np.linalg.norm(g_app):.6e}; largest component "
            f"{PNAMES[int(np.argmax(np.abs(g_app)))]} {np.abs(g_app).max():.4e}")
        say(f"         residual-Jacobian singular values {sv[0]:.4e} .. {sv[-1]:.4e}, "
            f"condition {sv[0] / sv[-1]:.4e}")
        # Gauss-Newton step length as a scale-free measure of how far from stationary APP13 is
        try:
            step = np.linalg.lstsq(J_app, -pl.residuals(theta_app), rcond=None)[0]
            say(f"         Gauss-Newton step norm from APP13 {np.linalg.norm(step):.4e} "
                f"in scaled units")
        except Exception:                                            # noqa: BLE001
            pass

        # ------------------------------------------------------------------ C. multistart
        say(f"\n    C. CONTROLLED MULTISTART on the full 13")
        seeds = []
        seeds.append(("APP13", x_app.copy()))
        xprod = np.zeros(13)
        xprod[0] = (FRAME_W / 2.0) / SCALE[0]; xprod[1] = (FRAME_H / 2.0) / SCALE[1]
        seeds.append(("production start", xprod))
        # the best lower-order solution, embedded with omitted terms exactly zero
        m0 = robust_solve(obj, xprod.copy(), M0_FREE, "M0 embedded (k1-k4,p1,p2)")
        assert np.all(m0["x"][[6, 7, 8, 11, 12]] == 0.0), "M0 seed has a nonzero held parameter"
        seeds.append(("M0 embedded", m0["x"].copy()))
        # the previous offline route: the gated fit the earlier fisheye conclusions used
        Z = L("round9a")
        S = Z.S
        gz = Z.G(pl.xy, pl.counts)
        v0 = np.zeros(15)
        v0[0] = (960.0 - S.W / 2) / S.R; v0[1] = (540.0 - S.H / 2) / S.R
        vstored = np.zeros(15)
        vstored[0] = (theta_app[0] - S.W / 2) / S.R
        vstored[1] = (theta_app[1] - S.H / 2) / S.R
        for j in range(7):
            vstored[2 + j] = theta_app[2 + j] * S.R ** (2 * (j + 1))
        vstored[9] = theta_app[9] * S.R; vstored[10] = theta_app[10] * S.R
        vstored[11] = theta_app[11] * S.R ** 2; vstored[12] = theta_app[12] * S.R ** 4
        vg = Z.best_fit(gz, FULL13, [v0.copy(), vstored.copy()])[0]
        cq, kq, pq, eq, _ = Z.nphys(vg)
        th_gated = np.array([cq[0], cq[1], *kq, *pq])
        seeds.append(("gated offline full-13", th_gated / SCALE))
        rr = np.random.default_rng(20260728)
        for i in range(4):
            s = x_app.copy()
            s = s + rr.normal(0.0, 0.05, 13) * np.maximum(np.abs(s), 1.0)
            seeds.append((f"APP13 perturbed {i + 1}", s))

        say(f"       {len(seeds)} seeds; each run is trust-region least squares on the bare")
        say(f"       objective followed by Nelder-Mead as an independent check")
        ends = []
        for name, s in seeds:
            res = robust_solve(obj, s, FULL13, name)
            ends.append(report_endpoint(say, obj, pl, res, theta_app, supports))
        m0end = report_endpoint(say, obj, pl, m0, theta_app, supports)

        best = min(ends, key=lambda e: e["sse"])
        say(f"\n       best endpoint: {best['label']}, SSE {best['sse']:.6f}, "
            f"RMS {best['rms']:.6f} px, gate ok {best['gate_ok']}")
        gated_ok = [e for e in ends if e["gate_ok"]]
        bestg = min(gated_ok, key=lambda e: e["sse"]) if gated_ok else None
        if bestg is not None:
            say(f"       best GATE-PASSING endpoint: {bestg['label']}, SSE {bestg['sse']:.6f}, "
                f"RMS {bestg['rms']:.6f} px")
        nsame = sum(1 for e in ends if abs(e["sse"] - best["sse"]) <= 1e-6 * max(best["sse"], 1.0))
        say(f"       {nsame}/{len(ends)} seeds land within 1e-6 relative of the best SSE")
        say(f"       spread of endpoint SSE: " +
            "  ".join(f"{e['sse']:.4f}" for e in sorted(ends, key=lambda z: z['sse'])))
        say(f"       APP13 SSE {sse_app:.6f} vs best {best['sse']:.6f}: "
            f"descent {sse_app - best['sse']:+.6f} px^2, "
            f"{100 * (1 - best['sse'] / sse_app):+.3f}% of APP13")
        say(f"       NESTING INVARIANT best full-13 SSE <= embedded M0 SSE: "
            f"{best['sse'] <= m0end['sse'] + 1e-9} "
            f"({best['sse']:.6f} vs {m0end['sse']:.6f})")

        results[clip] = {"app13": theta_app.tolist(), "app13_sse": sse_app,
                         "app13_rms": math.sqrt(sse_app / pl.n), "n": pl.n,
                         "nlines": pl.nlines, "timecodes": sorted(set(tcs)),
                         "replay": {"theta": th_rep.tolist(), "sse": rep["FINALSSE"],
                                    "iters": rep["ITERS"], "status": rep["STATUS"],
                                    "size": rep["SIMPLEXSIZE"],
                                    "perpoint": rep["REMAININGPERPOINT"],
                                    "reproduces_app13": replay_ok,
                                    "displacement": drep},
                         "restart_production": {"theta": th_rst.tolist(),
                                                "sse": rst["FINALSSE"],
                                                "iters": rst["ITERS"],
                                                "status": rst["STATUS"],
                                                "displacement": drst},
                         "grad_app13": float(np.linalg.norm(g_app)),
                         "jac_condition_app13": float(sv[0] / sv[-1]),
                         "endpoints": ends, "m0_embedded": m0end,
                         "best": best, "best_gated": bestg}

    db.close()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=1, default=float)
    say(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
