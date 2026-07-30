#!/usr/bin/env python3
"""Spatial structure of the leftover plumbline residual: coherent, or noise?

The practical question is not how much residual is left but what kind. A spatially coherent
residual field biases reconstructed geometry systematically; white scatter of the same rms largely
averages out. And if the coherent part has a recognisable shape, that shape names the functional
form the model is missing.

Method. Every board corner appears in two plumblines, one from each family, and each line measures
the residual along its own normal. Pairing them recovers the full 2D residual vector at that corner.
Then three things are measured:

  * **Coherence** -- spatial autocorrelation of the residual vectors against separation. This is the
    part that answers the user's question directly, and it survives the line fitting.
  * **Direction** -- radial against tangential rms, by image radius.
  * **Angular structure** -- harmonic content of the radial component in polar angle, by radius
    band, which is what would name a missing basis function. m = 1 is decentring; m = 2 is the
    conic signature a decentred dome port produces and no radial model can represent.

An important limit on what this can show. The per-line total-least-squares fit removes a constant
and a linear trend from each line's residuals, so any smooth field is high-pass filtered along the
line directions before it is ever seen here. A global radial bias would be largely absorbed into the
line fits, which means a near-zero mean radial component is partly guaranteed by construction and is
*not* evidence that no such bias exists. What survives is curvature-scale structure. Coherence and
angular harmonics are read against that caveat.

Gauge is a smaller worry than usual here. A homography applied after undistortion scales the
existing residuals rather than adding a field of its own, so it modulates the reconstructed vectors
smoothly without changing their pattern of sign or direction.

Run with ~/.venvs/vidsync/bin/python.
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

import numpy as np

FOLDER = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
SHEET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TrimmedVideoSiteDetails.csv")
# Documents confirmed to have modern, verified plumbline detection.
MODERN = ["2016-08-13-2 Chena", "2015-09-04-1 Clearwater", "2016-08-07-1 Panguingue",
          "2016-07-07-2 Panguingue", "2016-08-08-2 Panguingue"]


def undistort(xy, c):
    xd = xy[:, 0] - c[0]
    yd = xy[:, 1] - c[1]
    s = xd * xd + yd * yd
    R = np.ones_like(s)
    sp = np.ones_like(s)
    for ki in c[2:9]:
        sp = sp * s
        R = R + ki * sp
    T = 1.0 + c[11] * s + c[12] * s * s
    dx = (c[9] * (s + 2 * xd * xd) + 2 * c[10] * xd * yd) * T
    dy = (2 * c[9] * xd * yd + c[10] * (s + 2 * yd * yd)) * T
    return np.stack([c[0] + xd * R + dx, c[1] + yd * R + dy], axis=1)


def tls(pts):
    """Unit direction and signed perpendicular residuals of a point set's best-fit line."""
    c = pts.mean(axis=0)
    q = pts - c
    sxy = float(q[:, 0] @ q[:, 1])
    sd = float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1])
    th = 0.5 * math.atan2(2 * sxy, sd)
    u = np.array([math.cos(th), math.sin(th)])
    res = -q[:, 0] * u[1] + q[:, 1] * u[0]
    return u, res


