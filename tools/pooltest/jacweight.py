#!/usr/bin/env python3
"""Does weighting the refinement by the undistortion Jacobian improve real measurements?

VSPoint.m's iterative refinement minimizes squared reprojection error in *undistorted* pixels,
summed over cameras. Click noise is isotropic in *raw* pixels, and undistortion magnifies it by
the local Jacobian J, so a physical click error d contributes |J d|^2 rather than |d|^2. On an
8 mm fisheye that magnification runs 1.0 at the frame centre to 3.3 at the corner, so peripheral
clicks are weighted an order of magnitude too heavily. The maximum-likelihood objective for
isotropic raw-pixel noise is |J^-1 (reprojected - observed)|^2.

Tested here on 2015-09-04-1 Clearwater, which carries 'Length Tests' objects whose names give
the true length. It is a small set, but it is on a heavily distorted video, which the 2012 pool
test is not: there the two cameras' magnifications differ by 0.4% and nothing is measurable.

Everything is recomputed from the raw screen clicks, so the comparison is like-for-like.
"""

import math
import plistlib
import re
import sqlite3
from collections import defaultdict

DOC = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")

# Each entry: path, the tracked-object type holding known lengths, and the factor converting
# the document's world units to millimetres. The pool test works in metres; the Drift Model
# documents work in millimetres, which is why its stored cameraMeanPLD of 0.001 is 1.0 mm and
# not the vanishingly small number it looks like next to Clearwater's 3.9.
DOCS = [
    ("2015-09-04-1 Clearwater (8 mm fisheye)",
     "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
     "2015-09-04-1 Clearwater.vsd", "Length Tests", 1.0),
    ("2015-06-22-1 Clearwater (13 mm)",
     "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
     "2015-06-22-1 Clearwater.vsd", "Frame Test", 1.0),
    # Same 14 measurements as the first entry under an earlier, better-fitting calibration of
    # the right camera (1.12 px against 2.31). Not independent evidence -- a robustness check
    # on whether the comparison survives recalibration.
    ("2015-09-04-1 Clearwater, pre-1.8 backup calibration",
     "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
     "2015-09-04-1 Clearwater Backup pre-VidSync1.8.vsd", "Length Tests", 1.0),
    ("2012 pool test (mild distortion -- negative control)",
     "/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
     "2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd", None, 1000.0),
]


# ---------------------------------------------------------------- distortion

def undistort(x, y, c):
    xd, yd = x - c["x0"], y - c["y0"]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c["k"], start=1))
    T = 1 + c["p3"] * s + c["p4"] * s * s
    return (c["x0"] + xd * R + (c["p1"] * (s + 2 * xd * xd) + 2 * c["p2"] * xd * yd) * T,
            c["y0"] + yd * R + (2 * c["p1"] * xd * yd + c["p2"] * (s + 2 * yd * yd)) * T)


def jacobian(x, y, c):
    """d(undistorted)/d(distorted) at a raw screen point, as (a, b, cc, d) row-major."""
    xd, yd = x - c["x0"], y - c["y0"]
    k, p1, p2, p3, p4 = c["k"], c["p1"], c["p2"], c["p3"], c["p4"]
    s = xd * xd + yd * yd
    R = 1 + sum(kk * s ** i for i, kk in enumerate(k, start=1))
    Rp = sum(i * kk * s ** (i - 1) for i, kk in enumerate(k, start=1))
    T = 1 + p3 * s + p4 * s * s
    Tp = p3 + 2 * p4 * s
    Gx = p1 * (3 * xd * xd + yd * yd) + 2 * p2 * xd * yd
    Gy = 2 * p1 * xd * yd + p2 * (xd * xd + 3 * yd * yd)
    return (R + 2 * xd * xd * Rp + (6 * p1 * xd + 2 * p2 * yd) * T + 2 * xd * Gx * Tp,
            2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * yd * Gx * Tp,
            2 * xd * yd * Rp + (2 * p1 * yd + 2 * p2 * xd) * T + 2 * xd * Gy * Tp,
            R + 2 * yd * yd * Rp + (2 * p1 * xd + 6 * p2 * yd) * T + 2 * yd * Gy * Tp)


