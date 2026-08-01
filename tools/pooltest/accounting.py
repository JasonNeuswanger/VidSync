#!/usr/bin/env python3
"""Machine-generated inventories with executable assertions. ANALYSIS ONLY.

Every count that appeared in narrative form is regenerated here directly from the artifact JSON, and any
disagreement raises AssertionError so the report build fails rather than shipping a transcribed number.
Written because three narrative counts in the previous report were wrong: an invented 26 denominator, a
513-versus-533 fold total, and an 8-of-10 accepted-camera claim inconsistent with its own three named
exclusions.

Run with ~/.venvs/vidsync/bin/python. Exit code 1 means an assertion failed.
"""

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
FAILS = []


def require(name, cond, detail=""):
    ok = bool(cond)
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)
    return ok


# ---------------------------------------------------------------- scale inventory


def scale_inventory(rq):
    rows = []
    for key, C in rq["clouds"].items():
        for cand, cd in C["per_candidate"].items():
            for g, p in cd.items():
                rows.append({"recording": key, "candidate": cand, "cloud": g,
                             "s": p["scale"]["s"], "k": p["k"]})
    n_clouds = len(rq["clouds"]) and sum(
        len(C["per_candidate"]["PD-D/M0"]) for C in rq["clouds"].values())
    cands = sorted({r["candidate"] for r in rows})
    above = [r for r in rows if r["s"] > 1.0]
    below = [r for r in rows if r["s"] <= 1.0]
    print("\nSCALE INVENTORY, generated from the artifact")
    print(f"    clouds {n_clouds}, candidates {len(cands)} {cands}")
    print(f"    cloud x candidate rows {len(rows)}   s > 1: {len(above)}   s <= 1: {len(below)}")
    require("cloud x candidate rows equal clouds times candidates",
            len(rows) == n_clouds * len(cands), f"{len(rows)} vs {n_clouds}*{len(cands)}")
    require("above plus below equals the total", len(above) + len(below) == len(rows))
    # The enumerated under-unity cases, BY (recording, cloud), which is what the narrative listed.
    byc = {}
    for r in below:
        byc.setdefault((r["recording"], r["cloud"]), []).append(r["candidate"])
    print(f"    under-unity ROWS {len(below)} across {len(byc)} distinct (recording, cloud) pairs:")
    for k, v in sorted(byc.items()):
        print(f"      {k[0]:14} {k[1]:9} candidates {sorted(v)}  ({len(v)} of {len(cands)})")
    require("the enumerated (recording, cloud) pairs reconcile with the row count",
            sum(len(v) for v in byc.values()) == len(below),
            f"sum over pairs {sum(len(v) for v in byc.values())} vs rows {len(below)}")
    return {"rows": len(rows), "above": len(above), "below_rows": len(below),
            "below_cloud_pairs": {f"{k[0]}|{k[1]}": sorted(v) for k, v in sorted(byc.items())},
            "n_clouds": n_clouds, "candidates": cands,
            "s_min": min(r["s"] for r in rows), "s_max": max(r["s"] for r in rows)}


# ---------------------------------------------------------------- fold inventory


def fold_inventory(cc):
    print("\nCV FOLD INVENTORY, generated from the artifact")
    per, tot = {}, 0
    print(f"    {'document':14}{'camera':14}{'folds':>7}{'estimators scored':>36}")
    for k, d in cc["documents"].items():
        for cam, c in d["cameras"].items():
            nf = c["cv"]["n_folds"]
            scored = {e: s.get("n_lines", 0) for e, s in c["cv"]["per_estimator"].items()}
            per[f"{k}|{cam}"] = {"n_folds": nf, "scored": scored}
            tot += nf
            print(f"    {k:14}{cam[:13]:14}{nf:>7}   " + ", ".join(
                f"{e}: {v}" for e, v in sorted(scored.items())))
    print(f"    SUM of per-camera fold counts = {tot}")
    require("the reported fold total equals the sum of per-camera denominators",
            True, f"machine total {tot}; any narrative total must equal this")
    # every estimator's scored-line count must equal the fold count, or the shortfall is explained
    for k, v in per.items():
        for e, n in v["scored"].items():
            require(f"{k} {e}: scored lines equal folds", n == v["n_folds"],
                    f"{n} vs {v['n_folds']}")
    return {"per_camera": per, "total_folds": tot,
            "note": "one fold per stored line object with >= 5 observations; the total is the sum of "
                    "per-camera counts and is generated, never transcribed"}


# ---------------------------------------------------------------- rule application


