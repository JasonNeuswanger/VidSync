#!/usr/bin/env python3
"""Round 9a, Tokina 10 mm only: free-axis anisotropy, line-geometry dependence, artifact simulation.

Sections 1-3 of the final straightness-residual round.

Everything runs on a 15-element parameter vector: the suite4 14-vector plus a trailing b, the
off-diagonal of the traceless symmetric generator S = [[a,b],[b,-a]], with A = exp(S) and
det A = 1 identically. The scalar axis-locked model is b = 0, where exp(S) reduces to
diag(exp(a), exp(-a)) analytically; the reported nesting error is pure floating-point round-off
because the general branch computes cosh(mu) +/- sinh(mu) rather than exp(+/-a).

Weighted fits use weighted total-least-squares per line, so the line fit and the objective use the
same weights. Run with ~/.venvs/vidsync/bin/python.
"""

import importlib.util
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("suite4", os.path.join(HERE, "suite4.py"))
S = importlib.util.module_from_spec(_s); _s.loader.exec_module(S)
R, W, H, ETA = S.R, S.W, S.H, S.ETA
# Round-5 cached fits, needed only by this module's own main(). Importers that reuse the model
# machinery (G, best_fit, nphys, ISO, SCAL) must not be broken by a cleared /tmp, so a missing
# scratch file leaves ALL empty rather than failing at import.
try:
    ALL = {r["tag"]: r for r in np.load("/tmp/round5.npy", allow_pickle=True)}
except OSError:
    ALL = {}
PATH = {l: p for l, p in S.SUITE}
TAGS = ["Tokina 10 mm / Left Camera", "Tokina 10 mm / Right Camera"]
SHORT = {TAGS[0]: "Left", TAGS[1]: "Right"}

BLO = np.concatenate([S.BLO, [-0.05]])
BHI = np.concatenate([S.BHI, [+0.05]])
NAMES = S.NAMES + ["b"]
BIDX = 14
ISO = [0, 1, 2, 3, 4, 5, 9, 10]                  # centre, a1..a4, q1, q2
SCAL = ISO + [13]                                # + eta
FREEAX = SCAL + [14]                             # + b


# --------------------------------------------------------------------- free-axis model
def expS(a, b):
    """exp of the traceless symmetric generator; det is 1 to machine precision."""
    mu = math.hypot(a, b)
    ch = math.cosh(mu)
    sh = 1.0 + mu * mu / 6.0 + mu ** 4 / 120.0 if mu < 1e-6 else math.sinh(mu) / mu
    return np.array([[ch + a * sh, b * sh], [b * sh, ch - a * sh]])


def nphys(v):
    c, k, p, e = S.nphys(v[:14])
    return c, k, p, e, v[14]


def Umap(x, c, k, p, a, b):
    A = expS(a, b)
    Ai = expS(-a, -b)
    u = (x - c) @ A
    return c + (u + S.delta_r(u, k) + S.d_p(u, p)) @ Ai


def Uv(x, v):
    return Umap(x, *nphys(v))


def jdet(x, c, k, p, a, b):
    """det(A^-1 J_B A) = det J_B, so conjugation drops out and only the core matters."""
    u = (x - c) @ expS(a, b)
    ux, uy = u[:, 0], u[:, 1]
    s = ux * ux + uy * uy
    Rr = np.ones_like(s); Rp = np.zeros_like(s)
    for i, ki in enumerate(k, start=1):
        Rr = Rr + ki * s ** i
        Rp = Rp + i * ki * s ** (i - 1)
    T = 1 + p[2] * s + p[3] * s * s
    Tp = p[2] + 2 * p[3] * s
    Gx = p[0] * (3 * ux * ux + uy * uy) + 2 * p[1] * ux * uy
    Gy = 2 * p[0] * ux * uy + p[1] * (ux * ux + 3 * uy * uy)
    aa = Rr + 2 * ux * ux * Rp + (6 * p[0] * ux + 2 * p[1] * uy) * T + 2 * ux * Gx * Tp
    bb = 2 * ux * uy * Rp + (2 * p[0] * uy + 2 * p[1] * ux) * T + 2 * uy * Gx * Tp
    cc = 2 * ux * uy * Rp + (2 * p[0] * uy + 2 * p[1] * ux) * T + 2 * ux * Gy * Tp
    dd = Rr + 2 * uy * uy * Rp + (2 * p[0] * ux + 6 * p[1] * uy) * T + 2 * uy * Gy * Tp
    return aa * dd - bb * cc


