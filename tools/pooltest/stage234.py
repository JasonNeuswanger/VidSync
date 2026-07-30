#!/usr/bin/env python3
"""Stages 2-4: nuisance sensitivity of eta, projective-gauge quotient, residual-space harmonics.

Loads the converged Stage 1 solutions from /tmp/normfit_results.npy (rows: L_M0, R_M0, L_M1, R_M1).
Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("normfit", os.path.join(HERE, "normfit.py"))
N = importlib.util.module_from_spec(_s)
_s.loader.exec_module(N)
R, W, H = N.R, N.W, N.H


def fitv(clip, free, seeds):
    best = None
    basins = []
    for s0 in seeds:
        s0 = np.clip(np.asarray(s0, float), N.BLO, N.BHI)

        def rr(w, s0=s0):
            v = s0.copy()
            v[free] = w
            return clip.resid_b(v)
        try:
            r = least_squares(rr, s0[free], method="trf", x_scale=1.0,
                              bounds=(N.BLO[free], N.BHI[free]),
                              ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
        except Exception:                                    # noqa: BLE001
            continue
        v = s0.copy()
        v[free] = r.x
        c = clip.sse(v)
        basins.append(c)
        if best is None or c < best[1]:
            best = (v, c, r)
    v, c, r = best
    return {"v": v, "sse": c, "rms": math.sqrt(c / clip.n), "opt": float(r.optimality),
            "nsame": sum(1 for b in basins if abs(b - c) <= max(1e-9, 1e-6 * c)),
            "nstart": len(basins)}


def jac_svd(clip, v, free):
    eps = 1e-6
    J = []
    for j in free:
        a = v.copy(); a[j] += eps
        b = v.copy(); b[j] -= eps
        J.append((clip.resid(a) - clip.resid(b)) / (2 * eps))
    sv = np.linalg.svd(np.array(J).T, compute_uv=False)
    return sv


# ---------------------------------------------------------------- harmonics

def polar(pos, cref):
    d = pos - cref
    r = np.hypot(d[:, 0], d[:, 1])
    return d, r, np.arctan2(d[:, 1], d[:, 0])


def design(r, phi, mmax=8, nrad=3):
    t = (r / R) ** 2
    rad = np.stack([t ** j for j in range(nrad)], axis=1)
    cols = [rad]
    for m in range(1, mmax + 1):
        cols.append(rad * np.cos(m * phi)[:, None])
        cols.append(rad * np.sin(m * phi)[:, None])
    return np.concatenate(cols, axis=1)


def joint_harm(pos, vec, cref, rref=700.0, mmax=8, nrad=3):
    """Simultaneous radial-angular fit; returns cos/sin coefficient functions at rref."""
    d, r, phi = polar(pos, cref)
    keep = (r > 150.0) & np.isfinite(vec[:, 0]) & np.isfinite(vec[:, 1])
    d, r, phi, v = d[keep], r[keep], phi[keep], vec[keep]
    rad = (v[:, 0] * d[:, 0] + v[:, 1] * d[:, 1]) / r
    tan = (-v[:, 0] * d[:, 1] + v[:, 1] * d[:, 0]) / r
    X = design(r, phi, mmax, nrad)
    tr = (rref / R) ** 2
    basis = np.array([tr ** j for j in range(nrad)])
    sv = np.linalg.svd(X, compute_uv=False)
    rank = int((sv > sv[0] * 1e-10).sum())
    out = {}
    for nm, y in (("rad", rad), ("tan", tan)):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        for m in (1, 2, 3):
            i = nrad * (1 + 2 * (m - 1))
            cc = float(beta[i:i + nrad] @ basis)
            ss = float(beta[i + nrad:i + 2 * nrad] @ basis)
            out[(nm, m)] = (cc, ss, math.hypot(cc, ss), math.degrees(math.atan2(ss, cc)))
    return out, int(keep.sum()), rank, float(sv[0] / sv[-1]), X.shape[1]


def hline(tag, h):
    parts = []
    for nm in ("rad", "tan"):
        seg = "; ".join(f"m{m} cos {h[(nm,m)][0]:+8.4f} sin {h[(nm,m)][1]:+8.4f} "
                        f"(amp {h[(nm,m)][2]:7.4f}, ph {h[(nm,m)][3]:+7.1f})" for m in (1, 2, 3))
        parts.append(f"      {tag} {nm}: {seg}")
    return "\n".join(parts)


# ---------------------------------------------------------------- maps

def Uparts(x, c, k, p, eta, conj_r=True, conj_p=True):
    a = N.amat(eta)
    u = (x - c) * a
    u0 = x - c
    dr = N.delta_r(u, k) / a if conj_r else N.delta_r(u0, k)
    dp = N.d_p(u, p) / a if conj_p else N.d_p(u0, p)
    return c + u0 + dr + dp


def main():
    say = lambda *a: print(" ".join(str(x) for x in a), flush=True)
    V = np.load("/tmp/normfit_results.npy")
    L_M0, R_M0, L_M1, R_M1 = V[0], V[1], V[2], V[3]
    clipL = N.Clip("Left Camera")

    # ================= STAGE 2 =================
    say("=" * 100)
    say("STAGE 2  SENSITIVITY OF eta TO THE CENTRE / DECENTERING NUISANCE STRUCTURE (Left Camera)")
    say("=" * 100)
    variants = [
        ("1 free centre, p1..p4", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], None),
        ("2 free centre, p1,p2 only", [0, 1, 2, 3, 4, 5, 6, 7], None),
        ("3 centre fixed (960,540)", [2, 3, 4, 5, 6, 7, 8, 9], (0.0, 0.0)),
        ("4 free centre, no decentering", [0, 1, 2, 3, 4, 5], None),
    ]
    full_eta, full_gain = L_M1[10], (N.Clip("Left Camera").sse(L_M0) - clipL.sse(L_M1))
    rg = np.random.default_rng(11)
    say(f"  reference: full model eta-hat {full_eta:+.6f}, SSE gain "
        f"{clipL.sse(L_M0):.2f} -> {clipL.sse(L_M1):.2f} = {full_gain:.2f}")
    for name, freeb, fixc in variants:
        base = L_M1.copy()
        base[10] = 0.0
        if fixc:
            base[0], base[1] = fixc
        for j in range(11):
            if j not in freeb and j != 10 and not (fixc and j < 2):
                base[j] = 0.0
        seeds0 = [base.copy()] + [np.clip(base + np.concatenate(
            [rg.normal(0, .3, 10), [0.0]]), N.BLO, N.BHI) for _ in range(7)]
        for s in seeds0:
            s[10] = 0.0
            if fixc:
                s[0], s[1] = fixc
            for j in range(11):
                if j not in freeb and j != 10:
                    s[j] = base[j]
        m0 = fitv(clipL, np.array(freeb), seeds0)
        freea = np.array(freeb + [10])
        seeds1 = [m0["v"].copy()] + [np.clip(m0["v"] + np.concatenate(
            [rg.normal(0, .2, 10), [rg.normal(0, .01)]]), N.BLO, N.BHI) for _ in range(7)]
        m1 = fitv(clipL, freea, seeds1)
        c1, k1, p1, e1 = N.norm_to_phys(m1["v"])
        u = (clipL.xy - c1) * N.amat(e1)
        fr = float(np.linalg.norm(N.delta_r(u, k1), axis=1).max())
        fp = float(np.linalg.norm(N.d_p(u, p1), axis=1).max())
        sv = jac_svd(clipL, m1["v"], freea)
        gain = m0["sse"] - m1["sse"]
        # profile
        prof = []
        for e in (full_eta - 0.004, full_eta - 0.002, full_eta, full_eta + 0.002,
                  full_eta + 0.004):
            s0 = m1["v"].copy(); s0[10] = e
            pr = fitv(clipL, np.array(freeb), [s0])
            prof.append((e, pr["sse"]))
        say(f"\n  --- {name} ---")
        say(f"    eta=0   RMS {m0['rms']:.6f}  SSE {m0['sse']:.3f}  opt {m0['opt']:.2e}  "
            f"starts {m0['nsame']}/{m0['nstart']}")
        say(f"    free eta RMS {m1['rms']:.6f}  SSE {m1['sse']:.3f}  opt {m1['opt']:.2e}  "
            f"starts {m1['nsame']}/{m1['nstart']}")
        say(f"    eta-hat {e1:+.6f}   change from full model {e1-full_eta:+.6f} "
            f"({100*(e1-full_eta)/full_eta:+.1f}%)")
        say(f"    centre ({c1[0]:.2f}, {c1[1]:.2f})   max radial {fr:.2f} px, "
            f"max decentering {fp:.2f} px")
        say(f"    scaled singular values {np.array2string(sv, precision=3, max_line_width=200)}")
        say(f"    Jacobian condition {sv[0]/sv[-1]:.3e}")
        say(f"    SSE gain from eta {gain:.2f}; fraction of the full model's gain retained "
            f"{100*gain/full_gain:.1f}%")
        say(f"    eta profile (dSSE from this variant's optimum): " +
            "  ".join(f"{e:+.4f}:{s-m1['sse']:+.2f}" for e, s in prof))

    # ================= STAGE 3 =================
    say("\n" + "=" * 100)
    say("STAGE 3  MAP DIFFERENCE MODULO THE DOWNSTREAM PROJECTIVE GAUGE (Left Camera)")
    say("=" * 100)
    lo, hi = clipL.xy.min(axis=0), clipL.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 60), np.linspace(lo[1], hi[1], 40))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    cc = 0.5 * (lo + hi)
    keep = np.hypot(grid[:, 0] - cc[0], grid[:, 1] - cc[1]) <= 0.5 * np.hypot(*(hi - lo))
    grid = grid[keep]
    c0, k0, p0, e0 = N.norm_to_phys(L_M0)
    c1, k1, p1, e1 = N.norm_to_phys(L_M1)
    U0 = N.Umap(grid, c0, k0, p0, 0.0)
    U1 = N.Umap(grid, c1, k1, p1, e1)
    Uc = N.Umap(grid, c1, k1, p1, 0.0)
    say(f"  grid: {len(grid)} points, approximately area-uniform over the supported domain")

    def align(src, tgt, kind):
        n = len(src)
        A = np.zeros((2 * n, 6))
        b = np.zeros(2 * n)
        A[0::2, 0] = src[:, 0]; A[0::2, 1] = src[:, 1]; A[0::2, 2] = 1
        A[1::2, 3] = src[:, 0]; A[1::2, 4] = src[:, 1]; A[1::2, 5] = 1
        b[0::2] = tgt[:, 0]; b[1::2] = tgt[:, 1]
        aff, *_ = np.linalg.lstsq(A, b, rcond=None)
        pred = np.stack([src @ aff[0:2] + aff[2], src @ aff[3:5] + aff[5]], axis=1)
        if kind == "affine":
            return tgt - pred
        h0 = np.array([aff[0], aff[1], aff[2], aff[3], aff[4], aff[5], 0.0, 0.0])
        sc = np.abs(src).max()

        def res(h):
            w = (h[6] * src[:, 0] + h[7] * src[:, 1]) / sc + 1.0
            px = (h[0] * src[:, 0] + h[1] * src[:, 1] + h[2]) / w
            py = (h[3] * src[:, 0] + h[4] * src[:, 1] + h[5]) / w
            return np.concatenate([px - tgt[:, 0], py - tgt[:, 1]])
        r = least_squares(res, h0, method="lm", xtol=1e-15, ftol=1e-15, max_nfev=20000)
        h = r.x
        w = (h[6] * src[:, 0] + h[7] * src[:, 1]) / sc + 1.0
        pred = np.stack([(h[0] * src[:, 0] + h[1] * src[:, 1] + h[2]) / w,
                         (h[3] * src[:, 0] + h[4] * src[:, 1] + h[5]) / w], axis=1)
        return tgt - pred

    for lab, src, tgt in (("U0 -> U1  (baseline to anisotropic)", U0, U1),
                          ("Uc -> U1  (direct anisotropy only)", Uc, U1)):
        say(f"\n  {lab}")
        for kind, dv in (("before alignment", tgt - src),
                         ("after best affine", align(src, tgt, "affine")),
                         ("after best homography", align(src, tgt, "homog"))):
            mag = np.linalg.norm(dv, axis=1)
            d = grid - c1
            rr = np.hypot(d[:, 0], d[:, 1])
            radc = (dv[:, 0] * d[:, 0] + dv[:, 1] * d[:, 1]) / np.maximum(rr, 1e-9)
            tanc = (-dv[:, 0] * d[:, 1] + dv[:, 1] * d[:, 0]) / np.maximum(rr, 1e-9)
            say(f"    {kind:24s} rms {np.sqrt((mag**2).mean()):9.4f}  "
                f"median {np.median(mag):9.4f}  max {mag.max():9.4f}  "
                f"radial rms {np.sqrt((radc**2).mean()):8.4f}  "
                f"tangential rms {np.sqrt((tanc**2).mean()):8.4f}")

    # ================= STAGE 4 =================
    say("\n" + "=" * 100)
    say("STAGE 4  RESIDUAL-SPACE DECOMPOSITION WITH A JOINT HARMONIC ESTIMATOR (Left Camera)")
    say("=" * 100)
    spec = importlib.util.spec_from_file_location(
        "ellip_one", os.path.join(HERE, "ellip_one.py"))
    EO = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(EO)

    def pairs_and_field(eta, k, p, c, conj_r=True, conj_p=True, pairs=None):
        L = {i: np.asarray(v, float) for i, v in clipL.lineset.items() if len(v) >= 4}
        fits = {}
        for i, pts in L.items():
            u = Uparts(pts, c, k, p, eta, conj_r, conj_p)
            cen = u.mean(axis=0)
            q = u - cen
            th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                                  float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
            d = np.array([math.cos(th), math.sin(th)])
            fits[i] = (d, -q[:, 0] * d[1] + q[:, 1] * d[0])
        if pairs is None:
            angs = {i: math.degrees(math.atan2(d[1], d[0])) % 180 for i, (d, _) in fits.items()}
            ref = sorted(angs.values())[len(angs) // 2]
            fam = {i: 0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1
                   for i, a in angs.items()}
            idx = {}
            for i, pts in L.items():
                if fam[i] == 0:
                    for j, q in enumerate(pts):
                        idx[(round(q[0], 3), round(q[1], 3))] = (i, j)
            pairs = []
            for ib, pts in L.items():
                if fam[ib] != 1:
                    continue
                for jb, q in enumerate(pts):
                    hit = idx.get((round(q[0], 3), round(q[1], 3)))
                    if hit:
                        pairs.append((hit[0], hit[1], ib, jb, q[0], q[1]))
        out = []
        for ia, ja, ib, jb, px, py in pairs:
            ua, ub = fits[ia][0], fits[ib][0]
            na = np.array([-ua[1], ua[0]]); nb = np.array([-ub[1], ub[0]])
            det = na[0] * nb[1] - na[1] * nb[0]
            if abs(det) < 0.25:
                out.append((np.nan, np.nan)); continue
            ra, rb = fits[ia][1][ja], fits[ib][1][jb]
            out.append(((ra * nb[1] - rb * na[1]) / det, (na[0] * rb - nb[0] * ra) / det))
        return pairs, np.asarray(out)

    pairs, _ = pairs_and_field(0.0, k0, p0, c0)
    pos = np.array([[q[4], q[5]] for q in pairs])
    cref = c0
    say(f"  paired corners {len(pos)}; fixed polar origin for all projections "
        f"({cref[0]:.4f}, {cref[1]:.4f}); corners with r > 150 px used")

    # 4a intrinsic content on a uniform angular grid
    say("\n  4a INTRINSIC ANGULAR CONTENT ON A UNIFORM GRID (FFT, 512 angles)")
    a = N.amat(e1)
    for rad0 in (300.0, 600.0, 900.0):
        ph = np.linspace(0, 2 * math.pi, 512, endpoint=False)
        uu = np.stack([rad0 * np.cos(ph), rad0 * np.sin(ph)], axis=1)
        dAr = N.delta_r(uu * a, k1) / a - N.delta_r(uu, k1)
        dAp = N.d_p(uu * a, p1) / a - N.d_p(uu, p1)
        for nm, fld in (("dA_r", dAr), ("dA_p", dAp)):
            rc = (fld[:, 0] * np.cos(ph) + fld[:, 1] * np.sin(ph))
            tc = (-fld[:, 0] * np.sin(ph) + fld[:, 1] * np.cos(ph))
            Fr = np.fft.rfft(rc) / len(ph)
            Ft = np.fft.rfft(tc) / len(ph)
            amps = [2 * abs(Fr[m]) for m in range(0, 9)]
            say(f"    r={rad0:4.0f} {nm} radial     m0..m8 " +
                " ".join(f"{x:8.5f}" for x in amps))
            say(f"    r={rad0:4.0f} {nm} tangential rms {np.sqrt((tc**2).mean()):.3e}, "
                f"m1..m3 " + " ".join(f"{2*abs(Ft[m]):8.5f}" for m in (1, 2, 3)))

    # 4b/4c residual-space telescoping with the validated estimator
    say("\n  4c VALIDATION OF THE JOINT ESTIMATOR ON dA_r AT THE OBSERVED CORNERS")
    uu = (pos - c1) * a
    u0 = pos - c1
    dAr_obs = N.delta_r(uu, k1) / a - N.delta_r(u0, k1)
    h, nn, rank, cond, ncol = joint_harm(pos, dAr_obs, cref)
    say(f"    design {ncol} columns, rank {rank}, condition {cond:.3e}, n {nn}")
    say(hline("dA_r at corners", h))
    say("    (analytically dA_r has zero odd content; residual odd coefficients here measure")
    say("     the estimator's remaining leakage on this corner distribution)")

    maps = [("R(U0) baseline", (0.0, k0, p0, c0, True, True)),
            ("R(Uk) radial refit", (0.0, k1, p0, c0, True, True)),
            ("R(Up) decentering refit", (0.0, k1, p1, c0, True, True)),
            ("R(Uc) centre refit", (0.0, k1, p1, c1, True, True)),
            ("R(UA) full anisotropy", (e1, k1, p1, c1, True, True))]
    flds = {}
    for nm, args in maps:
        _, f = pairs_and_field(*args, pairs=pairs)
        flds[nm] = f
    order = [m[0] for m in maps]
    say("\n  4b RESIDUAL-SPACE FIELDS AND TELESCOPING INCREMENTS")
    for nm in order:
        h, nn, rank, cond, _ = joint_harm(pos, flds[nm], cref)
        mag = np.linalg.norm(flds[nm][np.isfinite(flds[nm][:, 0])], axis=1)
        say(f"\n    [{nm}]  n={nn}  rms |residual vector| {np.sqrt((mag**2).mean()):.4f} px")
        say(hline("", h))
    for i in range(1, len(order)):
        inc = flds[order[i]] - flds[order[i - 1]]
        h, nn, rank, cond, _ = joint_harm(pos, inc, cref)
        mag = np.linalg.norm(inc[np.isfinite(inc[:, 0])], axis=1)
        say(f"\n    [increment {order[i-1]} -> {order[i]}]  "
            f"rms {np.sqrt((mag**2).mean()):.4f} px")
        say(hline("", h))

    say("\n  4b SPLIT OF THE FINAL STEP, BOTH ORDERS")
    _, f_Ar = pairs_and_field(e1, k1, p1, c1, True, False, pairs)
    _, f_Ap = pairs_and_field(e1, k1, p1, c1, False, True, pairs)
    for lab, a1, a2 in (("radial first, then decentering", f_Ar, flds["R(UA) full anisotropy"]),
                        ("decentering first, then radial", f_Ap,
                         flds["R(UA) full anisotropy"])):
        s1 = a1 - flds["R(Uc) centre refit"]
        s2 = a2 - a1
        for nm2, ff in ((f"{lab}: step 1", s1), (f"{lab}: step 2", s2)):
            h, nn, rank, cond, _ = joint_harm(pos, ff, cref)
            mag = np.linalg.norm(ff[np.isfinite(ff[:, 0])], axis=1)
            say(f"\n    [{nm2}]  rms {np.sqrt((mag**2).mean()):.4f} px")
            say(hline("", h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
