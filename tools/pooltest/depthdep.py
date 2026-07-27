#!/usr/bin/env python3
"""Does the leftover plumbline residual depend on the board's *range* rather than on image
position alone?

A camera behind a flat port, or behind a dome whose entrance pupil sits off the centre of
curvature, is not a central camera: rays do not share a single viewpoint. For such a system the
apparent bearing of a world point depends on its range as well as its direction, so "distortion"
is a function of two variables, r_u = g(r_d, Z), not one. Two consequences follow, and both are
testable here:

  * A straight line in the world does not image to a straight line, so the plumbline
    calibration's premise fails. The failure is largest where the board is nearest.
  * A radial series in r_d alone cannot represent g(r_d, Z(x,y)) over an oblique plane, because
    Z varies across the image. It can over a fronto-parallel one.

The port is axially symmetric, so the leftover error should be a *radial* vector field whose
magnitude is separable as g(r) * (1/Z - 1/Zbar): radially directed, growing with r, and changing
sign between the near and far halves of the board. That is a narrow enough prediction to falsify.

Reconstructing the lattice is what makes it measurable. Every board corner appears twice, once
in a row plumbline and once in a column plumbline, and each line measures the residual along its
own normal. Pairing them recovers the full 2D residual vector at each corner, and indexing the
lines recovers the grid, whose homography to the image gives each corner's relative depth.
"""

import math
import sqlite3
from collections import defaultdict

DOC = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/"
       "VidSync Projects/2016-08-13-2 Chena.vsd")


# --------------------------------------------------------------------------- model / io

def undistort(x, y, c):
    xd, yd = x - c["x0"], y - c["y0"]
    s = xd * xd + yd * yd
    R = 1.0
    for i, k in enumerate(c["k"], start=1):
        R += k * s ** i
    T = 1 + c["p3"] * s + c["p4"] * s * s
    dx = (c["p1"] * (s + 2 * xd * xd) + 2 * c["p2"] * xd * yd) * T
    dy = (2 * c["p1"] * xd * yd + c["p2"] * (s + 2 * yd * yd)) * T
    return c["x0"] + xd * R + dx, c["y0"] + yd * R + dy


def load(path):
    db = sqlite3.connect(path)
    cals = {}
    for row in db.execute(
            "SELECT Z_PK, ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, "
            "ZDISTORTIONK1, ZDISTORTIONK2, ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, "
            "ZDISTORTIONK6, ZDISTORTIONK7, ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, "
            "ZDISTORTIONP4 FROM ZVSCALIBRATION"):
        cals[row[0]] = {"clip": row[1], "x0": row[2], "y0": row[3], "k": list(row[4:11]),
                        "p1": row[11], "p2": row[12], "p3": row[13], "p4": row[14]}
    lines = defaultdict(lambda: defaultdict(list))
    for cal, line, idx, x, y in db.execute(
            "SELECT l.ZCALIBRATION, l.Z_PK, p.ZINDEX1, p.ZSCREENX, p.ZSCREENY "
            "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK "
            "ORDER BY l.ZCALIBRATION, l.Z_PK, p.ZINDEX1"):
        lines[cal][line].append((x, y))
    return cals, lines


# --------------------------------------------------------------------------- linear algebra

