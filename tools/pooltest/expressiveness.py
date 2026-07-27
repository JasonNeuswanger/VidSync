#!/usr/bin/env python3
"""What structure is left in the plumbline residual, and could a richer model absorb it?

Two questions, both about the model rather than about the field protocol.

1. Do outer lines really fit worse, or is that an artifact of their length? A longer line has a
   longer lever arm, so the same curvature shows up as a bigger sagitta, and the eye compares the
   fitted line against a chord. Residual is therefore binned by radius *and* by line extent, so the
   two effects separate.

2. Is the leftover a deterministic function of image position that more parameters could remove?
   This is answered by a score test rather than by refitting. At a converged optimum the residual is
   orthogonal to the 13 parameter directions, so the reduction available from any candidate extra
   basis function is the fraction of residual variance it explains after those directions are
   controlled for. That is a linear computation: no nonlinear optimization, and no risk of the
   degenerate fits that unconstrained refitting has produced before in this project.

   The homography gauge matters here and is handled automatically. A homography maps straight lines
   to straight lines, so its displacement directions change no straightness residual at all and
   appear as null columns. Gram-Schmidt with a norm threshold drops them and reports the effective
   rank, which is itself informative: it counts how many directions of a displacement field the
   straightness objective can even see.
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
KEYS = ["distortionCenterX", "distortionCenterY", "distortionK1", "distortionK2", "distortionK3",
        "distortionK4", "distortionK5", "distortionK6", "distortionK7", "distortionP1",
        "distortionP2", "distortionP3", "distortionP4"]
# the solver's own parameter scaling, from VSCalibration.h
SCALE = [1.0e3, 1.0e3, 5.0e-8, 1.0e-14, 1.0e-21, 1.0e-27, 1.0e-34, 1.0e-40, 1.0e-43,
         1.0e-7, 1.0e-7, 1.0e-7, 1.0e-10]
R0 = 1000.0                        # radius normalizer for the candidate bases


def undistort(x, y, c):
    xd, yd = x - c[0], y - c[1]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c[2:9], start=1))
    T = 1 + c[11] * s + c[12] * s * s
    return (c[0] + xd * R + (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T,
            c[1] + yd * R + (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T)


def fit_line(pts):
    """Returns unit direction, centroid, and signed perpendicular residuals."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    th = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(th), math.sin(th)
    res = [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]
    t = [(p[0] - cx) * ux + (p[1] - cy) * uy for p in pts]
    return (ux, uy), (cx, cy), res, t


def read_fit(path):
    s = open(path, encoding="utf-8").read()
    i = s.find('<videoClip name="Left Camera"')
    seg = s[i:i + 7000]
    return [float(re.search(k + r'="(-?[\d.eE+]+)"', seg).group(1)) for k in KEYS]


