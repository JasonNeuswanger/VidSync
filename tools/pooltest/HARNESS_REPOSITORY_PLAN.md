# Preserving the offline validation harness in the VidSync repository

**STATUS: PLANNING ARTIFACT ONLY.** Nothing has been moved, renamed, packaged, ignored, or added to
CI. No `AGENTS.md` has been written. This note records the measured current state and recommends a
direction; every concrete change below is deferred.

## 1. Measured current state

- `tools/pooltest/` holds **78 Python files, 24,532 lines**, plus three C++ oracles
  (`oracle.cpp`, `plumb_oracle.cpp`, `tri_oracle.cpp`) and their compiled binaries.
- **86 files tracked, 51 untracked.** The untracked set is almost entirely
  `analysis-output/` (48 files, 4.9 MB of JSON/log/CSV/PNG) plus the three compiled binaries.
- **`analysis-output/` is neither tracked nor ignored.** `git check-ignore` reports no rule. A single
  `git add -A` would commit 4.9 MB of generated artifacts. The compiled `oracle`, `plumb_oracle` and
  `tri_oracle` binaries are in the same position. There is already a precedent for handling this:
  `.gitignore` ignores `tools/chessboard-harness/harness` as a built product.
- **47 of 78 Python files contain hard-coded absolute paths** (`/Users/jason/...`), spanning two
  distinct Dropbox roots — `Dropbox/Drift Model Project/VidSync Projects` and
  `Dropbox/Chena Project Synced/VidSync Projects` — plus a Papers directory for the pool-test Cal A/B
  XML. No document data is committed, and no `.vsd` or `.xml` is tracked anywhere in the repo.
- **Two test files exist**, `test_gate.py` and `test_knownlength.py`. There is no runner, no CI wiring,
  and no fixture directory.
- Dependencies: numpy, scipy, matplotlib for Python; the C++ oracles need **GSL** (found at
  `/usr/local`, not the Homebrew ARM prefix) and Apple's **Accelerate** framework. The GSL/Accelerate
  cblas header collision is worked around by pre-defining `__GSL_CBLAS_H__`, which is macOS-specific
  knowledge encoded in three places.
- Module loading is done by an `importlib.util.spec_from_file_location` helper named `L()`, duplicated
  verbatim in nearly every script. A consequence bit me this round: each `L("lattice")` call creates a
  **separate module instance**, so patching one script's `LT` does not affect another's. That is a
  portability and correctness hazard, not just untidiness.

## 2. Intended role

Internal scientific validation and regression harness for the geometry: production-parity testing,
objective and model experimentation, known-length and synthetic validation, and the reference record
behind `CALIBRATION_REFERENCE_NOTES.md`. **Not shipped in the end-user application bundle** and not on
any user-facing code path. It is a developer and agent tool that must remain runnable years from now by
someone who did not write it.

## 3. Proposed layout

Seven roles, currently intermixed in one flat directory:

| Role | Content | Notes |
|---|---|---|
| Reusable geometry and objectives | `lattice.py`, `objectives.py`, `downstream.py`, `fitter.py`, `nodes.py` | the authoritative modules; changes here need tests |
| Production-parity oracles | `oracle.cpp`, `plumb_oracle.cpp`, `tri_oracle.cpp` + a build script | macOS-only by construction |
| Document/data loaders | `knownlength.py`, `stage2.py`, `jacweight.py` | the only code that touches `.vsd` files |
| Synthetic fixtures | (does not exist yet) | needed for CI |
| Regression tests | `test_gate.py`, `test_knownlength.py` + new | no runner today |
| Round-specific analysis scripts | the ~60 remaining one-off scripts | historical record, frozen |
| Generated outputs | `analysis-output/` | ignored by default |

The most valuable separation is the last-but-one: distinguishing the handful of load-bearing modules
from the large tail of frozen round scripts. Today `obj_round1.py`, `round9a.py`, `parity_step5.py` and
`lattice.py` sit side by side with equal apparent authority, and a newcomer cannot tell which are
authoritative. That ambiguity is what an `AGENTS.md` mostly needs to resolve.

## 4. Data policy

Never commit `.vsd` documents, exported XML, or clicked coordinate data without explicit approval.
These are unpublished research data containing field-site information, and the pool-test XML alone is
2.4 MB per calibration.

Instead: a manifest naming each reference document, its SHA-256, its stored world unit, its expected
measurement counts, and a short description, with the path supplied by the user through configuration
or environment. Scripts should fail with a clear message naming the missing document and its expected
hash rather than a `FileNotFoundError` deep in a loader. Small synthetic or sanitised fixtures should
be committed so that the objective algebra, the lattice validator, the inverse, the analytic Jacobian,
and the units handling can all be tested with no private data present.

`analysis-output/` should be ignored by default. Specific artifacts that a note in
`CALIBRATION_REFERENCE_NOTES.md` depends on could be promoted to a small `reference-artifacts/`
directory by explicit choice, so that a claim in the notes remains checkable.

## 5. Portability

Concrete hazards, each already observed in this harness:

- **Absolute paths in 47 files.** Move to one configuration module resolving a small set of document
  keys, seeded by environment variable or a git-ignored local config, with the manifest above as the
  contract. Two different Dropbox roots are already in play, so a single `DM` constant will not do.
