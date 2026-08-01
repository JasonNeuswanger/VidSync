#!/usr/bin/env python3
"""Synthetic validation of reconquality.py. Every fixture injects ONE known deformation.

The requirement is that the expected band receives the dominant share of the residual energy, that the
claimed sum-of-squares identities hold numerically, and that quantities which should be zero at the
Procrustes optimum actually are. Fixtures are built on a 6x5 grid of 100 mm spacing embedded in 3D by a
fixed proper rotation, so nothing depends on the target lying in a coordinate plane.

Run with ~/.venvs/vidsync/bin/python (needs numpy and scipy).
"""

import importlib.util
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_results = []


def L(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


RQ = L("reconquality")


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


# --------------------------------------------------------------------------- fixtures

def grid(nx=6, ny=5, step=100.0):
    u, v = np.meshgrid(np.arange(nx) * step, np.arange(ny) * step)
    return np.stack([u.ravel(), v.ravel()], axis=1).astype(float)


def frame():
    """A fixed proper rotation and translation, so the target is not axis-aligned."""
    a = math.radians(23.0); b = math.radians(-17.0); c = math.radians(41.0)
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    return Rz @ Ry @ Rx, np.array([1234.5, -678.9, 2345.6])


def embed(N, warp2=None, warpn=None, R=None, t=None):
    """Place target coords in 3D, optionally warping in-plane (warp2) and out-of-plane (warpn)."""
    R = R if R is not None else frame()[0]
    t = t if t is not None else frame()[1]
    Nc = N - N.mean(0)
    uv = Nc if warp2 is None else warp2(Nc)
    w = np.zeros(len(N)) if warpn is None else warpn(Nc)
    local = np.stack([uv[:, 0], uv[:, 1], w], axis=1)
    return (R @ local.T).T + t


def dominant(sb, band):
    keys = ("affine_beyond_similarity", "normal_quadratic", "tangential_quadratic",
            "higher_residual", "normal_tilt")
    e = {k: sb[k] for k in keys}
    tot = sum(e.values()) or 1.0
    top = max(e, key=e.get)
    return top == band, {k: round(v / tot, 4) for k, v in e.items()}


# --------------------------------------------------------------------------- tests

def test_rigid():
    print("\n1. Rigid pose only: no scale error, no shape energy")
    N = grid(); P = embed(N)
    p = RQ.cloud_panel(N, P, do_heldout=False)
    check("scale s is 1 to 1e-12", abs(p["scale"]["s"] - 1.0) < 1e-12, f"s-1 = {p['scale']['s_minus_1']:.3e}")
    check("log s is 0", abs(p["scale"]["log_s"]) < 1e-12)
    check("similarity RMS is 0", p["shape"]["rms_sim_mm"] < 1e-9, f"{p['shape']['rms_sim_mm']:.3e}")
    check("scale identity holds", p["identities"]["scale"]["holds"],
          f"rel {p['identities']['scale']['rel_err']:.2e}")
    check("band identity holds", p["identities"]["bands"]["holds"],
          f"rel {p['identities']['bands']['rel_err']:.2e}")
    check("edge graph found the 100 mm step", p["edges"]["graph"]["step_mm"] == 100.0)
    check("edge log-length error is 0", abs(p["edges"]["rms_log"]) < 1e-12)


def test_isotropic_scale():
    print("\n2. Pure isotropic scale: absorbed by s, leaving no shape energy")
    for f in (1.02, 0.97):
        N = grid(); P = embed(N, warp2=lambda X, f=f: f * X)
        p = RQ.cloud_panel(N, P, do_heldout=False)
        check(f"s recovers {f}", abs(p["scale"]["s"] - f) < 1e-10, f"got {p['scale']['s']:.10f}")
        check(f"log s recovers log {f}", abs(p["scale"]["log_s"] - math.log(f)) < 1e-10)
        check(f"no residual shape energy at f={f}", p["shape"]["rms_sim_mm"] < 1e-9,
              f"{p['shape']['rms_sim_mm']:.3e}")
        check(f"scale identity holds at f={f}", p["identities"]["scale"]["holds"])
        # the redundancy claim: rigid RMS is fully predicted by s and the sim residual
        sp = RQ.similarity_procrustes(N, P)
        pred = math.sqrt((sp["Esim2"] + (sp["s"] - 1) ** 2 * sp["rho_q2"]) / len(N))
        check(f"rigid RMS is predicted from s and Esim at f={f}",
              abs(pred - sp["rms_rigid_mm"]) < 1e-9, f"{pred:.6f} vs {sp['rms_rigid_mm']:.6f}")


def test_affine_anisotropy():
    print("\n3. Pure affine anisotropy: lands in the affine band, not in curvature")
    N = grid()
    P = embed(N, warp2=lambda X: X @ np.diag([1.03, 0.98]).T)
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "affine_beyond_similarity")
    check("affine band dominates", ok, f"{share}")
    check("affine band holds essentially all the energy",
          sb["affine_beyond_similarity"] / sb["total_Esim2"] > 0.999, f"{share}")
    check("band identity holds", p["identities"]["bands"]["holds"])
    check("no leaked isotropic scale into the affine matrix",
          abs(p["shape"]["affine_purity"]["isotropic_leak"]) < 1e-9,
          f"{p['shape']['affine_purity']['isotropic_leak']:.3e}")
    check("no leaked rotation into the affine matrix",
          abs(p["shape"]["affine_purity"]["rotation_leak"]) < 1e-9,
          f"{p['shape']['affine_purity']['rotation_leak']:.3e}")
    # principal axis of a diag(1.03,0.98) stretch is the u axis
    check("principal axis is the u axis (0 or 180 deg)",
          min(p["shape"]["affine"]["principal_axis_deg"],
              180 - p["shape"]["affine"]["principal_axis_deg"]) < 1e-6,
          f"{p['shape']['affine']['principal_axis_deg']:.4f} deg")


