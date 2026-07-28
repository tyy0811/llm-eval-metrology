"""T2.5: results into card JSON and machine-written numbers.

This is the integration layer, and the only module entitled to know about both a Holm threshold
and a McNemar gap floor (`docs/DECISIONS.md` D1.9, and the boundary drawn for T2.4).

Two contracts dominate the tests below. D1.9: `verdict` belongs to pair cards only, family cards
carry a structured `family_finding`, and no verdict string may leak into it. D2.5: a pair report
is built from discordant counts, never from a precomputed discordance rate, so the aggregate gap
cannot be substituted for `q`.
"""

from __future__ import annotations

import inspect
import json

import pytest

from metrology.paired import minimum_gap_for_threshold
from metrology.reporting import (
    VERDICT_NOT_RESOLVED,
    VERDICT_RESOLVED,
    PairCounts,
    Provenance,
    build_family_report,
    build_pair_report,
    family_card_json,
    pair_card_json,
)

PROVENANCE = Provenance(
    source="SWE-bench/experiments",
    pinned_revision="2f15350cd32becc4569e0d826361048555b605c0",
    fetch_date="2026-07-28",
    deviations=("D4 harness comparability",),
)


def counts(name: str, n01: int, n10: int, n: int = 500) -> PairCounts:
    return PairCounts(
        name=name, system_a=f"{name}_a", system_b=f"{name}_b", n01=n01, n10=n10, n_items=n
    )


def report(n01: int, n10: int, n: int = 500, threshold: float = 0.05):
    return build_pair_report(
        counts("pair", n01, n10, n),
        instrument="hidden-tests",
        threshold=threshold,
        provenance=PROVENANCE,
    )


class TestDiscordanceIsDerivedNotSupplied:
    """D2.5, enforced structurally rather than by documentation."""

    def test_pair_report_does_not_accept_a_discordance_rate(self) -> None:
        parameters = inspect.signature(build_pair_report).parameters

        assert "discordance_rate" not in parameters
        assert "q" not in parameters

    def test_discordance_rate_is_computed_from_the_counts(self) -> None:
        assert report(n01=20, n10=20).discordance_rate == pytest.approx(0.08)

    def test_a_tied_pair_still_reports_real_discordance(self) -> None:
        """The error D2.5 exists to prevent: gap 0 does not mean q 0."""
        tied = report(n01=20, n10=20)

        assert tied.net_edge == 0
        assert tied.discordance_rate == pytest.approx(0.08)
        assert tied.mde.status == "attainable"

    def test_total_agreement_reports_an_unattainable_mde(self) -> None:
        agreed = report(n01=0, n10=0)

        assert agreed.discordance_rate == 0.0
        assert agreed.mde.status == "unattainable"


class TestPairVerdict:
    def test_a_clear_difference_resolves(self) -> None:
        assert report(n01=0, n10=40).verdict == VERDICT_RESOLVED

    def test_a_tie_does_not_resolve(self) -> None:
        assert report(n01=20, n10=20).verdict == VERDICT_NOT_RESOLVED

    def test_the_verdict_respects_the_supplied_threshold(self) -> None:
        """Same data, family-corrected threshold, different verdict."""
        loose = report(n01=0, n10=7, threshold=0.05)
        strict = report(n01=0, n10=7, threshold=0.05 / 19)

        assert loose.verdict == VERDICT_RESOLVED
        assert strict.verdict == VERDICT_NOT_RESOLVED

    def test_equivalent_is_not_reachable_without_a_declared_band(self) -> None:
        """TOST arrives in Phase 5. Until then EQUIVALENT has no consumer and is not emitted."""
        assert report(n01=20, n10=20).verdict in {VERDICT_RESOLVED, VERDICT_NOT_RESOLVED}


class TestRulerAtObservedDiscordance:
    """D1.7: the requirement shown is the one at the observed discordance, not the floor."""

    def test_required_edge_is_computed_at_the_observed_discordance(self) -> None:
        pair = report(n01=18, n10=25, threshold=0.005)

        assert pair.n_discordant == 43
        assert pair.net_edge == 7
        assert pair.required_net_edge == 21

    def test_required_edge_exceeds_the_absolute_floor(self) -> None:
        """Publishing the floor as the requirement understates it, which D1.7 warns about."""
        threshold = 0.005
        pair = report(n01=18, n10=25, threshold=threshold)

        assert pair.required_net_edge > minimum_gap_for_threshold(threshold)

    def test_required_edge_is_none_when_discordance_is_too_low_to_ever_reject(self) -> None:
        pair = report(n01=1, n10=2, threshold=0.05)

        assert pair.required_net_edge is None

    def test_a_pair_meeting_its_requirement_resolves(self) -> None:
        pair = report(n01=0, n10=40, threshold=0.05)

        assert pair.net_edge >= pair.required_net_edge
        assert pair.verdict == VERDICT_RESOLVED


