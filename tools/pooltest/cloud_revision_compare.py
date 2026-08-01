#!/usr/bin/env python3
"""Old-versus-new comparison of two `cloud_downstream` runs on the same document after a redigitization.

Occasion: on 2026-07-30 the operator redigitized the LEFT-camera plumblines of `2015-09-04-1 Clearwater`
with the checkerboard moved substantially farther from the camera, to test whether the near-field /
right-edge anomaly came from a close-range calibration that represented distortion poorly at measurement
distances. The right camera and all known-length annotations were left alone.

WHAT THIS SCRIPT CAN AND CANNOT DO. It compares two artifacts written by `cloud_downstream.py`. Whether a
given comparison is possible depends entirely on what each artifact persisted, and that is reported rather
than assumed:

  ALWAYS available from both artifacts: per-point reprojection residuals, incident pair errors, Procrustes
  and out-of-plane residuals, every downstream metric, per-camera fit loss, eta and every physical-map
  gate summary, and the cloud/conventional inventories.

  AVAILABLE ONLY IF THE ARTIFACT PERSISTED `theta14`: the parameter vectors, and hence the induced
  distortion-map comparison, vector-difference fields, and radial/azimuthal structure. `theta14` was added
  to `cloud_downstream.py` on 2026-07-30 precisely because its absence blocked this comparison once; runs
  written before that carry no map and NO MAP IS RECONSTRUCTED from rounded report summaries.

  AVAILABLE ONLY IF THE OLD DOCUMENT ITSELF SURVIVES: old plumbline coverage and residual structure.
  Point-set hashes are persisted from 2026-07-30 onward so at least the identity question -- did this
  camera's observations change? -- is answerable from artifacts alone.

Writes analysis-output/cloud_revision_compare_<label>.{json,log} plus figures. Never overwrites the inputs.
Run with ~/.venvs/vidsync/bin/python.
"""

import argparse
import json
import math
import os
import sys

import numpy as np

import harness_import

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")
L = harness_import.load
LT = L("lattice")

RIGHT_EDGE = (1680.0, 1920.0)
CANDS = ["stored", "B/M0", "B/M1", "PD-D/M0", "PD-D/M1"]


def load(path):
    R = json.load(open(path))
    return R.get("results", R), R.get("manifest", {})


def doc(res, key):
    return res["documents"][key]


# ---------------------------------------------------------------- map comparison


def map_diff(th_old, th_new, mask_region=None, steps=160):
    """Displacement difference between two induced maps over their COMMON valid domain.

    Common valid domain means: both maps' Newton inverse converged and both Jacobian determinants are
    positive at that pixel. Comparing where one map is invalid would report a number produced by a
    failure rather than by a difference.
    """
    th_old = np.asarray(th_old, float)
    th_new = np.asarray(th_new, float)
    gx, gy = np.meshgrid(np.linspace(0.5, LT.FRAME_W - 0.5, steps),
                         np.linspace(0.5, LT.FRAME_H - 0.5, steps))
    g = np.stack([gx.ravel(), gy.ravel()], axis=1)
    uo, un = LT.U(g, th_old), LT.U(g, th_new)
    Jo, Jn = LT.jac_U(g, th_old), LT.jac_U(g, th_new)
    do = Jo[:, 0, 0] * Jo[:, 1, 1] - Jo[:, 0, 1] * Jo[:, 1, 0]
    dn = Jn[:, 0, 0] * Jn[:, 1, 1] - Jn[:, 0, 1] * Jn[:, 1, 0]
    ok = np.isfinite(uo).all(1) & np.isfinite(un).all(1) & (do > 0) & (dn > 0)
    d = un - uo
    mag = np.linalg.norm(d, axis=1)
    sel = ok if mask_region is None else (ok & mask_region(g))
    out = {"n_grid": int(ok.sum()), "n_selected": int(sel.sum()),
           "common_valid_fraction": float(ok.mean())}
    if sel.any():
        m = mag[sel]
        out.update({"median_px": float(np.median(m)), "rms_px": float(math.sqrt((m ** 2).mean())),
                    "p95_px": float(np.percentile(m, 95)), "max_px": float(m.max()),
                    "mean_px": float(m.mean())})
    else:
        out.update({k: float("nan") for k in ("median_px", "rms_px", "p95_px", "max_px", "mean_px")})
    return out, {"grid": g, "diff": d, "mag": mag, "ok": ok,
                 "det_old": do, "det_new": dn, "u_old": uo, "u_new": un}