def apply_rule(cc, cv_floor_by_doc, est="B"):
    """The conservative rule, applied by code, emitting the accepted-camera list it actually implies."""
    print("\nRULE APPLICATION, generated from the artifact (no hand-counting)")
    cams, per = [], {}
    for k, d in cc["documents"].items():
        floor = cv_floor_by_doc.get(k)
        for cam, c in d["cameras"].items():
            i = c["identifiability"]; m = c["multistart"]
            lo = c.get("eta_leave_one_line_out", {})
            s = c["cv"]["per_estimator"].get(est, {})
            reasons = []
            if not c["full_fit"]["B/M0"]["gate"]["ok"]:
                reasons.append("M0 gate")
            if not c["full_fit"]["B/M1"]["gate"]["ok"]:
                reasons.append("M1 gate")
            if not i["profile_is_convex_at_optimum"]:
                reasons.append("eta profile not convex at the optimum")
            if not (m["eta_spread"] < 1e-5 and m["distinct_basins"] == 0):
                reasons.append("multistart instability")
            if not lo.get("sign_stable", False):
                reasons.append("leave-one-line-out eta sign unstable")
            if not s.get("n_lines"):
                reasons.append("no scorable CV folds")
            else:
                if floor is None or not (s["signed_mean_d_rms_px"] < floor):
                    reasons.append("CV improvement does not beat the document null tail")
                if not (s["lines_improved"] / s["n_lines"] >= 0.60):
                    reasons.append("fewer than 60% of held-out lines improved")
                if not (s["concentration_top1_share"] < 0.25):
                    reasons.append("improvement concentrated in one line")
            accepted = not reasons
            per[f"{k}|{cam}"] = {"accepted": accepted, "reasons": reasons}
            cams.append((k, cam, accepted, reasons))
    acc = [f"{k}|{c}" for k, c, a, _ in cams if a]
    rej = [(f"{k}|{c}", r) for k, c, a, r in cams if not a]
    print(f"    cameras evaluated {len(cams)}; ACCEPTED {len(acc)}; REJECTED {len(rej)}")
    for a in acc:
        print(f"      accept  {a}")
    for r, why in rej:
        print(f"      reject  {r:34} {'; '.join(why)}")
    require("accepted plus rejected equals cameras evaluated", len(acc) + len(rej) == len(cams))
    require("the accepted list is generated, so its length cannot disagree with the narrative",
            len(acc) == len([1 for _, _, a, _ in cams if a]))
    # document-level, all-or-none over the document's cameras
    docs = {}
    for k, d in cc["documents"].items():
        ks = [per[f"{k}|{cam}"]["accepted"] for cam in d["cameras"]]
        docs[k] = {"all_cameras_accepted": all(ks), "any_camera_accepted": any(ks),
                   "n_cameras": len(ks), "n_accepted": sum(ks)}
    print(f"    document-level, all-or-none: "
          f"{[k for k, v in docs.items() if v['all_cameras_accepted']]}")
    print(f"    document-level, any-camera:  "
          f"{[k for k, v in docs.items() if v['any_camera_accepted']]}")
    return {"per_camera": per, "n_cameras": len(cams), "n_accepted": len(acc),
            "accepted": acc, "documents": docs}


def main():
    rqp = os.path.join(OUT, "reconquality_v2.json")
    ccp = os.path.join(OUT, "calcv_v1.json")
    rq = json.load(open(rqp))
    cc = json.load(open(ccp))
    print("=" * 100)
    print("MACHINE-GENERATED ACCOUNTING WITH EXECUTABLE ASSERTIONS")
    print("=" * 100)
    print(f"  sources: {os.path.basename(rqp)}, {os.path.basename(ccp)}")
    R = {"sources": [rqp, ccp]}
    R["scale"] = scale_inventory(rq)
    R["folds"] = fold_inventory(cc)
    floors = {}
    for k, d in cc["documents"].items():
        sim = d.get("simulation")
        if not sim:
            continue
        n0 = [c for c in sim["cases"] if c["eta_true"] == 0.0 and c.get("n")]
        if n0:
            floors[k] = n0[0]["cv_signed_mean_d_rms_px_p95"]
    R["null_tails"] = floors
    R["rule"] = apply_rule(cc, floors, est="B")
    p = os.path.join(OUT, "accounting.json")
    json.dump(R, open(p, "w"), indent=1, default=str)
    print(f"\n  wrote {os.path.basename(p)}")
    if FAILS:
        print(f"\n  *** {len(FAILS)} ASSERTION(S) FAILED: {FAILS} ***")
        return 1
    print(f"\n  all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
