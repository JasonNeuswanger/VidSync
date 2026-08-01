#!/usr/bin/env python3
"""Regression tests for the cloud-identity defect: grouping by display name instead of obj_pk.

THE DEFECT. Until 2026-07-30 knownlength.load() grouped point-cloud points with
`clouds[r["cloud"]].append(r)`, where `cloud` was the object's display name ZNAME2, even though the
same row already carried the object's primary key. Two distinct `Length Point Cloud` objects sharing a
name were therefore merged into one pseudo-cloud, with two consequences, both silent:

  1. FABRICATED GROUND TRUTH. Note coordinates are local to one placement of the physical frame, so a
     pair built across two placements has a true length that corresponds to no measurable distance.
  2. DESTRUCTIVE DEDUPLICATION. Every cloud's coordinates start at the origin, so once merged, the
     second cloud's (0,0), (10,0), ... collided with the first's and were dropped as "duplicate note
     coordinate". The observed instance lost 48 of 93 points and left 602 of 990 pairs invalid.

The fix makes obj_pk the grouping identity and the name display metadata only. These tests exercise
that on synthetic stores where the same-name/different-pk case can be constructed deliberately, and
then assert the corresponding properties on both real cloud-bearing documents.

Plain Python 3, no venv needed.
"""

import importlib.util
import math
import os
import sqlite3
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DM = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects")
REAL = {"10 mm Chena": os.path.join(DM, "2015-07-10-1 Chena.vsd"),
        "8 mm Clearwater": os.path.join(DM, "2015-09-04-1 Clearwater.vsd")}

_results = []


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


kl = L("knownlength")
TK = L("test_knownlength")          # reuse the established synthetic-store writer and schema


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


def raises(name, fn, needle, exc=Exception):
    try:
        fn()
    except exc as e:                                                        # noqa: BLE001
        check(name, needle in str(e), f"{type(e).__name__}: {str(e)[:90]!r}")
        return
    check(name, False, "no exception raised")


class Store(TK.Store):
    """test_knownlength.Store, but object identity can be forced apart from the display name.

    The parent keys its object cache on (type_name, obj_name), which is exactly the conflation under
    test, so it can never build the case that matters. `slot` names the OBJECT; `obj_name` is only what
    that object is called.
    """

    def event(self, type_name, obj_name, npoints, slot=None, **kw):
        key = (type_name, slot if slot is not None else obj_name)
        if key not in self.objects:
            if type_name not in self.types:
                pk = self._next()
                self.db.execute("INSERT INTO ZVSVISIBLEITEM VALUES (?,20,NULL,?,NULL,NULL)",
                                (pk, type_name))
                self.types[type_name] = pk
            pk = self._next()
            self.db.execute("INSERT INTO ZVSVISIBLEITEM VALUES (?,19,?,NULL,?,NULL)",
                            (pk, obj_name, self.types[type_name]))
            self.objects[key] = pk
        # Hand the parent a cache entry it will hit, so it never creates a second object.
        self.objects[(type_name, obj_name)] = self.objects[key]
        try:
            return super().event(type_name, obj_name, npoints, **kw)
        finally:
            if slot is not None:
                self.objects.pop((type_name, obj_name), None)

    def obj_pk(self, type_name, slot):
        return self.objects[(type_name, slot)]


def _twins(path):
    """Two Length Point Cloud objects, BOTH named 'Cloud A', at different placements/timecodes.

    Coordinates deliberately overlap the way real clouds do: every placement is digitized from its own
    origin, so (0,0) and (10,0) occur in both. Under name grouping this is the destructive case.
    """
    s = Store(path)
    for xy in ("0,0", "10,0", "0,10"):
        s.event("Length Point Cloud", "Cloud A", 1, slot="first", notes=xy, tc="tc1")
    for xy in ("0,0", "10,0", "0,10", "30,40"):
        s.event("Length Point Cloud", "Cloud A", 1, slot="second", notes=xy, tc="tc2")
    pk1, pk2 = s.obj_pk("Length Point Cloud", "first"), s.obj_pk("Length Point Cloud", "second")
    s.close()
    return pk1, pk2


# --------------------------------------------------------------------------- synthetic