def solve(a, b):
    """Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-14:
            return None
        m[c], m[piv] = m[piv], m[c]
        for r in range(n):
            if r == c:
                continue
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def homography(src, dst):
    """DLT with Hartley normalization on both sides, h33 fixed to 1."""
    def norm(pts):
        n = len(pts)
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        d = sum(math.hypot(p[0] - cx, p[1] - cy) for p in pts) / n
        s = math.sqrt(2) / d if d > 0 else 1.0
        return [( (p[0]-cx)*s, (p[1]-cy)*s ) for p in pts], (s, cx, cy)

    ns, ts = norm(src)
    nd, td = norm(dst)
    a, b = [], []
    for (u, v), (x, y) in zip(ns, nd):
        a.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); b.append(x)
        a.append([0, 0, 0, u, v, 1, -u * y, -v * y]); b.append(y)
    ata = [[sum(a[r][i] * a[r][j] for r in range(len(a))) for j in range(8)] for i in range(8)]
    atb = [sum(a[r][i] * b[r] for r in range(len(a))) for i in range(8)]
    h = solve(ata, atb)
    if h is None:
        return None
    H = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]]
    # Undo both normalizations: H_final = Td^-1 * H * Ts
    ss, scx, scy = ts
    ds, dcx, dcy = td
    Ts = [[ss, 0, -ss * scx], [0, ss, -ss * scy], [0, 0, 1]]
    Td_inv = [[1 / ds, 0, dcx], [0, 1 / ds, dcy], [0, 0, 1]]
    def mul(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(Td_inv, mul(H, Ts))


def fit_line(pts):
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    theta = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(theta), math.sin(theta)
    return (ux, uy), [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]


def rms(v):
    return math.sqrt(sum(x * x for x in v) / len(v)) if v else float("nan")


def corr(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx > 0 and sy > 0 else float("nan")


# --------------------------------------------------------------------------- analysis

def analyse(pk, cal, lines):
    print(f"\n{'='*78}\ncalibration {pk}  (video clip {cal['clip']})\n{'='*78}")

    ul = {l: [undistort(x, y, cal) for x, y in p] for l, p in lines.items() if len(p) >= 5}
    fits = {l: fit_line(p) for l, p in ul.items()}

    angs = {l: math.degrees(math.atan2(f[0][1], f[0][0])) % 180 for l, f in fits.items()}
    ref = sorted(angs.values())[len(angs) // 2]
    fam = {l: 0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for l, a in angs.items()}

    # --- pair each corner across the two families to recover its full 2D residual ---
    index = {}
    for l, pts in ul.items():
        if fam[l] != 0:
            continue
        for i, p in enumerate(pts):
            index[(round(p[0], 3), round(p[1], 3))] = (l, i)
    corners = []
    for lb, pts in ul.items():
        if fam[lb] != 1:
            continue
        for ib, p in enumerate(pts):
            hit = index.get((round(p[0], 3), round(p[1], 3)))
            if hit is None:
                continue
            la, ia = hit
            na = (-fits[la][0][1], fits[la][0][0])
            nb = (-fits[lb][0][1], fits[lb][0][0])
            ra, rb = fits[la][1][ia], fits[lb][1][ib]
            # residual vector e satisfies e.na = ra, e.nb = rb
            det = na[0] * nb[1] - na[1] * nb[0]
            if abs(det) < 0.2:                      # families too near-parallel to invert
                continue
            ex = (ra * nb[1] - rb * na[1]) / det
            ey = (na[0] * rb - nb[0] * ra) / det
            corners.append({"x": p[0], "y": p[1], "la": la, "lb": lb, "e": (ex, ey)})

    print(f"lines {len(ul)} ({sum(1 for f in fam.values() if f==0)} + "
          f"{sum(1 for f in fam.values() if f==1)}), corners paired across both families: "
          f"{len(corners)}")
    if len(corners) < 60:
        print("  too few paired corners; skipping")
        return

    # --- index the lattice, then fit grid -> image to get relative depth ---
    def order(f):
        ls = [l for l in ul if fam[l] == f]
        # sort lines by their offset along the perpendicular to the family's mean direction
        mx = sum(math.cos(2 * math.radians(angs[l])) for l in ls)
        my = sum(math.sin(2 * math.radians(angs[l])) for l in ls)
        d = 0.5 * math.atan2(my, mx)
        px, py = -math.sin(d), math.cos(d)
        key = {l: sum(px * p[0] + py * p[1] for p in ul[l]) / len(ul[l]) for l in ls}
        return {l: i for i, l in enumerate(sorted(ls, key=lambda l: key[l]))}

    ia, ib = order(0), order(1)
    grid = [(ia[c["la"]], ib[c["lb"]]) for c in corners]
    img = [(c["x"], c["y"]) for c in corners]
    H = homography(grid, img)
    if H is None:
        print("  lattice homography failed")
        return

    # Reprojection check: if this is not tight the lattice indexing is wrong.
    rp = []
    for (u, v), (x, y) in zip(grid, img):
        w = H[2][0] * u + H[2][1] * v + H[2][2]
        rp.append(math.hypot((H[0][0]*u + H[0][1]*v + H[0][2]) / w - x,
                             (H[1][0]*u + H[1][1]*v + H[1][2]) / w - y))
    print(f"lattice homography reprojection: rms {rms(rp):.2f} px, max {max(rp):.2f} px")

    # For x = H (u,v,1), the homogeneous scale w is proportional to the point's depth.
    for c, (u, v) in zip(corners, grid):
        c["w"] = H[2][0] * u + H[2][1] * v + H[2][2]
    ws = [c["w"] for c in corners]
    if min(ws) * max(ws) <= 0:
        print("  depth changes sign across the board; pose estimate unusable")
        return
    ws = [abs(w) for w in ws]
    for c in corners:
        c["Z"] = abs(c["w"]) / min(ws)              # depth relative to the nearest corner
    print(f"board obliquity: farthest corner is {max(c['Z'] for c in corners):.3f}x "
          f"the depth of the nearest")

    # --- decompose each residual into radial and tangential ---
    for c in corners:
        dx, dy = c["x"] - cal["x0"], c["y"] - cal["y0"]
        r = math.hypot(dx, dy)
        c["r"] = r
        c["rad"] = (c["e"][0] * dx + c["e"][1] * dy) / r
        c["tan"] = (-c["e"][0] * dy + c["e"][1] * dx) / r

    print("\nis the residual field radial, as an axially symmetric port would make it?")
    print("  radius        n    rms radial   rms tangential   mean radial")
    for a, b in ((0, 300), (300, 500), (500, 700), (700, 900), (900, 1400)):
        s = [c for c in corners if a <= c["r"] < b]
        if len(s) < 10:
            continue
        print(f"  {a:4d}-{b:<5d} {len(s):5d}  {rms([c['rad'] for c in s]):10.3f}   "
              f"{rms([c['tan'] for c in s]):12.3f}   "
              f"{sum(c['rad'] for c in s)/len(s):+10.3f}")

    print("\ndoes the radial residual track 1/Z, at matched image radius?")
    print("  (prediction: mean radial residual changes sign between near and far halves)")
    print("  radius        n   near half   far half     corr(radial, 1/Z)")
    for a, b in ((0, 500), (500, 700), (700, 900), (900, 1400)):
        s = [c for c in corners if a <= c["r"] < b]
        if len(s) < 20:
            continue
        s.sort(key=lambda c: c["Z"])
        h = len(s) // 2
        near = sum(c["rad"] for c in s[:h]) / h
        far = sum(c["rad"] for c in s[h:]) / (len(s) - h)
        cc = corr([1.0 / c["Z"] for c in s], [c["rad"] for c in s])
        print(f"  {a:4d}-{b:<5d} {len(s):5d}   {near:+9.3f}  {far:+9.3f}     {cc:+.3f}")

    # --- how much of the residual is any smooth function of image position at all? ---
    # If a low-order bivariate polynomial explains it, the error is deterministic in image
    # position: a richer warp would absorb it *for this board pose*. That is the trap, because
    # under the range hypothesis the absorbed warp is only valid at this board's range.
    print("\nhow much is explained by a smooth field in image position alone?")
    print("  degree   dof   rms residual of e_x, e_y   (corner noise ~0.40 px)")
    base = rms([c["e"][0] for c in corners] + [c["e"][1] for c in corners])
    print(f"       0     1   {base:8.3f}")
    for deg in (2, 3, 4, 5):
        terms = [(i, j) for i in range(deg + 1) for j in range(deg + 1 - i)]
        sx = 1000.0
        A = [[((c["x"] - cal["x0"]) / sx) ** i * ((c["y"] - cal["y0"]) / sx) ** j
              for i, j in terms] for c in corners]
        left = []
        for comp in (0, 1):
            bvec = [c["e"][comp] for c in corners]
            n = len(terms)
            ata = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(n)]
                   for i in range(n)]
            atb = [sum(A[r][i] * bvec[r] for r in range(len(A))) for i in range(n)]
            coef = solve(ata, atb)
            if coef is None:
                left = None
                break
            left += [bvec[r] - sum(A[r][i] * coef[i] for i in range(n)) for r in range(len(A))]
        if left:
            print(f"       {deg}   {len(terms):3d}   {rms(left):8.3f}")


def main():
    cals, lines = load(DOC)
    for pk in sorted(cals):
        if pk in lines:
            analyse(pk, cals[pk], lines[pk])


if __name__ == "__main__":
    main()
