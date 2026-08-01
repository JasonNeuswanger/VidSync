# 10 mm point-cloud round — recorded conclusions and reporting rules, 2026-07-30

Authoritative record of what the 10 mm Chena point-cloud ground truth does and does not establish, plus
the wording and definitional rules any consolidated report must inherit. Written after review; the
seven corrections in the "Reporting rules" section are binding, not stylistic.

Inputs, artefacts, commands and the harness fix are recorded in
`analysis-output/cloud_downstream_full.{json,log}`. Evaluator: `cloud_downstream.py`. Loader fix and its
tests: `knownlength.py`, `test_cloud_identity.py`.

## The 10 mm conclusion, stated conservatively

**Classification: weakly supportive, but within the present production indifference region. NOT a
validated M1-acceptance case.**

1. M1 passes every optimization and physical-map gate on both cameras: finite parameters, production
   radial-scale and core-determinant gate, |eta| within bound, strictly positive eta-aware Jacobian
   determinant over the working domain, Newton inverse round trip below 1e-9 px, and improvement of its
   own objective's M0 loss under the M0-first warm start with eta = 0. Nothing was gate-rejected.
2. Both estimators give a favourable downstream direction on the cloud ground truth.
3. Under PD-D, the primary estimator, the improvement is small: mean per-cloud MAE change −0.128 mm on a
   4.688 mm base, i.e. 2.7 %, falling to −0.060 mm when the severely extrapolated Cloud C is excluded.
   Three of four clouds improve, two of three after excluding Cloud C.
4. B's improvement is larger (−0.411 mm, −0.495 mm excluding Cloud C) and is **corroborating evidence
   only**. It does not supersede the smaller effect under PD-D, which is the estimator production would
   use.
5. Therefore 10 mm is recorded as weakly supportive and inside the indifference region. It is
   qualitatively unlike the adverse 13 mm and Sony cases, whose PD-D contrasts run the wrong way, and it
   is much weaker than the 8 mm case. That is the whole of the claim.

Do not derive the camera-agnostic acceptance threshold from this. Wait for the newly digitized 17 mm
document and analyse it through this same evaluator, pairing scheme and cloud-balanced framework.

## Reporting rules (binding corrections)

1. **Digitization wording.** Write "no digitization errors detected under the specified diagnostics",
   never "no digitization errors". Reprojection consistency, swap tests and duplicate-click checks cannot
   exclude a physical-feature or annotation-label mistake that is reproduced consistently in both
   cameras: two consistent clicks on the wrong corner triangulate cleanly.
2. **Extrapolation is strongly implicated, not proven uniquely causal.** The Cloud C versus Cloud D
   comparison — same physical 1000x500 mm grid, 22 shared note coordinates, 377 mm versus 133 mm outside
   the calibrated node box, 2.0 % versus 0.16 % scale inflation, 10.57 mm versus 1.27 mm MAE — is strong
   evidence. It does not exclude every position-dependent reconstruction effect, and it does not exclude
   a global error in the physical target's own dimensions, which would rescale all placements together.
3. **Fitted |eta| is not equivalent to objective improvement.** They are distinct quantities. Neither is
   validated as a universal selection statistic. Do not present one as a proxy for the other, and do not
   present either as an established predictor.
4. **The 8 mm-to-10 mm ratio agreement is descriptive only.** Geometric improvement ratio ≈ 0.66
   (−0.481 px against −0.734 px) and PD-D downstream ratio ≈ 0.63 (−0.128 mm against −0.204 mm) happen to
   agree. With two configurations, and with the two downstream numbers coming from different measurement
   families (cloud pairs at 10 mm, conventional two-point measurements at 8 mm), that agreement is not
   evidence of a calibrated predictive relationship.
5. **Aggregation formulas must be stated.** For C groups: `meanMAE = (1/C) sum_c MAE_c`;
   `meanBias`, `meanMed`, `meanP90` likewise arithmetic means of per-group values;
   `meanRMSE = (1/C) sum_c RMSE_c` is an arithmetic mean of per-group RMSE, whereas
   `balRMSE = sqrt((1/C) sum_c MSE_c)` is the group-balanced root mean square — different quantities,
   both reported. Any arithmetic mean of per-group maxima is named **mean per-cloud maximum**, never a
   maximum, and the **worst observed pair error** is reported separately. The evaluator prints these
   formulas above every aggregate table and names every JSON key for the formula that produced it.
6. **Completeness scope.** The scan covered all 20 documents registered in `corpus.py`. It does not
   establish anything about `.vsd` files outside that corpus; those were not searched.
