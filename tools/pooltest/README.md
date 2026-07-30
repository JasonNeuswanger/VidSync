# Pool test analysis scripts

Offline experiments against the 2012 pool test, whose interpretation is documented in
`CALIBRATION_REFERENCE_NOTES.md` at the repository root. Plain Python 3, no dependencies —
deliberately, so they run anywhere without a virtual environment.

`fitter.py` needs numpy and scipy, which are not installed system-wide. Create the environment once:

```
/usr/local/bin/python3 -m venv ~/.venvs/vidsync
~/.venvs/vidsync/bin/python -m pip install numpy scipy
```

and run it with `~/.venvs/vidsync/bin/python`. Everything else is plain Python 3.

Most of them work from the 2016 XML export rather than from a `.vsd` document, because the export
carries the raw and undistorted screen coordinates for every click, the projections onto both
calibration frame planes, and both cameras' full calibrations. That makes it possible to refit
the calibration and re-triangulate all 1010 measurements from scratch, which is what turns the
pool test from a fixed set of numbers into an experiment.

The path to the export is hard-coded at the top of `homog.py`.

| script | what it does |
|---|---|
| `homog.py` | Normalized DLT, and a check that it reproduces the homographies VidSync exported |
| `refine.py` | Geometric refinement of a homography, and closest-point-of-approach triangulation |
| `framefit.py` | Estimates the frame's true node positions from cross-camera agreement |
| `evaluate.py` | Re-triangulates all 1010 measurements under two calibrations and compares errors |
| `planescan.py` | Sweeps the assumed front-to-back plane separation |
| `harvest.py` | Dumps every plumbline calibration in the Drift Model folder as TSV |
| `rangetest.py` | Tests whether fitted distortion depends on the board's distance |
| `curvature.py` | Model-free test of distance dependence, from imaged line curvature |
| `twodistance2.py` | Cross-evaluates VidSync's near-set, far-set and combined fits |
| `distcal.py` | Rebuilds the whole calibration under a given distortion model and re-measures known lengths |
| `loadbearing.py` | Identifiability spectrum: which parameters the data actually determines |
| `fitter.py` | Plumbline fitter with a configurable parameter subset, scored on held-out lines |
| `expressiveness.py` | Score test for richer models. **Known bug, do not quote its numbers** |
| `knownlength.py` | **THE** loader for known-length and point-cloud annotations. Run it on a document for a validation/exclusion report |
| `test_knownlength.py` | 90 parser and validation checks for `knownlength.py`, synthetic stores plus the real fisheye document |
| `nodes.py` | **THE** calibration-node accessor. `ZCALIBRATION1` is FRONT, `ZCALIBRATION` is BACK |
| `oracle.cpp` / `stage2.py` | Production-faithful refractive calibration rebuild, via the same Accelerate LAPACK and GSL routines production calls |
| `parity.py` | Parity-validated port of `VSPoint.m` triangulation; reproduces stored 3D coordinates |
| `fisheye_knownlength_analysis.py` | Four-model known-length **and** point-cloud-shape analysis of the 8 mm fisheye, with node jackknife. Writes `analysis-output/` |
| `fisheye_eta_vs_radial_control.py` | Control for the above: is the ninth parameter's benefit eta specifically, or any ninth parameter? |
| `plumb_oracle.cpp` | **THE** production-equivalent plumbline objective, gate and Nelder-Mead solver, transcribed verbatim from `VSCalibration.mm`. Must be linked against the app's own bundled `gsl-2.6-universal/libgsl.a`, not the system GSL 2.7 |
| `parity_step1.py` | Solver-parity audit 1: freeze the document, read the in-app 13 parameters (`APP13`), report the plumbline observations each solve saw |
| `parity_step2.py` | Solver-parity audit 2: map and objective parity at `APP13`, with no optimization |
| `parity_step3.py` | Solver-parity audit 3: application replay, restart at `APP13`, controlled multistart, replay sensitivity |
| `parity_step4.py` | Solver-parity audit 4: does the Left clip's two-capture composition explain anything? (Right clip is the single-capture control) |
| `parity_step5.py` | Solver-parity audit 5: production-faithful downstream comparison of `APP13`, `POLISH13`, `M0`, `M1`, `APP13+eta`, `POLISH13+eta` |
| `parity_step6.py` | Solver-parity audit 6: is `APP13` -> `POLISH13` incomplete convergence, a separate basin, or a weak direction? |
| `stab_fits.py` | Model-stability 1: the controlled seed battery for M0, M1, FULL13 and F13eta, both solvers, with exact nesting checks |
| `stab_gauge.py` | Model-stability 2: projective-gauge decomposition of map differences, plus Jacobian conditioning per model |
| `stab_metrics.py` | Model-stability 3: production-faithful measurement spread across solver endpoints |
| `stab_degeneracy.py` | Model-stability 4: **THE** admissibility rule, and the demonstration that the shipped gate accepts collapsed eta maps |
| `stab_etaprofile.py` | Model-stability 5: eta profile with all nuisance parameters reoptimized |
| `lattice.py` | **THE** unique-observation, lattice-index and quadrature-weight foundation, plus the eta-aware map with analytic Jacobian and Newton inverse. Run it for the observation audit on a document |
| `objectives.py` | The four objectives on one interface: B (production), SD (unique-point block Sampson), ED (exact raw-space line EIV), PD (exact projective lattice) |
| `obj_synth.py` | Synthetic validation of all four objectives; run before trusting any real fit |
| `obj_round1.py` | First real round: M0 and M1 under all four objectives on both Clearwater clips, with cross-objective and zero-weight diagnostics |

