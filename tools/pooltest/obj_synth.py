#!/usr/bin/env python3
"""Synthetic validation of the four objectives. Cheap, deterministic, and run before any real fit.

Tests, in order:

  1  Recovery from a known central model with irregular missing lattice points.
  2  Recovery with a known nonzero eta.
  3  Invariance of SD, ED and PD to duplicated line-storage of the same unique observation.
  4  A separable nonprojective warp that keeps horizontal and vertical lines straight but curves
     diagonals: the row/column objectives must NOT see it, and PD or the diagonal holdout must.
  5  Two captures with different homographies but one shared distortion.
  6  A small capture-specific noncentral perturbation: the shared model must form one pooled
     compromise, not a per-capture correction.
  7  Forward/inverse round trips for M0 and M1 over the fitted domain, plus the analytic Jacobian
     against central differences.
  8  SD versus ED as noise amplitude grows, to locate the regime where Sampson is adequate rather
     than assuming it.

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
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LT = L("lattice")
OB = L("objectives")
SCALE14 = LT.SCALE14
CENTRE = OB.CENTRE
FAILS = []


def check(name, cond, detail=""):
    print(f"    [{'ok  ' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)
    return cond


# =============================================================== synthetic capture construction


def truth_theta(k1=-1.2e-7, k2=4.0e-14, eta=0.0, cx=955.0, cy=535.0):
    """A physically plausible barrel model in production's raw units."""
    th = np.zeros(14)
    th[0], th[1] = cx, cy
    th[2], th[3] = k1, k2
    th[9], th[10] = 3.0e-9, -2.0e-9
    th[13] = eta
    return th


class SynthCap(LT.Capture):
    """A Capture built from a synthetic lattice rather than from a document."""

    def __init__(self, xy, rows, cols, timecode="synthetic", rc=None, duplicate_lines=False):
        super().__init__("synthetic", timecode)
        self.xy = np.asarray(xy, float)
        self.lines = []
        self.inc = [[] for _ in range(len(self.xy))]
        for fam, groups in ((0, rows), (1, cols)):
            for g in groups:
                if len(g) < 2:
                    continue
                self.lines.append({"id": len(self.lines), "family": fam, "angle": 0.0,
                                   "members": list(g), "stored": len(g)})
        if duplicate_lines:
            for ln in list(self.lines):
                self.lines.append({"id": len(self.lines), "family": ln["family"], "angle": 0.0,
                                   "members": list(ln["members"]), "stored": ln["stored"]})
        for li, ln in enumerate(self.lines):
            for m in ln["members"]:
                self.inc[m].append(li)
        self.rc = np.array(rc, float) if rc is not None else np.full((len(self.xy), 2), np.nan)
        self.component = np.zeros(len(self.xy), int)
        d = []
        for i in range(len(self.xy)):
            nb = np.linalg.norm(self.xy - self.xy[i], axis=1)
            nb = nb[nb > 1e-9]
            d.append(np.median(np.sort(nb)[:4]) if len(nb) >= 4 else 100.0)
        self.local_scale = np.array(d, float)
        self.notes = {}


def make_lattice(th_true, nr=9, nc=12, pitch=110.0, H=None, drop_frac=0.22, seed=0,
                 noise=0.0, extra_warp=None, duplicate_lines=False, latmap=None):
    """Build a synthetic capture: an ideal lattice mapped by a homography into CORRECTED space, then
    pushed through U^-1 to raw space, with irregular missing corners and optional noise."""
    rng = np.random.default_rng(seed)
    rr, cc = np.meshgrid(np.arange(nr), np.arange(nc), indexing="ij")
    lat = np.stack([cc.ravel().astype(float), rr.ravel().astype(float)], axis=1)
    keep = rng.random(len(lat)) > drop_frac
    lat = lat[keep]
    rcs = np.stack([lat[:, 1], lat[:, 0]], axis=1)
    if latmap is not None:
        # Build corrected coordinates directly from the lattice indices. With a separable map
        # (f(c), g(r)) every row has constant y and every column constant x, so BOTH line families
        # are exactly straight while the map is projective only if f and g are affine.
        corr = latmap(lat)
    else:
        if H is None:
            H = np.array([[pitch, 0.06 * pitch, 380.0],
                          [-0.05 * pitch, pitch, 180.0],
                          [7e-5, -5e-5, 1.0]])
        w = H[2, 0] * lat[:, 0] + H[2, 1] * lat[:, 1] + H[2, 2]
        corr = np.stack([(H[0, 0] * lat[:, 0] + H[0, 1] * lat[:, 1] + H[0, 2]) / w,
                         (H[1, 0] * lat[:, 0] + H[1, 1] * lat[:, 1] + H[1, 2]) / w], axis=1)
    if extra_warp is not None:
        corr = extra_warp(corr)
    raw, conv, mx = LT.inv_U(corr, th_true)
    assert conv.all(), f"synthetic inverse failed, max residual {mx:.3g}"
    if noise > 0:
        raw = raw + rng.normal(0.0, noise, raw.shape)
    rows = [np.where(rcs[:, 0] == r)[0] for r in np.unique(rcs[:, 0])]
    cols = [np.where(rcs[:, 1] == c)[0] for c in np.unique(rcs[:, 1])]
    rows = [g for g in rows if len(g) >= 3]
    cols = [g for g in cols if len(g) >= 3]
    return SynthCap(raw, rows, cols, rc=rcs, duplicate_lines=duplicate_lines)