7. **Git condition.** No index operation was performed intentionally. `cloud_downstream.py` and
   `test_cloud_identity.py` are nonetheless staged, by the environment. `knownlength.py` is
   unstaged-modified. Do not stage, unstage, restore or otherwise normalize that state.

## Numbers of record, 10 mm Chena (`e402b370…`, 4 clouds, 93 points, 1070 pairs)

Per-cloud MAE in mm for Clouds A, B, C, D:
stored 2.2522 / 6.0520 / 10.3742 / 2.0642; B/M0 1.9253 / 6.5418 / 10.8532 / 1.4127;
B/M1 1.9913 / 5.1050 / 10.6930 / 1.2996; PD-D/M0 2.0403 / 4.8721 / 10.5688 / 1.2715;
PD-D/M1 2.1420 / 4.6133 / 10.2352 / 1.2488.

Mean per-cloud MAE: stored 5.1857, B/M0 5.1833, B/M1 4.7722, PD-D/M0 4.6882, PD-D/M1 4.5598.
Excluding Cloud C: B/M0 3.2933, B/M1 2.7986, PD-D/M0 2.7280, PD-D/M1 2.6680.

Paired on identical pairs, mean per-cloud mean d|err| in mm:
B/M1 − B/M0 = −0.4110 (per cloud +0.0659, −1.4368, −0.1602, −0.1131; 3/4 clouds);
PD-D/M1 − PD-D/M0 = −0.1283 (+0.1017, −0.2587, −0.3336, −0.0227; 3/4);
PD-D/M0 − B/M0 = −0.4951 (3/4); PD-D/M1 − B/M1 = −0.2124 (3/4).
Excluding Cloud C: B −0.4947 (2/3), PD-D −0.0599 (2/3).

Fitted eta, PD-D/M1: Left +0.004768, Right +0.004508. B/M1: +0.004582, +0.005000. Bound is ±0.05.

## 8 mm supplemental cloud evidence and the flagged points

**Correction to an earlier count: there are eight points at or above 6 px reprojection residual, not
six.** The earlier report omitted event 701 (6.231 px) and event 655 (6.081 px). The residual tail is
smooth from 9.312 px down through 5.341 px with no natural gap, so any single cut is arbitrary; the
predetermined sensitivity therefore runs both 6.0 px (8 points) and 5.0 px (11 points).

Flagged points, 8 mm document, by residual: Cloud A event 658 (pk 1017) 9.312 px; Cloud A event 662
(pk 1016) 8.244; Cloud D event 709 (pk 1061) 7.596; Cloud A event 665 (pk 1011) 7.586; Cloud A event 650
(pk 1007) 6.516; Cloud A event 661 (pk 1022) 6.482; Cloud D event 701 (pk 1066) 6.231; Cloud A event 655
(pk 1020) 6.081; then Cloud A event 660 (pk 1021) 5.956, Cloud A event 646 (pk 1006) 5.463, Cloud A
event 659 (pk 1013) 5.341. Median across all 65 points is 1.158 px. Chena has zero points above 6 px
(median 1.424, max 3.166), so this is specific to the 8 mm document.

Nine of the eleven are in Cloud A, the closest placement at 304 mm mean camera distance, and the overlays
(`cloud_downstream_8mm_overlay_{Left,Right}.png`) show them concentrated at the right frame edge around
x = 1680–1920 px and in the lower left. Near-field, extreme-field-angle points on an 8 mm fisheye are
also where residual distortion-model error is largest, so a high residual there is not by itself a
mis-click. They warrant a later click review; **do not edit them.**

Predetermined sensitivity, mean per-cloud mean d|err| in mm, no refitting (cloud points are ground truth,
not calibration inputs, so the maps are identical with and without them):

- Excluding all 8 points at >= 6 px: PD-D/M1 − PD-D/M0 goes −0.2472 to −0.1960, clouds improved 3/4;
  B/M1 − B/M0 goes −1.3838 to −1.0340, clouds improved 4/4.
- Excluding all 11 points at >= 5 px: PD-D −0.2472 to −0.1823, clouds 3/4; B −1.3838 to −0.8552, 3/4.
- Excluded individually, the PD-D contrast ranges only −0.2271 to −0.2521 across all eleven, so no single
  point moves it by more than about 0.02 mm; the B contrast ranges −1.2040 to −1.4258.

So the 8 mm supplemental cloud evidence for M1 is robust to these points individually and together at
both cuts, and the independent 42-measurement conventional result (B 5.0049 to 4.1865, PD-D 4.1128 to
3.9050 mm MAE) is untouched by them. The click review must not delay the 17 mm analysis.
