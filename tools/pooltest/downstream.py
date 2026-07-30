#!/usr/bin/env python3
"""Downstream geometry with the distortion map passed in EXPLICITLY.

WHY THIS EXISTS. The previous harness worked for eta only because
`fisheye_knownlength_analysis.py:84` monkeypatched `parity.undistort = nodes.undistort13` at import
time. Without that side effect, `parity.sightline` (parity.py:117) calls the pure 13-parameter
`parity.undistort` (parity.py:60), which ignores theta[13] entirely -- so every M1 candidate would have
carried eta through its calibration but silently dropped it from every measurement sightline. That is
hidden global state deciding a scientific result, and it is removed here.

Every function in this module takes a `DistortionMap`. There is no module-level mutable state, no
"current model", and no monkeypatch. The map itself owns exactly one implementation of the forward
map: it delegates to lattice.U, which delegates to the parity-verified parity_step5.undistort14. M0 and
M1 are the SAME code path, distinguished only by whether theta[13] is zero.

SECOND DEFECT, found by independent audit 2026-07-29. Explicit injection removed the hidden state but
left camera identity as documentation rather than a check: a caller could hand the Left camera's map to
the Right camera's calibration and the whole pipeline would run to completion. The audit did exactly
that on the 2015 document and moved conventional MAE from 3.9146 mm to 4.2777 mm with no error, no
warning, and no way to tell the result apart from a real one. `CameraIdentity` below makes that
unrepresentable: a map is bound to the camera it was fitted for, and `build_calibration` refuses a map
bound to anything else. See `CameraIdentity` for why "Left"/"Right" is not an identity.

Run with ~/.venvs/vidsync/bin/python.
"""

import dataclasses
import hashlib
import math
import os
import sqlite3
import subprocess

import numpy as np
from scipy.optimize import least_squares

import harness_import

HERE = os.path.dirname(os.path.abspath(__file__))
TRI_ORACLE = os.path.join(HERE, "tri_oracle")

L = harness_import.load          # ONE shared instance per module; see harness_import.py

LT = L("lattice")
OB = L("objectives")
st = L("stage2")
nd = L("nodes")

AX = {"x": 0, "y": 1, "z": 2}


# =============================================================== camera identity


_SHA_CACHE = {}


def document_sha256(path):
    """SHA-256 of a .vsd, cached by (path, size, mtime). Read-only; never opens the document."""
    stt = os.stat(path)
    key = (os.path.abspath(path), stt.st_size, stt.st_mtime_ns)
    if key not in _SHA_CACHE:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        _SHA_CACHE[key] = h.hexdigest()
    return _SHA_CACHE[key]


def document_key(path):
    """A safe, stable, publishable name for a document: its basename without the extension.

    Manifests carry this plus the SHA-256, never the absolute path, because the paths run through
    private field-site directory structures.
    """
    return os.path.splitext(os.path.basename(path))[0]


@dataclasses.dataclass(frozen=True)
class CameraIdentity:
    """Which camera, in which document, a distortion map was fitted for.

    WHY NOT "Left"/"Right". Those strings recur in every document, so they cannot distinguish cameras
    across documents, and on this corpus they are not even ordered consistently WITHIN the convention:

        pool test           Left Camera  -> ZVSCALIBRATION.Z_PK 2,  Right Camera -> Z_PK 1
        2015-09-04-1 (8 mm) Left Camera  -> Z_PK 1,                 Right Camera -> Z_PK 2
        2015-06-22-1 (mid)  Left Camera  -> Z_PK 1,                 Right Camera -> Z_PK 2

    So neither the label nor the primary key alone is an identity: `Z_PK` is only 1 or 2 in every
    document, and the label-to-key mapping is inverted between the pool test and the 2015 documents.
    The identity used here is therefore the PAIR

        (document SHA-256, ZVSCALIBRATION.Z_PK)

    which is immutable for a given document revision and unique within the corpus. `clip_pk`
    (ZVSVIDEOCLIP.Z_PK) is recorded too but is redundant given `cal_pk`; `clip_name` is human-readable
    metadata only and is deliberately NOT part of the comparison, so that a Left/Right relabelling
    could never make two different cameras compare equal.

    Hashing the whole document also means a map fitted against one revision of a .vsd will not silently
    be applied to a re-saved revision with different node clicks.
    """

    doc_sha256: str
    doc_key: str
    cal_pk: int
    clip_pk: int
    clip_name: str

    @property
    def token(self):
        """The part that actually establishes identity. Labels are excluded on purpose."""
        return (self.doc_sha256, int(self.cal_pk))

    def matches(self, other):
        return isinstance(other, CameraIdentity) and self.token == other.token

    def describe(self):
        return (f"{self.doc_key}/{self.clip_name} (cal_pk={self.cal_pk}, "
                f"doc {self.doc_sha256[:12]}...)")

    def to_dict(self):
        """Manifest-safe: document KEY and hash, never the absolute path."""
        return {"doc_key": self.doc_key, "doc_sha256": self.doc_sha256,
                "cal_pk": int(self.cal_pk), "clip_pk": int(self.clip_pk),
                "clip_name": self.clip_name}


