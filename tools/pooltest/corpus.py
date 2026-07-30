#!/usr/bin/env python3
"""THE corpus definition for the 2026-07-30 multi-document distortion round, and its inventory.

Everything before this round rested on three documents and six cameras: pool (mild), the 8 mm
fisheye (strong), and `mid` (intermediate). The addendum's own Scope section says the obvious thing
about that -- repeated fits of the same camera are not independent evidence. This module names a
wider corpus so that later scripts stop hard-coding paths.

WHAT THE CORPUS IS AND IS NOT

  It is a PLUMBLINE corpus. Eighteen documents, thirty-six cameras, four nominal focal lengths, each
  with its own separate calibration -- no document here borrows another's, checked against the
  `Calibration` and `Borrow source` columns of TrimmedVideoSiteDetails.csv.

  It is NOT a known-length corpus. Seventeen of the eighteen documents carry ZERO conventional
  measurements and ZERO point clouds; only `2015-06-22-1 Clearwater` has any (57), and that document
  was already in the harness as `mid`. So the one rule -- judge a change on the measurements, never
  on the calibration residual -- cannot be applied to the new documents at all. Any script that uses
  this corpus is measuring identifiability, stability and reproducibility, not physical accuracy.
  `has_ground_truth` records that distinction per document and must not be ignored.

FOCAL LENGTH IS METADATA, NOT MEASUREMENT. `focal_mm` comes from the operator's field CSV, which is
external to the .vsd; documents store no lens metadata (ZVSVIDEOCLIP has only clipName, fileName,
syncOffset and windowFrame). The 8 mm entries are a Rokinon fisheye prime, so that number is a lens
identity. The 10, 13 and 17 mm entries are zoom settings read off a lens barrel, so nominally equal
focal lengths are NOT guaranteed to be the same optical configuration. Treat within-focal-length
agreement as weak evidence in the 10/13/17 groups and strong evidence in the 8 mm group.

Run directly for the inventory report.
"""

import argparse
import json
import os
import sqlite3
import sys

import numpy as np

import harness_import

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
DEFAULT_DRIFT = os.path.join(HOME, "Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects")
DEFAULT_CHENA = os.path.join(HOME, "Library/CloudStorage/Dropbox/Chena Project Synced")
POOL_REL = "VidSync Projects/2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd"

LT = harness_import.load("lattice")

# (code, site, nominal focal length in mm). Focal lengths cross-checked against
# TrimmedVideoSiteDetails.csv; all eighteen have their own calibration, none borrows.
DRIFT_CORPUS = [
    ("2016-08-13-2", "Chena", 8),
    ("2016-08-08-4", "Panguingue", 8),
    ("2016-08-08-2", "Panguingue", 8),
    ("2016-08-07-1", "Panguingue", 8),
    ("2016-08-01-1", "Clearwater", 8),
    ("2015-07-17-1", "Panguingue", 10),
    ("2015-07-16-2", "Panguingue", 10),
    ("2015-07-15-1", "Panguingue", 10),
    ("2015-07-10-1", "Chena", 10),
    ("2015-06-12-1", "Chena", 10),
    ("2015-06-22-1", "Clearwater", 13),
    ("2015-06-22-2", "Clearwater", 13),
    ("2015-06-23-1", "Clearwater", 13),
    ("2016-08-02-2", "Clearwater", 17),
    ("2016-08-02-1", "Clearwater", 17),
    ("2016-07-07-1", "Clearwater", 17),
    ("2016-06-17-1", "Panguingue", 17),
    ("2016-06-11-1", "Clearwater", 17),
]

# Documents already established in the harness, carried so that a corpus-wide run can include the
# two anchors that DO have ground truth. `8mm` is not in the new list; `mid` is 2015-06-22-1.
LEGACY_8MM = ("2015-09-04-1", "Clearwater", 8)


def roots(drift_dir=None, chena_dir=None):
    drift = drift_dir or os.environ.get("VIDSYNC_DRIFT_PROJECTS") or DEFAULT_DRIFT
    chena = chena_dir or os.environ.get("VIDSYNC_CHENA_PROJECTS") or DEFAULT_CHENA
    return drift, chena


def documents(drift_dir=None, chena_dir=None, include_pool=True, include_legacy_8mm=True):
    """The corpus as records. `vsd` may not exist; `present` says whether it does."""
    drift, chena = roots(drift_dir, chena_dir)
    docs = []
    if include_pool:
        docs.append(dict(key="pool", code="2012-01-31", site="PoolTest", focal_mm=None,
                         role="anchor", vsd=os.path.join(chena, POOL_REL)))
    if include_legacy_8mm:
        code, site, f = LEGACY_8MM
        docs.append(dict(key="8mm", code=code, site=site, focal_mm=f, role="anchor",
                         vsd=os.path.join(drift, f"{code} {site}.vsd")))
    for code, site, f in DRIFT_CORPUS:
        docs.append(dict(key=f"{code}", code=code, site=site, focal_mm=f, role="corpus",
                         vsd=os.path.join(drift, f"{code} {site}.vsd")))
    for d in docs:
        d["label"] = f"{d['code']} {d['site']}" + (f" ({d['focal_mm']} mm)" if d["focal_mm"] else "")
        d["present"] = os.path.exists(d["vsd"])
    return docs