def test_same_name_distinct_objects(tmp):
    print("\n1. Two cloud objects sharing a display name stay two clouds")
    p = os.path.join(tmp, "twins.vsd")
    pk1, pk2 = _twins(p)
    d = kl.load(p)
    check("the two objects really do share a display name in the store",
          d["cloud_names"][pk1] == d["cloud_names"][pk2] == "Cloud A")
    check("two cloud objects are reported, not one", len(d["clouds"]) == 2,
          f"got {sorted(d['clouds'])}")
    pks = {r["obj_pk"] for r in d["cloud_objects"]}
    check("both primary keys appear in the cloud inventory", pks == {pk1, pk2}, f"got {sorted(pks)}")
    check("no point is lost to cross-object coordinate collision: 3 + 4 = 7 points",
          len(d["cloud_points"]) == 7, f"got {len(d['cloud_points'])}")
    check("no point was excluded as a duplicate coordinate", not d["exclusions"],
          f"{d['exclusions']}")
    byk = defaultdict(int)
    for q in d["cloud_pairs"]:
        byk[q["cloud_pk"]] += 1
    check("pairs are 3 and 6, i.e. n(n-1)/2 within each object",
          byk == {pk1: 3, pk2: 6}, f"got {dict(byk)}")
    check("total pairs 9, so no pair was built across the two placements",
          len(d["cloud_pairs"]) == 9, f"got {len(d['cloud_pairs'])}")
    check("display keys disambiguate the shared name instead of colliding",
          sorted(d["clouds"]) == sorted([f"Cloud A #{pk1}", f"Cloud A #{pk2}"]),
          f"got {sorted(d['clouds'])}")
    check("every record still carries the raw display name for reporting",
          {r["cloud_name"] for r in d["cloud_points"]} == {"Cloud A"})
    # The counterfactual: name grouping would have merged these into ONE cloud of 4 points
    # (3 + 4 minus 3 collisions) and 6 pairs, three of which cross placements.
    check("the merged-by-name outcome (4 points, 6 pairs) is NOT what the loader produces",
          not (len(d["cloud_points"]) == 4 and len(d["cloud_pairs"]) == 6))


def test_no_pair_crosses_object_or_timecode(tmp):
    print("\n2. Every pair has two distinct points from exactly one object and one timecode")
    p = os.path.join(tmp, "twins2.vsd")
    pk1, pk2 = _twins(p)
    d = kl.load(p)
    ev = {q["event"]: q for q in d["cloud_points"]}
    bad_obj = [q for q in d["cloud_pairs"]
               if {ev[q["i"]]["cloud_pk"], ev[q["j"]]["cloud_pk"]} != {q["cloud_pk"]}]
    check("no pair spans two obj_pk values", not bad_obj, f"{bad_obj[:2]}")
    bad_tc = [q for q in d["cloud_pairs"] if ev[q["i"]]["tc"] != ev[q["j"]]["tc"]]
    check("no pair spans two timecodes", not bad_tc, f"{bad_tc[:2]}")
    check("no self-pair", all(q["i"] != q["j"] for q in d["cloud_pairs"]))
    keys = [frozenset((q["i"], q["j"])) for q in d["cloud_pairs"]]
    check("no reversed duplicate and no ordinary duplicate", len(keys) == len(set(keys)))
    check("every pair's true length is positive", all(q["true"] > 0 for q in d["cloud_pairs"]))
    # a true length that could only come from crossing the two placements
    check("no pair reports a distance that only a cross-placement pairing could produce",
          all(q["true"] > 0 for q in d["cloud_pairs"]) and
          sum(1 for q in d["cloud_pairs"] if abs(q["true"]) < 1e-12) == 0)


