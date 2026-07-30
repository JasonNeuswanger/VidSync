# Correction, 2026-07-29 — two SD-D execution paths, and Clearwater's observation-set sensitivity

A **correction addendum**. It does not overwrite `ADDENDUM_2026-07-29_REAL_DATA.md` or any historical
artifact; new output is in `analysis-output/correction-2026-07-29/`. Tables and plots unaffected by the
points below are not redone.

**REVISION 2, same date.** Five consistency defects in revision 1 of this document are corrected below,
with no new fits and no change to any stored calibration result: (a) the overloaded `valid` status is
replaced by five explicit states, and pool/Right PD-D/M1 is excluded from every accepted ranking because
it fails the frozen empirical gate; (b) explicit `--sd-from` reuse is now fail-closed and can no longer
silently refit; (c) the Clearwater experiment is renamed and re-described as `min_inc=1` versus
`min_inc=2` **incidence-filter** sensitivity, because every observation in both views was successfully
lattice-indexed; (d) the sensitivity experiment is 2 views x 2 models x 2 cameras = **8 fits**, not four;
(e) the known-length interpretation now separates point-estimate stability from inferential stability.
Sections 3, 4 and 6 are rewritten accordingly; section 1's numbers are unchanged. Revision 2 outputs:
`sd_report_regen_full.{json,log}` (regenerated from stored artifacts with a tripwire proving zero
optimizer calls).

**REVISION 3, same date.** Revision 2's `--sd-from` verifier was fail-closed but its notion of *identity*
was too weak, in five specific ways confirmed from the code: it inferred the observation view from `n_obs`
alone, accepted missing frame and coordinate-convention metadata, accepted **either** recognized view
rather than the view the caller was about to use, identified the producing implementation only by the
manifest's analysis *name*, and never tied a reused map to the bytes of the artifact it came from. Section
7 below defines the exact provenance contract that replaces it, the canonical point-set hash, the
producer-code fingerprint and the legacy sidecar mechanism. **No fit was run and no number in this document
changed:** the revision-3 verifier selects exactly the same twelve SD-D maps the corrected report already
used, with identical `loss`, `nfev` and `eta`, verified with every optimizer entry point tripwired.
Revision 3 outputs: `sd_real_full.json.provenance.json` (the legacy sidecar) and a re-run
`sd_report_regen_full.{json,log}` that now records content hashes rather than modification times.

## 1. The two SD-D paths, and why they differed

There were two SD-D workflows and they were **not** solving the same optimization problem, although they
were minimizing the same objective:

- `sd_real.py` fits SD-D with `sd_fast.SDFast` and `sd_fast.solve`: an **analytic sparse Jacobian**,
  `ftol = xtol = gtol = 1e-8`, `max_nfev = 300` (rescue at 600), and a **multistart** bank of up to six
  initializations with best-by-objective selection. Every one of the twelve reported fits terminated
  on `ftol` or `ftol+xtol` in 5–61 evaluations, well inside the 300 cap.
- `xdoc_objectives.py` refit SD-D with `objectives.fit(..., "SD", ...)`: **finite-difference** Jacobian
  under `jac_sparsity`, `ftol = xtol = gtol = 1e-14`, `max_nfev = 1200`, single start from B. Those
  tolerances are unreachable on this objective — the relative cost change plateaus near 1e-9 per
  iteration (`sd_fast` module docstring, measured) — so this path could not certify convergence: it hit
  the 1200-evaluation cap on **8 of the 12 camera-fits** (the other four terminated at nfev 154, 151, 391
  and 829). Because a candidate is usable only if it is valid on *both* cameras of a document, a single
  capped camera excluded SD-D from that document entirely, so SD-D never once appeared in a downstream
  table on any of the three documents.

  It was nevertheless finding the **same optimum**. On the four cameras where both paths used the same
  view, the two SD-D objective values agree to ≤1.1e-4 absolute (118.56308 vs 118.56301; 88.30450 vs
  88.30450; 51.14786 vs 51.14787; 50.83273 vs 50.83262; 110.53121 vs 110.53121; 18.22518 vs 18.22519;
  222.09867 vs 222.09866; 29.13580 vs 29.13574). On `mid` they differ substantially — 52.96866 vs
  39.78244, 31.42573 vs 25.91489, 94.28535 vs 54.91367, 16.27546 vs 9.72867 — and that difference is
  entirely the observation set: the old `xdoc` values reproduce the fallback-view arm of section 4 to
  ≤1.3e-4. So the two paths solved the same problem on four cameras and a different problem on `mid`.

