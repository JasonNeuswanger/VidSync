#!/usr/bin/env python3
"""Parser and validation tests for knownlength.py, THE authoritative known-length loader.

Two halves. The first builds synthetic single-file Core Data stores in a temp directory, so every
rejection path can be exercised deliberately rather than hoped for. The second runs against the real
`2015-09-04-1 Clearwater.vsd` and checks the properties that make the expanded analysis trustworthy:
that the loader still reproduces the ORIGINAL 14-measurement subset the earlier fisheye conclusions
were built on, that repeated note coordinates in different clouds stay separate, and that no pair
ever crosses a cloud boundary.

Counts from the real document are checked as PROVENANCE, not as schema requirements: a count
assertion that would fail when a valid annotation is added is a bug in the test, so those checks
assert monotone lower bounds and exact agreement with independently recomputed values instead.

Plain Python 3, no venv needed.
"""

import importlib.util
import math
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")

# Provenance snapshot, 2026-07-28, AFTER the Cloud D repair (two mis-placed/mis-labelled points
# corrected and two added, 16 -> 18 points). Lower bounds, so adding valid annotations later cannot
# fail the test.
SNAPSHOT = {"conventional": 42, "clouds": 4, "cloud_points": 65, "cloud_pairs": 504}
# The 14 conventional measurements analysed before the expansion, identified by event primary key.
# Verified independently: these and only these reproduce the historical stored MAE of 2.9712 mm.
ORIGINAL_14 = [184, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 201]
ORIGINAL_14_STORED_MAE = 2.9712

_results = []


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


kl = L("knownlength")


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


def raises(name, fn, needle):
    """The reason string is part of the contract: exclusions must say WHY."""
    try:
        fn()
    except ValueError as e:
        check(name, needle in str(e), f"{str(e)[:70]!r}")
        return
    check(name, False, "no ValueError raised")


# --------------------------------------------------------------- synthetic store construction

SCHEMA = """
CREATE TABLE ZVSVIDEOCLIP (Z_PK INTEGER PRIMARY KEY, ZCLIPNAME TEXT);
CREATE TABLE ZVSVISIBLEITEM (Z_PK INTEGER PRIMARY KEY, Z_ENT INTEGER, ZNAME2 TEXT, ZNAME3 TEXT,
                             ZTYPE1 INTEGER, ZNOTES TEXT);
CREATE TABLE Z_17TRACKEDOBJECTS (Z_17TRACKEDEVENTS INTEGER, Z_19TRACKEDOBJECTS INTEGER);
CREATE TABLE ZVSPOINT3D (Z_PK INTEGER PRIMARY KEY, ZTRACKEDEVENT INTEGER, ZINDEX INTEGER,
                         ZTIMECODE TEXT);
CREATE TABLE ZVSSCREENPOINT (Z_PK INTEGER PRIMARY KEY, ZPOINT INTEGER, ZVIDEOCLIP INTEGER,
                             ZSCREENX REAL, ZSCREENY REAL);
"""


