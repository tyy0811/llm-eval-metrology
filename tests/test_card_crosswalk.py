"""validate_card_set: every card leaf maps to exactly one rule, both directions.

cards.json is a validated intermediate artifact, never an independent source of
figures (T3.4 spec section 3). The committed data passes every rule, so every control
here mutates a copy: a check that only ever sees correct input proves nothing.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from metrology.reporting import validate_card_set

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEBENCH = REPO_ROOT / "experiments" / "swebench"


def load() -> tuple[dict, dict, dict, dict]:
    return (
        json.loads((SWEBENCH / "results/cards.json").read_text(encoding="utf-8")),
        json.loads((SWEBENCH / "results/results.json").read_text(encoding="utf-8")),
        json.loads((SWEBENCH / "derived/aggregates.json").read_text(encoding="utf-8")),
        json.loads((SWEBENCH / "manifests/upstream_digests.json").read_text(encoding="utf-8")),
    )


def mutated(**_unused):
    cards, results, aggregates, manifest = load()
    return copy.deepcopy(cards), results, aggregates, manifest


class TestCommittedSet:
    def test_the_committed_card_set_validates(self) -> None:
        validate_card_set(*load())


class TestStructuralTotality:
    """A scalar-leaf walk alone lets an unknown empty container pass, so the walk
    emits empty objects and lists as leaves too and totality is set equality."""

    @pytest.mark.parametrize(
        "value",
        [123, "text", True, None, {}, []],
        ids=["int", "str", "bool", "null", "obj", "list"],
    )
    def test_an_unmapped_leaf_of_any_type_fails(self, value) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"]["invented"] = value
        with pytest.raises(ValueError, match="no rule"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_missing_leaf_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        del cards["family"]["family_finding"]["headline"]["family_size"]
        with pytest.raises(ValueError, match="rule"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_extra_list_element_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"]["conditionality"].append("invented")
        with pytest.raises(ValueError, match="no rule"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_missing_list_element_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"]["conditionality"].pop()
        with pytest.raises(ValueError, match="rule"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_boolean_where_a_count_belongs_fails_on_type(self) -> None:
        """True == 1 in Python, so equality alone would accept this."""
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"]["headline"]["separable_count"] = False
        with pytest.raises(ValueError, match="type"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_float_where_an_int_belongs_fails_on_type(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"]["headline"]["family_size"] = 19.0
        with pytest.raises(ValueError, match="type"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_extra_top_level_key_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["extra"] = {}
        with pytest.raises(ValueError, match="top-level"):
            validate_card_set(cards, results, aggregates, manifest)


class TestValueRules:
    def test_a_reversed_ruler_split_fails(self) -> None:
        """split is [n10, n01]; reversing it renders the edge favouring the wrong
        system while every number on the card stays individually correct."""
        cards, results, aggregates, manifest = mutated()
        ruler = cards["pairs"]["rank_3_vs_4"]["ruler"]
        ruler["split"] = [ruler["split"][1], ruler["split"][0]]
        with pytest.raises(ValueError, match="split"):
            validate_card_set(cards, results, aggregates, manifest)

    @pytest.mark.parametrize(
        "field",
        ["instances", "rate_difference", "max_attainable_power", "status", "alpha", "target_power"],
    )
    def test_each_mde_field_is_checked(self, field) -> None:
        cards, results, aggregates, manifest = mutated()
        block = cards["pairs"]["rank_3_vs_4"]["mde"]
        block[field] = "tampered" if isinstance(block[field], str) else 0.5
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_changed_required_edge_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["pairs"]["rank_3_vs_4"]["ruler"]["required_net_edge_at_observed"] = 99
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_the_two_statistic_fields_must_agree(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["pairs"]["rank_3_vs_4"]["test"]["statistic"] = "chi_square"
        with pytest.raises(ValueError, match="statistic"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_mutated_comparison_name_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["pairs"]["rank_3_vs_4"]["comparison"]["name"] = "rank_9_vs_10"
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    @pytest.mark.parametrize(
        "path",
        [
            ("ruler", "requirement_basis"),
            ("ruler", "threshold_basis"),
            ("mde", "alpha_basis"),
        ],
    )
    def test_each_basis_string_is_pinned(self, path) -> None:
        """These name which threshold produced a number. D2.6 collapsed three
        thresholds into one once; a swapped basis string is that defect relocated
        into a label, with every figure still correct."""
        cards, results, aggregates, manifest = mutated()
        cards["pairs"]["rank_3_vs_4"][path[0]][path[1]] = (
            "the family correction, not the registered uncorrected level"
        )
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_stale_numeral_in_the_inference_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        finding = cards["family"]["family_finding"]
        finding["limit"]["inference"] = finding["limit"]["inference"].replace("10", "7")
        with pytest.raises(ValueError, match="inference"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_reversed_inference_conclusion_fails(self) -> None:
        """The numeral survives; the meaning inverts. A numeral-only rule accepted
        this, which is why PROSE_TEMPLATE checks the literal text too."""
        cards, results, aggregates, manifest = mutated()
        finding = cards["family"]["family_finding"]
        finding["limit"]["inference"] = (
            "every adjacent gap sits below the gateway floor of 10, so every pair can "
            "open the family and all can separate at any discordance configuration"
        )
        with pytest.raises(ValueError, match="inference"):
            validate_card_set(cards, results, aggregates, manifest)


class TestWrapper:
    def test_a_missing_family_card_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        del cards["family"]
        with pytest.raises(ValueError, match="family"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_extra_pair_card_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["pairs"]["rank_9_vs_10"] = copy.deepcopy(cards["pairs"]["rank_3_vs_4"])
        with pytest.raises(ValueError, match="selection"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_missing_selected_pair_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        del cards["pairs"]["rank_1_vs_2"]
        with pytest.raises(ValueError, match="selection"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_key_disagreeing_with_its_own_card_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        card = cards["pairs"].pop("rank_3_vs_4")
        cards["pairs"]["rank_1_vs_2"], cards["pairs"]["rank_3_vs_4"] = (
            card,
            cards["pairs"]["rank_1_vs_2"],
        )
        with pytest.raises(ValueError, match="key"):
            validate_card_set(cards, results, aggregates, manifest)


class TestManifestPopulation:
    """A manifest holding only the four systems named on the illustrative cards would
    satisfy every revision rule while the family card described a twenty-system
    analysis, so the population is validated before anything is derived from it
    (T3.4 spec 4a). Every requirement holds on the committed manifest today.
    """

    def tampered(self):
        cards, results, aggregates, manifest = load()
        return cards, results, aggregates, copy.deepcopy(manifest)

    def test_the_committed_manifest_population_is_valid(self) -> None:
        from metrology.reporting import validate_manifest_population

        _, _, aggregates, manifest = load()
        facts = validate_manifest_population(manifest, aggregates)
        assert facts["artifact_repo"] == "SWE-bench/experiments"
        assert facts["board_repo"] == "SWE-bench/swe-bench.github.io"
        assert facts["fetch_date"] == "2026-07-29"

    def test_a_missing_artifact_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        manifest["artifacts"].pop()
        with pytest.raises(ValueError, match="artifact"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_extra_artifact_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        manifest["artifacts"].append(copy.deepcopy(manifest["artifacts"][0]))
        with pytest.raises(ValueError, match="artifact"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_duplicated_artifact_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        manifest["artifacts"][1] = copy.deepcopy(manifest["artifacts"][0])
        with pytest.raises(ValueError, match="artifact"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_reordered_artifacts_fail(self) -> None:
        """Order is the published order, validated not repaired."""
        cards, results, aggregates, manifest = self.tampered()
        manifest["artifacts"][0], manifest["artifacts"][1] = (
            manifest["artifacts"][1],
            manifest["artifacts"][0],
        )
        with pytest.raises(ValueError, match="order"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_url_disagreeing_with_its_system_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        manifest["artifacts"][0]["url"] = manifest["artifacts"][0]["url"].replace(
            manifest["artifacts"][0]["system"], "20991231_fake_agent"
        )
        with pytest.raises(ValueError, match="url"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_board_url_disagreeing_with_its_commit_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        manifest["board"]["commit"] = "0" * 40
        with pytest.raises(ValueError, match="board"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_mixed_artifact_revision_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        first = manifest["artifacts"][0]
        first["url"] = first["url"].replace("2f15350", "0000000", 1)
        with pytest.raises(ValueError, match="revision"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_unexpected_repository_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        first = manifest["artifacts"][0]
        first["url"] = first["url"].replace("SWE-bench/experiments", "evil/repo", 1)
        with pytest.raises(ValueError, match="repositor"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_noncanonical_fetch_date_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        manifest["fetch_date"] = "2026-7-29"
        with pytest.raises(ValueError, match="canonical"):
            validate_card_set(cards, results, aggregates, manifest)


class TestProvenanceSemantics:
    def tampered(self):
        cards, results, aggregates, manifest = load()
        return copy.deepcopy(cards), results, aggregates, manifest

    def test_d4_removed_from_a_pair_card_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        card = cards["pairs"]["rank_1_vs_2"]
        card["provenance"]["deviations"] = []
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_d4_duplicated_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        card = cards["pairs"]["rank_1_vs_2"]
        card["provenance"]["deviations"] = card["provenance"]["deviations"] * 2
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_reordered_deviations_fail(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        card = cards["pairs"]["rank_3_vs_4"]
        card["provenance"]["deviations"].reverse()
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_d4_in_the_headline_disclosure_fails(self) -> None:
        """D1.11: the caveat must never look as if it qualifies the headline."""
        cards, results, aggregates, manifest = self.tampered()
        finding = cards["family"]["family_finding"]
        finding["disclosure"]["applies_to_headline"] = ["D4 harness comparability"]
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_wrong_source_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        cards["pairs"]["rank_1_vs_2"]["provenance"]["source"] = "evil/repo"
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_wrong_fetch_date_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        cards["pairs"]["rank_1_vs_2"]["provenance"]["fetch_date"] = "2026-07-30"
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_wrong_pinned_revision_fails(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        cards["pairs"]["rank_1_vs_2"]["provenance"]["pinned_revision"] = "0" * 40
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_the_malformed_disclosure_is_derived_from_the_aggregates(self) -> None:
        """D8 requires rank 4's malformed checked field disclosed on its card. The
        expected text is derived from checked_is_malformed and checked_raw, so a
        substring search for the word checked cannot satisfy it."""
        cards, results, aggregates, manifest = self.tampered()
        card = cards["pairs"]["rank_3_vs_4"]
        card["provenance"]["deviations"][1] = "upstream 'checked' field was odd"
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_the_malformed_disclosure_cannot_be_dropped(self) -> None:
        cards, results, aggregates, manifest = self.tampered()
        card = cards["pairs"]["rank_3_vs_4"]
        card["provenance"]["deviations"] = card["provenance"]["deviations"][:1]
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_the_malformed_disclosure_cannot_be_added_to_a_clean_pair(self) -> None:
        """Neither rank 1 nor rank 2 carries a malformed field, so this card must
        not claim one. Checkable in both directions is the point."""
        cards, results, aggregates, manifest = self.tampered()
        card = cards["pairs"]["rank_1_vs_2"]
        card["provenance"]["deviations"].append(
            "upstream 'checked' field for rank 4 is a sentence, not a boolean: "
            "'false (See README.md for info on how to get your results verified)'"
        )
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)


class TestCrossUnitCollision:
    """A count and a threshold can share a numeral while meaning different things;
    the crosswalk must fail on the wrong path even though no value comparison can
    tell the two sources apart (T3.4 spec section 13)."""

    def test_a_collision_across_units_fails(self) -> None:
        """tie_forced_not_distinguishable_count is 9 PAIRS and non_tied_family.gap_floor
        is 9 TASKS. A count and a threshold, different units, identical value, and the
        family card reads the second. Swapping them renders a correct-looking figure under
        a correct-looking label and no value comparison can object. This was a live error
        during drafting, caught by reading cards.json against results.json rather than by
        any test, which is why it now has one. The general rule: equal values under
        different units are as dangerous as equal values under the same name."""
        cards, results, aggregates, manifest = mutated()
        assert (
            results["primary"]["headline"]["tie_forced_not_distinguishable_count"]
            == results["secondary"]["non_tied_family"]["gap_floor"]
        )
        finding = cards["family"]["family_finding"]
        finding["progressive_disclosure"]["secondary_family_floor"] = 8
        with pytest.raises(ValueError, match="secondary_family_floor"):
            validate_card_set(cards, results, aggregates, manifest)


class TestPlainLanguageRules:
    """The most-read sentence in the document gets the same guarantee as every other
    leaf. Spec 10.3."""

    def test_a_swapped_family_size_fails(self) -> None:
        """aggregates:family_size is 20 and results:primary.family_size is 19. Swapping
        them renders "top-19" and "0 of 20", every number individually correct."""
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        block["lead"] = block["lead"].replace("top-20", "top-19")
        with pytest.raises(ValueError, match="lead"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_the_headline_count_must_come_from_the_registered_path(self) -> None:
        """distinguishable_count and separable_count are both 0 here, so this can only
        fail on the path, never on the value. D3.4."""
        cards, results, aggregates, manifest = mutated()
        assert (
            results["primary"]["separable_count"]
            == (results["primary"]["headline"]["distinguishable_count"])
        )
        cards["family"]["family_finding"]["plain_language"]["headline"]["count"] = 1
        with pytest.raises(ValueError, match="headline"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_stale_figure_in_the_scope_sentence_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        block["scope"] = block["scope"].replace("500", "499")
        with pytest.raises(ValueError, match="scope"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_analogy_that_implies_sufficiency_fails(self) -> None:
        """Clearing the mark is necessary, not sufficient. The numerals survive; the
        claim about the procedure inverts."""
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        block["analogy"] = block["analogy"].replace(
            "would not have settled a comparison on its own; it is the point at which "
            "the question becomes answerable at all",
            "would have settled the comparison",
        )
        with pytest.raises(ValueError, match="analogy"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_unscoped_superlative_in_the_analogy_fails(self) -> None:
        """7 is the largest lead between neighbors. Rank 1 leads rank 20 by 24, so
        dropping the word turns a true sentence into a false one with the numeral intact."""
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        block["analogy"] = block["analogy"].replace(
            "No neighboring pair anywhere", "No pair anywhere"
        )
        with pytest.raises(ValueError, match="analogy"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_reversed_task_level_note_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        block["task_level_note"] = (
            "Task-by-task results can overturn this once the per-instance artifacts are "
            "read, since a lead of 7 says little on its own."
        )
        with pytest.raises(ValueError, match="task_level_note"):
            validate_card_set(cards, results, aggregates, manifest)

    @pytest.mark.parametrize("index", [0, 1])
    def test_a_dropped_non_claim_fails(self, index) -> None:
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        del block["non_claims"][index]
        with pytest.raises(ValueError, match="rule"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_reordered_non_claims_fail(self) -> None:
        cards, results, aggregates, manifest = mutated()
        block = cards["family"]["family_finding"]["plain_language"]
        block["non_claims"].reverse()
        with pytest.raises(ValueError):
            validate_card_set(cards, results, aggregates, manifest)

    def test_an_added_plain_language_leaf_fails(self) -> None:
        """Totality reaches the new block without being told to, because the leaf walk
        is structural."""
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"]["plain_language"]["extra"] = "invented"
        with pytest.raises(ValueError, match="no rule"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_the_renderer_and_the_validator_read_one_mapping(self) -> None:
        """Two copies would let the validated path and the rendered path drift while both
        stayed individually correct, which is the defect D1.12 exists to prevent."""
        from metrology.reporting import PLAIN_LANGUAGE_SOURCES

        source = (REPO_ROOT / "metrology/cards/__init__.py").read_text(encoding="utf-8")
        assert "PLAIN_LANGUAGE_SOURCES" in source
        for path in PLAIN_LANGUAGE_SOURCES.values():
            assert source.count(f'"{path}"') == 0, (
                f"{path} is written as a literal in the renderer; it must come from "
                "PLAIN_LANGUAGE_SOURCES"
            )


class TestTaskLevelNotePremise:
    """plain_language_finding gates its own construction on needs_per_instance_data, but
    that gate protects run.py's live path only. validate_card_set re-checks the same
    premise directly against the committed artifact, so a stale or hand-edited cards.json
    whose task_level_note still claims the headline follows from totals alone cannot pass
    review just because the construction-time gate was satisfied on a different run. Spec
    10.2: 'the validator must refuse a card that carries it anyway.'"""

    def test_needs_per_instance_data_true_is_refused_even_with_unchanged_figures(self) -> None:
        """largest_lead and opening_lead are untouched, so this cannot fail on a numeral;
        it must fail on the premise alone or it is not actually gated."""
        cards, results, aggregates, manifest = mutated()
        results["primary"]["needs_per_instance_data"] = True
        with pytest.raises(ValueError, match="needs_per_instance_data"):
            validate_card_set(cards, results, aggregates, manifest)


class TestPathShadowing:
    """A card key containing "." or "[n]" collided with a flattened nested path.

    _card_leaves flattens with "." and "[n]", and _apply collapsed its output with
    dict(), keeping the last entry for a repeated path. The shadowed leaf was then
    validated in neither direction: absent from the leaf mapping so the unmapped check
    could not see it, and its path still present so the dead-rule check could not
    either. Any value could be substituted into the real leaf while the card set
    validated clean. cards.json is exactly the artifact report.py cannot byte-regenerate,
    so this crosswalk stands in place of a byte check, and a byte check caught every one
    of the four shapes below. One shape would have been an enumeration of size one, which
    is the defect this project has met at every other level, so all four are controls.

    These assert the reservation's message rather than the duplicate check's, because
    the reservation now fires first. Removing it leaves these decoys still refused by
    the duplicate layer behind it, so a failure here means the layering moved, not that
    the artifact became forgeable. TestReplacementShadowing is the control where
    removing the reservation genuinely lets a forged card through.
    """

    def test_a_decoy_shadowing_a_headline_figure_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        finding = cards["family"]["family_finding"]
        finding["headline"]["family_size"] = 99
        finding["headline.family_size"] = 19
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_decoy_shadowing_the_analogy_fails(self) -> None:
        """The inverted sentence is the document's most-read line."""
        cards, results, aggregates, manifest = mutated()
        finding = cards["family"]["family_finding"]
        real = finding["plain_language"]["analogy"]
        finding["plain_language"]["analogy"] = (
            "Every neighboring pair cleared the mark, so the ranking is reliable."
        )
        # The decoy sits one level above the block, so its flattened path is exactly the
        # nested leaf's path. Placed inside the block it would flatten to
        # plain_language.plain_language.analogy, which is merely unmapped, not a collision.
        finding["plain_language.analogy"] = real
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_decoy_shadowing_an_indexed_list_entry_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        finding = cards["family"]["family_finding"]
        real = finding["conditionality"][0]
        finding["conditionality"][0] = "integrity gate 3 was waived"
        finding["conditionality[0]"] = real
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_a_decoy_shadowing_a_pair_card_identity_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        card = cards["pairs"]["rank_3_vs_4"]
        comparison = card["comparison"]
        comparison["system_a"], comparison["system_b"] = (
            comparison["system_b"],
            comparison["system_a"],
        )
        card["comparison.system_a"] = comparison["system_b"]
        card["comparison.system_b"] = comparison["system_a"]
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)


