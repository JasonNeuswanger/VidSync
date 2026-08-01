#!/usr/bin/env python3
"""Freeze and inventory the 40-view corpus, and VERIFY the previously reported numbers.

This is the provenance gate for the 2026-07-30 held-out round. Nothing downstream may run until the
inputs are pinned and the earlier full-data results are reproduced FROM THE ARTIFACTS rather than
assumed. If a claimed value does not reproduce, that is reported as a failure here, not silently
absorbed later.

THE INFERENTIAL UNIT IS THE CLIP. A VidSync document contains two clips, but each clip is a separate
physical distortion system needing its own calibration. Document membership is PROVENANCE ONLY. This
module therefore records `document` purely as a source field and defines the analysis stratum as

    camera identity x focal length

CAMERA IDENTITY, AND ITS LIMITATION. No document stores a camera serial number. `ZVSVIDEOCLIP.
ZFILENAME` places every clip on one of two dedicated volumes, `/Volumes/VideosLeft` or
`/Volumes/VideosRight`, with a matching `... Left.mp4` / `... Right.mp4` basename, consistently across
all twenty documents. That establishes a stable two-way rig-position identity, and the operator
reports it corresponds to two physical cameras. It is NOT a serial number: this identifies the camera
POSITION, and would fail to distinguish a body swapped into the same position mid-project. Stated
here rather than assumed away. `camera_evidence` records how each clip was resolved.

RESOLUTION. No .vsd field carries the video resolution, and the source videos live on external
volumes that are not mounted. `lattice.FRAME_W/H` assumes 1920x1080 for every clip. This module
therefore reports the observed coordinate extent per clip as the only available evidence, and flags
any clip whose detections fall outside, or well short of, that assumed frame. Map comparisons in
later steps must not cross clips whose frame geometry cannot be reconciled.

Run with ~/.venvs/vidsync/bin/python. Writes analysis-output/corpus_freeze.{json,log}.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys

import numpy as np

import corpus
import harness_import

LT = harness_import.load("lattice")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")

# The values reported at the end of the 2026-07-30 projective-validity round, to be VERIFIED.
CLAIMED = {
    "uncorrected_median": 91.5, "B/M0_median": 3.33, "PD-D/M0_median": 2.64,
    "B/M1_median": 1.96, "PD-D/M1_median": 2.06,
    "B/M1_improved": 38, "PD-D/M1_improved": 39, "max_eta": 0.031,
}
CLAIM_TOL = {"median": 0.005, "count": 0, "eta": 0.0005}


def git_rev():
    def run(*a):
        try:
            return subprocess.run(a, cwd=HERE, capture_output=True, text=True).stdout.strip()
        except Exception:
            return "unavailable"
    return dict(head=run("git", "rev-parse", "HEAD"),
                lattice_blob=run("git", "hash-object", os.path.join(HERE, "lattice.py")),
                lattice_dirty=bool(run("git", "diff", "--name-only", "--", "lattice.py")),
                describe=run("git", "log", "-1", "--format=%h %s", "--", "lattice.py"))


def clip_metadata(vsd, clip):
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    row = db.execute("SELECT ZFILENAME, ZWINDOWFRAME FROM ZVSVIDEOCLIP WHERE ZCLIPNAME = ?",
                     (clip,)).fetchone()
    db.close()
    fn = row[0] if row else None
    cam, ev = None, "unresolved"
    if fn:
        vol = re.search(r"/Volumes/Videos(Left|Right)", fn)
        base = re.search(r"(Left|Right)\.[A-Za-z0-9]+$", os.path.basename(fn))
        if vol and base and vol.group(1) == base.group(1):
            cam, ev = vol.group(1), "volume+basename agree"
        elif vol:
            cam, ev = vol.group(1), "volume only"
        elif base:
            cam, ev = base.group(1), "basename only"
    if cam is None:                       # fall back to the clip name, and say so
        m = re.search(r"(Left|Right)", clip)
        if m:
            cam, ev = m.group(1), "clip name only (WEAKEST evidence)"
    return dict(file_name=fn, window_frame=row[1] if row else None,
                camera=cam, camera_evidence=ev)


def freeze_clip(d, clip):
    caps = LT.load_captures(d["vsd"], clip)
    xy = np.vstack([C.xy for C in caps]) if caps else np.zeros((0, 2))
    # point-set hash: click-direction and record-order invariant, so re-saving the document without
    # changing geometry cannot alter it. Sorted exact coordinates, fixed formatting.
    h = hashlib.sha256()
    for p in sorted(map(tuple, np.round(xy, 6).tolist())):
        h.update(f"{p[0]:.6f},{p[1]:.6f};".encode())
    rec = dict(document=d["code"], site=d["site"], focal_mm=d["focal_mm"], clip=clip,
               vsd=d["vsd"], role=d["role"])
    rec.update(clip_metadata(d["vsd"], clip))
    ext = dict(x_min=float(xy[:, 0].min()), x_max=float(xy[:, 0].max()),
               y_min=float(xy[:, 1].min()), y_max=float(xy[:, 1].max())) if len(xy) else {}
    lat = []
    n_lines = n_obs = n_idx = n_2c = 0
    for C in caps:
        ok = C.indexed()
        nc = C.n_constraints()
        n_lines += C.notes["n_lines"]
        n_obs += C.n
        n_idx += int(ok.sum())
        n_2c += int((ok & (nc >= 2)).sum())
        if ok.any():
            r, c = C.rc[ok, 0], C.rc[ok, 1]
            lat.append(dict(timecode=C.timecode, rows=int(r.max() - r.min() + 1),
                            cols=int(c.max() - c.min() + 1), n=int(ok.sum())))
    rec.update(point_set_sha256=h.hexdigest(), n_captures=len(caps), n_lines=n_lines,
               n_observations=n_obs, n_indexed=n_idx, n_indexed_2con=n_2c,
               lattice_extent=lat, observed_extent=ext,
               assumed_frame=[LT.FRAME_W, LT.FRAME_H],
               within_assumed_frame=bool(len(xy) and ext["x_min"] >= 0 and ext["y_min"] >= 0
                                         and ext["x_max"] <= LT.FRAME_W
                                         and ext["y_max"] <= LT.FRAME_H))
    return rec


def verify_prior(say):
    """Reproduce the eight claimed numbers FROM the stored round artifact."""
    p = os.path.join(OUT, "corpus_round_full.json")
    if not os.path.exists(p):
        say("  VERIFY: corpus_round_full.json absent; nothing verified")
        return dict(available=False)
    R = [r for r in json.load(open(p))["cameras"] if "error" not in r]
    v, cands = {}, ["B/M0", "B/M1", "PD-D/M0", "PD-D/M1"]
    unc = np.array([r["uncorrected_projective"]["rms"] for r in R])
    val = {c: np.array([r["fits"][c]["projective"]["rms"] for r in R]) for c in cands}
    v["uncorrected_median"] = float(np.median(unc))
    for c in cands:
        v[f"{c}_median"] = float(np.median(val[c]))
    v["B/M1_improved"] = int((val["B/M1"] < val["B/M0"]).sum())
    v["PD-D/M1_improved"] = int((val["PD-D/M1"] < val["PD-D/M0"]).sum())
    v["max_eta"] = float(max(abs(r["fits"][c]["eta"]) for r in R for c in cands))
    v["n_cameras"] = len(R)

    say(f"  {'claim':22} {'reported':>10} {'recomputed':>12}  verdict")
    ok = True
    for k, claim in CLAIMED.items():
        got = v[k]
        tol = (CLAIM_TOL["count"] if "improved" in k
               else CLAIM_TOL["eta"] if k == "max_eta" else CLAIM_TOL["median"])
        # the reported medians were quoted to 2-3 significant figures; compare at that precision
        good = (abs(got - claim) <= tol if "improved" in k or k == "max_eta"
                else abs(round(got, 2) - round(claim, 2)) <= 0.011)
        ok &= good
        say(f"  {k:22} {claim:10} {got:12.4f}  {'OK' if good else 'MISMATCH'}")
    v["all_verified"] = bool(ok)
    v["available"] = True
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(OUT, "corpus_freeze.json"))
    args = ap.parse_args()
    logp = os.path.join(OUT, "corpus_freeze.log")
    fh = open(logp, "w")

    def say(s=""):
        print(s, flush=True)
        fh.write(s + "\n")

    say("=" * 104)
    say("CORPUS FREEZE -- provenance, stratification, and verification of prior results")
    say("Inferential unit: the CLIP. Stratum: camera identity x focal length.")
    say("VidSync document is PROVENANCE ONLY and is never an inferential unit.")
    say("=" * 104)

    rev = git_rev()
    say(f"\n  grid-assembly revision: {rev['describe']}")
    say(f"  lattice.py blob {rev['lattice_blob'][:12]}  worktree-dirty={rev['lattice_dirty']}")
    say(f"  repo HEAD {rev['head'][:12]}")

    clips = []
    for d in corpus.documents():
        if not d["present"]:
            say(f"  ABSENT {d['label']}")
            continue
        for clip, _ in corpus.clips_with_plumblines(d["vsd"]):
            clips.append(freeze_clip(d, clip))

    say(f"\n  {len(clips)} clips from {len({c['document'] for c in clips})} documents")
    say(f"\n  {'document':14} {'clip':13} {'cam':>5} {'foc':>4} {'obs':>5} {'idx':>5} "
        f"{'2con':>5} {'extent x':>13} {'extent y':>13} {'hash':>10}")
    for c in sorted(clips, key=lambda z: (str(z["camera"]), str(z["focal_mm"]), z["document"])):
        e = c["observed_extent"]
        say(f"  {c['document']:14} {c['clip'][:13]:13} {str(c['camera']):>5} "
            f"{str(c['focal_mm'] or '-'):>4} {c['n_observations']:5d} {c['n_indexed']:5d} "
            f"{c['n_indexed_2con']:5d} {e['x_min']:6.0f}-{e['x_max']:<6.0f} "
            f"{e['y_min']:6.0f}-{e['y_max']:<6.0f} {c['point_set_sha256'][:10]}")

    say("\n  CAMERA IDENTITY EVIDENCE")
    from collections import Counter
    for k, n in Counter(c["camera_evidence"] for c in clips).items():
        say(f"    {k}: {n} clips")
    say("    NOTE: this is camera POSITION (Left/Right rig slot), not a serial number. A body")
    say("    swapped into the same slot mid-project would be indistinguishable.")

    say("\n  STRATA (camera x focal length) -- the analysis groups")
    groups = {}
    for c in clips:
        groups.setdefault((c["camera"], c["focal_mm"]), []).append(c["document"])
    for k in sorted(groups, key=lambda z: (str(z[0]), str(z[1]))):
        say(f"    {str(k[0]):>5} {str(k[1] or 'pool'):>5} mm  n={len(groups[k]):2d} clips  "
            f"{sorted(groups[k])}")
    say(f"    {len(groups)} strata; groups of size 1 cannot support within-group consistency.")

    bad = [c for c in clips if not c["within_assumed_frame"]]
    say(f"\n  FRAME CHECK against the assumed {LT.FRAME_W:.0f}x{LT.FRAME_H:.0f}: "
        f"{len(bad)} clips fall outside")
    for c in bad:
        say(f"    OUTSIDE: {c['document']} {c['clip']} {c['observed_extent']}")
    say("    Resolution is NOT stored in the .vsd and the source videos are on unmounted volumes,")
    say("    so this extent check is the only available evidence that 1920x1080 is right.")

    say("\n  VERIFICATION OF PREVIOUSLY REPORTED RESULTS")
    ver = verify_prior(say)

    with open(args.json, "w") as f:
        json.dump(dict(revision=rev, clips=clips, verification=ver,
                       strata={f"{k[0]}|{k[1]}": v for k, v in groups.items()}), f, indent=1)
    say(f"\n  wrote {args.json}")
    fh.close()
    return 0 if ver.get("all_verified", False) else 1


if __name__ == "__main__":
    sys.exit(main())