class Store:
    """Minimal writer for the subset of the Core Data schema knownlength.load() reads.

    Entity codes are production's: 17 events, 19 objects, 20 object types. The object's own name is
    ZNAME2 and its type's name is ZNAME3, because the shared table gives each entity's `name`
    attribute its own column.
    """

    def __init__(self, path, clips=("Left Camera", "Right Camera")):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.clips = list(clips)
        for i, c in enumerate(self.clips, start=1):
            self.db.execute("INSERT INTO ZVSVIDEOCLIP VALUES (?,?)", (i, c))
        self._pk = 1000
        self.types, self.objects = {}, {}

    def _next(self):
        self._pk += 1
        return self._pk

    def obj(self, type_name, obj_name):
        if type_name not in self.types:
            pk = self._next()
            self.db.execute("INSERT INTO ZVSVISIBLEITEM VALUES (?,20,NULL,?,NULL,NULL)",
                            (pk, type_name))
            self.types[type_name] = pk
        key = (type_name, obj_name)
        if key not in self.objects:
            pk = self._next()
            self.db.execute("INSERT INTO ZVSVISIBLEITEM VALUES (?,19,?,NULL,?,NULL)",
                            (pk, obj_name, self.types[type_name]))
            self.objects[key] = pk
        return self.objects[key]

    def event(self, type_name, obj_name, npoints, notes=None, tc="0:00:00:00.0/30",
              clicked=None, screen=None):
        """clicked=None means every point is clicked in every clip. Returns (event_pk, [point_pks])."""
        opk = self.obj(type_name, obj_name)
        epk = self._next()
        self.db.execute("INSERT INTO ZVSVISIBLEITEM VALUES (?,17,NULL,NULL,NULL,?)", (epk, notes))
        self.db.execute("INSERT INTO Z_17TRACKEDOBJECTS VALUES (?,?)", (epk, opk))
        pks = []
        for i in range(npoints):
            ppk = self._next()
            self.db.execute("INSERT INTO ZVSPOINT3D VALUES (?,?,?,?)", (ppk, epk, i, tc))
            pks.append(ppk)
            for c in (self.clips if clicked is None else clicked):
                x, y = (100.0 + 10 * i, 200.0 + 10 * i) if screen is None else screen
                self.db.execute("INSERT INTO ZVSSCREENPOINT VALUES (?,?,?,?,?)",
                                (self._next(), ppk, self.clips.index(c) + 1, x, y))
        return epk, pks

    def close(self):
        self.db.commit(); self.db.close()


def reasons(d, event_pk):
    return [e[3] for e in d["exclusions"] if e[2] == event_pk
            or (isinstance(e[2], tuple) and event_pk in e[2])]


# ------------------------------------------------------------------------------- unit tests

def test_conventional_true_length():
    print("\n1. Conventional true-length parsing (a number in the object name is authoritative)")
    jw = kl._jw()
    for name, want in (("10 cm", 100.0), ("19.6 cm", 196.0), ("30 cm", 300.0),
                       ("50 cm", 500.0), ("100 cm", 1000.0), ("  30 cm  ", 300.0)):
        got = jw.true_length_mm(name, "Length Tests", 1.0)
        check(f"'{name}' -> {want} mm", got == want, f"got {got}")
    check("name with no length -> None",
          jw.true_length_mm("Cloud A", "Length Point Cloud", 1.0) is None)
    # The 48squares trap: the type name lies, the object name does not.
    check("pool-test 48squares trap: object name beats type name",
          jw.true_length_mm("Full Width 0.5969", "48squares", 1000.0) == 596.9,
          f"got {jw.true_length_mm('Full Width 0.5969', '48squares', 1000.0)}")


def test_note_parsing():
    print("\n2. Note-coordinate parsing, cm->mm conversion, and dimensionality")
    for note, cm, mm in (("10,0", [10.0, 0.0], [100.0, 0.0]),
                         ("0,0", [0.0, 0.0], [0.0, 0.0]),
                         ("100,50", [100.0, 50.0], [1000.0, 500.0]),
                         ("-7.5,2.25", [-7.5, 2.25], [-75.0, 22.5]),
                         (" 10 , 0 ", [10.0, 0.0], [100.0, 0.0])):
        gc, gm = kl.parse_note_coords(note)
        check(f"{note!r} -> {cm} cm", gc == cm, f"got {gc}")
        check(f"{note!r} -> {mm} mm  (x10 exactly)", gm == mm, f"got {gm}")
    gc, gm = kl.parse_note_coords("1,2,3")
    check("three components accepted, dimensionality not hard-coded to 2", gc == [1.0, 2.0, 3.0])
    check("three components convert componentwise", gm == [10.0, 20.0, 30.0])
    # exactness matters: 0.1 cm must not become 0.9999999999999999 mm
    check("conversion is exact for a decimal cm value",
          kl.parse_note_coords("0.7,0")[1][0] == 7.0, f"got {kl.parse_note_coords('0.7,0')[1][0]}")

    print("\n3. Malformed and missing notes are rejected with a specific reason")
    raises("None note", lambda: kl.parse_note_coords(None), "empty or missing")
    raises("empty note", lambda: kl.parse_note_coords(""), "empty or missing")
    raises("whitespace-only note", lambda: kl.parse_note_coords("   "), "empty or missing")
    raises("single component", lambda: kl.parse_note_coords("10"), "fewer than two")
    raises("nonnumeric component", lambda: kl.parse_note_coords("10,abc"), "nonnumeric")
    raises("empty component", lambda: kl.parse_note_coords("10,"), "nonnumeric")
    raises("nonfinite component", lambda: kl.parse_note_coords("10,inf"), "nonfinite")
    raises("nan component", lambda: kl.parse_note_coords("nan,0"), "nonfinite")


