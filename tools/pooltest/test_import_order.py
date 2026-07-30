#!/usr/bin/env python3
"""Import order must not change any eta-aware result.

THE DEFECT THIS COVERS. Four scripts monkeypatched `parity.undistort = nodes.undistort13` at import
time, and almost every script loaded its modules through a private

    def L(n): spec_from_file_location(...); exec_module(...)

which bypasses `sys.modules` and therefore built a SEPARATE `parity` module per call. Whether a given
script's sightlines were eta-aware depended on whether it happened to reach `parity` through a module
instance that some other script had patched. That made import order a scientific variable: the same
code could silently drop eta from every measurement sightline depending only on who imported first.

This test runs the authoritative path under several import orders in FRESH SUBPROCESSES and requires
bit-identical eta-aware output from all of them.

Run with ~/.venvs/vidsync/bin/python.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DM = "/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects"
FISHEYE = os.path.join(DM, "2015-09-04-1 Clearwater.vsd")

PASS, FAIL = [], []

# Each variant imports the SAME authoritative work last, but reaches it after importing different
# things first -- including the historical monkeypatching module, which is the worst case.
PROBE = r'''
import json, os, sys
sys.path.append({here!r})
{preamble}
import downstream as DS
import numpy as np
cals = DS.load_bound_cals({vsd!r})
clip = sorted(cals)[0]
th = np.concatenate([cals[clip]["dist"], [0.037]])
m = DS.DistortionMap.for_camera(th, cals[clip], name="eta probe")
cam = DS.build_calibration(cals[clip], m)
sl = DS.sightline(731.0, 517.0, cam)
u = m.forward(np.array([[731.0, 517.0], [1500.0, 900.0]]))
import parity as _pa
shared_hook = _pa.historical_eta_map_state()["installed"]
private_hook = None
if "fisheye_knownlength_analysis" in sys.modules:
    private_hook = sys.modules["fisheye_knownlength_analysis"].pa.historical_eta_map_state()["installed"]
print("RESULT" + json.dumps({{
    "eta": m.eta,
    "undistorted": u.tolist(),
    "cam": [float(v) for v in cam["cam"]],
    "sightline": [[float(v) for v in p] for p in sl],
    "s2f": [[float(v) for v in row] for row in cam["s2f"]],
    "shared_parity_hook_installed": shared_hook,
    "historical_private_hook_installed": private_hook,
}}, sort_keys=True))
'''

VARIANTS = {
    "downstream only": "",
    "parity first": "import parity",
    "nodes, lattice, objectives first": "import nodes\nimport lattice\nimport objectives",
    "stage2 first": "import stage2",
    "HISTORICAL monkeypatcher first":
        "import fisheye_knownlength_analysis   # installs the historical eta hook into parity",
    "reverse: downstream then historical":
        "import downstream\nimport fisheye_knownlength_analysis",
}


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    return bool(cond)


def run(preamble):
    src = PROBE.format(here=HERE, vsd=FISHEYE, preamble=preamble)
    r = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, cwd=HERE)
    if r.returncode != 0:
        return None, r.stderr[-800:]
    for ln in r.stdout.splitlines():
        if ln.startswith("RESULT"):
            return json.loads(ln[6:]), None
    return None, "no RESULT line\n" + r.stdout[-500:]


def main():
    print("=" * 100)
    print("IMPORT-ORDER INVARIANCE OF ETA-AWARE RESULTS")
    print("=" * 100)
    print(f"\n  probing the authoritative path (downstream.py) under {len(VARIANTS)} import orders,")
    print(f"  each in a fresh subprocess\n")

    results = {}
    for name, pre in VARIANTS.items():
        out, err = run(pre)
        if out is None:
            check(f"variant ran: {name}", False, err)
            continue
        results[name] = out
        check(f"variant ran: {name}", True,
              f"shared parity hook = {out['shared_parity_hook_installed']}, "
              f"historical private hook = {out['historical_private_hook_installed']}")

    if len(results) < 2:
        print("\n  not enough variants ran to compare")
        return 1

    ref_name = "downstream only"
    ref = results.get(ref_name) or next(iter(results.values()))
    print(f"\n  comparing every variant against {ref_name!r}, requiring BIT-IDENTICAL values")
    for name, out in results.items():
        for key in ("eta", "undistorted", "cam", "sightline", "s2f"):
            same = out[key] == ref[key]
            check(f"{key} identical under {name!r}", same,
                  "" if same else f"DIFFERS: {out[key]} vs {ref[key]}")

    # The eta must actually be doing something, or "identical" would be vacuous.
    check("eta is nonzero in the probe, so the comparison is meaningful", ref["eta"] == 0.037)
    # The strong isolation result: importing the historical monkeypatching module NEVER leaves the
    # shared `parity` instance modified, so no later script can inherit an eta-aware `parity` by
    # accident -- which is precisely how import order became a scientific variable before.
    check("importing the historical module never contaminates the shared parity instance",
          all(r["shared_parity_hook_installed"] is False for r in results.values()),
          f"{ {n: r['shared_parity_hook_installed'] for n, r in results.items()} }")
    hist_variants = {n: r for n, r in results.items()
                     if r["historical_private_hook_installed"] is not None}
    check("the historical module DOES still install the hook in its own private parity instance, "
          "so its frozen analysis still reproduces",
          bool(hist_variants)
          and all(r["historical_private_hook_installed"] is True
                  for r in hist_variants.values()),
          f"{ {n: r['historical_private_hook_installed'] for n, r in hist_variants.items()} }")
    check("that private hook is installed in some variants and absent in others, "
          "yet no authoritative value moved",
          len({r["historical_private_hook_installed"] for r in results.values()}) > 1,
          f"{ {n: r['historical_private_hook_installed'] for n, r in results.items()} }")

    print("\n" + "=" * 100)
    print(f"  {len(PASS)} passed, {len(FAIL)} FAILED")
    for f in FAIL:
        print(f"    FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
