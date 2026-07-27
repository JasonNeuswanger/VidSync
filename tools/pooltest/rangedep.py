#!/usr/bin/env python3
"""Does the effective distortion depend on the subject's range?

For an ideal central camera the answer is no: distortion is a function of the incoming ray's
field angle alone, and every point along a ray lands on the same pixel whatever its range. That
is the entire reason a pinhole-plus-radial-distortion model works.

Behind a flat port, or a dome whose entrance pupil is off the centre of curvature, the answer is
yes. Such a system is non-central -- rays do not share one viewpoint -- so the apparent bearing
of a point depends on its range as well as its direction, by roughly (viewpoint spread)/range.
The system's "radial distortion" is then a surface g(r, Z), not a curve g(r), and a calibration
performed at one range is wrong at every other.

The signature that separates the two, on data with known lengths: an *interaction* between image
radius and range. A range-independent distortion error produces a scale error that depends on
image radius the same way at every range. A range-dependent one produces a radius effect whose
size or sign changes with range.

The 2012 pool test is the right instrument: 688 measurements of one 50.8 mm target, spread over
300-2000 mm of range and over the whole frame, with the true length known exactly.
"""

import math
import re
import sqlite3
from collections import defaultdict

DOC = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
       "2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd")


def load():
    db = sqlite3.connect(DOC)
    centres = {clip: (cx, cy) for clip, cx, cy in db.execute(
        "SELECT ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY FROM ZVSCALIBRATION")}

    # screen clicks, keyed by the 3D point they belong to
    clicks = defaultdict(dict)
    for pt, clip, x, y in db.execute(
            "SELECT ZPOINT, ZVIDEOCLIP, ZSCREENX, ZSCREENY FROM ZVSSCREENPOINT "
            "WHERE ZPOINT IS NOT NULL"):
        clicks[pt][clip] = (x, y)

    events = defaultdict(lambda: {"pts": []})
    for name, tname, ev, pk, wx, wy, wz, dist in db.execute(
            "SELECT o.ZNAME2, t.ZNAME3, e.Z_PK, p.Z_PK, p.ZWORLDX, p.ZWORLDY, p.ZWORLDZ, "
            "       p.ZNEARESTCAMERADISTANCE "
            "FROM ZVSVISIBLEITEM e "
            "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
            "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
            "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
            "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK "
            "WHERE e.Z_ENT = 17 ORDER BY e.Z_PK, p.ZINDEX"):
        events[ev]["object"] = name
        events[ev]["type"] = tname
        events[ev]["pts"].append({"pk": pk, "w": (wx, wy, wz), "dist": dist})

    rows = []
    for ev, e in events.items():
        if len(e["pts"]) != 2:
            continue
        a, b = e["pts"]
        # A number embedded in the object's name is the authoritative true length, in metres:
        # the type names are unreliable (`48squares` is really 47 squares, 596.9 mm).
        m = re.search(r"(\d+\.\d+)", e["object"] or "")
        if m:
            true = float(m.group(1))
        else:
            n = re.match(r"(\d+)squares", e["type"] or "")
            if not n:
                continue
            true = int(n.group(1)) * 0.0127
        meas = math.dist(a["w"], b["w"])
        if a["dist"] is None or b["dist"] is None:
            continue
        rng = 0.5 * (a["dist"] + b["dist"])

        # mean image radius of the four clicks that produced this measurement
        radii, ok = [], True
        for p in (a, b):
            for clip, (cx, cy) in centres.items():
                c = clicks.get(p["pk"], {}).get(clip)
                if c is None:
                    ok = False
                    break
                radii.append(math.hypot(c[0] - cx, c[1] - cy))
        if not ok or not radii:
            continue
        rows.append({"object": e["object"], "true": true, "meas": meas,
                     "err": meas / true - 1.0, "range": rng,
                     "radius": sum(radii) / len(radii)})
    return rows