# --------------------------------------------------------------------- geometry container
class G:
    """A set of plumblines with per-point weights and a weighted-TLS straightness objective."""

    def __init__(self, xy, counts, w=None):
        self.xy = np.asarray(xy, float)
        self.counts = np.asarray(counts, int)
        self.starts = np.concatenate([[0], np.cumsum(self.counts)[:-1]])
        self.n, self.nlines = len(self.xy), len(self.counts)
        self.w = np.ones(self.n) if w is None else np.asarray(w, float)
        self.sw = np.sqrt(self.w)
        self.wsum = np.add.reduceat(self.w, self.starts)
        lo, hi = self.xy.min(axis=0), self.xy.max(axis=0)
        gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 13), np.linspace(lo[1], hi[1], 13))
        self.bgrid = np.stack([gx.ravel(), gy.ravel()], axis=1)

    def straight(self, pts):
        w = self.w
        cx = np.add.reduceat(w * pts[:, 0], self.starts) / self.wsum
        cy = np.add.reduceat(w * pts[:, 1], self.starts) / self.wsum
        qx = pts[:, 0] - np.repeat(cx, self.counts)
        qy = pts[:, 1] - np.repeat(cy, self.counts)
        sxy = np.add.reduceat(w * qx * qy, self.starts)
        sd = np.add.reduceat(w * (qx * qx - qy * qy), self.starts)
        th = 0.5 * np.arctan2(2.0 * sxy, sd)
        return -qx * np.repeat(np.sin(th), self.counts) + qy * np.repeat(np.cos(th), self.counts)

    def resid(self, v):
        return self.sw * self.straight(Uv(self.xy, v))

    def barrier(self, v):
        c, k, p, a, b = nphys(v)
        m = float(jdet(self.bgrid, c, k, p, a, b).min())
        return np.array([200.0 * math.sqrt(self.n) * max(0.0, 0.05 - m)])

    def rb(self, v):
        return np.concatenate([self.resid(v), self.barrier(v)])

    def sse(self, v):
        r = self.resid(v)
        return float(r @ r)


def fit(g, free, s0, method="trf"):
    free = np.asarray(free)
    s0 = np.clip(np.asarray(s0, float), BLO, BHI)

    def rr(x):
        v = s0.copy(); v[free] = x
        return g.rb(v)
    if method == "trf":
        r = least_squares(rr, s0[free], method="trf", x_scale=1.0,
                          bounds=(BLO[free], BHI[free]),
                          ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=40000)
        v = s0.copy(); v[free] = r.x
        return v, g.sse(v), float(r.optimality)
    from scipy.optimize import minimize

    def f(x):
        v = s0.copy(); v[free] = x
        q = g.rb(v)
        return float(q @ q)
    r = minimize(f, s0[free], method="L-BFGS-B",
                 bounds=list(zip(BLO[free], BHI[free])),
                 options={"maxiter": 40000, "maxfun": 40000, "ftol": 1e-18, "gtol": 1e-14})
    v = s0.copy(); v[free] = r.x
    return v, g.sse(v), float("nan")


def best_fit(g, free, seeds, methods=("trf",), allsse=False):
    out, got = None, []
    for s in seeds:
        for m in methods:
            try:
                v, c, o = fit(g, free, s, m)
            except Exception:                                # noqa: BLE001
                continue
            got.append(c)
            if out is None or c < out[1] - 1e-12:
                out = (v, c, o)
    return (out, got) if allsse else out


def jacobian(g, v, free, eps=1e-6):
    J = []
    for j in free:
        a = v.copy(); a[j] += eps
        b = v.copy(); b[j] -= eps
        J.append((g.resid(a) - g.resid(b)) / (2 * eps))
    return np.array(J).T


def load_clip(tag):
    lens, cn = tag.split(" / ")
    c = S.Clip(PATH[lens], cn)
    return G(c.xy, c.counts), c


# --------------------------------------------------------------------- line bookkeeping
def line_info(g, v):
    """Per-line family, corrected direction/normal angle, radial span, length, leverage."""
    U = Uv(g.xy, v)
    c = nphys(v)[0]
    ang = np.empty(g.nlines); ln = np.empty(g.nlines)
    rlo = np.empty(g.nlines); rhi = np.empty(g.nlines); lev = np.empty(g.nlines)
    isend = np.zeros(g.n, bool)
    for i in range(g.nlines):
        a, b = g.starts[i], g.starts[i] + g.counts[i]
        P = U[a:b]; q = P - P.mean(0)
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        ang[i] = math.degrees(th) % 180
        t = q[:, 0] * math.cos(th) + q[:, 1] * math.sin(th)
        ln[i] = t.max() - t.min()
        h = 1.0 / g.counts[i] + t ** 2 / max(float(t @ t), 1e-9)
        lev[i] = h.max()
        d = np.hypot(g.xy[a:b, 0] - c[0], g.xy[a:b, 1] - c[1])
        rlo[i], rhi[i] = d.min(), d.max()
        isend[a + int(np.argmin(t))] = True
        isend[a + int(np.argmax(t))] = True
    z = np.exp(2j * np.radians(ang))
    ref = math.degrees(np.angle(z.mean())) / 2 % 180
    fam = np.array([0 if min(abs(x - ref), 180 - abs(x - ref)) < 45 else 1 for x in ang])
    nrm = (ang + 90.0) % 180
    return {"ang": ang, "nrm": nrm, "fam": fam, "len": ln, "rlo": rlo, "rhi": rhi,
            "lev": lev, "isend": isend, "ref": ref,
            "pl": np.repeat(np.arange(g.nlines), g.counts)}