def fit_and_err(caps, objective, model, th_true, seed_th=None, pts=None):
    D = OB.Dataset(caps, require_indexed=True, kappa=3.0)
    base = OB.default_base() if seed_th is None else np.asarray(seed_th, float) / SCALE14
    r = OB.fit(D, objective, model, base=base)
    th = np.array(r["theta14"], float)
    P = D.xy if pts is None else pts
    e = np.linalg.norm(LT.U(P, th) - LT.U(P, th_true), axis=1)
    # the map is only determined up to the projective gauge the objective cannot see, so also report
    # the residual after removing a best-fit homography
    return r, float(np.median(e)), float(e.max()), th, D


def gauge_free_err(P, th_a, th_b):
    """Map difference after removing the projective gauge the line objectives cannot constrain."""
    G = L("stab_gauge")
    A = LT.U(P, th_a); B = LT.U(P, th_b)
    H = G.fit_homography(A, B)
    return float(np.median(np.linalg.norm(G.apply_H(H, A) - B, axis=1)))


# =============================================================== tests


def test_jacobian_and_roundtrip():
    print("\n[7] ANALYTIC JACOBIAN AND FORWARD/INVERSE ROUND TRIP")
    rng = np.random.default_rng(3)
    P = np.column_stack([rng.uniform(20, 1900, 400), rng.uniform(20, 1060, 400)])
    for lbl, th in (("M0", truth_theta()), ("M1 eta=+0.03", truth_theta(eta=0.03)),
                    ("M1 eta=-0.05", truth_theta(eta=-0.05))):
        J = LT.jac_U(P, th)
        h = 1e-3
        Jx = (LT.U(P + [h, 0], th) - LT.U(P - [h, 0], th)) / (2 * h)
        Jy = (LT.U(P + [0, h], th) - LT.U(P - [0, h], th)) / (2 * h)
        Jn = np.stack([np.stack([Jx[:, 0], Jy[:, 0]], -1), np.stack([Jx[:, 1], Jy[:, 1]], -1)], -2)
        err = float(np.abs(J - Jn).max())
        check(f"analytic Jacobian matches central differences, {lbl}", err < 5e-7,
              f"max |difference| {err:.2e}")
        back, conv, mx = LT.inv_U(LT.U(P, th), th)
        rt = float(np.abs(back - P).max())
        check(f"round trip U then U^-1, {lbl}", rt < 1e-9 and conv.all(),
              f"max {rt:.2e} px, forward residual {mx:.2e}, all converged {bool(conv.all())}")
        ad = LT.admissible(th, P)
        check(f"admissibility passes and map is injective on the domain, {lbl}",
              ad["ok"] and ad["min_det_full_box"] > 0,
              f"min det {ad['min_det_full_box']:.4f}, R_scale {ad['R_scale']:.4f}, "
              f"round trip {ad['roundtrip_box_px']:.2e} px")


