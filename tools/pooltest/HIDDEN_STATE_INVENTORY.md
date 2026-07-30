# Hidden-state and import-order inventory

Compiled 2026-07-29 for the independent-audit remediation. Covers every `.py` file in
`tools/pooltest`. The question being answered: **where could hidden global state or import order decide
a scientific result?**

## The two mechanisms

**Monkeypatching `undistort`.** `parity.undistort` was a 13-parameter function whose name suggested it
was the module's generic distortion map. It was not — it ignores `theta[13]`, the conjugated anisotropy
eta. Four scripts compensated by assigning `parity.undistort = nodes.undistort13` at import time. Any
code reaching `parity.sightline` through an unpatched instance silently dropped eta from every
measurement sightline while the calibration rebuild still used it.

**Duplicate module instances.** Almost every script carries a private

    def L(n):
        s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

`spec_from_file_location` + `exec_module` bypasses `sys.modules`, so **every call builds a new module
object**. Two scripts that both `L("parity")` hold two unrelated `parity` modules. A patch applied to one
is invisible in the other. This is what made eta propagation depend on who imported what first.

## Findings, with the hazard for each

| file | line | code | hazard |
|---|---|---|---|
| `fisheye_knownlength_analysis.py` | 84 | `pa.undistort = nd.undistort13` | import-time patch; anything importing this module inherited it |
| `fisheye_pd_downstream.py` | 45 | `FK = L("fisheye_knownlength_analysis")` | imported *for* that side effect; asserted it at line 135 rather than owning it |
| `round10.py` | 41 | `pa.undistort = nd.undistort13` | import-time patch |
| `calab.py` | 21 | `pa.undistort = nd.undistort13` | import-time patch |
| `knownlen.py` | 106 | `dc.undistort = undistort_eta` | patches **distcal**, not parity; affects `distcal.build/sightline/refine` |
| `fisheye_knownlength_analysis.py` | 638-643 | swaps `pa.undistort` in and out | deliberate eta = 0 nesting check, but via attribute assignment |
| `parity_step5.py` | 58 | `FK = L("fisheye_knownlength_analysis")` | **an authoritative chain pulling a historical module in at import time**: `lattice.py` → `parity_step5.py` → `fisheye_knownlength_analysis.py`, so every authoritative run triggered a historical side effect it never used |

Searched and **not** found: no module-level "current model" or `_CURRENT`-style mutable state; no
`global` statement mutating shared numerics; no theta truncation that loses eta — every `[:13]` is either
paired with an explicit `eta=` argument (`stage2.run_oracle`, `downstream.build_calibration`) or is
deliberately feeding a documented 13-parameter function.

## Classification

**(A) Authoritative / reusable modules** — imported by others for shared functionality.

`nodes.py`, `fitter.py`, `lattice.py`, `objectives.py`, `stage2.py`, `distcal.py`, `parity.py`,
`knownlength.py`, `jacweight.py`, `downstream.py`, and new this round: `harness_import.py`,
`artifacts.py`, `fitvalidity.py`.

**(B) Current entry points** — run today to produce headline results.

`xdoc_objectives.py` (cross-document candidate tables), `downstream_parity.py` (injection, binding and
solver-parity gate), `obj_pd_closure.py` and `obj_pd_fast.py` (PD objective fits and benchmark),
`nodes.py --main` (node-orientation invariant), and the four test scripts.

**(C) Frozen historical round scripts** — reproduce a published analysis; not to be imported for reusable
functionality.

`round3.py`, `round3b.py`, `round5.py`, `round5b.py`, `round6.py`, `round6b.py`, `round7.py`,
`round8.py`, `round8b.py`, `round9a.py`, `round9a2.py`, `round9b.py`, `round10.py`,
`parity_step1.py`–`parity_step6.py`, `knownlen.py`, `knownlen2.py`, `knownlen3.py`, `knownlen4.py`,
`calab.py`, `stab_degeneracy.py`, `stab_etaprofile.py`, `stab_fits.py`, `stab_gauge.py`,
`stab_metrics.py`, `obj_round1.py`, `obj_synth.py`, `closure.py`, `conjugate.py`, `anisotropy.py`,
`elliptest.py`, `ellip_one.py`, `normfit.py`, `lattice.py --main`, `modeltest.py`, `suite4.py`,
`stage234.py`, `fisheye_eta_vs_radial_control.py`, and now
**`fisheye_knownlength_analysis.py`** and **`fisheye_pd_downstream.py`**, both reclassified from (B).

## Repairs

### Authoritative paths

- **`parity.py`**: `undistort` renamed **`undistort13`**, with a docstring stating that it ignores eta and
  is not a generic candidate-aware map. The old name no longer exists, so a stale monkeypatch cannot
  silently no-op. `sightline` and `triangulate` call `_undistort_active`, which is `undistort13` unless a
  historical script explicitly installs otherwise.
- **`harness_import.py`** (new): `load(name)` uses the ordinary import machinery, so `sys.modules`
  guarantees exactly one instance per module process-wide. The directory is *appended* to `sys.path` so
  it cannot shadow the standard library. Adopted by `downstream.py`, `xdoc_objectives.py` and
  `downstream_parity.py`.
- **`downstream.py`**: no monkeypatch, no module-level mutable state, and maps are now bound to their
  camera via `CameraIdentity` and re-verified in `build_calibration`.
- **`xdoc_objectives.py`**: loads calibrations with `DS.load_bound_cals` and constructs every map with
  `DistortionMap.for_camera` / `from13_for_camera`, so M1 reaches every downstream stage through an
  explicitly bound object.
- **`parity_step5.py`**: `FK` is now loaded **lazily** inside `main()`. This severs
  `lattice → parity_step5 → fisheye_knownlength_analysis`, so authoritative runs no longer trigger a
  historical import side effect. `lattice` needs only `SCALE14`, `ETA_SCALE` and `undistort14`.

### Historical scripts — marked, not rewritten

`round10.py`, `calab.py` and `fisheye_knownlength_analysis.py` still need eta-aware behaviour from
`parity.sightline`/`triangulate` to reproduce what they published. Their attribute assignment is replaced
by

    parity.install_historical_eta_map(nodes.undistort13, reason="...")

which requires a written reason of at least 20 characters, prints a notice to stderr when it fires, and
is queryable via `parity.historical_eta_map_state()`. The state is still process-wide within that
module instance — but it is now named, explicit, default-off, and impossible to trigger accidentally.
`fisheye_knownlength_analysis.py` and `fisheye_pd_downstream.py` carry a HISTORICAL / NON-AUTHORITATIVE
banner at the top naming what supersedes them and telling readers not to import them.

`knownlen.py`'s `dc.undistort` patch (of `distcal`, not `parity`) is untouched: it is a frozen historical
script, `distcal` is not on any authoritative path, and rewriting it would change what it reproduces.

## Verification

`test_import_order.py` runs the authoritative path in six fresh subprocesses under different import
orders — including importing the historical monkeypatching module first, and importing it *after*
`downstream` — and requires bit-identical eta, undistorted coordinates, camera position, front
homography and sightline from all of them. It additionally asserts:

- importing the historical module **never** leaves the shared `parity` instance modified, so no later
  script can inherit an eta-aware `parity` by accident; and
- the historical module *does* still install the hook in its own private `parity` instance, so its frozen
  analysis still reproduces.

All 40 checks pass.