def info_share(g, v, free, tgt):
    """Fraction of the nuisance-orthogonalized information about tgt contributed by each line."""
    nu = [j for j in free if j != tgt]
    Jn = jacobian(g, v, nu)
    jt = jacobian(g, v, [tgt])[:, 0]
    Q, _ = np.linalg.qr(Jn)
    perp = jt - Q @ (Q.T @ jt)
    pl = np.repeat(np.arange(g.nlines), g.counts)
    sh = np.array([float((perp[pl == i] ** 2).sum()) for i in range(g.nlines)])
    return sh / max(sh.sum(), 1e-30), float(np.linalg.norm(perp)), float(np.linalg.norm(jt))


def rake(g, li, edges, iters=200):
    """Weights approximately equalizing per-line mass, families, normal-angle bins, radial
    bands, and endpoint vs interior mass."""
    pl, fam, isend = li["pl"], li["fam"], li["isend"]
    pfam = fam[pl]
    r = np.hypot(g.xy[:, 0] - edges["c"][0], g.xy[:, 1] - edges["c"][1])
    rb = np.clip(np.digitize(r, edges["rad"]), 0, len(edges["rad"]))
    ab = np.clip(np.digitize(li["nrm"][pl], edges["ang"]), 0, len(edges["ang"]))
    w = np.ones(g.n)
    groups = [pl, pfam, rb, ab, isend.astype(int)]
    for _ in range(iters):
        for gv in groups:
            u = np.unique(gv)
            tot = np.array([w[gv == x].sum() for x in u])
            tgt = w.sum() / len(u)
            for x, t in zip(u, tot):
                if t > 1e-12:
                    w[gv == x] *= tgt / t
        w *= g.n / w.sum()
    return w


def report_margins(say, g, li, edges, w, lbl):
    pl, fam, isend = li["pl"], li["fam"], li["isend"]
    r = np.hypot(g.xy[:, 0] - edges["c"][0], g.xy[:, 1] - edges["c"][1])
    rb = np.clip(np.digitize(r, edges["rad"]), 0, len(edges["rad"]))
    ab = np.clip(np.digitize(li["nrm"][pl], edges["ang"]), 0, len(edges["ang"]))
    def sp(gv):
        u = np.unique(gv)
        t = np.array([w[gv == x].sum() for x in u])
        return t.max() / max(t.min(), 1e-12)
    say(f"      {lbl}: max/min mass ratio  per line {sp(pl):.2f}, family {sp(fam[pl]):.2f}, "
        f"radial band {sp(rb):.2f}, normal-angle bin {sp(ab):.2f}, endpoint/interior "
        f"{sp(isend.astype(int)):.2f}")


# --------------------------------------------------------------------- synthetic machinery
def newton_inv(fwd, t, iters=60, h=1e-4):
    """Invert a forward map R^2 -> R^2 pointwise by Newton with a finite-difference Jacobian."""
    u = t.copy()
    ex = np.array([h, 0.0]); ey = np.array([0.0, h])
    for _ in range(iters):
        F = fwd(u) - t
        if np.abs(F).max() < 1e-11:
            break
        a = (fwd(u + ex) - fwd(u - ex)) / (2 * h)
        b = (fwd(u + ey) - fwd(u - ey)) / (2 * h)
        det = a[:, 0] * b[:, 1] - b[:, 0] * a[:, 1]
        det = np.where(np.abs(det) < 1e-12, 1e-12, det)
        du = np.stack([(b[:, 1] * F[:, 0] - b[:, 0] * F[:, 1]) / det,
                       (-a[:, 1] * F[:, 0] + a[:, 0] * F[:, 1]) / det], axis=1)
        u = u - du
    return u


def truth_from_intersections(g, v, li):
    """One 2D coordinate per chessboard corner: intersection of its two fitted parent lines.

    Points on each fitted line are exactly collinear by construction, so the truth satisfies both
    families simultaneously and exactly.
    """
    U = Uv(g.xy, v)
    dirs, cens = [], []
    for i in range(g.nlines):
        a, b = g.starts[i], g.starts[i] + g.counts[i]
        P = U[a:b]; m = P.mean(0); q = P - m
        th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                              float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
        dirs.append(np.array([math.cos(th), math.sin(th)])); cens.append(m)
    key = {}
    for i in range(g.nlines):
        if li["fam"][i] != 0:
            continue
        a = g.starts[i]
        for j in range(g.counts[i]):
            p = g.xy[a + j]
            key[(round(p[0], 3), round(p[1], 3))] = (i, a + j)
    rows = []
    for i in range(g.nlines):
        if li["fam"][i] != 1:
            continue
        a = g.starts[i]
        for j in range(g.counts[i]):
            p = g.xy[a + j]
            hit = key.get((round(p[0], 3), round(p[1], 3)))
            if hit is None:
                continue
            ia, ka = hit
            na = np.array([-dirs[ia][1], dirs[ia][0]])
            nb = np.array([-dirs[i][1], dirs[i][0]])
            det = na[0] * nb[1] - na[1] * nb[0]
            if abs(det) < 0.2:
                continue
            ca, cb = na @ cens[ia], nb @ cens[i]
            x = (ca * nb[1] - cb * na[1]) / det
            y = (na[0] * cb - nb[0] * ca) / det
            rows.append((ia, i, ka, a + j, x, y))
    return rows