class CameraBindingError(RuntimeError):
    """A distortion map was used with a camera it was not fitted for."""


def load_bound_cals(vsd):
    """`stage2.load_cal`, with every calibration tagged with its immutable CameraIdentity.

    Authoritative downstream code must load calibrations through here rather than `stage2.load_cal`,
    because `build_calibration` refuses a calibration that carries no identity. That is the fail-closed
    half of the fix: forgetting to bind is an error, not a silent unchecked run.
    """
    sha = document_sha256(vsd)
    key = document_key(vsd)
    db = sqlite3.connect(f"file:{vsd}?mode=ro", uri=True)
    clip_pk = {r[0]: r[1] for r in db.execute(
        "SELECT c.Z_PK, c.ZVIDEOCLIP FROM ZVSCALIBRATION c")}
    db.close()
    cals = st.load_cal(vsd)
    for clip, c in cals.items():
        c["identity"] = CameraIdentity(doc_sha256=sha, doc_key=key, cal_pk=int(c["pk"]),
                                       clip_pk=int(clip_pk[c["pk"]]), clip_name=clip)
        c["node_source"] = "vsd"
    return cals


def calibration_identity(cal):
    """The identity of a calibration dict, or a clear error saying how to get one."""
    ident = cal.get("identity")
    if not isinstance(ident, CameraIdentity):
        raise CameraBindingError(
            f"calibration for clip {cal.get('clip')!r} carries no CameraIdentity. Load calibrations "
            f"with downstream.load_bound_cals(vsd), not stage2.load_cal(vsd); an unbound calibration "
            f"cannot verify that the distortion map belongs to this camera.")
    return ident


# =============================================================== the injected map