def apply3x3(m, x, y):
    w = m[2][0] * x + m[2][1] * y + m[2][2]
    return ((m[0][0] * x + m[0][1] * y + m[0][2]) / w,
            (m[1][0] * x + m[1][1] * y + m[1][2]) / w)


# ---------------------------------------------------------------- loading

def unarchive_matrix(blob):
    """A 3x3 row-major matrix stored as a keyed archive of nested NSArrays."""
    p = plistlib.loads(blob)
    objs = p["$objects"]

    def resolve(uid):
        o = objs[uid.data if hasattr(uid, "data") else int(uid)]
        if isinstance(o, dict) and "NS.objects" in o:
            return [resolve(u) for u in o["NS.objects"]]
        return o

    return resolve(p["$top"]["root"])


def load(path=DOC, typefilter="Length Tests"):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    clipname = dict(db.execute("SELECT Z_PK, ZCLIPNAME FROM ZVSVIDEOCLIP"))
    cals = {}
    for row in db.execute(
            "SELECT ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, ZDISTORTIONK1, "
            "ZDISTORTIONK2, ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, ZDISTORTIONK6, "
            "ZDISTORTIONK7, ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, ZDISTORTIONP4, "
            "ZAXISHORIZONTAL, ZAXISVERTICAL, ZPLANECOORDFRONT, ZPLANECOORDBACK, "
            "ZCAMERAX, ZCAMERAY, ZCAMERAZ, ZMATRIXSCREENTOQUADRATFRONT, "
            "ZMATRIXSCREENTOQUADRATBACK, ZMATRIXQUADRATFRONTTOSCREEN FROM ZVSCALIBRATION"):
        cals[row[0]] = {
            "name": clipname[row[0]], "x0": row[1], "y0": row[2], "k": list(row[3:10]),
            "p1": row[10], "p2": row[11], "p3": row[12], "p4": row[13],
            "ah": row[14], "av": row[15], "front": row[16], "back": row[17],
            "cam": (row[18], row[19], row[20]),
            "s2f": unarchive_matrix(row[21]), "s2b": unarchive_matrix(row[22]),
            "f2s": unarchive_matrix(row[23])}

    clicks = defaultdict(dict)
    cached = {}
    for pt, clip, x, y, fh, fv in db.execute(
            "SELECT ZPOINT, ZVIDEOCLIP, ZSCREENX, ZSCREENY, ZFRONTFRAMEWORLDH, "
            "ZFRONTFRAMEWORLDV FROM ZVSSCREENPOINT WHERE ZPOINT IS NOT NULL"):
        clicks[pt][clip] = (x, y)
        cached[(pt, clip)] = (fh, fv)

    events = defaultdict(list)
    names = {}
    sql = ("SELECT o.ZNAME2, t.ZNAME3, e.Z_PK, p.Z_PK FROM ZVSVISIBLEITEM e "
           "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
           "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
           "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
           "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK WHERE e.Z_ENT = 17")
    args = ()
    if typefilter:
        sql += " AND t.ZNAME3 = ?"
        args = (typefilter,)
    for name, tname, ev, pk in db.execute(sql + " ORDER BY e.Z_PK, p.ZINDEX", args):
        events[ev].append(pk)
        names[ev] = (name, tname)
    db.close()
    return cals, clicks, cached, events, names


def true_length_mm(name, tname, unit_mm):
    """True length in mm. A number embedded in the object name is authoritative -- the pool
    test's `48squares` type is really 47 squares, and trusting the type name invents a 9.4 mm
    bias larger than any effect being looked for."""
    m = re.search(r"([\d.]+)\s*cm", name or "")
    if m:
        return float(m.group(1)) * 10.0
    m = re.search(r"(\d+\.\d+)", name or "")
    if m:
        return float(m.group(1)) * unit_mm
    m = re.match(r"(\d+)squares", tname or "")
    if m:
        return int(m.group(1)) * 12.7
    return None


