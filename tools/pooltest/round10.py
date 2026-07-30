#!/usr/bin/env python3
"""Production-faithful known-length evaluation of four candidate distortion models.

Sections 3 to 10 of the final round. Calibration is rebuilt by oracle.cpp, which calls the same
Accelerate LAPACK and GSL routines production calls, through production's own ordering (front
uncorrected, back in a four-iteration refractive fixed point with the camera position recomputed each
time). Endpoints are then triangulated by the parity-validated port of VSPoint.m.

Node access goes through nodes.py, the single authoritative accessor: ZCALIBRATION1 is FRONT,
ZCALIBRATION is BACK.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sqlite3
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


nd = L("nodes")
jw = L("jacweight")
pa = L("parity")
st = L("stage2")
Z = L("round9a")
F = L("fitter")
S = Z.S
# HISTORICAL SCRIPT / NON-AUTHORITATIVE. Was `pa.undistort = nd.undistort13`, a silent import-time
# monkeypatch; now the explicit reason-carrying hook. Do not import this module for reusable
# functionality -- current work uses downstream.DistortionMap, which is camera-bound and 14-parameter.
pa.install_historical_eta_map(
    nd.undistort13,
    reason="reproducing the frozen round-10 fisheye 14-parameter evaluation, published with "
           "parity.sightline/triangulate made eta-aware process-wide")

FULL13 = list(range(13))
MODELS = [("stored", None), ("conv-13", FULL13), ("trunc-10", Z.ISO), ("trunc+eta", Z.SCAL)]
DOCS = st.DOCS


class PL:
    def __init__(self, xy):
        self.xy = np.asarray(xy, float); self.sref = 0.0


def fit_model(clip_obj, free, seeds):
    g = Z.G(clip_obj.xy, clip_obj.counts)
    held = [j for j in range(15) if j not in free]
    ss = []
    for s in seeds:
        s = s.copy(); s[held] = 0.0; ss.append(s)
    rr = np.random.default_rng(4)
    for _ in range(4):
        s = ss[rr.integers(0, len(ss))].copy()
        s[np.array(free)] += rr.normal(0, 0.03, len(free)); ss.append(s)
    if 13 in free:
        for e in (-0.02, 0.01, 0.02, 0.04):
            s = ss[0].copy(); s[13] = e; ss.append(s)
            s2 = ss[0].copy(); s2[held] = 0.0; s2[13] = e
    (v, sse, _), allc = Z.best_fit(g, free, ss, allsse=True)
    return v, math.sqrt(sse / g.n), sorted(allc)[:3], g


def stored_to_v(d13):
    v = np.zeros(15)
    v[0] = (d13[0] - S.W / 2) / S.R; v[1] = (d13[1] - S.H / 2) / S.R
    for j in range(7):
        v[2 + j] = d13[2 + j] * S.R ** (2 * (j + 1))
    v[9] = d13[9] * S.R; v[10] = d13[10] * S.R
    v[11] = d13[11] * S.R ** 2; v[12] = d13[12] * S.R ** 4
    return v


def build_cam(c, dist14):
    o = st.run_oracle(c, dist=dist14[:13], eta=dist14[13])
    return {"ah": c["ah"], "av": c["av"], "front_d": c["front_d"], "back_d": c["back_d"],
            "dist": dist14, "cam": o["cam"], "camPLD": o["camPLD"],
            "s2f": nd.flat_colmajor_to_nested(o["FRONT"]),
            "s2b": nd.flat_colmajor_to_nested(o["BACK"]),
            "f2s": nd.flat_colmajor_to_nested(o["FRONTINV"]), "oracle": o}


def stats(err):
    e = np.abs(np.asarray(err)); s = np.asarray(err)
    return {"n": len(e), "mae": e.mean(), "rmse": math.sqrt((s ** 2).mean()),
            "med": float(np.median(e)), "bias": s.mean(),
            "p75": float(np.percentile(e, 75)), "p90": float(np.percentile(e, 90)),
            "p95": float(np.percentile(e, 95)), "max": e.max()}


def main():
    t0 = time.time()
    say = print
    for label, vsd, tf, unit in DOCS:
        say("\n" + "=" * 104)
        say(label)
        say("=" * 104)
        cals = st.load_cal(vsd)
        db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
        for clip, c in cals.items():
            nd.assert_node_orientation(db, c["pk"], c["s2f"], c["s2b"], c["dist"], clip)
        # measured points, with timecode for replication structure
        sql = ("SELECT o.ZNAME2, t.ZNAME3, e.Z_PK, p.Z_PK, p.ZINDEX, p.ZTIMECODE "
               "FROM ZVSVISIBLEITEM e "
               "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK "
               "JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS "
               "JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1 "
               "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK WHERE e.Z_ENT = 17")
        args = ()
        if tf:
            sql += " AND t.ZNAME3 = ?"; args = (tf,)
        ev = defaultdict(list); meta = {}
        for nm, tn, e, pk, idx, tc in db.execute(sql + " ORDER BY e.Z_PK, p.ZINDEX", args):
            ev[e].append(pk); meta[e] = (nm, tn, tc)
        clicks = defaultdict(dict)
        for pt, cl, x, y in db.execute(
                "SELECT p.ZPOINT, v.ZCLIPNAME, p.ZSCREENX, p.ZSCREENY FROM ZVSSCREENPOINT p "
                "JOIN ZVSVIDEOCLIP v ON v.Z_PK = p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
            clicks[pt][cl] = (x, y)
        db.close()

        # ---- fit each model on each camera and rebuild the calibration
        dists, diag = {}, {}
        for mname, free in MODELS:
            dists[mname] = {}
            for clip in sorted(cals):
                c = cals[clip]
                if free is None:
                    d14 = list(c["dist"]) + [0.0]
                    prms = float("nan"); basins = []
                else:
                    co = S.Clip(vsd, clip)
                    sv = stored_to_v(c["dist"])
                    s0 = np.zeros(15)
                    s0[0] = (co.centre0[0] - S.W / 2) / S.R
                    s0[1] = (co.centre0[1] - S.H / 2) / S.R
                    v, prms, basins, g = fit_model(co, free, [s0, sv])
                    cq, kq, pq, eq, _ = Z.nphys(v)
                    d14 = [cq[0], cq[1], *kq, *pq, eq]
                dists[mname][clip] = d14
                pl = PL(S.Clip(vsd, clip).xy)
                gr = F.gate_report(np.array(d14[:13]), pl, sref=0.0, frame=(1920.0, 1080.0))
                cam = build_cam(c, d14)
                fr, fmx = nd._rms_max(c["front"], cam["s2f"], d14)
                br, bmx = nd._rms_max(c["back"], cam["s2b"], d14)
                diag[(mname, clip)] = {"prms": prms, "gate": gr, "cam": cam,
                                       "fr": fr, "fmx": fmx, "br": br, "bmx": bmx,
                                       "eta": d14[13], "basins": basins}

        say(f"\n  CALIBRATION DIAGNOSTICS  (world units "
            f"{'m, shown in mm' if unit == 1000.0 else 'mm'})")
        say(f"    {'model':10} {'camera':14} {'plumb px':>9} {'eta':>10} {'R_scale':>8} "
            f"{'minDet':>8} {'spread':>7} {'cond':>7} {'frontRMS':>9} {'backRMS':>9} "
            f"{'camPLD':>9} {'gate':>5}")
        for mname, _ in MODELS:
            for clip in sorted(cals):
                d = diag[(mname, clip)]; gr = d["gate"]
                say(f"    {mname:10} {clip:14} {d['prms']:9.4f} {d['eta']:+10.6f} "
                    f"{gr['radial_scale_ratio']:8.4f} {gr['min_det_box']:8.4f} "
                    f"{gr['area_scale_spread']:7.3f} {gr['jac_condition']:7.3f} "
                    f"{d['fr']*unit:9.4f} {d['br']*unit:9.4f} "
                    f"{d['cam']['camPLD']*unit:9.4f} {'ok' if gr['ok'] else 'FAIL':>5}")

        # ---- eta = 0 nesting check, all the way downstream
        clip0 = sorted(cals)[0]
        d10 = list(dists["trunc-10"][clip0])
        dz = list(d10[:13]) + [0.0]
        a = build_cam(cals[clip0], d10); b = build_cam(cals[clip0], dz)
        mdiff = max(abs(x - y) for r1, r2 in zip(a["s2f"], b["s2f"]) for x, y in zip(r1, r2))
        mdiff = max(mdiff, max(abs(x - y) for r1, r2 in zip(a["s2b"], b["s2b"])
                               for x, y in zip(r1, r2)))
        say(f"\n  eta = 0 nesting: max homography coefficient difference {mdiff:.2e}, "
            f"camera position difference {math.dist(a['cam'], b['cam'])*unit:.2e} mm")

        # ---- triangulate every endpoint under every model
        res = {}
        for mname, _ in MODELS:
            built = {cl: diag[(mname, cl)]["cam"] for cl in cals}
            rows = []
            for e, pks in sorted(ev.items()):
                if len(pks) != 2:
                    continue
                true = jw.true_length_mm(meta[e][0], meta[e][1], unit)
                if true is None:
                    continue
                P = []
                for pk in pks:
                    obs = [(built[cl], clicks[pk][cl]) for cl in sorted(built)
                           if cl in clicks.get(pk, {})]
                    if len(obs) < 2:
                        P = None; break
                    P.append(pa.triangulate(obs)[0])
                if P is None:
                    continue
                Lm = float(np.linalg.norm(np.array(P[0], np.float32)
                                          - np.array(P[1], np.float32))) * unit
                rows.append({"e": e, "obj": meta[e][0], "tc": meta[e][2], "true": true,
                             "meas": Lm, "err": Lm - true, "X": P})
            res[mname] = rows
        say(f"\n  KNOWN-LENGTH ACCURACY (mm), n = {len(res['stored'])}")
        say(f"    {'model':10} {'MAE':>8} {'RMSE':>8} {'median':>8} {'bias':>8} {'p75':>8} "
            f"{'p90':>8} {'p95':>8} {'max':>9} {'rel%':>7}")
        for mname, _ in MODELS:
            s = stats([r["err"] for r in res[mname]])
            rel = float(np.mean([abs(r["err"]) / r["true"] for r in res[mname]])) * 100
            say(f"    {mname:10} {s['mae']:8.4f} {s['rmse']:8.4f} {s['med']:8.4f} "
                f"{s['bias']:+8.4f} {s['p75']:8.4f} {s['p90']:8.4f} {s['p95']:8.4f} "
                f"{s['max']:9.4f} {rel:7.3f}")

        # ---- replication structure
        objs = sorted({r["obj"] for r in res["stored"]})
        tcs = sorted({r["tc"] for r in res["stored"] if r["tc"]})
        say(f"\n  REPLICATION STRUCTURE: {len(res['stored'])} measurements, "
            f"{len(objs)} distinct objects, {len(tcs)} distinct timecodes, "
            f"1 shared calibration per camera")
        for o in objs:
            k = [r for r in res["stored"] if r["obj"] == o]
            ktc = len({r["tc"] for r in k if r["tc"]})
            say(f"    {str(o):30} n {len(k):5d}  distinct timecodes {ktc:5d}")

        # ---- paired contrasts with cluster bootstrap over the highest defensible unit
        say(f"\n  PAIRED CONTRASTS (change in absolute error, mm; negative = improvement)")
        say(f"    {'contrast':34} {'mean':>9} {'median':>9} {'better/worse':>14} "
            f"{'cluster 5-95%':>22}")
        pairs = [("stored", "conv-13"), ("stored", "trunc-10"),
                 ("trunc-10", "trunc+eta"), ("stored", "trunc+eta")]
        clus_key = "tc" if len(tcs) >= 8 else "obj"
        for A, B in pairs:
            ea = np.array([abs(r["err"]) for r in res[A]])
            eb = np.array([abs(r["err"]) for r in res[B]])
            d = eb - ea
            keys = np.array([res[A][i][clus_key] if res[A][i][clus_key] else "none"
                             for i in range(len(d))])
            uk = np.unique(keys)
            if len(uk) >= 5:
                rng = np.random.default_rng(11)
                bs = []
                for _ in range(2000):
                    pick = rng.choice(uk, size=len(uk), replace=True)
                    idx = np.concatenate([np.where(keys == k)[0] for k in pick])
                    bs.append(d[idx].mean())
                ci = f"[{np.percentile(bs,5):+.4f}, {np.percentile(bs,95):+.4f}]"
            else:
                ci = f"only {len(uk)} clusters"
            say(f"    {A} -> {B:24} {d.mean():+9.4f} {np.median(d):+9.4f} "
                f"{int((d<0).sum()):6d}/{int((d>0).sum()):<7d} {ci:>22}")
        say(f"    cluster unit for resampling: {clus_key} ({len(np.unique(keys))} clusters); "
            f"all measurements share one calibration, so intervals are conditional on it")

        # ---- common-mode vs differential endpoint movement
        say(f"\n  ENDPOINT MOVEMENT DECOMPOSITION")
        say(f"    {'contrast':34} {'|common|':>10} {'|diff|':>10} {'along':>10} "
            f"{'perp':>10} {'com/diff':>9} {'dL exact':>10} {'dL linear':>10}")
        for A, B in (("trunc-10", "trunc+eta"), ("stored", "conv-13"), ("stored", "trunc+eta")):
            com, dif, alo, per, dle, dll = [], [], [], [], [], []
            for ra, rb in zip(res[A], res[B]):
                X1, X2 = np.array(ra["X"][0]), np.array(ra["X"][1])
                Y1, Y2 = np.array(rb["X"][0]), np.array(rb["X"][1])
                dX1, dX2 = Y1 - X1, Y2 - X2
                cm = 0.5 * (dX1 + dX2); df = dX2 - dX1
                dh = (X2 - X1) / max(np.linalg.norm(X2 - X1), 1e-30)
                com.append(np.linalg.norm(cm) * unit); dif.append(np.linalg.norm(df) * unit)
                alo.append(abs(float(dh @ df)) * unit)
                per.append(np.linalg.norm(df - float(dh @ df) * dh) * unit)
                dle.append(rb["meas"] - ra["meas"]); dll.append(float(dh @ df) * unit)
            com, dif = np.array(com), np.array(dif)
            say(f"    {A} -> {B:24} {np.median(com):10.4f} {np.median(dif):10.4f} "
                f"{np.median(alo):10.4f} {np.median(per):10.4f} "
                f"{np.median(com/np.maximum(dif,1e-12)):9.2f} "
                f"{np.median(np.abs(dle)):10.4f} {np.median(np.abs(dll)):10.4f}")
            if A == "trunc-10":
                mx = float(np.max(np.abs(np.array(dle) - np.array(dll))))
                say(f"      first-order length change agrees with exact to {mx:.2e} mm (max)")

        # ---- support covariates and strata
        cov = []
        built = {cl: diag[("trunc-10", cl)]["cam"] for cl in cals}
        for i, r in enumerate(res["stored"]):
            rads, depths = [], []
            for pk in ev[r["e"]]:
                for cl in sorted(built):
                    if cl in clicks.get(pk, {}):
                        cc = built[cl]["dist"]
                        x, y = clicks[pk][cl]
                        rads.append(math.hypot(x - cc[0], y - cc[1]))
            ax = pa.AX[({"x", "y", "z"} - {list(cals.values())[0]["ah"],
                                           list(cals.values())[0]["av"]}).pop()]
            fd = list(cals.values())[0]["front_d"]; bd = list(cals.values())[0]["back_d"]
            for P in r["X"]:
                depths.append(P[ax])
            lo, hi = min(fd, bd), max(fd, bd)
            outd = max(0.0, max(max(depths) - hi, lo - min(depths))) * unit
            cov.append({"rmax": max(rads), "rmean": float(np.mean(rads)),
                        "rsep": max(rads) - min(rads), "outdepth": outd})
        say(f"\n  SUPPORT: endpoint image radius and depth extrapolation")
        say(f"    max radius median {np.median([c['rmax'] for c in cov]):.0f} px, "
            f"90th {np.percentile([c['rmax'] for c in cov],90):.0f} px; "
            f"radial separation median {np.median([c['rsep'] for c in cov]):.0f} px")
        outd = np.array([c["outdepth"] for c in cov])
        say(f"    outside the calibrated depth interval: {int((outd>0).sum())} of {len(outd)} "
            f"measurements, median excess {np.median(outd[outd>0]) if (outd>0).any() else 0:.1f} mm")
        ea = np.array([abs(r["err"]) for r in res["trunc-10"]])
        eb = np.array([abs(r["err"]) for r in res["trunc+eta"]])
        d = eb - ea
        for nm, mask in (("inside depth interval", outd <= 0), ("outside depth interval", outd > 0),
                         ("inner half by radius",
                          np.array([c["rmax"] for c in cov]) <= np.median([c["rmax"] for c in cov])),
                         ("outer half by radius",
                          np.array([c["rmax"] for c in cov]) > np.median([c["rmax"] for c in cov])),
                         ("endpoints at similar radii",
                          np.array([c["rsep"] for c in cov]) <= np.median([c["rsep"] for c in cov])),
                         ("endpoints spanning radii",
                          np.array([c["rsep"] for c in cov]) > np.median([c["rsep"] for c in cov]))):
            if mask.sum() == 0:
                continue
            say(f"      eta effect, {nm:28} n {int(mask.sum()):5d}  mean "
                f"{d[mask].mean():+.4f} mm  median {np.median(d[mask]):+.4f}")

        if len(res["stored"]) <= 20:
            say(f"\n  INDIVIDUAL MEASUREMENTS")
            say(f"    {'obj':10} {'true':>7} " + " ".join(f"{m:>9}" for m, _ in MODELS) +
                f" {'eta gain':>9} {'conv gain':>10} {'rmax':>7} {'outD':>7}")
            for i, r in enumerate(res["stored"]):
                errs = [res[m][i]["err"] for m, _ in MODELS]
                eg = abs(res["trunc+eta"][i]["err"]) - abs(res["trunc-10"][i]["err"])
                cg = abs(res["conv-13"][i]["err"]) - abs(res["stored"][i]["err"])
                say(f"    {str(r['obj'])[:10]:10} {r['true']:7.1f} " +
                    " ".join(f"{v:+9.3f}" for v in errs) +
                    f" {eg:+9.3f} {cg:+10.3f} {cov[i]['rmax']:7.0f} {cov[i]['outdepth']:7.1f}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