The refit was never mathematically necessary. `sd_fast`'s residual is verified **bit-identical** to
`objectives.resid_SD` at a common parameter point (`test_sd_fast.py`), the datasets are built by the same
`OB.Dataset` rules from the same captures, and the known-length path consumes only a 14-parameter map.

## 2. Correction to the tooling

`xdoc_objectives.py` gains an **opt-in** `--sd-from <artifact>`. With it, SD-D maps are *evaluated* from
an `sd_real`-shaped artifact instead of refit; without it, behaviour is exactly as before. Full source
provenance — artifact path, analysis name, source-file hashes, git state, solver description, source init
and termination — is carried into the log, into each fit record and into the manifest, and validity is
decided from the **source** fit's cap (`sd_fast`'s 300), not this script's 1200.

**Revision 2 makes this fail-closed.** Revision 1's loader returned `None` for a record it could not
verify and the caller then quietly refit, so an incomplete or mismatched artifact produced a table with
mixed provenance and no marker. Now `preflight_sd_reuse` runs **before the document loop and before any
optimizer is constructed**, demands a verified record for every requested document/camera/model, collects
every failure into one diagnostic, and exits 3. Each record is checked for: document sha256, clip name,
model, exactly-one-record (duplicates across camera entries are refused rather than arbitrated), a finite
14-entry theta, `completed`, an identified producing implementation (manifest analysis name), and
**observation-view identity** — the artifact's recorded observation count must match exactly one of the two
locally recomputed views, the matched view is recorded on the record, and a self-declared view that
contradicts the count fails. Declared frame and coordinate convention, when present, must match the local
ones. Refitting an **absent** map is still a legitimate workflow but requires the separate, conspicuous
`--sd-refit-missing`, which is announced loudly, is rejected outright without `--sd-from` (exit 2), and
never rescues a present-but-mismatched or malformed record — that is corruption, not a gap. Verified
against the real artifact: 12 of 12 maps verified, all on `min_inc2_indexed`, zero optimizer calls.

Regression test: `test_sd_map_reuse.py`, 19 checks. It covers the fail-closed cases (wrong hash, wrong
clip, absent model, incomplete fit, non-finite theta, no source at all), the cap accounting (a capped
fit stays invalid; a reused converged fit is valid), and — on the real pool document — that a reused map
passed through `DistortionMap.for_camera` → `build_calibration` → `node_residuals` is **bit-identical**
at seven deterministic probe pixels before and after, i.e. evaluating a map does not recalibrate it.

**Revision 3 supersedes the identity check described in the paragraph above.** The observation view is no
longer matched by count and no longer chosen by the artifact, frame and coordinate convention are no longer
optional, the producing implementation is no longer identified by its analysis name, and every reused map is
bound to the artifact's content hash. See section 7. The fail-closed *mechanism* — preflight before the
document loop, all failures in one diagnostic, exit 3, `--sd-refit-missing` for absent records only — is
unchanged.

No production calibration behaviour or default was touched.

## 3. Corrected known-length results

`xdoc_objectives.py --sd-from analysis-output/addendum-2026-07-29/sd_real_full.json` puts SD-D into a
known-length table for the first time. Mean absolute error in millimetres — the *measurements*, which
revision 2 does not change:

| Document / placement | stored | B/M0 | B/M1 | SD-D/M0 | SD-D/M1 | PD-D/M0 | PD-D/M1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pool / vsd nodes (n=1010) | 0.9900 | 0.9540 | 1.0058 | 0.9586 | 1.0064 | 1.0556 | 1.0900 |
| pool / Cal B XML (n=1010) | 0.7503 | 0.6693 | 0.6803 | 0.6763 | 0.6847 | 0.6535 | 0.6575 |
| 8 mm / vsd nodes (n=42) | 4.9432 | 5.0049 | 4.1865 | 4.1637 | **3.8597** | 4.1193 | 3.9146 |
| mid / vsd nodes (n=57) | 3.1669 | 3.4341 | 3.4799 | 3.3220 | 3.4256 | 3.4703 | 3.5833 |

**Correction to revision 1's ranking claim.** Revision 1 said all seven candidates were "valid on all
three documents". That was wrong, because it inherited `xdoc`'s single `valid` flag, whose `admissible`
field comes from the weaker production gate `lattice.admissible` rather than from the frozen empirical
gate `mapmetrics.admissibility_v2` used everywhere else. Under the explicit rule in `fitstatus`
(reproduced in section 7), **pool/Right PD-D/M1 is empirically inadmissible and therefore diagnostic-only
on the pool document**, so the pool rankings admit five fitted candidates, not six. On the 8 mm fisheye
and on mid all six fitted candidates are eligible. The accepted rankings, with the stored calibration
reported separately as a reference rather than ranked as a fitted candidate:

