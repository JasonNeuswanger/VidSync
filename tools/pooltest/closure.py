#!/usr/bin/env python3
"""Cal A / Cal B closure: signed-error mechanism, percent tails, projective absorption, node CV."""
import importlib.util, math, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
cb = L("calab"); nd, pa, st, S = cb.nd, cb.pa, cb.st, cb.S
UNIT = cb.UNIT


def dfun(e, dl):            # change in |error| from a signed perturbation
    return np.abs(e + dl) - np.abs(e)


def cboot(d, keys, n=1500, seed=7):
    uk = np.unique(keys)
    if len(uk) < 5: return None
    rng = np.random.default_rng(seed)
    idxs = {k: np.where(keys == k)[0] for k in uk}
    o = [d[np.concatenate([idxs[k] for k in rng.choice(uk, len(uk), True)])].mean()
         for _ in range(n)]
    return float(np.percentile(o, 5)), float(np.percentile(o, 95))


def homog_fit(src, dst):
    A = []
    for (u, v), (x, y) in zip(src, dst):
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x, -x])
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y, -y])
    _, _, V = np.linalg.svd(np.array(A))
    h = V[-1].reshape(3, 3)
    return h / h[2, 2]


def happly(h, p):
    q = np.hstack([p, np.ones((len(p), 1))]) @ h.T
    return q[:, :2] / q[:, 2:3]


