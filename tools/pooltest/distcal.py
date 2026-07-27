#!/usr/bin/env python3
"""What does calibrating at the wrong board distance cost in millimetres?

The two-distance cross-fit shows a symmetric 0.45-0.48 px straightness penalty for transferring
the left camera's distortion fit between two board distances differing 1.35-fold. That is a pixel
number. This converts it into the units that matter by rebuilding the whole downstream calibration
under each distortion model and re-measuring the 14 known lengths.

For each of the near-set fit and the far-set fit: undistort the calibration frame's front and back
node clicks, refit both homographies by normalized DLT, re-estimate the camera position from the
back-node sightlines, then re-triangulate every length test.

Refraction correction of the back-plane node positions is *not* replicated here, so absolute
errors sit slightly above the document's own. That is deliberate and harmless: the quantity of
interest is the difference between two distortion models, and a common approximation cancels from
it. Only the right camera's calibration is held fixed, since only the left camera's distortion
differs between the exports.
"""

import math
import re
import sqlite3
from collections import defaultdict

VSD = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
       "2015-09-04-1 Clearwater.vsd")
EXPORTS = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/"
           "VidSync Projects/Exports")
FITS = [("near-set fit", "2015-09-04-1 Clearwater - NearDistortionSetOnly.xml"),
        ("far-set fit", "2015-09-04-1 Clearwater - FarDistortionSetOnly.xml"),
        ("both-set fit", "2015-09-04-1 Clearwater - BothDistortionSets.xml")]
KEYS = ["distortionCenterX", "distortionCenterY", "distortionK1", "distortionK2", "distortionK3",
        "distortionK4", "distortionK5", "distortionK6", "distortionK7", "distortionP1",
        "distortionP2", "distortionP3", "distortionP4"]


def undistort(x, y, c):
    xd, yd = x - c[0], y - c[1]
    s = xd * xd + yd * yd
    R = 1.0 + sum(k * s ** i for i, k in enumerate(c[2:9], start=1))
    T = 1 + c[11] * s + c[12] * s * s
    return (c[0] + xd * R + (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T,
            c[1] + yd * R + (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T)


def gauss(a, b):
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-18:
            return None
        m[col], m[piv] = m[piv], m[col]
        d = m[col][col]
        m[col] = [v / d for v in m[col]]
        for r in range(n):
            if r != col and m[r][col]:
                f = m[r][col]
                m[r] = [vr - f * vc for vr, vc in zip(m[r], m[col])]
    return [m[i][n] for i in range(n)]


def homography(src, dst):
    """Normalized DLT (Hartley & Zisserman alg. 4.2), h33 fixed to 1."""
    def norm(p):
        n = len(p)
        cx = sum(q[0] for q in p) / n
        cy = sum(q[1] for q in p) / n
        d = sum(math.hypot(q[0] - cx, q[1] - cy) for q in p) / n
        s = math.sqrt(2) / d if d else 1.0
        return [((q[0] - cx) * s, (q[1] - cy) * s) for q in p], (s, cx, cy)
    ns, ts = norm(src)
    nd, td = norm(dst)
    A, B = [], []
    for (u, v), (x, y) in zip(ns, nd):
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); B.append(x)
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y]); B.append(y)
    ata = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(8)] for i in range(8)]
    atb = [sum(A[r][i] * B[r] for r in range(len(A))) for i in range(8)]
    h = gauss(ata, atb)
    if h is None:
        return None
    H = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]]
    ss, scx, scy = ts
    ds, dcx, dcy = td
    Ts = [[ss, 0, -ss * scx], [0, ss, -ss * scy], [0, 0, 1]]
    Ti = [[1 / ds, 0, dcx], [0, 1 / ds, dcy], [0, 0, 1]]
    mul = lambda X, Y: [[sum(X[i][k] * Y[k][j] for k in range(3)) for j in range(3)]
                        for i in range(3)]
    return mul(Ti, mul(H, Ts))


