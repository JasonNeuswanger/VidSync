#!/usr/bin/env python3
"""THE authoritative loader for VidSync known-length annotations.

Two annotation families, both living in the shared ZVSVISIBLEITEM table (Z_ENT 17 events,
19 objects, 20 object types), with the object's type name in ZNAME3 and the object's own name in
ZNAME2.

CONVENTIONAL two-point measurements
  object type name : 'Length Tests'   (also 'Frame Test' in the 13 mm document)
  object name      : encodes the true length, e.g. '10 cm', '19.6 cm', '100 cm'
  points per event : exactly 2
  true length      : from the object name via jacweight.true_length_mm(); a number embedded in the
                     name is authoritative. See CALIBRATION_REFERENCE_NOTES.md for the
                     `48squares` trap in the pool-test document.

POINT-CLOUD annotations
  object type name : 'Length Point Cloud'
  object name      : 'Cloud A', 'Cloud B', ...
  points per event : exactly 1
  event ZNOTES     : comma-separated numeric local coordinates, no spaces, e.g. '10,0'
  dimensionality   : verified per cloud, NOT assumed. As of 2026-07-28 the fisheye document uses
                     TWO components.
  units            : CENTIMETRES in the notes; multiply by 10 for millimetres.
  scope            : coordinates are meaningful only WITHIN one cloud object. Absolute translation
                     and orientation between clouds are not supplied and must not be inferred.
                     NEVER build a distance between points of different clouds, even if their note
                     coordinates coincide.
  geometry         : each cloud is the front face of the physical calibration frame at one
                     placement, so all points in a cloud are coplanar.

Derived pairs: every unordered within-cloud pair (i, j) with i < j, exactly once. True length is the
Euclidean distance between the millimetre-converted note coordinates.

DEPENDENCE WARNING. A cloud of n points yields n(n-1)/2 distances that are NOT independent: each
point sits in n-1 pairs, so one badly clicked point corrupts n-1 distances. Pair count is not a
sample size. Use cloud-level and leave-one-point-out summaries; do not run independent-pair t-tests,
sign tests, or confidence intervals over pairs.

Reconstruction is the caller's job and must use the production-faithful pipeline (oracle.cpp for the
refractive calibration rebuild, parity.triangulate for endpoints). The front-face coplanarity of the
clouds is a property of the test data, not a licence to reconstruct them differently.

Run directly for a validation and exclusion report on a document.
"""

import importlib.util
import math
import os
import sqlite3
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
# The Drift Model documents name their two-point measurement types this way and store world
# coordinates in millimetres. The 2012 pool test uses per-length type names ("4squares", "12squares",
# "30squares", "48squares") and stores world coordinates in METRES, so both the accepted type set and
# the unit scale have to be stated per document rather than assumed. load() takes them as arguments;
# these remain the defaults so existing callers are unaffected.
CONVENTIONAL_TYPES = ("Length Tests", "Frame Test")
POOL_CONVENTIONAL_TYPES = ("4squares", "12squares", "30squares", "48squares")
CLOUD_TYPE = "Length Point Cloud"


