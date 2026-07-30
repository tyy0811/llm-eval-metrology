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

    def test_a_sentence_final_fabricated_figure_fails(self) -> None:
        """The previous tail lookahead (?![\\w.-]) excluded the period itself, so a
        fabricated figure ending a sentence with no trailing space was never matched
        and never checked; the most common English sentence shape must still be
        caught."""
        assert self.violations("The score improved by 12.34.") != []

    def test_a_hyphen_glued_fabricated_figure_fails(self) -> None:
        """A hyphen immediately after the numeral is not a word character, so the
        old tail lookahead treated it the same as an identifier boundary and let a
        fabricated figure hide behind a glued modifier; it must still be caught."""
        assert self.violations("a 42.7-point swing") != []

    def test_a_fabricated_ordinal_fails(self) -> None:
        """An ordinal suffix (st/nd/rd/th) is a word character to NUMERAL's tail
        guard (?!\\w), so "42nd" never matched NUMERAL at all and was invisible
        to the checker regardless of whether 42 is a corpus member."""
        assert self.violations("The 42nd adjacent pair was the only one to reject.") != []

    def test_hyphen_glued_numerals_check_membership_both_ways(self) -> None:
        """A hyphen immediately before a numeral is an identifier boundary to
        NUMERAL's head guard (?<![\\w.-]), so neither "rank-999" nor "top-20"
        was ever scanned. "top-20" must still pass, because 20 is a genuine
        corpus member (the board size); "rank-999" must fail, because 999 is
        not a member anywhere in the corpus."""
        assert self.violations("rank-999 sits below the cut") != []
        assert self.violations("the top-20 entries") == []

    def test_a_hyphen_glued_range_fails(self) -> None:
        """ "0-42" is a range, not a single glued modifier: the second number is
        hidden from NUMERAL by the same head-guard gap as "rank-999", and 42 is
        not a corpus member."""
        assert self.violations("gaps ranged 0-42 instances") != []

    def test_a_leading_dot_decimal_always_fails(self) -> None:
        """No corpus rendering begins with a bare dot (every float renderer
        writes a leading zero), so a leading-dot decimal is always a violation,
        independent of membership."""
        assert self.violations("a rate of .421 was observed") != []

    def test_scientific_notation_always_fails(self) -> None:
        """No corpus rendering contains an exponent, so scientific notation is
        always a violation, independent of membership."""
        assert self.violations("a threshold of 4.2e-3 was used") != []

    def test_corpus_values_at_sentence_end_still_pass(self) -> None:
        """The looser tail must not turn genuine corpus figures into false
        positives merely because a sentence happens to end right after them."""
        assert self.violations("the largest gap is 7.") == []
        assert self.violations("the published rate is 74.4.") == []


class TestDocumentSweep:
    def test_the_readme_passes(self) -> None:
        assert checker.main(["README.md"]) == 0

    def test_the_notebook_markdown_cells_pass(self) -> None:
        assert checker.main(["experiments/swebench/notebook.py"]) == 0

    def test_the_new_passes_do_not_flag_real_prose(self) -> None:
        """The ordinal, hyphen-glued, leading-dot, and scientific-notation passes
        are additive: they must not surface a violation anywhere in the
        committed README or notebook prose. Restates test_the_readme_passes and
        test_the_notebook_markdown_cells_pass explicitly for the new shapes,
        since those two tests would otherwise be the only signal that the new
        passes are clean against real prose."""
        assert checker.main(["README.md"]) == 0
        assert checker.main(["experiments/swebench/notebook.py"]) == 0

    def test_an_injected_figure_is_caught(self, tmp_path) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        bad = tmp_path / "README.md"
        bad.write_text(readme + "\nThe score improved by 12.34 points.\n", encoding="utf-8")
        assert checker.main([str(bad)]) != 0
