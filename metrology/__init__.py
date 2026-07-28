"""Measurement engine for LLM evaluation.

Modules arrive when an experiment needs them, per the build order in PLAN.md: `schema`,
`paired`, `power`, `multiplicity`, `reporting`, and `cards` in Phase 2 (driven by Experiment 1),
then `estimators` and `certificate` in Phase 5 (driven by Experiment 2). No module is written
before it has a consumer.

Import boundary: standard library, numpy, and scipy only, so the engine stays portable to
pyodide. `make import-check` enforces this.
"""

from __future__ import annotations

import sys

__all__ = ["MINIMUM_PYTHON", "__version__"]

#: Pre-release. The version stays at 0.0.0 until the validation bar in PLAN.md is cleared.
__version__ = "0.0.0"

#: The engine uses `zip(strict=)` and 3.11-era typing. An older interpreter fails in obscure
#: places (an AttributeError inside a checker script, a TypeError deep in a loader), so it is
#: rejected here where the message can say what is actually wrong.
MINIMUM_PYTHON: tuple[int, int] = (3, 11)

if sys.version_info[:2] < MINIMUM_PYTHON:
    running = ".".join(str(part) for part in sys.version_info[:3])
    required = ".".join(str(part) for part in MINIMUM_PYTHON)
    raise RuntimeError(
        f"metrology requires Python {required} or newer, but this interpreter is {running} "
        f"({sys.executable}). Run with an explicit interpreter, for example "
        f"`make test PYTHON=python3.11`."
    )