class DistortionMap:
    """A distortion candidate, carried explicitly and BOUND to the camera it was fitted for.

    `theta14` is always length 14; entry 13 is the conjugated anisotropy eta. A 13-parameter map is
    just eta = 0, constructed through `from13`, so legacy behaviour is an explicit map rather than a
    separate code path.

    `identity` is the `CameraIdentity` this map belongs to. A map may be constructed unbound -- that is
    useful for pure forward/inverse arithmetic in tests -- but `build_calibration` refuses an unbound
    map, so nothing can reach a reconstruction without having been bound.
    """

    def __init__(self, theta14, name="unnamed", model=None, source=None, identity=None):
        t = np.asarray(theta14, float).ravel()
        if t.size == 13:
            raise ValueError("pass a 14-vector, or use DistortionMap.from13 to be explicit")
        if t.size != 14:
            raise ValueError(f"theta14 must have 14 entries, got {t.size}")
        if not np.all(np.isfinite(t)):
            raise ValueError("non-finite distortion parameter")
        if identity is not None and not isinstance(identity, CameraIdentity):
            raise TypeError(f"identity must be a CameraIdentity, got {type(identity).__name__}")
        self.theta14 = t
        self.name = name
        self.model = model if model is not None else ("M0" if t[13] == 0.0 else "M1")
        self.source = source
        self.identity = identity

    @classmethod
    def from13(cls, theta13, name="unnamed", **kw):
        """The shipped 13-parameter map, stated explicitly as eta = 0."""
        t = np.zeros(14)
        t[:13] = np.asarray(theta13, float).ravel()
        return cls(t, name=name, model="M0", **kw)

    @classmethod
    def for_camera(cls, theta14, cal, name="unnamed", **kw):
        """Bind at construction to the camera whose calibration dict is `cal`. Preferred constructor."""
        return cls(theta14, name=name, identity=calibration_identity(cal), **kw)

    @classmethod
    def from13_for_camera(cls, theta13, cal, name="unnamed", **kw):
        """`from13`, bound to `cal`'s camera. Used for the stored ZVSCALIBRATION anchor."""
        return cls.from13(theta13, name=name, identity=calibration_identity(cal), **kw)

    def bound_to(self, cal):
        """A copy of this map bound to `cal`'s camera. Errors if it is already bound elsewhere."""
        ident = calibration_identity(cal)
        if self.identity is not None and not self.identity.matches(ident):
            raise CameraBindingError(
                f"map {self.name!r} is already bound to {self.identity.describe()} and cannot be "
                f"re-bound to {ident.describe()}. For a deliberate experiment use "
                f"rebind_for_cross_camera_experiment(cal, reason=...).")
        return DistortionMap(self.theta14, name=self.name, model=self.model, source=self.source,
                             identity=ident)

    def rebind_for_cross_camera_experiment(self, cal, reason):
        """DELIBERATE cross-camera / cross-document transfer. Experiments only, never in a result.

        This is the ONLY way to move a map off its own camera. It is not a boolean flag on a normal
        call path, because the audited failure mode was exactly a caller not noticing that it had
        supplied the wrong map; a flag defaulting to off would have been set casually and the mistake
        would have survived. `reason` must be a non-trivial sentence and is recorded on the returned
        map's `source`, so anything downstream that serialises provenance shows the transfer.
        """
        if not isinstance(reason, str) or len(reason.strip()) < 20:
            raise ValueError(
                "rebind_for_cross_camera_experiment requires an explicit written reason of at least "
                "20 characters explaining why a map is being taken off its own camera; this call is "
                "not for production result paths")
        ident = calibration_identity(cal)
        old = self.identity.describe() if self.identity is not None else "unbound"
        return DistortionMap(
            self.theta14, name=f"{self.name} [CROSS-CAMERA EXPERIMENT]", model=self.model,
            source=f"CROSS-CAMERA REBIND from {old} to {ident.describe()}; reason: {reason.strip()}",
            identity=ident)

    @property
    def eta(self):
        return float(self.theta14[13])

    @property
    def centre(self):
        return self.theta14[:2].copy()

    # -- eta cannot be lost by silently degrading the object to a 13-vector ---------------------
    #
    # `np.asarray(dmap)` / `list(dmap)` / `dmap[:13]` all used to be plausible-looking ways to reach
    # "the distortion parameters", and every one of them would have dropped eta without a word. The
    # only supported accessors are `.theta14` (all 14) and `.theta13_and_eta()` (explicitly split).

    def __array__(self, dtype=None, copy=None):
        if self.eta != 0.0:
            raise TypeError(
                f"refusing to convert {self!r} to a bare array: eta = {self.eta:+.8f} would be "
                f"dropped by any 13-parameter consumer. Use .theta14, or .theta13_and_eta() to split "
                f"it explicitly.")
        t = self.theta14 if dtype is None else self.theta14.astype(dtype)
        return t.copy() if copy is not False else t

    def __iter__(self):
        raise TypeError(f"refusing to iterate {self!r}; use .theta14 or .theta13_and_eta()")

    def __getitem__(self, k):
        raise TypeError(f"refusing to slice {self!r}; use .theta14 or .theta13_and_eta()")

    def theta13_and_eta(self):
        """The 13 shipped parameters and eta, split explicitly because the caller said so."""
        return self.theta14[:13].copy(), self.eta

    def forward(self, xy):
        """Raw sensor pixels -> ideal pinhole pixels. (n, 2) in, (n, 2) out."""
        return LT.U(np.atleast_2d(np.asarray(xy, float)), self.theta14)

    def forward_xy(self, x, y):
        u = self.forward(np.array([[float(x), float(y)]]))
        return float(u[0, 0]), float(u[0, 1])

    def jacobian(self, xy):
        return LT.jac_U(np.atleast_2d(np.asarray(xy, float)), self.theta14)

    def inverse(self, uv, **kw):
        """Ideal -> raw. Returns (xy, converged_mask, max_residual)."""
        return LT.inv_U(np.atleast_2d(np.asarray(uv, float)), self.theta14, **kw)

    def meta(self):
        return {"name": self.name, "model": self.model, "eta": self.eta,
                "centre": self.centre.tolist(), "source": self.source,
                "theta14": self.theta14.tolist(),
                "identity": self.identity.to_dict() if self.identity is not None else None,
                "implementation": "lattice.U -> parity_step5.undistort14"}

    def __repr__(self):
        who = self.identity.describe() if self.identity is not None else "UNBOUND"
        return (f"DistortionMap({self.name!r}, model={self.model}, eta={self.eta:+.8f}, "
                f"camera={who})")


