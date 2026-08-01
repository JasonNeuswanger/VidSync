#!/usr/bin/env python3
"""Cal A / Cal B pool-test calibration-geometry sensitivity experiment.

XML supplies ONLY raw frame-node clicks and their world coordinates. All distortion candidates come
from the current .vsd plumblines; all physical metadata (plane depths, pane, indices, axes) is
inherited from the .vsd and that inheritance is reported. XML distortion, xu/yu, homographies, camera
positions and 3D coordinates are historical outputs and are not used.

Run with ~/.venvs/vidsync/bin/python.
"""
import importlib.util, math, os, re, sqlite3, sys, time
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
nd, jw, pa, st, Z, F = L("nodes"), L("jacweight"), L("parity"), L("stage2"), L("round9a"), L("fitter")
S = Z.S
# HISTORICAL SCRIPT / NON-AUTHORITATIVE. Was `pa.undistort = nd.undistort13`, a silent import-time
# monkeypatch; now the explicit reason-carrying hook. Do not import for reusable functionality.
pa.install_historical_eta_map(
    nd.undistort13,
    reason="reproducing the frozen Cal A/B pool-test node-placement sensitivity analysis, published "
           "with parity.sightline/triangulate made eta-aware process-wide")
XD = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/Papers/"
      "2010 3D Video Methods/2012 Pool Test - 2016 Cal%s.xml")
POOL = ("/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/"
        "2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd")
FULL13 = list(range(13))
MODELS = [("stored", None), ("conv-13", FULL13), ("trunc", Z.ISO), ("trunc+eta", Z.SCAL)]
UNIT = 1000.0


def parse_xml(tag):
    s = open(XD % tag, encoding="utf-8").read()
    tc = re.search(r'calibrationTimecode="([^"]+)"', s).group(1)
    out = {}
    # The [^>]* tolerates the clip metadata attributes that follow the name as of export format version 2.
    for m in re.finditer(r'<videoClip name="([^"]+)"[^>]*>(.*?)</videoClip>', s, re.S):
        clip, blk = m.group(1), m.group(2)
        d = {}
        for nm, t in (("front", "frontCalibrationPoints"), ("back", "backCalibrationPoints")):
            seg = re.search("<" + t + ">(.*?)</" + t + ">", blk, re.S).group(1)
            d[nm] = [(float(a["x"]), float(a["y"]), float(a["worldHcoord"]), float(a["worldVcoord"]))
                     for a in (dict(re.findall(r'(\w+)="([^"]*)"', mm.group(1)))
                               for mm in re.finditer(r"<screenpoint ([^>]*)></screenpoint>", seg))]
        out[clip] = d
    return tc, out


class PL:
    def __init__(self, xy): self.xy = np.asarray(xy, float); self.sref = 0.0


def stored_v(d13):
    v = np.zeros(15)
    v[0] = (d13[0] - S.W / 2) / S.R; v[1] = (d13[1] - S.H / 2) / S.R
    for j in range(7): v[2 + j] = d13[2 + j] * S.R ** (2 * (j + 1))
    v[9] = d13[9] * S.R; v[10] = d13[10] * S.R
    v[11] = d13[11] * S.R ** 2; v[12] = d13[12] * S.R ** 4
    return v


def stats(e):
    a = np.abs(np.asarray(e))
    return dict(n=len(a), mae=a.mean(), rmse=math.sqrt((np.asarray(e) ** 2).mean()),
                med=np.median(a), p75=np.percentile(a, 75), p90=np.percentile(a, 90),
                p95=np.percentile(a, 95), p99=np.percentile(a, 99), mx=a.max(),
                w10=a[a >= np.percentile(a, 90)].mean(), w5=a[a >= np.percentile(a, 95)].mean(),
                bias=np.asarray(e).mean())


def cboot(d, keys, n=2000, seed=7):
    uk = np.unique(keys)
    if len(uk) < 5: return None
    rng = np.random.default_rng(seed); out = []
    idxs = {k: np.where(keys == k)[0] for k in uk}
    for _ in range(n):
        pick = rng.choice(uk, size=len(uk), replace=True)
        out.append(d[np.concatenate([idxs[k] for k in pick])].mean())
    return float(np.percentile(out, 5)), float(np.percentile(out, 95))