def test_recovery():
    print("\n[1] RECOVERY FROM A KNOWN CENTRAL MODEL, IRREGULAR MISSING CORNERS")
    th = truth_theta()
    cap = make_lattice(th, seed=1)
    print(f"    synthetic capture: {cap.n} corners, {len(cap.lines)} lines, "
          f"{int((cap.n_constraints() >= 2).sum())} doubly constrained")
    for obj in ("SD", "ED", "PD"):
        r, med, mx, thf, D = fit_and_err([cap], obj, "M0", th)
        g = gauge_free_err(D.xy, thf, th)
        check(f"{obj} recovers the map (gauge-removed)", g < 0.01,
              f"raw median {med:.4f} px, max {mx:.4f} px, gauge-removed median {g:.2e} px, "
              f"loss {r['loss']:.3e}")

    print("\n[2] RECOVERY WITH A KNOWN NONZERO eta")
    the = truth_theta(eta=0.022)
    cape = make_lattice(the, seed=2)
    for obj in ("SD", "ED", "PD"):
        r, med, mx, thf, D = fit_and_err([cape], obj, "M1", the)
        g = gauge_free_err(D.xy, thf, the)
        check(f"{obj} recovers eta", abs(thf[13] - 0.022) < 2e-3,
              f"eta fitted {thf[13]:+.6f} against truth +0.022000, gauge-removed median {g:.2e} px")


def test_duplicate_invariance():
    print("\n[3] INVARIANCE TO DUPLICATED LINE STORAGE OF THE SAME UNIQUE OBSERVATION")
    th = truth_theta()
    a = make_lattice(th, seed=4, noise=0.25)
    b = make_lattice(th, seed=4, noise=0.25, duplicate_lines=True)
    check("duplicated storage yields the same unique observations",
          a.n == b.n and len(b.lines) == 2 * len(a.lines),
          f"{a.n} observations either way; lines {len(a.lines)} vs {len(b.lines)}")
    Da0, Db0 = OB.Dataset([a]), OB.Dataset([b])
    wb = OB.fit(Da0, "B", "M0", warm=False)
    x0 = np.array(wb["theta14"], float)[OB.MODELS["M0"]] / SCALE14[OB.MODELS["M0"]]
    for obj in ("SD", "ED", "PD"):
        Da, Db = OB.Dataset([a]), OB.Dataset([b])
        ra = OB.fit(Da, obj, "M0", x0_model=x0)
        rb = OB.fit(Db, obj, "M0", x0_model=x0)
        tha = np.array(ra["theta14"], float); thb = np.array(rb["theta14"], float)
        mp = float(np.median(np.linalg.norm(LT.U(Da.xy, tha) - LT.U(Da.xy, thb), axis=1)))
        # SD and ED weight per unique point, so duplication must not change the fit; PD never sees
        # lines at all
        check(f"{obj} is invariant to duplicated line storage", mp < 1e-6,
              f"median map difference {mp:.2e} px")
    # and the contrast: B is NOT invariant, by design, which is the historical behaviour
    Da, Db = OB.Dataset([a]), OB.Dataset([b])
    rba = OB.fit(Da, "B", "M0", warm=False); rbb = OB.fit(Db, "B", "M0", warm=False)
    mp = float(np.median(np.linalg.norm(LT.U(Da.xy, np.array(rba["theta14"]))
                                        - LT.U(Da.xy, np.array(rbb["theta14"])), axis=1)))
    print(f"    [note] B under duplicated storage moves the map by a median of {mp:.3e} px, "
          f"and its loss doubles ({rba['loss']:.3f} -> {rbb['loss']:.3f}); that per-incidence "
          f"counting is exactly what SD, ED and PD are meant to remove")