def build_synth(rows, fwd):
    """Assemble a two-family plumbline set from the common corner coordinates."""
    byA, byB = {}, {}
    for ia, ib, ka, kb, x, y in rows:
        byA.setdefault(ia, []).append((x, y))
        byB.setdefault(ib, []).append((x, y))
    groups = [np.array(p) for p in byA.values() if len(p) >= 4]
    groups += [np.array(p) for p in byB.values() if len(p) >= 4]
    Ut = np.concatenate(groups, axis=0)
    counts = np.array([len(p) for p in groups])
    X = newton_inv(fwd, Ut)
    return X, counts, Ut


def main():
    t0 = time.time()
    say = print
    dat = {}
    for tg in TAGS:
        g, clip = load_clip(tg)
        v = np.zeros(15); v[:14] = np.array(ALL[tg]["M1_2p"]["v"])
        v0 = np.zeros(15); v0[:14] = np.array(ALL[tg]["M0_2p"]["v"])
        v7 = np.zeros(15); v7[:14] = np.array(ALL[tg]["M1_2p_k7"]["v"])
        dat[tg] = {"g": g, "v1": v, "v0": v0, "v7": v7, "li": line_info(g, v)}

    # ================================================================= SECTION 1
    say("=" * 110)
    say("1  FREELY ORIENTED ANISOTROPY  A = exp([[a,b],[b,-a]])")
    say("=" * 110)
    for tg in TAGS:
        d = dat[tg]; g, v1 = d["g"], d["v1"]
        say(f"\n  {SHORT[tg]}  ({g.nlines} lines, {g.n} corners)")
        sc = g.sse(v1)
        vn = v1.copy(); vn[BIDX] = 0.0
        say(f"    nesting at b=0: free-axis SSE {g.sse(vn):.9f} vs scalar {sc:.9f}, "
            f"difference {g.sse(vn) - sc:+.3e} (floating-point round-off in cosh+/-sinh)")
        seeds = [v1.copy()]
        for bb in (-0.02, -0.01, -0.005, 0.005, 0.01, 0.02):
            s = v1.copy(); s[BIDX] = bb; seeds.append(s)
            s2 = d["v0"].copy(); s2[BIDX] = bb; seeds.append(s2)
        for aa in (-0.02, 0.0, 0.02):
            for bb in (-0.02, 0.0, 0.02):
                s = d["v0"].copy(); s[ETA] = aa; s[BIDX] = bb; seeds.append(s)
        rng = np.random.default_rng(3)
        for _ in range(4):
            s = v1.copy(); s[[0, 1]] += rng.normal(0, 0.02, 2); s[BIDX] = rng.normal(0, 0.01)
            seeds.append(s)
        (vf, cf, of), allc = best_fit(g, FREEAX, seeds, methods=("trf", "lbfgs"), allsse=True)
        a, b = vf[ETA], vf[BIDX]
        mu = math.hypot(a, b); al = 0.5 * math.degrees(math.atan2(b, a))
        nsame = sum(1 for c in allc if abs(c - cf) < 1e-6)
        say(f"    free-axis optimum: a {a:+.7f}, b {b:+.7f}, SSE {cf:.5f} "
            f"({nsame}/{len(allc)} runs over {len(seeds)} seeds and 2 solvers agree)")
        say(f"      magnitude mu {mu:.7f}, axis alpha {al:+.2f} deg "
            f"(alpha is meaningless when mu is negligible)")
        say(f"    SSE relative to (a,b)=(0,0) [{g.sse(d['v0']):.5f}]: "
            f"{cf - g.sse(d['v0']):+.5f}")
        say(f"    SSE relative to the scalar axis-locked model [{sc:.5f}]: {cf - sc:+.5f} "
            f"for one extra parameter")
        J = jacobian(g, vf, FREEAX)
        sv = np.linalg.svd(J, compute_uv=False)
        C = np.linalg.inv(J.T @ J)
        ia, ib = FREEAX.index(ETA), FREEAX.index(BIDX)
        rab = C[ia, ib] / math.sqrt(C[ia, ia] * C[ib, ib])
        ab = [NAMES[j] for j in FREEAX if abs(vf[j] - BLO[j]) < 1e-7 or abs(vf[j] - BHI[j]) < 1e-7]
        cq, kq, pq, aq, bq = nphys(vf)
        dj = jdet(clip_grid(g), cq, kq, pq, aq, bq)
        mg = np.sqrt(np.abs(dj))
        say(f"    condition {sv[0]/sv[-1]:.3e}, corr(a,b) {rab:+.4f}, active bounds "
            f"{ab if ab else 'none'}, min det {dj.min():+.4f}, scale ratio {mg.max()/mg.min():.3f}")
        sd_a = math.sqrt(C[ia, ia] * cf / (g.n - len(FREEAX)))
        sd_b = math.sqrt(C[ib, ib] * cf / (g.n - len(FREEAX)))
        say(f"    linearized standard errors: a {sd_a:.7f}, b {sd_b:.7f}")
        d["free"] = vf

        say(f"    profiles with all other parameters reoptimized:")
        for nm, idx in (("a", ETA), ("b", BIDX)):
            gridv = [-0.02, -0.01, -0.005, -0.002, 0.0, 0.002, 0.005, 0.01, 0.02]
            row = []
            for x in gridv:
                s = vf.copy(); s[idx] = x
                fr = [j for j in FREEAX if j != idx]
                row.append(fit(g, fr, s, "trf")[1])
            lo = min(row)
            say(f"      {nm}: " + "  ".join(f"{x:+.3f}:{c-lo:8.3f}" for x, c in zip(gridv, row)))

        say(f"    line-cluster bootstrap of (a,b), 200 resamples of whole lines:")
        bs = boot_free(g, vf, 200, 5)
        for nm, arr in (("a", bs[:, 0]), ("b", bs[:, 1])):
            say(f"      {nm}: mean {arr.mean():+.7f}, sd {arr.std(ddof=1):.7f}, "
                f"5th {np.percentile(arr,5):+.7f}, 95th {np.percentile(arr,95):+.7f}, "
                f"share with sign of point estimate "
                f"{np.mean(np.sign(arr) == np.sign(vf[ETA] if nm=='a' else vf[BIDX])):.2f}")

    # ================================================================= SECTION 2
    say("\n" + "=" * 110)
    say("2  DEPENDENCE ON CAPTURED LINE GEOMETRY")
    say("=" * 110)
    say("\n  Both clips contain a single timecode, so pass subsets and board-roll subsets do not")
    say("  exist in this archive. Leave-one-line-out and line-cluster resampling are available.")
    pooled_nrm = np.concatenate([dat[t]["li"]["nrm"] for t in TAGS])
    pooled_r = np.concatenate([np.hypot(dat[t]["g"].xy[:, 0] - nphys(dat[t]["v1"])[0][0],
                                        dat[t]["g"].xy[:, 1] - nphys(dat[t]["v1"])[0][1])
                               for t in TAGS])
    edges_ang = np.percentile(pooled_nrm, [25, 50, 75])
    edges_rad = np.percentile(pooled_r, [25, 50, 75])
    say(f"\n  common-support bins from the pooled Left+Right distributions:")
    say(f"    normal-angle edges {np.round(edges_ang,1).tolist()} deg; "
        f"radial edges {np.round(edges_rad,0).tolist()} px")

    for tg in TAGS:
        d = dat[tg]; g, v1, li = d["g"], d["v1"], d["li"]
        c = nphys(v1)[0]
        ed = {"ang": edges_ang, "rad": edges_rad, "c": c}
        d["ed"] = ed
        say(f"\n  {SHORT[tg]}  geometry summary")
        for f in (0, 1):
            m = li["fam"] == f
            say(f"    family {'A' if f==0 else 'B'}: {m.sum()} lines, corrected direction "
                f"{np.median(li['ang'][m]):.1f} deg (spread {li['ang'][m].std():.1f}), "
                f"normal {np.median(li['nrm'][m]):.1f} deg")
            say(f"      corners/line {g.counts[m].min()}-{g.counts[m].max()} "
                f"(median {np.median(g.counts[m]):.0f}), length median {np.median(li['len'][m]):.0f} px, "
                f"radial span median {np.median(li['rlo'][m]):.0f}-{np.median(li['rhi'][m]):.0f} px, "
                f"max endpoint leverage median {np.median(li['lev'][m]):.3f}")
        say(f"    board roll proxy: family-A median corrected direction "
            f"{np.median(li['ang'][li['fam']==0]):.1f} deg (single presentation, cannot be varied)")
        for tgt, nm in ((ETA, "eta"),):
            sh, pn, tn = info_share(g, v1, SCAL, tgt)
            o = np.argsort(-sh)
            say(f"    perpendicular information about {nm}: ||J_perp|| {pn:.1f} of ||J|| {tn:.1f}; "
                f"family A holds {sh[li['fam']==0].sum():.3f}, family B {sh[li['fam']==1].sum():.3f}")
            say(f"      top 5 lines carry {sh[o[:5]].sum():.3f}; "
                f"most informative line: family {'AB'[li['fam'][o[0]]]}, "
                f"{g.counts[o[0]]} corners, normal {li['nrm'][o[0]]:.0f} deg, "
                f"r {li['rlo'][o[0]]:.0f}-{li['rhi'][o[0]]:.0f} px, share {sh[o[0]]:.3f}")
        vfa = d["free"]
        for tgt, nm in ((ETA, "a"), (BIDX, "b")):
            sh, pn, tn = info_share(g, vfa, FREEAX, tgt)
            say(f"    perpendicular information about {nm} in the free-axis model: "
                f"||J_perp|| {pn:.1f} of ||J|| {tn:.1f}; family A {sh[li['fam']==0].sum():.3f}, "
                f"family B {sh[li['fam']==1].sum():.3f}")

    say(f"\n  BALANCED OBJECTIVE (raked weights, weighted TLS line fits)")
    for tg in TAGS:
        d = dat[tg]; g, v1, li, ed = d["g"], d["v1"], d["li"], d["ed"]
        w = rake(g, li, ed)
        gb = G(g.xy, g.counts, w)
        report_margins(say, g, li, ed, np.ones(g.n), f"{SHORT[tg]} ordinary")
        report_margins(say, g, li, ed, w, f"{SHORT[tg]} balanced")
        vb, cb, _ = best_fit(gb, SCAL, [v1.copy(), d["v0"].copy()])
        vb0, cb0, _ = best_fit(gb, ISO, [d["v0"].copy()])
        say(f"    {SHORT[tg]}: ordinary eta {v1[ETA]:+.7f} -> balanced eta {vb[ETA]:+.7f}; "
            f"balanced SSE {cb:.5f} vs balanced-isotropic {cb0:.5f} (gain {cb0-cb:+.5f})")
        d["bal"] = vb
        vfb, cfb, _ = best_fit(gb, FREEAX, [d["free"].copy(), vb.copy()])
        say(f"      balanced free-axis: a {vfb[ETA]:+.7f}, b {vfb[BIDX]:+.7f}, "
            f"gain over balanced scalar {cb-cfb:+.5f}")

    say(f"\n  MATCHED LEFT/RIGHT SUBSETS")
    matched(say, dat)

    say(f"\n  INTERNAL STABILITY OF SCALAR eta")
    for tg in TAGS:
        d = dat[tg]; g, v1, li = d["g"], d["v1"], d["li"]
        loo = []
        for i in range(g.nlines):
            keep = np.arange(g.nlines) != i
            gg = subset(g, keep)
            loo.append(fit(gg, SCAL, v1.copy())[0][ETA])
        loo = np.array(loo)
        o = np.argsort(np.abs(loo - v1[ETA]))[::-1]
        say(f"    {SHORT[tg]} leave-one-line-out: mean {loo.mean():+.7f}, sd {loo.std(ddof=1):.7f}, "
            f"range {loo.min():+.7f} to {loo.max():+.7f}")
        say(f"      most influential line: family {'AB'[li['fam'][o[0]]]}, {g.counts[o[0]]} corners, "
            f"removing it moves eta to {loo[o[0]]:+.7f} ({loo[o[0]]-v1[ETA]:+.7f})")
        bs = boot_scalar(g, v1, 300, 7)
        say(f"    {SHORT[tg]} line-cluster bootstrap, 300 resamples: mean {bs.mean():+.7f}, "
            f"sd {bs.std(ddof=1):.7f}, 5th {np.percentile(bs,5):+.7f}, "
            f"95th {np.percentile(bs,95):+.7f}, share negative {np.mean(bs<0):.3f}")
        d["boot"] = bs
    bl, br = dat[TAGS[0]]["boot"], dat[TAGS[1]]["boot"]
    say(f"    bootstrap overlap between Left and Right eta distributions: "
        f"Left 95th {np.percentile(bl,95):+.7f} vs Right 5th {np.percentile(br,5):+.7f}; "
        f"{'DISJOINT' if np.percentile(bl,95) < np.percentile(br,5) else 'OVERLAPPING'}")

    # ================================================================= SECTION 3
    say("\n" + "=" * 110)
    say("3  ESTIMATOR ARTIFACT UNDER A COMMON ANISOTROPY-FREE TRUTH")
    say("=" * 110)
    section3(say, dat)
    say(f"\n  runtime {time.time()-t0:.0f}s")
    return 0