class TestSecondaryFiguresArePathPinned:
    """primary.headline.tie_forced_not_distinguishable_count is 9 PAIRS and
    secondary.non_tied_family.gap_floor is 9 TASKS, and the family card reads the second.

    Equal values under different units, so no value comparison can separate them.
    Repointing the rule at the pairs count left the whole crosswalk suite green, because
    the unit-collision control fails on the value rather than on the path. This asserts
    the path itself, derived from the block's own name rather than restated as a literal,
    so any results:primary.* repoint is rejected.
    """

    def rules(self) -> dict:
        from metrology.reporting import (
            _family_rules,
            expected_deviations,
            validate_manifest_population,
        )

        _cards, results, aggregates, manifest = load()
        entries = sorted(aggregates["entries"], key=lambda entry: entry["rank"])
        facts = validate_manifest_population(manifest, aggregates)
        return _family_rules(results, facts, expected_deviations((), entries))

    @pytest.mark.parametrize(
        ("leaf", "path"),
        [
            ("secondary_family_size", "results:secondary.non_tied_family.size"),
            ("secondary_family_floor", "results:secondary.non_tied_family.gap_floor"),
        ],
    )
    def test_the_source_path_is_exact(self, leaf, path) -> None:
        """The exact path, not merely the prefix: gap_floor and size both live under
        non_tied_family, so a prefix assertion accepts them being swapped for each other,
        which is 9 tasks rendered where 10 pairs belong and no value comparison objects."""
        rules = self.rules()
        assert rules[f"family_finding.progressive_disclosure.{leaf}"] == ("source", path)