def main():
    t0 = time.time(); say = print
    say("=" * 100); say("CAL A / CAL B CLOSURE"); say("=" * 100)
    R = cb.build_all() if hasattr(cb, "build_all") else None
    # rebuild the needed state by re-running calab's pipeline pieces
    tcA, XA = cb.parse_xml("A"); tcB, XB = cb.parse_xml("B")
    import sqlite3
    from collections import defaultdict
    base = st.load_cal(cb.POOL)
    db = sqlite3.connect(f"file:{cb.POOL}?mode=ro", uri=True)
    ev = defaultdict(list); meta = {}
    for nm_, tn, e, pk, tc in db.execute(
            "SELECT o.ZNAME2,t.ZNAME3,e.Z_PK,p.Z_PK,p.ZTIMECODE FROM ZVSVISIBLEITEM e "
            "JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS=e.Z_PK "
            "JOIN ZVSVISIBLEITEM o ON o.Z_PK=j.Z_19TRACKEDOBJECTS "
            "JOIN ZVSVISIBLEITEM t ON t.Z_PK=o.ZTYPE1 JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT=e.Z_PK "
            "WHERE e.Z_ENT=17 ORDER BY e.Z_PK,p.ZINDEX"):
        ev[e].append(pk); meta[e] = (nm_, tn, tc)
    clicks = defaultdict(dict)
    for pt, cl, x, y in db.execute(
            "SELECT p.ZPOINT,v.ZCLIPNAME,p.ZSCREENX,p.ZSCREENY FROM ZVSSCREENPOINT p "
            "JOIN ZVSVIDEOCLIP v ON v.Z_PK=p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
        clicks[pt][cl] = (x, y)
    db.close()
    # the two converged distortion fits, exactly as before
    dists = {}
    for mname, free in (("M0", cb.Z.ISO), ("M1", cb.Z.SCAL)):
        dists[mname] = {}
        for clip in sorted(base):
            co = S.Clip(cb.POOL, clip)
            g = cb.Z.G(co.xy, co.counts)
            held = [j for j in range(15) if j not in free]
            s0 = np.zeros(15)
            s0[0] = (co.centre0[0] - S.W / 2) / S.R; s0[1] = (co.centre0[1] - S.H / 2) / S.R
            seeds = []
            for sd in (s0, cb.stored_v(base[clip]["dist"])):
                sd = sd.copy(); sd[held] = 0.0; seeds.append(sd)
            rr = np.random.default_rng(4)
            for _ in range(4):
                sd = seeds[rr.integers(0, len(seeds))].copy()
                sd[np.array(free)] += rr.normal(0, 0.03, len(free)); sd[held] = 0.0; seeds.append(sd)
            if 13 in free:
                for e_ in (-0.02, 0.01, 0.02, 0.04):
                    sd = seeds[0].copy(); sd[13] = e_; seeds.append(sd)
            v, sse, _ = cb.Z.best_fit(g, free, seeds)
            c_, k_, p_, e_, _ = cb.Z.nphys(v)
            dists[mname][clip] = [c_[0], c_[1], *k_, *p_, e_]

    def build(tag, X, mname):
        cams = {}
        for clip in sorted(base):
            c = dict(base[clip]); c["front"] = X[clip]["front"]; c["back"] = X[clip]["back"]
            d = dists[mname][clip]
            o = st.run_oracle(c, dist=d[:13], eta=d[13])
            cams[clip] = {"ah": c["ah"], "av": c["av"], "front_d": c["front_d"],
                          "back_d": c["back_d"], "dist": d, "cam": o["cam"],
                          "camPLD": o["camPLD"], "sv": o["sv"],
                          "s2f": nd.flat_colmajor_to_nested(o["FRONT"]),
                          "s2b": nd.flat_colmajor_to_nested(o["BACK"]),
                          "f2s": nd.flat_colmajor_to_nested(o["FRONTINV"]),
                          "nodes": X[clip]}
        return cams

    cells = {(t, m): build(t, X, m) for t, X in (("A", XA), ("B", XB)) for m in ("M0", "M1")}

    def measure(cams):
        rows = []
        for e, pks in sorted(ev.items()):
            if len(pks) != 2: continue
            true = cb.jw.true_length_mm(meta[e][0], meta[e][1], UNIT)
            if true is None: continue
            P = []
            for pk in pks:
                obs = [(cams[cl], clicks[pk][cl]) for cl in sorted(cams) if cl in clicks.get(pk, {})]
                if len(obs) < 2: P = None; break
                P.append(pa.triangulate(obs)[0])
            if P is None: continue
            Lm = float(np.linalg.norm(np.array(P[0], np.float32)
                                      - np.array(P[1], np.float32))) * UNIT
            rows.append(dict(e=e, obj=meta[e][0], tc=meta[e][2], true=true, meas=Lm, X=P, pks=pks))
        return rows
    res = {k: measure(v) for k, v in cells.items()}
    obj = np.array([r["obj"] for r in res[("A", "M0")]])
    tru = np.array([r["true"] for r in res[("A", "M0")]])
    keys = np.array([r["tc"] if r["tc"] else "none" for r in res[("A", "M0")]])
    eA = np.array([r["meas"] for r in res[("A", "M0")]]) - tru
    eB = np.array([r["meas"] for r in res[("B", "M0")]]) - tru
    dlA = np.array([r["meas"] for r in res[("A", "M1")]]) - np.array([r["meas"] for r in res[("A", "M0")]])
    dlB = np.array([r["meas"] for r in res[("B", "M1")]]) - np.array([r["meas"] for r in res[("B", "M0")]])
    dA, dB = dfun(eA, dlA), dfun(eB, dlB)

    say(f"\n1. SIGNED-ERROR MECHANISM  (mm)")
    for nm_, v in (("e_A", eA), ("e_B", eB), ("dL_A", dlA), ("dL_B", dlB)):
        say(f"    {nm_:6} mean {v.mean():+8.4f} median {np.median(v):+8.4f} sd {v.std():7.4f} "
            f"RMS {math.sqrt((v**2).mean()):7.4f} max|.| {np.abs(v).max():8.4f}")
    sl, ic = np.polyfit(dlA, dlB, 1)
    say(f"    corr(dL_A, dL_B) {np.corrcoef(dlA,dlB)[0,1]:+.4f}; regression dL_B = "
        f"{sl:+.4f}*dL_A {ic:+.5f}")
    say(f"    RMS(dL_B - dL_A) {math.sqrt(((dlB-dlA)**2).mean()):.4f}, max "
        f"{np.abs(dlB-dlA).max():.4f} mm")
    say(f"    same sign: dL {np.mean(np.sign(dlA)==np.sign(dlB)):.3f}; "
        f"baseline errors e {np.mean(np.sign(eA)==np.sign(eB)):.3f}")
    say(f"    mean sign(e)*dL:  A {np.mean(np.sign(eA)*dlA):+.4f}   B "
        f"{np.mean(np.sign(eB)*dlB):+.4f}   (this is the first-order prediction of d)")
    say(f"    exact d:          A {dA.mean():+.4f}   B {dB.mean():+.4f}")
    say(f"    |dL| mean:        A {np.abs(dlA).mean():.4f}   B {np.abs(dlB).mean():.4f}")
    say(f"    |e| mean:         A {np.abs(eA).mean():.4f}   B {np.abs(eB).mean():.4f}")
    say(f"    fraction |dL|>|e| (sign-flip regime): A {np.mean(np.abs(dlA)>np.abs(eA)):.3f}  "
        f"B {np.mean(np.abs(dlB)>np.abs(eB)):.3f}")
    # Shapley decomposition of d_B - d_A over {baseline state, perturbation}
    sh_e = 0.5 * ((dfun(eB, dlA) - dfun(eA, dlA)) + (dfun(eB, dlB) - dfun(eA, dlB)))
    sh_d = 0.5 * ((dfun(eA, dlB) - dfun(eA, dlA)) + (dfun(eB, dlB) - dfun(eB, dlA)))
    say(f"    Shapley split of mean(d_B-d_A) = {(dB-dA).mean():+.4f}:  baseline-error change "
        f"{sh_e.mean():+.4f}  perturbation change {sh_d.mean():+.4f}  (sum "
        f"{(sh_e+sh_d).mean():+.4f})")

    say(f"\n2. DISTANCE VERSUS OBJECT IDENTITY")
    cams0 = cells[("A", "M0")]
    camd = {}
    for t in "AB":
        cm = cells[(t, "M0")]
        camd[t] = np.array([np.mean([math.dist(0.5*(np.array(r["X"][0])+np.array(r["X"][1])),
                                               cm[cl]["cam"]) for cl in sorted(cm)]) * UNIT
                            for r in res[(t, "M0")]])
    say(f"    {'object':28} {'n':>4} {'true':>7} {'distA range':>16} {'dA':>8} {'dB':>8} "
        f"{'slope dA/m':>11} {'slope dLA/m':>12}")
    for o in sorted(set(obj)):
        m = obj == o
        s1 = np.polyfit(camd["A"][m] / 1000.0, dA[m], 1)[0] if m.sum() > 3 else float("nan")
        s2 = np.polyfit(camd["A"][m] / 1000.0, dlA[m], 1)[0] if m.sum() > 3 else float("nan")
        say(f"    {str(o)[:28]:28} {int(m.sum()):4d} {tru[m][0]:7.1f} "
            f"{camd['A'][m].min():7.0f}-{camd['A'][m].max():<8.0f} {dA[m].mean():+8.4f} "
            f"{dB[m].mean():+8.4f} {s1:+11.4f} {s2:+12.4f}")
    say(f"    leave-one-object-out means of d_A / d_B:")
    for o in sorted(set(obj)):
        m = obj != o
        say(f"      excluding {str(o)[:26]:26} d_A {dA[m].mean():+.4f}  d_B {dB[m].mean():+.4f}  "
            f"interaction {(dB-dA)[m].mean():+.4f}")
    m = obj != "Full Width 0.5969"
    ciA, ciB = cboot(dA[m], keys[m]), cboot((dB-dA)[m], keys[m])
    say(f"    Full Width excluded (n {int(m.sum())}): d_A {dA[m].mean():+.4f} "
        f"{('[%+.4f, %+.4f]'%ciA) if ciA else ''}, d_B {dB[m].mean():+.4f}, interaction "
        f"{(dB-dA)[m].mean():+.4f} {('[%+.4f, %+.4f]'%ciB) if ciB else ''}")

    say(f"\n3. PERCENT-ERROR TAILS  (100*|e|/true)")
    say(f"    {'cell':10} {'med':>7} {'p75':>7} {'p90':>7} {'p95':>7} {'p99':>7} {'max':>8} "
        f"{'w10%':>7} {'w5%':>7} {'w1%':>7}")
    pct = {}
    for t in "AB":
        for m_ in ("M0", "M1"):
            p = 100 * np.abs(np.array([r["meas"] for r in res[(t, m_)]]) - tru) / tru
            pct[(t, m_)] = p
            say(f"    {t+' '+m_:10} {np.median(p):7.3f} {np.percentile(p,75):7.3f} "
                f"{np.percentile(p,90):7.3f} {np.percentile(p,95):7.3f} "
                f"{np.percentile(p,99):7.3f} {p.max():8.3f} "
                f"{p[p>=np.percentile(p,90)].mean():7.3f} {p[p>=np.percentile(p,95)].mean():7.3f} "
                f"{p[p>=np.percentile(p,99)].mean():7.3f}")
    say(f"    exceedance counts of 1010:")
    for th in (0.5, 1.0, 2.0, 5.0):
        say(f"      >{th:4.1f}% : " + "  ".join(
            f"{t} {m_} {int((pct[(t,m_)]>th).sum()):4d}" for t in "AB" for m_ in ("M0", "M1")))
    for t in "AB":
        p0, p1 = pct[(t, "M0")], pct[(t, "M1")]
        for fr in (10, 5, 1):
            k = p0 >= np.percentile(p0, 100 - fr)
            say(f"    Cal {t} worst {fr:2d}% by percent error (n {int(k.sum()):3d}): "
                f"{p0[k].mean():6.3f}% -> {p1[k].mean():6.3f}%, improved on "
                f"{int((p1[k]<p0[k]).sum())}")
    say(f"    largest eta degradations by percentage points (Cal A):")
    dp = pct[("A", "M1")] - pct[("A", "M0")]
    for i in np.argsort(dp)[-5:][::-1]:
        say(f"      {str(obj[i])[:26]:26} true {tru[i]:6.1f}  {pct[('A','M0')][i]:6.3f}% -> "
            f"{pct[('A','M1')][i]:6.3f}%  ({dp[i]:+.3f} pp)  mm change {dA[i]:+.3f}")

    say(f"\n4. PROJECTIVE ABSORPTION: effective maps H*U, M1 minus M0 (mm in frame coords)")
    say(f"    {'cal':4} {'camera':13} {'plane':6} {'nodes RMS':>10} {'endpts RMS':>11} "
        f"{'endpts p95':>11} {'endpts max':>11}")
    epts = {}
    for t in "AB":
        allc = []
        for cl in sorted(base):
            pts = []
            for r in res[(t, "M0")]:
                for pk in r["pks"]:
                    if cl in clicks.get(pk, {}): pts.append(clicks[pk][cl])
            epts[(t, cl)] = np.array(pts)
        for cl in sorted(base):
            c0, c1 = cells[(t, "M0")][cl], cells[(t, "M1")][cl]
            for plane, key in (("front", "s2f"), ("back", "s2b")):
                nds = np.array([[p[0], p[1]] for p in c0["nodes"][plane]])
                for nm_, P in (("nodes", nds), ("endpts", epts[(t, cl)])):
                    U0 = np.array([nd.undistort13(x, y, c0["dist"]) for x, y in P])
                    U1 = np.array([nd.undistort13(x, y, c1["dist"]) for x, y in P])
                    F0 = happly(np.array(c0[key]), U0); F1 = happly(np.array(c1[key]), U1)
                    e_ = np.hypot(*(F1 - F0).T) * UNIT
                    if nm_ == "nodes": nr = math.sqrt((e_ ** 2).mean())
                    else: er, ep, em = math.sqrt((e_**2).mean()), np.percentile(e_,95), e_.max()
                say(f"    {t:4} {cl:13} {plane:6} {nr:10.4f} {er:11.4f} {ep:11.4f} {em:11.4f}")
    say(f"    abstract projective decomposition of U_eta vs U_0 over each node support:")
    for t in "AB":
        for cl in sorted(base):
            c0, c1 = cells[(t, "M0")][cl], cells[(t, "M1")][cl]
            nds = np.array([[p[0], p[1]] for p in c0["nodes"]["front"] + c0["nodes"]["back"]])
            U0n = np.array([nd.undistort13(x, y, c0["dist"]) for x, y in nds])
            U1n = np.array([nd.undistort13(x, y, c1["dist"]) for x, y in nds])
            H = homog_fit(U1n, U0n)
            rn = np.hypot(*(happly(H, U1n) - U0n).T)
            P = epts[(t, cl)]
            U0e = np.array([nd.undistort13(x, y, c0["dist"]) for x, y in P])
            U1e = np.array([nd.undistort13(x, y, c1["dist"]) for x, y in P])
            raw = np.hypot(*(U1e - U0e).T)
            rse = np.hypot(*(happly(H, U1e) - U0e).T)
            say(f"      {t} {cl:13} raw endpoint map diff {raw.mean():7.3f} px -> after removing "
                f"node-fitted projective {rse.mean():7.3f} px ({100*(1-rse.mean()/raw.mean()):5.1f}% "
                f"absorbed); node residual {rn.mean():.4f} px")

    say(f"\n5. LEAVE-ONE-PHYSICAL-NODE-OUT CALIBRATION CROSS-VALIDATION (mm)")
    say(f"    {'cal':4} {'model':6} {'plane':6} {'n':>4} {'held-out RMS':>13} {'max':>9} "
        f"{'inner half':>11} {'outer half':>11}")
    for t, X in (("A", XA), ("B", XB)):
        for m_ in ("M0", "M1"):
            for plane in ("front", "back"):
                errs, rads = [], []
                wl = sorted({(round(p[2], 6), round(p[3], 6))
                             for cl in sorted(base) for p in X[cl][plane]})
                for w in wl:
                    Xh = {cl: {k: [p for p in X[cl][k]
                                   if not (k == plane and (round(p[2],6), round(p[3],6)) == w)]
                               for k in ("front", "back")} for cl in sorted(base)}
                    if any(len(Xh[cl][plane]) < 5 for cl in sorted(base)): continue
                    try: cm = build(t, Xh, m_)
                    except Exception: continue
                    for cl in sorted(base):
                        held = [p for p in X[cl][plane]
                                if (round(p[2],6), round(p[3],6)) == w]
                        for p in held:
                            u = nd.undistort13(p[0], p[1], cm[cl]["dist"])
                            q = nd.apply3(cm[cl]["s2f" if plane == "front" else "s2b"], *u)
                            errs.append(math.hypot(q[0]-p[2], q[1]-p[3]) * UNIT)
                            rads.append(math.hypot(p[0]-cm[cl]["dist"][0], p[1]-cm[cl]["dist"][1]))
                if not errs: continue
                e_ = np.array(errs); rr_ = np.array(rads); md = np.median(rr_)
                say(f"    {t:4} {m_:6} {plane:6} {len(e_):4d} "
                    f"{math.sqrt((e_**2).mean()):13.4f} {e_.max():9.4f} "
                    f"{math.sqrt((e_[rr_<=md]**2).mean()):11.4f} "
                    f"{math.sqrt((e_[rr_>md]**2).mean()):11.4f}")

    say(f"\n6. DLT SINGULAR-VALUE DIAGNOSTICS (normalized design, front then back per camera)")
    say(f"    {'cal':4} {'model':6} {'camera':13} {'s_min':>10} {'s_next':>10} {'ratio':>9}")
    for t in "AB":
        for m_ in ("M0", "M1"):
            for cl in sorted(base):
                for i, plane in enumerate(("front", "back")):
                    sv = cells[(t, m_)][cl]["sv"][0 if i == 0 else 1]
                    say(f"    {t:4} {m_:6} {cl+' '+plane:13} {sv[-1]:10.5f} {sv[-2]:10.5f} "
                        f"{sv[-2]/sv[-1]:9.3f}")
                break
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
