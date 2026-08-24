"""Test configuration: make the repo root and `scripts/` importable."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

for path in (REPO_ROOT, SCRIPTS_DIR):
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)

from metrology.reporting import PlainLanguageInputs, plain_language_finding  # noqa: E402


def load_module(name: str, path: Path):
    """Load a script under experiments/ or scripts/ as an importable module.

    Registered in sys.modules under `name` before executing, so dataclasses in the loaded
    module can resolve forward-referenced annotations through sys.modules.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def plain_language_stub(family_size: int) -> dict:
    """A self-consistent plain-language block for a family card fixture with this many
    pairs. family_card_json takes a completed block rather than building one (D3.4), so
    every caller must supply one. A single constant block shared across fixtures whose
    families differ would say "0 of 19" and "top 20" beside a family that actually has 1
    pair: nothing checks that today, but it is internally contradictory data sitting in a
    fixture, and the cheapest way to make Task 7's consistency rules pass on a fixture like
    that would be to weaken the rule rather than fix the fixture. board_size is family_size
    plus one, the same relationship the real registered board has.
    """
    return plain_language_finding(
        PlainLanguageInputs(
            board_size=family_size + 1,
            family_size=family_size,
            n_items=500,
            distinguishable_count=0,
            largest_lead=7,
            opening_lead=10,
            needs_per_instance_data=False,
        )
    )


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