def apply3(m, x, y):
    w = m[2][0] * x + m[2][1] * y + m[2][2]
    return ((m[0][0] * x + m[0][1] * y + m[0][2]) / w,
            (m[1][0] * x + m[1][1] * y + m[1][2]) / w)


def lift(h, v, depth, ah, av):
    if ah == "x":
        return (h, v, depth) if av == "y" else (h, depth, v)
    if ah == "y":
        return (v, h, depth) if av == "x" else (depth, h, v)
    return (v, depth, h) if av == "x" else (depth, v, h)


def drop(p, ah, av):
    i = {"x": 0, "y": 1, "z": 2}
    return p[i[ah]], p[i[av]]


def depth_axis(ah, av):
    return {"x": 0, "y": 1, "z": 2}[({"x", "y", "z"} - {ah, av}).pop()]


def build(cal, dist):
    """Rebuild homographies and camera position for one camera under one distortion model."""
    fs = [undistort(x, y, dist) for x, y, _, _ in cal["front"]]
    fw = [(h, v) for _, _, h, v in cal["front"]]
    bs = [undistort(x, y, dist) for x, y, _, _ in cal["back"]]
    bw = [(h, v) for _, _, h, v in cal["back"]]
    out = dict(cal)
    out["dist"] = dist
    out["s2f"] = homography(fs, fw)
    out["s2b"] = homography(bs, bw)
    out["f2s"] = homography(fw, fs)
    # Camera position from the back-node sightlines, as calculateCameraPosition does.
    lines = []
    for (x, y, _, _) in cal["back"]:
        lines.append(sightline(x, y, out))
    out["cam"], out["pld"] = intersect(lines)
    return out


def sightline(sx, sy, c):
    u = undistort(sx, sy, c["dist"])
    f = apply3(c["s2f"], *u)
    b = apply3(c["s2b"], *u)
    return (lift(f[0], f[1], c["front_d"], c["ah"], c["av"]),
            lift(b[0], b[1], c["back_d"], c["ah"], c["av"]))


def intersect(lines):
    """Least-squares point nearest a bundle of 3D lines, plus the mean point-line distance."""
    A = [[0.0] * 3 for _ in range(3)]
    bb = [0.0] * 3
    dirs = []
    for p, q in lines:
        d = [q[i] - p[i] for i in range(3)]
        L = math.sqrt(sum(v * v for v in d))
        if L == 0:
            continue
        d = [v / L for v in d]
        dirs.append((p, d))
        for i in range(3):
            for j in range(3):
                A[i][j] += (1.0 if i == j else 0.0) - d[i] * d[j]
            bb[i] += sum(((1.0 if i == j else 0.0) - d[i] * d[j]) * p[j] for j in range(3))
    P = gauss(A, bb)
    if P is None:
        return None, None
    tot = 0.0
    for p, d in dirs:
        w = [P[i] - p[i] for i in range(3)]
        t = sum(w[i] * d[i] for i in range(3))
        tot += math.sqrt(max(0.0, sum(v * v for v in w) - t * t))
    return tuple(P), tot / len(dirs)


def cpa(l1, l2):
    (p1, q1), (p2, q2) = l1, l2
    d1 = [q1[i] - p1[i] for i in range(3)]
    d2 = [q2[i] - p2[i] for i in range(3)]
    r = [p1[i] - p2[i] for i in range(3)]
    a = sum(v * v for v in d1)
    b = sum(u * v for u, v in zip(d1, d2))
    cc = sum(v * v for v in d2)
    d = sum(u * v for u, v in zip(d1, r))
    e = sum(u * v for u, v in zip(d2, r))
    den = a * cc - b * b
    if abs(den) < 1e-12:
        return None
    s = (b * e - cc * d) / den
    t = (a * e - b * d) / den
    return tuple(0.5 * ((p1[i] + s * d1[i]) + (p2[i] + t * d2[i])) for i in range(3))