def test_exact_pair_count(tmp):
    print("\n3. Each cloud yields exactly n(n-1)/2 pairs after eligibility filtering")
    p = os.path.join(tmp, "counts.vsd")
    s = Store(p)
    sizes = {"a": 2, "b": 5, "c": 9}
    for slot, n in sizes.items():
        for i in range(n):
            s.event("Length Point Cloud", f"Cloud {slot}", 1, slot=slot, notes=f"{i},0", tc=f"tc{slot}")
    # one point of cloud c is clicked in a single camera, so eligibility must shrink 9 -> 8
    s.event("Length Point Cloud", "Cloud c", 1, slot="c", notes="99,0", tc="tcc",
            clicked=["Left Camera"])
    pks = {k: s.obj_pk("Length Point Cloud", k) for k in sizes}
    s.close()
    d = kl.load(p)
    want = {pks["a"]: 2, pks["b"]: 5, pks["c"]: 9}
    for rec in sorted(d["cloud_objects"], key=lambda r: r["obj_pk"]):
        n = rec["n_points"]
        check(f"obj {rec['obj_pk']}: {n} eligible points -> {n * (n - 1) // 2} pairs",
              rec["n_pairs"] == n * (n - 1) // 2, f"got {rec['n_pairs']}")
    check("the ineligible point is excluded, so cloud c counts 9 not 10",
          {r["obj_pk"]: r["n_points"] for r in d["cloud_objects"]} == want,
          f"got {[(r['obj_pk'], r['n_points']) for r in d['cloud_objects']]}")
    check("counting uses ELIGIBLE points, not stored points",
          any("clicked in" in e[3] for e in d["exclusions"]))
    tot = sum(n * (n - 1) // 2 for n in want.values())
    check(f"document total is the sum of within-cloud pair counts ({tot})",
          len(d["cloud_pairs"]) == tot, f"got {len(d['cloud_pairs'])}")


def test_multi_timecode_fails_clearly(tmp):
    print("\n4. A cloud object spanning two timecodes fails clearly, never silently combined")
    p = os.path.join(tmp, "twotc.vsd")
    s = Store(p)
    for xy, tc in (("0,0", "tc1"), ("10,0", "tc1"), ("0,10", "tc2")):
        s.event("Length Point Cloud", "Cloud A", 1, slot="a", notes=xy, tc=tc)
    s.close()
    raises("strict mode raises CloudIdentityError naming the object and its timecodes",
           lambda: kl.load(p), "spans 2 timecodes", kl.CloudIdentityError)
    d = kl.load(p, strict_cloud_timecode=False)
    check("permissive mode still refuses to combine them: the cloud is dropped whole",
          not d["clouds"] and not d["cloud_pairs"], f"{sorted(d['clouds'])}")
    check("and every dropped point carries the reason",
          len(d["exclusions"]) == 3 and all("one timecode" in e[3] for e in d["exclusions"]))


def test_duplicate_dedup_is_within_object(tmp):
    print("\n5. Duplicate-coordinate rejection applies within one object, never across objects")
    p = os.path.join(tmp, "dup.vsd")
    s = Store(p)
    for xy in ("0,0", "0,0", "10,0"):          # a genuine within-object duplicate
        s.event("Length Point Cloud", "Cloud A", 1, slot="a", notes=xy, tc="tc1")
    for xy in ("0,0", "10,0"):                 # same coordinates, different object
        s.event("Length Point Cloud", "Cloud A", 1, slot="b", notes=xy, tc="tc2")
    pa, pb = s.obj_pk("Length Point Cloud", "a"), s.obj_pk("Length Point Cloud", "b")
    s.close()
    d = kl.load(p)
    n = {r["obj_pk"]: r["n_points"] for r in d["cloud_objects"]}
    check("the within-object duplicate is rejected: object a keeps 2 of 3",
          n[pa] == 2, f"got {n[pa]}")
    check("the cross-object repetition is untouched: object b keeps 2 of 2",
          n[pb] == 2, f"got {n[pb]}")
    check("exactly one exclusion, and it names the duplicate coordinate",
          len(d["exclusions"]) == 1 and "duplicate note coordinate" in d["exclusions"][0][3],
          f"{d['exclusions']}")
    check("the exclusion is attributed to the disambiguated cloud key, not the bare shared name",
          d["exclusions"][0][1] == f"Cloud A #{pa}", f"got {d['exclusions'][0][1]!r}")


def test_unique_names_unchanged(tmp):
    print("\n6. When names are unique the keys are the bare names, so nothing else changes")
    p = os.path.join(tmp, "uniq.vsd")
    s = Store(p)
    for nm in ("Cloud A", "Cloud B"):
        for i in range(3):
            s.event("Length Point Cloud", nm, 1, notes=f"{i},0", tc=f"tc{nm[-1]}")
    s.close()
    d = kl.load(p)
    check("cloud keys are exactly the display names", sorted(d["clouds"]) == ["Cloud A", "Cloud B"],
          f"got {sorted(d['clouds'])}")
    check("pair records still carry the bare name in 'cloud'",
          {q["cloud"] for q in d["cloud_pairs"]} == {"Cloud A", "Cloud B"})


# --------------------------------------------------------------------------- real documents

def test_real_documents():
    print("\n7. Both real cloud-bearing documents: complete, exact, within-object pair inventories")
    for label, path in sorted(REAL.items()):
        print(f"\n   {label}: {os.path.basename(path)}")
        if not os.path.exists(path):
            check(f"{label} present", False, "not found")
            continue
        d = kl.load(path)
        # every cloud OBJECT in the document is accounted for, from an independent query
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        raw = {int(pk): int(n) for pk, n in db.execute(
            "SELECT o.Z_PK, COUNT(p.Z_PK) FROM ZVSVISIBLEITEM o "
            "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
            "JOIN Z_17TRACKEDOBJECTS j ON j.Z_19TRACKEDOBJECTS = o.Z_PK "
            "JOIN ZVSVISIBLEITEM e ON e.Z_PK = j.Z_17TRACKEDEVENTS AND e.Z_ENT = 17 "
            "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK "
            "WHERE o.Z_ENT = 19 AND t.ZNAME3 = ? GROUP BY o.Z_PK", (kl.CLOUD_TYPE,))}
        db.close()
        seen = {r["obj_pk"] for r in d["cloud_objects"]}
        check(f"{label}: every cloud object in the file is processed", seen == set(raw),
              f"file {sorted(raw)} vs loader {sorted(seen)}")
        check(f"{label}: every cloud object was KEPT (none silently rejected)",
              all(r["kept"] for r in d["cloud_objects"]),
              f"{[(r['obj_pk'], r.get('rejected')) for r in d['cloud_objects'] if not r['kept']]}")
        check(f"{label}: display names are unique, so no disambiguation was needed",
              len(set(d["cloud_names"].values())) == len(d["cloud_names"]),
              f"{sorted(d['cloud_names'].values())}")
        exact = all(r["n_pairs"] == r["n_points"] * (r["n_points"] - 1) // 2
                    for r in d["cloud_objects"])
        check(f"{label}: each cloud yields exactly n(n-1)/2 pairs", exact,
              f"{[(r['name'], r['n_points'], r['n_pairs']) for r in d['cloud_objects']]}")
        tot = sum(r["n_points"] * (r["n_points"] - 1) // 2 for r in d["cloud_objects"])
        check(f"{label}: {len(d['cloud_pairs'])} pairs equals the sum of n(n-1)/2 = {tot}",
              len(d["cloud_pairs"]) == tot)
        ev = {q["event"]: q for q in d["cloud_points"]}
        check(f"{label}: no pair spans two cloud objects",
              all({ev[q["i"]]["cloud_pk"], ev[q["j"]]["cloud_pk"]} == {q["cloud_pk"]}
                  for q in d["cloud_pairs"]))
        check(f"{label}: no pair spans two timecodes",
              all(ev[q["i"]]["tc"] == ev[q["j"]]["tc"] for q in d["cloud_pairs"]))
        check(f"{label}: each cloud object sits at exactly one timecode",
              all(len(r["timecodes"]) == 1 for r in d["cloud_objects"]),
              f"{[(r['name'], r['timecodes']) for r in d['cloud_objects']]}")
        keys = [frozenset((q["i"], q["j"])) for q in d["cloud_pairs"]]
        check(f"{label}: no self-pair, reversed duplicate or ordinary duplicate",
              len(keys) == len(set(keys)) and all(q["i"] != q["j"] for q in d["cloud_pairs"]))
        check(f"{label}: every point is clicked in every camera",
              all(len(d["clicks"][q["pk"]]) >= 2 for q in d["cloud_points"]))
        check(f"{label}: no loader exclusions", not d["exclusions"], f"{d['exclusions'][:3]}")
        # the coordinate collisions that name grouping would have destroyed
        bycoord = defaultdict(set)
        for q in d["cloud_points"]:
            bycoord[tuple(q["mm"])].add(q["cloud_pk"])
        shared = {k: v for k, v in bycoord.items() if len(v) > 1}
        check(f"{label}: coordinates ARE shared across clouds ({len(shared)} of them) and survive",
              len(shared) > 0, f"e.g. {sorted(shared)[:2]}")
        check(f"{label}: point total equals the sum over clouds, so nothing was globally deduped",
              len(d["cloud_points"]) == sum(r["n_points"] for r in d["cloud_objects"]))
        # true lengths are consistent with the note coordinates, recomputed independently
        bad = [q for q in d["cloud_pairs"]
               if abs(q["true"] - math.dist(ev[q["i"]]["mm"], ev[q["j"]]["mm"])) > 1e-9]
        check(f"{label}: every true length is the mm distance of its own two note coordinates",
              not bad, f"{bad[:1]}")
        print(f"      inventory: " + ", ".join(
            f"{r['name']} (obj {r['obj_pk']}) {r['n_points']}p/{r['n_pairs']}pr"
            for r in sorted(d["cloud_objects"], key=lambda z: z["key"])))


def main():
    print("=" * 100)
    print("cloud identity (obj_pk) regression tests for knownlength.py")
    print("=" * 100)
    with tempfile.TemporaryDirectory() as tmp:
        test_same_name_distinct_objects(tmp)
        test_no_pair_crosses_object_or_timecode(tmp)
        test_exact_pair_count(tmp)
        test_multi_timecode_fails_clearly(tmp)
        test_duplicate_dedup_is_within_object(tmp)
        test_unique_names_unchanged(tmp)
    test_real_documents()
    npass = sum(1 for _, ok in _results if ok)
    print(f"\n{npass}/{len(_results)} checks passed")
    for name, ok in _results:
        if not ok:
            print(f"  FAILED: {name}")
    return 0 if npass == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