| Block | accepted ranking (best first) | diagnostic-only | reference anchor |
| --- | --- | --- | --- |
| pool / vsd nodes | B/M0 0.9540, SD-D/M0 0.9586, B/M1 1.0058, SD-D/M1 1.0064, PD-D/M0 1.0556 | PD-D/M1 1.0900 (frozen gate) | stored 0.9900 |
| pool / Cal B XML | PD-D/M0 0.6535, B/M0 0.6693, SD-D/M0 0.6763, B/M1 0.6803, SD-D/M1 0.6847 | PD-D/M1 0.6575 (frozen gate) | stored 0.7503 |
| 8 mm / vsd nodes | SD-D/M1 3.8597, PD-D/M1 3.9146, PD-D/M0 4.1193, SD-D/M0 4.1637, B/M1 4.1865, B/M0 5.0049 | none | stored 4.9432 |
| mid / vsd nodes | SD-D/M0 3.3220, SD-D/M1 3.4256, B/M0 3.4341, PD-D/M0 3.4703, B/M1 3.4799, PD-D/M1 3.5833 | none | stored 3.1669 |

Note the consequence on pool with the Cal B nodes: PD-D/M1's MAE of 0.6575 mm would have placed second,
and it is excluded anyway. Whether any accepted gap is separated from zero is a separate question, and on
mid the replication structure is five clusters. No objective magnitude is compared across estimators
anywhere in this document.

## 4. Clearwater INCIDENCE-FILTER view sensitivity (within-method, 8 fits)

**Terminology correction.** Revision 1 called this "observation-set sensitivity" and named the arms
`fallback_raw` and `indexed`, which reads as though one arm contained observations that could not be
lattice-indexed. That is not what happened. On `2015-06-22-1 Clearwater` **every** observation is
successfully lattice-indexed — 340 of 340 on Left, 365 of 365 on Right, zero index contradictions — in
both arms. The two views differ only in the **incidence filter**: `min_inc=1` keeps every observation,
`min_inc=2` keeps only observations carrying at least two line incidences. The 31 (Left) and 47 (Right)
excluded observations are single-incidence points, not indexing failures. The correct description is
*incidence-filter (min_inc) view sensitivity*, triggered by the lattice-eligible caller branch choosing
which view to hand SD-D. The historical internal identifiers are preserved in the already-written
artifact for provenance; `sd_viewsens.DISPLAY_LABEL` and `sd_report_regen.VIEW_META` supply the display
labels and definitions that reports must use.

| Canonical name | Display label | Selection predicate | Left | Right | Caller branch |
| --- | --- | --- | --- | --- | --- |
| `min_inc1_all_incidences` (was `fallback_raw`) | min_inc=1 view (all incidences kept) | `OB.Dataset(caps, require_indexed=False, min_inc=1, kappa=3.0)` | 340 obs / 38 lines / `7034093eea1518c5` | 365 / 39 / `3a9fb1fc4a59871e` | `sd_real.build` else-branch, `xdoc_objectives` `dlines[clip]`; lattice-eligibility test FAILS |
| `min_inc2_indexed` (was `indexed`) | min_inc=2 view (≥2 line incidences) | `OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)` | 309 obs / 38 lines / `caae37fd00f4d356` | 318 / 39 / `5683fb309c162828` | `sd_real.build` if-branch, `xdoc_objectives` `dsets[clip]`; lattice-eligibility test PASSES |

Hashes are order-independent digests of the coordinates, weights and line incidences of the exact
observation set. The `min_inc=2` set is a strict subset in both cameras, so the common intersection is
309 and 318.

**Fit count correction.** The experiment contains **eight** fits — 2 views × 2 models × 2 cameras — not
four. Revision 1 said "all four fits", which was a per-camera count stated as if it were the total.
`sd_report_regen.py` asserts the full Cartesian product and reports 8 expected, 8 found, 0 missing,
0 duplicated, with 4 distinct observation-set hashes (one per camera per view). All eight terminate on
`ftol` (4–34 evaluations, cap 300), all eight pass the frozen `admissibility_v2` gate, and all eight
invert with zero failures.