def _jw():
    s = importlib.util.spec_from_file_location("jacweight", os.path.join(HERE, "jacweight.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def parse_note_coords(note):
    """'10,0' -> ([10.0, 0.0] cm, [100.0, 0.0] mm). Raises ValueError with a specific reason."""
    if note is None or not str(note).strip():
        raise ValueError("empty or missing note")
    parts = [p for p in str(note).strip().split(",")]
    if len(parts) < 2:
        raise ValueError(f"fewer than two comma-separated components: {note!r}")
    cm = []
    for p in parts:
        try:
            v = float(p.strip())
        except ValueError:
            raise ValueError(f"nonnumeric coordinate component {p!r} in {note!r}")
        if not math.isfinite(v):
            raise ValueError(f"nonfinite coordinate in {note!r}")
        cm.append(v)
    return cm, [10.0 * v for v in cm]


def load(vsd, clip_names=None, conventional_types=None, unit_mm=1.0):
    """Returns dict with keys 'conventional', 'cloud_points', 'cloud_pairs', 'exclusions',
    'clouds'. Nothing is silently dropped; every rejection lands in 'exclusions'.

    `conventional_types` is the set of object-type names holding two-point length measurements, and
    `unit_mm` converts that document's stored world unit to millimetres. Both default to the Drift
    Model convention; the 2012 pool test needs POOL_CONVENTIONAL_TYPES and unit_mm = 1000.0 because it
    stores metres. Passing these explicitly rather than hardcoding them is what lets one loader serve
    both, and getting unit_mm wrong silently rescales every true length by 1000."""
    jw = _jw()
    ctypes = CONVENTIONAL_TYPES if conventional_types is None else tuple(conventional_types)
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    if clip_names is None:
        clip_names = [r[0] for r in db.execute("SELECT ZCLIPNAME FROM ZVSVIDEOCLIP")]
    clicks = defaultdict(dict)
    for pt, cl, x, y in db.execute(
            "SELECT p.ZPOINT, v.ZCLIPNAME, p.ZSCREENX, p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK = p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        if x is None or y is None or not (math.isfinite(x) and math.isfinite(y)):
            continue
        clicks[pt][cl] = (float(x), float(y))
    rows = list(db.execute(
        "SELECT t.ZNAME3, o.ZNAME2, o.Z_PK, e.Z_PK, e.ZNOTES, p.Z_PK, p.ZINDEX, p.ZTIMECODE "
        "FROM ZVSVISIBLEITEM o JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
        "JOIN Z_17TRACKEDOBJECTS j ON j.Z_19TRACKEDOBJECTS = o.Z_PK "
        "JOIN ZVSVISIBLEITEM e ON e.Z_PK = j.Z_17TRACKEDEVENTS AND e.Z_ENT = 17 "
        "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK "
        "WHERE o.Z_ENT = 19 ORDER BY t.ZNAME3, o.ZNAME2, e.Z_PK, p.ZINDEX"))
    db.close()
    byev = defaultdict(list)
    info = {}
    for tn, on, opk, epk, notes, ppk, pidx, tc in rows:
        byev[epk].append((ppk, pidx))
        info[epk] = (tn, on, opk, notes, tc)

    exclusions, conventional, cloud_points = [], [], []
    for epk, pts in byev.items():
        tn, on, opk, notes, tc = info[epk]
        need = set(clip_names)
        if tn in ctypes:
            if len(pts) != 2:
                exclusions.append((tn, on, epk, f"conventional event has {len(pts)} points, not 2"))
                continue
            true = jw.true_length_mm(on, tn, unit_mm)
            if true is None:
                exclusions.append((tn, on, epk, "true length not encoded in object name"))
                continue
            miss = [pk for pk, _ in pts if not need.issubset(clicks.get(pk, {}))]
            if miss:
                exclusions.append((tn, on, epk, "missing a camera click on one or both endpoints"))
                continue
            conventional.append(dict(kind="conventional", type=tn, obj=on, obj_pk=opk, event=epk,
                                     tc=tc, true=true, pks=[pk for pk, _ in sorted(pts,
                                                                                   key=lambda z: z[1])]))
        elif tn == CLOUD_TYPE:
            if len(pts) != 1:
                exclusions.append((tn, on, epk, f"cloud event has {len(pts)} points, not 1"))
                continue
            try:
                cm, mm = parse_note_coords(notes)
            except ValueError as e:
                exclusions.append((tn, on, epk, str(e)))
                continue
            pk = pts[0][0]
            if not need.issubset(clicks.get(pk, {})):
                have = sorted(clicks.get(pk, {}))
                exclusions.append((tn, on, epk, f"cloud point clicked in {have} only"))
                continue
            cloud_points.append(dict(kind="cloud_point", type=tn, cloud=on, obj_pk=opk, event=epk,
                                     tc=tc, cm=cm, mm=mm, pk=pk))
    # per-cloud validation: dimensionality, duplicates, minimum size
    clouds = defaultdict(list)
    for r in cloud_points:
        clouds[r["cloud"]].append(r)
    keep_clouds = {}
    for cname, pts in sorted(clouds.items()):
        dims = {len(p["cm"]) for p in pts}
        if len(dims) > 1:
            for p in pts:
                exclusions.append((CLOUD_TYPE, cname, p["event"],
                                   f"inconsistent note dimensionality within cloud: {sorted(dims)}"))
            continue
        seen, uniq = {}, []
        for p in pts:
            key = tuple(p["mm"])
            if key in seen:
                exclusions.append((CLOUD_TYPE, cname, p["event"],
                                   f"duplicate note coordinate {p['cm']} (also event {seen[key]})"))
                continue
            seen[key] = p["event"]; uniq.append(p)
        if len(uniq) < 2:
            for p in uniq:
                exclusions.append((CLOUD_TYPE, cname, p["event"],
                                   "cloud has fewer than two valid points"))
            continue
        keep_clouds[cname] = uniq
    cloud_pairs = []
    for cname, pts in sorted(keep_clouds.items()):
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                a, b = pts[i], pts[j]
                assert a["cloud"] == b["cloud"], "cross-cloud pairing attempted"
                true = math.dist(a["mm"], b["mm"])
                if true <= 0:
                    exclusions.append((CLOUD_TYPE, cname, (a["event"], b["event"]),
                                       "zero true separation"))
                    continue
                cloud_pairs.append(dict(kind="cloud_pair", cloud=cname, tc=a["tc"],
                                        i=a["event"], j=b["event"], true=true,
                                        pks=[a["pk"], b["pk"]],
                                        mm_i=a["mm"], mm_j=b["mm"]))
    valid_points = [p for pts in keep_clouds.values() for p in pts]
    return dict(conventional=conventional, cloud_points=valid_points, cloud_pairs=cloud_pairs,
                clouds=keep_clouds, exclusions=exclusions, clicks=clicks)


def main():
    vsd = (sys.argv[1] if len(sys.argv) > 1 else
           "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
    d = load(vsd)
    print(f"document: {os.path.basename(vsd)}")
    print(f"\nCONVENTIONAL: {len(d['conventional'])} valid two-point measurements")
    byobj = defaultdict(int)
    for r in d["conventional"]:
        byobj[(r["type"], r["obj"], r["true"])] += 1
    for (tn, on, tl), n in sorted(byobj.items(), key=lambda z: z[0][2]):
        print(f"    {tn:14} {str(on):10} true {tl:8.1f} mm   n {n}")
    print(f"\nPOINT CLOUDS: {len(d['clouds'])} clouds, {len(d['cloud_points'])} valid points, "
          f"{len(d['cloud_pairs'])} derived pairs")
    for cname, pts in sorted(d["clouds"].items()):
        npair = sum(1 for p in d["cloud_pairs"] if p["cloud"] == cname)
        dim = len(pts[0]["cm"])
        tcs = sorted({p["tc"] for p in pts})
        tl = [p["true"] for p in d["cloud_pairs"] if p["cloud"] == cname]
        print(f"    {cname:9} {len(pts):3d} pts ({dim}D notes), {npair:4d} pairs, "
              f"{len(tcs)} timecode(s), true length {min(tl):.1f}-{max(tl):.1f} mm")
    print(f"\nEXCLUSIONS: {len(d['exclusions'])}")
    for e in d["exclusions"][:40]:
        print(f"    {e[0]:20} {str(e[1]):10} event {e[2]}  -> {e[3]}")
    if not d["exclusions"]:
        print("    none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