def test_nonprojective_warp():
    print("\n[4] A SEPARABLE NONPROJECTIVE WARP THAT PRESERVES ROWS AND COLUMNS EXACTLY")
    th = truth_theta()

    def make_latmap(alpha, beta, pitch=118.0):
        def f(lat):
            c = lat[:, 0] - lat[:, 0].mean()
            r = lat[:, 1] - lat[:, 1].mean()
            x = pitch * (c + alpha * c * c)
            y = pitch * (r + beta * r * r)
            return np.stack([x + 960.0, y + 540.0], axis=1)
        return f

    clean = make_lattice(th, seed=6, latmap=make_latmap(0.0, 0.0))
    warped = make_lattice(th, seed=6, latmap=make_latmap(0.035, -0.028))
    # verify the premise: in the warped truth, both line families are still exactly straight
    for lbl, cap in (("clean", clean), ("warped", warped)):
        u = LT.U(cap.xy, th)
        r = []
        for ln in cap.lines:
            P = u[ln["members"]]
            q = P - P.mean(axis=0)
            t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                                 float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            r.append(-q[:, 0] * math.sin(t) + q[:, 1] * math.cos(t))
        rr = np.concatenate(r)
        check(f"premise: row and column families are exactly straight in the {lbl} truth",
              float(np.abs(rr).max()) < 1e-8, f"max straightness residual {np.abs(rr).max():.2e} px")

    Dc, Dw = OB.Dataset([clean]), OB.Dataset([warped])
    for obj in ("SD", "ED"):
        rc_ = OB.fit(Dc, obj, "M0")
        rw = OB.fit(Dw, obj, "M0")
        check(f"{obj} cannot see the warp: loss stays at the clean level",
              rw["loss"] < 1e-6 and rc_["loss"] < 1e-6,
              f"clean loss {rc_['loss']:.3e}, warped loss {rw['loss']:.3e}")
    rpd_c = OB.fit(Dc, "PD", "M0")
    rpd_w = OB.fit(Dw, "PD", "M0")
    check("PD DOES see the warp: its loss rises by orders of magnitude",
          rpd_w["loss"] > 1e4 * max(rpd_c["loss"], 1e-24) and rpd_w["loss"] > 1.0,
          f"clean loss {rpd_c['loss']:.3e}, warped loss {rpd_w['loss']:.3e}")
    rw = OB.fit(Dw, "SD", "M0")
    resw = diagonal_residuals(warped, np.array(rw["theta14"], float),
                              LT.diagonal_families(warped))
    rc2 = OB.fit(Dc, "SD", "M0")
    resc = diagonal_residuals(clean, np.array(rc2["theta14"], float),
                              LT.diagonal_families(clean))
    check("the diagonal holdout also exposes the warp after an SD fit",
          resw["rms"] > 100.0 * max(resc["rms"], 1e-9) and resw["rms"] > 1.0,
          f"clean diagonal RMS {resc['rms']:.3e} px over {resc['n_families']} families, "
          f"warped {resw['rms']:.3f} px over {resw['n_families']}")