# ---------------------------------------------------------------- geometry

def lift(h, v, depth, c):
    """A 2D point on a calibration plane, plus that plane's depth, into 3D world coords."""
    ah, av = c["ah"], c["av"]
    if ah == "x":
        return (h, v, depth) if av == "y" else (h, depth, v)
    if ah == "y":
        return (v, h, depth) if av == "x" else (depth, h, v)
    return (v, depth, h) if av == "x" else (depth, v, h)


def drop(pt, c):
    """3D world point to the 2D (horizontal, vertical) pair the homography expects."""
    idx = {"x": 0, "y": 1, "z": 2}
    return pt[idx[c["ah"]]], pt[idx[c["av"]]]


def sightline(sx, sy, c):
    ux, uy = undistort(sx, sy, c)
    fh, fv = apply3x3(c["s2f"], ux, uy)
    bh, bv = apply3x3(c["s2b"], ux, uy)
    return lift(fh, fv, c["front"], c), lift(bh, bv, c["back"], c)


def cpa(lines):
    """Closest point of approach of two 3D lines."""
    (p1, q1), (p2, q2) = lines
    d1 = [q1[i] - p1[i] for i in range(3)]
    d2 = [q2[i] - p2[i] for i in range(3)]
    r = [p1[i] - p2[i] for i in range(3)]
    a = sum(x * x for x in d1)
    b = sum(x * y for x, y in zip(d1, d2))
    cc = sum(x * x for x in d2)
    d = sum(x * y for x, y in zip(d1, r))
    e = sum(x * y for x, y in zip(d2, r))
    den = a * cc - b * b
    if abs(den) < 1e-12:
        return None
    s = (b * e - cc * d) / den
    t = (a * e - b * d) / den
    return tuple(0.5 * ((p1[i] + s * d1[i]) + (p2[i] + t * d2[i])) for i in range(3))


def line_plane_intersect(a, b, depth, c):
    """Where the segment a->b crosses the plane at the given depth coordinate."""
    axis = {"x": 0, "y": 1, "z": 2}[({"x", "y", "z"} - {c["ah"], c["av"]}).pop()]
    da, db = a[axis] - depth, b[axis] - depth
    if abs(da - db) < 1e-15:
        return None
    t = da / (da - db)
    return tuple(a[i] + t * (b[i] - a[i]) for i in range(3))