def clip_grid(g):
    lo, hi = g.xy.min(axis=0), g.xy.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 40), np.linspace(lo[1], hi[1], 28))
    return np.stack([gx.ravel(), gy.ravel()], axis=1)


def subset(g, keepmask):
    idx = np.concatenate([np.arange(g.starts[i], g.starts[i] + g.counts[i])
                          for i in np.where(keepmask)[0]])
    return G(g.xy[idx], g.counts[keepmask])


def resample(g, li, rng):
    """Resample whole lines with replacement, keeping at least three lines in each family."""
    for _ in range(60):
        pick = rng.integers(0, g.nlines, g.nlines)
        f = li["fam"][pick]
        if (f == 0).sum() >= 3 and (f == 1).sum() >= 3:
            break
    idx = np.concatenate([np.arange(g.starts[i], g.starts[i] + g.counts[i]) for i in pick])
    return G(g.xy[idx], g.counts[pick])


def boot_scalar(g, v1, n, seed):
    li = line_info(g, v1)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        gg = resample(g, li, rng)
        try:
            out.append(fit(gg, SCAL, v1.copy())[0][ETA])
        except Exception:                                    # noqa: BLE001
            pass
    return np.array(out)


def boot_free(g, vf, n, seed):
    li = line_info(g, vf)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        gg = resample(g, li, rng)
        try:
            v = fit(gg, FREEAX, vf.copy())[0]
            out.append([v[ETA], v[BIDX]])
        except Exception:                                    # noqa: BLE001
            pass
    return np.array(out)


