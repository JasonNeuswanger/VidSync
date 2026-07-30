# Provenance of the C++ oracle binaries

Established 2026-07-29, in response to the independent audit finding that `plumb_oracle`'s claim of
GSL 2.6 was documented in a source comment but never verified. All commands below are read-only. No
dependency was downloaded, installed, substituted or rebuilt to produce this record.

## Verdict

**`plumb_oracle`'s GSL 2.6 provenance IS established**, not by trusting the build comment but by
byte-level code identity against the archive the production app links. Exact production
plumbline-trajectory parity is therefore **resolved**, with one residual caveat recorded below.

**Separately: `tri_oracle` and `oracle` are linked against GSL 2.7.1, not 2.6.** This was not
previously recorded and it qualifies — though it does not by itself invalidate — the downstream
Nelder-Mead parity result. See "What this does NOT establish".

## Why the comment alone was not evidence

`plumb_oracle.cpp:11-12` records

    clang++ -O2 -std=c++17 plumb_oracle.cpp -o plumb_oracle \
      -I../../gsl-2.6-universal ../../gsl-2.6-universal/libgsl.a -framework Accelerate

The archive is named as a positional input, so the binary is statically linked and `otool -L` shows no
`libgsl` at all — which is exactly what a *wrong* build would also show, because `/usr/local` ships a
static `libgsl.a` too. A stray `-lgsl` would have produced a binary that looked identical by every
cheap check. So the following were tried and all failed to discriminate: `gsl_multimin.h` and
`gsl_vector.h` are byte-identical between the two versions; the embedded assertion-path strings are
identical; and no GSL version string is present in the binary at all, because `version.o` is never
pulled in (nothing references `gsl_version`).

## The decisive test: `simplex2.o` symbol composition

GSL restructured `multimin/simplex2.c` between 2.6 and 2.7.1, so the two archives' `simplex2.o`
members define different helper functions. Verified with `nm -arch arm64` on each archive, restricted
to its `simplex2.o` member:

| Archive | `simplex2.o` defines |
|---|---|
| `gsl-2.6-universal/libgsl.a` (GSL 2.6) | `_nmsimplex_iterate`, `_update_point` |
| `/usr/local/lib/libgsl.a` (GSL 2.7.1) | `_nmsimplex_iterate`, `_update_point`, `_compute_center`, `_compute_size`, `_contract_by_best`, `_ran_unif` |

The four symbols `_compute_center`, `_compute_size`, `_contract_by_best` and `_ran_unif` exist **only**
in 2.7.1. `nm -arch arm64 tools/pooltest/plumb_oracle` defines `_nmsimplex_iterate` and
`_update_point` and **none of those four**. The binary also references `___sincos_stret`, which the 2.6
member uses and the 2.7.1 member does not (2.7.1 calls `_sin` and `_cos` separately).

`plumb_oracle`'s Nelder-Mead code therefore came from `gsl-2.6-universal/libgsl.a` — the same archive
production links. Reproduce with:

    nm -arch arm64 tools/pooltest/plumb_oracle | grep -E '_(compute_center|compute_size|contract_by_best|ran_unif)$'   # must print nothing
    nm -arch arm64 tools/pooltest/plumb_oracle | grep -E '_(update_point|nmsimplex_iterate)$'                          # must print both

## Recorded provenance

| Item | Value |
|---|---|
| GSL version | 2.6, per `gsl-2.6-universal/gsl/gsl_version.h` (`GSL_VERSION "2.6"`, `GSL_MINOR_VERSION 6`) |
| GSL path | `gsl-2.6-universal/libgsl.a`, in-repo, universal x86_64 + arm64, 29,420,112 bytes |
| GSL archive SHA-256 | `a7cef7d503eb20b3d98264826b6a9a92f36fcc04f0b50cd23a057b68703a43cb` |
| GSL archive in git | tracked as a plain blob; `git check-attr filter` reports `unspecified`, so it is **not** LFS and a fresh clone materialises it |
| Production link | `VidSync.xcodeproj/project.pbxproj` references `gsl-2.6-universal/libgsl.a` in a Frameworks build phase and adds `$(PROJECT_DIR)/gsl-2.6-universal` to `LIBRARY_SEARCH_PATHS` for both configurations; `gslcblas` appears nowhere, so cblas comes from Accelerate |
| `plumb_oracle.cpp` SHA-256 | `80e488a8924711ba3926c7c14dc850033e5dd44443f419693a6c963b57d1b105` |
| `plumb_oracle` SHA-256 | `98e6cbdeca4eb889bac898b83da2b0e777a30ed0aadbd1a7508a04a48fccbfb9` |
| Linked libraries | Accelerate, `libc++.1.dylib`, `libSystem.B.dylib` — **no** `libgsl`, consistent with static linking |
| Compiler present now | Apple clang 17.0.0 (clang-1700.6.4.2), target arm64-apple-darwin25.4.0 |
| GSL API used | Nelder-Mead only: `gsl_multimin_fminimizer_{alloc,set,iterate,free,size}`, `nmsimplex2`, `gsl_multimin_test_size`, `gsl_vector_{alloc,free,get,set}` |

