#!/usr/bin/env python3
"""Does a plumbline calibration depend on how far away the board was?

All the Drift Model deployments used the same chessboard, so the cell size in pixels is
proportional to 1/Z: a bigger cell means the board was closer. Two lenses were carried, an 8 mm
fisheye and a 10-17 mm zoom, so focal length comes from TrimmedVideoSiteDetails.csv and every
comparison is made within a focal length.

Two measurement traps are dealt with here.

*Severity is gauge-dependent.* Straightness is invariant under any homography applied after
undistortion, so a plumbline fit determines the distortion only up to that gauge. Uniform scale
about the distortion centre is the part of the gauge the Brown-Conrady series can most easily
absorb, and it is unconstrained by the data. The absolute radial displacement r*R(r^2) therefore
is not an estimate of anything: it mixes real distortion with an arbitrary scale the optimizer
happened to wander into. What bends lines, and what the data actually determines, is the
*departure of r_u(r) from proportionality*. That is what SEVERITY measures below.

*Cross-prediction needs no severity metric at all.* Apply calibration i's parameters to
calibration j's plumblines and measure how straight they come out. Straightness is precisely the
gauge-invariant quantity, so this comparison is clean. If distortion is range-dependent, a
calibration made with the board close should visibly fail to straighten lines from a session
where the board was far, and the failure should grow with the difference in board range.
"""

import csv
import glob
import math
import os
import re
import sqlite3
import statistics
import sys
from collections import defaultdict

FOLDER = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
SHEET = "/Users/jason/Downloads/TrimmedVideoSiteDetails.csv"

GRID = [float(r) for r in range(60, 861, 10)]   # fixed radii, so severities are comparable


# ------------------------------------------------------------------ distortion model

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


def severity(c, grid=GRID):
    """Rms departure of the radial map r -> r*R(r^2) from the best-fitting proportionality.

    Removing the best-fit scale removes the part of the model the plumbline objective cannot
    see. What remains is the curvature of the radial map, which is what actually bends a
    straight line, in pixels.
    """
    u = [r * (1.0 + sum(k * (r * r) ** i for i, k in enumerate(c["k"], start=1))) for r in grid]
    lam = sum(ui * r for ui, r in zip(u, grid)) / sum(r * r for r in grid)
    return math.sqrt(sum((ui - lam * r) ** 2 for ui, r in zip(u, grid)) / len(grid))


def line_res(pts):
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    sd = sum((p[0] - cx) ** 2 - (p[1] - cy) ** 2 for p in pts)
    th = 0.5 * math.atan2(2 * sxy, sd)
    ux, uy = math.cos(th), math.sin(th)
    return [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in pts]


def straightness(lines, c, rlimit=None, centre=None):
    """Rms straightness residual of these plumblines after undistortion by c.

    rlimit truncates to points inside a given image radius, measured from `centre` rather than
    from c's own distortion centre so that the identical point set is used whichever calibration
    is being tested. That is what makes the self/cross comparison fair: a board that filled the
    frame constrains its fit out to a larger radius, so without the truncation a cross-prediction
    would be measuring extrapolation rather than range.
    """
    res = []
    for pts in lines:
        if rlimit is not None:
            cx, cy = centre
            pts = [p for p in pts if math.hypot(p[0] - cx, p[1] - cy) <= rlimit]
        if len(pts) < 4:
            continue
        res += line_res([undistort(x, y, c) for x, y in pts])
    return math.sqrt(sum(r * r for r in res) / len(res)) if len(res) >= 30 else None


# ------------------------------------------------------------------ loading