class TestPairCardJson:
    def test_pair_card_carries_a_verdict(self) -> None:
        card = pair_card_json(report(n01=20, n10=20))

        assert card["card_kind"] == "pair_verdict"
        assert card["verdict"] == VERDICT_NOT_RESOLVED

    def test_pair_card_carries_the_ruler_in_discordance_terms(self) -> None:
        card = pair_card_json(report(n01=18, n10=25, threshold=0.005))
        ruler = card["ruler"]

        assert ruler["observed_disagreements"] == 43
        assert ruler["split"] == [25, 18]
        assert ruler["observed_net_edge"] == 7
        assert ruler["required_net_edge_at_observed"] == 21

    def test_pair_card_names_the_test_convention(self) -> None:
        card = pair_card_json(report(n01=1, n10=2))

        assert card["test"]["convention"] == "doubled-tail"

    def test_pair_card_carries_the_provenance_block(self) -> None:
        card = pair_card_json(report(n01=1, n10=2))

        assert card["provenance"]["pinned_revision"].startswith("2f15350")
        assert card["provenance"]["fetch_date"] == "2026-07-28"
        assert "D4 harness comparability" in card["provenance"]["deviations"]

    def test_pair_card_is_json_serializable(self) -> None:
        text = json.dumps(pair_card_json(report(n01=18, n10=25)), sort_keys=True)

        assert json.loads(text)["card_kind"] == "pair_verdict"


