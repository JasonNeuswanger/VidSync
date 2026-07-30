# Real-data validation of the lattice traversal-canonicalization fix

> **THE PINNED REFERENCES BELOW ARE STALE AS OF 2026-07-30, FOR TWO INDEPENDENT REASONS. Do not
> re-pin them without separating the two.**
>
> **Reason 1, document drift, which is NOT a code change.** Seven of the eight pinned observation
> counts were already wrong before any 2026-07-30 code change was made, measured by loading the
> documents through the then-current `lattice.py`: `mid`/Left reliable 341 against a pinned 340 and
> `Dind.n` 325 against 309, `mid`/Right 369 against 365 and 353 against 318, `8mm`/Left `Dind.n` 401
> against 398, `8mm`/Right 388 against 387. The stored plumbline geometry in
> `2015-06-22-1 Clearwater.vsd` and `2015-09-04-1 Clearwater.vsd` has therefore changed since these
> references were recorded. **The consequence is that the `PDD_REF` losses, and the `mid` PD-D numbers
> quoted in `ADDENDUM_2026-07-29_REAL_DATA.md`, are no longer reproducible from the documents as they
> now stand** — the observation set they were computed on no longer exists. That is not a solver
> difference and not a model effect; `mid`/Right alone gained 35 doubly-constrained observations.
> Establish what changed those documents before quoting or re-pinning any of it.
>
> **Reason 2, three intended `lattice.py` fixes on 2026-07-30**, each verified against the whole
> 20-document corpus. Their only effect on the six established cameras is `8mm`/Right gaining one
> observation, 408 to 409. Everything else on pool, `8mm` and `mid` is bit-identical. See
> `_split_axes`, `_expected_gap` and `_consensus_indices` for what each one does and why.

The traversal-canonicalization fix in `lattice._recover_indices` is covered at two levels. Both are
durable files in this directory; neither depends on a transcript or on a script under `/tmp`.

## 1. Runs anywhere: `test_lattice_traversal.py`

```
~/.venvs/vidsync/bin/python test_lattice_traversal.py
```

67 checks, no external data required. Sections [1]–[9] build synthetic lattices through the production
`_family_split` / `_recover_indices` / `_local_scale` path and assert that click direction, record
order and grid rotation are non-semantic while genuine topological contradictions and non-unit gaps
still fail closed. Section [10] tests the `_orient_members` zero-projection branch directly, because
that branch cannot be reached through `_family_split` — a line only joins a family when it lies within
45° of the family reference, so its chord is never exactly perpendicular to it. The rotation tests in
section [6] all take the ordinary nonzero-projection path and do **not** exercise it. Section [11] runs
the real `2015-06-22-1 Clearwater` permutation checks when that document happens to be present, and
prints `document unavailable; skipping` when it is not.

## 2. Opt-in, needs the field documents: `validate_lattice_real.py`

```
~/.venvs/vidsync/bin/python validate_lattice_real.py                      # all three checks
~/.venvs/vidsync/bin/python validate_lattice_real.py --check lattice      # six-camera before/after
~/.venvs/vidsync/bin/python validate_lattice_real.py --check permutation  # click-order invariance
~/.venvs/vidsync/bin/python validate_lattice_real.py --check pdd          # Clearwater PD-D smoke
~/.venvs/vidsync/bin/python validate_lattice_real.py --json analysis-output/validate_lattice_real.json
```

Exit status is `0` if every requested check passed, `1` if any check failed, and `3` if no document was
found — in which case nothing was verified and the script says so rather than reporting success. Run it
from this directory; the whole thing takes about six seconds.

### Required local data

Three documents, six cameras. They live outside the repository, which is why this cannot be an ordinary
CI test: the checks are opt-in rather than weakened to run without the real data.

| Key | Root | Path within the root |
| --- | --- | --- |
| `pool` | chena | `VidSync Projects/2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd` |
| `8mm` | drift | `2015-09-04-1 Clearwater.vsd` |
| `mid` | drift | `2015-06-22-1 Clearwater.vsd` |

No absolute path is baked into the script. The two roots resolve in this order: the `--drift-dir` /
`--chena-dir` options, then `VIDSYNC_DRIFT_PROJECTS` / `VIDSYNC_CHENA_PROJECTS`, then the conventional
Dropbox locations on the original machine.

```
export VIDSYNC_DRIFT_PROJECTS="/path/to/Drift Model Project/VidSync Projects"
export VIDSYNC_CHENA_PROJECTS="/path/to/Chena Project Synced"
```

A document that is absent is named in the header and its checks are skipped explicitly; results are
never inferred from the documents that were present.

### What each check asserts

**Check 1, six-camera lattice state.** Loads all six cameras through the ordinary production path with
no diagnostic override, and compares contradictions, dropped non-unit edges, component count, reliably
indexed observations, `Dind.n`, PD-D eligibility and the number of canonicalized lines against the
values in `EXPECTED`. The four cameras that already worked (`pool` and `8mm`) must be unchanged in every
field; `mid` must go from 32 and 36 contradictions with zero usable observations to zero contradictions
with all 340 and 365 observations indexed. It also prints the family reference directions and confirms
that every `mid` observation is consistently indexed before any downstream filtering.

Note that `reliably_indexed` (340, 365) and `Dind.n` (309, 318) legitimately differ on `mid`: the first
counts every consistently indexed observation, the second counts what survives the unrelated `min_inc=2`
requirement of the projective dataset.

**Check 2, click-order and record-order invariance.** For each camera, permutes the line records and
reverses the point order of a random half of the lines, then requires the component partition, the
gauge-normalized indices, the contradiction count and the indexed count to be identical to the
stored-order result. The gauge-invariant comparison helpers are imported from
`test_lattice_traversal.py` rather than duplicated, so the two files cannot disagree about what
"identical indexing" means.

**Check 3, Clearwater PD-D smoke test.** Fits PD-D/M0 and PD-D/M1 on both `mid` cameras through the
production path and compares loss and eta with `PDD_REF`. Under the unfixed code neither camera was
eligible, so those reference numbers could only be obtained with a temporary diagnostic override;
reproducing them without the override is the evidence that the fix, not the override, is what makes the
document usable. Forward injectivity, `admissibility_v2` and inverse reliability are reported alongside.

### Status of the reference numbers

`BEFORE`, `EXPECTED`, `EXPECTED_CANON` and `PDD_REF` are **regression** references: they pin behaviour so
a later edit cannot change it unnoticed. None of them is a scientific expectation or an accuracy claim,
and these PD-D fits are not part of the cross-method benchmark. The PD-D tolerances (`5e-3` on loss,
`5e-7` on eta) are ten times the quantization of the references as quoted, and were fixed before the run
rather than chosen to accommodate its output.

### Provenance

This file and `validate_lattice_real.py` are the durable form of two scripts written under `/tmp` while
the fix was being developed (`val9.py`, the six-camera comparison, and `smoke9.py`, the PD-D smoke test).
The logic is preserved, not re-derived: the first fixed run through `validate_lattice_real.py` reproduced
the earlier `/tmp/val9.json` values field for field on all six cameras, including the canonicalized-line
counts 43, 44, 55, 33, 2 and 37.
