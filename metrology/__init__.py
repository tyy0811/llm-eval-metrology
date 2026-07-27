"""Measurement engine for LLM evaluation.

This package is intentionally empty at Phase 0. Modules arrive when an experiment needs them,
per the build order in PLAN.md: `schema`, `paired`, `power`, `multiplicity`, `reporting`, and
`cards` in Phase 2 (driven by Experiment 1), then `estimators` and `certificate` in Phase 5
(driven by Experiment 2). No module is written before it has a consumer.

Import boundary: standard library, numpy, and scipy only, so the engine stays portable to
pyodide. `make import-check` enforces this.
"""

from __future__ import annotations

__all__ = ["__version__"]

#: Pre-release. The version stays at 0.0.0 until the validation bar in PLAN.md is cleared.
__version__ = "0.0.0"