- **Monkeypatching.** `fisheye_knownlength_analysis.py:84` reassigns `parity.undistort` at import time,
  and that side effect was the only reason eta reached measurement sightlines. This round replaced it
  with explicit injection in `downstream.py`, where the map is bound to the camera at
  `build_calibration` time. The general rule worth adopting: **model choice travels as an argument or
  an attribute of the object it belongs to, never as module state.**
- **Duplicated `L()` loaders creating distinct module instances.** Real package imports would remove a
  whole class of aliasing bug.
- **Undocumented virtual environment.** Every script says "Run with `~/.venvs/vidsync/bin/python`" but
  nothing records what is in it. A requirements or lock file is needed.
- **Platform assumptions leaking into Python.** The GSL prefix, the Accelerate framework, and the
  cblas-guard trick are macOS-specific and belong in the oracle build script, not spread across
  scripts.

**Which parity tests genuinely need macOS:** anything comparing against production numerics — the
Accelerate LAPACK call sequences in `oracle.cpp`, the GSL `hybrids` refraction root solve, the GSL
`nmsimplex2` triangulation replay in `tri_oracle.cpp`, and any Core Data/sqlite read of a real `.vsd`.
Everything else can run on ordinary Python CI: the distortion map and its analytic Jacobian, the
lattice validator, the Delaunay quadrature, the PD/SD objective algebra, unit and scale handling,
loader validation against synthetic fixtures, and the M1-reduces-to-M0 invariant. That split is
favourable — the portable half covers most of the code that changes.

## 6. Reproducibility

- Pinned dependency specification plus the recorded interpreter.
- Deterministic seeds everywhere; this round's scripts already pass explicit `default_rng(...)` seeds.
- **Objective and model version identifiers** emitted into every machine-readable output, so a stored
  result can be traced to the code that produced it. `DistortionMap.meta()` is a first step: it reports
  name, model, eta, centre, source and the implementation chain.
- Machine-readable JSON alongside every human-readable log, which the recent scripts already do.
- **Three runtime tiers:** a smoke tier of seconds on synthetic fixtures for CI; a focused regression
  tier of a few minutes on one real document; and a full local validation tier of tens of minutes
  across all documents. This round is a natural fit — `downstream_parity.py` is 3 s, the closure round
  4 s, the cross-document run 222 s.
- Checksums for external documents, and **explicit tolerances with a stated reason**. This round showed
  why the reason matters: a single blanket 1e-6 gate wrongly failed the injection parity, because
  deterministic arithmetic stages must agree at round-off (measured 9e-13) while iterative solver
  stages have a convergence-noise floor (measured 4e-6 mm). Those need separate, separately justified
  thresholds.

## 7. Proposed `AGENTS.md` outline

Not written here. Sections it should carry:

1. Purpose and scope; explicitly not shipped, explicitly not production.
2. Authoritative modules versus frozen round scripts, named.
3. Production-parity invariants: which oracle reproduces which production routine, at which line.
4. Model nomenclature: M0, M1, eta, B, PD-D, PD-U, SD-D, ED, and what each objective's loss means.
5. Prohibited shortcuts: no monkeypatching, no module-level model state, no reusing stored downstream
   geometry for a candidate, no pseudoinverse hiding a rank failure, no forcing PD onto an unvalidated
   lattice.
6. Candidate-map injection rules: the map travels with the camera; a 13-parameter map is an explicit
   eta = 0 map, never a separate code path.
7. No silent held-parameter contamination: reduced models zero their held entries, except when holding
   a parameter at a nonzero value for a profile, which is a distinct and labelled case.
8. Objective-specific residual interpretation: losses are not comparable across objectives, and a
   residual reported without its objective is uninterpretable.
9. Treatment of dependent measurements: cluster by timecode and placement; pair counts are not sample
   sizes.
10. Data privacy: no documents, no clicked coordinates, manifest and hashes only.
11. Required tests before touching geometry code, by tier.
12. Runtime expectations and per-fit ceilings.
13. When a finding may enter `CALIBRATION_REFERENCE_NOTES.md`: verified numbers only, with the
    reproduction command, and design proposals kept in separate clearly-labelled files.

## 8. Near-term decisions worth making now

Cheap now, expensive to retrofit:

1. **Explicit distortion-map injection** — done this round in `downstream.py`. Keep it; do not reinstate
   the patch. The `cam["dmap"]` binding also makes the wrong-camera-map error unrepresentable, which is
   worth preserving deliberately.
2. **Add `tools/pooltest/analysis-output/` and the compiled oracle binaries to `.gitignore`.** This is
   the single highest-value one-line change and prevents an accidental 4.9 MB commit.
3. **Stable command-line interfaces.** The recent scripts already take `--outdir` and document
   selectors; keep that shape so a runner can drive them.
4. **Central configuration of external document paths**, even as a thin module that the 47 offenders
   can adopt incrementally.
5. **Separate reusable modules from round scripts** at least by naming convention, before the tail grows
   further.
6. **Preserve detector lattice indices and unique observation identity in future exports.** Independent
   of the harness, this is what would let `lattice.py` stop inferring indices from an adjacency graph —
   the step that failed outright on `2015-06-22-1 Clearwater` this round, with 32 and 36 index
   contradictions and zero indexed observations. See `NON_LATTICE_FALLBACK_DESIGN.md`.
7. **Version objectives and serialize solver provenance**, so that a stored calibration records which
   objective produced it and a residual is never reported bare.
