# Backward-compatible calibration when no valid projective lattice exists

**STATUS: UNIMPLEMENTED DESIGN PROPOSAL.** No production code, schema, or UI has been changed. Nothing
here is a verified numerical finding; the measured results live in `CALIBRATION_REFERENCE_NOTES.md`.
Field names are deliberately left abstract because the serialization decisions below depend on schema
review that has not happened yet.

## 1. What the code actually does today

Established by reading the current source, not assumed.

The detector already computes the lattice. `VSChessboardDetector.hpp:129-139` builds a `GrownLattice`
carrying `std::vector<cv::Point2i> ij`, the integer grid coordinate of every corner, and
`:176-180` defines `Plumbline` with `isRow` (constant *j* versus constant *i*) and `index` (the
constant lattice coordinate). `extractPlumblines` emits one plumbline per lattice row and column, and
its comment records that holes are not breaks.

**That structure is then discarded at the storage boundary.** `VSCalibration.mm:1944-1952` passes only
`std::vector<cv::Point2f>*` into `addNewAutodetectedLineWithPoints`, so `isRow` and `index` are not
even handed across the call. `CalibDistortionLineArrayController.mm:63-71` writes `screenX`, `screenY`
and a sequential within-line `index`. `VSDistortionPoint` (`VSDistortionPoint.h:29-40`) has no lattice
coordinate, no family flag, and no persistent identity; `VSDistortionLine`
(`VSDistortionLine.h:29-42`) has `lambda`, `timecode`, `calibration` and its point set.

Consequences that shape the whole design:

- A corner where two lines cross is **two independent records**, not one shared entity. There is no
  uniquing logic anywhere. The offline harness recovers identity by exact coordinate equality, which
  works only because both records are written from the same `cv::Point2f` and stored as **float32**
  (`numberWithFloat:`, `CalibDistortionLineArrayController.mm:66-67`), making the duplicate values
  bit-identical. That is a fortunate accident of the writer, not a guarantee.
- A "capture" has **no entity**. Timecode string equality is the only grouping key.
- There is **one hardcoded objective**: `orthogonalRegressionTotalCostFunction`
  (`VSCalibration.mm:76-126`), driven from `calculateDistortionCorrection` (`:2308-2491`) through GSL
  `nmsimplex2`. There is a detection-method dispatch in `autodetectChessboardPlumblines` (`:1793`),
  but both branches feed the same objective. There is no objective-selection flag to extend.
- Persisted quality fields exist — `distortionReductionAchieved`, `distortionRemainingPerPoint`,
  `distortionHoldOutResidual`, and the six front/back residuals — but there is **no method, version,
  or timestamp** field anywhere.
- Existing modal precedent is well established: `UtilityFunctions InformUser:withTitle:`
  (`VSCalibration.mm:2337`), the critical `NSAlert` "Distortion correction rejected" (`:2447-2452`),
  and "accepted, with a caveat" (`:2488-2490`), all downstream of the rejection gate at `:2243-2302`.

The single most important design consequence: **the offline harness's hardest and least reliable step
is reconstructing lattice indices that production already had and threw away.** `lattice.py` rebuilds
them from a within-line adjacency graph with a unit-step tolerance, drops ambiguous edges, and still
reports index contradictions and multiple components. None of that inference is necessary if the
detector's `ij` is persisted at write time.

## 2. The three cases

**A — valid modern lattice.** Exact PD-D, one homography per capture, one shared distortion map per
camera. Missing corners, incomplete rows and irregular raw spacing must not invalidate it; the measured
occupancy on Clearwater is well under half the bounding lattice and PD-D fits it without difficulty.

**B — legitimate non-lattice plumblines.** A user deliberately clicks arbitrary straight physical
lines: a tank edge, a taut wire, a building seam. Fully supported, no warning, no degraded status. This
is a first-class workflow, not a failure.

**C — expected lattice that fails validation.** Chessboard autodetection ran but indexing or topology
validation failed. Conspicuous and repairable.

B and C must never share a user experience. The distinguishing signal must be **provenance, not
geometry**: whether this calibration's lines came from the chessboard autodetector or from manual
clicking. Inferring intent from whether a lattice happens to validate is exactly the conflation to
avoid, and today that provenance is not recorded — which is itself an argument for recording it.

## 3. Assessment of the proposed fallback policy

The policy is sound in outline. Five hidden failure modes:

**(a) `Auto` cannot distinguish B from C without stored provenance.** As written, "explicitly declared
non-lattice" is a user action, so a user who never touches the setting and clicks manual lines lands in
the same `Auto` bucket as a failed chessboard detection, and gets a modal about a lattice they never
wanted. Fix: set the structure mode at *line creation* time. When
`addNewAutodetectedLineWithPoints` runs, the lines are chessboard-derived and a lattice is expected.
When lines are created by manual clicking (`appendPointToSelectedLineAt:` and siblings), they are not.
Mixed sets should be treated as case C and surfaced, not silently resolved.