class TestFamilyReport:
    def family(self):
        gaps = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]
        members = []
        for index, gap in enumerate(gaps):
            n01, n10 = 15, 15 + gap
            members.append(counts(f"pair_{index + 1}", n01=n01, n10=n10))
        return build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

    def test_family_size_and_threshold_come_from_holm(self) -> None:
        result = self.family()

        assert result.n_tests == 19
        assert result.first_critical == pytest.approx(0.05 / 19)

    def test_gap_floor_is_translated_from_the_holm_threshold(self) -> None:
        """The translation T2.4 was kept out of, performed here."""
        result = self.family()

        assert result.best_case_gap_floor == 10

    def test_largest_observed_gap_is_reported(self) -> None:
        assert self.family().largest_observed_gap == 7

    def test_no_pair_separates_when_every_gap_is_below_the_floor(self) -> None:
        result = self.family()

        assert result.separable_count == 0
        assert result.largest_observed_gap < result.best_case_gap_floor

    def test_a_family_with_a_large_gap_can_separate(self) -> None:
        members = [counts("wide", n01=0, n10=40), counts("narrow", n01=15, n10=16)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.separable_count == 1


class TestFamilyCardJson:
    def family_card(self):
        members = [counts(f"pair_{i}", n01=15, n10=15) for i in range(19)]
        return family_card_json(
            build_family_report(
                members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
            )
        )

    def test_family_card_carries_a_family_finding(self) -> None:
        card = self.family_card()

        assert card["card_kind"] == "family_summary"
        assert card["family_finding"]["claim_type"] == "resolving_power"

    def test_family_card_has_no_verdict_field(self) -> None:
        """D1.9 schema test one."""
        assert "verdict" not in self.family_card()

    def test_no_verdict_string_leaks_into_the_family_finding(self) -> None:
        """D1.9 schema test three, the one that actually holds the line."""
        blob = json.dumps(self.family_card()["family_finding"])

        for forbidden in ("RESOLVED", "NOT RESOLVED", "EQUIVALENT"):
            assert forbidden not in blob

    def test_headline_reports_the_separable_count_and_family_size(self) -> None:
        headline = self.family_card()["family_finding"]["headline"]

        assert headline == {"separable_count": 0, "family_size": 19, "unit": "adjacent_pairs"}

    def test_the_floor_is_labeled_best_case(self) -> None:
        limit = self.family_card()["family_finding"]["limit"]

        assert limit["floor_label"] == "best-case family floor"
        assert limit["best_case_family_floor"] == 10

    def test_the_inference_between_the_two_numbers_is_rendered(self) -> None:
        """D1.9 face requirement three: the reader must not perform the step themselves."""
        limit = self.family_card()["family_finding"]["limit"]

        assert "floor" in limit["inference"].lower()

    def test_scope_excludes_non_adjacent_comparisons(self) -> None:
        scope = self.family_card()["family_finding"]["scope"]

        assert scope["comparisons"] == "adjacent pairs only"
        assert "non-adjacent" in scope["excludes"]

    def test_secondary_floor_sits_under_progressive_disclosure(self) -> None:
        card = self.family_card()["family_finding"]

        assert "secondary_family_floor" in card["progressive_disclosure"]
        assert "secondary_family_floor" not in card["limit"]


class TestSchemaGuards:
    def test_a_pair_card_missing_a_verdict_is_rejected(self) -> None:
        """D1.9 schema test two, enforced by the validator the renderer will call."""
        from metrology.reporting import validate_card

        card = pair_card_json(report(n01=1, n10=2))
        del card["verdict"]

        with pytest.raises(ValueError, match="verdict"):
            validate_card(card)

    def test_a_family_card_carrying_a_verdict_is_rejected(self) -> None:
        from metrology.reporting import validate_card

        members = [counts(f"p{i}", n01=15, n10=15) for i in range(3)]
        card = family_card_json(
            build_family_report(
                members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
            )
        )
        card["verdict"] = VERDICT_NOT_RESOLVED

        with pytest.raises(ValueError, match="verdict"):
            validate_card(card)

    def test_a_verdict_string_inside_family_finding_is_rejected(self) -> None:
        from metrology.reporting import validate_card

        members = [counts(f"p{i}", n01=15, n10=15) for i in range(3)]
        card = family_card_json(
            build_family_report(
                members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
            )
        )
        card["family_finding"]["limit"]["inference"] = "NOT RESOLVED at any discordance"

        with pytest.raises(ValueError, match="verdict"):
            validate_card(card)

    def test_a_well_formed_card_passes(self) -> None:
        from metrology.reporting import validate_card

        assert validate_card(pair_card_json(report(n01=1, n10=2))) is True


class TestFamilyAndPairCardsAgree:
    """The family card's count and the pair cards' verdicts must describe the same events.

    Holm is a step-down: only the smallest p-value faces `alpha / m`, and the bar loosens for
    later ranks. Comparing every member against `alpha / m` is therefore stricter than Holm and
    can reject fewer pairs than the family card counts.
    """

    def disagreeing_family(self):
        members = [
            counts("wide", n01=0, n10=40),
            counts("six", n01=0, n10=6),
        ]
        return build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

    def test_the_case_that_exposed_it(self) -> None:
        """p = 0.03125 exceeds alpha/m = 0.025 yet Holm rejects it at the second step."""
        result = self.disagreeing_family()
        six = next(m for m in result.members if m.name == "six")

        assert six.p_value == pytest.approx(0.03125)
        assert six.p_value > result.first_critical

    def test_verdicts_match_holm_rejections_member_for_member(self) -> None:
        result = self.disagreeing_family()

        verdicts = [m.verdict == VERDICT_RESOLVED for m in result.members]
        assert verdicts == list(result.rejected)

    def test_resolved_count_equals_the_number_of_resolved_cards(self) -> None:
        """Resolved, not separable. The earlier form of this test encoded the conflation."""
        result = self.disagreeing_family()

        assert result.resolved_count == sum(m.verdict == VERDICT_RESOLVED for m in result.members)

    def test_adjusted_p_value_is_recorded_for_family_members(self) -> None:
        result = self.disagreeing_family()

        for member, adjusted in zip(result.members, result.adjusted, strict=True):
            assert member.adjusted_p_value == pytest.approx(adjusted)

    def test_the_card_shows_the_decision_rule_it_actually_used(self) -> None:
        result = self.disagreeing_family()
        card = pair_card_json(next(m for m in result.members if m.name == "six"))

        assert card["test"]["adjusted_p_value"] == pytest.approx(0.03125)
        assert card["test"]["alpha"] == 0.05
        assert card["test"]["decision_rule"] == "holm-adjusted p <= alpha"
        assert card["verdict"] == VERDICT_RESOLVED

    def test_a_standalone_report_has_no_adjusted_p_value(self) -> None:
        """Outside a family there is nothing to correct against."""
        assert report(n01=1, n10=2).adjusted_p_value is None


class TestSeparableIsNotResolved:
    """D1.9 keeps these distinct, and the registered result masks the difference.

    Resolved: the observed Holm test rejected. Separable: rejection was reachable under some
    feasible discordance configuration, which for a gap `g` means `g` clears the family floor.
    Every registered Experiment 1 pair fails both, so conflating them shows no symptom there.
    """

    def family_with_a_clearing_gap(self):
        members = [counts(f"p{i}", n01=100, n10=100) for i in range(18)]
        members.append(counts("wide", n01=100, n10=112))
        return build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

    def test_a_gap_clearing_the_floor_is_separable(self) -> None:
        result = self.family_with_a_clearing_gap()

        assert result.largest_observed_gap == 12
        assert result.largest_observed_gap >= result.best_case_gap_floor
        assert result.separable_count == 1

    def test_that_same_pair_is_not_resolved(self) -> None:
        """Reachable in principle, not rejected in fact, because discordance is high."""
        result = self.family_with_a_clearing_gap()

        assert result.resolved_count == 0

    def test_a_family_that_cannot_clear_its_floor_resolves_nothing(self) -> None:
        """The property that actually holds, and the one the registered case relies on.

        Holm cannot reject anything unless the smallest p-value clears `alpha / m`. So when no
        gap reaches the floor, `resolved_count` is necessarily zero as well.
        """
        gaps = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]
        members = [counts(f"pair_{i}", n01=15, n10=15 + g) for i, g in enumerate(gaps)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.largest_observed_gap < result.best_case_gap_floor
        assert result.separable_count == 0
        assert result.resolved_count == 0

    def test_holm_can_resolve_a_pair_below_the_family_floor(self) -> None:
        """Recorded as an open semantic question, not asserted as desirable.

        Separability is measured against `alpha / m`, the bar the family's first rejection must
        clear. Holm then loosens, so once one pair opens the family a second can be rejected
        with a gap below that floor. `resolved_count` can therefore exceed `separable_count`,
        which reads as a contradiction on a card and needs a ruling before T2.6.
        """
        members = [counts("wide", n01=0, n10=40), counts("six", n01=0, n10=6)]
        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.best_case_gap_floor == 7
        assert result.resolved_count == 2
        assert result.separable_count == 1

    def test_headline_reports_separability_and_observed_rejections_separately(self) -> None:
        card = family_card_json(self.family_with_a_clearing_gap())
        finding = card["family_finding"]

        assert finding["headline"]["separable_count"] == 1
        assert finding["observed"]["resolved_count"] == 0

    def test_the_registered_case_still_reads_zero_on_both(self) -> None:
        gaps = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]
        members = [counts(f"pair_{i}", n01=15, n10=15 + g) for i, g in enumerate(gaps)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert (result.separable_count, result.resolved_count) == (0, 0)


class TestThresholdsAreNotConflated:
    """Three different thresholds govern three different numbers."""

    def family(self):
        members = [counts(f"p{i}", n01=18, n10=25) for i in range(19)]
        return build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

    def test_mde_uses_the_registered_uncorrected_alpha(self) -> None:
        """PREREG section 5 registers alpha 0.05 for the MDE, not the corrected threshold."""
        member = self.family().members[0]

        assert member.mde.alpha == 0.05

    def test_the_decision_uses_the_family_alpha(self) -> None:
        member = self.family().members[0]

        assert member.alpha == 0.05
        assert member.adjusted_p_value is not None

    def test_the_ruler_uses_the_family_critical_value(self) -> None:
        result = self.family()
        member = result.members[0]

        assert member.ruler_threshold == pytest.approx(result.first_critical)

    def test_the_ruler_and_the_floor_share_one_threshold(self) -> None:
        """`21 against a floor of 6` would combine incompatible thresholds."""
        result = self.family()
        member = result.members[0]

        assert member.required_net_edge == 21
        assert result.best_case_gap_floor == 10
        assert member.ruler_threshold == pytest.approx(result.first_critical)

    def test_each_threshold_is_labeled_on_the_card(self) -> None:
        card = pair_card_json(self.family().members[0])

        assert card["test"]["alpha"] == 0.05
        assert card["ruler"]["threshold"] == pytest.approx(0.05 / 19)
        assert card["mde"]["alpha"] == 0.05


class TestDuplicateNamesAreRejected:
    def test_duplicate_member_names_raise(self) -> None:
        """The dict comprehension silently dropped one, giving a pair another pair's verdict."""
        members = [counts("same", n01=0, n10=40), counts("same", n01=20, n10=20)]

        with pytest.raises(ValueError, match="duplicate"):
            build_family_report(
                members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
            )

    def test_members_and_flags_stay_aligned(self) -> None:
        members = [counts(f"p{i}", n01=i, n10=i + 2) for i in range(5)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert len(result.members) == len(result.adjusted) == len(result.rejected) == 5


class TestDataclassInvariants:
    """D2.3, applied to the T2.5 dataclasses."""

    def test_pair_counts_rejects_discordance_above_the_item_count(self) -> None:
        with pytest.raises(ValueError, match="exceed"):
            PairCounts(name="p", system_a="a", system_b="b", n01=300, n10=300, n_items=500)

    def test_pair_counts_rejects_a_self_comparison(self) -> None:
        with pytest.raises(ValueError, match="itself"):
            PairCounts(name="p", system_a="a", system_b="a", n01=1, n10=2, n_items=500)

    def test_pair_counts_rejects_a_blank_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            PairCounts(name="  ", system_a="a", system_b="b", n01=1, n10=2, n_items=500)

    def test_provenance_rejects_a_blank_revision(self) -> None:
        with pytest.raises(ValueError, match="pinned_revision"):
            Provenance(source="s", pinned_revision="", fetch_date="2026-07-28")

    def test_pair_report_rejects_an_unknown_verdict(self) -> None:
        from metrology.reporting import PairReport

        with pytest.raises(ValueError, match="verdict"):
            PairReport(
                name="p",
                system_a="a",
                system_b="b",
                instrument="t",
                n_items=500,
                n01=1,
                n10=2,
                p_value=0.5,
                threshold=0.05,
                ruler_threshold=0.05,
                verdict="MAYBE",
                adjusted_p_value=None,
                alpha=None,
                discordance_rate=0.006,
                required_net_edge=None,
                mde=report(n01=1, n10=2).mde,
                provenance=PROVENANCE,
            )

    def test_pair_report_rejects_a_verdict_contradicting_its_adjusted_p(self) -> None:
        from metrology.reporting import PairReport

        with pytest.raises(ValueError, match="verdict"):
            PairReport(
                name="p",
                system_a="a",
                system_b="b",
                instrument="t",
                n_items=500,
                n01=1,
                n10=2,
                p_value=0.5,
                threshold=0.05,
                ruler_threshold=0.05,
                verdict=VERDICT_RESOLVED,
                adjusted_p_value=0.9,
                alpha=0.05,
                discordance_rate=0.006,
                required_net_edge=None,
                mde=report(n01=1, n10=2).mde,
                provenance=PROVENANCE,
            )


class TestFamilyCardRequiredShape:
    def card(self):
        members = [counts(f"p{i}", n01=15, n10=15) for i in range(19)]
        return family_card_json(
            build_family_report(
                members,
                instrument="hidden-tests",
                alpha=0.05,
                provenance=PROVENANCE,
                secondary_family_size=10,
            )
        )

    def test_conditionality_is_stated(self) -> None:
        assert self.card()["family_finding"]["conditionality"]

    def test_disclosure_separates_headline_from_secondary(self) -> None:
        disclosure = self.card()["family_finding"]["disclosure"]

        assert disclosure["applies_to_headline"] == []
        assert "D4 harness comparability" in disclosure["applies_to_secondary"]

    def test_secondary_family_size_and_floor_are_disclosed(self) -> None:
        block = self.card()["family_finding"]["progressive_disclosure"]

        assert block["secondary_family_size"] == 10
        assert block["secondary_family_floor"] == 9

    def test_validate_card_rejects_a_family_card_missing_required_blocks(self) -> None:
        from metrology.reporting import validate_card

        card = self.card()
        del card["family_finding"]["scope"]

        with pytest.raises(ValueError, match="scope"):
            validate_card(card)

    def test_validate_card_rejects_a_pair_card_missing_required_blocks(self) -> None:
        from metrology.reporting import validate_card

        card = pair_card_json(report(n01=1, n10=2))
        del card["ruler"]

        with pytest.raises(ValueError, match="ruler"):
            validate_card(card)

    def test_validate_card_rejects_an_almost_empty_card(self) -> None:
        from metrology.reporting import validate_card

        with pytest.raises(ValueError):
            validate_card({"card_kind": "family_summary", "family_finding": {"a": 1}})