def diagonal_residuals(C, th14, fams):
    """Orthogonal straightness residual of each diagonal family in corrected space, in px."""
    u = LT.U(C.xy, th14)
    out, n = [], 0
    for f in fams:
        if not f["adequate"]:
            continue
        P = u[f["members"]]
        q = P - P.mean(axis=0)
        t = 0.5 * math.atan2(2.0 * float(q[:, 0] @ q[:, 1]),
                             float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        out.append(-q[:, 0] * math.sin(t) + q[:, 1] * math.cos(t))
        n += 1
    if not out:
        return {"rms": float("nan"), "n_families": 0, "n_points": 0}
    r = np.concatenate(out)
    return {"rms": float(np.sqrt((r ** 2).mean())), "n_families": n, "n_points": len(r),
            "max": float(np.abs(r).max())}


def test_two_captures():
    print("\n[5] TWO CAPTURES, DIFFERENT HOMOGRAPHIES, ONE SHARED DISTORTION")
    th = truth_theta()
    H1 = np.array([[110.0, 6.0, 300.0], [-5.0, 110.0, 150.0], [7e-5, -5e-5, 1.0]])
    H2 = np.array([[86.0, -14.0, 520.0], [12.0, 92.0, 330.0], [-6e-5, 9e-5, 1.0]])
    c1 = make_lattice(th, H=H1, seed=7, nr=9, nc=11)
    c2 = make_lattice(th, H=H2, seed=8, nr=10, nc=12)
    for obj in ("SD", "ED", "PD"):
        r, med, mx, thf, D = fit_and_err([c1, c2], obj, "M0", th)
        g = gauge_free_err(D.xy, thf, th)
        check(f"{obj} recovers one shared map from two captures", g < 0.02,
              f"gauge-removed median {g:.2e} px, observations {D.n} "
              f"({D.info['per_capture']}), loss {r['loss']:.3e}")


def test_capture_specific_perturbation():
    print("\n[6] A CAPTURE-SPECIFIC NONCENTRAL PERTURBATION: ONE POOLED COMPROMISE EXPECTED")
    thA = truth_theta(cx=955.0, cy=535.0)
    thB = truth_theta(cx=975.0, cy=515.0)          # 20 px centre shift in the second capture only
    H1 = np.array([[110.0, 6.0, 300.0], [-5.0, 110.0, 150.0], [7e-5, -5e-5, 1.0]])
    H2 = np.array([[92.0, -12.0, 500.0], [10.0, 96.0, 300.0], [-6e-5, 9e-5, 1.0]])
    c1 = make_lattice(thA, H=H1, seed=9, nr=9, nc=11)
    c2 = make_lattice(thB, H=H2, seed=10, nr=9, nc=11)
    D = OB.Dataset([c1, c2])
    r = OB.fit(D, "ED", "M0")
    th = np.array(r["theta14"], float)
    cA, cB = np.array([955.0, 535.0]), np.array([975.0, 515.0])
    d = np.array([th[0], th[1]])
    check("the shared centre lands between the two capture truths, not on either, and stays in "
          "the image",
          min(np.linalg.norm(d - cA), np.linalg.norm(d - cB)) > 2.0
          and 0.0 < th[0] < LT.FRAME_W and 0.0 < th[1] < LT.FRAME_H,
          f"fitted centre ({th[0]:.2f}, {th[1]:.2f}); distance to capture A "
          f"{np.linalg.norm(d - cA):.2f} px, to capture B {np.linalg.norm(d - cB):.2f} px")
    # and the compromise should show up as per-capture residual imbalance rather than a good fit
    per = []
    for c in range(2):
        m = D.cap_of == c
        pk = OB.Pack("M0", nline=D.nline, ncap=D.ncap,
                     nfree_t=sum(1 for l in D.obs_lines if len(l) == 1), objective="ED")
        rr = OB.resid_ED(np.array(r["p"]), D, pk, np.zeros(14)).reshape(-1, 2)
        per.append(float(np.sqrt((rr[m] ** 2).sum(axis=1).mean())))
    print(f"    per-capture weighted ED residual RMS {per[0]:.4f} and {per[1]:.4f} px "
          f"(a pooled compromise leaves both nonzero rather than one at zero)")
    check("both captures retain residual, i.e. no capture-specific correction was smuggled in",
          min(per) > 0.05, f"min per-capture RMS {min(per):.4f} px")


def test_sd_vs_ed_noise():
    print("\n[8] SD VERSUS ED AS NOISE GROWS  (where is Sampson adequate?)")
    th = truth_theta()
    print(f"    {'noise px':>9} {'SD-vs-ED map median':>21} {'SD-vs-ED gauge-removed':>24} "
          f"{'eta-free centre shift':>22}")
    rows = []
    for sd in (0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0):
        cap = make_lattice(th, seed=11, noise=sd)
        D = OB.Dataset([cap])
        rs = OB.fit(D, "SD", "M0")
        re = OB.fit(D, "ED", "M0")
        ts = np.array(rs["theta14"], float); te = np.array(re["theta14"], float)
        med = float(np.median(np.linalg.norm(LT.U(D.xy, ts) - LT.U(D.xy, te), axis=1)))
        g = gauge_free_err(D.xy, ts, te)
        cshift = float(np.linalg.norm(ts[:2] - te[:2]))
        rows.append((sd, med, g, cshift))
        print(f"    {sd:9.2f} {med:21.5f} {g:24.5f} {cshift:22.4f}")
    small = [r for r in rows if r[0] <= 0.5]
    check("SD and ED agree to well under a tenth of a pixel at realistic noise (<= 0.5 px)",
          max(r[1] for r in small) < 0.1,
          f"largest map difference over that range {max(r[1] for r in small):.5f} px")
    print(f"    [note] the project's own measured plumbline localization scatter is about 0.40 px, "
          f"so the realistic regime is the top of this table")


def main():
    print("=" * 104)
    print("SYNTHETIC VALIDATION OF THE NEW OBJECTIVES")
    print("=" * 104)
    test_jacobian_and_roundtrip()
    test_recovery()
    test_duplicate_invariance()
    test_nonprojective_warp()
    test_two_captures()
    test_capture_specific_perturbation()
    test_sd_vs_ed_noise()
    print("\n" + "=" * 104)
    if FAILS:
        print(f"  {len(FAILS)} FAILURE(S): " + "; ".join(FAILS))
    else:
        print("  all synthetic checks passed")
    print("=" * 104)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