def radial_azimuthal(g, mag, ok, centre):
    r = np.linalg.norm(g - np.asarray(centre, float), axis=1)
    a = np.degrees(np.arctan2(g[:, 1] - centre[1], g[:, 0] - centre[0]))
    rows = []
    edges = np.linspace(0, r[ok].max(), 9)
    for i in range(len(edges) - 1):
        s = ok & (r >= edges[i]) & (r < edges[i + 1])
        if s.any():
            rows.append({"kind": "radial", "lo": float(edges[i]), "hi": float(edges[i + 1]),
                         "n": int(s.sum()), "median_px": float(np.median(mag[s])),
                         "max_px": float(mag[s].max())})
    for i in range(-180, 180, 45):
        s = ok & (a >= i) & (a < i + 45)
        if s.any():
            rows.append({"kind": "azimuthal", "lo": float(i), "hi": float(i + 45),
                         "n": int(s.sum()), "median_px": float(np.median(mag[s])),
                         "max_px": float(mag[s].max())})
    return rows


# ---------------------------------------------------------------- figures


def fig_vector_diff(outdir, stem, clip, D, centre, say):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                                   # noqa: BLE001
        say(f"    figures skipped: matplotlib unavailable ({e})")
        return []
    g, d, mag, ok = D["grid"], D["diff"], D["mag"], D["ok"]
    n = int(math.sqrt(len(g)))
    fig, ax = plt.subplots(1, 2, figsize=(17, 6))
    M = np.where(ok, mag, np.nan).reshape(n, n)
    im = ax[0].imshow(M, origin="upper", extent=[0, LT.FRAME_W, LT.FRAME_H, 0], cmap="magma")
    fig.colorbar(im, ax=ax[0], label="|new - old| displacement (px)")
    ax[0].axvspan(RIGHT_EDGE[0], RIGHT_EDGE[1], color="cyan", alpha=0.18)
    ax[0].set_title(f"{clip}: induced-map difference magnitude\n"
                    f"cyan band = former right-edge problem region", fontsize=10)
    st = max(1, n // 26)
    sl = (slice(None, None, st), slice(None, None, st))
    G = g.reshape(n, n, 2)
    Dv = np.where(ok[:, None], d, np.nan).reshape(n, n, 2)
    ax[1].quiver(G[sl + (0,)], G[sl + (1,)], Dv[sl + (0,)], -Dv[sl + (1,)],
                 np.linalg.norm(Dv[sl], axis=-1), cmap="magma", angles="xy")
    ax[1].axvspan(RIGHT_EDGE[0], RIGHT_EDGE[1], color="cyan", alpha=0.18)
    ax[1].set_xlim(0, LT.FRAME_W); ax[1].set_ylim(LT.FRAME_H, 0); ax[1].set_aspect("equal")
    ax[1].set_title(f"{clip}: vector difference field (new minus old), y flipped to image sense",
                    fontsize=10)
    for a in ax:
        a.set_xlabel("screen x (px)"); a.set_ylabel("screen y (px)")
    p = os.path.join(outdir, f"{stem}_mapdiff_{clip.split()[0]}.png")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig)
    say(f"    wrote {os.path.basename(p)}")
    return [p]


