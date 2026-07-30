# `xdoc_objectives.json` is STALE and SUPERSEDED — kept as evidence, do not quote it

**Superseded by:** `xdoc_objectives_full.json` (document scope `full`, `manifest.complete: true`).

## What this file is

`xdoc_objectives.json` (51,163 bytes, written 2026-07-29 10:01) is the artifact left behind by the
defect the independent audit found on 2026-07-29. A `--docs pool` run wrote to the same unqualified
filename that the full three-document run used, destroying the complete cross-document artifact and
replacing it with a **pool-only** one that carried nothing to say it was partial. Its contents are:

    documents:    ['pool']                     <- only one of the three
    known_length: pool/vsd nodes, pool/Cal A (XML nodes), pool/Cal B (XML nodes)
    manifest:     none at all

Any summary that read this file between 10:01 and the fix was reading one document's worth of a
three-document claim, and had no way to detect that.

It also contains the capped SD-D fits that were being reported as results: `pool Left SD-D/M0`,
`pool Right SD-D/M0` and `pool Right SD-D/M1`, all at `nfev = 1200` with `status = 0` (SciPy's
"maximum number of function evaluations reached", which is not a convergence code).

## Why it has been kept

It is the primary evidence for both defects, and `test_fitvalidity.py` replays the real fit statuses
recorded in it to prove those exact candidates are now excluded. It has deliberately **not** been
deleted, moved or overwritten. It is not in git (`analysis-output/` is untracked), so preserving it in
place is the only way to preserve it at all.

## What to use instead

| want | read |
|---|---|
| cross-document candidate tables | `xdoc_objectives_full.json` |
| a deliberate single-document run | `xdoc_objectives_pool.json`, `_8mm.json`, `_mid.json` — each scope gets its own name |
| an interrupted or failed run | `xdoc_objectives_<scope>_partial.json`, always with `complete: false` |

Every new artifact carries a `manifest` block: schema version, script, document scope requested and
completed, per-document SHA-256 under a safe document key, calibration-node source, objective versions,
authoritative source-file hashes, git commit plus a dirty flag, interpreter and library versions, the
reproduction command, start/end times and runtime, and a fit-validity record for every candidate.

Check before trusting any artifact:

    ~/.venvs/vidsync/bin/python -c "import json,sys; m=json.load(open(sys.argv[1]))['manifest']; \
      print(m['analysis'], m['document_scope'], 'complete=' + str(m['complete']), \
            m['completed_documents'])" analysis-output/xdoc_objectives_full.json

A file with no `manifest` key predates the fix and its scope cannot be established from the file.

## Regenerating

    cd tools/pooltest
    ~/.venvs/vidsync/bin/python xdoc_objectives.py --docs pool 8mm mid    # ~211 s -> _full.json