The map change attributable **solely** to the view, after projective alignment inside the common hull, is
0.1200 px median (M0) and 0.0372 px (M1) on Left, and 0.1085 px and 0.1035 px on Right; raw medians are
0.22–0.39 px, and corner-region aligned medians reach 0.30 px. For scale, the M0 → M1 step *within* a
single view is 0.21–0.42 px aligned median — larger than the view effect.

**Known length: point estimate versus inference.** The known-length point estimates are insensitive to
the incidence-view change on this dataset: MAE moves by −0.0562 mm for M0 (3.3782 → 3.3220) and
−0.0192 mm for M1 (3.4448 → 3.4256), one to two orders of magnitude below the ≈0.4 mm spread between
candidates. Inference is **not** equally stable. The `SD-D/M1 − SD-D/M0` contrast is classified as
separated from zero on the `min_inc=1` arm (cluster mean +0.0515 mm, 95% CI [+0.0055, +0.0976]) and not
separated on the `min_inc=2` arm (+0.0796 mm, [−0.0428, +0.2020]) — the point estimate moves in the same
direction and grows, while the interval widens enough to change the classification. Both intervals come
from five timecode clusters under the established clustered procedure, so the correct statement is: the
point estimates were insensitive to the view, but one interval's separation classification changed, and
with five clusters the inference is not robust to the view choice. Revision 1's unqualified "does not
materially affect known length" is withdrawn.

This is a within-method experiment. It is not evidence about which calibration method is better.

## 5. Caller coupling

The branch is `sd_real.py:135`, `D = Dind if lat_ok else OB.Dataset(caps, require_indexed=False,
min_inc=1, kappa=3.0)`, with the same pattern at `xdoc_objectives.py:226` (`Dsd = D if pd_ok else
Dline`), `sd_diag.py:72` and `sd_refit.py:126`. All four are **harness** callers; shipped VidSync
calibration has no SD-D path at all, so no production behaviour is involved.

SD-D does **not** mathematically require lattice indices: `objectives.resid_SD` and `_blocks` use
per-observation line incidences only and never read `C.rc` or the component labelling. The indexed
subset was adopted deliberately so that SD-D and PD-D are compared on identical observations
(`xdoc_objectives.fit_candidates` docstring), which is a **comparison-design** choice, not part of the
estimator's contract; the `require_indexed=False` view was the error-recovery path for documents where
PD-D cannot run. Consequently a lattice-validation fix legitimately changes which view the caller
supplies, and therefore changes the SD-D fit — which means the earlier report's mid SD-D comparison
conflated an estimator difference with an observation-set difference. Section 4 quantifies that
confound: it is about 0.04–0.12 px of map and under 0.06 mm of known length.

Smallest correction, **not made in this tranche**: give SD-D its own explicit view selector rather than
inheriting PD-D's eligibility — e.g. a `sd_view` parameter with values `unique` (the estimator's natural
domain) and `match_pdd` (for like-for-like comparison) — defaulting to `match_pdd` so existing numbers
are unchanged, and record the choice in the artifact. Regression tests it would need: that `unique` and
`match_pdd` select exactly the documented counts on all six established cameras; that the selector is
recorded in the manifest and in every fit record; that a lattice-eligibility change cannot alter the
`unique` view; and that the comparison tables refuse to place two different views in the same row.

## 6. Corrections to earlier statements

- **Observation counts.** The previous addendum said the historical mid SD-D fits used "365 and 365
  observations". That is wrong for Left. The correct counts are **340 (Left) and 365 (Right)** for the
  fallback view — those are the unique-observation totals — against 309 and 318 for the indexed view.
  340/365 are also the "consistently indexed before filtering" figures, because on this document every
  unique observation is indexed; the drop to 309/318 is caused by `min_inc = 2`, not by indexing.
- **Cross-estimator objective magnitudes.** Any comparison of raw objective values between B, SD-D and
  PD-D is withdrawn; they are different objectives on different residual definitions. Only same-estimator
  comparisons (M0 versus M1, or view versus view) are made here, and each is labelled as such. Section 1's
  paired numbers are same-estimator, same-view SD-D values and are therefore legitimate.
- **SD-D convergence accounting.** SD-D is now reported consistently: the `sd_fast` fits converged
  (`ftol`, 4–202 evaluations, cap 300); the old `xdoc` refits reached the 1200-evaluation cap and are
  non-convergent. A capped fit is never described as converged, and the four statuses —
  optimizer convergence, numerical invertibility, empirical admissibility, and eligibility for accepted
  rankings — are kept separate.
