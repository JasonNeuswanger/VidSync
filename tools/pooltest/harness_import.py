#!/usr/bin/env python3
"""ONE instance per harness module, shared by every importer.

WHY THIS EXISTS. Most scripts here carry a private copy of

    def L(n):
        s = importlib.util.spec_from_file_location(n, os.path.join(HERE, n + ".py"))
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

`spec_from_file_location` + `exec_module` deliberately bypasses `sys.modules`, so every call builds a
NEW module object. Two scripts that both `L("parity")` get two unrelated `parity` modules, and a
monkeypatch applied to one is invisible in the other. That turned import order into a scientific
variable: `downstream_parity.py` observed `parity.undistort` already patched only because it reached
`parity` through `fisheye_knownlength_analysis`'s instance, while a script that loaded `parity`
directly saw the unpatched 13-parameter function and silently dropped eta.

`load()` uses the ordinary import machinery instead, so `sys.modules` guarantees exactly one instance
of each module process-wide, and results cannot depend on who imported what first. The directory is
appended (not prepended) to `sys.path` so it can never shadow the standard library or site-packages;
none of the harness module names collide with an installed package.

Prefer plain `import lattice` in new code. `load()` exists for the many existing modules whose own
`L()` is being replaced in place.

Run with ~/.venvs/vidsync/bin/python.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def ensure_path():
    """Make the harness directory importable, without shadowing anything installed."""
    if HERE not in sys.path:
        sys.path.append(HERE)
    return HERE


def load(name):
    """The single shared instance of harness module `name`."""
    ensure_path()
    return importlib.import_module(name)


def instance_count(name):
    """Diagnostic: how many distinct module objects for `name` this process is holding.

    With `load()` everywhere this is always 0 or 1. A private `L()` elsewhere does not register in
    `sys.modules` at all, so this cannot see those; it exists to assert that the shared path is used.
    """
    return 1 if name in sys.modules else 0