# =============================================================== calibration


def build_calibration(cal, dmap, niter=0):
    """Rebuild the full refractive calibration under `dmap`, from the RAW node clicks.

    The oracle already takes the distortion vector and eta as explicit arguments, so this stage never
    had hidden state; the map is threaded through for uniformity and provenance.

    THE BINDING GATE. This is the single chokepoint every reconstruction must pass, so it is where the
    map is checked against the camera. Nothing below this function accepts a free map: `sightline`,
    `triangulate_lm`, `triangulate_nm_batch` and `point_diagnostics` all read `cam["dmap"]`. A
    Left/Right swap or a map from another document therefore fails HERE, before any node residual or
    measurement is computed.
    """
    ident = calibration_identity(cal)
    if dmap.identity is None:
        raise CameraBindingError(
            f"distortion map {dmap.name!r} is unbound and cannot be used to calibrate "
            f"{ident.describe()}. Construct it with DistortionMap.for_camera(theta14, cal) or bind an "
            f"existing map with .bound_to(cal).")
    if not dmap.identity.matches(ident):
        raise CameraBindingError(
            f"CAMERA BINDING VIOLATION: distortion map {dmap.name!r} was fitted for "
            f"{dmap.identity.describe()} but build_calibration was asked to apply it to "
            f"{ident.describe()}.\n"
            f"  map camera:   doc {dmap.identity.doc_sha256[:16]} cal_pk={dmap.identity.cal_pk} "
            f"clip={dmap.identity.clip_name!r}\n"
            f"  target camera: doc {ident.doc_sha256[:16]} cal_pk={ident.cal_pk} "
            f"clip={ident.clip_name!r}\n"
            f"  {'Same document, different camera -- this is a Left/Right swap.' if dmap.identity.doc_sha256 == ident.doc_sha256 else 'Different document -- this map belongs to another .vsd.'}\n"
            f"  Clip NAMES are not an identity: 'Left Camera' is cal_pk 2 in the pool test but "
            f"cal_pk 1 in both 2015 documents. If the transfer is deliberate, use "
            f"rebind_for_cross_camera_experiment(cal, reason=...).")
    o = st.run_oracle(cal, dist=dmap.theta14[:13], eta=dmap.eta, niter=niter)
    return {"ah": cal["ah"], "av": cal["av"], "front_d": cal["front_d"], "back_d": cal["back_d"],
            "dmap": dmap, "identity": ident, "node_source": cal.get("node_source", "vsd"),
            "cam": o["cam"], "camPLD": o["camPLD"],
            "s2f": nd.flat_colmajor_to_nested(o["FRONT"]),
            "s2b": nd.flat_colmajor_to_nested(o["BACK"]),
            "f2s": nd.flat_colmajor_to_nested(o["FRONTINV"]),
            "oracle": o}