def test_pair_construction(tmp):
    print("\n4. Pair construction: unordered i<j, once each, never across clouds")
    p = os.path.join(tmp, "pairs.vsd")
    s = Store(p)
    # Cloud A and Cloud B deliberately SHARE note coordinates, including the (0,0) origin every
    # cloud starts from. If scope were ignored these would generate spurious zero-length pairs.
    for xy in ("0,0", "10,0", "0,10"):
        s.event("Length Point Cloud", "Cloud A", 1, notes=xy, tc="tcA")
    for xy in ("0,0", "10,0", "0,10", "30,40"):
        s.event("Length Point Cloud", "Cloud B", 1, notes=xy, tc="tcB")
    s.close()
    d = kl.load(p)
    byc = {c: [q for q in d["cloud_pairs"] if q["cloud"] == c] for c in ("Cloud A", "Cloud B")}
    check("Cloud A: 3 points -> 3 pairs", len(byc["Cloud A"]) == 3, f"got {len(byc['Cloud A'])}")
    check("Cloud B: 4 points -> 6 pairs", len(byc["Cloud B"]) == 6, f"got {len(byc['Cloud B'])}")
    check("total pairs = sum of within-cloud pairs, no cross-cloud pairs",
          len(d["cloud_pairs"]) == 9, f"got {len(d['cloud_pairs'])}")
    ev2c = {q["event"]: q["cloud"] for q in d["cloud_points"]}
    check("every pair's two endpoints belong to the same cloud",
          all(ev2c[q["i"]] == ev2c[q["j"]] == q["cloud"] for q in d["cloud_pairs"]))
    # unordered and unique
    keys = [frozenset((q["i"], q["j"])) for q in d["cloud_pairs"]]
    check("no pair repeated in the other order", len(keys) == len(set(keys)))
    check("no self-pair", all(q["i"] != q["j"] for q in d["cloud_pairs"]))
    check("no zero-length pair survived (would signal cross-cloud leakage)",
          all(q["true"] > 0 for q in d["cloud_pairs"]))
    # true lengths in mm from cm notes
    tl = sorted(round(q["true"], 6) for q in byc["Cloud A"])
    want = sorted([100.0, 100.0, round(math.hypot(100.0, 100.0), 6)])
    check("Cloud A true lengths are mm distances of the x10 coordinates", tl == want, f"got {tl}")
    check("Cloud B has a 500 mm pair from (0,0)-(30,40) cm",
          any(abs(q["true"] - 500.0) < 1e-9 for q in byc["Cloud B"]))

    print("\n5. Repeated coordinates in DIFFERENT clouds stay separate")
    shared = [q for q in d["cloud_points"] if q["mm"] == [0.0, 0.0]]
    check("the (0,0) origin appears once per cloud and is not deduplicated globally",
          len(shared) == 2 and {q["cloud"] for q in shared} == {"Cloud A", "Cloud B"},
          f"got {[(q['cloud'], q['mm']) for q in shared]}")
    check("sharing coordinates produced no exclusion", len(d["exclusions"]) == 0,
          f"{d['exclusions']}")