class TestSchemaValidationStillRuns:
    """_apply runs before validate_card so the crosswalk's path-naming error is the one
    reported first, but validate_card must still fire. Replacing it with a no-op left the
    whole crosswalk suite green, so nothing noticed the layer at all.

    This case passes the crosswalk by construction, since the card leaf and its source
    agree, and is rejected only by the schema layer's cross-field invariant.
    """

    def test_a_count_the_crosswalk_accepts_is_still_rejected_by_the_invariant(self) -> None:
        cards, results, aggregates, manifest = mutated()
        results = copy.deepcopy(results)
        results["primary"]["resolved_count"] = 5
        cards["family"]["family_finding"]["observed"]["resolved_count"] = 5
        with pytest.raises(ValueError, match="resolved <= separable <= family_size"):
            validate_card_set(cards, results, aggregates, manifest)


class TestReplacementShadowing:
    """The duplicate check alone missed the stronger attack: replace the block outright.

    Detecting duplicate flattened paths catches a decoy sitting beside a real block. It
    cannot catch the block being removed and its leaves reinserted as literal flattened
    keys, because then nothing is duplicated: the nested leaves no longer exist, every
    remaining value still matches its source, and validate_card_set returned clean. It is
    the more dangerous of the two, because the structure the renderer reaches for is gone
    rather than merely wrong, so the failure would surface downstream in report.py as a
    missing key rather than here as a validation error. validate_card does not catch it
    either, since _FINDING_SHAPE does not declare the block.

    The fix reserves the path characters at the point paths are built, which closes both
    shapes without either having to be anticipated.
    """

    def flattened(self, block: dict, prefix: str) -> dict:
        from metrology.reporting import _card_leaves

        return dict(_card_leaves(block, prefix))

    def test_replacing_the_whole_block_with_flattened_keys_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        finding = cards["family"]["family_finding"]
        finding.update(self.flattened(finding.pop("plain_language"), "plain_language"))
        assert not isinstance(finding.get("plain_language"), dict)
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)

    def test_replacing_a_nested_pair_block_with_flattened_keys_fails(self) -> None:
        cards, results, aggregates, manifest = mutated()
        card = cards["pairs"]["rank_3_vs_4"]
        card.update(self.flattened(card.pop("ruler"), "ruler"))
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)

    @pytest.mark.parametrize("character", [".", "[", "]"])
    def test_each_reserved_character_is_refused_in_a_key(self, character) -> None:
        cards, results, aggregates, manifest = mutated()
        cards["family"]["family_finding"][f"invented{character}key"] = 1
        with pytest.raises(ValueError, match="reserved for leaf paths"):
            validate_card_set(cards, results, aggregates, manifest)


class TestDuplicatePathsAreStillRefused:
    """The duplicate check behind the reservation, kept and verified as a second layer.

    Once _card_leaves refuses the reserved characters, no card reachable through
    validate_card_set can produce two identical leaf paths: paths are built only from
    dict keys and list indices, keys are unique within their object, and a colliding key
    would have to contain a reserved character to begin with. So _apply's duplicate check
    is unreachable from the public entry point by construction, which is exactly why it
    needs a direct test rather than none: an untested second layer is indistinguishable
    from a deleted one, and the first layer is what the next refactor is most likely to
    move.
    """

    def test_apply_refuses_a_collision_that_reaches_it(self, monkeypatch) -> None:
        from metrology import reporting

        monkeypatch.setattr(
            reporting,
            "_card_leaves",
            lambda node, prefix="": iter([("headline.of", 19), ("headline.of", 99)]),
        )
        with pytest.raises(ValueError, match="more than one leaf"):
            reporting._apply({"headline.of": ("constant", 19)}, {}, {}, "family")