def clips_with_plumblines(vsd):
    """Clip names whose calibration owns at least one distortion line, in stored order."""
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT v.ZCLIPNAME, COUNT(l.Z_PK) FROM ZVSVIDEOCLIP v "
        "JOIN ZVSCALIBRATION c ON c.ZVIDEOCLIP = v.Z_PK "
        "LEFT JOIN ZVSDISTORTIONLINE l ON l.ZCALIBRATION = c.Z_PK "
        "GROUP BY v.Z_PK ORDER BY v.Z_PK").fetchall()
    db.close()
    return [(str(n), int(k)) for n, k in rows if k]


def _hull_fraction(xy):
    """Convex-hull area of the observations as a fraction of the 1920x1080 frame."""
    if len(xy) < 3:
        return 0.0
    from scipy.spatial import ConvexHull
    try:
        return float(ConvexHull(xy).volume / (LT.FRAME_W * LT.FRAME_H))
    except Exception:
        return 0.0


def camera_inventory(vsd, clip):
    """Lattice state for one camera, aggregated over its captures. No fitting."""
    caps = LT.load_captures(vsd, clip)
    xy = np.vstack([C.xy for C in caps]) if caps else np.zeros((0, 2))
    rec = dict(clip=clip, n_captures=len(caps), n_lines=0, stored_incidences=0,
               unique_observations=0, index_contradictions=0, dropped_nonunit_edges=0,
               n_components=0, reliably_indexed=0, doubly_constrained=0,
               hull_fraction=_hull_fraction(xy), captures=[])
    for C in caps:
        N, nc = C.notes, C.n_constraints()
        ok = C.indexed()
        both = int((ok & (nc >= 2)).sum())
        rec["n_lines"] += N["n_lines"]
        rec["stored_incidences"] += N["stored_incidences"]
        rec["unique_observations"] += N["unique_observations"]
        rec["index_contradictions"] += N["index_contradictions"]
        rec["dropped_nonunit_edges"] += N["dropped_nonunit_edges"]
        rec["n_components"] += N["n_components"]
        rec["reliably_indexed"] += int(N["reliably_indexed"])
        rec["doubly_constrained"] += both
        rec["captures"].append(dict(
            timecode=C.timecode, n_lines=N["n_lines"], unique=N["unique_observations"],
            contradictions=N["index_contradictions"], components=N["n_components"],
            reliably_indexed=int(N["reliably_indexed"]), doubly_constrained=both,
            hull_fraction=_hull_fraction(C.xy)))
    # PD-D needs consistently indexed, doubly constrained observations in every capture.
    rec["pdd_eligible"] = bool(caps) and all(
        c["contradictions"] == 0 and c["doubly_constrained"] >= 20 for c in rec["captures"])
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drift-dir", default=None)
    ap.add_argument("--chena-dir", default=None)
    ap.add_argument("--json", default=None, help="write the full inventory here")
    ap.add_argument("--no-pool", action="store_true")
    args = ap.parse_args()

    docs = documents(args.drift_dir, args.chena_dir, include_pool=not args.no_pool)
    print("=" * 108)
    print("CORPUS INVENTORY -- plumbline geometry only; no fitting, no ground truth used")
    print("=" * 108)

    missing = [d["label"] for d in docs if not d["present"]]
    if missing:
        print(f"  ABSENT, skipped and not inferred from: {', '.join(missing)}")

    out = []
    hdr = (f"  {'document':26} {'foc':>4} {'camera':14} {'caps':>4} {'lines':>6} {'uniq':>6} "
           f"{'contra':>6} {'indexed':>7} {'2-con':>6} {'hull':>6}  PD-D")
    print(hdr)
    print("  " + "-" * 104)
    for d in docs:
        if not d["present"]:
            continue
        rec = dict(d)
        rec["cameras"] = []
        for clip, nlines in clips_with_plumblines(d["vsd"]):
            cam = camera_inventory(d["vsd"], clip)
            rec["cameras"].append(cam)
            print(f"  {d['code'] + ' ' + d['site']:26} {str(d['focal_mm'] or '-'):>4} "
                  f"{clip[:14]:14} {cam['n_captures']:>4} {cam['n_lines']:>6} "
                  f"{cam['unique_observations']:>6} {cam['index_contradictions']:>6} "
                  f"{cam['reliably_indexed']:>7} {cam['doubly_constrained']:>6} "
                  f"{cam['hull_fraction']:>6.3f}  {'yes' if cam['pdd_eligible'] else 'NO'}")
        out.append(rec)

    print("\n  SUMMARY")
    cams = [c for r in out for c in r["cameras"]]
    print(f"    {len(out)} documents present, {len(cams)} cameras with plumblines")
    print(f"    PD-D eligible: {sum(1 for c in cams if c['pdd_eligible'])} of {len(cams)}")
    if cams:
        hf = np.array([c["hull_fraction"] for c in cams])
        di = np.array([c["doubly_constrained"] for c in cams])
        print(f"    frame coverage (convex hull / frame): min {hf.min():.3f}, median "
              f"{np.median(hf):.3f}, max {hf.max():.3f}")
        print(f"    doubly constrained indexed observations: min {int(di.min())}, median "
              f"{int(np.median(di))}, max {int(di.max())}")
    byf = {}
    for r in out:
        byf.setdefault(r["focal_mm"], []).append(r["code"])
    for f in sorted(byf, key=lambda z: (z is None, z)):
        print(f"    {str(f) + ' mm' if f else 'pool':>7}: {len(byf[f])} documents")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(dict(documents=out, missing=missing), fh, indent=1)
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