def corr(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx > 0 and sy > 0 else float("nan")


def ols(rows, cols):
    """Least squares of err on an intercept plus the named, mean-centred columns.
    Returns coefficients and their standard errors."""
    n = len(rows)
    means = {c: sum(r[c] for r in rows) / n for c in cols}
    A = [[1.0] + [r[c] - means[c] for c in cols] for r in rows]
    y = [r["err"] for r in rows]
    k = len(cols) + 1
    ata = [[sum(A[t][i] * A[t][j] for t in range(n)) for j in range(k)] for i in range(k)]
    atb = [sum(A[t][i] * y[t] for t in range(n)) for i in range(k)]

    # solve and invert together via Gauss-Jordan on the augmented system
    m = [ata[i][:] + [1.0 if i == j else 0.0 for j in range(k)] + [atb[i]] for i in range(k)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-30:
            return None
        m[c], m[piv] = m[piv], m[c]
        d = m[c][c]
        m[c] = [v / d for v in m[c]]
        for r in range(k):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [vr - f * vc for vr, vc in zip(m[r], m[c])]
    beta = [m[i][2 * k] for i in range(k)]
    inv = [[m[i][k + j] for j in range(k)] for i in range(k)]
    resid = [y[t] - sum(A[t][i] * beta[i] for i in range(k)) for t in range(n)]
    s2 = sum(r * r for r in resid) / (n - k)
    se = [math.sqrt(s2 * inv[i][i]) for i in range(k)]
    return beta, se


def main():
    rows = load()
    print(f"{len(rows)} measurements with range and screen positions\n")

    # The single-length subset holds target size exactly constant, so nothing here can be a
    # length confound.
    sub = [r for r in rows if abs(r["true"] - 0.0508) < 1e-9]
    print(f"{'='*78}\n50.8 mm target only: n = {len(sub)}\n{'='*78}")
    print(f"  corr(scale error, range)  = {corr([r['range'] for r in sub], [r['err'] for r in sub]):+.3f}")
    print(f"  corr(scale error, radius) = {corr([r['radius'] for r in sub], [r['err'] for r in sub]):+.3f}")
    print(f"  corr(range, radius)       = {corr([r['range'] for r in sub], [r['radius'] for r in sub]):+.3f}"
          "   <- how badly the two are confounded")

    print("\n  mean scale error (%) by range x image radius")
    rq = sorted(r["radius"] for r in sub)
    rcuts = [rq[len(rq) * i // 3] for i in (1, 2)]
    print(f"  radius terciles split at {rcuts[0]:.0f} and {rcuts[1]:.0f} px")
    print(f"  {'range (mm)':>14} {'n':>5} {'centre':>9} {'middle':>9} {'edge':>9}")
    for a, b in ((0, 500), (500, 700), (700, 900), (900, 1300), (1300, 1800), (1800, 9999)):
        band = [r for r in sub if a <= r["range"] * 1000 < b]
        if len(band) < 12:
            continue
        cells = []
        for lo, hi in ((0, rcuts[0]), (rcuts[0], rcuts[1]), (rcuts[1], 1e9)):
            c = [r["err"] for r in band if lo <= r["radius"] < hi]
            cells.append(f"{100*sum(c)/len(c):+7.3f}({len(c)})" if len(c) >= 4 else "     -   ")
        print(f"  {a:5d}-{b:<8d} {len(band):5d} " + " ".join(f"{c:>9}" for c in cells))

    print("\n  regression of scale error on range, image radius, and their interaction")
    for cols in (["range"], ["range", "radius"], ["range", "radius", "rxr"]):
        rs = [dict(r) for r in sub]
        for r in rs:
            r["rxr"] = r["range"] * r["radius"]
        out = ols(rs, cols)
        if out is None:
            continue
        beta, se = out
        parts = []
        for name, bv, sv in zip(cols, beta[1:], se[1:]):
            parts.append(f"{name} {bv:+.3e} (t={bv/sv:+.2f})")
        print("    " + ";  ".join(parts))

    print("\n" + "=" * 78)
    print("all 1010 measurements")
    print("=" * 78)
    for cols in (["range", "radius", "rxr"],):
        rs = [dict(r) for r in rows]
        for r in rs:
            r["rxr"] = r["range"] * r["radius"]
        beta, se = ols(rs, cols)
        for name, bv, sv in zip(cols, beta[1:], se[1:]):
            print(f"    {name:8s} {bv:+.3e}  (t = {bv/sv:+.2f})")


if __name__ == "__main__":
    main()