def main():
    t0 = time.time(); say = print
    say("=" * 100); say("CAL A / CAL B POOL-TEST CALIBRATION-GEOMETRY EXPERIMENT"); say("=" * 100)
    tcA, XA = parse_xml("A"); tcB, XB = parse_xml("B")
    db = sqlite3.connect(f"file:{POOL}?mode=ro", uri=True)
    base = st.load_cal(POOL)
    say(f"\n  Cal A timecode {tcA}   Cal B timecode {tcB}")
    say(f"  inherited from the .vsd for BOTH calibrations (not serialized in the XML): "
        f"front plane {list(base.values())[0]['front_d']}, back plane "
        f"{list(base.values())[0]['back_d']}, pane {list(base.values())[0]['thick']} m, "
        f"pane index {list(base.values())[0]['n2']}, medium {list(base.values())[0]['n1']}, "
        f"refraction on, axes {list(base.values())[0]['ah']}{list(base.values())[0]['av']}")
    for tag, X in (("A", XA), ("B", XB)):
        for clip in sorted(X):
            say(f"    Cal {tag} {clip:13} {len(X[clip]['front'])}F/{len(X[clip]['back'])}B nodes")
    # Cal A import validation against the .vsd node clicks
    for clip in sorted(XA):
        vf = nd.front_calibration_nodes(db, base[clip]["pk"])
        vb = nd.back_calibration_nodes(db, base[clip]["pk"])
        for nm, xs, vs in (("front", XA[clip]["front"], vf), ("back", XA[clip]["back"], vb)):
            e = []
            for x in xs:
                b = min(vs, key=lambda v: (v[2] - x[2]) ** 2 + (v[3] - x[3]) ** 2)
                if math.hypot(b[2] - x[2], b[3] - x[3]) < 1e-6:
                    e.append(math.hypot(b[0] - x[0], b[1] - x[1]))
            say(f"    Cal A {clip:13} {nm:5} matched {len(e)}/{len(xs)}, click diff max "
                f"{max(e):.2e} px")
    # measurements
    ev = defaultdict(list); meta = {}
    for nm_, tn, e, pk, tc in db.execute(
            "SELECT o.ZNAME2,t.ZNAME3,e.Z_PK,p.Z_PK,p.ZTIMECODE FROM ZVSVISIBLEITEM e "
            "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS=e.Z_PK "
            "JOIN ZVSVISIBLEITEM o ON o.Z_PK=j.Z_19TRACKEDOBJECTS "
            "JOIN ZVSVISIBLEITEM t ON t.Z_PK=o.ZTYPE1 "
            "JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT=e.Z_PK WHERE e.Z_ENT=17 ORDER BY e.Z_PK,p.ZINDEX"):
        ev[e].append(pk); meta[e] = (nm_, tn, tc)
    clicks = defaultdict(dict)
    for pt, cl, x, y in db.execute(
            "SELECT p.ZPOINT,v.ZCLIPNAME,p.ZSCREENX,p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK=p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        clicks[pt][cl] = (x, y)
    db.close()

    # distortion candidates, fitted once per camera from .vsd plumblines
    dists = {}
    for mname, free in MODELS:
        dists[mname] = {}
        for clip in sorted(base):
            if free is None:
                dists[mname][clip] = list(base[clip]["dist"]) + [0.0]; continue
            co = S.Clip(POOL, clip)
            s0 = np.zeros(15)
            s0[0] = (co.centre0[0] - S.W / 2) / S.R; s0[1] = (co.centre0[1] - S.H / 2) / S.R
            v, prms, _, g = None, None, None, None
            g = Z.G(co.xy, co.counts)
            held = [j for j in range(15) if j not in free]
            seeds = []
            for sd in (s0, stored_v(base[clip]["dist"])):
                sd = sd.copy(); sd[held] = 0.0; seeds.append(sd)
            rr = np.random.default_rng(4)
            for _ in range(4):
                sd = seeds[rr.integers(0, len(seeds))].copy()
                sd[np.array(free)] += rr.normal(0, 0.03, len(free)); sd[held] = 0.0; seeds.append(sd)
            if 13 in free:
                for e_ in (-0.02, 0.01, 0.02, 0.04):
                    sd = seeds[0].copy(); sd[13] = e_; seeds.append(sd)
            v, sse, _ = Z.best_fit(g, free, seeds)
            cq, kq, pq, eq, _ = Z.nphys(v)
            dists[mname][clip] = [cq[0], cq[1], *kq, *pq, eq]
    say(f"\n  distortion candidates (from .vsd plumblines only)")
    for mname, _ in MODELS:
        for clip in sorted(base):
            d = dists[mname][clip]
            pl = PL(S.Clip(POOL, clip).xy)
            gr = F.gate_report(np.array(d[:13]), pl, sref=0.0)
            say(f"    {mname:10} {clip:13} eta {d[13]:+.6f}  R_scale {gr['radial_scale_ratio']:.4f} "
                f"minDet {gr['min_det_box']:.4f}  gate {'ok' if gr['ok'] else 'FAIL'}")

    # build the 8 cells
    cells = {}
    for tag, X in (("A", XA), ("B", XB)):
        for mname, _ in MODELS:
            cams = {}
            for clip in sorted(base):
                c = dict(base[clip]); c["front"] = X[clip]["front"]; c["back"] = X[clip]["back"]
                d = dists[mname][clip]
                o = st.run_oracle(c, dist=d[:13], eta=d[13])
                cams[clip] = {"ah": c["ah"], "av": c["av"], "front_d": c["front_d"],
                              "back_d": c["back_d"], "dist": d, "cam": o["cam"],
                              "camPLD": o["camPLD"],
                              "s2f": nd.flat_colmajor_to_nested(o["FRONT"]),
                              "s2b": nd.flat_colmajor_to_nested(o["BACK"]),
                              "f2s": nd.flat_colmajor_to_nested(o["FRONTINV"]),
                              "nodes": X[clip]}
            cells[(tag, mname)] = cams

    say(f"\n  CALIBRATION CHARACTERISATION (stored distortion; distances in mm)")
    say(f"    {'cal':4} {'camera':13} {'cam->front':>11} {'frontRMS':>9} {'backRMS':>9} "
         f"{'camPLD':>9} {'svRatio':>9}")
    for tag in ("A", "B"):
        for clip in sorted(base):
            cm = cells[(tag, "stored")][clip]
            ax = pa.AX[({"x", "y", "z"} - {cm["ah"], cm["av"]}).pop()]
            dfront = abs(cm["cam"][ax] - cm["front_d"]) * UNIT
            fr, _ = nd._rms_max(cm["nodes"]["front"], cm["s2f"], cm["dist"])
            br, _ = nd._rms_max(cm["nodes"]["back"], cm["s2b"], cm["dist"])
            say(f"    {tag:4} {clip:13} {dfront:11.1f} {fr*UNIT:9.4f} {br*UNIT:9.4f} "
                f"{cm['camPLD']*UNIT:9.4f} {'-':>9}")

    # triangulate
    res = {}
    for key, cams in cells.items():
        rows = []
        for e, pks in sorted(ev.items()):
            if len(pks) != 2: continue
            true = jw.true_length_mm(meta[e][0], meta[e][1], UNIT)
            if true is None: continue
            P = []
            for pk in pks:
                obs = [(cams[cl], clicks[pk][cl]) for cl in sorted(cams) if cl in clicks.get(pk, {})]
                if len(obs) < 2: P = None; break
                P.append(pa.triangulate(obs)[0])
            if P is None: continue
            Lm = float(np.linalg.norm(np.array(P[0], np.float32) - np.array(P[1], np.float32))) * UNIT
            rows.append(dict(e=e, obj=meta[e][0], tc=meta[e][2], true=true, meas=Lm,
                             err=Lm - true, X=P))
        res[key] = rows
    n = len(res[("A", "stored")])
    say(f"\n  PRINCIPAL EIGHT-CELL TABLE, n = {n} (mm)")
    say(f"    {'model':10} " + " ".join(f"{'Cal'+t+' '+k:>12}" for t in "AB"
                                        for k in ("MAE", "RMSE", "p95")))
    for mname, _ in MODELS:
        row = []
        for t in "AB":
            s = stats([r["err"] for r in res[(t, mname)]])
            row += [f"{s['mae']:12.4f}", f"{s['rmse']:12.4f}", f"{s['p95']:12.4f}"]
        say(f"    {mname:10} " + " ".join(row))

    # eta contrasts and interaction
    say(f"\n  eta EFFECT (truncated -> truncated+eta), change in |error| mm; negative favours eta")
    keys = np.array([r["tc"] if r["tc"] else "none" for r in res[("A", "trunc")]])
    dA = np.array([abs(a["err"]) - abs(b["err"]) for a, b in
                   zip(res[("A", "trunc+eta")], res[("A", "trunc")])])
    dB = np.array([abs(a["err"]) - abs(b["err"]) for a, b in
                   zip(res[("B", "trunc+eta")], res[("B", "trunc")])])
    for nm_, d in (("Cal A", dA), ("Cal B", dB), ("interaction B-A", dB - dA)):
        ci = cboot(d, keys)
        say(f"    {nm_:16} mean {d.mean():+.4f}  median {np.median(d):+.4f}  "
            f"better/worse {int((d<0).sum())}/{int((d>0).sum())}  "
            f"cluster 5-95% {('[%+.4f, %+.4f]' % ci) if ci else 'n/a'}")
    say(f"    per object:")
    for o in sorted({r["obj"] for r in res[("A", "trunc")]}):
        m = np.array([r["obj"] == o for r in res[("A", "trunc")]])
        say(f"      {str(o):30} n {int(m.sum()):5d}  A {dA[m].mean():+.4f}  B {dB[m].mean():+.4f}  "
            f"interaction {(dB-dA)[m].mean():+.4f}")

    # covariates
    cov = []
    for i, r in enumerate(res[("A", "stored")]):
        pks = ev[r["e"]]
        rad, edge = [], []
        for pk in pks:
            for cl in sorted(base):
                if cl in clicks.get(pk, {}):
                    x, y = clicks[pk][cl]
                    dd = dists["stored"][cl]
                    rad.append(math.hypot(x - dd[0], y - dd[1]) / math.hypot(S.W / 2, S.H / 2))
                    edge.append(min(x, S.W - x, y, S.H - y) / min(S.W, S.H) * 2)
        dd = {}
        for t in "AB":
            cams = cells[(t, "stored")]
            rr = res[(t, "stored")][i]
            mid = 0.5 * (np.array(rr["X"][0]) + np.array(rr["X"][1]))
            cds = [math.dist(mid, cams[cl]["cam"]) * UNIT for cl in sorted(cams)]
            nodes_f = cams[sorted(cams)[0]]["nodes"]
            ax = pa.AX[({"x", "y", "z"} - {cams[sorted(cams)[0]]["ah"],
                                           cams[sorted(cams)[0]]["av"]}).pop()]
            ctr = np.zeros(3); ctr[ax] = 0.5 * (cams[sorted(cams)[0]]["front_d"] +
                                                cams[sorted(cams)[0]]["back_d"])
            wh = [p[2] for p in nodes_f["front"]]; wv = [p[3] for p in nodes_f["front"]]
            oth = [k for k in range(3) if k != ax]
            ctr[oth[0]] = 0.5 * (min(wh) + max(wh)); ctr[oth[1]] = 0.5 * (min(wv) + max(wv))
            dd[t] = dict(camd=float(np.mean(cds)), ctrd=float(math.dist(mid, ctr) * UNIT))
        cov.append(dict(rmax=max(rad), edge=min(edge), true=r["true"], **{
            "camd" + t: dd[t]["camd"] for t in "AB"}, **{"ctrd" + t: dd[t]["ctrd"] for t in "AB"}))
    say(f"\n  HIGH-RISK CATEGORIES (upper/lower quartile definitions, model-independent)")
    say(f"    {'category':34} {'n':>5} {'A mean':>9} {'B mean':>9} {'interaction':>12}")
    def q(v, hi=True):
        a = np.array(v); t = np.percentile(a, 75 if hi else 25)
        return (a >= t) if hi else (a <= t)
    cats = [("far from cameras (Cal A dist)", q([c["camdA"] for c in cov])),
            ("far from cal centre (Cal A)", q([c["ctrdA"] for c in cov])),
            ("far from cal centre (Cal B)", q([c["ctrdB"] for c in cov])),
            ("near screen edge", q([c["edge"] for c in cov], hi=False)),
            ("long objects", q([c["true"] for c in cov])),
            ("large image radius", q([c["rmax"] for c in cov]))]
    flags = np.zeros(len(cov), int)
    for nm_, m in cats:
        say(f"    {nm_:34} {int(m.sum()):5d} {dA[m].mean():+9.4f} {dB[m].mean():+9.4f} "
            f"{(dB-dA)[m].mean():+12.4f}")
    for nm_, m in cats[:1] + cats[3:]:
        flags += m.astype(int)
    say(f"    by accumulated risk-factor count (camera distance, edge, long, radius):")
    for k in range(5):
        m = flags == k
        if m.sum() == 0: continue
        say(f"      {k} flags  n {int(m.sum()):5d}  A {dA[m].mean():+.4f}  B {dB[m].mean():+.4f}")

    say(f"\n  UPPER TAILS of |error| (mm)")
    say(f"    {'cell':18} {'med':>7} {'p75':>7} {'p90':>7} {'p95':>7} {'p99':>8} {'max':>8} "
        f"{'worst10%':>9} {'worst5%':>8}")
    for t in "AB":
        for mname, _ in MODELS:
            s = stats([r["err"] for r in res[(t, mname)]])
            say(f"    Cal {t} {mname:12} {s['med']:7.3f} {s['p75']:7.3f} {s['p90']:7.3f} "
                f"{s['p95']:7.3f} {s['p99']:8.3f} {s['mx']:8.3f} {s['w10']:9.3f} {s['w5']:8.3f}")
    say(f"\n  FIXED-BASELINE TAILS: the truncated model's own worst cases, re-evaluated under eta")
    for t in "AB":
        e0 = np.array([abs(r["err"]) for r in res[(t, "trunc")]])
        e1 = np.array([abs(r["err"]) for r in res[(t, "trunc+eta")]])
        for frac in (10, 5, 1):
            m = e0 >= np.percentile(e0, 100 - frac)
            say(f"    Cal {t} worst {frac:2d}% under truncated (n {int(m.sum()):3d}): "
                f"mean |e| {e0[m].mean():8.3f} -> {e1[m].mean():8.3f} mm  "
                f"({(e1[m].mean()-e0[m].mean()):+.3f}), improved on {int((e1[m]<e0[m]).sum())}")

    say(f"\n  ENDPOINT MOVEMENT, truncated -> truncated+eta, within each calibration (mm)")
    say(f"    {'cal':5} {'|common|':>10} {'|diff|':>10} {'along':>9} {'perp':>9} {'com/diff':>9}")
    for t in "AB":
        com, dif, alo, per = [], [], [], []
        for ra, rb in zip(res[(t, "trunc")], res[(t, "trunc+eta")]):
            X1, X2 = np.array(ra["X"][0]), np.array(ra["X"][1])
            Y1, Y2 = np.array(rb["X"][0]), np.array(rb["X"][1])
            cm = 0.5 * ((Y1 - X1) + (Y2 - X2)); df = (Y2 - X2) - (Y1 - X1)
            dh = (X2 - X1) / max(np.linalg.norm(X2 - X1), 1e-30)
            com.append(np.linalg.norm(cm) * UNIT); dif.append(np.linalg.norm(df) * UNIT)
            alo.append(abs(float(dh @ df)) * UNIT)
            per.append(np.linalg.norm(df - float(dh @ df) * dh) * UNIT)
        com, dif = np.array(com), np.array(dif)
        say(f"    {t:5} {np.median(com):10.4f} {np.median(dif):10.4f} {np.median(alo):9.4f} "
            f"{np.median(per):9.4f} {np.median(com/np.maximum(dif,1e-12)):9.2f}")

    say(f"\n  LARGEST eta IMPROVEMENTS AND DEGRADATIONS under Cal A (top 10 each)")
    say(f"    {'obj':26} {'true':>7} {'trunc':>9} {'+eta':>9} {'dA':>8} {'dB':>8} "
        f"{'camdA':>8} {'ctrdA':>8} {'rmax':>6} {'edge':>6}")
    order = np.argsort(dA)
    for idx in list(order[:10]) + list(order[-10:]):
        r0 = res[("A", "trunc")][idx]; r1 = res[("A", "trunc+eta")][idx]; c = cov[idx]
        say(f"    {str(r0['obj'])[:26]:26} {r0['true']:7.1f} {r0['err']:+9.3f} {r1['err']:+9.3f} "
            f"{dA[idx]:+8.3f} {dB[idx]:+8.3f} {c['camdA']:8.0f} {c['ctrdA']:8.0f} "
            f"{c['rmax']:6.2f} {c['edge']:6.2f}")
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