def load_sheet():
    meta = {}
    with open(SHEET, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            meta[r["Code"].strip()] = {
                "stream": r["Study stream"].strip(),
                "focal": r["Focal length"].strip(),
                "borrow": r["Borrow source"].strip(),
                "framesep": r["Frame sep"].strip(),
                "quality": r["Quality"].strip()}
    return meta


def load_doc(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        clipname = dict(db.execute("SELECT Z_PK, ZCLIPNAME FROM ZVSVIDEOCLIP"))
        cals = {}
        for row in db.execute(
                "SELECT Z_PK, ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, "
                "ZDISTORTIONK1, ZDISTORTIONK2, ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, "
                "ZDISTORTIONK6, ZDISTORTIONK7, ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, "
                "ZDISTORTIONP4 FROM ZVSCALIBRATION"):
            if row[2] is None or row[4] is None:
                continue
            cals[row[0]] = {"clip": clipname.get(row[1], "?"), "x0": row[2], "y0": row[3],
                            "k": [v or 0.0 for v in row[4:11]], "p1": row[11] or 0.0,
                            "p2": row[12] or 0.0, "p3": row[13] or 0.0, "p4": row[14] or 0.0}
        lines = defaultdict(lambda: defaultdict(list))
        for cal, ln, x, y in db.execute(
                "SELECT l.ZCALIBRATION, l.Z_PK, p.ZSCREENX, p.ZSCREENY "
                "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK "
                "ORDER BY l.ZCALIBRATION, l.Z_PK, p.ZINDEX1"):
            if x is not None and y is not None:
                lines[cal][ln].append((x, y))
        return cals, lines
    finally:
        db.close()


def build():
    meta = load_sheet()
    recs = []
    for path in sorted(glob.glob(os.path.join(FOLDER, "*.vsd"))):
        doc = os.path.basename(path)[:-4]
        m = re.match(r"(\d{4}-\d{2}-\d{2}-\w+)\s+(.*)$", doc)
        if not m:
            continue
        code = m.group(1)
        info = meta.get(code)
        if info is None:
            continue
        try:
            cals, alllines = load_doc(path)
        except Exception as e:                              # noqa: BLE001
            print(f"# skip {doc}: {e}", file=sys.stderr)
            continue
        for pk, c in sorted(cals.items()):
            pls = [p for p in alllines.get(pk, {}).values() if len(p) >= 4]
            pts = [q for p in pls for q in p]
            if len(pts) < 150 or len(pls) < 8:
                continue
            sp, near = [], []
            for p in pls:
                u = [undistort(x, y, c) for x, y in p]
                for a, b in zip(u, u[1:]):
                    d = math.dist(a, b)
                    if not (1.0 < d < 400.0):
                        continue
                    sp.append(d)
                    mr = 0.5 * (math.hypot(a[0] - c["x0"], a[1] - c["y0"]) +
                                math.hypot(b[0] - c["x0"], b[1] - c["y0"]))
                    if mr < 500:
                        near.append(d)
            if len(near) < 15:
                continue
            cv = statistics.pstdev(sp) / statistics.mean(sp)
            if cv > 0.20:                                    # not a regular detected lattice
                continue
            radii = sorted(math.hypot(x - c["x0"], y - c["y0"]) for x, y in pts)
            recs.append({"doc": doc, "code": code, "date": code[:10],
                         "stream": info["stream"], "focal": info["focal"],
                         "borrow": info["borrow"], "framesep": info["framesep"],
                         "side": "R" if "Right" in c["clip"] else "L",
                         "cal": c, "lines": pls, "npts": len(pts),
                         "cell": statistics.median(near),
                         "rmax": radii[int(0.95 * (len(radii) - 1))],
                         "sev": severity(c),
                         "self": straightness(pls, c)})
    return recs


# ------------------------------------------------------------------ statistics

def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx > 0 and sy > 0 else float("nan")


def slope_t(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan"), float("nan"), n
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return float("nan"), float("nan"), n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    s2 = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / (n - 2)
    se = math.sqrt(s2 / sxx) if sxx > 0 else 0.0
    return b, (b / se if se > 0 else float("nan")), n


# ------------------------------------------------------------------ report

def main():
    recs = build()

    # Deduplicate: a borrowed calibration is the same fit, not new evidence.
    seen, uniq = set(), []
    for r in recs:
        key = tuple(round(v, 10) for v in r["cal"]["k"]) + (round(r["cal"]["x0"], 6),)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    print(f"{len(recs)} usable (document, camera) fits; {len(uniq)} distinct after removing "
          f"{len(recs)-len(uniq)} borrowed/duplicated calibrations")

    known = [r for r in uniq if r["focal"] in ("8", "10", "13", "17")]
    print(f"{len(known)} have a known focal length\n")

    print("distortion severity by focal length")
    print("  (rms departure of the radial map from proportionality, over r = 60-860 px;")
    print("   the scale-gauge the plumbline objective cannot see has been removed)")
    print(f"  {'focal':>6} {'n':>4} {'severity px: min':>17} {'median':>8} {'max':>8}"
          f" {'cell px: min':>14} {'max':>7}")
    byf = defaultdict(list)
    for r in known:
        byf[r["focal"]].append(r)
    for f in sorted(byf, key=int):
        v = byf[f]
        s = sorted(x["sev"] for x in v)
        c = sorted(x["cell"] for x in v)
        print(f"  {f+' mm':>6} {len(v):4d} {s[0]:17.2f} {statistics.median(s):8.2f} {s[-1]:8.2f}"
              f" {c[0]:14.1f} {c[-1]:7.1f}")

    print("\n" + "=" * 78)
    print("TEST 1  severity vs board distance, within focal length and camera side")
    print("=" * 78)
    print("  a 1/Z term in the distortion predicts a positive slope")
    print(f"  {'group':>16} {'n':>4} {'cell range':>14} {'corr':>8} {'slope':>10} {'t':>7}")
    xs_all, ys_all = [], []
    for f in sorted(byf, key=int):
        for side in ("L", "R"):
            v = [r for r in byf[f] if r["side"] == side]
            if len(v) < 4:
                continue
            xs = [r["cell"] for r in v]
            ys = [r["sev"] for r in v]
            b, t, n = slope_t(xs, ys)
            print(f"  {f+' mm '+side:>16} {n:4d} {min(xs):6.0f}-{max(xs):<7.0f} "
                  f"{corr(xs, ys):8.3f} {b:10.4f} {t:7.2f}")
            mx, my = sum(xs) / n, sum(ys) / n
            xs_all += [x - mx for x in xs]
            ys_all += [y - my for y in ys]
    b, t, n = slope_t(xs_all, ys_all)
    print(f"  {'POOLED':>16} {n:4d} {'':14} {corr(xs_all, ys_all):8.3f} {b:10.4f} {t:7.2f}")

    print("\n" + "=" * 78)
    print("TEST 2  cross-prediction: does a calibration transfer to a different board range?")
    print("=" * 78)
    print("  For every pair from the same focal length and camera side, apply one fit to the")
    print("  other's plumblines. Degradation = cross straightness - that session's own.")
    print("  Straightness is gauge-invariant, so no severity metric is involved.")
    pairs = []
    for f in byf:
        for side in ("L", "R"):
            v = [r for r in byf[f] if r["side"] == side]
            for i in v:
                for j in v:
                    if i is j:
                        continue
                    # Evaluate both fits on the same points, all inside the radius the donor's
                    # own board actually reached, so neither calibration is extrapolating.
                    lim = min(i["rmax"], j["rmax"])
                    ctr = (j["cal"]["x0"], j["cal"]["y0"])
                    own = straightness(j["lines"], j["cal"], lim, ctr)
                    cross = straightness(j["lines"], i["cal"], lim, ctr)
                    if own is None or cross is None:
                        continue
                    if not math.isfinite(cross) or cross > 200:
                        continue
                    pairs.append({"f": f, "side": side, "i": i, "j": j, "lim": lim,
                                  "dcell": abs(i["cell"] - j["cell"]),
                                  "sdcell": i["cell"] - j["cell"],
                                  "same_day": i["date"] == j["date"],
                                  "own": own, "cross": cross, "deg": cross - own})
    print(f"\n  {len(pairs)} ordered pairs")
    print(f"  {'|cell difference| (px)':>24} {'n':>5} {'median degradation (px)':>25}")
    for a, b2 in ((0, 5), (5, 15), (15, 30), (30, 50), (50, 1000)):
        s = [p for p in pairs if a <= p["dcell"] < b2]
        if len(s) < 5:
            continue
        print(f"  {f'{a}-{b2}':>24} {len(s):5d} "
              f"{statistics.median(p['deg'] for p in s):25.3f}")
    sl, t, n = slope_t([p["dcell"] for p in pairs], [p["deg"] for p in pairs])
    print(f"\n  slope of degradation on |cell difference| = {sl:+.4f} px/px  (t = {t:+.2f})")
    print(f"  correlation = {corr([p['dcell'] for p in pairs], [p['deg'] for p in pairs]):+.3f}")

    sd = [p for p in pairs if p["same_day"]]
    if sd:
        print(f"\n  restricted to the {len(sd)} same-day pairs (rig definitely not rebuilt):")
        sl, t, n = slope_t([p["dcell"] for p in sd], [p["deg"] for p in sd])
        print(f"    median degradation {statistics.median(p['deg'] for p in sd):+.3f} px; "
              f"slope on |cell difference| {sl:+.4f} (t = {t:+.2f})")
        print(f"    {'donor':>26} -> {'recipient':<26} {'lens':>5} {'dcell':>7} "
              f"{'own':>6} {'cross':>6}")
        for p in sorted(sd, key=lambda p: -p["dcell"]):
            print(f"    {p['i']['doc'][:26]:>26} -> {p['j']['doc'][:26]:<26} "
                  f"{p['f']+'mm '+p['side']:>5} {p['sdcell']:+7.1f} "
                  f"{p['own']:6.2f} {p['cross']:6.2f}")

    print("\n  A range-dependent distortion predicts degradation rising with |cell difference|")
    print("  and, in the signed version, an asymmetry. A range-independent one predicts")
    print("  degradation driven by rig differences alone, unrelated to board distance.")
    sl, t, n = slope_t([p["sdcell"] for p in pairs], [p["deg"] for p in pairs])
    print(f"  signed slope = {sl:+.4f} px/px (t = {t:+.2f})")


if __name__ == "__main__":
    main()