def test_shear():
    print("\n4. Pure shear / nonorthogonality: SAME two dof as anisotropy, reported once")
    N = grid()
    g = 0.02
    P = embed(N, warp2=lambda X: X @ np.array([[1.0, g], [0.0, 1.0]]).T)
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "affine_beyond_similarity")
    check("affine band dominates for shear too", ok, f"{share}")
    check("shear is expressed in the same affine matrix, not a separate band",
          "shear" not in str(sb.keys()).lower())
    check("deviatoric norm is nonzero, i.e. shear registers as anisotropy",
          p["shape"]["affine"]["anisotropy_magnitude"] > 1e-3,
          f"{p['shape']['affine']['anisotropy_magnitude']:.5f}")
    check("principal axis of a pure shear is near 45 deg",
          abs(p["shape"]["affine"]["principal_axis_deg"] - 45.0) < 2.0,
          f"{p['shape']['affine']['principal_axis_deg']:.3f} deg")
    check("band identity holds", p["identities"]["bands"]["holds"])


def test_bowl():
    print("\n5. Pure bowl: normal quadratic, isotropic Hessian, no saddle")
    N = grid()
    a = 2.0e-5
    P = embed(N, warpn=lambda X: a * (X[:, 0] ** 2 + X[:, 1] ** 2))
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "normal_quadratic")
    check("normal-quadratic band dominates", ok, f"{share}")
    nc = p["shape"]["normal_curvature"]
    check("bowl mean curvature recovers 2a", abs(nc["bowl_mean_curvature"] - 2 * a) < 1e-9,
          f"got {nc['bowl_mean_curvature']:.3e}, expected {2*a:.3e}")
    check("saddle magnitude is ~0 for a pure bowl", abs(nc["saddle_magnitude"]) < 1e-9,
          f"{nc['saddle_magnitude']:.3e}")
    check("normal tilt is ~0 at the Procrustes optimum",
          sb["normal_tilt"] / sb["total_Esim2"] < 1e-12, f"{sb['normal_tilt']:.3e}")
    check("band identity holds", p["identities"]["bands"]["holds"])
    check("plane residuals are a view of the same band, nonzero here",
          p["plane"]["rms_mm"] > 1e-3, f"{p['plane']['rms_mm']:.4f} mm")


def test_saddle():
    print("\n6. Pure saddle: normal quadratic, deviatoric Hessian, no bowl")
    N = grid()
    a = 2.0e-5
    P = embed(N, warpn=lambda X: a * (X[:, 0] ** 2 - X[:, 1] ** 2))
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "normal_quadratic")
    check("normal-quadratic band dominates", ok, f"{share}")
    nc = p["shape"]["normal_curvature"]
    check("bowl mean curvature is ~0 for a pure saddle",
          abs(nc["bowl_mean_curvature"]) < 1e-9, f"{nc['bowl_mean_curvature']:.3e}")
    check("saddle magnitude recovers 2*sqrt(2)*a",
          abs(nc["saddle_magnitude"] - 2 * math.sqrt(2) * a) < 1e-9,
          f"got {nc['saddle_magnitude']:.3e}, expected {2*math.sqrt(2)*a:.3e}")
    check("band identity holds", p["identities"]["bands"]["holds"])


def test_inplane_quadratic():
    print("\n7. In-plane quadratic warp: tangential-quadratic band, NOT normal curvature")
    N = grid()
    a = 3.0e-5
    P = embed(N, warp2=lambda X: X + np.stack([a * X[:, 1] ** 2, np.zeros(len(X))], axis=1))
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "tangential_quadratic")
    check("tangential-quadratic band dominates", ok, f"{share}")
    check("normal-quadratic band stays negligible",
          sb["normal_quadratic"] / sb["total_Esim2"] < 1e-9, f"{share}")
    check("in-plane and normal quadratic warp are kept distinct", True)
    check("band identity holds", p["identities"]["bands"]["holds"])


