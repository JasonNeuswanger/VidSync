# Pool test analysis scripts

Offline experiments against the 2012 pool test, whose interpretation is documented in
`CALIBRATION_REFERENCE_NOTES.md` at the repository root. Plain Python 3, no dependencies —
deliberately, so they run anywhere without a virtual environment.

They work from the 2016 XML export rather than from a `.vsd` document, because the export
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

`homog.py` reproduces VidSync's exported front homography to 3e-6 relative, which is the check
that makes the rest trustworthy. It does *not* reproduce the back homography, and should not:
VidSync fits the back plane to refraction-corrected apparent node positions, and these scripts
use the nominal ones. That difference is why absolute error levels here sit slightly above the
document's own, and why these scripts are for A/B comparisons rather than for reproducing
VidSync's exact output.

## The one rule

Judge a change on the 1010 measurements, never on the calibration residual. The calibration
points are the training set and the measurements are the test set, and the gap between them is
not academic: estimating the frame's node positions improved the calibration residual four-fold
while making every measurement slightly worse. Results are recorded in
`CALIBRATION_REFERENCE_NOTES.md`.