- **pool/Right PD-D/M1** failed the frozen empirical gate and is **diagnostic-only**. Verified from the
  serialized artifacts: optimizer status 2 (`ftol`), 74 evaluations, cap not reached, so **converged**;
  zero shipped-inverse failures and 8.64e-13 px maximum round-trip, so **numerically invertible**;
  `lattice.admissible` passes with min det over the full frame 0.9298, so the **production gate is
  satisfied**; but `admissibility_v2` reports `safe=False`, `physically_plausible=False`, min det 0.9298,
  min σ 0.9462, expansion 1.7157, so the **frozen empirical gate fails**. It is therefore excluded from
  every accepted ranking on the pool document (both cameras' candidate is disqualified, because a stereo
  measurement uses both), retained as a labelled diagnostic row with that reason, and never counted among
  valid candidates. This is the only gate disagreement among the 42 document/camera/candidate records.
- **The "significantly better residual but worse accuracy" claim is withdrawn** and replaced with the
  narrower statement the data supports: *improvements in line residuals do not reliably predict
  improvements in physical accuracy.* No claim of a statistically separated residual-accuracy inversion is
  made, because no single valid comparison establishes both halves: on mid, PD-D/M1 improves the line fit
  over PD-D/M0 and its known-length MAE is worse, but the PD-D/M1-minus-PD-D/M0 contrast is not separated
  from zero; the only separated mid contrast is PD-D/M1 minus B/M1, which compares two different
  estimators rather than a residual improvement within one.
- **The mid separation is conditional** on the established clustered procedure: 57 measurements in five
  timecode clusters, cluster-level mean with a normal 95 percent interval from five values. With five
  clusters that interval is fragile, and the claim should not be read as a general result.
- **A genuine whole-line holdout remains uncompleted.** The only real-data zero-weight holdout used so
  far is the lattice diagonal families, which is not genuinely held out for PD-D. No whole-line holdout
  has been defined or run on real data.

## Reproduction

From `tools/pooltest`, with `~/.venvs/vidsync/bin/python`:

```
python test_sd_map_reuse.py
python sd_viewsens.py   --outdir analysis-output/correction-2026-07-29
python xdoc_objectives.py --outdir analysis-output/correction-2026-07-29 \
       --sd-from analysis-output/addendum-2026-07-29/sd_real_full.json
# the fallback-arm known-length, from the maps sd_viewsens produced:
python xdoc_objectives.py --outdir <tmp> --docs mid \
       --sd-from analysis-output/correction-2026-07-29/sd_fallback_arm_maps.json
```

Artifacts: `sd_viewsens_full.{json,log}`, `xdoc_objectives_full.{json,log}` (indexed arm, all three
documents), `xdoc_objectives_mid_FALLBACKARM.{json,log}`, and `sd_fallback_arm_maps.json` (the
fallback-view SD-D maps, in `sd_real` artifact shape, so the established procedure can consume them
without refitting).

## 7. The status schema and the ranking rule (revision 2)

`fitstatus.py` records five states independently and never collapses them:

| State | Meaning |
| --- | --- |
| `optimizer_converged` | the optimizer reported a convergence criterion (status > 0) **and** did not reach its evaluation cap. A cap is not convergence. |
| `numerically_invertible` | zero shipped-inverse failures and a maximum round-trip below 1e-9 px. |
| `empirically_admissible` | the **frozen** gate `mapmetrics.admissibility_v2` reports `safe` **and** `physically_plausible`. Recorded beside, never merged with, `production_gate_ok` (`lattice.admissible`), which is weaker. |
| `eligible_for_ranking` | the conjunction of the three above plus finite parameters, per camera; a document candidate additionally requires every camera to be eligible. |
| `diagnostic_only` | not eligible, always with `diagnostic_reasons`; retained in labelled diagnostic tables. |

The ranking rule, quoted from `fitstatus.RANKING_RULE`: a candidate is eligible for an accepted ranking on
a document if and only if, for every camera of that document, the optimizer converged without reaching its
cap, the map is numerically invertible, the map passes the frozen empirical gate, and its parameters are
finite. Anything else is diagnostic-only, excluded from every accepted ranking and from accepted-map
synthesis, and never counted among "all valid candidates". The stored calibration anchor is not an
optimizer output and is reported separately as a reference, never ranked as an accepted fitted candidate.
Passing the frozen gate is an empirical result on a finite grid at a finite cell bound, not proof of global
injectivity or physical correctness.

## Revision 2 reproduction and artifacts

