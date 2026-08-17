"""Test configuration: make the repo root and `scripts/` importable."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

for path in (REPO_ROOT, SCRIPTS_DIR):
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)

#: Every name `pair_display_label` must refuse. One set, imported by both
#: `test_reporting.py::TestPairDisplayLabel` (the isolation test, against `pair_display_label`
#: directly) and `test_cards.py::TestNonCanonicalNameIsNotSilentlyRendered` (the renderer-level
#: test, against `render_card`). A case added here is covered at both levels automatically; a
#: case added to only one test's own local list would not be, which is exactly how a
#: rank_-prefixed but malformed name (`rank_3_vs_`) escaped a fallback tuned to the renderer
#: test's single prior example (`baseline_vs_rank_1`, which does not start with `rank_`).
MALFORMED_PAIR_NAMES = (
    "rank_3_vs_",
    "rank_a_vs_b",
    "3_vs_4",
    "",
    "Ranks 3 and 4",
    "rank_3",
    "baseline_vs_rank_1",
)
