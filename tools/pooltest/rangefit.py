#!/usr/bin/env python3
"""Does the fitted distortion depend on how far away the calibration board was?

Reads the table produced by harvest.py. Every deployment used the same chessboard, so the cell
size in pixels is proportional to 1/Z: a bigger cell means the board was closer.

Two hazards, both handled here:

  * Duplicate rows. Calibrations get copied between documents, so the same fit appears several
    times. Deduplicated on the parameter vector, since a repeated fit is not new evidence.
  * Lens identity. Fitted severity varies far more between rigs than any range effect could
    explain, so a raw correlation across the whole folder measures which lens was on the camera,
    not where the board was. Handled by demeaning within (site, year, camera side): the rig is
    assumed stable within a field season, and only variation in board placement remains.
"""

import math
import statistics
import sys
from collections import defaultdict

NUM = {"npts", "nlines", "cell_near", "cell_p90", "cell_med", "cv", "rmax", "resid",
       "d200", "d400", "d600", "d800", "cal"}


def load(path):
    with open(path) as fh:
        head = fh.readline().rstrip("\n").split("\t")
        rows = []
        for ln in fh:
            if ln.startswith("#"):
                continue
            v = dict(zip(head, ln.rstrip("\n").split("\t")))
            for k in NUM:
                try:
                    v[k] = float(v[k])
                except (ValueError, KeyError):
                    v[k] = float("nan")
            rows.append(v)
    return rows


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
    """Slope of y on x, its t statistic, and n."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return float("nan"), float("nan"), n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = [y - a - b * x for x, y in zip(xs, ys)]
    if n <= 2:
        return b, float("nan"), n
    s2 = sum(r * r for r in resid) / (n - 2)
    se = math.sqrt(s2 / sxx)
    return b, (b / se if se > 0 else float("nan")), n


def main():
    rows = load(sys.argv[1] if len(sys.argv) > 1 else "/tmp/plumb.tsv")
    print(f"{len(rows)} (document, camera) calibrations harvested")

    # --- dedupe: a calibration copied into another document is not new evidence ---
    seen, uniq = {}, []
    for r in rows:
        key = (round(r["d200"], 6), round(r["d400"], 6), round(r["d800"], 6),
               round(r["cell_med"], 4), int(r["npts"]))
        if key in seen:
            seen[key].append(r["doc"])
            continue
        seen[key] = [r["doc"]]
        uniq.append(r)
    dups = sum(len(v) - 1 for v in seen.values())
    print(f"{dups} were copies of another document's fit; {len(uniq)} distinct fits remain")

    # Irregular point spacing means the line was not a detected chessboard lattice, so its
    # spacing is not a range proxy. Keep the regular ones.
    good = [r for r in uniq if r["cv"] < 0.20 and r["npts"] >= 150 and math.isfinite(r["cell_near"])]
    print(f"{len(good)} have regular lattice spacing (cv < 0.20) and >= 150 points\n")

    for r in good:
        parts = r["doc"].split()
        r["site"] = parts[-1]
        r["year"] = parts[0][:4]
        r["side"] = "R" if "Right" in r["clip"] else "L"
        r["group"] = f"{r['site']}-{r['year']}-{r['side']}"

    print("range of the board-distance proxy (median cell size, undistorted, r < 500 px)")
    cs = sorted(r["cell_near"] for r in good)
    print(f"  {cs[0]:.1f} to {cs[-1]:.1f} px  (a factor of {cs[-1]/cs[0]:.2f} in cell size, "
          f"so a factor of {cs[-1]/cs[0]:.2f} in 1/Z)")
    rm = sorted(r["rmax"] for r in good)
    print(f"  radial coverage is nearly constant: 95th-percentile radius {rm[0]:.0f} to "
          f"{rm[-1]:.0f} px, median {statistics.median(rm):.0f}")

    print("\n" + "=" * 76)
    print("RAW correlation across the whole folder (confounded by lens identity)")
    print("=" * 76)
    for m in ("d200", "d400", "d600", "d800"):
        print(f"  corr(cell size, {m}) = {corr([r['cell_near'] for r in good], [r[m] for r in good]):+.3f}")

    groups = defaultdict(list)
    for r in good:
        groups[r["group"]].append(r)
    usable = {g: v for g, v in groups.items() if len(v) >= 4}
    print(f"\ngroups (site-year-camera) with >= 4 distinct fits: {len(usable)} "
          f"covering {sum(len(v) for v in usable.values())} fits")
    for g, v in sorted(usable.items()):
        c = sorted(r["cell_near"] for r in v)
        print(f"  {g:22s} n={len(v):2d}  cell {c[0]:5.1f}-{c[-1]:5.1f} px   "
              f"d400 {min(r['d400'] for r in v):6.2f}-{max(r['d400'] for r in v):6.2f}")

    print("\n" + "=" * 76)
    print("WITHIN-GROUP (fixed effects): lens identity removed by demeaning each group")
    print("=" * 76)
    print("  a range-dependent distortion predicts a POSITIVE slope: closer board (bigger")
    print("  cell) means a larger 1/Z term baked into the fit")
    print(f"\n  {'metric':8s} {'slope (px per px of cell)':>26} {'t':>8} {'within-corr':>13}")
    for m in ("d200", "d400", "d600", "d800", "resid"):
        xs, ys = [], []
        for g, v in usable.items():
            mx = sum(r["cell_near"] for r in v) / len(v)
            my = sum(r[m] for r in v) / len(v)
            for r in v:
                xs.append(r["cell_near"] - mx)
                ys.append(r[m] - my)
        b, t, n = slope_t(xs, ys)
        print(f"  {m:8s} {b:26.4f} {t:8.2f} {corr(xs, ys):13.3f}")

    # Paired left/right within a document: both cameras saw the same board at slightly
    # different ranges, and differencing removes each document's shared conditions.
    print("\n" + "=" * 76)
    print("PAIRED left-vs-right within each document")
    print("=" * 76)
    bydoc = defaultdict(list)
    for r in good:
        bydoc[r["doc"]].append(r)
    dx, dy = [], []
    for d, v in bydoc.items():
        if len(v) != 2:
            continue
        a, b = (v[0], v[1]) if v[0]["side"] == "L" else (v[1], v[0])
        dx.append(a["cell_near"] - b["cell_near"])
        dy.append(a["d400"] - b["d400"])
    if len(dx) >= 5:
        sl, t, n = slope_t(dx, dy)
        print(f"  n = {n} documents with both cameras")
        print(f"  slope of (d400_L - d400_R) on (cell_L - cell_R) = {sl:+.4f}  (t = {t:+.2f})")
        print(f"  correlation = {corr(dx, dy):+.3f}")
        print("  the fixed lens difference between the two cameras is absorbed in the intercept")


if __name__ == "__main__":
    main()