def fig_point_delta(outdir, stem, old_pts, new_pts, clicks_by_pk, clips, say, flagged):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                                   # noqa: BLE001
        say(f"    figures skipped: matplotlib unavailable ({e})")
        return []
    o = {r["pk"]: r for r in old_pts}
    nw = {r["pk"]: r for r in new_pts}
    shared = [p for p in nw if p in o]
    written = []
    for cam in clips:
        pts = [p for p in shared if cam in clicks_by_pk.get(p, {})]
        if not pts:
            continue
        dl = np.array([nw[p]["rep_px"] - o[p]["rep_px"] for p in pts])
        lim = float(np.abs(dl).max()) or 1.0
        fig, ax = plt.subplots(figsize=(12, 7))
        sc = ax.scatter([clicks_by_pk[p][cam][0] for p in pts],
                        [clicks_by_pk[p][cam][1] for p in pts], c=dl, s=64, cmap="coolwarm",
                        vmin=-lim, vmax=lim, edgecolors="0.2", linewidths=0.5, zorder=3)
        fig.colorbar(sc, ax=ax, label="new minus old reprojection residual (px)\n"
                                      "blue = improved, red = worse")
        for p in pts:
            if p in flagged:
                x, y = clicks_by_pk[p][cam]
                ax.scatter([x], [y], s=300, facecolors="none", edgecolors="black",
                           linewidths=1.6, zorder=4)
                ax.annotate(f"ev {nw[p]['event']}\n{o[p]['rep_px']:.1f}->{nw[p]['rep_px']:.1f}",
                            (x, y), textcoords="offset points", xytext=(8, 8), fontsize=7,
                            zorder=6)
        ax.axvspan(RIGHT_EDGE[0], RIGHT_EDGE[1], color="cyan", alpha=0.15, zorder=1)
        ax.set_xlim(0, LT.FRAME_W); ax.set_ylim(LT.FRAME_H, 0); ax.set_aspect("equal")
        ax.set_title(f"{cam}: change in per-point reprojection residual after the left-camera\n"
                     f"plumbline redigitization; cyan band = former right-edge problem region",
                     fontsize=10)
        ax.set_xlabel("screen x (px)"); ax.set_ylabel("screen y (px)"); ax.grid(alpha=0.25)
        p2 = os.path.join(outdir, f"{stem}_repdelta_{cam.split()[0]}.png")
        fig.tight_layout(); fig.savefig(p2, dpi=130); plt.close(fig)
        written.append(p2); say(f"    wrote {os.path.basename(p2)}")
    return written


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="previous cloud_downstream artifact JSON")
    ap.add_argument("--new", required=True, help="current cloud_downstream artifact JSON")
    ap.add_argument("--key", default="8mm", help="document key present in both artifacts")
    ap.add_argument("--label", default="rev2")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--flagged", nargs="*", type=int,
                    default=[658, 662, 709, 665, 650, 661, 701, 655, 660, 646, 659],
                    help="event IDs flagged under the OLD calibration; a FIXED set")
    args = ap.parse_args()
    stem = f"cloud_revision_compare_{args.label}"
    log = open(os.path.join(args.outdir, stem + ".log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    O, Om = load(args.old)
    N, Nm = load(args.new)
    do, dn = doc(O, args.key), doc(N, args.key)
    R = {"inputs": {"old": {"path": os.path.abspath(args.old), "doc_sha256": do["doc_sha256"],
                            "size_bytes": do.get("size_bytes"),
                            "mtime_epoch": do.get("mtime_epoch"),
                            "analysis_started": Om.get("started")},
                    "new": {"path": os.path.abspath(args.new), "doc_sha256": dn["doc_sha256"],
                            "size_bytes": dn.get("size_bytes"),
                            "mtime_epoch": dn.get("mtime_epoch"),
                            "analysis_started": Nm.get("started")}}}
    say("=" * 112)
    say("OLD-VERSUS-NEW COMPARISON AFTER THE LEFT-CAMERA PLUMBLINE REDIGITIZATION")
    say("=" * 112)
    say(f"  OLD artifact {os.path.basename(args.old)}   document SHA-256 {do['doc_sha256']}")
    say(f"  NEW artifact {os.path.basename(args.new)}   document SHA-256 {dn['doc_sha256']}")
    if do["doc_sha256"] == dn["doc_sha256"]:
        say("  *** the two artifacts describe the SAME document; there is nothing to compare ***")
        return 2
    clips = sorted(dn["cameras"])

    # ---- 1. what changed, and what is claimed unchanged
    say(f"\n  [1] WHAT CHANGED. Counts and, where persisted, order-independent point-set hashes.")
    R["inventory"] = {}
    say(f"      ground truth  {'old':>10} {'new':>10}   identical?")
    for k, lab in (("n_conventional", "conventional"), ("n_cloud_points", "cloud points"),
                   ("n_cloud_pairs", "cloud pairs")):
        a, b = do.get(k), dn.get(k)
        say(f"      {lab:22} {str(a):>6} {str(b):>10}   {'yes' if a == b else '*** NO ***'}")
        R["inventory"][k] = {"old": a, "new": b, "identical": a == b}
    say(f"\n      plumblines per camera")
    R["plumblines"] = {}
    for c in clips:
        po = (do.get("plumblines") or {}).get(c)
        pn = (dn.get("plumblines") or {}).get(c)
        if pn is None:
            say(f"        {c:14} NEW artifact records no plumbline provenance")
            continue
        if po is None:
            say(f"        {c:14} OLD artifact records no plumbline provenance (predates the "
                f"2026-07-30 addition), so identity CANNOT be hash-verified; counts only")
            say(f"          new: {pn['n_captures']} capture(s), {pn['n_observations']} observations, "
                f"hull {pn['hull_fraction_all']:.4f}, fitted {pn.get('fitted_n')} on "
                f"{pn.get('fitted_nline')} lines, pointsetSHA {pn['pointset_sha256'][:16]}")
            for cp in pn["captures"]:
                say(f"            tc {cp['timecode']:22} lines {cp['n_lines']:3d} unique "
                    f"{cp['unique_observations']:4d} hull {cp['hull_fraction']:.4f} "
                    f"x {cp['x_range'][0]:.1f}..{cp['x_range'][1]:.1f} "
                    f"y {cp['y_range'][0]:.1f}..{cp['y_range'][1]:.1f}")
            R["plumblines"][c] = {"old_recorded": False, "new": pn}
            continue
        same = po["pointset_sha256"] == pn["pointset_sha256"]
        say(f"        {c:14} observations {po['n_observations']} -> {pn['n_observations']}, "
            f"captures {po['n_captures']} -> {pn['n_captures']}, "
            f"pointset {'IDENTICAL' if same else 'CHANGED'}")
        R["plumblines"][c] = {"old_recorded": True, "identical": same, "old": po, "new": pn}

    # ---- 2. fits: loss, eta, gates
    say(f"\n  [2] PER-CAMERA FITS. Loss is each objective's own and is NOT comparable across "
        f"objectives, nor")
    say(f"      across observation sets of different size, so it is shown for the record rather than "
        f"as a contrast.")
    say(f"      {'camera':14} {'candidate':10} {'loss old':>13} {'loss new':>13} "
        f"{'eta old':>11} {'eta new':>11} {'d eta':>11}")
    R["fits"] = {}
    for c in clips:
        for k in sorted(dn["fits"][c]):
            a, b = do["fits"][c].get(k), dn["fits"][c][k]
            if a is None:
                continue
            say(f"      {c:14} {k:10} {a['loss']:13.5f} {b['loss']:13.5f} "
                f"{a['eta']:+11.7f} {b['eta']:+11.7f} {b['eta'] - a['eta']:+11.7f}")
            R["fits"].setdefault(c, {})[k] = {
                "loss_old": a["loss"], "loss_new": b["loss"],
                "eta_old": a["eta"], "eta_new": b["eta"], "d_eta": b["eta"] - a["eta"],
                "gate_old": a.get("gate"), "gate_new": b.get("gate")}

    # ---- 3. parameter vectors and induced maps
    say(f"\n  [3] PARAMETER VECTORS AND INDUCED MAPS")
    to, tn = do.get("theta14"), dn.get("theta14")
    R["maps"] = {"possible": bool(to and tn)}
    if not (to and tn):
        which = "OLD" if not to else "NEW"
        say(f"      NOT POSSIBLE: the {which} artifact does not persist theta14. Parameter vectors and")
        say(f"      induced-map differences are therefore UNAVAILABLE for this pair. No parameter")
        say(f"      vector has been reconstructed from rounded report summaries, and none should be.")
        say(f"      What IS available instead, and is reported above and below: per-camera loss, eta,")
        say(f"      every physical-map gate summary (radial scale, minimum Jacobian determinant over")
        say(f"      box and frame, maximum local anisotropy, Newton inverse round trip), the")
        say(f"      estimator-neutral calibration node residuals, and every downstream measurement.")
        say(f"      To make this comparison possible in future the current script persists theta14;")
        say(f"      to make it possible for THIS pair the previous .vsd must be recovered and refitted.")
    else:
        for c in clips:
            say(f"\n      {c}")
            for k in [x for x in CANDS if x in tn.get(c, {}) and x in to.get(c, {})]:
                a = np.asarray(to[c][k], float)
                b = np.asarray(tn[c][k], float)
                say(f"        {k}: max |d theta| {np.abs(b - a).max():.6g}, "
                    f"d eta {b[13] - a[13]:+.7f}")
                say(f"          old {np.array2string(a, precision=8, max_line_width=200)}")
                say(f"          new {np.array2string(b, precision=8, max_line_width=200)}")
                say(f"          NOTE: raw coefficient changes are NOT a physical change. The terms are "
                    f"compensating and poorly")
                say(f"          identified individually; only the induced map below is interpretable.")
                st, Dg = map_diff(a, b)
                stR, _ = map_diff(a, b, mask_region=lambda g: (g[:, 0] >= RIGHT_EDGE[0])
                                  & (g[:, 0] <= RIGHT_EDGE[1]))
                say(f"          induced map, common valid domain ({st['common_valid_fraction']:.4f} of "
                    f"frame): median {st['median_px']:.4f}, RMS {st['rms_px']:.4f}, "
                    f"p95 {st['p95_px']:.4f}, max {st['max_px']:.4f} px")
                say(f"          within x in [{RIGHT_EDGE[0]:.0f}, {RIGHT_EDGE[1]:.0f}]: median "
                    f"{stR['median_px']:.4f}, RMS {stR['rms_px']:.4f}, p95 {stR['p95_px']:.4f}, "
                    f"max {stR['max_px']:.4f} px")
                R["maps"].setdefault(c, {})[k] = {
                    "theta14_old": a.tolist(), "theta14_new": b.tolist(),
                    "abs_delta": np.abs(b - a).tolist(),
                    "max_abs_delta": float(np.abs(b - a).max()),
                    "d_eta": float(b[13] - a[13]),
                    "full_frame": st, "right_edge_region": stR,
                    "structure": radial_azimuthal(Dg["grid"], Dg["mag"], Dg["ok"],
                                                  (b[0], b[1]))}
                if k == "PD-D/M1":
                    R.setdefault("figures", []).extend(
                        os.path.basename(p) for p in
                        fig_vector_diff(args.outdir, stem, c, Dg, (b[0], b[1]), say))

    # ---- 4. downstream, old versus new
    say(f"\n  [4] DOWNSTREAM KNOWN-LENGTH, OLD VERSUS NEW")
    R["downstream"] = {}
    for blk, lab in (("group_balanced", "cloud pairs, mean per-cloud MAE"),
                     ("conventional", "conventional MAE")):
        ao = O.get(blk, {}).get(args.key)
        an = N.get(blk, {}).get(args.key)
        if not (ao and an):
            continue
        say(f"\n      {lab}")
        say(f"        {'candidate':10} {'old':>10} {'new':>10} {'change':>10}")
        for k in CANDS:
            if k not in ao or k not in an:
                continue
            va = ao[k].get("mean_per_group_mae", ao[k].get("mae"))
            vb = an[k].get("mean_per_group_mae", an[k].get("mae"))
            say(f"        {k:10} {va:10.4f} {vb:10.4f} {vb - va:+10.4f}")
            R["downstream"].setdefault(blk, {})[k] = {"old": va, "new": vb, "change": vb - va}
    say(f"\n      paired within-estimator contrasts, mean per-group mean d|err| (mm)")
    for blk in ("paired",):
        ao, an = O.get(blk, {}), N.get(blk, {})
        for tg in [t for t in an if t.startswith(args.key)]:
            if tg not in ao:
                continue
            say(f"        {tg}")
            for cn in an[tg]:
                if cn not in ao[tg] or not an[tg][cn].get("available"):
                    continue
                ka = ao[tg][cn].get("mean_per_group_mean_d_abs_err",
                                    ao[tg][cn].get("group_balanced_mean_d_abs_err"))
                kb = an[tg][cn]["mean_per_group_mean_d_abs_err"]
                say(f"          {cn:24} {ka:+9.4f} -> {kb:+9.4f}  "
                    f"(groups improved {ao[tg][cn]['groups_improved']}/"
                    f"{ao[tg][cn]['n_groups']} -> {an[tg][cn]['groups_improved']}/"
                    f"{an[tg][cn]['n_groups']})")
                R["downstream"].setdefault("paired", {}).setdefault(tg, {})[cn] = {
                    "old": ka, "new": kb}

    # ---- 5. per-point, the previously flagged set held FIXED
    say(f"\n  [5] PER-POINT REPROJECTION RESIDUAL, OLD VERSUS NEW")
    ap_o = O.get("audit", {}).get(args.key, {}).get("points", [])
    ap_n = N.get("audit", {}).get(args.key, {}).get("points", [])
    o = {r["pk"]: r for r in ap_o}
    nw = {r["pk"]: r for r in ap_n}
    say(f"      audit candidate: old {O['audit'][args.key]['candidate']}, "
        f"new {N['audit'][args.key]['candidate']}")
    allr_o = np.array([r["rep_px"] for r in ap_o])
    allr_n = np.array([r["rep_px"] for r in ap_n])
    say(f"      all {len(ap_n)} points: median {np.median(allr_o):.3f} -> {np.median(allr_n):.3f} px, "
        f"p90 {np.percentile(allr_o, 90):.3f} -> {np.percentile(allr_n, 90):.3f}, "
        f"max {allr_o.max():.3f} -> {allr_n.max():.3f}")
    fixed = set(args.flagged)
    say(f"\n      the FIXED previously flagged set ({len(fixed)} events), every one of them:")
    say(f"        {'event':>7} {'pk':>6} {'cloud':10} {'rep old':>9} {'rep new':>9} {'change':>9} "
        f"{'incMAE old':>11} {'incMAE new':>11} {'proc old':>9} {'proc new':>9}")
    R["per_point"] = {"fixed_set": sorted(fixed), "rows": []}
    for pk, rn in sorted(nw.items(), key=lambda z: -z[1]["rep_px"]):
        if rn["event"] not in fixed:
            continue
        ro = o.get(pk)
        if ro is None:
            continue
        say(f"        {rn['event']:>7} {pk:>6} {rn['cloud']:10} {ro['rep_px']:9.3f} "
            f"{rn['rep_px']:9.3f} {rn['rep_px'] - ro['rep_px']:+9.3f} "
            f"{ro['incident_mae']:11.3f} {rn['incident_mae']:11.3f} "
            f"{ro['procrustes_resid_mm']:9.3f} {rn['procrustes_resid_mm']:9.3f}")
        R["per_point"]["rows"].append({
            "event": rn["event"], "pk": pk, "cloud": rn["cloud"],
            "rep_old": ro["rep_px"], "rep_new": rn["rep_px"],
            "d_rep": rn["rep_px"] - ro["rep_px"],
            "incident_mae_old": ro["incident_mae"], "incident_mae_new": rn["incident_mae"],
            "incident_bias_old": ro["incident_bias"], "incident_bias_new": rn["incident_bias"],
            "procrustes_old": ro["procrustes_resid_mm"],
            "procrustes_new": rn["procrustes_resid_mm"],
            "lopo_old": ro.get("lopo_dmae"), "lopo_new": rn.get("lopo_dmae"),
            "in_right_edge": bool(RIGHT_EDGE[0] <= rn.get("radius", -1) * 0 +
                                  (rn.get("clicks", {}) or {}).get(clips[0], [0])[0]
                                  <= RIGHT_EDGE[1]) if rn.get("clicks") else None})
    say(f"\n      NEWLY flagged under the new calibration (not in the fixed set):")
    newly = [r for r in ap_n if r["rep_px"] >= 5.0 and r["event"] not in fixed]
    if not newly:
        say(f"        none at >= 5 px, and therefore none at >= 6 px")
    for r in sorted(newly, key=lambda z: -z["rep_px"]):
        ro = o.get(r["pk"])
        say(f"        event {r['event']:>5} pk {r['pk']:>5} {r['cloud']:10} rep "
            f"{(ro['rep_px'] if ro else float('nan')):6.3f} -> {r['rep_px']:6.3f} px")
    R["per_point"]["newly_flagged_ge5"] = [
        {"event": r["event"], "pk": r["pk"], "cloud": r["cloud"],
         "rep_old": (o.get(r["pk"]) or {}).get("rep_px"), "rep_new": r["rep_px"]}
        for r in sorted(newly, key=lambda z: -z["rep_px"])]
    for thr in (5.0, 6.0):
        so = {r["event"] for r in ap_o if r["rep_px"] >= thr}
        sn = {r["event"] for r in ap_n if r["rep_px"] >= thr}
        say(f"      at >= {thr} px: old {len(so)} events {sorted(so)}")
        say(f"                    new {len(sn)} events {sorted(sn)}")
        say(f"                    same set? {'yes' if so == sn else 'no'}; entered "
            f"{sorted(sn - so)}; left {sorted(so - sn)}")
        R["per_point"][f"threshold_{thr}"] = {"old": sorted(so), "new": sorted(sn),
                                              "entered": sorted(sn - so), "left": sorted(so - sn)}

    # ---- 6. per-cloud audit geometry
    say(f"\n  [6] PER-CLOUD RECONSTRUCTION GEOMETRY, OLD VERSUS NEW")
    co = O["audit"][args.key]["clouds"]
    cn2 = N["audit"][args.key]["clouds"]
    say(f"        {'cloud':10} {'procRMS old':>12} {'procRMS new':>12} {'freeScale old':>14} "
        f"{'freeScale new':>14} {'planeRMS old':>13} {'planeRMS new':>13}")
    for g in sorted(cn2):
        a, b = co.get(g), cn2[g]
        if not a:
            continue
        say(f"        {g:10} {a['procrustes_rms_mm']:12.4f} {b['procrustes_rms_mm']:12.4f} "
            f"{a['free_scale']:14.6f} {b['free_scale']:14.6f} {a['plane_rms_mm']:13.4f} "
            f"{b['plane_rms_mm']:13.4f}")
        R.setdefault("clouds", {})[g] = {"old": a, "new": b}

    # ---- figures
    clicks_by_pk = {r["pk"]: r.get("clicks", {}) for r in ap_n}
    figs = fig_point_delta(args.outdir, stem, ap_o, ap_n, clicks_by_pk, clips, say,
                           {r["pk"] for r in ap_n if r["event"] in fixed})
    R.setdefault("figures", []).extend(os.path.basename(p) for p in figs)

    p = os.path.join(args.outdir, stem + ".json")
    json.dump(R, open(p, "w"), indent=1, default=str)
    say(f"\n  wrote {os.path.basename(p)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
