#!/usr/bin/env python3
"""OPT-IN real-data validation of the lattice traversal-canonicalization fix.

This is the durable form of two scripts that were written under /tmp while the fix was being made
(`val9.py`, the six-camera before/after comparison, and `smoke9.py`, the Clearwater PD-D regression
smoke test). Nothing here is new analysis: it is the exact validation workflow, preserved so the fix
can be re-checked later instead of being taken on trust from a transcript.

WHY THIS IS NOT AN ORDINARY UNIT TEST. Every check needs a real `.vsd` document, and those documents
live outside the repository (they are multi-gigabyte field projects in the user's Dropbox). Ordinary CI
therefore cannot run any of it. The choice made here is to keep the checks HONEST and OPT-IN rather
than to weaken them into something that runs everywhere: with no document available the script reports
`DATA UNAVAILABLE` and exits 3, and it never substitutes synthetic data for the real thing.
Synthetic and gauge-invariance coverage that CAN run anywhere lives in `test_lattice_traversal.py`.

REQUIRED LOCAL DATA. Three documents, six cameras:

    pool   <chena>/VidSync Projects/2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd
    8mm    <drift>/2015-09-04-1 Clearwater.vsd
    mid    <drift>/2015-06-22-1 Clearwater.vsd

`<drift>` and `<chena>` are the two project roots. No absolute path is baked into this file. They are
resolved, in order of precedence, from `--drift-dir` / `--chena-dir`, then the environment variables
`VIDSYNC_DRIFT_PROJECTS` / `VIDSYNC_CHENA_PROJECTS`, then the two conventional Dropbox locations on
this machine. Missing documents are skipped and named; they are never silently omitted.

COMMANDS (from tools/pooltest, with ~/.venvs/vidsync/bin/python):

    ~/.venvs/vidsync/bin/python validate_lattice_real.py                      # all three checks
    ~/.venvs/vidsync/bin/python validate_lattice_real.py --check lattice      # six-camera table
    ~/.venvs/vidsync/bin/python validate_lattice_real.py --check permutation  # click-order invariance
    ~/.venvs/vidsync/bin/python validate_lattice_real.py --check pdd          # Clearwater PD-D smoke

    export VIDSYNC_DRIFT_PROJECTS="/path/to/Drift Model Project/VidSync Projects"
    export VIDSYNC_CHENA_PROJECTS="/path/to/Chena Project Synced"

Exit status: 0 every requested check passed; 1 at least one check FAILED; 3 no document was available
so nothing was actually verified. Writing `--json <path>` records the measured values.

WHAT THE REFERENCE NUMBERS ARE. `BEFORE` is the state of the six cameras under the unfixed code, and
`PDD_REF` is the PD-D loss and eta obtained on `2015-06-22-1 Clearwater` when the lattice was indexed
through a temporary diagnostic override. Both are REGRESSION references -- they pin behaviour so a
later edit cannot change it unnoticed -- and neither is a scientific expectation or an accuracy claim.
These fits are not part of the cross-method benchmark.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

import harness_import
import mapmetrics as MM

harness_import.ensure_path()
LT = harness_import.load("lattice")
OB = harness_import.load("objectives")
DS = harness_import.load("downstream")                                        # noqa: F401 (parity)

# Gauge-invariant comparison helpers are shared with the runnable-anywhere regression tests rather than
# duplicated, so the two files cannot drift apart in what "identical indexing" means.
import test_lattice_traversal as TT                                           # noqa: E402

HOME = os.path.expanduser("~")
DEFAULT_DRIFT = os.path.join(HOME, "Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects")
DEFAULT_CHENA = os.path.join(HOME, "Library/CloudStorage/Dropbox/Chena Project Synced")

# key -> (root name, path relative to that root)
DOC_SPECS = {
    "pool": ("chena", "VidSync Projects/2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd"),
    "8mm": ("drift", "2015-09-04-1 Clearwater.vsd"),
    "mid": ("drift", "2015-06-22-1 Clearwater.vsd"),
}
CLIPS = ("Left Camera", "Right Camera")

# The six cameras under the UNFIXED code, measured in the round-8 lattice diagnostic. `mid` is the
# failure the fix addresses: a single line per family per camera clicked against its family-mates put
# 32 and 36 contradictions into a single connected component, which discarded every observation.
BEFORE = {
    "pool/Left": dict(contra=0, dropped=0, comps=1, reliable=1013, dind=1013, elig=True),
    "pool/Right": dict(contra=0, dropped=1, comps=1, reliable=1042, dind=1039, elig=True),
    "8mm/Left": dict(contra=0, dropped=5, comps=16, reliable=587, dind=398, elig=True),
    "8mm/Right": dict(contra=0, dropped=14, comps=4, reliable=408, dind=387, elig=True),
    "mid/Left": dict(contra=32, dropped=0, comps=1, reliable=0, dind=0, elig=False),
    "mid/Right": dict(contra=36, dropped=0, comps=1, reliable=0, dind=0, elig=False),
}

# What the fix is expected to produce, as measured on the first fixed run. The four cameras that already
# worked must be unchanged in every field; only `mid` may move, and only from total failure to full
# recovery. `reliable` and `dind` differ on `mid` because `reliably_indexed` counts every consistently
# indexed observation (340 and 365, i.e. all of them) while `Dind.n` is what survives the unrelated
# `min_inc=2` requirement of the projective dataset (309 and 318). Neither number is a target.
EXPECTED = {
    "pool/Left": dict(contra=0, dropped=0, comps=1, reliable=1013, dind=1013, elig=True),
    "pool/Right": dict(contra=0, dropped=1, comps=1, reliable=1042, dind=1039, elig=True),
    "8mm/Left": dict(contra=0, dropped=5, comps=16, reliable=587, dind=398, elig=True),
    "8mm/Right": dict(contra=0, dropped=14, comps=4, reliable=408, dind=387, elig=True),
    "mid/Left": dict(contra=0, dropped=0, comps=1, reliable=340, dind=309, elig=True),
    "mid/Right": dict(contra=0, dropped=0, comps=1, reliable=365, dind=318, elig=True),
}
# Lines whose stored traversal disagreed with their family reference, per camera. Reported for
# information and pinned here because a change in it would mean the canonicalization itself changed.
EXPECTED_CANON = {"pool/Left": 43, "pool/Right": 44, "8mm/Left": 55, "8mm/Right": 33,
                  "mid/Left": 2, "mid/Right": 37}

PDD_REF = {("Left Camera", "M0"): (271.836, None),
           ("Left Camera", "M1"): (262.274, 0.0053225),
           ("Right Camera", "M0"): (427.310, None),
           ("Right Camera", "M1"): (385.726, 0.0100847)}
# The references above are quoted to 3 and 7 decimals, so they are themselves only known to +-5e-4 and
# +-5e-8. The tolerances are ten times that quantization -- tight enough that any real change in the
# estimator or the indexing would break them, and not chosen after seeing this run's numbers.
PDD_LOSS_TOL = 5e-3
PDD_ETA_TOL = 5e-7


def resolve_roots(args):
    drift = args.drift_dir or os.environ.get("VIDSYNC_DRIFT_PROJECTS") or DEFAULT_DRIFT
    chena = args.chena_dir or os.environ.get("VIDSYNC_CHENA_PROJECTS") or DEFAULT_CHENA
    return {"drift": drift, "chena": chena}


def resolve_docs(args):
    """key -> absolute path, for the documents that exist. Also returns what was missing and why."""
    roots = resolve_roots(args)
    found, missing = {}, {}
    for key, (root, rel) in DOC_SPECS.items():
        p = os.path.join(roots[root], rel)
        if os.path.exists(p):
            found[key] = p
        else:
            missing[key] = p
    return found, missing, roots


def _camera_state(path, clip):
    """The production path, with no diagnostic override: exactly what a caller gets."""
    caps = LT.load_captures(path, clip)
    Dind = OB.Dataset(caps, require_indexed=True, min_inc=2, kappa=3.0)
    s = dict(
        contra=sum(C.notes["index_contradictions"] for C in caps),
        dropped=sum(C.notes["dropped_nonunit_edges"] for C in caps),
        comps=sum(C.notes["n_components"] for C in caps),
        reliable=sum(C.notes["reliably_indexed"] for C in caps),
        dind=int(Dind.n),
        canon=sum(C.notes["n_traversal_canonicalized"] for C in caps),
        nonmono=sum(len(C.notes["nonmonotone_member_order"]) for C in caps),
        degen=sum(len(C.notes.get("degenerate_direction_lines", [])) for C in caps),
        nobs=sum(C.n for C in caps),
        famdir={k: v for C in caps for k, v in C.notes["family_reference_dirs"].items()},
    )
    s["elig"] = bool(s["dind"] >= 20 and s["contra"] == 0)
    return caps, Dind, s


def check_lattice(docs, say):
    """The six-camera before/after comparison. Fails on any departure from EXPECTED."""
    say("=" * 118)
    say("CHECK 1 -- SIX-CAMERA LATTICE STATE, before the fix -> after the fix (production path)")
    say("=" * 118)
    say(f"  {'camera':12} {'contra':>14} {'dropped':>13} {'comps':>11} {'reliable':>15} "
        f"{'Dind.n':>13} {'eligible':>15} {'canon':>6} {'nonMono':>8} {'degen':>6}")
    out, fails = {}, []
    for key in ("pool", "8mm", "mid"):
        if key not in docs:
            say(f"  {key:12} DOCUMENT UNAVAILABLE -- skipped, not assumed")
            continue
        for clip in CLIPS:
            cid = f"{key}/{clip.split()[0]}"
            _, _, s = _camera_state(docs[key], clip)
            b, e = BEFORE[cid], EXPECTED[cid]

            def f(now, was):
                return f"{was}->{now}" + ("" if now == was else " *")

            say(f"  {cid:12} {f(s['contra'], b['contra']):>14} {f(s['dropped'], b['dropped']):>13} "
                f"{f(s['comps'], b['comps']):>11} {f(s['reliable'], b['reliable']):>15} "
                f"{f(s['dind'], b['dind']):>13} {f(s['elig'], b['elig']):>15} "
                f"{s['canon']:6d} {s['nonmono']:8d} {s['degen']:6d}")
            for fld in ("contra", "dropped", "comps", "reliable", "dind", "elig"):
                if s[fld] != e[fld]:
                    fails.append(f"{cid}: {fld} is {s[fld]}, expected {e[fld]}")
            if s["canon"] != EXPECTED_CANON[cid]:
                fails.append(f"{cid}: {s['canon']} lines canonicalized, expected "
                             f"{EXPECTED_CANON[cid]}")
            out[cid] = s
    say("")
    say("  (* marks a change from the unfixed code. canon = lines whose traversal was canonicalized;")
    say("   nonMono = lines whose member order is not monotone in the family projection; degen = lines")
    say("   with no recoverable direction. The last two are recorded, never repaired.)")
    say("")
    say("  family reference directions (deterministic, dominant-coordinate sign, no stored order used)")
    for cid, s in out.items():
        say(f"    {cid:12} " + "  ".join(f"fam{k}=({d[0]:+.4f},{d[1]:+.4f})"
                                        for k, d in sorted(s["famdir"].items())))
    if "mid" in docs:
        say("")
        say("  mid: are ALL observations consistently indexed before any downstream filtering?")
        for clip in CLIPS:
            C = LT.load_captures(docs["mid"], clip)[0]
            ok = np.isfinite(C.rc).all(axis=1)
            say(f"    mid/{clip.split()[0]:6} reliably indexed {int(ok.sum())} of {C.n} "
                f"({'ALL' if ok.all() else 'NOT all'}); components {C.notes['n_components']}; "
                f"contradictions {C.notes['index_contradictions']}")
            if not ok.all():
                fails.append(f"mid/{clip.split()[0]}: only {int(ok.sum())} of {C.n} indexed")
    return out, fails


def check_permutation(docs, say, trials=5, seed=4100):
    """Click direction and record order must not be semantic on any real camera.

    Both nuisance transformations are applied at once: line records are permuted and a random half of
    the lines have their point order reversed. Acceptance, the component partition and the
    gauge-normalized indices must all be identical to the stored-order result.
    """
    say("=" * 118)
    say(f"CHECK 2 -- CLICK-ORDER AND RECORD-ORDER INVARIANCE, {trials} permutations per camera")
    say("=" * 118)
    out, fails = {}, []
    for key in ("pool", "8mm", "mid"):
        if key not in docs:
            say(f"  {key:12} DOCUMENT UNAVAILABLE -- skipped, not assumed")
            continue
        for clip in CLIPS:
            cid = f"{key}/{clip.split()[0]}"
            caps, _, s = _camera_state(docs[key], clip)
            ref = [(TT.signature(C), TT.comp_partition(C), C.notes["index_contradictions"],
                    C.notes["reliably_indexed"]) for C in caps]
            bad = []
            for trial in range(trials):
                caps2 = LT.load_captures(docs[key], clip)
                rg = np.random.default_rng(seed + trial)
                for C2 in caps2:
                    order = list(rg.permutation(len(C2.lines)))
                    C2.lines = [C2.lines[i] for i in order]
                    for ln in C2.lines:
                        if rg.random() < 0.5:
                            ln["members"] = list(reversed(ln["members"]))
                    C2.inc = [[] for _ in range(C2.n)]
                    for li, ln in enumerate(C2.lines):
                        for m in ln["members"]:
                            C2.inc[m].append(li)
                    LT._recover_indices(C2)
                got = [(TT.signature(C), TT.comp_partition(C), C.notes["index_contradictions"],
                        C.notes["reliably_indexed"]) for C in caps2]
                if got != ref:
                    bad.append(trial)
            ok = not bad
            say(f"  {cid:12} {trials} permutations: {'INVARIANT' if ok else 'CHANGED on ' + str(bad)}"
                f"   ({len(caps)} captures, contradictions {s['contra']}, indexed {s['reliable']})")
            if not ok:
                fails.append(f"{cid}: indexing changed under permutation trials {bad}")
            out[cid] = {"trials": trials, "invariant": ok, "failed_trials": bad}
    return out, fails


def check_pdd(docs, say):
    """PD-D on both Clearwater cameras through the ordinary production path.

    Under the unfixed code neither camera was eligible, so these fits could only be obtained with a
    temporary diagnostic override. Reproducing the same loss and eta without the override is the
    evidence that the fix, and not the override, is what makes the document usable.
    """
    say("=" * 118)
    say("CHECK 3 -- PD-D SMOKE TEST on 2015-06-22-1 Clearwater, production path, no override")
    say("=" * 118)
    if "mid" not in docs:
        say("  DOCUMENT UNAVAILABLE -- skipped, not assumed")
        return {}, []
    out, fails = {}, []
    for clip in CLIPS:
        caps, Dind, s = _camera_state(docs["mid"], clip)
        say(f"  {clip}: eligible={s['elig']}  Dind.n={Dind.n} lines={Dind.nline} caps={Dind.ncap} "
            f"canonicalized={s['canon']} lines")
        if not s["elig"]:
            say("    INELIGIBLE -- the fix is not doing what it must")
            fails.append(f"mid/{clip.split()[0]}: ineligible for PD-D")
            continue
        base0 = OB.default_base()
        for model in ("M0", "M1"):
            fr = OB.MODELS[model]
            base = base0.copy()
            base[[j for j in range(14) if j not in set(fr)]] = 0.0
            t0 = time.time()
            wb = OB.fit(Dind, "B", model, base=base.copy(), warm=False, max_nfev=3000, free=fr)
            ev = OB.PDExact(Dind, model)
            res, _ = ev.fit(ev.init_dlt(np.asarray(wb["theta14"], float)))
            th = ev.theta(res.x)
            el = time.time() - t0
            a2 = MM.admissibility_v2(th)
            iv = MM.inverse_reliability(th, n_int=13, n_edge=80, unfavourable=False)
            cert = MM.certify_forward_injective(th, max_cells=800)
            rl, re_ = PDD_REF[(clip, model)]
            loss = float(2 * res.cost)
            dl = loss - rl
            say(f"    PD-D/{model}: status {res.status} nfev {res.nfev} loss {loss:.5f} "
                f"(ref {rl:.3f}, delta {dl:+.5f}) eta {th[13]:+.7f}"
                + (f" (ref {re_:+.7f}, delta {th[13] - re_:+.2e})" if re_ else "")
                + f"  {el:.2f}s")
            say(f"      forward: {cert['verdict']} ({cert['cells_certified']} cells); "
                f"admV2 safe={a2['safe']} plausible={a2['physically_plausible']} "
                f"minDet={a2['min_det']:.4f} minSigma={a2['min_sigma']:.4f} "
                f"expansion={a2['expansion_ratio']:.2f}")
            say(f"      inverse: PDExact failures {ev.C['inverse_failures']}, shipped-inverse failures "
                f"{iv['summary']['shipped_total_failures']}, max round-trip {a2['roundtrip_px']:.2e} px")
            if abs(dl) > PDD_LOSS_TOL:
                fails.append(f"mid/{clip.split()[0]} PD-D/{model}: loss {loss:.5f} vs ref {rl:.3f} "
                             f"(delta {dl:+.5f} exceeds {PDD_LOSS_TOL})")
            if re_ is not None and abs(th[13] - re_) > PDD_ETA_TOL:
                fails.append(f"mid/{clip.split()[0]} PD-D/{model}: eta {th[13]:.7f} vs ref {re_:.7f}")
            out[f"{clip.split()[0]}/{model}"] = {
                "loss": loss, "loss_ref": rl, "loss_delta": dl, "eta": float(th[13]),
                "eta_ref": re_, "status": int(res.status), "nfev": int(res.nfev),
                "seconds": el, "forward_verdict": cert["verdict"], "safe": bool(a2["safe"]),
                "dind_n": int(Dind.n)}
    return out, fails


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", default="all",
                    choices=("all", "lattice", "permutation", "pdd"))
    ap.add_argument("--drift-dir", default=None, help="root holding the Drift Model .vsd projects")
    ap.add_argument("--chena-dir", default=None, help="root holding the Chena .vsd projects")
    ap.add_argument("--trials", type=int, default=5, help="permutation trials per camera")
    ap.add_argument("--json", default=None, help="write measured values here")
    args = ap.parse_args()

    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    docs, missing, roots = resolve_docs(args)
    say("REAL-DATA VALIDATION OF THE LATTICE TRAVERSAL-CANONICALIZATION FIX")
    say(f"  drift root {roots['drift']}")
    say(f"  chena root {roots['chena']}")
    for key in DOC_SPECS:
        say(f"  {key:6} {'FOUND    ' if key in docs else 'MISSING  '}"
            f"{docs.get(key, missing.get(key))}")
    if not docs:
        say("\nDATA UNAVAILABLE: no document could be found, so NOTHING was verified. Set")
        say("VIDSYNC_DRIFT_PROJECTS / VIDSYNC_CHENA_PROJECTS or pass --drift-dir / --chena-dir.")
        return 3
    if missing:
        say(f"\n  NOTE: {len(missing)} document(s) missing; their checks are skipped and named above,")
        say("  not inferred from the others.")
    say("")

    R, fails = {}, []
    if args.check in ("all", "lattice"):
        R["lattice"], f = check_lattice(docs, say)
        fails += f
        say("")
    if args.check in ("all", "permutation"):
        R["permutation"], f = check_permutation(docs, say, trials=args.trials)
        fails += f
        say("")
    if args.check in ("all", "pdd"):
        R["pdd"], f = check_pdd(docs, say)
        fails += f
        say("")

    say("=" * 118)
    if fails:
        say(f"VALIDATION FAILED -- {len(fails)} problem(s)")
        for m in fails:
            say(f"  {m}")
    else:
        say("VALIDATION PASSED -- every requested check on every available document")
    say(f"  documents checked {sorted(docs)}; skipped {sorted(missing)}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"roots": roots, "documents": docs, "missing": missing,
                       "results": R, "failures": fails,
                       "tolerances": {"pdd_loss": PDD_LOSS_TOL, "pdd_eta": PDD_ETA_TOL}}, fh, indent=1)
        say(f"  wrote {args.json}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
