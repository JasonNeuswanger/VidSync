#!/usr/bin/env python3
"""How many of Brown-Conrady's 13 parameters does this data actually determine?

The radial series runs in powers of s = r^2, so over the covered radius range its terms form a
Vandermonde-like basis: s, s^2, ... s^7 are nearly collinear as functions on the data. If only a few
independent directions are determined, the rest are free to wander, which is both why an
unconstrained fit can find degenerate solutions and why a lower-dimensional model might be fit
reliably in pure Python.

Two measurements, neither of which needs a nonlinear solver.

*Spectrum.* Build the Jacobian of the straightness residual with respect to the parameters and take
the eigenvalues of J'J. A direction is determined only if moving along it changes the residual by
more than the corner noise.

*Nested-model penalty.* Linearize about the converged fit: forcing a subset of parameters to zero
and re-optimizing the rest costs a predictable amount of residual. Comparing that cost to the noise
floor says directly which terms are load-bearing. The linearization is checked against an exact
evaluation at the extreme where every parameter is dropped.
"""

import math
import re
import sqlite3
import statistics
from collections import defaultdict

VSD = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")
EXPORTS = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/"
           "VidSync Projects/Exports")
NAMES = ["x0", "y0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "p1", "p2", "p3", "p4"]
KEYS = ["distortionCenterX", "distortionCenterY", "distortionK1", "distortionK2", "distortionK3",
        "distortionK4", "distortionK5", "distortionK6", "distortionK7", "distortionP1",
        "distortionP2", "distortionP3", "distortionP4"]
SCALE = [1.0e3, 1.0e3, 5.0e-8, 1.0e-14, 1.0e-21, 1.0e-27, 1.0e-34, 1.0e-40, 1.0e-43,
         1.0e-7, 1.0e-7, 1.0e-7, 1.0e-10]
NOISE = 0.150          # px, measured from the four-point stencil on this set


def undistort(x, y, c):
    xd, yd = x - c[0], y - c[1]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c[2:9], start=1))
    T = 1 + c[11] * s + c[12] * s * s
    return (c[0] + xd * R + (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T,
            c[1] + yd * R + (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T)


def line_res(pts):
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    th = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(th), math.sin(th)
    return [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]


def residual_vector(lines, c):
    out = []
    for L in lines:
        out += line_res([undistort(x, y, c) for x, y in L])
    return out


def jacobi_eig(a, iters=200):
    """Eigenvalues and eigenvectors of a symmetric matrix by cyclic Jacobi rotations."""
    n = len(a)
    m = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(iters):
        off = max((abs(m[i][j]), i, j) for i in range(n) for j in range(i + 1, n))
        if off[0] < 1e-300:
            break
        _, p, q = off
        if abs(m[p][q]) < 1e-18 * math.sqrt(abs(m[p][p] * m[q][q]) + 1e-300):
            break
        theta = 0.5 * math.atan2(2 * m[p][q], m[q][q] - m[p][p])
        c, s = math.cos(theta), math.sin(theta)
        for k in range(n):
            mkp, mkq = m[k][p], m[k][q]
            m[k][p] = c * mkp - s * mkq
            m[k][q] = s * mkp + c * mkq
        for k in range(n):
            mpk, mqk = m[p][k], m[q][k]
            m[p][k] = c * mpk - s * mqk
            m[q][k] = s * mpk + c * mqk
        for k in range(n):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p] = c * vkp - s * vkq
            v[k][q] = s * vkp + c * vkq
    eig = [m[i][i] for i in range(n)]
    order = sorted(range(n), key=lambda i: -eig[i])
    return [eig[i] for i in order], [[v[r][i] for i in order] for r in range(n)]


def main():
    db = sqlite3.connect(f"file:{VSD}?mode=ro", uri=True)
    pk, = db.execute(
        "SELECT c.Z_PK FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP "
        "WHERE v.ZCLIPNAME = 'Left Camera'").fetchone()
    S = defaultdict(lambda: defaultdict(list))
    for tc, ln, x, y in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY FROM ZVSDISTORTIONLINE l "
            "JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
            "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
        if x is not None:
            S[tc][ln].append((x, y))
    db.close()
    sets = {tc: [p for p in d.values() if len(p) >= 3] for tc, d in S.items()}
    cells = {tc: statistics.median([math.dist(a, b) for p in L for a, b in zip(p, p[1:])
                                    if 1 < math.dist(a, b) < 400]) for tc, L in sets.items()}
    far = min(cells, key=lambda k: cells[k])
    lines = sets[far]
    s = open(f"{EXPORTS}/2015-09-04-1 Clearwater - FarDistortionSetOnly.xml",
             encoding="utf-8").read()
    i = s.find('<videoClip name="Left Camera"')
    theta = [float(re.search(k + r'="(-?[\d.eE+]+)"', s[i:i + 7000]).group(1)) for k in KEYS]

    r0 = residual_vector(lines, theta)
    n = len(r0)
    rms0 = math.sqrt(sum(v * v for v in r0) / n)
    print("=" * 78)
    print("Left camera, far plumbline set, its own VidSync fit")
    print("=" * 78)
    print(f"  {len(lines)} lines, {n} points, rms residual {rms0:.4f} px, "
          f"corner noise {NOISE:.3f} px")

    # Jacobian in the solver's own scaled units: a step of 1 in these units is what
    # Nelder-Mead's simplex actually moves, so the spectrum here is what it has to search.
    J = []
    for j in range(13):
        h = 1e-3
        a = list(theta); a[j] += h * SCALE[j]
        b = list(theta); b[j] -= h * SCALE[j]
        ra = residual_vector(lines, a)
        rb = residual_vector(lines, b)
        J.append([(x - y) / (2 * h) for x, y in zip(ra, rb)])

    G = [[sum(J[i][k] * J[j][k] for k in range(n)) for j in range(13)] for i in range(13)]
    eig, vec = jacobi_eig(G)
    # validate the eigensolver
    err = 0.0
    for i in range(13):
        for j in range(13):
            rec = sum(vec[i][k] * eig[k] * vec[j][k] for k in range(13))
            err = max(err, abs(rec - G[i][j]) / (abs(G[i][j]) + 1e-30))
    print(f"  eigensolver check: max relative reconstruction error {err:.2e}")

    print("\n" + "=" * 78)
    print("SPECTRUM of J'J in the solver's scaled parameters")
    print("=" * 78)
    print("  sigma is the residual change (px, rms over all points) per unit step along that")
    print("  eigen-direction. A direction is determined only if sigma exceeds the noise.")
    print(f"  {'#':>3} {'sigma (px/unit)':>17} {'vs noise':>10}   dominant parameters")
    for k in range(13):
        sigma = math.sqrt(max(0.0, eig[k]) / n)
        contrib = sorted(range(13), key=lambda i: -abs(vec[i][k]))[:3]
        desc = ", ".join(f"{NAMES[i]}({vec[i][k]:+.2f})" for i in contrib)
        flag = "determined" if sigma > NOISE else "below noise"
        print(f"  {k+1:3d} {sigma:17.4e} {sigma/NOISE:9.1e}  {flag:12s} {desc}")
    det = sum(1 for k in range(13) if math.sqrt(max(0.0, eig[k]) / n) > NOISE)
    print(f"\n  {det} of 13 directions move the residual by more than the corner noise.")
    print(f"  condition number {math.sqrt(eig[0]/max(eig[-1],1e-300)):.2e}")

    # ---- nested-model penalty ----
    print("\n" + "=" * 78)
    print("COST OF DROPPING TERMS (linearized about the converged fit)")
    print("=" * 78)

    def penalty(keep):
        """rms residual if parameters outside `keep` are forced to zero and the rest refitted."""
        drop = [j for j in range(13) if j not in keep]
        # d_j = -theta_j for dropped, in scaled units
        a = list(r0)
        for j in drop:
            dj = -theta[j] / SCALE[j]
            a = [x + dj * J[j][k] for k, x in enumerate(a)]
        kl = list(keep)
        if kl:
            Gk = [[sum(J[i][k] * J[j][k] for k in range(n)) for j in kl] for i in kl]
            bk = [-sum(J[i][k] * a[k] for k in range(n)) for i in kl]
            ek, vk = jacobi_eig(Gk)
            # truncated pseudo-inverse: directions below noise are not re-optimizable anyway
            thresh = max(ek) * 1e-12
            d = [0.0] * len(kl)
            for m in range(len(kl)):
                if ek[m] <= thresh:
                    continue
                proj = sum(vk[i][m] * bk[i] for i in range(len(kl))) / ek[m]
                for i in range(len(kl)):
                    d[i] += proj * vk[i][m]
            for i, j in enumerate(kl):
                a = [x + d[i] * J[j][k] for k, x in enumerate(a)]
        return math.sqrt(sum(x * x for x in a) / n)

    allp = list(range(13))
    base = penalty(allp)
    print(f"  linearized baseline, all 13 re-optimized: {base:.4f} px, against the true "
          f"{rms0:.4f}.")
    print("  The gap is the linear step's own improvement: the fit sits at the optimum of the")
    print("  true nonlinear objective, not of its linearization. Excesses below are measured")
    print("  against this baseline, which is the like-for-like comparison.")
    exact_zero = math.sqrt(sum(v * v for v in residual_vector(
        lines, [theta[0], theta[1]] + [0.0] * 11)) / n)
    print(f"  linearization check at the extreme -- all distortion terms zero:")
    print(f"    linear prediction {penalty([0, 1]):.2f} px vs exact {exact_zero:.2f} px")
    print("    (the model is strongly nonlinear over that whole range, so trust the")
    print("     linearization only for dropping the small high-order terms)")

    print(f"\n  {'model':>34} {'params':>7} {'predicted rms':>14} {'excess over full':>17}")
    tang = [9, 10, 11, 12]
    for m in range(7, -1, -1):
        keep = [0, 1] + list(range(2, 2 + m)) + tang
        p = penalty(keep)
        print(f"  {f'x0,y0 + k1..k{m} + p1..p4' if m else 'x0,y0 + p1..p4 only':>34} "
              f"{len(keep):7d} {p:14.4f} {math.sqrt(max(0,p*p-base*base)):17.4f}")
    print()
    for m in (7, 5, 4, 3, 2):
        keep = [0, 1] + list(range(2, 2 + m))
        p = penalty(keep)
        print(f"  {f'x0,y0 + k1..k{m}, no tangential':>34} {len(keep):7d} {p:14.4f} "
              f"{math.sqrt(max(0,p*p-base*base)):17.4f}")


if __name__ == "__main__":
    main()
