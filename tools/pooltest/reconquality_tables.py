#!/usr/bin/env python3
"""Compact human-readable exports from a reconquality artifact, plus candidate-frozen profile plots.

ANALYSIS ONLY. Reads an existing reconquality_<label>.json; computes nothing new about the models.

Two products:
  1. `reconquality_percloud_<label>.csv` and a printed table: for both PD-D and B, per cloud, the M0 and
     M1 scale s, log s and |log s|, the change in |log s|, similarity RMS, normalized deformation, plane
     RMS, local-edge RMS log error, and the LEFT and RIGHT camera LOPO RMS kept separate.
  2. Candidate-frozen difficulty PROFILES as actual plots: paired M1-minus-M0 against image radius,
     image azimuth, true edge length, physical edge orientation, M0 reference depth, M0 triangulation
     angle, and calibration support class. Points and edges are plotted descriptively with a LOESS-style
     local mean; they are NOT treated as independent sampling units and the cloud remains the
     aggregation unit, so every panel also carries the per-cloud means as large markers.
"""

import argparse
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "analysis-output")


def local_mean(x, y, nwin=9):
    """Running local mean over the x-order, purely descriptive smoothing. No inference is attached."""
    o = np.argsort(x)
    xs, ys = np.asarray(x, float)[o], np.asarray(y, float)[o]
    if len(xs) < 3:
        return xs, ys
    k = max(3, min(nwin, len(xs) // 3 * 2 + 1))
    sm = np.convolve(ys, np.ones(k) / k, mode="valid")
    xm = np.convolve(xs, np.ones(k) / k, mode="valid")
    return xm, sm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(OUT, "reconquality_v2.json"))
    ap.add_argument("--label", default="v2")
    ap.add_argument("--outdir", default=OUT)
    args = ap.parse_args()
    R = json.load(open(args.json))
    log = open(os.path.join(args.outdir, f"reconquality_tables_{args.label}.log"), "w")

    def say(s=""):
        print(s); log.write(s + "\n"); log.flush()

    # ---------------------------------------------------------------- per-cloud table
    cols = ["recording", "focal_mm", "cloud", "obj_pk", "k", "estimator",
            "s_M0", "s_M1", "log_s_M0", "log_s_M1", "abs_log_s_M0", "abs_log_s_M1",
            "d_abs_log_s", "rms_sim_M0_mm", "rms_sim_M1_mm",
            "norm_deform_M0", "norm_deform_M1", "plane_rms_M0_mm", "plane_rms_M1_mm",
            "edge_rms_log_M0", "edge_rms_log_M1",
            "lopo_left_M0_px", "lopo_left_M1_px", "lopo_right_M0_px", "lopo_right_M1_px",
            "mean_camdist_mm", "mean_outside_cal_volume_mm"]
    rows = []
    for key, C in R.get("clouds", {}).items():
        foc = R["documents"][key].get("focal_mm_metadata")
        pc = C["per_candidate"]
        for est in ("PD-D", "B"):
            m0, m1 = f"{est}/M0", f"{est}/M1"
            if m0 not in pc or m1 not in pc:
                continue
            for g in sorted(pc[m0]):
                if g not in pc[m1]:
                    continue
                a, b = pc[m0][g], pc[m1][g]

                def lop(p, cam):
                    h = p.get("heldout") or {}
                    return (h.get("per_camera", {}).get(cam, {}) or {}).get("rms_px", float("nan"))
                rows.append({
                    "recording": key, "focal_mm": foc, "cloud": g, "obj_pk": a.get("obj_pk"),
                    "k": a["k"], "estimator": est,
                    "s_M0": a["scale"]["s"], "s_M1": b["scale"]["s"],
                    "log_s_M0": a["scale"]["log_s"], "log_s_M1": b["scale"]["log_s"],
                    "abs_log_s_M0": a["scale"]["abs_log_s"], "abs_log_s_M1": b["scale"]["abs_log_s"],
                    "d_abs_log_s": b["scale"]["abs_log_s"] - a["scale"]["abs_log_s"],
                    "rms_sim_M0_mm": a["shape"]["rms_sim_mm"], "rms_sim_M1_mm": b["shape"]["rms_sim_mm"],
                    "norm_deform_M0": a["shape"]["normalized_deformation"],
                    "norm_deform_M1": b["shape"]["normalized_deformation"],
                    "plane_rms_M0_mm": a["plane"]["rms_mm"], "plane_rms_M1_mm": b["plane"]["rms_mm"],
                    "edge_rms_log_M0": a["edges"].get("rms_log"),
                    "edge_rms_log_M1": b["edges"].get("rms_log"),
                    "lopo_left_M0_px": lop(a, "Left Camera"), "lopo_left_M1_px": lop(b, "Left Camera"),
                    "lopo_right_M0_px": lop(a, "Right Camera"),
                    "lopo_right_M1_px": lop(b, "Right Camera"),
                    "mean_camdist_mm": a["support"]["mean_camdist_mm"],
                    "mean_outside_cal_volume_mm": a["support"]["mean_outside_cal_volume_mm"]})
    p = os.path.join(args.outdir, f"reconquality_percloud_{args.label}.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    say(f"wrote {os.path.basename(p)}  ({len(rows)} cloud x estimator rows)")

    for est in ("PD-D", "B"):
        say(f"\n{'=' * 150}\nPER-CLOUD PANEL -- {est}   (d|log s| < 0 means the SCALE ERROR fell)\n"
            f"{'=' * 150}")
        say(f"{'recording':14}{'cloud':9}{'k':>3} {'s M0':>9}{'s M1':>9} {'|logs|M0':>10}"
            f"{'|logs|M1':>10}{'d|logs|':>10} {'simRMS M0':>10}{'simRMS M1':>10} "
            f"{'nDef M0':>9}{'nDef M1':>9} {'plane M0':>9}{'plane M1':>9} "
            f"{'edge M0':>9}{'edge M1':>9} {'LopoL M0':>9}{'LopoL M1':>9}"
            f"{'LopoR M0':>9}{'LopoR M1':>9}")
        for r in [x for x in rows if x["estimator"] == est]:
            say(f"{r['recording']:14}{r['cloud']:9}{r['k']:>3} {r['s_M0']:>9.6f}{r['s_M1']:>9.6f} "
                f"{r['abs_log_s_M0']:>10.6f}{r['abs_log_s_M1']:>10.6f}{r['d_abs_log_s']:>+10.6f} "
                f"{r['rms_sim_M0_mm']:>10.4f}{r['rms_sim_M1_mm']:>10.4f} "
                f"{r['norm_deform_M0']:>9.6f}{r['norm_deform_M1']:>9.6f} "
                f"{r['plane_rms_M0_mm']:>9.4f}{r['plane_rms_M1_mm']:>9.4f} "
                f"{(r['edge_rms_log_M0'] or float('nan')):>9.6f}"
                f"{(r['edge_rms_log_M1'] or float('nan')):>9.6f} "
                f"{r['lopo_left_M0_px']:>9.4f}{r['lopo_left_M1_px']:>9.4f}"
                f"{r['lopo_right_M0_px']:>9.4f}{r['lopo_right_M1_px']:>9.4f}")

    # ---------------------------------------------------------------- profile plots
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                                   # noqa: BLE001
        say(f"profile plots skipped: {e}")
        json.dump({"rows": rows}, open(os.path.join(args.outdir,
                  f"reconquality_tables_{args.label}.json"), "w"), indent=1, default=str)
        return 0

    figs = []
    for key, dp in R.get("difficulty_profiles", {}).items():
        pts = dp.get("point_level") or []
        edg = dp.get("edge_level") or []
        if not pts:
            continue
        panels = []
        for cam in sorted({p["camera"] for p in pts}):
            sub = [p for p in pts if p["camera"] == cam and p.get("d_heldout_px") is not None]
            panels.append((f"image radius, {cam}", "image_radius_px", "d_heldout_px", sub,
                           "M1-M0 held-out px"))
            panels.append((f"image azimuth, {cam}", "image_azimuth_deg", "d_heldout_px", sub,
                           "M1-M0 held-out px"))
            panels.append((f"M0 reference depth, {cam}", "reference_depth_mm", "d_heldout_px", sub,
                           "M1-M0 held-out px"))
            panels.append((f"M0 ray-miss, {cam}", "ray_miss_mm", "d_heldout_px", sub,
                           "M1-M0 held-out px"))
        panels.append(("true edge length", "true_mm", "d_abs_log", edg, "M1-M0 |log ratio|"))
        panels.append(("edge kind (0 neighbour, 1 diagonal)", "_kind", "d_abs_log", edg,
                       "M1-M0 |log ratio|"))
        prof = dp.get("cloud_level_profiles", {})
        n = len(panels)
        ncol = 4
        nrow = int(math.ceil((n + 2) / ncol))
        fig, ax = plt.subplots(nrow, ncol, figsize=(5.2 * ncol, 3.7 * nrow), squeeze=False)
        for i, (title, xk, yk, data, ylab) in enumerate(panels):
            a = ax[i // ncol][i % ncol]
            xs, ys = [], []
            for d in data:
                xv = (1.0 if d.get("kind") == "diagonal" else 0.0) if xk == "_kind" else d.get(xk)
                yv = d.get(yk)
                if xv is None or yv is None or not (np.isfinite(xv) and np.isfinite(yv)):
                    continue
                xs.append(float(xv)); ys.append(float(yv))
            if not xs:
                a.set_visible(False); continue
            a.axhline(0.0, color="0.6", lw=0.8)
            a.scatter(xs, ys, s=9, alpha=0.35, color="tab:blue", label="observation (descriptive)")
            xm, sm = local_mean(xs, ys)
            a.plot(xm, sm, color="crimson", lw=1.8, label="local mean (descriptive)")
            # cloud means as the ACTUAL aggregation unit
            byc = {}
            for d in data:
                xv = (1.0 if d.get("kind") == "diagonal" else 0.0) if xk == "_kind" else d.get(xk)
                yv = d.get(yk)
                if xv is None or yv is None or not (np.isfinite(xv) and np.isfinite(yv)):
                    continue
                byc.setdefault(d["cloud"], [[], []])
                byc[d["cloud"]][0].append(float(xv)); byc[d["cloud"]][1].append(float(yv))
            a.scatter([np.mean(v[0]) for v in byc.values()], [np.mean(v[1]) for v in byc.values()],
                      s=150, marker="D", facecolors="none", edgecolors="black", linewidths=1.6,
                      label="cloud mean (aggregation unit)", zorder=5)
            a.set_title(f"{key}: {title}", fontsize=9)
            a.set_xlabel(xk); a.set_ylabel(ylab, fontsize=8); a.grid(alpha=0.25)
            if i == 0:
                a.legend(fontsize=7, loc="best")
        # cloud-level support-class panel
        j = n
        a = ax[j // ncol][j % ncol]
        rowsc = prof.get("mean_outside_cal_volume_mm") or []
        if rowsc:
            a.axhline(0.0, color="0.6", lw=0.8)
            a.plot([r["covariate"] for r in rowsc], [r["d_shape_rms_mm"] for r in rowsc],
                   "o-", label="d similarity RMS (mm)")
            a.plot([r["covariate"] for r in rowsc], [r["d_edge_rms_log"] for r in rowsc],
                   "s--", label="d edge RMS log")
            a.set_title(f"{key}: calibration support (cloud level)", fontsize=9)
            a.set_xlabel("mean mm outside calibrated node volume"); a.grid(alpha=0.25)
            a.legend(fontsize=7)
        else:
            a.set_visible(False)
        j += 1
        a = ax[j // ncol][j % ncol]
        rowsd = prof.get("mean_camdist_mm") or []
        if rowsd:
            a.axhline(0.0, color="0.6", lw=0.8)
            a.plot([r["covariate"] for r in rowsd], [r["d_log_s"] for r in rowsd], "o-",
                   label="d signed log s")
            a.set_title(f"{key}: M0 reference distance (cloud level)", fontsize=9)
            a.set_xlabel("mean camera distance (mm)"); a.grid(alpha=0.25); a.legend(fontsize=7)
        else:
            a.set_visible(False)
        for i in range(j + 1, nrow * ncol):
            ax[i // ncol][i % ncol].set_visible(False)
        pth = os.path.join(args.outdir,
                           f"reconquality_profiles_{args.label}_{key.replace('/', '_')}.png")
        fig.suptitle(f"{key}: candidate-frozen difficulty profiles, PD-D M1 minus M0. Points and edges "
                     f"are DESCRIPTIVE, not independent sampling units.", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.97)); fig.savefig(pth, dpi=110); plt.close(fig)
        figs.append(os.path.basename(pth))
        say(f"wrote {os.path.basename(pth)}")
    json.dump({"rows": rows, "figures": figs},
              open(os.path.join(args.outdir, f"reconquality_tables_{args.label}.json"), "w"),
              indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
