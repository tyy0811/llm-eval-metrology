"""T2.5: results into card JSON and machine-written numbers.

This is the integration layer, and the only module entitled to know about both a Holm threshold
and a McNemar gap floor (`docs/DECISIONS.md` D1.9, and the boundary drawn for T2.4).

Two contracts dominate the tests below. D1.9: `verdict` belongs to pair cards only, family cards
carry a structured `family_finding`, and no verdict string may leak into it. D2.5: a pair report
is built from discordant counts, never from a precomputed discordance rate, so the aggregate gap
cannot be substituted for `q`.
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest
from conftest import MALFORMED_PAIR_NAMES

from metrology.paired import minimum_gap_for_threshold
from metrology.reporting import (
    CSV_COLUMNS,
    FINDINGS_COLUMNS,
    NUMBER_FORMATS,
    VERDICT_NOT_RESOLVED,
    VERDICT_RESOLVED,
    PairCounts,
    Provenance,
    build_family_report,
    build_pair_report,
    csv_pair_rows,
    family_card_json,
    findings_markdown,
    findings_pair_rows,
    iter_numeric_leaves,
    pair_card_json,
    render_number,
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

        assert result.first_rejection_gap_floor == 10

    def test_largest_observed_gap_is_reported(self) -> None:
        assert self.family().largest_observed_gap == 7

    def test_no_pair_separates_when_every_gap_is_below_the_floor(self) -> None:
        result = self.family()

        assert result.separable_count == 0
        assert result.largest_observed_gap < result.first_rejection_gap_floor

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

    def test_the_floor_is_labeled_as_the_gateway(self) -> None:
        """Renamed from best-case: it bounds the first rejection, not the best case overall."""
        limit = self.family_card()["family_finding"]["limit"]

        assert limit["floor_label"] == "family gateway floor, cleared by the first rejection"
        assert limit["first_rejection_gap_floor"] == 10

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
        assert result.largest_observed_gap >= result.first_rejection_gap_floor
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

        assert result.largest_observed_gap < result.first_rejection_gap_floor
        assert result.separable_count == 0
        assert result.resolved_count == 0

    def test_a_pair_below_the_gateway_floor_is_still_separable(self) -> None:
        """Superseded the contradiction this test used to document.

        Separability now runs Holm over the per-pair p-value floors, so the gap-6 pair, which
        cannot open the family, is correctly separable because it can follow the gap-40 pair.
        """
        members = [counts("wide", n01=0, n10=40), counts("six", n01=0, n10=6)]
        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.first_rejection_gap_floor == 7
        assert result.resolved_count == 2
        assert result.separable_count == 2


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
        assert result.first_rejection_gap_floor == 10
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


class TestSeparabilityViaBestCaseHolm:
    """Separability runs the family's own gateway logic on the best case.

    For each pair the minimum attainable p-value is `p_value_floor(|gap|)`. Holm applied to that
    vector answers "what could reject under jointly best-case overlaps", which respects the
    gateway (a pair below the first-rejection floor can still follow one that clears it) without
    letting a resolving-power claim depend on observed overlaps.
    """

    def test_a_pair_below_the_gateway_floor_can_still_be_separable(self) -> None:
        """Gap 6 cannot open the family, but it can follow gap 40."""
        members = [counts("wide", n01=0, n10=40), counts("six", n01=0, n10=6)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.first_rejection_gap_floor == 7
        assert result.separable_count == 2
        assert result.resolved_count == 2

    def test_the_registered_family_separates_nothing(self) -> None:
        """D1.9 preserved exactly: the smallest floor cannot clear alpha / 19."""
        gaps = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]
        members = [counts(f"pair_{i}", n01=15, n10=15 + g) for i, g in enumerate(gaps)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.first_rejection_gap_floor == 10
        assert result.separable_count == 0
        assert result.resolved_count == 0

    @pytest.mark.parametrize(
        "gaps",
        [
            [40, 6],
            [0, 2, 7, 3, 0, 0, 2],
            [12, 12, 12],
            [0, 0, 0],
            [40, 30, 20, 6, 1],
            [9, 9],
        ],
    )
    def test_resolved_never_exceeds_separable(self, gaps: list[int]) -> None:
        """The invariant option 1 could not provide.

        Observed p is at least the floor for every pair, and Holm is monotone in the p vector,
        so best-case rejections weakly exceed observed ones.
        """
        members = [counts(f"p{i}", n01=10, n10=10 + g) for i, g in enumerate(gaps)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert result.resolved_count <= result.separable_count

    def test_separability_ignores_observed_overlap(self) -> None:
        """Same gaps, wildly different discordance, identical separability."""
        tight = [counts(f"p{i}", n01=0, n10=g) for i, g in enumerate([12, 3], start=1)]
        loose = [counts(f"p{i}", n01=200, n10=200 + g) for i, g in enumerate([12, 3], start=1)]

        a = build_family_report(tight, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE)
        b = build_family_report(loose, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE)

        assert a.separable_count == b.separable_count
        assert a.resolved_count != b.resolved_count

    def test_per_member_separability_flags_align_with_members(self) -> None:
        members = [counts("wide", n01=0, n10=40), counts("six", n01=0, n10=6)]

        result = build_family_report(
            members, instrument="hidden-tests", alpha=0.05, provenance=PROVENANCE
        )

        assert len(result.separable) == len(result.members)
        assert result.separable == (True, True)


class TestSeparabilityLabelling:
    def card(self):
        gaps = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]
        members = [counts(f"pair_{i}", n01=15, n10=15 + g) for i, g in enumerate(gaps)]
        return family_card_json(
            build_family_report(
                members,
                instrument="hidden-tests",
                alpha=0.05,
                provenance=PROVENANCE,
                secondary_family_size=10,
            )
        )

    def test_the_basis_of_separability_is_stated(self) -> None:
        finding = self.card()["family_finding"]

        assert (
            finding["separability_basis"] == "Holm applied to per-pair minimum attainable p-values"
        )

    def test_the_floor_is_named_as_the_gateway_not_the_best_case(self) -> None:
        """It bounds the first rejection, which is not the same as the best case overall."""
        limit = self.card()["family_finding"]["limit"]

        assert limit["first_rejection_gap_floor"] == 10
        assert limit["floor_label"] == "family gateway floor, cleared by the first rejection"
        assert "best_case_family_floor" not in limit


_REPO = Path(__file__).resolve().parent.parent
_RESULTS = _REPO / "experiments/swebench/results/results.json"
_AGGREGATES = _REPO / "experiments/swebench/derived/aggregates.json"

# Hand-written from the spec section 3 table. Constants no code produced: if
# render_number and the checker share a defect, these still catch it.
GOLDEN_CASES = (
    ("aggregates:n_items", 500, "500"),
    ("aggregates:entries[].published_rate", 74.4, "74.4"),
    ("results:pairs[].discordance_rate", 0.072, "0.072"),
    ("results:pairs[].discordance_rate", 0.1, "0.100"),
    ("results:pairs[].bootstrap.low", -0.022, "-0.022"),
    ("results:pairs[].p_value", 0.4570207854105899, "0.457"),
    ("results:pairs[].adjusted_p_value", 1.0, "1.000"),
    ("results:pairs[].mde.max_attainable_power", 0.9999999999511919, "1.000"),
    ("results:primary.first_critical", 0.002631578947368421, "0.00263158"),
    ("results:configuration.alpha", 0.05, "0.05"),
    ("results:configuration.bootstrap_level", 0.95, "0.95"),
    ("results:mde_grid.target_power", 0.8, "0.8"),
    ("results:pairs[].mde.instances", 17.384765625, "17.4"),
    ("results:configuration.master_seed", 20260727, "20260727"),
    ("results:primary.headline.tie_forced_not_distinguishable_count", 9, "9"),
)

_FLOAT_FORMATS = {"rate3", "p3", "pow3", "sig6", "inst1", "pct1"}


def corpus_documents() -> dict[str, dict]:
    return {
        "results": json.loads(_RESULTS.read_text(encoding="utf-8")),
        "aggregates": json.loads(_AGGREGATES.read_text(encoding="utf-8")),
    }


class TestRenderNumber:
    def test_golden_cases(self) -> None:
        for qualified_path, value, expected in GOLDEN_CASES:
            assert render_number(qualified_path, value) == expected, qualified_path

    def test_an_unregistered_path_raises(self) -> None:
        with pytest.raises(ValueError, match="no registered renderer"):
            render_number("results:primary.invented_field", 1)

    def test_registry_covers_the_two_file_inventory_exactly(self) -> None:
        """Both directions: no corpus path without a rule, no rule without a path.
        The inventory is derived at test time, never pinned to a count (spec sec. 3)."""
        observed = set()
        for source, document in corpus_documents().items():
            for qualified_path, _ in iter_numeric_leaves(source, document):
                observed.add(qualified_path)
        assert observed == set(NUMBER_FORMATS)

    def test_no_float_class_renders_a_committed_value_to_bare_zero_or_one(self) -> None:
        """Bounds the sig6 trimming exception. Integer classes are exempt by design:
        a separable count of 0 is the actual result and must be citable."""
        for source, document in corpus_documents().items():
            for qualified_path, value in iter_numeric_leaves(source, document):
                if NUMBER_FORMATS[qualified_path] in _FLOAT_FORMATS:
                    assert render_number(qualified_path, value) not in ("0", "1", "-0"), (
                        qualified_path,
                        value,
                    )

    def test_no_path_accepts_both_raw_and_scaled(self) -> None:
        """A percentage is a scaling, not a formatting: 0.072 and 7.2 must never
        both be accepted renderings at one path."""
        for source, document in corpus_documents().items():
            for qualified_path, value in iter_numeric_leaves(source, document):
                if NUMBER_FORMATS[qualified_path] in _FLOAT_FORMATS and value != 0:
                    raw = render_number(qualified_path, value)
                    scaled = render_number(qualified_path, value * 100)
                    assert raw != scaled, qualified_path

    def test_iter_numeric_leaves_skips_booleans_and_strings(self) -> None:
        leaves = dict(iter_numeric_leaves("x", {"a": True, "b": "s", "c": 3, "d": None}))
        assert leaves == {"x:c": 3}


def _flatten_keys(record: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in record.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            keys |= _flatten_keys(value, f"{name}_")
        else:
            keys.add(name)
    return keys


class TestPairProjections:
    def test_findings_rows_shape(self) -> None:
        rows = findings_pair_rows(corpus_documents()["results"])
        assert len(rows) == 19
        assert all(len(row) == len(FINDINGS_COLUMNS) == 5 for row in rows)
        assert all(isinstance(cell, str) for row in rows for cell in row)

    def test_findings_first_row_renders_the_committed_pair(self) -> None:
        row = findings_pair_rows(corpus_documents()["results"])[0]
        assert row == ("rank_1_vs_2", "0", "36", "1.000", "1.000")

    def test_csv_rows_shape(self) -> None:
        rows = csv_pair_rows(corpus_documents()["results"])
        assert len(rows) == 19
        assert all(len(row) == len(CSV_COLUMNS) == 24 for row in rows)

    def test_csv_columns_cover_the_record_key_set_both_directions(self) -> None:
        """A field added to the pair record later must fail here, not silently drop."""
        record = corpus_documents()["results"]["pairs"][0]
        assert set(CSV_COLUMNS) == _flatten_keys(record)

    def test_csv_row_values_are_the_registry_renderings(self) -> None:
        results = corpus_documents()["results"]
        row = dict(zip(CSV_COLUMNS, csv_pair_rows(results)[2], strict=True))
        pair = results["pairs"][2]
        assert row["p_value"] == render_number("results:pairs[].p_value", pair["p_value"])
        assert row["separable"] == "false"
        assert row["verdict"] == pair["verdict"]
        assert row["bootstrap_seed"] == str(pair["bootstrap"]["seed"])

    def test_no_findings_column_is_entirely_the_gateway_floor(self) -> None:
        """D2.7 guard: a column of nineteen 10s would re-assert the option-1
        separability definition in a presentation slot no other test watches."""
        results = corpus_documents()["results"]
        floor = str(results["primary"]["first_rejection_gap_floor"])
        for index in range(len(FINDINGS_COLUMNS)):
            column = [row[index] for row in findings_pair_rows(results)]
            assert set(column) != {floor}

    def test_csv_cells_render_none_as_empty_string(self) -> None:
        """The committed corpus is all-attainable with no None-valued cells, so without
        a synthetic pair this path is dead in the suite. None is schema-valid for
        mde.rate_difference and mde.instances (when unattainable) and
        required_net_edge_at_observed (when n_discordant too small for any rejection)."""
        results = copy.deepcopy(corpus_documents()["results"])
        results["pairs"][0]["mde"] = {
            "status": "unattainable",
            "instances": None,
            "rate_difference": None,
            "max_attainable_power": 0.05,
        }
        results["pairs"][0]["required_net_edge_at_observed"] = None
        rows = csv_pair_rows(results)
        row = dict(zip(CSV_COLUMNS, rows[0], strict=True))
        assert row["mde_instances"] == ""
        assert row["mde_rate_difference"] == ""
        assert row["required_net_edge_at_observed"] == ""


_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def assert_markdown_snapshot(name: str, rendered: str) -> None:
    """Write-then-fail, same discipline as the card snapshots (D2.8): a baseline is
    reviewed as a diff, never blessed by the code that produced it."""
    _FIXTURES.mkdir(exist_ok=True)
    path = _FIXTURES / name
    if not path.exists():  # pragma: no cover - first generation only
        path.write_text(rendered, encoding="utf-8")
        pytest.fail(f"baseline {name} did not exist and was written; review and re-run")
    assert rendered == path.read_text(encoding="utf-8")


class TestFindingsMarkdown:
    def block(self) -> str:
        documents = corpus_documents()
        return findings_markdown(documents["results"], documents["aggregates"])

    def test_the_lead_is_the_three_part_headline_before_any_table(self) -> None:
        """D1.6: the analytic result leads; a reader must not meet a p-value first."""
        block = self.block()
        assert block.index("0 of 19") < block.index("|")
        assert "9 are indistinguishable by tie arithmetic" in block
        assert "10 admit a real test and none rejects" in block

    def test_the_basis_is_the_public_wording(self) -> None:
        block = self.block()
        assert "derived from published leaderboard aggregates alone" in block
        assert "provenance-free" not in block

    def test_the_scope_line_precedes_the_table(self) -> None:
        block = self.block()
        assert block.index("adjacent pairs only") < block.index("| pair |")

    def test_the_inference_is_rendered_not_left_to_the_reader(self) -> None:
        block = self.block()
        assert "family gateway floor" in block
        assert "largest observed gap" in block
        assert "best-case family floor" not in block

    def test_d4_sits_beside_the_table_and_scopes_to_observed_quantities(self) -> None:
        block = self.block()
        assert "D4 harness comparability" in block
        assert "observed discordance, p-values, intervals, and MDEs" in block
        assert "pair identity and the resolved-count gap derive from published aggregates" in block
        assert "every column" not in block

    def test_both_registered_secondaries_and_the_straddle_surface(self) -> None:
        block = self.block()
        assert "non-tied" in block
        assert "no_logs sensitivity" in block
        assert "5 of the 19" in block
        assert "no adjacent pair straddles" in block

    def test_equivalent_never_appears(self) -> None:
        assert "EQUIVALENT" not in self.block()

    def test_snapshot(self) -> None:
        assert_markdown_snapshot("findings_block.md", self.block())


class TestFormatterStrictness:
    """The registry boundary must not repair malformed values (Jane's T3.3 review,
    finding 5). str(int(9.9)) silently wrote "9", True became "1", and "9" the
    string became 9 the figure; each of those is a wrong value laundered into the
    one string the checker will then accept. nan and inf rendered as literal text.
    """

    def test_int_format_rejects_fractional_floats(self) -> None:
        with pytest.raises(TypeError, match="exact non-boolean integer"):
            render_number("aggregates:n_items", 9.9)

    def test_int_format_rejects_booleans(self) -> None:
        with pytest.raises(TypeError, match="exact non-boolean integer"):
            render_number("aggregates:n_items", True)

    def test_int_format_rejects_strings(self) -> None:
        with pytest.raises(TypeError, match="exact non-boolean integer"):
            render_number("aggregates:n_items", "9")

    def test_float_formats_reject_booleans_and_strings(self) -> None:
        for bad in (True, "0.5"):
            with pytest.raises(TypeError, match="finite number"):
                render_number("results:pairs[].p_value", bad)

    def test_float_formats_reject_nan_and_inf(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValueError, match="finite"):
                render_number("results:pairs[].p_value", bad)

    def test_float_formats_still_accept_exact_ints(self) -> None:
        """JSON can hold an integral float's value as an int; the float classes
        accept both numeric kinds, they only refuse bool and non-finite."""
        assert render_number("results:pairs[].adjusted_p_value", 1) == "1.000"


class TestFindingsMarkdownConditionals:
    """The corpus-masked branches (Jane's T3.3 review, finding 1). Every committed
    count that gates a sentence is zero or empty, so the alternative branches were
    dead in the suite.

    The synthetic family is the D2.7 counterexample, gaps 40 and 6, with every
    related field derived from the engine rather than typed: the first fixture was
    hand-assembled and internally impossible (floor 10 against largest gap 7 with
    two separable pairs, one primary rejection with zero non-tied rejections), so
    the snapshot permanently approved contradictory measurement output (Jane's
    follow-up, finding 2).
    """

    def synthetic_d27_family(self) -> tuple[dict, dict]:
        from metrology.multiplicity import holm
        from metrology.paired import (
            mcnemar_exact_from_counts,
            minimum_gap_for_threshold,
            p_value_floor,
        )
        from metrology.power import mde_paired_binary
        from metrology.reporting import required_net_edge_at

        documents = corpus_documents()
        n_items = 500
        alpha = 0.05
        systems = [
            ("2025-01-15_alpha_agent", 440, "2025-01-15"),
            ("2024-05-01_beta_agent", 400, "2024-05-01"),
            ("2023-11-01_gamma_agent", 394, "2023-11-01"),
        ]
        entries = [
            {
                "artifact_format": "resolved-id-list",
                "checked": False,
                "checked_is_malformed": False,
                "checked_raw": None,
                "date": date,
                "no_generation": 0,
                "no_logs": 0,
                "published_rate": resolved / 5,
                "rank": rank,
                "resolved": resolved,
                "split_dir": "verified",
                "system": system,
            }
            for rank, (system, resolved, date) in enumerate(systems, start=1)
        ]
        aggregates = {
            "board": "Verified",
            "entries": entries,
            "family_size": len(entries),
            "instrument": "hidden-tests",
            "n_items": n_items,
            "substitutions": [],
        }

        counts = [(5, 45), (22, 28)]
        gaps = [entries[i]["resolved"] - entries[i + 1]["resolved"] for i in range(2)]
        assert [n10 - n01 for n01, n10 in counts] == gaps == [40, 6]

        names = [f"rank_{i + 1}_vs_{i + 2}" for i in range(2)]
        observed = holm(
            tuple(
                (name, mcnemar_exact_from_counts(n01=n01, n10=n10).p_value)
                for name, (n01, n10) in zip(names, counts, strict=True)
            ),
            alpha=alpha,
        )
        best_case = holm(
            tuple((name, p_value_floor(gap)) for name, gap in zip(names, gaps, strict=True)),
            alpha=alpha,
        )
        first_critical = alpha / len(names)
        floor = minimum_gap_for_threshold(first_critical)
        mde = mde_paired_binary(n=n_items, discordance_rate=0.1, alpha=alpha, target_power=0.8)

        pairs = []
        for index, (name, (n01, n10)) in enumerate(zip(names, counts, strict=True)):
            n_discordant = n01 + n10
            pairs.append(
                {
                    "adjusted_p_value": observed.adjusted[index],
                    "bootstrap": {
                        "estimate": gaps[index] / n_items,
                        "high": gaps[index] / n_items + 0.02,
                        "level": 0.95,
                        "low": gaps[index] / n_items - 0.02,
                        "n_resamples": 10000,
                        "seed": 2026072790 + index,
                        "unit": "instance",
                    },
                    "discordance_rate": n_discordant / n_items,
                    "mde": {
                        "instances": mde.instances,
                        "max_attainable_power": mde.max_attainable_power,
                        "rate_difference": mde.rate_difference,
                        "status": mde.status,
                    },
                    "n01": n01,
                    "n10": n10,
                    "n_discordant": n_discordant,
                    "name": name,
                    "net_edge": n10 - n01,
                    "p_value": observed.p_values[index],
                    "required_net_edge_at_observed": required_net_edge_at(
                        n_discordant, threshold=first_critical
                    ),
                    "separable": best_case.rejected[index],
                    "system_a": entries[index]["system"],
                    "system_b": entries[index + 1]["system"],
                    "verdict": "RESOLVED" if observed.rejected[index] else "NOT RESOLVED",
                }
            )

        results = copy.deepcopy(documents["results"])
        results["pairs"] = pairs
        results["primary"] = {
            **results["primary"],
            "family_size": len(names),
            "first_critical": first_critical,
            "first_rejection_gap_floor": floor,
            "headline": {
                "distinguishable_count": observed.n_rejected,
                "real_test_not_distinguishable_count": len(names) - observed.n_rejected,
                "tie_forced_not_distinguishable_count": 0,
            },
            "largest_observed_gap": max(gaps),
            "resolved_count": observed.n_rejected,
            "separable_count": best_case.n_rejected,
        }
        results["secondary"] = {
            "harness_straddle": {
                "boundary": "2024-04-15",
                "earliest_submission_date": "2023-11-01",
                "entries_predating_the_fix": 1,
                "straddling_pairs": [{"rank_a": 2, "rank_b": 3}],
            },
            "no_logs_sensitivity": {
                "family": {
                    "alpha": alpha,
                    "first_critical": first_critical,
                    "resolved_count": observed.n_rejected,
                    "separable_count": best_case.n_rejected,
                    "size": len(names),
                },
                "pairs": [
                    {
                        "adjusted_p_value": observed.adjusted[index],
                        "dropped_instances": index,
                        "n01": pairs[index]["n01"],
                        "n10": pairs[index]["n10"],
                        "n_items": n_items - index,
                        "p_value": observed.p_values[index],
                        "rank_a": index + 1,
                        "rank_b": index + 2,
                        "rejected": observed.rejected[index],
                    }
                    for index in range(2)
                ],
                "rule": results["secondary"]["no_logs_sensitivity"]["rule"],
                "total_pairs_affected": 1,
            },
            "non_tied_family": {
                "first_critical": first_critical,
                "gap_floor": floor,
                "rejected": observed.n_rejected,
                "size": len(names),
            },
        }

        # Coherence the first fixture lacked, asserted so it cannot rot silently.
        assert results["primary"]["separable_count"] == 2
        assert results["primary"]["resolved_count"] == 1
        assert results["primary"]["largest_observed_gap"] > floor
        assert (
            results["secondary"]["non_tied_family"]["rejected"]
            == results["primary"]["resolved_count"]
        )
        return results, aggregates

    def test_admitted_total_comes_from_the_non_tied_family(self) -> None:
        """With one rejection the first draft printed the not-distinguishable count
        as the admitted total. Both pairs here admit the test; one rejects."""
        results, aggregates = self.synthetic_d27_family()
        block = findings_markdown(results, aggregates)
        assert "2 admit a real test, with 1 rejecting and 1 not" in block

    def test_a_nonempty_straddle_list_renders_pair_identifiers(self) -> None:
        """The entries are rank dictionaries; joining them raised TypeError before
        any sentence rendered, and the ranks now render through the aggregate rank
        path rather than raw interpolation."""
        results, aggregates = self.synthetic_d27_family()
        block = findings_markdown(results, aggregates)
        assert "rank_2_vs_3 straddling the 2024-04-15" in block
        assert "no adjacent pair straddles" not in block

    def test_the_heading_is_outcome_neutral(self) -> None:
        """The first draft's heading said "cannot separate" even when the body
        reported separable pairs. The same question shape heads both outcomes."""
        documents = corpus_documents()
        zero_block = findings_markdown(documents["results"], documents["aggregates"])
        results, aggregates = self.synthetic_d27_family()
        nonzero_block = findings_markdown(results, aggregates)
        prefix = "### Experiment 1: can SWE-bench Verified separate its adjacent top"
        assert zero_block.splitlines()[0].startswith(prefix)
        assert nonzero_block.splitlines()[0].startswith(prefix)
        assert "cannot separate" not in zero_block.splitlines()[0]

    def test_the_floor_inference_reports_separability_when_present(self) -> None:
        results, aggregates = self.synthetic_d27_family()
        block = findings_markdown(results, aggregates)
        assert "2 of 2 pairs could reject under best-case overlaps." in block
        assert "no pair can open the family" not in block

    def test_no_measured_numeral_is_hand_typed(self) -> None:
        """The tie-arithmetic parenthetical carried a hand-typed p = 1 and the
        scope example hand-typed rank 1; the first now needs no numeral and the
        second reads the board's first and last ranks."""
        documents = corpus_documents()
        block = findings_markdown(documents["results"], documents["aggregates"])
        assert "force the exact test to its maximum p-value" in block
        assert "p = 1" not in block

    def test_nonzero_snapshot(self) -> None:
        results, aggregates = self.synthetic_d27_family()
        assert_markdown_snapshot(
            "findings_block_nonzero.md", findings_markdown(results, aggregates)
        )


class TestSharedSelectionRule:
    """PREREG D8's rule must have exactly one implementation. run.py and report.py
    both apply it, and two copies of a registered selection rule is the defect D1.12
    exists to prevent (T3.4 spec section 2).
    """

    def test_the_registered_selection_on_the_committed_board(self) -> None:
        from metrology.reporting import illustrative_pair_names

        entries = sorted(corpus_documents()["aggregates"]["entries"], key=lambda e: e["rank"])
        assert illustrative_pair_names(entries) == ["rank_1_vs_2", "rank_3_vs_4"]

    def test_the_widest_gap_moves_the_second_selection(self) -> None:
        from metrology.reporting import illustrative_pair_names

        entries = copy.deepcopy(
            sorted(corpus_documents()["aggregates"]["entries"], key=lambda e: e["rank"])
        )
        for entry in entries:
            if entry["rank"] >= 17:
                entry["resolved"] -= 9
        assert illustrative_pair_names(entries) == ["rank_1_vs_2", "rank_16_vs_17"]

    def test_a_tie_for_widest_breaks_by_earliest_rank(self) -> None:
        from metrology.reporting import adjacent_pairs, illustrative_pair_names

        entries = copy.deepcopy(
            sorted(corpus_documents()["aggregates"]["entries"], key=lambda e: e["rank"])
        )
        for entry in entries:
            if entry["rank"] >= 17:
                entry["resolved"] -= 7
        # The control's premise is a genuine two-way tie for the widest gap. If a future
        # aggregates.json shifts so this mutation no longer ties, the no-tie answer is also
        # rank_3_vs_4, and the assertion below would keep passing while silently ceasing to
        # test the tie-break rule at all. Verify the premise before trusting the answer.
        gaps = [a["resolved"] - b["resolved"] for a, b in adjacent_pairs(entries)]
        widest = max(gaps)
        tied_at_widest = [index for index, gap in enumerate(gaps) if gap == widest]
        assert len(tied_at_widest) == 2, (
            f"expected exactly one other index tied with index 2 for the widest gap, got "
            f"{tied_at_widest}; this control no longer exercises a real tie"
        )
        assert illustrative_pair_names(entries) == ["rank_1_vs_2", "rank_3_vs_4"]

    def test_a_widest_first_pair_yields_one_card(self) -> None:
        from metrology.reporting import illustrative_pair_names

        entries = copy.deepcopy(
            sorted(corpus_documents()["aggregates"]["entries"], key=lambda e: e["rank"])
        )
        for entry in entries:
            if entry["rank"] >= 2:
                entry["resolved"] -= 20
        assert illustrative_pair_names(entries) == ["rank_1_vs_2"]

    def test_one_statistic_constant_serves_both_card_kinds(self) -> None:
        """A family card and a pair card must not be able to name different
        statistics for the same procedure."""
        from metrology.reporting import STATISTIC_EXACT_MCNEMAR

        cards = json.loads(
            (
                Path(__file__).resolve().parent.parent / "experiments/swebench/results/cards.json"
            ).read_text(encoding="utf-8")
        )
        assert cards["family"]["family_finding"]["criterion"]["statistic"] == (
            STATISTIC_EXACT_MCNEMAR
        )
        assert cards["pairs"]
        for card in cards["pairs"].values():
            assert card["test"]["statistic"] == STATISTIC_EXACT_MCNEMAR

    def test_the_statistic_literal_has_one_home(self) -> None:
        """The value-equality check above passes even if a second raw literal is
        re-inlined beside the constant, e.g. in family_card_json, because both would
        still equal the same string. That is the D1.12 defect for the constant, and
        the two moved functions already have a source-level one-home guard
        (tests/test_run_swebench.py TestSelectionRuleHasOneHome); this mirrors it."""
        source = (Path(__file__).resolve().parent.parent / "metrology/reporting.py").read_text(
            encoding="utf-8"
        )
        assert source.count('"exact_mcnemar_two_sided"') == 1


class TestPairDisplayLabel:
    """The first human-readable reading of a pair must not be its machine identifier.

    render_pair_card emitted `label = escape(comparison["name"])`, so the heading read
    "Pair verdict: rank_3_vs_4". The "rank 3 against rank 4" wording in
    fixtures/verdict_reference.html was aspirational fixture prose that no renderer ever
    produced, which is why this conversion has to be built rather than wired up.
    """

    def test_it_reads_as_ranks(self) -> None:
        from metrology.reporting import pair_display_label

        assert pair_display_label("rank_3_vs_4") == "Ranks 3 and 4"
        assert pair_display_label("rank_1_vs_2") == "Ranks 1 and 2"
        assert pair_display_label("rank_16_vs_17") == "Ranks 16 and 17"

    @pytest.mark.parametrize("bad", MALFORMED_PAIR_NAMES)
    def test_it_refuses_anything_outside_the_registered_shape(self, bad: str) -> None:
        """A silent passthrough would put the identifier back with no test failing.

        Parametrized over the shared MALFORMED_PAIR_NAMES (conftest.py) rather than a local
        tuple, so a case added here is automatically covered by the renderer-level test in
        test_cards.py::TestNonCanonicalNameIsNotSilentlyRendered too, instead of requiring
        someone to remember to mirror it by hand.
        """
        from metrology.reporting import pair_display_label

        with pytest.raises(ValueError, match="rank_"):
            pair_display_label(bad)