def focal_lengths():
    out = {}
    with open(SHEET, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            out[r["Code"].strip()] = r["Focal length"].strip()
    return out


def load_doc(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    clipname = dict(db.execute("SELECT Z_PK, ZCLIPNAME FROM ZVSVIDEOCLIP"))
    cals = {}
    for row in db.execute(
            "SELECT Z_PK, ZVIDEOCLIP, ZDISTORTIONCENTERX, ZDISTORTIONCENTERY, ZDISTORTIONK1, "
            "ZDISTORTIONK2, ZDISTORTIONK3, ZDISTORTIONK4, ZDISTORTIONK5, ZDISTORTIONK6, "
            "ZDISTORTIONK7, ZDISTORTIONP1, ZDISTORTIONP2, ZDISTORTIONP3, ZDISTORTIONP4 "
            "FROM ZVSCALIBRATION"):
        if row[2] is None or row[4] is None:
            continue
        cals[row[0]] = (clipname.get(row[1], "?"), [v or 0.0 for v in row[2:15]])
    lines = defaultdict(lambda: defaultdict(list))
    for cal, tc, ln, x, y in db.execute(
            "SELECT l.ZCALIBRATION, l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY "
            "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p ON p.ZDISTORTIONLINE = l.Z_PK "
            "ORDER BY l.ZCALIBRATION, l.ZTIMECODE, l.Z_PK, p.ZINDEX1"):
        if x is not None:
            lines[cal][(tc, ln)].append((x, y))
    db.close()
    return cals, lines


def corner_field(lineset, cal):
    """Reconstruct 2D residual vectors at corners shared by both line families."""
    L = {k: np.asarray(v, float) for k, v in lineset.items() if len(v) >= 4}
    if len(L) < 8:
        return None
    fits = {}
    for k, pts in L.items():
        u, res = tls(undistort(pts, cal))
        fits[k] = (u, res)
    angs = {k: math.degrees(math.atan2(f[0][1], f[0][0])) % 180 for k, f in fits.items()}
    ref = sorted(angs.values())[len(angs) // 2]
    fam = {k: 0 if min(abs(a - ref), 180 - abs(a - ref)) < 45 else 1 for k, a in angs.items()}

    index = {}
    for k, pts in L.items():
        if fam[k] != 0:
            continue
        for i, p in enumerate(pts):
            index[(round(p[0], 3), round(p[1], 3))] = (k, i)
    out = []
    for kb, pts in L.items():
        if fam[kb] != 1:
            continue
        for ib, p in enumerate(pts):
            hit = index.get((round(p[0], 3), round(p[1], 3)))
            if hit is None:
                continue
            ka, ia = hit
            ua, ub = fits[ka][0], fits[kb][0]
            na = np.array([-ua[1], ua[0]])
            nb = np.array([-ub[1], ub[0]])
            det = na[0] * nb[1] - na[1] * nb[0]
            if abs(det) < 0.25:
                continue
            ra, rb = fits[ka][1][ia], fits[kb][1][ib]
            ex = (ra * nb[1] - rb * na[1]) / det
            ey = (na[0] * rb - nb[0] * ra) / det
            out.append((p[0], p[1], ex, ey))
    return np.asarray(out) if len(out) >= 60 else None


def noise_floor(lineset):
    """Corner noise from the centred four-point stencil on evenly spaced runs, model-free."""
    vals = []
    for pts in lineset.values():
        q = np.asarray(pts, float)
        for i in range(len(q) - 3):
            w = q[i:i + 4]
            d = np.linalg.norm(np.diff(w, axis=0), axis=1)
            if d.min() <= 0 or (d.max() - d.min()) / d.min() > 0.05:
                continue
            v = w[3] - w[0]
            Ln = np.linalg.norm(v)
            if Ln == 0:
                continue
            n = np.array([-v[1], v[0]]) / Ln
            vals.append(float((w @ n) @ np.array([-1.0, 3.0, -3.0, 1.0])) / math.sqrt(20.0))
    return (float(np.sqrt(np.mean(np.square(vals)))), len(vals)) if vals else (float("nan"), 0)


def analyse(label, field, centre, noise):
    x, y, ex, ey = field[:, 0], field[:, 1], field[:, 2], field[:, 3]
    dx, dy = x - centre[0], y - centre[1]
    r = np.hypot(dx, dy)
    ok = r > 1e-6
    x, y, ex, ey, dx, dy, r = x[ok], y[ok], ex[ok], ey[ok], dx[ok], dy[ok], r[ok]
    rad = (ex * dx + ey * dy) / r
    tan = (-ex * dy + ey * dx) / r
    phi = np.arctan2(dy, dx)

    print(f"\n  {label}   n = {len(r)} corners, corner noise {noise:.3f} px")
    print(f"    {'radius':>11} {'n':>5} {'rms rad':>9} {'rms tan':>9} {'rad/tan':>8} "
          f"{'mean rad':>10}")
    for lo, hi in ((0, 300), (300, 500), (500, 700), (700, 900), (900, 1400)):
        m = (r >= lo) & (r < hi)
        if m.sum() < 12:
            continue
        rr = math.sqrt(float(np.mean(rad[m] ** 2)))
        tt = math.sqrt(float(np.mean(tan[m] ** 2)))
        se = noise / math.sqrt(m.sum())
        print(f"    {f'{lo}-{hi}':>11} {m.sum():5d} {rr:9.3f} {tt:9.3f} {rr/tt:8.2f} "
              f"{np.mean(rad[m]):+7.3f}+-{se:.3f}")

    # spatial coherence: how correlated are neighbouring corners' residual vectors?
    print(f"    spatial autocorrelation of the residual vector against separation:")
    idx = np.arange(len(r))
    pts = np.stack([x, y], axis=1)
    e = np.stack([ex, ey], axis=1)
    evar = float(np.mean((e * e).sum(axis=1)))
    line = []
    for lo, hi in ((0, 60), (60, 120), (120, 200), (200, 320), (320, 500), (500, 800)):
        num, cnt = 0.0, 0
        for i in idx[::2]:
            d = np.linalg.norm(pts - pts[i], axis=1)
            sel = (d >= lo) & (d < hi)
            if sel.any():
                num += float((e[sel] @ e[i]).sum())
                cnt += int(sel.sum())
        if cnt > 30:
            line.append(f"{lo}-{hi}px: {num/cnt/evar:+.2f}")
    print("      " + "   ".join(line))

    # angular harmonics of the radial component
    print(f"    angular harmonics of the radial component (amplitude px, +- {noise:.2f}/sqrt(n)):")
    for lo, hi in ((300, 700), (700, 1400)):
        m = (r >= lo) & (r < hi)
        if m.sum() < 30:
            continue
        se = noise * math.sqrt(2.0 / m.sum())
        amps = []
        for mm in (1, 2, 3):
            a = 2.0 * float(np.mean(rad[m] * np.cos(mm * phi[m])))
            b = 2.0 * float(np.mean(rad[m] * np.sin(mm * phi[m])))
            amp = math.hypot(a, b)
            ph = math.degrees(math.atan2(b, a))
            amps.append(f"m={mm}: {amp:5.3f} at {ph:+4.0f}deg ({amp/se:4.1f}sig)")
        print(f"      r {lo}-{hi}: " + "  ".join(amps))
    return rad, tan, r, phi


def main():
    fl = focal_lengths()
    for doc in MODERN:
        path = os.path.join(FOLDER, doc + ".vsd")
        if not os.path.exists(path):
            print(f"missing {doc}")
            continue
        code = doc.split()[0]
        cals, lines = load_doc(path)
        print("=" * 84)
        print(f"{doc}   focal length {fl.get(code, '?')} mm")
        print("=" * 84)
        for pk, (clip, cal) in sorted(cals.items()):
            ls = lines.get(pk, {})
            if not ls:
                continue
            fld = corner_field(ls, cal)
            if fld is None:
                print(f"  {clip}: too few paired corners")
                continue
            nf, nn = noise_floor(ls)
            analyse(clip, fld, (cal[0], cal[1]), nf)
    print("\n  rad/tan above 1 means the leftover points radially even where it is not radially")
    print("  symmetric. Autocorrelation near 1 at short separation means a coherent field rather")
    print("  than white noise. A significant m = 2 harmonic is the decentred-dome signature, which")
    print("  no radial model can represent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