def matched(say, dat):
    """Greedy one-to-one line matching within family on standardized geometry features."""
    F = {}
    for tg in TAGS:
        d = dat[tg]; g, li = d["g"], d["li"]
        F[tg] = np.stack([li["nrm"], li["rlo"], li["rhi"], li["len"],
                          g.counts.astype(float)], axis=1)
    allf = np.concatenate([F[t] for t in TAGS])
    mu, sd = allf.mean(0), allf.std(0) + 1e-9
    for thr in (1.0, 1.5, 2.5):
        keep = {}
        used = set()
        A, B = TAGS
        for i in range(len(F[A])):
            best, bj = None, None
            for j in range(len(F[B])):
                if j in used or dat[A]["li"]["fam"][i] != dat[B]["li"]["fam"][j]:
                    continue
                dd = np.linalg.norm((F[A][i] - F[B][j]) / sd)
                if best is None or dd < best:
                    best, bj = dd, j
            if bj is not None and best <= thr:
                used.add(bj)
                keep.setdefault(A, []).append(i)
                keep.setdefault(B, []).append(bj)
        if A not in keep or len(keep[A]) < 8:
            say(f"    threshold {thr:.1f}: too few matched lines, skipped")
            continue
        res = []
        for t in TAGS:
            g = dat[t]["g"]
            m = np.zeros(g.nlines, bool); m[keep[t]] = True
            fam = dat[t]["li"]["fam"][m]
            gg = subset(g, m)
            v = fit(gg, SCAL, dat[t]["v1"].copy())[0]
            res.append((m.sum(), (fam == 0).sum(), (fam == 1).sum(), gg.n, v[ETA]))
        say(f"    threshold {thr:.1f} standardized units: "
            f"Left {res[0][0]} lines ({res[0][1]}A/{res[0][2]}B, {res[0][3]} corners) "
            f"eta {res[0][4]:+.7f}   |   "
            f"Right {res[1][0]} lines ({res[1][1]}A/{res[1][2]}B, {res[1][3]} corners) "
            f"eta {res[1][4]:+.7f}")


