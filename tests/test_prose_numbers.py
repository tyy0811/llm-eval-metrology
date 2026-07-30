"""The D1.8 membership check: every numeral in running prose is a corpus rendering.

The checker module is imported directly (conftest puts scripts/ on the path) so the
controls run the real tokenizer, not a reimplementation.
"""

from __future__ import annotations

from pathlib import Path

import check_prose_numbers as checker

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestTokenizer:
    def violations(self, text: str) -> list[str]:
        return checker.check_text(text, checker.build_context(REPO_ROOT))

    def test_clean_corpus_figures_pass(self) -> None:
        assert self.violations("The floor is 10 and the largest gap is 7.") == []

    def test_a_fabricated_figure_fails(self) -> None:
        assert self.violations("The improvement was 42.7 points.") != []

    def test_generic_rounding_collisions_do_not_pass(self) -> None:
        """0 and 1 pass only as integer members, never via a rounded float."""
        assert self.violations("exactly 0 of 19") == []
        assert self.violations("a rate of 0.9573 was seen") != []

    def test_percentage_scaling_is_rejected(self) -> None:
        assert self.violations("discordance of 7.2 percent") != []

    def test_bare_numeric_code_span_is_rejected(self) -> None:
        assert self.violations("the value `79.2` appears") != []

    def test_identifier_spans_do_not_launder(self) -> None:
        assert self.violations("set `p=0.123` in the config") != []

    def test_untracked_path_spans_are_scanned(self) -> None:
        assert self.violations("see `docs/fake999.md` for details") != []

    def test_tracked_path_spans_are_exempt(self) -> None:
        assert self.violations("see `docs/DECISIONS.md` for details") == []

    def test_undeclared_make_target_fails(self) -> None:
        assert self.violations("run `make solve-everything-42`") != []

    def test_system_name_spans_must_be_real(self) -> None:
        good = "`20251215_livesweagent_claude-opus-4-5` leads"
        bad = "`20991231_fake_agent-9000` leads"
        assert self.violations(good) == []
        assert self.violations(bad) != []

    def test_labels_absorb_bare_integers_but_never_decimals(self) -> None:
        """0.072 is deliberately not used here: it is the genuine discordance_rate
        rendering for two committed pairs (36 of 500), so it would pass membership
        regardless of label absorption and the assertion would prove nothing about
        the "never decimals" restriction. 0.618 is not a corpus rendering."""
        assert self.violations("Phase 4 and Experiment 2 and item 6 and T3.5 and D2.7") == []
        assert self.violations("Phase 0.618 looked plausible") != []

    def test_rank_is_not_a_label(self) -> None:
        assert self.violations("rank 4 sits above rank 5") == []
        assert self.violations("rank 999 does not exist") != []

    def test_dates_hashes_versions_are_atomic(self) -> None:
        text = "pinned 2026-07-27 at 2f15350cd32becc4569e0d826361048555b605c0, needs 3.11.15"
        assert self.violations(text) == []

    def test_a_ten_digit_integer_is_not_a_hash(self) -> None:
        """The seed 2026072700 is all digits; the hex rule demands a letter."""
        assert self.violations("we used 2026072700 as the seed") == []
        assert self.violations("we saw 4444444444 events") != []

    def test_version_needs_three_components(self) -> None:
        """74.4 is two components and must NOT hide behind the version rule; it
        passes only because it is a published rate in the corpus."""
        assert self.violations("published at 74.4") == []
        assert self.violations("published at 74.5") != []


class TestDocumentSweep:
    def test_the_readme_passes(self) -> None:
        assert checker.main(["README.md"]) == 0

    def test_the_notebook_markdown_cells_pass(self) -> None:
        assert checker.main(["experiments/swebench/notebook.py"]) == 0

    def test_an_injected_figure_is_caught(self, tmp_path) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        bad = tmp_path / "README.md"
        bad.write_text(readme + "\nThe score improved by 12.34 points.\n", encoding="utf-8")
        assert checker.main([str(bad)]) != 0