def node_residuals(cal, cam, dmap=None):
    """Front and back node residuals under the CAMERA's own map, in world units.

    `dmap` is accepted only so existing callers keep working, and if supplied it must be the very map
    the camera was built with -- passing a different one was another way to smuggle the wrong map into
    a reported number.
    """
    if dmap is not None and dmap is not cam["dmap"]:
        if not (dmap.identity is not None and cam["dmap"].identity is not None
                and dmap.identity.matches(cam["dmap"].identity)
                and np.array_equal(dmap.theta14, cam["dmap"].theta14)):
            raise CameraBindingError(
                f"node_residuals was given map {dmap.name!r} but the calibration was built with "
                f"{cam['dmap'].name!r}; residuals would describe neither. Omit the argument.")
    dmap = cam["dmap"]
    if not calibration_identity(cal).matches(cam["identity"]):
        raise CameraBindingError(
            f"node_residuals: nodes come from {calibration_identity(cal).describe()} but the "
            f"calibration was built for {cam['identity'].describe()}")
    fr = [math.hypot(*(np.array(nd.apply3(cam["s2f"], *dmap.forward_xy(x, y)))
                       - np.array([wh, wv]))) for x, y, wh, wv in cal["front"]]
    app = cam["oracle"].get("app", [])
    appc = np.array([[a[0], a[1]] for a in app], float)
    bk = [math.hypot(*(np.array(nd.apply3(cam["s2b"], *dmap.forward_xy(x, y))) - a))
          for (x, y, _, _), a in zip(cal["back"], appc)]
    true = np.array([[wh, wv] for _, _, wh, wv in cal["back"]], float)
    return {"front_rms": float(np.sqrt(np.mean(np.square(fr)))),
            "front_max": float(np.max(fr)),
            "back_rms_vs_apparent": float(np.sqrt(np.mean(np.square(bk)))),
            "apparent_disp_mean": float(np.linalg.norm(appc - true, axis=1).mean()),
            "apparent_disp_max": float(np.linalg.norm(appc - true, axis=1).max()),
            "refraction_failures": int(sum(1 for a in app if a[3] != 0)),
            "refraction_resid_max": float(max((a[4] for a in app), default=float("nan")))}


# =============================================================== sightlines and triangulation


def lift(h, v, depth, ah, av):
    if ah == "x":
        return (h, v, depth) if av == "y" else (h, depth, v)
    if ah == "y":
        return (v, h, depth) if av == "x" else (depth, h, v)
    return (v, depth, h) if av == "x" else (depth, v, h)


def drop(p, ah, av):
    return p[AX[ah]], p[AX[av]]


def sightline(sx, sy, cam):
    """The two-plane sightline for a raw screen click, undistorted by that CAMERA's injected map.

    The map is deliberately read from `cam["dmap"]` rather than passed separately. A distortion map
    belongs to one camera, and the cameras of a stereo pair have different ones; an earlier version of
    this module took the map as an argument and a caller passed the Left map for both cameras, moving
    reconstructed points by up to 48 mm. Binding the map to the camera at build_calibration time makes
    that mistake unrepresentable while keeping the injection explicit.

    Since 2026-07-29 `cam["dmap"]` is additionally guaranteed to have been VERIFIED against the
    camera's `CameraIdentity` in build_calibration, so this function cannot be reached with a map from
    the sibling camera or from another document.
    """
    dmap = cam["dmap"]
    u = dmap.forward_xy(sx, sy)
    f = nd.apply3(cam["s2f"], *u)
    b = nd.apply3(cam["s2b"], *u)
    return (lift(f[0], f[1], cam["front_d"], cam["ah"], cam["av"]),
            lift(b[0], b[1], cam["back_d"], cam["ah"], cam["av"]))


def cpa_lines(lines):
    """UtilityFunctions.mm:255 least-squares closest point of approach, plus mean point-line distance."""
    A = np.zeros((3, 3)); b = np.zeros(3)
    for p, q in lines:
        d = np.array(q, float) - np.array(p, float)
        n = np.linalg.norm(d)
        if n == 0:
            continue
        v = d / n
        M = np.eye(3) - np.outer(v, v)
        A += M; b += M @ np.array(p, float)
    P = np.linalg.solve(A, b)
    tot = 0.0
    for p, q in lines:
        a = np.array(p, float) - P
        e = np.array(q, float) - np.array(p, float)
        n2 = np.linalg.norm(e)
        if n2 == 0:
            continue
        tot += math.sqrt(max(0.0, (a @ a * n2 * n2 - (a @ e) ** 2) / (n2 * n2)))
    return P, tot / len(lines)


def reproject(P, cam):
    """VSPoint.m: candidate 3D point -> line to camera -> front plane -> undistorted screen."""
    ax = AX[({"x", "y", "z"} - {cam["ah"], cam["av"]}).pop()]
    da = P[ax] - cam["front_d"]
    db = cam["cam"][ax] - cam["front_d"]
    if abs(da - db) < 1e-15:
        return None
    t = da / (da - db)
    hit = tuple(P[i] + t * (cam["cam"][i] - P[i]) for i in range(3))
    return nd.apply3(cam["f2s"], *drop(hit, cam["ah"], cam["av"]))