def test_rejections(tmp):
    print("\n6. Duplicate coordinates WITHIN a cloud, bad point counts, missing clicks")
    p = os.path.join(tmp, "reject.vsd")
    s = Store(p)
    e_dup_a, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="5,5", tc="tcA")
    e_dup_b, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="5,5", tc="tcA")
    e_zero, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="0,0", tc="tcA")
    e_two, _ = s.event("Length Point Cloud", "Cloud A", 2, notes="9,9", tc="tcA")
    e_bad, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="oops,x", tc="tcA")
    e_1d, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="7", tc="tcA")
    e_nonote, _ = s.event("Length Point Cloud", "Cloud A", 1, notes=None, tc="tcA")
    e_1cam, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="1,1", tc="tcA",
                        clicked=["Left Camera"])
    e_lone, _ = s.event("Length Point Cloud", "Cloud Z", 1, notes="0,0", tc="tcZ")
    e_c1, _ = s.event("Length Tests", "30 cm", 1, tc="tcL")
    e_c3, _ = s.event("Length Tests", "30 cm", 3, tc="tcL")
    e_cok, _ = s.event("Length Tests", "30 cm", 2, tc="tcL")
    e_cnl, _ = s.event("Length Tests", "Mystery Object", 2, tc="tcL")
    e_cmiss, _ = s.event("Length Tests", "30 cm", 2, tc="tcL", clicked=["Right Camera"])
    s.close()
    d = kl.load(p)

    def has(pk, needle):
        return any(needle in r for r in reasons(d, pk))

    check("duplicate coordinate within a cloud is excluded, keeping the first",
          has(e_dup_b, "duplicate note coordinate") and not has(e_dup_a, "duplicate"))
    check("the duplicate's reason names the event it duplicates",
          any(f"event {e_dup_a}" in r for r in reasons(d, e_dup_b)),
          f"{reasons(d, e_dup_b)}")
    check("cloud event with 2 points is excluded", has(e_two, "not 1"), f"{reasons(d, e_two)}")
    check("nonnumeric note component is excluded through load()",
          has(e_bad, "nonnumeric"), f"{reasons(d, e_bad)}")
    check("one-component note is excluded through load()",
          has(e_1d, "fewer than two"), f"{reasons(d, e_1d)}")
    check("missing note is excluded through load()",
          has(e_nonote, "empty or missing"), f"{reasons(d, e_nonote)}")
    check("cloud point clicked in only one camera is excluded",
          has(e_1cam, "clicked in"), f"{reasons(d, e_1cam)}")
    check("the missing-click reason lists which cameras were found",
          any("Left Camera" in r for r in reasons(d, e_1cam)), f"{reasons(d, e_1cam)}")
    check("a cloud with fewer than two valid points is dropped",
          "Cloud Z" not in d["clouds"] and has(e_lone, "fewer than two"))
    check("conventional event with 1 point is excluded", has(e_c1, "not 2"), f"{reasons(d, e_c1)}")
    check("conventional event with 3 points is excluded", has(e_c3, "not 2"), f"{reasons(d, e_c3)}")
    check("conventional event whose name lacks a length is excluded",
          has(e_cnl, "true length not encoded"), f"{reasons(d, e_cnl)}")
    check("conventional event missing a camera click is excluded",
          has(e_cmiss, "missing a camera click"), f"{reasons(d, e_cmiss)}")
    kept = {r["event"] for r in d["conventional"]}
    check("the one good conventional event survives", kept == {e_cok}, f"got {sorted(kept)}")
    surv = {q["event"] for q in d["cloud_points"]}
    check("exactly the two good cloud points survive, one pair between them",
          surv == {e_dup_a, e_zero} and len(d["cloud_pairs"]) == 1, f"got {sorted(surv)}")
    check("nothing is silently dropped: every rejection carries a reason",
          all(isinstance(e[3], str) and e[3] for e in d["exclusions"]))


def test_inconsistent_dimensionality(tmp):
    print("\n7. Dimensionality is verified per cloud, not assumed")
    p = os.path.join(tmp, "dims.vsd")
    s = Store(p)
    e2, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="0,0", tc="tcA")
    e3, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="1,1,1", tc="tcA")
    for xy in ("0,0,0", "1,2,3", "4,5,6"):
        s.event("Length Point Cloud", "Cloud B", 1, notes=xy, tc="tcB")
    s.close()
    d = kl.load(p)
    check("a cloud mixing 2D and 3D notes is rejected wholesale, not silently coerced",
          "Cloud A" not in d["clouds"] and
          any("inconsistent note dimensionality" in r for r in reasons(d, e3)),
          f"{reasons(d, e3) + reasons(d, e2)}")
    check("a consistently 3D cloud is accepted, so 2D is not hard-coded",
          "Cloud B" in d["clouds"] and len(d["clouds"]["Cloud B"]) == 3)
    b = [q for q in d["cloud_pairs"] if q["cloud"] == "Cloud B"]
    check("3D pair lengths use all three components", len(b) == 3 and
          any(abs(q["true"] - math.dist([0, 0, 0], [10, 20, 30])) < 1e-9 for q in b))