def nm(f, x0, step=5.0, tol=1e-11, maxit=4000):
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (step if j == i else 0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(maxit):
        o = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in o]
        vals = [vals[i] for i in o]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol):
            break
        cen = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        ref = [cen[j] + (cen[j] - pts[-1][j]) for j in range(n)]
        fr = f(ref)
        if fr < vals[0]:
            ex = [cen[j] + 2 * (cen[j] - pts[-1][j]) for j in range(n)]
            fe = f(ex)
            pts[-1], vals[-1] = (ex, fe) if fe < fr else (ref, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = ref, fr
        else:
            co = [cen[j] + 0.5 * (pts[-1][j] - cen[j]) for j in range(n)]
            fc = f(co)
            if fc < vals[-1]:
                pts[-1], vals[-1] = co, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    return pts[min(range(n + 1), key=lambda i: vals[i])]


def refine(obs, seed):
    prep = []
    for c, (sx, sy) in obs:
        prep.append((c, undistort(sx, sy, c["dist"])))

    def cost(P):
        tot = 0.0
        for c, u in prep:
            ax = depth_axis(c["ah"], c["av"])
            da, dbq = P[ax] - c["front_d"], c["cam"][ax] - c["front_d"]
            if abs(da - dbq) < 1e-15:
                return 1e18
            t = da / (da - dbq)
            hit = tuple(P[i] + t * (c["cam"][i] - P[i]) for i in range(3))
            rx, ry = apply3(c["f2s"], *drop(hit, c["ah"], c["av"]))
            tot += (rx - u[0]) ** 2 + (ry - u[1]) ** 2
        return tot
    return nm(cost, seed)


def read_fit(path, clip):
    s = open(path, encoding="utf-8").read()
    i = s.find(f'<videoClip name="{clip}"')
    seg = s[i:i + 7000]
    return [float(re.search(k + r'="(-?[\d.eE+]+)"', seg).group(1)) for k in KEYS]


def main():
    db = sqlite3.connect(f"file:{VSD}?mode=ro", uri=True)
    cams = {}
    for pk, clip, ah, av, fd, bd, *dp in db.execute(
            "SELECT c.Z_PK, v.ZCLIPNAME, c.ZAXISHORIZONTAL, c.ZAXISVERTICAL, "
            "c.ZPLANECOORDFRONT, c.ZPLANECOORDBACK, c.ZDISTORTIONCENTERX, c.ZDISTORTIONCENTERY, "
            "c.ZDISTORTIONK1, c.ZDISTORTIONK2, c.ZDISTORTIONK3, c.ZDISTORTIONK4, "
            "c.ZDISTORTIONK5, c.ZDISTORTIONK6, c.ZDISTORTIONK7, c.ZDISTORTIONP1, "
            "c.ZDISTORTIONP2, c.ZDISTORTIONP3, c.ZDISTORTIONP4 FROM ZVSCALIBRATION c "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP"):
        cams[clip] = {"pk": pk, "clip": clip, "ah": ah, "av": av, "front_d": fd, "back_d": bd,
                      "stored": list(dp), "front": [], "back": []}
    bypk = {c["pk"]: c for c in cams.values()}
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION IS NOT NULL ORDER BY ZINDEX"):
        bypk[pk]["front"].append((x, y, h, v))
    for pk, x, y, h, v in db.execute(
            "SELECT ZCALIBRATION1, ZSCREENX, ZSCREENY, ZWORLDHCOORD, ZWORLDVCOORD "
            "FROM ZVSSCREENPOINT WHERE ZCALIBRATION1 IS NOT NULL ORDER BY ZINDEX"):
        bypk[pk]["back"].append((x, y, h, v))

    clicks = defaultdict(dict)
    for pt, clip, x, y in db.execute(
            "SELECT p.ZPOINT, v.ZCLIPNAME, p.ZSCREENX, p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        clicks[pt][clip] = (x, y)
    events = defaultdict(list)
    names = {}
    for name, ev, pk in db.execute(
            "SELECT o.ZNAME2, e.Z_PK, p.Z_PK FROM ZVSVISIBLEITEM e "
            "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
            "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
            "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
            "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK "
            "WHERE e.Z_ENT = 17 AND t.ZNAME3 = 'Length Tests' ORDER BY e.Z_PK, p.ZINDEX"):
        events[ev].append(pk)
        names[ev] = name
    db.close()

    print("=" * 80)
    print("Cost in millimetres of calibrating the left camera at the wrong board distance")
    print("=" * 80)
    for clip, c in cams.items():
        print(f"  {clip:14s} {len(c['front']):3d} front nodes, {len(c['back']):3d} back nodes, "
              f"planes {c['front_d']:.0f}/{c['back_d']:.0f}, axes {c['ah']}{c['av']}")

    right = build(cams["Right Camera"], cams["Right Camera"]["stored"])
    variants = {"document": cams["Left Camera"]["stored"]}
    for label, f in FITS:
        variants[label] = read_fit(f"{EXPORTS}/{f}", "Left Camera")

    print(f"\n  right camera rebuilt once and held fixed; its back-node PLD "
          f"{right['pld']:.3f} mm")

    results = {}
    for label, dist in variants.items():
        left = build(cams["Left Camera"], dist)
        rows = []
        for ev, pks in sorted(events.items()):
            if len(pks) != 2:
                continue
            m = re.match(r"([\d.]+)\s*cm", names[ev] or "")
            if not m:
                continue
            true = float(m.group(1)) * 10.0
            pos = []
            for pk in pks:
                obs = [(left, clicks[pk]["Left Camera"]), (right, clicks[pk]["Right Camera"])]
                seed = cpa(sightline(*obs[0][1], obs[0][0]), sightline(*obs[1][1], obs[1][0]))
                pos.append(refine(obs, seed))
            rows.append((names[ev], true, math.dist(pos[0], pos[1])))
        results[label] = rows
        e = [r[2] - r[1] for r in rows]
        n = len(e)
        mean = sum(e) / n
        print(f"\n  {label:14s} left-camera back-node PLD {left['pld']:6.3f} mm")
        print(f"                 n={n}  mean abs err {sum(abs(v) for v in e)/n:6.3f} mm  "
              f"rms {math.sqrt(sum(v*v for v in e)/n):6.3f}  bias {mean:+6.3f}")

    print("\n" + "=" * 80)
    print("PAIRED per-measurement difference, near-set fit vs far-set fit")
    print("=" * 80)
    a = {r[0] + f"{r[1]}": r[2] for r in results["near-set fit"]}
    print(f"  {'object':>10} {'true':>7} {'near fit':>10} {'far fit':>10} {'both fit':>10} "
          f"{'near-far':>10}")
    dif = []
    for i, r in enumerate(results["far-set fit"]):
        nv = results["near-set fit"][i][2]
        bv = results["both-set fit"][i][2]
        dif.append(nv - r[2])
        print(f"  {r[0]:>10} {r[1]:7.1f} {nv:10.2f} {r[2]:10.2f} {bv:10.2f} {nv - r[2]:+10.3f}")
    n = len(dif)
    md = sum(dif) / n
    sd = math.sqrt(sum((v - md) ** 2 for v in dif) / (n - 1))
    print(f"\n  mean difference {md:+.3f} mm, sd {sd:.3f}, max |difference| "
          f"{max(abs(v) for v in dif):.3f} mm")
    print(f"  against a measurement error of about "
          f"{sum(abs(r[2]-r[1]) for r in results['far-set fit'])/n:.2f} mm")
    print("\n  This is what the choice of calibration distance is worth, at this rig's working")
    print("  range. Compare it to the measurement error to judge whether it matters.")


if __name__ == "__main__":
    main()