def nelder_mead(f, x0, step=5.0, tol=1e-10, maxit=2000):
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (step if j == i else 0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(maxit):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol):
            break
        cen = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        ref = [cen[j] + (cen[j] - pts[-1][j]) for j in range(n)]
        fr = f(ref)
        if fr < vals[0]:
            exp = [cen[j] + 2 * (cen[j] - pts[-1][j]) for j in range(n)]
            fe = f(exp)
            pts[-1], vals[-1] = (exp, fe) if fe < fr else (ref, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = ref, fr
        else:
            con = [cen[j] + 0.5 * (pts[-1][j] - cen[j]) for j in range(n)]
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    i = min(range(n + 1), key=lambda i: vals[i])
    return pts[i]


def refine(obs, seed, weighted):
    """obs: list of (calibration, raw click). Minimize reprojection error to the front plane."""
    prepared = []
    for c, (sx, sy) in obs:
        u = undistort(sx, sy, c)
        if weighted:
            a, b, cc, d = jacobian(sx, sy, c)
            det = a * d - b * cc
            inv = (d / det, -b / det, -cc / det, a / det) if abs(det) > 1e-12 else (1, 0, 0, 1)
        else:
            inv = (1.0, 0.0, 0.0, 1.0)
        prepared.append((c, u, inv))

    def cost(p):
        total = 0.0
        for c, u, inv in prepared:
            hit = line_plane_intersect(p, c["cam"], c["front"], c)
            if hit is None:
                return 1e18
            rx, ry = apply3x3(c["f2s"], *drop(hit, c))
            ex, ey = rx - u[0], ry - u[1]
            wx = inv[0] * ex + inv[1] * ey
            wy = inv[2] * ex + inv[3] * ey
            total += wx * wx + wy * wy
        return total

    return nelder_mead(cost, seed)


# ---------------------------------------------------------------- run

def sign_test(wins, n):
    """Two-sided exact binomial p for `wins` successes in n paired trials under p = 1/2."""
    def choose(a, b):
        r = 1
        for i in range(b):
            r = r * (a - i) // (i + 1)
        return r
    k = min(wins, n - wins)
    tail = sum(choose(n, i) for i in range(k + 1))
    return min(1.0, 2.0 * tail / 2 ** n)


def run(label, path, typefilter, unit_mm):
    print(f"\n{'='*78}\n{label}\n{'='*78}")
    cals, clicks, cached, events, names = load(path, typefilter)

    # Self-check: the pipeline must reproduce the front-plane projections the app cached.
    err = [math.hypot(*(a - b for a, b in zip(
             apply3x3(cals[clip]["s2f"], *undistort(*clicks[pt][clip], cals[clip])), (fh, fv))))
           for (pt, clip), (fh, fv) in cached.items() if fh is not None and clip in cals]
    print(f"self-check vs the app's cached front-plane projections: max {max(err):.2e} "
          f"over {len(err)} clicks")
    mags = {}
    for clip, c in sorted(cals.items()):
        pts = [xy for d in clicks.values() for cl, xy in d.items() if cl == clip]
        m = [math.sqrt(abs(lambda_ := (j[0] * j[3] - j[1] * j[2])))
             for j in (jacobian(x, y, c) for x, y in pts)]
        mags[clip] = (sum(m) / len(m), max(m))
        print(f"  {c['name']:14s} undistortion magnification: mean "
              f"{mags[clip][0]:.3f}, max {mags[clip][1]:.3f}")

    rows = []
    for ev, pks in sorted(events.items()):
        if len(pks) != 2:
            continue
        true_len = true_length_mm(*names[ev], unit_mm)
        if true_len is None:
            continue
        got, ok = {}, True
        for method in ("linear", "current", "weighted"):
            pos = []
            for pk in pks:
                obs = [(cals[cl], xy) for cl, xy in sorted(clicks[pk].items()) if cl in cals]
                seed = cpa([sightline(xy[0], xy[1], c) for c, xy in obs]) if len(obs) >= 2 \
                    else None
                if seed is None:
                    ok = False
                    break
                pos.append(seed if method == "linear"
                           else refine(obs, seed, method == "weighted"))
            if not ok:
                break
            got[method] = math.dist(pos[0], pos[1]) * unit_mm
        if ok:
            rows.append({"name": names[ev][0], "true": true_len, **got})

    print(f"\n{len(rows)} measurements of known length\n")
    print(f"  {'method':>10} {'mean abs err':>14} {'rms err':>10} {'bias':>10} {'sd':>10}")
    for m in ("linear", "current", "weighted"):
        e = [r[m] - r["true"] for r in rows]
        n = len(e)
        mean = sum(e) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in e) / (n - 1))
        print(f"  {m:>10} {sum(abs(x) for x in e)/n:14.3f} "
              f"{math.sqrt(sum(x*x for x in e)/n):10.3f} {mean:10.3f} {sd:10.3f}")

    for a, b in (("weighted", "current"), ("linear", "current")):
        w = sum(1 for r in rows if abs(r[a] - r["true"]) < abs(r[b] - r["true"]))
        t = sum(1 for r in rows if abs(r[a] - r["true"]) == abs(r[b] - r["true"]))
        print(f"  {a} beats {b} on {w} of {len(rows) - t} non-tied "
              f"(sign test p = {sign_test(w, len(rows) - t):.3f})")
    return rows


def main():
    for label, path, tf, unit in DOCS:
        run(label, path, tf, unit)


if __name__ == "__main__":
    main()
