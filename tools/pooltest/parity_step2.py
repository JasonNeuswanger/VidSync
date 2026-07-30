#!/usr/bin/env python3
"""Step 2 of the solver-parity audit: map parity and objective parity at APP13, no optimization.

Two independent implementations are compared at exactly the same parameter vector:

  PRODUCTION-EQUIVALENT   plumb_oracle.cpp, whose undistortPoint,
                          orthogonalRegressionLineCostFunction, orthogonalRegressionTotalCostFunction,
                          undistortionJacobian and reasonToRejectSolvedDistortion are transcribed
                          verbatim from VSCalibration.mm, driven by the same GSL nmsimplex2.

  OFFLINE                 fitter.Plumblines.residuals (the vectorized reduceat form) and
                          nodes.undistort13 at eta = 0, i.e. the evaluator every earlier fisheye
                          conclusion was computed with.

Map parity is checked on every plumbline point, every front and back calibration node, every
conventional and point-cloud measurement click, and a dense full-frame grid. Objective parity is
checked on total SSE, per-point RMS, per-line SSE, and individual point residuals.

Read-only. Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import importlib.util
import math
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(HERE, "plumb_oracle")
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
FRAME_W, FRAME_H = 1920.0, 1080.0
CLIPS = ["Left Camera", "Right Camera"]


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


F = L("fitter")
nd = L("nodes")
kl = L("knownlength")


# --------------------------------------------------------------------------- data


def load_app13(vsd):
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    out = {}
    for row in db.execute(
            "SELECT v.ZCLIPNAME, c.Z_PK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
            "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
            "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
            "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4, "
            "c.ZDISTORTIONREMAININGPERPOINT FROM ZVSCALIBRATION c "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
        out[row[0]] = {"pk": row[1], "theta": np.array(row[2:15], float), "perpoint": row[15]}
    db.close()
    return out


def load_lines(vsd, clip):
    """Plumblines exactly as production assembles them: every line of the calibration, points
    ordered by index, no timecode filter, lines of any length retained (production keeps them and
    they contribute zero cost)."""
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    pk = db.execute("SELECT c.Z_PK FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v "
                    "ON v.Z_PK = c.ZVIDEOCLIP WHERE v.ZCLIPNAME = ?", (clip,)).fetchone()[0]
    byline, tc_of = defaultdict(list), {}
    for tc, ln, x, y, idx in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY, p.ZINDEX1 "
            "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK "
            "WHERE l.ZCALIBRATION = ? ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
        if x is not None:
            byline[ln].append((x, y))
            tc_of[ln] = tc
    db.close()
    keys = sorted(byline, key=lambda k: (tc_of[k], k))
    return [byline[k] for k in keys], [tc_of[k] for k in keys], pk


def run_oracle(mode, theta, lines, query=(), use_prod_start=0, maxiter=10000, sizetol=1e-10,
               eta=None, freemask=None):
    """Drive plumb_oracle. `eta` and `freemask` are the optional trailing fields added for the
    model-stability round; leaving them None reproduces the pre-extension protocol exactly, which
    the replay regression check relies on."""
    buf = [mode, " ".join(repr(float(v)) for v in theta), str(int(use_prod_start)),
           f"{FRAME_W!r} {FRAME_H!r}", f"{maxiter} {sizetol!r}", str(len(lines))]
    for Lg in lines:
        buf.append(str(len(Lg)))
        buf.extend(f"{float(x)!r} {float(y)!r}" for x, y in Lg)
    buf.append(str(len(query)))
    buf.extend(f"{float(x)!r} {float(y)!r}" for x, y in query)
    if eta is not None or freemask is not None:
        fm = [1] * 13 + [0] if freemask is None else [int(v) for v in freemask]
        assert len(fm) == 14, "freemask must have 14 entries"
        buf.append(repr(float(eta or 0.0)))
        buf.append(" ".join(str(v) for v in fm))
    r = subprocess.run([ORACLE], input="\n".join(buf) + "\n", capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"plumb_oracle failed: {r.stderr[:400]}")
    out = {"LINE": [], "RESID": [], "MAP": []}
    for ln in r.stdout.splitlines():
        t = ln.split()
        if t[0] == "LINE":
            out["LINE"].append((int(t[1]), int(t[2]), float(t[3]), float(t[4]),
                                float(t[5]), float(t[6])))
        elif t[0] == "RESID":
            out["RESID"].append((int(t[1]), int(t[2]), float(t[3]), float(t[4]), float(t[5])))
        elif t[0] == "MAP":
            out["MAP"].append((int(t[1]), float(t[2]), float(t[3])))
        elif t[0] == "GATE":
            body = ln.split("|")
            out["GATE"] = {"ok": t[1] == "1", "min_det_box": float(t[2]),
                           "scale_ratio": float(t[3]), "min_det_frame": float(t[4]),
                           "reason": body[1], "warning": body[2]}
        elif t[0] == "BOX":
            out["BOX"] = tuple(float(v) for v in t[1:5])
        elif t[0] == "SOLVED":
            out["SOLVED"] = np.array([float(v) for v in t[1:14]])
        else:
            out[t[0]] = float(t[1]) if "." in t[1] or "e" in t[1].lower() else int(t[1])
    return out


# --------------------------------------------------------------------------- reporting helpers


def cmp_stats(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    d = a - b
    return {"max": float(np.abs(d).max()), "rms": float(np.sqrt((d * d).mean())),
            "n": int(d.size)}


def point_cmp(A, B):
    A = np.asarray(A, float); B = np.asarray(B, float)
    e = np.hypot(*(A - B).T)
    return {"max": float(e.max()), "rms": float(np.sqrt((e * e).mean())),
            "median": float(np.median(e)), "n": int(len(e))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsd", default=FISHEYE)
    args = ap.parse_args()
    say = print

    say("=" * 100)
    say("STEP 2  MAP PARITY AND OBJECTIVE PARITY AT APP13, WITH NO OPTIMIZATION")
    say("=" * 100)
    say("  production-equivalent = plumb_oracle.cpp, functions transcribed verbatim from")
    say("  VSCalibration.mm (lines 37, 76, 219, 228, 2243) and driven by the same GSL nmsimplex2.")
    say("  offline = fitter.Plumblines.residuals and nodes.undistort13 at eta = 0.")

    app = load_app13(args.vsd)
    ann = kl.load(args.vsd, CLIPS)

    # measurement clicks per clip
    clicks = defaultdict(list)
    for pk, d in ann["clicks"].items():
        for cl, xy in d.items():
            clicks[cl].append(xy)

    db = sqlite3.connect(f"file:{args.vsd}?mode=ro", uri=True)

    verdict = {"map": True, "objective": True}
    for clip in CLIPS:
        theta = app[clip]["theta"]
        pk = app[clip]["pk"]
        lines, tcs, _ = load_lines(args.vsd, clip)
        pl = F.Plumblines(lines)

        say(f"\n{'-' * 100}")
        say(f"  {clip}   APP13, {pl.nlines} lines, {pl.n} points, "
            f"{len(set(tcs))} timecode(s)")
        say(f"{'-' * 100}")

        # ---------------------------------------------------------------- 2a map parity
        front = nd.front_calibration_nodes(db, pk)
        back = nd.back_calibration_nodes(db, pk)
        gx, gy = np.meshgrid(np.linspace(0.0, FRAME_W, 61), np.linspace(0.0, FRAME_H, 61))
        grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
        sets = [("plumbline points", pl.xy),
                ("front calibration nodes", np.array([[p[0], p[1]] for p in front], float)),
                ("back calibration nodes", np.array([[p[0], p[1]] for p in back], float)),
                ("measurement clicks", np.array(clicks[clip], float)),
                ("full-frame 61x61 grid", grid)]
        say(f"\n    MAP PARITY  undistortPoint (production) vs the offline map, at APP13")
        for label, pts in sets:
            if len(pts) == 0:
                say(f"      {label:26} no points")
                continue
            o = run_oracle("map", theta, lines, query=[tuple(p) for p in pts])
            P = np.array([[m[1], m[2]] for m in sorted(o["MAP"])], float)
            Q = F.undistort(pts, theta, 0.0)
            Q2 = np.array([nd.undistort13(x, y, list(theta)) for x, y in pts], float)
            s1 = point_cmp(P, Q)
            s2 = point_cmp(P, Q2)
            say(f"      {label:26} n {s1['n']:5d}   fitter.undistort max {s1['max']:.3e} px "
                f"rms {s1['rms']:.3e}   nodes.undistort13 max {s2['max']:.3e} px")
            if max(s1["max"], s2["max"]) > 1e-9:
                verdict["map"] = False

        # ---------------------------------------------------------------- 2b objective parity
        o = run_oracle("eval", theta, lines)
        say(f"\n    OBJECTIVE PARITY  total")
        prod_sse = o["SSE"]
        off_r = pl.residuals(theta)
        off_sse = float(off_r @ off_r)
        ncost = o["NCOSTPOINTS"]
        say(f"      production-equivalent SSE {prod_sse:.12f} px^2 over {ncost} cost-bearing points")
        say(f"      offline               SSE {off_sse:.12f} px^2 over {pl.n} points")
        say(f"      difference {prod_sse - off_sse:+.6e} px^2 "
            f"({abs(prod_sse - off_sse) / max(prod_sse, 1e-30):.3e} relative)")
        prms = math.sqrt(prod_sse / ncost)
        orms = math.sqrt(off_sse / pl.n)
        say(f"      production-equivalent RMS {prms:.12f} px;  offline RMS {orms:.12f} px;  "
            f"difference {prms - orms:+.3e}")
        say(f"      document's stored distortionRemainingPerPoint "
            f"{app[clip]['perpoint']:.12f} px  (difference from production-equivalent "
            f"{prms - app[clip]['perpoint']:+.3e} px)")
        say(f"      internal SSE cross-check inside the oracle "
            f"{o['SSECHECK'] - prod_sse:+.3e} px^2")

        # per-line
        plsse = np.array([x[2] for x in sorted(o["LINE"])], float)
        offl = np.array([float(off_r[s:s + c] @ off_r[s:s + c])
                         for s, c in zip(pl.starts, pl.counts)], float)
        st = cmp_stats(plsse, offl)
        worst = int(np.argmax(np.abs(plsse - offl)))
        say(f"\n    OBJECTIVE PARITY  per line ({len(plsse)} lines)")
        say(f"      max |difference| {st['max']:.3e} px^2, rms {st['rms']:.3e}; worst line index "
            f"{worst} (timecode {tcs[worst]}, {pl.counts[worst]} points, production "
            f"{plsse[worst]:.9f} vs offline {offl[worst]:.9f})")
        rel = np.abs(plsse - offl) / np.maximum(plsse, 1e-30)
        say(f"      max relative per-line difference {rel.max():.3e}")

        # per point
        R = np.zeros(pl.n)
        for _, _, r, _, _ in []:
            pass
        idx = {}
        for i, (s, c) in enumerate(zip(pl.starts, pl.counts)):
            idx[i] = (s, c)
        prod_r = np.zeros(pl.n)
        for li, pj, r, _, _ in o["RESID"]:
            s, c = idx[li]
            prod_r[s + pj] = r
        # sign of a TLS residual is arbitrary per line only through theta's branch; both
        # implementations use the same 0.5*atan2 branch, so compare signed values directly
        ps = cmp_stats(prod_r, off_r)
        say(f"\n    OBJECTIVE PARITY  per point ({pl.n} points)")
        say(f"      max |difference| {ps['max']:.3e} px, rms {ps['rms']:.3e}")
        k = int(np.argmax(np.abs(prod_r - off_r)))
        which = int(np.searchsorted(pl.starts, k, side="right") - 1)
        say(f"      worst point: flat index {k}, line {which} (timecode {tcs[which]}), "
            f"production {prod_r[k]:+.12f} vs offline {off_r[k]:+.12f}")
        say(f"      residual magnitudes: production rms {math.sqrt(float(prod_r @ prod_r) / pl.n):.9f} px, "
            f"offline rms {orms:.9f} px")
        if ps["max"] > 1e-9 or abs(prod_sse - off_sse) / max(prod_sse, 1e-30) > 1e-12:
            verdict["objective"] = False

        # ---------------------------------------------------------------- gate at APP13
        g = o["GATE"]
        say(f"\n    PRODUCTION GATE AT APP13 (oracle, over the plumbline bounding box)")
        say(f"      box {tuple(round(v, 3) for v in o['BOX'])}")
        say(f"      accepted {g['ok']}; min Jacobian determinant in box {g['min_det_box']:+.6f}; "
            f"radial scale ratio {g['scale_ratio']:.6f}")
        say(f"      whole-frame min determinant {g['min_det_frame']:+.6f}; warning "
            f"{g['warning'] if g['warning'] else 'none'}")
        gr = F.gate_report(theta, pl, 0.0, (FRAME_W, FRAME_H))
        say(f"      offline gate_report: ok {gr['ok']}, min det box {gr['min_det_box']:+.6f}, "
            f"radial scale ratio {gr['radial_scale_ratio']:.6f}, min det frame "
            f"{gr['min_det_frame']:+.6f}")
        say(f"      gate agreement: min det {abs(gr['min_det_box'] - g['min_det_box']):.3e}, "
            f"scale ratio {abs(gr['radial_scale_ratio'] - g['scale_ratio']):.3e}")

    db.close()
    say(f"\n{'=' * 100}")
    say(f"  VERDICT  map parity {'PASS' if verdict['map'] else 'FAIL'};  "
        f"objective parity {'PASS' if verdict['objective'] else 'FAIL'}")
    say(f"{'=' * 100}")
    return 0 if all(verdict.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
