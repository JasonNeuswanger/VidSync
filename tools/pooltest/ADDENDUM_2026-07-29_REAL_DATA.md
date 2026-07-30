# Addendum, 2026-07-29 — completing the established-real-data method comparison

This is an **addendum**, not a replacement. The historical artifacts in `analysis-output/` are left
exactly as they were; everything produced here is in `analysis-output/addendum-2026-07-29/`.

> **PARTIALLY SUPERSEDED, same date, by `CORRECTION_2026-07-29_SD_PATHS.md` revision 2.** The
> measurements in this document stand unchanged. Four *statements* in it are corrected there and should
> be read from that document instead: (1) headline finding 4's implication of a statistically separated
> residual-versus-accuracy inversion — the supported claim is only that improvements in line residuals do
> not reliably predict improvements in physical accuracy; (2) headline finding 5, which reports
> pool/Right PD-D/M1 as a flagged solution — it is now formally **diagnostic-only** and excluded from
> every accepted ranking; (3) the description of the two `mid` SD-D observation views, which are a
> `min_inc=1` versus `min_inc=2` **incidence-filter** difference, not an indexing difference: every
> observation in both views was successfully lattice-indexed; and (4) any reading of "all candidates
> valid", which conflated the production gate with the frozen empirical gate.

## What is superseded

The lattice traversal-canonicalization defect in `lattice._recover_indices` (fixed the same day; see
`VALIDATION_REAL_DATA.md` and `test_lattice_traversal.py`) let the operator's click direction decide
edge direction while the index step was chosen by orientation family. On `2015-06-22-1 Clearwater`
("mid") one line per family per camera had been clicked against its family-mates, so every cycle through
it contradicted: 32 contradictions of 611 edges on Left and 36 of 644 on Right, one connected component,
every observation discarded.

The following earlier statements are therefore **superseded**:

- "`2015-06-22-1 Clearwater` has an inconsistent plumbline lattice." — It does not. Both cameras index
  completely with zero contradictions (340 of 340 and 365 of 365 observations).
- "PD-D cannot be fitted for mid/Left or mid/Right." — It can, through the ordinary production path with
  no diagnostic override.
- "The mid cameras contribute no PD-D evidence." — They now contribute two PD-D/M0 and two PD-D/M1 fits
  plus known-length results, which is what this addendum adds.

Nothing about the plumbline data itself changed. The click-direction-invariant `plumbline_sha256`
recorded in the addendum artifact is a digest of the stored geometry that is unchanged by the fix.

## Reproduction

From `tools/pooltest`, with `~/.venvs/vidsync/bin/python`:

```
# 1. the two ESTABLISHED scripts, re-run UNCHANGED into the dated directory (~55 s and ~225 s)
python sd_real.py         --outdir analysis-output/addendum-2026-07-29
python xdoc_objectives.py --outdir analysis-output/addendum-2026-07-29

# 2. the addendum analysis that reads them and adds what they do not compute (~11 s)
python real_addendum.py   --outdir analysis-output/addendum-2026-07-29
```

The `.vsd` documents are external; `VALIDATION_REAL_DATA.md` documents the required paths. Re-running
step 1 into the default `analysis-output/` would overwrite the historical artifacts, which is why the
`--outdir` is not optional in practice.

## Artifacts

| Path (under `analysis-output/addendum-2026-07-29/`) | Contents |
| --- | --- |
| `sd_real_full.json`, `.log` | established script, unchanged, six cameras × {B, SD-D multistart, PD-D, stored} with admissibility, inverse reliability, plausibility and residuals. PD-D now present for `mid`. |
| `xdoc_objectives_full.json`, `.log` | established script, unchanged, downstream known-length for all candidates with fail-closed validity and clustered contrasts. PD-D now present for `mid`. |
| `real_addendum_full.json`, `.log` | frozen inputs and hashes, PD-D fits with both initializations, the common residual tables (native and common observation sets), the full pairwise map-disagreement matrices, and the assembled known-length tables. |
| `real_addendum_pairwise_aligned.png` | 2×3 heatmaps: projectively aligned median in-hull disagreement, every method pair, per camera. |

## Data views

Defined once, not adjusted to make the comparison symmetrical:

- **V_raw** — every stored line-point record; a corner shared by two lines appears in both. B's reported
  fit consumes V_raw, which is B's documented semantics. (`sd_fast.dedup_view` is a *retained-line*
  filter, not a duplicate filter; it is used only for the SD-D warm start, never for reported B.)