```
python test_sd_reuse_failclosed.py        # 53 checks under revision 3, zero fitting-entry-point calls
python test_sd_map_reuse.py               # 19 checks (revision 1, still passing)
python sd_report_regen.py --outdir analysis-output/correction-2026-07-29
```

`sd_report_regen.py` derives the status table, the accepted rankings, the view metadata and the 8-cell
consistency check from stored artifacts only. It installs a tripwire over `objectives.fit`,
`objectives.PDExact.fit`, `objectives.profile_H`, `sd_fast.solve` and `sd_fast.fit_sd` before reading
anything, so any attempted optimizer call fails the run; the artifact records
`optimizer_calls_attempted: []`. A missing map or summary is reported and exits non-zero rather than being
refitted. New artifact: `analysis-output/correction-2026-07-29/sd_report_regen_full.{json,log}`.

## 7. Revision 3 — the exact provenance contract for reused SD-D maps

### 7.1 What revision 2's verifier actually established

Read from `xdoc_objectives.verify_sd_records` as it stood, not from a summary of it:

| Weakness | The code | Consequence |
| --- | --- | --- |
| View inferred from a count | `matches = [v for v, cnt in lv.items() if v in SD_VIEWS and cnt == n]` | two different point sets of the same cardinality were indistinguishable |
| Missing frame accepted | `if fr and lv.get("frame")` | the real artifact records no `frame`, so the test never ran |
| Missing convention accepted | `if cv and lv.get("coordinate_convention")` | likewise never ran |
| Either recognized view accepted | request tuple was `(doc_key, sha, clip, name)` — no expected view | a `min_inc=1` map verified for a caller about to use the `min_inc=2` map; the old test asserted this as intended |
| Producer = a name | `if not src.get("analysis")` | an analysis name is neither a revision nor a code identity |
| No artifact binding | nothing hashed the file | "the source fits did not change" could only be argued from `mtime` |

### 7.2 The contract (`sdprov`, schema `sd-provenance/2`)

Every explicitly reused SD-D map must present, and match, all of: `artifact_sha256` (computed from the
file's bytes at load time); `doc_key` and `doc_sha256`; `clip`, `cal_pk`, `clip_pk`; `candidate` and
`model`; `view_id`; `view_selector`, `view_selector_id` and `view_selector_version`; `n_obs`, `n_lines`,
`n_captures`; `pointset_hash_version`, `pointset_sha256` and `ordered_pointset_sha256`; `frame`;
`coordinate_convention`; `model_parameterization`; `producer_revision`; `producer_code_fingerprint`;
`parameter_sha256`; and a `status` block carrying `optimizer_converged`, `numerically_invertible`,
`empirically_admissible` and `eligible_for_ranking`. Every field is required — none is skipped when absent.

The expectation each record is matched against is reconstructed **independently from the documents** by
`sdprov.view_identity`, never read from the artifact.

### 7.3 The specifically requested view

A reuse request is an `sdprov.reuse_request` naming one exact `expected_view`. The caller decides it with
the same predicate the document loop uses (`Dd.n >= 20` and zero index contradictions), so the artifact
never gets to choose which view it supplied. A valid map for the other recognized view fails, and the error
says so: *"view_id 'min_inc1_all_incidences' is not the requested view 'min_inc2_indexed' (a recognized
view, but not the one requested)"*. Verified on the real artifact: requesting `min_inc=1` instead of
`min_inc=2` rejects all twelve real maps.

Terminology, unchanged from section 4: on 2015-06-22-1 **all 340 Left and 365 Right source observations
were successfully lattice-indexed**. The 309 and 318 subsets arise from the `min_inc=2` incidence filter,
not from any indexing failure.

### 7.4 The canonical point-set hash (`sd-pointset/1`)

`sd_viewsens.obs_hash` was not reused: it formats coordinates as `%.6f` (colliding sub-micropixel
differences), identifies a line by its construction-order integer id, and is unversioned. The versioned
serialization instead is:

1. **Line fingerprint.** For each line, `sha256` over `sd-pointset/1|line|<capture>|family=<f>|n_members=<k>`
   followed by its selected members' `(x, y)` sorted, each coordinate as `float.hex()` — lossless and
   locale-free. Content-derived, so it is stable under any renumbering; the capture is included because two
   captures may legitimately hold the same coordinates.
2. **Observation record.** `<capture>|x=<hex>|y=<hex>|w=<hex>|n_inc=<k>|lines=<sorted fingerprints>`. These
   are exactly the fields `sd_fast.SDFast` and `objectives.resid_SD` read; `rc`, `lat` and `local` are PD-D
   and ED inputs and are deliberately excluded so an SD-D map is not invalidated by a field it never saw.
   The weight is included because it enters the residual as `sqrt(w)`.