**(b) Partial-lattice acceptance is unspecified and is the highest-risk decision.** "If a lattice
validates" hides the question of what happens when 90% of corners form one clean component and a
handful form a second. See §5.

**(c) The modal's "continue with the line fallback" option silently changes the estimand, not just the
solver.** PD-D and the line objective weight the data differently and answer subtly different
questions. The modal must say that the result is not comparable to a PD-D calibration rather than
presenting fallback as a neutral retry.

**(d) "Fail closed in headless mode" needs a defined exit contract.** Batch callers need a
distinguishable non-zero status and a machine-readable reason, not just an error, or they will paper
over it with a blanket retry.

**(e) Re-validation on edit is unaddressed.** A stored calibration marked lattice-valid can be
invalidated by later point editing. Validation status must be recomputed and invalidated when the line
or point set changes, otherwise provenance goes stale and lies.

One addition: because `distortionRemainingPerPoint` is not comparable across objectives, any UI or
export that shows a residual must also show which objective produced it. Otherwise users will compare
a PD-D residual against a legacy ODR residual and conclude the calibration got worse.

## 4. Which line objective should be the modern fallback

**Two modes, both explicit.**

*Legacy reproduction mode.* The exact current transformed-coordinate line ODR objective, preserved
bit-for-bit, used when reopening or deliberately reproducing a historical calibration. Versioned and
labelled legacy. It must not be silently reinterpreted: parity work has already established that this
objective, on the stored representation, counts a shared corner once per line it appears in, and that
counting is part of what "legacy" means.

*Modern non-lattice mode: unique-observation block Sampson with frozen raw-coordinate quadrature.* For
observation *i* with one or two valid incidences, minimize
`sum_i a_i F_i^T (G_i G_i^T)^-1 F_i` with `F_i` the applicable signed line offsets and
`G_i` their rows of `n_j^T J_U(x_i)`. This is the right fallback because it fixes the three specific
defects of the legacy objective — per-incidence double counting, approximate rather than exact
geometry, and unweighted quadrature — without requiring lattice structure. The offline exact line-EIV
objective stays as a verification oracle only, given its demonstrated agreement with Sampson in this
residual regime.

Requirements, restated as implementation constraints: one block per unique observation; `a_i` applied
once per observation, never once per incidence; a single incidence degenerating to scalar Sampson
distance; rank-two blocks only for genuinely non-parallel incidences; explicit detection of duplicate
and near-parallel constraints with a reported conditioning floor rather than a pseudoinverse that
hides rank failure; and Delaunay area quadrature used **only** when support validation confirms
genuinely two-dimensional coverage, falling back to uniform weights otherwise.

### What must happen in each awkward case

The dividing line: a solver may accommodate *sparsity and geometry*; it must never accommodate
*incorrect line membership*, because membership errors change which physical line a point is asserted
to lie on, and no reweighting can repair a false assertion.

| Situation | Handling |
|---|---|
| No persistent shared point identity | Cluster by coordinate proximity at a tolerance derived from stored float32 resolution and detector noise, then **report** the merge count. Today exact equality happens to work; a tolerance is needed if the writer ever changes. Merges above a small threshold indicate a real problem and should be surfaced. |
| Two lines cross but detections are not bit-identical | Merge within tolerance; if the gap exceeds detector noise, that is a detection inconsistency — flag for review, do not average silently. |
| Point with more than two incidences | Legitimate only if the constraints are consistent. Build the full-rank block, cap the rank at two, and report. More than two *non-parallel* incidences at one corner usually means duplicate line records. |
| Fragmented line records | Solver-accommodatable and common: the legacy detector splits one physical row into several records. Sampson handles fragments correctly because each block is local. But fragmentation inflates the apparent line count and must be reported, since it also weakens any per-line statistic. |
| A line record joining unrelated segments | **Blocks calibration. Requires user review.** This is a false membership assertion — the measured 1649 px within-line jump on one Right-camera line is the example. No objective can detect that the two halves are different physical lines without an outlier model that would also discard real distortion signal. |
| Nearly one-dimensional support | Refuse Delaunay quadrature and fall back to uniform weights, reporting the support dimensionality. Area quadrature on a degenerate point set produces meaningless weights. |
| Only one line orientation present | Permit fitting but warn prominently: a single orientation cannot constrain the distortion centre transverse to that orientation, so the fit will be weakly identified in a direction the residual will not reveal. |
| Delaunay bridging unsupported gaps | Already handled by the `kappa` × local-lattice-edge filter; retain it, and report retained and rejected triangle counts **for the exact observation set being fitted**. The Round-1 count confusion came precisely from reporting a triangle count for a different observation set than the one fitted. |

## 5. Lattice validator, severity, and partial acceptance