- **V_indexed** — unique observations (exact-coordinate match) carrying a consistent lattice index, with
  at least two line incidences and the established `kappa=3.0` weighting. PD-D requires it; SD-D is given
  the same view whenever the lattice validates, so the two are compared on identical observations.

That rule did not change — its precondition did. On `mid`, the historical SD-D fits ran on the
`min_inc=1` view (340 observations on Left and 365 on Right — corrected here; revision 1 of this document
mistakenly gave both as 365) *because the lattice was wrongly rejected*. The addendum SD-D fits for `mid`
run on the `min_inc=2` view (309 and 318), like the other four cameras. Both views contain only
successfully indexed observations; they differ by the incidence filter. Historical `mid` SD-D objective
values are therefore not comparable with the addendum's, because the observation set differs.

Residuals are reported on both **native** (V_raw, B's set) and **common** (V_indexed) point sets for
every map, using one implementation (`sd_real.orthogonal_residuals`) that shares no code with any
estimator. Raw objective values are never compared across estimators.

## Holdout

There is no previously defined whole-line real-data holdout to reuse; the only established real-data
zero-weight holdout is the lattice **diagonal families**, which is used here. For PD-D it is not
genuinely held out — PD-D's fitted homography already predicts every indexed corner, diagonals
included — and every table says so.

## Reproducibility against the historical run

Comparing `analysis-output/sd_real_full.json` (pre-fix) with the addendum re-run, on the four cameras
that were already eligible: every objective agrees to ≤1.1e-8 absolute, and every fitted map agrees to
≤0.027 px maximum over the whole frame grid (≤0.008 px for all but one SD-D fit; PD-D to ≤2.5e-5 px).
Those residual differences are flat-direction solver noise, not a change of solution.

On `mid` the B fits agree to ≤9e-4 px but the SD-D fits move materially (median 0.26–0.50 px, max
3.5–6.6 px, objective 52.97 → 39.78 and 94.29 → 54.91). That is the observation-set change described
above, not a solver difference, and it is the reason historical `mid` SD-D numbers must not be quoted
alongside the addendum's.

## Headline findings

1. **The four previously eligible cameras are unchanged**, and the two new PD-D fits reproduce the
   pre-registered smoke references (271.83587, 262.27399, 427.31049, 385.72569; η 0.0053225 and
   0.0100847). Both PD-D/M1 initializations — DLT-from-B and the fitted-M0-at-η=0 start — reach the same
   objective to all printed digits on all six cameras, so the M1 result is not start-dependent.
2. **Adding `mid` strengthens the cross-method ambiguity evidence.** On `mid` the aligned in-hull median
   disagreement among B, SD-D, PD-D and the stored map is 0.05–1.25 px, even though the estimators
   minimize different objectives and cannot be compared by objective magnitude. Large raw disagreement is
   mostly gauge: pool/Right shows 35 px raw against 0.54 px aligned (gauge fraction 0.98).
3. **The largest disagreements are not confined to the 8 mm fisheye**, but they are much larger there
   (up to 3.4 px aligned in-hull, 16 px aligned p95) than on `mid` (≤1.25 px) or pool (≤0.64 px).
4. **M1's better line fit does not predict better physical accuracy.** On `mid`, PD-D/M1 fits the lines
   substantially better than PD-D/M0 (objective 427.31 → 385.73, residual RMS 0.640 → 0.306 px) yet its
   known-length MAE is *worse* (3.4703 → 3.5833 mm), and the `PD-D/M1 − B/M1` contrast is +0.1034 mm with
   a cluster 95% CI of [+0.0156, +0.1733] — separated from zero in the wrong direction. On the 8 mm
   fisheye the same contrast is −0.2718 mm, separated in the *right* direction. The sign is
   document-dependent, so line residual is not a usable model-selection criterion.
5. **One flagged solution:** pool/Right PD-D/M1 is `admissibility_v2 safe=False`
   (`physically_plausible=False`, min det 0.9298, min σ 0.9462, expansion 1.716) although it converges,
   inverts cleanly (round-trip 8.6e-13 px, zero failures) and is forward-certified at the cell bound.
   This is a pre-existing finding carried forward, not new.

Passing `admissibility_v2`, `certify_forward_injective` and `inverse_reliability` is an **empirical**
result on a finite grid at a finite cell bound. It is not proof of global injectivity or of physical
correctness.

## Scope

Six established cameras from three documents. No archive search, no detector run, no other stored point
set, no production change, no threshold change, no document or plumbline modification. Repeated fits of
the same camera are not independent evidence, and the six cameras are only three stereo documents: pool
(mild), 8 mm fisheye (strong), `mid` (intermediate, lens nominally 13 mm but unverified).
