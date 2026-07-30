#!/usr/bin/env python3
"""Step 1 of the solver-parity audit: freeze the document and identify APP13.

Reports the document's modification time and content hash, the newly stored 13 distortion
parameters for each clip (called APP13 throughout, never "stored" or "production calibration"),
the exact plumbline observations available to each solve, and the downstream state that a
distortion recomputation does or does not rebuild.

Read-only throughout: sqlite is opened with mode=ro and the file is never written.

Plain Python 3; no numpy needed.
"""

import hashlib
import math
import os
import sqlite3
import statistics
import sys
import time
from collections import defaultdict

FISHEYE = ("/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/"
           "2015-09-04-1 Clearwater.vsd")
PNAMES = ["centerX", "centerY", "K1", "K2", "K3", "K4", "K5", "K6", "K7",
          "P1", "P2", "P3", "P4"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main():
    vsd = sys.argv[1] if len(sys.argv) > 1 else FISHEYE
    say = print
    say("=" * 100)
    say("STEP 1  FREEZE AND IDENTIFY THE NEW ANCHOR (APP13)")
    say("=" * 100)

    say(f"\n  document {vsd}")
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = vsd + suffix
        if os.path.exists(p):
            st = os.stat(p)
            say(f"    {os.path.basename(p):50} {st.st_size:>12,} bytes   mtime "
                f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}")
            say(f"      sha256 {sha256(p)}")
        elif suffix:
            say(f"    {os.path.basename(p):50} absent")

    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    say(f"    sqlite journal_mode {db.execute('PRAGMA journal_mode').fetchone()[0]}")

    cols = {r[1] for r in db.execute("PRAGMA table_info(ZVSCALIBRATION)")}
    extra = [c for c in ("ZDISTORTIONHOLDOUTRESIDUAL",) if c in cols]
    sel = ("SELECT v.ZCLIPNAME, c.Z_PK, " +
           ", ".join(f"c.ZDISTORTION{n.upper()}" for n in
                     ["CENTERX", "CENTERY", "K1", "K2", "K3", "K4", "K5", "K6", "K7",
                      "P1", "P2", "P3", "P4"]) +
           ", c.ZDISTORTIONREMAININGPERPOINT, c.ZDISTORTIONREDUCTIONACHIEVED" +
           ("".join(f", c.{c}" for c in extra)) +
           " FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v ON v.Z_PK = c.ZVIDEOCLIP "
           "ORDER BY v.ZCLIPNAME")
    cals = {}
    for row in db.execute(sel):
        clip, pk = row[0], row[1]
        cals[clip] = {"pk": pk, "d13": list(row[2:15]), "perpoint": row[15],
                      "reduction": row[16],
                      "holdout": row[17] if extra else None}

    say(f"\n  APP13  the thirteen parameters now stored in the document")
    for clip in sorted(cals):
        c = cals[clip]
        say(f"\n    {clip}   (ZVSCALIBRATION.Z_PK = {c['pk']})")
        for n, v in zip(PNAMES, c["d13"]):
            say(f"      {n:8} {v!r}")
        say(f"      distortionRemainingPerPoint {c['perpoint']!r} px")
        say(f"      distortionReductionAchieved {c['reduction']!r}")
        say(f"      distortionHoldOutResidual   {c['holdout']!r}"
            + ("" if extra else "   (attribute absent from this document's model)"))

    # ------------------------------------------------------------------ plumbline observations
    say(f"\n  PLUMBLINE OBSERVATIONS  (production reads [self.distortionLines allObjects], i.e.")
    say(f"  every line attached to the calibration, with no timecode filter: VSCalibration.mm:2310)")
    for clip in sorted(cals):
        pk = cals[clip]["pk"]
        S = defaultdict(lambda: defaultdict(list))
        for tc, ln, x, y, idx in db.execute(
                "SELECT l.ZTIMECODE, l.Z_PK, p.ZSCREENX, p.ZSCREENY, p.ZINDEX1 "
                "FROM ZVSDISTORTIONLINE l JOIN ZVSSCREENPOINT p "
                "ON p.ZDISTORTIONLINE = l.Z_PK WHERE l.ZCALIBRATION = ? "
                "ORDER BY l.ZTIMECODE, l.Z_PK, p.ZINDEX1", (pk,)):
            S[tc][ln].append((x, y, idx))
        nullpts = sum(1 for tc in S for ln in S[tc] for x, _, _ in S[tc][ln] if x is None)
        say(f"\n    {clip}")
        tot_lines = tot_pts = tot_cost_lines = tot_cost_pts = 0
        for tc in sorted(S):
            lens = [len(v) for v in S[tc].values()]
            short = [n for n in lens if n < 3]
            cost = [n for n in lens if n >= 3]
            # median adjacent-point spacing, the board-distance proxy used elsewhere
            sp = [math.dist((a[0], a[1]), (b[0], b[1]))
                  for v in S[tc].values() for a, b in zip(v, v[1:])
                  if a[0] is not None and b[0] is not None
                  and 1 < math.dist((a[0], a[1]), (b[0], b[1])) < 400]
            say(f"      timecode {tc!r}: {len(lens)} lines, {sum(lens)} points; "
                f"{len(cost)} lines with >=3 points contributing {sum(cost)} points to the cost; "
                f"{len(short)} shorter lines contributing 0")
            say(f"        points per line {min(lens)}-{max(lens)} (median "
                f"{statistics.median(lens):.0f}); median adjacent spacing "
                f"{statistics.median(sp):.2f} px" if sp else "")
            tot_lines += len(lens); tot_pts += sum(lens)
            tot_cost_lines += len(cost); tot_cost_pts += sum(cost)
        say(f"      TOTAL available to the solve: {tot_lines} lines / {tot_pts} points; "
            f"cost-bearing {tot_cost_lines} lines / {tot_cost_pts} points")
        say(f"      null screen coordinates: {nullpts}")
        say(f"      timecodes combined by production: "
            f"{'YES, all ' + str(len(S)) + ' jointly' if len(S) > 1 else 'single timecode'}")
        pp = cals[clip]["perpoint"]
        if pp is not None:
            say(f"      implied final SSE from stored per-point residual and this point count: "
                f"{pp * pp * tot_cost_pts:.6f} px^2")

    # ------------------------------------------------------------------ downstream freshness
    say(f"\n  DOWNSTREAM STATE")
    say(f"    calculateDistortionCorrection (VSCalibration.mm:2308) writes only the 13 parameters,")
    say(f"    distortionReductionAchieved, distortionRemainingPerPoint and the hold-out residual,")
    say(f"    then refreshes the video overlay. It does NOT call calculateCalibration, so the")
    say(f"    homographies, refractive back-surface correction, camera position and stored 3D")
    say(f"    coordinates are NOT rebuilt by a distortion recomputation. They are separate menu")
    say(f"    actions wired independently in VidSyncProject.xib.")
    for clip in sorted(cals):
        pk = cals[clip]["pk"]
        row = db.execute(
            "SELECT ZCAMERAX, ZCAMERAY, ZCAMERAZ, ZCAMERAMEANPLD, ZPLANECOORDFRONT, "
            "ZPLANECOORDBACK FROM ZVSCALIBRATION WHERE Z_PK = ?", (pk,)).fetchone()
        nf = db.execute("SELECT COUNT(*) FROM ZVSSCREENPOINT WHERE ZCALIBRATION1 = ?",
                        (pk,)).fetchone()[0]
        nb = db.execute("SELECT COUNT(*) FROM ZVSSCREENPOINT WHERE ZCALIBRATION = ?",
                        (pk,)).fetchone()[0]
        say(f"    {clip}: stored camera ({row[0]!r}, {row[1]!r}, {row[2]!r}), cameraMeanPLD "
            f"{row[3]!r}; front nodes {nf}, back nodes {nb}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