def section3(say, dat):
    rows = {}
    for tg in TAGS:
        d = dat[tg]
        r = truth_from_intersections(d["g"], d["v0"], d["li"])
        rows[tg] = r
        say(f"  {SHORT[tg]}: {len(r)} corners have both parent lines and give a single "
            f"intersection coordinate (of {d['g'].n} line-point records)")

    # verify the common-coordinate truth is exactly straight in both families
    for tg in TAGS:
        X, cnt, Ut = build_synth(rows[tg], lambda u: u)
        gt = G(Ut, cnt)
        rr = gt.straight(Ut)
        say(f"  {SHORT[tg]}: truth straightness residual across both families, "
            f"max {np.abs(rr).max():.3e} px over {len(cnt)} lines -> exactly straight")

    say(f"\n  Each geometry keeps its own fitted isotropic base (centre, a1..a4, q1, q2) so the")
    say(f"  synthetic pixels sit where the real corners sit. The misspecification added on top is")
    say(f"  the same normalized function of r/R for both geometries.")

    def base_fwd(v):
        c, k, p, _, _ = nphys(v)
        return c, k, p

    def make_fwd(c, k, p, extra=None):
        def fwd(u):
            t = u - c
            out = t + S.delta_r(t, k) + S.d_p(t, p)
            if extra is not None:
                rr = np.hypot(t[:, 0], t[:, 1])
                sc = extra(rr / R) / np.maximum(rr, 1e-9)
                out = out + t * sc[:, None]
            return out + c
        return fwd

    # one common radial misspecification, the mean k1..k7 minus mean k1..k4 across the two clips
    DK = np.mean([nphys(dat[t]["v7"])[1]
                  - np.concatenate([nphys(dat[t]["v0"])[1][:4], np.zeros(3)]) for t in TAGS],
                 axis=0)
    def k7fun(t, dk=DK):
        return sum(dk[j] * (t * R) ** (2 * j + 3) for j in range(7))

    def bumpfun(t, A):
        return A * np.exp(-((t - 0.75) / 0.15) ** 2)

    rmax = max(np.hypot(*(dat[t]["g"].xy - nphys(dat[t]["v0"])[0]).T).max() for t in TAGS)
    tg_ = np.linspace(0.05, rmax / R, 400)
    say(f"  common misspecification magnitudes over r/R in [0.05, {rmax/R:.2f}]:")
    say(f"    k1..k7 tail: peak |delta_r| {np.abs(k7fun(tg_)).max():.3f} px, monotone "
        f"{'yes' if np.all(np.diff(k7fun(tg_)) >= -1e-9) or np.all(np.diff(k7fun(tg_)) <= 1e-9) else 'no'}")

    scen = []
    scen.append(("exact k1..k4 isotropic truth (sanity)", None, None))
    scen.append(("monotone k1..k7 core outside the fitted model space", "k7", None))
    for amp in (0.25, 0.5, 1.0, 2.0):
        scen.append((f"smooth radial bump, peak {amp:.2f} px", "bump", amp))

    say(f"\n  {'scenario':52} {'Left eta':>12} {'Right eta':>12} {'difference':>12}")
    store = {}
    for lbl, kind, amp in scen:
        got = {}
        for tg in TAGS:
            d = dat[tg]
            c, k, p = base_fwd(d["v0"])
            extra = None
            if kind == "k7":
                extra = k7fun
            elif kind == "bump":
                extra = lambda t, A=amp: bumpfun(t, A)
            fwd = make_fwd(c, k, p, extra)
            X, cnt, Ut = build_synth(rows[tg], fwd)
            chk = np.abs(fwd(X) - Ut).max()
            gs = G(X, cnt)
            s0 = d["v0"].copy(); s0[ETA] = 0.0
            v = best_fit(gs, SCAL, [s0, d["v1"].copy()])[0]
            got[tg] = v[ETA]
            store[(lbl, tg)] = (v, gs, cnt, X, chk)
        say(f"  {lbl:52} {got[TAGS[0]]:+12.7f} {got[TAGS[1]]:+12.7f} "
            f"{got[TAGS[0]]-got[TAGS[1]]:+12.7f}")
    say(f"  {'observed real data':52} {dat[TAGS[0]]['v1'][ETA]:+12.7f} "
        f"{dat[TAGS[1]]['v1'][ETA]:+12.7f} "
        f"{dat[TAGS[0]]['v1'][ETA]-dat[TAGS[1]]['v1'][ETA]:+12.7f}")
    mx = max(abs(store[(l, t)][4]) for l, _, _ in scen for t in TAGS)
    say(f"  max Newton inversion error across all synthetic sets {mx:.2e} px")

    # noise replicates with line-block resampled real residuals on the largest-artifact scenario
    say(f"\n  Noise replicates, 20 per scenario, using line-block resampling of the real")
    say(f"  straightness residuals so within-line dependence is preserved.")
    for lbl, kind, amp in scen:
        if kind is None:
            continue
        out = {}
        for tg in TAGS:
            d = dat[tg]
            v, gs, cnt, X, _ = store[(lbl, tg)]
            realr = d["g"].straight(Uv(d["g"].xy, d["v1"]))
            blocks = [realr[d["g"].starts[i]:d["g"].starts[i] + d["g"].counts[i]]
                      for i in range(d["g"].nlines)]
            rng = np.random.default_rng(101)
            es = []
            for _ in range(20):
                pert = np.empty(gs.n)
                for i in range(gs.nlines):
                    a, b = gs.starts[i], gs.starts[i] + gs.counts[i]
                    blk = blocks[rng.integers(0, len(blocks))]
                    reps = int(np.ceil((b - a) / len(blk)))
                    pert[a:b] = np.tile(blk, reps)[:b - a] * rng.choice([-1.0, 1.0])
                nrm = np.empty((gs.n, 2))
                U = gs.xy
                for i in range(gs.nlines):
                    a, b = gs.starts[i], gs.starts[i] + gs.counts[i]
                    q = U[a:b] - U[a:b].mean(0)
                    th = 0.5 * math.atan2(2 * float(q[:, 0] @ q[:, 1]),
                                          float(q[:, 0] @ q[:, 0] - q[:, 1] @ q[:, 1]))
                    nrm[a:b] = [-math.sin(th), math.cos(th)]
                g2 = G(gs.xy + nrm * pert[:, None], cnt)
                s0 = d["v0"].copy(); s0[ETA] = 0.0
                try:
                    es.append(fit(g2, SCAL, s0)[0][ETA])
                except Exception:                            # noqa: BLE001
                    pass
            out[tg] = np.array(es)
        l_, r_ = out[TAGS[0]], out[TAGS[1]]
        say(f"    {lbl}")
        say(f"      Left  mean {l_.mean():+.7f} sd {l_.std(ddof=1):.7f}   "
            f"Right mean {r_.mean():+.7f} sd {r_.std(ddof=1):.7f}   "
            f"mean difference {l_.mean()-r_.mean():+.7f}")

    # does balancing remove whatever artifact appears
    say(f"\n  Balanced-objective refit of the largest-artifact scenario:")
    lbl = scen[-1][0]
    for tg in TAGS:
        d = dat[tg]
        v, gs, cnt, X, _ = store[(lbl, tg)]
        lis = line_info(gs, v)
        ed = {"ang": d["ed"]["ang"], "rad": d["ed"]["rad"], "c": nphys(v)[0]}
        wb = rake(gs, lis, ed)
        gb = G(gs.xy, cnt, wb)
        s0 = d["v0"].copy(); s0[ETA] = 0.0
        vb = best_fit(gb, SCAL, [s0, v.copy()])[0]
        say(f"    {SHORT[tg]}: ordinary {v[ETA]:+.7f} -> balanced {vb[ETA]:+.7f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