3. **`pointset_sha256`** hashes a `sd-pointset/1|n_obs|n_lines|n_captures` header plus the records **sorted**
   — record order is not semantic, so the identity of a point *set* must not depend on visit order.
4. **`ordered_pointset_sha256`** hashes the same records **unsorted**, recorded in addition because order
   does reach execution: `objectives._blocks` groups observations by incidence count in visit order, fixing
   the residual row layout and hence the floating-point summation order. Both are compared on reuse.

Demonstrated in `test_sd_provenance.py [0]`: two views with identical `n_obs`, `n_lines` and `n_captures`
but one coordinate moved 0.25 px hash differently; a 1e-12 change in one weight changes the hash;
reordering leaves `pointset_sha256` unchanged but changes the ordered hash.

### 7.5 Producer revision and dirty-worktree code identity

The producing worktree **was** dirty (`dirty: true, n_dirty_paths: 172`), so the commit does not determine
the code that ran. Both are required and recorded: `producer_revision` (`commit`, `branch`, `dirty`,
`n_dirty_paths` — a commit without a `dirty` flag fails, because it cannot be interpreted) and
`producer_code_fingerprint` (`sd-code-fingerprint/1`): a `{basename: sha256}` map over the required
implementation subset `lattice.py, mapmetrics.py, objectives.py, sd_fast.py, sd_real.py`, plus
`combined_sha256 = sha256("sd-code-fingerprint/1\n" + "\n".join(f"{n}={h}" for n in sorted(required)))`.

That map is exactly what `artifacts.source_hashes` writes into every harness manifest at run time, so a
legacy artifact's own manifest is sufficient evidence for it. The fingerprint is verified three ways: it
must recompute from its own file hashes, it must cover every required file, and it must agree with the
producing manifest's `source_file_sha256`. The **current** worktree is never required to be clean.

For `sd_real_full.json` the fingerprint is
`0d4374a6ed048e4ccbeaa28f2ae9c8d85d6c95ac53f10d7e93dae2e74cf28176`.

### 7.6 The legacy sidecar (`sd-provenance-sidecar/1`)

`sd_real_full.json` is **not modified**. `sd_sidecar_build.py` writes
`sd_real_full.json.provenance.json`: `{schema_version, artifact_sha256, artifact_basename, built_by,
built_at, builder_code_fingerprint, policy, records: [...]}`, each record a full `sd-provenance/2` block
plus an `evidence` map naming where every field came from. Lookup is keyed by
`(artifact_sha256, doc_sha256, clip, candidate)`, so a sidecar written for other bytes can never be
consulted. Malformed, wrongly versioned, incomplete, duplicated and conflicting entries are all rejected at
load time — a duplicate is refused even when both copies are byte-identical, because silently preferring one
is how provenance rots.

Evidence used for the twelve real records, none of it copied as a guess from the artifact being verified:

* `view_id` — **derived**, from the producer's own rule (`sd_real.build`: `D = Dind if lat_ok else Dline`,
  pinned by the code fingerprint) applied to the outcome the artifact recorded (`lattice_valid`), then
  **confirmed** by rebuilding the view from the document and requiring its observation, line and capture
  counts to equal the artifact's. All six cameras: `min_inc2_indexed`, all three counts matching.
* counts and point-set hashes — rebuilt from the documents via `lattice.load_captures` and
  `objectives.Dataset` at the view's kwargs.
* `frame` — `lattice.FRAME_W/FRAME_H`, confirmed against a **raw sqlite** read of min/max
  `ZSCREENX`/`ZSCREENY`, which is independent of `lattice.load_captures`.
* `coordinate_convention` — `raw ZVSSCREENPOINT.ZSCREENX/ZSCREENY pixels as stored, no transform applied
  (lattice.load_captures)`. Phrased as a code-verifiable fact; "origin top-left, y down" is an
  interpretation of the app, not something a harness run establishes, so it is not what the contract
  compares.
* `producer_revision` and `producer_code_fingerprint` — the artifact manifest's own `git` block and
  `source_file_sha256`, recorded by the producing process at run time.
* `parameter_sha256` — from the artifact's stored `theta14`.
* `status` — **recomputed** with `fitstatus.camera_status` from the artifact's stored optimizer,
  inverse-audit and frozen-gate numbers, at the source cap of 300. A declared status that contradicts the
  artifact's own evidence is refused.