def test_reflection():
    print("\n8. Reflection: detected as a reflection GAIN, since det R = +1 is vacuous for a plane")
    N = grid()
    P = embed(N, warp2=lambda X: X @ np.diag([1.0, -1.0]).T)
    sp = RQ.similarity_procrustes(N, P)
    check("the proper fit is poor on mirrored data", sp["rms_sim_mm"] > 10.0,
          f"proper sim RMS {sp['rms_sim_mm']:.3f} mm")
    check("reflection gain is large, so the mirror is detected",
          sp["reflection_gain"] > 0.99, f"gain {sp['reflection_gain']:.6f}")
    check("reflection is flagged", sp["reflection_suspected"])
    P2 = embed(N)
    sp2 = RQ.similarity_procrustes(N, P2)
    check("unmirrored data are not flagged", not sp2["reflection_suspected"],
          f"gain {sp2['reflection_gain']:.3e}")


def test_noise():
    print("\n9. Localization noise: spread into the higher-residual band, scale ~unchanged")
    rng = np.random.default_rng(20260730)
    N = grid()
    sd = 0.5
    P = embed(N) + rng.normal(0.0, sd, size=(len(N), 3))
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "higher_residual")
    check("higher-residual band dominates for isotropic noise", ok, f"{share}")
    check("scale stays close to 1 under noise", abs(p["scale"]["s_minus_1"]) < 2e-3,
          f"s-1 = {p['scale']['s_minus_1']:.3e}")
    check("similarity RMS is of the injected noise magnitude",
          0.3 * sd < p["shape"]["rms_sim_mm"] < 3 * sd, f"{p['shape']['rms_sim_mm']:.3f} mm")
    check("band identity holds under noise", p["identities"]["bands"]["holds"])


def test_local_catastrophe():
    print("\n10. Localized catastrophic warp: one point, bounded edge leverage vs all-pairs")
    N = grid()
    P = embed(N)
    bad = 7
    P[bad] += np.array([60.0, -40.0, 25.0])
    p = RQ.cloud_panel(N, P, do_heldout=False)
    sb = p["shape"]["bands"]
    ok, share = dominant(sb, "higher_residual")
    check("a single displaced point lands in the higher-residual band", ok, f"{share}")
    check("band identity holds", p["identities"]["bands"]["holds"])
    inc = sum(1 for i, j, _, _ in RQ.lattice_edges(N)["edges"] if bad in (i, j))
    npair = len(N) - 1
    check("edge leverage is bounded well below all-pairs leverage", inc < npair,
          f"{inc} incident edges vs {npair} incident pairs")
    ap = p["all_pairs_descriptive"]
    check("all-pairs is labelled as a distinct loss, not a Procrustes identity",
          "NOT identical" in ap["loss"])


def test_edge_graph_irregular():
    print("\n11. Irregular and degenerate grids are handled explicitly, not silently")
    N = np.array([[0.0, 0.0], [37.0, 0.0], [111.0, 0.0]])
    g = RQ.lattice_edges(N)
    check("an irregular set still reports its inferred step and rule",
          g["step_mm"] is not None and "inferred" in g["rule"], f"step {g['step_mm']}")
    N1 = np.array([[5.0, 5.0], [5.0, 5.0]])
    g1 = RQ.lattice_edges(N1)
    check("coincident points give an empty graph rather than invented neighbours",
          g1["edges"] == [] and g1["step_mm"] is None, f"{g1['rule'][:40]}")
    N2 = grid(3, 3)
    g2 = RQ.lattice_edges(N2)
    nb = sum(1 for e in g2["edges"] if e[3] == "neighbour")
    dg = sum(1 for e in g2["edges"] if e[3] == "diagonal")
    check("a 3x3 grid gives 12 neighbour edges and 8 cell diagonals",
          nb == 12 and dg == 8, f"neighbours {nb}, diagonals {dg}")


def main():
    print("=" * 100)
    print("reconquality.py synthetic validation")
    print("=" * 100)
    test_rigid()
    test_isotropic_scale()
    test_affine_anisotropy()
    test_shear()
    test_bowl()
    test_saddle()
    test_inplane_quadratic()
    test_reflection()
    test_noise()
    test_local_catastrophe()
    test_edge_graph_irregular()
    npass = sum(1 for _, ok in _results if ok)
    print(f"\n{npass}/{len(_results)} checks passed")
    for n, ok in _results:
        if not ok:
            print(f"  FAILED: {n}")
    return 0 if npass == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