def _obs_undistorted(obs):
    return [(cam, cam["dmap"].forward_xy(xy[0], xy[1])) for cam, xy in obs]


def triangulate_lm(obs):
    """CPA seed then scipy least_squares 'lm' on the production cost. Efficient, NOT production."""
    lines = [sightline(xy[0], xy[1], cam) for cam, xy in obs]
    seed, pld = cpa_lines(lines)
    und = _obs_undistorted(obs)

    def res(P):
        out = []
        for cam, u in und:
            r = reproject(P, cam)
            out += [0.0, 0.0] if r is None else [r[0] - u[0], r[1] - u[1]]
        return np.array(out)

    r = least_squares(res, seed, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=20000)
    v = res(r.x)
    return {"X": np.array(r.x, float), "cost": float(v @ v), "pld": pld,
            "rep": float(math.sqrt((v @ v) / len(und))), "nfev": int(r.nfev), "solver": "lm"}


def triangulate_nm_batch(obs_list):
    """Production's own GSL nmsimplex2 replay, batched through tri_oracle.

    Same seed, cost, parameterization, initial step sizes, size tolerance 1e-6 and 500-iteration cap
    as VSPoint.m:147-215.
    """
    if not obs_list:
        return []
    blocks = [str(len(obs_list))]
    seeds = []
    for obs in obs_list:
        lines = [sightline(xy[0], xy[1], cam) for cam, xy in obs]
        seed, _ = cpa_lines(lines)
        seeds.append(seed)
        blocks.append(str(len(obs)))
        for cam, xy in obs:
            u = cam["dmap"].forward_xy(xy[0], xy[1])
            blocks.append(" ".join([repr(float(cam["cam"][0])), repr(float(cam["cam"][1])),
                                    repr(float(cam["cam"][2])), cam["ah"], cam["av"],
                                    repr(float(cam["front_d"]))]
                                   + [repr(float(v)) for row in cam["f2s"] for v in row]
                                   + [repr(float(u[0])), repr(float(u[1]))]))
        blocks.append(" ".join(repr(float(v)) for v in seed))
    r = subprocess.run([TRI_ORACLE], input="\n".join(blocks) + "\n", capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"tri_oracle failed: {r.stderr[:400]}")
    out = [None] * len(obs_list)
    for ln in r.stdout.splitlines():
        t = ln.split()
        if t[0] != "TRI":
            continue
        i = int(t[1])
        out[i] = {"X": np.array([float(t[2]), float(t[3]), float(t[4])]), "cost": float(t[5]),
                  "iters": int(t[6]), "status": int(t[7]), "size": float(t[8]),
                  "seed": seeds[i], "solver": "nm"}
    return out


# =============================================================== measurement bookkeeping


def observations(pk, cams, clicks):
    """The (calibration, raw click) pairs for one measured point, in a deterministic clip order."""
    order = sorted(cams)
    return [(cams[cl], clicks[pk][cl]) for cl in order if cl in clicks.get(pk, {})]


def point_diagnostics(obs, X, frame=(1920.0, 1080.0)):
    """Per-point geometry that does not depend on the solver."""
    rad, edge = {}, {}
    for i, (cam, xy) in enumerate(obs):
        c = cam["dmap"].centre
        rad[i] = math.hypot(xy[0] - c[0], xy[1] - c[1])
        edge[i] = min(xy[0], frame[0] - xy[0], xy[1], frame[1] - xy[1])
    dirs = []
    for cam, xy in obs:
        p, q = sightline(xy[0], xy[1], cam)
        d = np.array(q, float) - np.array(p, float)
        dirs.append(d / np.linalg.norm(d))
    stereo = float("nan")
    if len(dirs) >= 2:
        stereo = 90.0 - math.degrees(math.acos(max(-1.0, min(1.0, abs(float(dirs[0] @ dirs[1]))))))
    return {"radius": max(rad.values()), "edge": min(edge.values()), "stereo_deg": stereo,
            "camdist": min(float(np.linalg.norm(np.asarray(X, float) - np.array(c["cam"], float)))
                           for c, _ in obs)}