`plumb_oracle.cpp` predefines `__GSL_CBLAS_H__` before including `<gsl/gsl_multimin.h>` so the
`CBLAS_*` enums come from Accelerate rather than GSL's own cblas headers. That is mandatory rather than
cosmetic: the vendored 2.6 archive ships no `libgslcblas`. It is the same arrangement `VSCalibration.mm`
compiles under.

### Clean rebuild

    cd tools/pooltest
    clang++ -O2 -std=c++17 plumb_oracle.cpp -o plumb_oracle \
      -I../../gsl-2.6-universal ../../gsl-2.6-universal/libgsl.a -framework Accelerate
    nm -arch arm64 plumb_oracle | grep -E '_(compute_center|contract_by_best|ran_unif)$'   # must print nothing

The final `nm` check is the point: it is the only step that distinguishes a correct build from one that
silently picked up `/usr/local`'s 2.7.1. Run it after every rebuild.

## Binary-to-source correspondence

There is no embedded source hash, no build-id and no `-frecord-command-line` data, so the binary cannot
be tied to its source cryptographically. The strongest available check was done instead: the worktree
source differs from the staged source by 163 added lines, and the three format strings that exist only
in the worktree version (`ETASCALE %.17g`, `NFREE %d`, `SOLVEDETA %.17g`) are all present in the
binary, as is the worktree-only local symbol `_ZL10maskedCost`. All 17 worktree format strings appear.
The binary corresponds to the current worktree source, not the staged one. This is strong evidence, not
a guarantee.

## What this does NOT establish

1. **`tri_oracle` and `oracle` link GSL 2.7.1, not 2.6.** `otool -L tri_oracle` shows
   `/usr/local/lib/libgsl.27.dylib` and `/usr/local/lib/libgslcblas.0.dylib`; `oracle` shows
   `libgsl.27.dylib`. Their build comments record `-L/usr/local/lib -lgsl -lgslcblas`.
   `/usr/local/include/gsl/gsl_version.h` and `/usr/local/lib/pkgconfig/gsl.pc` both say 2.7.1, and
   `libgsl.dylib -> libgsl.27.dylib`.

   This matters because `CALIBRATION_REFERENCE_NOTES.md` states that GSL version is load-bearing for
   `nmsimplex2` trajectories, and separately describes `tri_oracle.cpp` as replaying
   `VSPoint.m:147-215` "exactly: GSL nmsimplex2". By the notes' own criterion, `tri_oracle`'s
   `nmsimplex2` is the 2.7.1 implementation — a materially different code path from the 2.6 one
   production uses, as the symbol table above shows.

   What is still true: `downstream_parity.py` measures production-NM (via `tri_oracle`) against the
   harness LM and finds a worst 3D difference of 9.6e-6 mm and a worst length difference of 2.9e-6 mm
   across 149 points and 6 candidates. That agreement is real and is 4 orders of magnitude below the
   0.1-1 mm model contrasts. But it is agreement with **2.7.1's** `nmsimplex2`, so it does not by
   itself certify bit-level agreement with production's 2.6 triangulation. Rebuilding `tri_oracle`
   against the vendored 2.6 archive would settle it; that was not done in this round because it was
   out of scope. `oracle` uses `hybrids` (a root finder) rather than `nmsimplex2`, so whether 2.6
   versus 2.7.1 moves that solve is a separate untested question.

2. **The vendored archive's own upstream origin is undocumented.** There is no `gsl*.tar*` anywhere in
   the repository, no configure log, no upstream checksum, and no note recording which GSL 2.6 tarball
   it was built from or how the universal slices were produced. Its "2.6" identity rests entirely on
   the co-vendored `gsl_version.h`. Mitigating this: the archive is committed to git, so the *link
   step* is reproducible from a clone even though the archive's provenance is not.

3. **The oracle binaries are untracked.** `git status` shows `?? tools/pooltest/plumb_oracle`,
   `?? tools/pooltest/oracle`, `?? tools/pooltest/tri_oracle`. They exist only on this disk; a fresh
   clone must rebuild them. There is no build script or Makefile — the compile lines exist only as
   comments in the three `.cpp` files, and `HARNESS_REPOSITORY_PLAN.md:47` already lists "a build
   script" as outstanding.

4. **The compiler that produced the current binaries is not recorded.** Apple clang 17.0.0 is what is
   installed now; nothing in the binary confirms it was the one used.

## Legacy-B conclusions that depend on plumbline-trajectory parity

Now supported, given the resolution above: everything resting on `plumb_oracle` reproducing
production's masked Nelder-Mead plumbline fit — the APP13 replay agreeing to 1e-14 px per-point and
9e-6 px frame-wide, the masked/eta extension replaying APP13 at the same iteration counts
(3902 / 3646), and the legacy-B fits in `stab_fits.py` that are described as using "the exact
production GSL 2.6 Nelder-Mead".

Still qualified: any claim that the **triangulation** stage is bit-faithful to production, because
that path runs through `tri_oracle` at GSL 2.7.1. Metric agreement is established to ~1e-5 mm;
bit-level trajectory identity is not.