Proposed checks, each with a severity:

*Blocking:* index contradictions after propagation; two different observations assigned the same
lattice index within one capture; a line record whose inferred indices are non-monotonic or jump
(the joined-segments case); fewer than the minimum non-collinear points for a homography; projective
denominator too close to zero at any fitted point.

*Warning, proceed:* inconsistent unit-step adjacency below a threshold fraction; more than one
connected component; index-space or screen-space span below target; coverage of the intended working
region incomplete; ambiguous gaps that had to be dropped; excluded point or component counts above a
threshold.

*Informational:* missing corners, holes, scratches, irregular spacing — explicitly tolerated, and never
by themselves a validation failure.

**On using a large valid component while excluding invalid ones:** permissible, with two guards. The
retained component must cover a stated fraction of both the image support and the intended working
region, and the excluded fraction must be reported in the UI and the export rather than buried. It
becomes too misleading when the excluded material is *spatially systematic* — one whole side of the
frame, or the entire periphery — because the distortion map is then extrapolating over a region the
user believes was calibrated. A count-based threshold alone is insufficient; the guard must be
spatial. On Clearwater this mattered: restricting each capture to its largest indexed component
dropped observations, and the correct behaviour was to report that rather than fit an incoherent index
set.

**No hybrid PD-plus-line objective.** Adding line residuals for the non-lattice points to a PD fit
would sum two differently-normalized residuals whose relative weight is arbitrary, giving an estimand
that is neither PD nor Sampson and that changes silently with the ratio of lattice to non-lattice
points. If a combined fit is ever wanted, its estimand and weighting need their own analysis round.

**Provenance to persist and export** (abstract until schema review): requested structure mode;
objective actually used; objective identifier and version; validator version; validation status;
fallback reason if any; counts of included and excluded points and components; spatial-weighting method
and version; and whether the user acknowledged a fallback warning. Exports currently carry distortion
parameters and quality metrics but no method at all
(`VSCalibration.mm:2598-2649`), so a residual in an export is presently uninterpretable as to which
objective produced it. Line and point records reach XML only when the
`includeScreenCoordsInExports` default is set (`:2600`), so provenance must not be attached only to
those child elements.

**Persisting the detector's lattice indices is the highest-value change and is separable from
everything else.** Carrying `Plumbline.isRow` and `index`, and ideally `GrownLattice.ij` per corner,
through `addNewAutodetectedLineWithPoints` into new point/line attributes would remove the entire
index-reconstruction step, eliminate the contradiction and component-splitting failure modes that
inference creates, and give shared corners a real identity. It is additive, so old documents simply
lack the fields and fall back to inference or to the line objective.

## 6. Answers to the eight questions

1. **Old documents stay reproducible** by absence of the new metadata meaning "legacy": no structure
   mode, no objective identifier, therefore legacy ODR on the stored representation, with the existing
   gate. Nothing is reinterpreted, and modernizing is an explicit user action that is recorded.
2. **Deliberate non-lattice calibration** is declared by line provenance at creation (manually clicked
   lines are non-lattice) or by an explicit structure-mode setting, and proceeds to the modern Sampson
   line objective with no warning and no degraded status.
3. **An unexpected lattice failure** presents a modal naming the specific blocking checks, offering
   return-to-review, continue-with-line-fallback (stating that the estimand changes and results are not
   comparable), or cancel. Never a silent downgrade. Headless fails closed with a distinguishable
   status and a machine-readable reason unless a fallback policy was configured.
4. **The modern fallback** is unique-observation block Sampson with frozen raw-coordinate quadrature,
   with legacy ODR retained as an explicitly versioned reproduction mode.
5. **Blocking failures** are those asserting false structure: index contradictions, duplicate indices,
   a line joining unrelated segments, insufficient non-collinear support, and unsafe projective
   denominators. Sparsity, holes and fragmentation are not blocking.
6. **Disclosed interactively:** which objective ran and why; validation status with named failures;
   included and excluded counts with their spatial distribution; the residual *labelled with its
   objective*; and any single-orientation or degenerate-support warning.
7. **Persisted and exported:** the provenance list in §5, with exports carrying the objective
   identifier alongside every residual.
8. **Offline tests required before implementation:** validator behaviour on the known-pathological
   captures, including the 1649 px joined line and the multi-component captures; Sampson-versus-EIV
   equivalence re-confirmed on non-lattice line sets rather than only on chessboards; single-orientation
   and one-dimensional-support identifiability probes; quadrature support validation on deliberately
   degenerate sets; downstream metric validation of the Sampson fallback on documents that have no
   lattice at all, which this round did not test; and a round-trip test that stored provenance
   reproduces a calibration bit-for-bit. Downstream validation to date covers PD-D versus legacy ODR on
   **one** document, so the fallback objective's metric behaviour is currently unmeasured.
