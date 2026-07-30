"""The README's authored prose is checked against the repo's actual state.

Three of this project's defects were correct code with a false sentence attached
(D3.3). These are the exact stale strings the T3.3 spec section 8 table names,
asserted absent for as long as committed results exist.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
RESULTS = REPO_ROOT / "experiments" / "swebench" / "results" / "results.json"

STALE_CLAIMS = (
    "No results exist yet.",
    "This repo is at Phase 0 (bootstrap)",
    "There is no engine code, no data, and",
    "before that experiment's data exists",
    "None has run.",
    "fails loudly until an experiment produces results",
    "This repo ships derived label tables",
    "before its data is fetched",
)


class TestReadmeTruth:
    def test_results_exist_so_the_sweep_is_live(self) -> None:
        assert RESULTS.is_file()

    def test_no_stale_claim_survives(self) -> None:
        text = README.read_text(encoding="utf-8")
        for claim in STALE_CLAIMS:
            assert claim not in text, f"stale claim in README: {claim!r}"

    def test_the_marker_pair_is_present_exactly_once_and_ordered(self) -> None:
        text = README.read_text(encoding="utf-8")
        assert text.count("<!-- findings:start -->") == 1
        assert text.count("<!-- findings:end -->") == 1
        assert text.index("<!-- findings:start -->") < text.index("<!-- findings:end -->")

    def test_the_provenance_wording_is_the_d3_form(self) -> None:
        """PREREG D3 replaced "before any data was fetched" with the narrower claim,
        wherever this experiment's provenance is described. The README is such a place."""
        text = README.read_text(encoding="utf-8")
        assert "after structural recon" in text
