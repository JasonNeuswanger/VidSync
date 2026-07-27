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

## The one rule

Judge a change on the 1010 measurements, never on the calibration residual. The calibration
points are the training set and the measurements are the test set, and the gap between them is
not academic: estimating the frame's node positions improved the calibration residual four-fold
while making every measurement slightly worse. Results are recorded in
`CALIBRATION_REFERENCE_NOTES.md`.