`homog.py` reproduces VidSync's exported front homography to 3e-6 relative, which is the check
that makes the rest trustworthy. It does *not* reproduce the back homography, and should not:
VidSync fits the back plane to refraction-corrected apparent node positions, and these scripts
use the nominal ones. That difference is why absolute error levels here sit slightly above the
document's own, and why these scripts are for A/B comparisons rather than for reproducing
VidSync's exact output.

## Two rules

Fit with the acceptance gate enforced. A thorough optimizer beats VidSync's own solver on residual
(0.8208 px against 0.9173 on the reference set) by finding solutions that fail the gate on scale
ratio: the extra reduction comes from quietly shrinking the undistorted image, not from describing
the lens. `fitter.py` appends penalty residuals to keep the search feasible, and it is not optional.

## The third rule, added by the 2026-07-28 solver-parity audit

Never compare a candidate model against "whatever the document currently contains". The in-app
13-parameter Nelder-Mead solve is chaotic on the Left camera of the fisheye document: a relative
1e-12 nudge to its starting centre moves the fitted map by 5.5 px, and re-running it moved the
known-length MAE by 0.70 mm — comparable to every model effect this project has measured. Name the
in-app solution `APP13` and treat it as one draw, not as a baseline. See
`CALIBRATION_REFERENCE_NOTES.md`.

## The fourth rule, added by the 2026-07-28 model-stability round

eta is not bounded by anything. `reasonToRejectSolvedDistortion:` inspects the thirteen
Brown-Conrady parameters only, so it accepts an M1 solution at eta = -1.98 whose plumbline residual
(0.4636 px) is *better* than the physical optimum's (1.1317 px). Any fit with eta free must be
filtered through `stab_degeneracy.on_physical_branch()`, and eta must not ship until the gate's
minimum-determinant test is evaluated on the eta-aware map, which does separate the branches.

## The fifth rule, added by the 2026-07-28 new-objective round

Lattice indices are only comparable WITHIN a connected component of the adjacency graph, because each
component's breadth-first search starts at its own (0, 0). Group diagonal holdouts by component, and
give the projective-lattice objective one component per capture. Pooling across components produced a
meaningless 260 px holdout residual for every candidate map.

## The one rule

Judge a change on the 1010 measurements, never on the calibration residual. The calibration
points are the training set and the measurements are the test set, and the gap between them is
not academic: estimating the frame's node positions improved the calibration residual four-fold
while making every measurement slightly worse. Results are recorded in
`CALIBRATION_REFERENCE_NOTES.md`.