def load():
    db = sqlite3.connect(f"file:{VSD}?mode=ro", uri=True)
    pk, cx, cy = db.execute(
        "SELECT c.Z_PK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY FROM ZVSCALIBRATION c "
        "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP "
        "WHERE v.ZCLIPNAME = 'Left Camera'").fetchone()
    S = defaultdict(lambda: defaultdict(list))
    for tc, ln, x, y in db.execute(
            "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY FROM ZVSDISTORTIONLINE l "
            "JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
            "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
        if x is not None:
            S[tc][ln].append((x, y))
    db.close()
    return (cx, cy), {tc: [p for p in d.values() if len(p) >= 3] for tc, d in S.items()}


def residualize(col, groups, tcols):
    """Remove each line's own fitted degrees of freedom (offset and rotation) from a column."""
    out = list(col)
    for idx, t in zip(groups, tcols):
        n = len(idx)
        v = [out[i] for i in idx]
        mt = sum(t) / n
        mv = sum(v) / n
        stt = sum((x - mt) ** 2 for x in t)
        b = (sum((x - mt) * (y - mv) for x, y in zip(t, v)) / stt) if stt > 0 else 0.0
        for k, i in enumerate(idx):
            out[i] = v[k] - mv - b * (t[k] - mt)
    return out


def gram_schmidt(cols, tol=1e-6):
    """Orthonormalize a set of columns that are already on a common physical scale.

    Two numerical traps had to be closed here, and both produced a spurious 100% variance
    reduction before they were.

    The parameter-direction fields span some forty-five orders of magnitude, because the k7
    derivative carries s^7 and s reaches 1e6 at the frame corner. Orthogonalizing a small
    candidate against a huge one cancels every significant digit. Fixed upstream, by scaling
    every displacement field to 1 px rms before it becomes a column.

    Worse, some candidate fields are pure gauge -- a uniform scaling about the distortion centre
    bends no line at all, so its true column is exactly zero. Normalizing such a column to unit
    length promotes round-off into a unit vector that then absorbs real variance. Gauge columns
    are therefore rejected upstream by an absolute threshold, and the tolerance here only has to
    catch combinations that reduce to gauge after orthogonalization.
    """
    basis, kept = [], []
    for j, c in enumerate(cols):
        n0 = math.sqrt(sum(x * x for x in c))
        if n0 == 0:
            continue
        v = [x / n0 for x in c]
        for _ in range(2):
            for b in basis:
                d = sum(x * y for x, y in zip(v, b))
                v = [x - d * y for x, y in zip(v, b)]
        n = math.sqrt(sum(x * x for x in v))
        if n > tol:
            basis.append([x / n for x in v])
            kept.append(j)
    return basis, kept


def explained(resid, cols):
    """Fraction of residual variance removable by the span of cols, and the leftover rms."""
    basis, kept = gram_schmidt(cols)
    r = list(resid)
    for b in basis:
        d = sum(x * y for x, y in zip(r, b))
        r = [x - d * y for x, y in zip(r, b)]
    n = len(resid)
    return (math.sqrt(sum(x * x for x in r) / n), len(basis), len(kept))


def main():
    centre, sets = load()
    cx, cy = centre
    cells = {tc: statistics.median([math.dist(a, b) for p in L for a, b in zip(p, p[1:])
                                    if 1 < math.dist(a, b) < 400]) for tc, L in sets.items()}
    far = min(cells, key=lambda k: cells[k])
    lines = sets[far]
    fit = read_fit(f"{EXPORTS}/2015-09-04-1 Clearwater - FarDistortionSetOnly.xml")

    # flatten, keeping line membership
    pts, resid, groups, tcols, extent = [], [], [], [], []
    for L in lines:
        u = [undistort(x, y, fit) for x, y in L]
        d, cen, r, t = fit_line(u)
        idx = list(range(len(pts), len(pts) + len(L)))
        groups.append(idx)
        tcols.append(t)
        span = max(t) - min(t)
        for (ox, oy), rr in zip(L, r):
            pts.append((ox, oy))
            resid.append(rr)
            extent.append(span)
        for _ in L:
            pass
    n = len(pts)
    rms0 = math.sqrt(sum(v * v for v in resid) / n)
    print("=" * 82)
    print("Left camera, far plumbline set (47 lines, 640 points), its own VidSync fit")
    print("=" * 82)
    print(f"  overall rms straightness residual {rms0:.4f} px over {n} points")
    print(f"  corner-noise floor measured earlier: 0.150 px")

    # ---- question 1: radius versus line extent ----
    print("\n" + "=" * 82)
    print("1. Is the outer-band residual about radius, or about line length?")
    print("=" * 82)
    ex = sorted(set(extent))
    cuts = [ex[len(ex) // 3], ex[2 * len(ex) // 3]]
    print(f"  line extent terciles split at {cuts[0]:.0f} and {cuts[1]:.0f} px")
    print(f"  {'radius':>12} " + "".join(f"{lab:>18}" for lab in
                                         ("short lines", "medium", "long lines")))
    for lo, hi in ((0, 400), (400, 600), (600, 800), (800, 1200)):
        row = []
        for elo, ehi in ((0, cuts[0]), (cuts[0], cuts[1]), (cuts[1], 1e9)):
            s = [resid[i] for i in range(n)
                 if lo <= math.hypot(pts[i][0] - cx, pts[i][1] - cy) < hi
                 and elo <= extent[i] < ehi]
            row.append(f"{math.sqrt(sum(v*v for v in s)/len(s)):.3f} (n={len(s)})"
                       if len(s) >= 10 else "-")
        print(f"  {f'{lo}-{hi}':>12} " + "".join(f"{v:>18}" for v in row))
    print("\n  Reading down a column holds line length roughly fixed; reading across holds")
    print("  radius fixed. Whichever direction the residual grows in is the real driver.")

    # ---- build the 13 existing parameter directions, numerically ----
    def param_dir(j):
        step = SCALE[j] * 1e-2
        a = list(fit); a[j] += step
        b = list(fit); b[j] -= step
        col = []
        for (x, y), gi in zip(pts, range(n)):
            ua = undistort(x, y, a)
            ub = undistort(x, y, b)
            col.append(((ua[0] - ub[0]) / (2 * step), (ua[1] - ub[1]) / (2 * step)))
        return col

    normals = [0.0] * n
    nvecs = []
    for L, idx in zip(lines, groups):
        u = [undistort(x, y, fit) for x, y in L]
        d, cen, r, t = fit_line(u)
        nv = (-d[1], d[0])
        for i in idx:
            nvecs.append(nv)
    assert len(nvecs) == n

    def raw_col(vecfield):
        """Signed non-straightness a displacement field induces, per 1 px rms of displacement."""
        m = math.sqrt(sum(vx * vx + vy * vy for vx, vy in vecfield) / len(vecfield))
        if m == 0:
            return None
        return residualize([(vx * nv[0] + vy * nv[1]) / m
                            for (vx, vy), nv in zip(vecfield, nvecs)], groups, tcols)

    # The eight generators of the projective group acting on the image plane: two translations,
    # four linear (two scalings and two shears), two projective. These must be removed by hand
    # rather than detected numerically.
    #
    # It is tempting to assume they induce no straightness change, since a homography maps
    # straight lines to straight lines. That holds only for points that are *already* straight.
    # The plumbline points are not -- they carry the residual -- so a homography rescales the
    # existing residuals, and the isotropic-scale generator's column comes out exactly parallel
    # to the residual vector. Left in, it "explains" 100% of the residual by shrinking the image,
    # which is the same scale degeneracy that let an unconstrained fit reach 0.0037 px per point
    # while being physically meaningless.
    def gauge_fields():
        u = [(x - cx) / R0 for x, y in pts]
        v = [(y - cy) / R0 for x, y in pts]
        return [[(1.0, 0.0)] * len(pts), [(0.0, 1.0)] * len(pts),
                [(a, 0.0) for a in u], [(b, 0.0) for b in v],
                [(0.0, a) for a in u], [(0.0, b) for b in v],
                [(a * a, a * b) for a, b in zip(u, v)],
                [(a * b, b * b) for a, b in zip(u, v)]]

    gauge, _ = gram_schmidt([c for c in (raw_col(f) for f in gauge_fields()) if c is not None])
    print(f"\n  projective gauge spans {len(gauge)} of 8 possible directions in this data;")
    print("  every column below is projected orthogonal to it, so no reported improvement can")
    print("  be obtained by rescaling or reprojecting the image.")

    def degauge(col):
        v = list(col)
        for _ in range(2):
            for g in gauge:
                d = sum(x * y for x, y in zip(v, g))
                v = [x - d * y for x, y in zip(v, g)]
        return v

    def to_col(vecfield):
        c = raw_col(vecfield)
        if c is None:
            return None
        n0 = math.sqrt(sum(x * x for x in c))
        if n0 == 0:
            return None
        v = degauge(c)
        # a field whose entire effect is gauge carries no information about the model
        if math.sqrt(sum(x * x for x in v)) / n0 < 1e-6:
            return None
        return v

    def cols_of(fields):
        return [c for c in (to_col(f) for f in fields) if c is not None]

    existing = cols_of([param_dir(j) for j in range(13)])

    print("\n" + "=" * 82)
    print("2. Convergence check: is the residual already orthogonal to the 13 parameters?")
    print("=" * 82)
    rn = math.sqrt(sum(v * v for v in resid))
    print(f"  {'parameter':>12} {'|correlation with residual|':>28}")
    worst = 0.0
    for j, name in enumerate(["x0", "y0", "k1", "k2", "k3", "k4", "k5", "k6", "k7",
                              "p1", "p2", "p3", "p4"]):
        c = to_col(param_dir(j))
        if c is None:
            print(f"  {name:>12} {'pure gauge, invisible':>28}")
            continue
        cn = math.sqrt(sum(v * v for v in c))
        corr = abs(sum(a * b for a, b in zip(resid, c)) / (rn * cn)) if cn > 0 else 0.0
        worst = max(worst, corr)
        print(f"  {name:>12} {corr:28.4f}")
    print(f"  largest {worst:.4f} -- small values confirm the solve reached its optimum, so")
    print("  nothing more is available from the existing parameters.")
    after, rank, _ = explained(resid, existing)
    print(f"  residual after projecting out all 13: {after:.4f} px "
          f"(from {rms0:.4f}); effective rank {rank}")

    # ---- candidate extra bases ----
    def poly_fields(deg):
        out = []
        for i in range(deg + 1):
            for j in range(deg + 1 - i):
                if i + j == 0:
                    continue
                out.append([(((x - cx) / R0) ** i * ((y - cy) / R0) ** j, 0.0) for x, y in pts])
                out.append([(0.0, ((x - cx) / R0) ** i * ((y - cy) / R0) ** j) for x, y in pts])
        return out

    print("\n" + "=" * 82)
    print("3. What could a richer image-space model buy? (score test, no refitting)")
    print("=" * 82)
    print(f"  {'added basis':>34} {'dof seen':>9} {'rms after':>11} {'reduction':>11}")
    print(f"  {'nothing (current fit)':>34} {'':9} {rms0:11.4f} {'':11}")
    for deg in (2, 3, 4, 5, 6):
        fields = poly_fields(deg)
        seen = cols_of(fields)
        cols = existing + seen
        rms, rank, _ = explained(resid, cols)
        print(f"  {f'polynomial displacement, degree {deg}':>34} {rank:9d} {rms:11.4f} "
              f"{1 - rms/rms0:10.1%}   ({len(fields)-len(seen)} of {len(fields)} gauge)")

    # extra purely radial terms, the obvious first guess
    radial = []
    for p in (8, 9, 10):
        radial.append([(((x - cx)) * (((x - cx) ** 2 + (y - cy) ** 2) / R0 ** 2) ** p,
                        ((y - cy)) * (((x - cx) ** 2 + (y - cy) ** 2) / R0 ** 2) ** p)
                       for x, y in pts])
    rms, rank, _ = explained(resid, existing + cols_of(radial))
    print(f"  {'three more radial terms k8-k10':>34} {rank:9d} {rms:11.4f} "
          f"{1 - rms/rms0:10.1%}")

    # angular harmonics of a radial displacement: the decentred-dome signature
    print("\n" + "=" * 82)
    print("4. Angular structure: which harmonics carry the missing signal?")
    print("=" * 82)
    print("  radial displacement modulated by cos/sin(m*phi), radial weight rho^1..rho^4")
    print(f"  {'harmonic':>12} {'dof seen':>9} {'rms after':>11} {'reduction':>11}")
    for m in (0, 1, 2, 3, 4):
        fields = []
        for p in (1, 2, 3, 4):
            for phase in (0, 1):
                f = []
                for x, y in pts:
                    ex, ey = x - cx, y - cy
                    rho = math.hypot(ex, ey) / R0
                    if rho < 1e-9:
                        f.append((0.0, 0.0))
                        continue
                    phi = math.atan2(ey, ex)
                    a = math.cos(m * phi) if phase == 0 else math.sin(m * phi)
                    w = rho ** p * a
                    f.append((w * ex / (rho * R0), w * ey / (rho * R0)))
                fields.append(f)
        cols = existing + cols_of(fields)
        rms, rank, _ = explained(resid, cols)
        print(f"  {f'm = {m}':>12} {rank:9d} {rms:11.4f} {1 - rms/rms0:10.1%}")


if __name__ == "__main__":
    main()