def test_clip_set(tmp):
    print("\n8. The required camera set is the document's clips unless overridden")
    p = os.path.join(tmp, "clips.vsd")
    s = Store(p, clips=("Left Camera", "Right Camera", "Third Camera"))
    e, _ = s.event("Length Point Cloud", "Cloud A", 1, notes="0,0", tc="tcA",
                   clicked=["Left Camera", "Right Camera"])
    s.event("Length Point Cloud", "Cloud A", 1, notes="1,0", tc="tcA")
    s.close()
    d3 = kl.load(p)
    check("a point missing the third clip's click is excluded by default",
          any("clicked in" in r for r in reasons(d3, e)), f"{reasons(d3, e)}")
    d2 = kl.load(p, clip_names=["Left Camera", "Right Camera"])
    check("restricting clip_names to two cameras admits it",
          e in {q["event"] for q in d2["cloud_points"]})


# --------------------------------------------------------------- real-document tests

def test_real_document():
    print(f"\n9. Real document: {os.path.basename(FISHEYE)}")
    if not os.path.exists(FISHEYE):
        check("document present", False, "not found; skipping real-document tests")
        return
    d = kl.load(FISHEYE)

    print("\n   9a. Provenance counts (lower bounds; valid annotations may be added later)")
    for key, want in SNAPSHOT.items():
        got = len(d["clouds"]) if key == "clouds" else len(d[key])
        check(f"{key} >= {want} (snapshot 2026-07-28)", got >= want, f"got {got}")
    check("zero exclusions in the current snapshot", len(d["exclusions"]) == 0,
          f"got {len(d['exclusions'])}")

    print("\n   9b. Pair count is exactly n(n-1)/2 per cloud, computed not asserted")
    for c, pts in sorted(d["clouds"].items()):
        n = len(pts)
        got = sum(1 for q in d["cloud_pairs"] if q["cloud"] == c)
        check(f"{c}: {n} points -> {n*(n-1)//2} pairs", got == n * (n - 1) // 2, f"got {got}")
    check("no pair crosses a cloud boundary",
          all(q["cloud"] == q["cloud"] for q in d["cloud_pairs"]) and
          sum(len(p) * (len(p) - 1) // 2 for p in d["clouds"].values()) == len(d["cloud_pairs"]))

    print("\n   9c. Repeated coordinates across clouds are real in this document and stay separate")
    from collections import defaultdict
    bymm = defaultdict(set)
    for q in d["cloud_points"]:
        bymm[tuple(q["mm"])].add(q["cloud"])
    shared = {k: v for k, v in bymm.items() if len(v) > 1}
    check("at least one coordinate is shared by two or more clouds", len(shared) > 0,
          f"{len(shared)} shared coordinates, e.g. {sorted(shared.items())[:2]}")
    check("the (0,0) origin is shared and duplicated per cloud, not merged",
          len(bymm.get((0.0, 0.0), ())) >= 2, f"clouds at origin: {sorted(bymm.get((0.0,0.0), ()))}")
    npts = len(d["cloud_points"])
    check("point count equals the sum over clouds, so nothing was globally deduplicated",
          npts == sum(len(p) for p in d["clouds"].values()), f"got {npts}")

    print("\n   9d. Units: notes are CENTIMETRES; mm is exactly ten times cm")
    check("every point's mm vector is 10x its cm vector",
          all(q["mm"] == [10.0 * v for v in q["cm"]] for q in d["cloud_points"]))
    check("all notes in this document are two-dimensional",
          {len(q["cm"]) for q in d["cloud_points"]} == {2},
          f"dims {sorted({len(q['cm']) for q in d['cloud_points']})}")
    mx = max(max(abs(v) for v in q["mm"]) for q in d["cloud_points"])
    check("largest coordinate is of millimetre magnitude, not centimetre", mx > 500.0,
          f"max |coord| {mx} mm")

    print("\n   9e. Each cloud is one timecode / one physical placement")
    for c, pts in sorted(d["clouds"].items()):
        tcs = {q["tc"] for q in pts}
        check(f"{c} sits at exactly one timecode", len(tcs) == 1, f"{sorted(tcs)}")
    ctc = {c: {q["tc"] for q in pts}.pop() for c, pts in d["clouds"].items()}
    check("the clouds' timecodes are all distinct, so clouds are distinct placements",
          len(set(ctc.values())) == len(ctc), f"{ctc}")

    print("\n   9f. The ORIGINAL 14 conventional measurements are still reproduced")
    ev = {r["event"] for r in d["conventional"]}
    missing = [e for e in ORIGINAL_14 if e not in ev]
    check("all 14 original events are still loaded as valid conventional measurements",
          not missing, f"missing {missing}")
    orig = [r for r in d["conventional"] if r["event"] in ORIGINAL_14]
    cls = sorted(r["true"] for r in orig)
    check("their true lengths are the original 10 cm / 19.6 cm / 30 cm classes",
          cls == [100.0] * 5 + [196.0] * 4 + [300.0] * 5, f"got {cls}")
    mae = _stored_mae(FISHEYE, ORIGINAL_14)
    check(f"stored 3D coordinates over those 14 give the historical MAE "
          f"{ORIGINAL_14_STORED_MAE} mm", abs(mae - ORIGINAL_14_STORED_MAE) < 5e-5,
          f"got {mae:.4f} mm")
    newer = sorted(r["event"] for r in d["conventional"] if r["event"] not in ORIGINAL_14)
    check("the newly added conventional measurements are disjoint from the original 14",
          not (set(newer) & set(ORIGINAL_14)), f"{len(newer)} new events")
    ntc = {r["tc"] for r in d["conventional"] if r["event"] not in ORIGINAL_14}
    check("the new conventional measurements all sit at ONE timecode, so they are one placement",
          len(ntc) == 1, f"{sorted(ntc)}")

    print("\n   9g. Every conventional event has exactly two endpoint points")
    check("two point primary keys per conventional measurement",
          all(len(r["pks"]) == 2 and r["pks"][0] != r["pks"][1] for r in d["conventional"]))
    check("every conventional endpoint is clicked in both cameras",
          all(len(d["clicks"][pk]) >= 2 for r in d["conventional"] for pk in r["pks"]))
    check("every cloud point is clicked in both cameras",
          all(len(d["clicks"][q["pk"]]) >= 2 for q in d["cloud_points"]))


def _stored_mae(vsd, events):
    """Length error from the document's own stored 3D coordinates, in the app's float32 arithmetic.

    Deliberately independent of the analysis pipeline: it reads ZVSPOINT3D directly, so agreement
    with the historical 2.9712 mm pins the loader's event selection rather than the reconstruction.
    """
    import struct
    jw = kl._jw()
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    rows = list(db.execute(
        "SELECT o.ZNAME2, t.ZNAME3, e.Z_PK, p.ZWORLDX, p.ZWORLDY, p.ZWORLDZ "
        "FROM ZVSVISIBLEITEM e JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
        "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
        "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
        "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK WHERE e.Z_ENT = 17 "
        "ORDER BY e.Z_PK, p.ZINDEX"))
    db.close()
    per = {}
    for nm, tn, e, x, y, z in rows:
        per.setdefault(e, {"nm": nm, "tn": tn, "p": []})["p"].append((x, y, z))
    f32 = lambda v: struct.unpack("f", struct.pack("f", v))[0]
    errs = []
    for e in events:
        r = per[e]
        a, b = r["p"][0], r["p"][1]
        d = math.sqrt(sum(f32(f32(a[i]) - f32(b[i])) ** 2 for i in range(3)))
        errs.append(f32(d) - jw.true_length_mm(r["nm"], r["tn"], 1.0))
    return sum(abs(v) for v in errs) / len(errs)


def main():
    print("=" * 100)
    print("knownlength.py parser and validation tests")
    print("=" * 100)
    with tempfile.TemporaryDirectory() as tmp:
        test_conventional_true_length()
        test_note_parsing()
        test_pair_construction(tmp)
        test_rejections(tmp)
        test_inconsistent_dimensionality(tmp)
        test_clip_set(tmp)
    test_real_document()
    npass = sum(1 for _, ok in _results if ok)
    print(f"\n{npass}/{len(_results)} checks passed")
    for name, ok in _results:
        if not ok:
            print(f"  FAILED: {name}")
    return 0 if npass == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