* document identity — confirmed by recomputing `downstream.document_sha256` and reloading the bound
  calibration identity.

If any required field cannot be established the builder writes **nothing** and exits non-zero, so explicit
reuse then fails closed with an unverifiable-provenance error.

### 7.7 Fail-closed loading

`preflight_sd_reuse` still runs before the document loop and before any optimizer is constructed, still
collects every problem into one diagnostic, and still exits 3. Representative errors, all real output:

```
pointset_sha256 mismatch: 9999999999999999 != independently reconstructed 7fdc872bb621b56b
  -- SAME observation count, DIFFERENT point set
view_id 'min_inc1_all_incidences' is not the requested view 'min_inc2_indexed'
  (a recognized view, but not the one requested)
no view_id: the observation view is UNSPECIFIED and may not be inferred
n_lines: artifact/sidecar says 41, request requires 38
no frame metadata: frame width and height are required
coordinate_convention: artifact/sidecar says 'normalized [-1,1], y up', request requires '...'
producer_revision does not state whether the producing worktree was dirty, so the commit
  cannot be interpreted
producer_code_fingerprint.combined_sha256 0000000000000000 does not match its own file hashes
NO embedded provenance and no verified sidecar entry for artifact cfe207288866
sidecar entry .../SD-D/M0 for artifact e458cbfc4ef0 is CONFLICTING between conB.json and
  dupA.json; refusing to choose between them
provenance is INCOMPLETE; missing or empty: pointset_sha256, model_parameterization
declared status contradicts the artifact's own stored evidence for ['empirically_admissible',
  'eligible_for_ranking']
```

The separately explicit refit workflow is preserved: `--sd-refit-missing` still downgrades **absent**
records only, still never rescues a present-but-mismatched one, and is still rejected without `--sd-from`
(exit 2). `--sd-sidecar` is rejected the same way, so no flag combination is ambiguous.

### 7.8 Content-hash evidence instead of modification times

`sd_report_regen.py` now hashes every authoritative source artifact it consumes before reading anything and
again at the end of the run, prints both, records `source_artifact_sha256_before`,
`source_artifact_sha256_after`, `source_artifacts_unchanged` and `source_artifacts_changed`, and turns any
difference into a hard `problems` entry rather than a note. Modification times are not used as evidence of
content identity anywhere. Beginning and ending SHA-256, identical in both positions:

| Artifact | SHA-256, before and after |
| --- | --- |
| `addendum-2026-07-29/sd_real_full.json` | `fbfe7dec33c0c395b915fe24c83c53e8277bddb592794a5a380b016c73b48042` |
| `addendum-2026-07-29/sd_real_full.json.provenance.json` | `4b8c97835cc50fe70f354e247dc748bd1a979ec5d155942c70d503f541fb87b6` |
| `correction-2026-07-29/xdoc_objectives_full.json` | `5a91edeaaa8af8262d2f3650a2e189b682fdbe30dcbab165ac62edc9d6e4f67b` |
| `correction-2026-07-29/sd_viewsens_full.json` | `69ed1cf770714e3b306d32b383b334cdaa480f3f97e91e8e680ddf5f3f2bf1eb` |

`sd_sidecar_build.py` independently re-hashes the artifact after writing the sidecar and reports
`artifact is byte-unchanged`.

### 7.9 No scientific number changed

The revision-3 verifier selects **exactly** the twelve SD-D maps the corrected report already evaluated —
same keys, same `loss`, same `nfev`, same `eta`, nothing extra — checked with `objectives.fit`,
`objectives.PDExact.fit`, `sd_fast.solve` and `sd_fast.fit_sd` replaced by tripwires. Section 3's
known-length table, section 4's sensitivity matrix and every residual and disagreement figure are therefore
untouched, and none of them was regenerated.

## Revision 3 reproduction and artifacts

```
python sd_sidecar_build.py --dry-run    # validate; writes nothing
python sd_sidecar_build.py              # writes sd_real_full.json.provenance.json
python test_sd_provenance.py            # 70 checks, zero fitting-entry-point calls
python test_sd_reuse_failclosed.py      # 53 checks, zero fitting-entry-point calls
python test_sd_map_reuse.py             # 19 checks (revision 1, still passing)
python sd_report_regen.py --outdir analysis-output/correction-2026-07-29
```

`test_sd_provenance.py` installs the tripwire before anything else runs and asserts the attempted-call list
empty at the end, so "every verification failure happened without invoking the optimizer" is enforced rather
than assumed. It also runs the three prior suites as subprocesses, so a regression in them fails it.
