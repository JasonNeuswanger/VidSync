#!/usr/bin/env python3
"""Regression checks for the corrected production-equivalent gate in fitter.py.

The reference implementation being matched is `reasonToRejectSolvedDistortion:overPlumblineBox:`
at VidSync/Model Classes/VSCalibration.mm:2243, which is transcribed independently below so the
two are not sharing an error. Includes synthetic collapse and expansion cases that must fail the
radial-scale bracket, which the old (area-spread) quantity would have judged differently.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


F = L("fitter")
S = L("suite4")

FAILS, CHECKS = [], [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(f"{name}: {detail}")
    print(f"  [{'ok ' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


# ---------------------------------------------------------------- reference transcription
def ref_undistort_scalar(x, y, t):
    """Independent transcription of undistortPoint(), VSCalibration.mm:219."""
    xd, yd = x - t[0], y - t[1]
    rs = xd * xd + yd * yd
    rad = 1.0
    for i in range(7):
        rad += t[2 + i] * rs ** (i + 1)
    dec = 1.0 + t[11] * rs + t[12] * rs * rs
    xu = t[0] + xd * rad + (t[9] * (rs + 2 * xd * xd) + 2 * t[10] * xd * yd) * dec
    yu = t[1] + yd * rad + (2 * t[9] * xd * yd + t[10] * (rs + 2 * yd * yd)) * dec
    return xu, yu


def ref_jac_det_scalar(xd, yd, t):
    """Independent transcription of undistortionJacobian(), VSCalibration.mm:228."""
    k = t[2:9]; p1, p2, p3, p4 = t[9], t[10], t[11], t[12]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k[i] * s ** (i + 1) for i in range(7))
    Rp = sum((i + 1) * k[i] * s ** i for i in range(7))
    T = 1 + p3 * s + p4 * s * s
    Tp = p3 + 2 * p4 * s
    Gx = p1 * (3 * xd * xd + yd * yd) + 2 * p2 * xd * yd
    Gy = 2 * p1 * xd * yd + p2 * (xd * xd + 3 * yd * yd)
    a = R + 2 * xd * xd * Rp + (6 * p1 * xd + 2 * p2 * yd) * T + 2 * xd * Gx * Tp
    b = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * yd * Gx * Tp
    c = 2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * xd * Gy * Tp
    d = R + 2 * yd * yd * Rp + (2 * p1 * xd + 6 * p2 * yd) * T + 2 * yd * Gy * Tp
    return a * d - b * c


def ref_gate(theta, xy, steps=24):
    """Independent transcription of reasonToRejectSolvedDistortion:, VSCalibration.mm:2243-2283."""
    if not all(math.isfinite(v) for v in theta):
        return False, None, None, "non-finite parameter"
    x0, y0 = theta[0], theta[1]
    lo = xy.min(axis=0); hi = xy.max(axis=0)
    mind = math.inf
    tot_u = 0.0
    tot_d = 0.0
    for i in range(steps + 1):
        for j in range(steps + 1):
            gx = lo[0] + (hi[0] - lo[0]) * (i / steps)
            gy = lo[1] + (hi[1] - lo[1]) * (j / steps)
            det = ref_jac_det_scalar(gx - x0, gy - y0, theta)
            if not math.isfinite(det):
                return False, None, None, "non-finite determinant"
            mind = min(mind, det)
            ux, uy = ref_undistort_scalar(gx, gy, theta)
            tot_u += math.hypot(ux - x0, uy - y0)
            tot_d += math.hypot(gx - x0, gy - y0)
    if mind <= 0.0:
        return False, mind, None, "fold-over in box"
    r = tot_u / tot_d if tot_d > 0 else float("nan")
    if r < 0.25 or r > 4.0:
        return False, mind, r, "scale ratio out of bracket"
    return True, mind, r, None


class PL:
    def __init__(self, xy):
        self.xy = np.asarray(xy, float)
        self.sref = 0.0


def main():
    print("REGRESSION: corrected production gate in fitter.py")
    print()
    ALL = {r["tag"]: r for r in np.load("/tmp/round5.npy", allow_pickle=True)}
    PATH = {l: p for l, p in S.SUITE}

    print("1. Real stored and refitted calibrations, offline gate vs independent transcription")
    for tag in sorted(ALL):
        lens, cn = tag.split(" / ")
        clip = S.Clip(PATH[lens], cn)
        pl = PL(clip.xy)
        for key in ("M0_2p", "M1_2p"):
            v = np.array(ALL[tag][key]["v"])
            c, k, p, e = S.nphys(v)
            # eta is not part of the production 13-vector; this compares the isotropic core, and
            # for M1 that means the gate is being evaluated on the map production would store.
            th = np.array([c[0], c[1], *k, *p])
            ok, mind, r = F.gate(th, pl)
            rok, rmind, rr, why = ref_gate(th, clip.xy)
            agree_ok = (ok == rok)
            dmind = abs(mind - rmind) / max(abs(rmind), 1e-30)
            dr = abs(r - rr) / max(abs(rr), 1e-30)
            check(f"{tag} {key}", agree_ok and dmind < 1e-10 and dr < 1e-10,
                  f"R_scale {r:.6f} vs ref {rr:.6f}, min det {mind:.6f}, "
                  f"{'PASS' if ok else 'REJECT'}")

    print()
    print("2. Synthetic collapse and expansion: must fail the radial-scale bracket")
    xy = np.stack(np.meshgrid(np.linspace(400, 1500, 12),
                              np.linspace(250, 850, 12)), axis=-1).reshape(-1, 2)
    pl = PL(xy)
    # A pure uniform rescaling about the centre is exactly the degeneracy the bracket targets:
    # k1..k7 = 0 gives ratio 1; a large negative k1 collapses, a large positive k1 expands.
    for label, k1, expect_ok in (("collapse, k1 = -1.6e-6", -1.6e-6, False),
                                 ("expansion, k1 = +1.0e-5 (ratio 2.84, legitimately inside)",
                                  1.0e-5, True),
                                 ("expansion, k1 = +3.0e-5 (breaches the 4.0 bound)", 3.0e-5,
                                  False),
                                 ("mild, k1 = -1.0e-7", -1.0e-7, True)):
        th = np.zeros(13); th[0], th[1] = 960.0, 540.0; th[2] = k1
        ok, mind, r = F.gate(th, pl)
        rok, rmind, rr, why = ref_gate(th, xy)
        spread = F.area_scale_spread(th, F.box_grid(pl))
        check(f"{label}", ok == expect_ok and ok == rok,
              f"R_scale {r:.4f}, min det {mind:+.4f}, area spread {spread:.3f}, "
              f"{'PASS' if ok else 'REJECT ' + str(why)}")

    print()
    print("3. The two quantities are genuinely different, so the old name was wrong")
    tag = "Rokinon 8 mm / Right Camera"
    lens, cn = tag.split(" / ")
    clip = S.Clip(PATH[lens], cn)
    pl = PL(clip.xy)
    v = np.array(ALL[tag]["M1_2p"]["v"])
    c, k, p, e = S.nphys(v)
    th = np.array([c[0], c[1], *k, *p])
    r = F.radial_scale_ratio(th, F.box_grid(pl))
    sp = F.area_scale_spread(th, F.box_grid(pl))
    check("fisheye: production ratio inside bracket while area spread exceeds 4",
          r < 4.0 and sp > 4.0,
          f"radial_scale_ratio {r:.4f} (PASS), area_scale_spread {sp:.4f} "
          f"(would have been called a failure)")

    print()
    print("4. Unthresholded diagnostics are present and finite")
    d = F.gate_report(th, pl, frame=(1920.0, 1080.0))
    for key in ("min_det_box", "max_det_box", "radial_scale_ratio", "area_scale_spread",
                "jac_condition", "roundtrip_px", "min_det_frame", "radial_scale_ratio_frame"):
        check(f"diagnostic {key}", key in d and d[key] is not None and np.isfinite(d[key]),
              f"{d.get(key)}")
    check("whole-frame determinant is a warning, never a rejection",
          d["ok"] is True or d["reason"] != "frame",
          f"frame_warning {d['frame_warning']}, min_det_frame {d['min_det_frame']:.4f}, "
          f"ok {d['ok']}")

    print()
    print(f"{CHECKS[0] - len(FAILS)}/{CHECKS[0]} checks passed")
    for f in FAILS:
        print(f"  FAILED: {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
