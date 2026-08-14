"""T2.6: the card renderer, targeting the approved reference.

Per D1.3 the reference HTML was built and approved before this renderer existed, so these
snapshots lock output against an independently approved artifact rather than recording whatever
the renderer happened to emit.

Two pair states are covered, as specified: balanced disagreement at gap zero, which exercises the
edge-safe marker at position zero, and the nonzero-gap ruler case.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest

from metrology.cards import (
    CARD_STYLESHEET,
    render_card,
    render_document,
    ruler_marker_class,
)
from metrology.reporting import (
    PairCounts,
    Provenance,
    build_family_report,
    family_card_json,
    pair_card_json,
)

FIXTURES = Path(__file__).resolve().parent.parent / "metrology" / "cards" / "fixtures"

PROVENANCE = Provenance(
    source="ILLUSTRATIVE, not a real run",
    pinned_revision="0000000illustrative",
    fetch_date="0000-00-00",
    deviations=("D4 harness comparability",),
)

REGISTERED_GAPS = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]


def registered_family():
    members = []
    for index, gap in enumerate(REGISTERED_GAPS):
        if gap == 7:
            members.append(
                PairCounts(
                    name=f"rank_{index + 1}_vs_{index + 2}",
                    system_a="system_c",
                    system_b="system_d",
                    n01=18,
                    n10=25,
                    n_items=500,
                )
            )
        else:
            members.append(
                PairCounts(
                    name=f"rank_{index + 1}_vs_{index + 2}",
                    system_a=f"system_{index}",
                    system_b=f"system_{index + 1}",
                    n01=15,
                    n10=15 + gap,
                    n_items=500,
                )
            )
    return build_family_report(
        members,
        instrument="hidden-tests",
        alpha=0.05,
        provenance=PROVENANCE,
        secondary_family_size=10,
    )


def pair_with(n_discordant: int):
    family = registered_family()
    return pair_card_json(next(m for m in family.members if m.n_discordant == n_discordant))


def assert_snapshot(name: str, rendered: str) -> None:
    """Compare against a committed baseline, writing it only when it does not exist yet."""
    path = FIXTURES / name
    if not path.exists():  # pragma: no cover - first generation only
        path.write_text(rendered, encoding="utf-8")
        pytest.fail(f"baseline {name} did not exist and was written; review and re-run")
    assert rendered == path.read_text(encoding="utf-8")


class TestSnapshots:
    def test_pair_card_with_a_nonzero_gap(self) -> None:
        assert_snapshot("snapshot_pair_gap7.html", render_card(pair_with(43)))

    def test_pair_card_with_balanced_disagreement(self) -> None:
        """Gap zero. The observed marker sits at position zero and must not overhang."""
        assert_snapshot("snapshot_pair_gap0.html", render_card(pair_with(30)))

    def test_family_card(self) -> None:
        assert_snapshot("snapshot_family.html", render_card(family_card_json(registered_family())))

    def test_rendering_is_byte_stable(self) -> None:
        """`make reproduce` promises identical bytes, so the renderer must be deterministic."""
        card = pair_with(43)

        assert render_card(card) == render_card(card)


class TestEdgeSafeMarkers:
    @pytest.mark.parametrize(
        ("edge", "total", "expected"),
        [(0, 43, "at-start"), (43, 43, "at-end"), (7, 43, ""), (21, 43, "")],
    )
    def test_marker_class_depends_on_position(self, edge: int, total: int, expected: str) -> None:
        assert ruler_marker_class(edge, total) == expected

    def test_the_balanced_pair_uses_the_start_class(self) -> None:
        rendered = render_card(pair_with(30))

        assert "at-start" in rendered

    def test_the_nonzero_gap_pair_uses_no_edge_class(self) -> None:
        rendered = render_card(pair_with(43))

        assert "at-start" not in rendered
        assert "at-end" not in rendered

    def test_zero_discordance_does_not_divide_by_zero(self) -> None:
        family = build_family_report(
            [
                PairCounts(name="agree", system_a="a", system_b="b", n01=0, n10=0, n_items=500),
                PairCounts(name="other", system_a="c", system_b="d", n01=5, n10=5, n_items=500),
            ],
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
        )
        card = pair_card_json(family.members[0])

        rendered = render_card(card)

        assert "0 of 500" in rendered or "no disagreement" in rendered.lower()


class TestRendererContract:
    def test_an_invalid_card_is_rejected_before_rendering(self) -> None:
        card = pair_with(43)
        del card["verdict"]

        with pytest.raises(ValueError, match="verdict"):
            render_card(card)

    def test_review_annotations_are_not_emitted(self) -> None:
        """The reference labels each structural element for review; the renderer must not."""
        rendered = render_card(pair_with(43))

        assert "data-element" not in rendered

    def test_system_names_are_escaped(self) -> None:
        family = build_family_report(
            [
                PairCounts(
                    name="injection",
                    system_a="<script>alert(1)</script>",
                    system_b="safe",
                    n01=1,
                    n10=2,
                    n_items=500,
                )
            ],
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
        )

        rendered = render_card(pair_card_json(family.members[0]))

        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered

    def test_a_family_card_renders_no_verdict_stamp(self) -> None:
        rendered = render_card(family_card_json(registered_family()))

        assert "verdict-stamp" not in rendered
        assert "NOT RESOLVED" not in rendered

    def test_a_pair_card_renders_its_verdict_stamp(self) -> None:
        rendered = render_card(pair_with(43))

        assert "verdict-stamp" in rendered
        assert "NOT RESOLVED" in rendered

    def test_the_provenance_seal_is_always_present(self) -> None:
        for card in (pair_with(43), family_card_json(registered_family())):
            assert "0000000illustrative" in render_card(card)


class TestDocument:
    def test_a_document_is_self_contained(self) -> None:
        document = render_document([render_card(pair_with(43))], title="Pair verdict")

        assert document.startswith("<!doctype html>")
        assert CARD_STYLESHEET in document
        assert "http://" not in document and "https://" not in document

    def test_the_document_title_is_escaped(self) -> None:
        document = render_document([], title="a & b")

        assert "<title>a &amp; b</title>" in document

    def test_several_cards_share_one_document(self) -> None:
        document = render_document(
            [render_card(family_card_json(registered_family())), render_card(pair_with(43))],
            title="Experiment 1",
        )

        assert document.count("<article") == 2

    def test_the_stylesheet_matches_the_approved_reference(self) -> None:
        """The renderer must not drift from the visual language that was signed off."""
        reference = (FIXTURES / "verdict_reference.html").read_text(encoding="utf-8")

        for token in (
            "--state-open: #8a6516",
            ".ruler-mark.at-start",
            "font-variant-numeric: tabular-nums",
            "prefers-color-scheme: dark",
        ):
            assert token in CARD_STYLESHEET, token
            assert token in reference, token


class TestValidationCoversEveryRenderedField:
    """Validation checked key presence only, so a malformed card reached the renderer."""

    @pytest.mark.parametrize(
        ("block", "key"),
        [
            ("test", "adjusted_p_value"),
            ("ruler", "threshold_basis"),
            ("mde", "alpha_basis"),
        ],
    )
    def test_a_missing_rendered_field_is_rejected_not_a_keyerror(self, block, key) -> None:
        card = pair_with(43)
        del card[block][key]

        with pytest.raises(ValueError, match=key):
            render_card(card)

    def test_a_missing_separability_basis_is_rejected(self) -> None:
        card = family_card_json(registered_family())
        del card["family_finding"]["separability_basis"]

        with pytest.raises(ValueError, match="separability_basis"):
            render_card(card)

    def test_a_non_numeric_split_is_rejected(self) -> None:
        """The injection vector: split reached an unescaped style attribute."""
        card = pair_with(43)
        card["ruler"]["split"] = ['1;" onmouseover="alert(1)', 18]

        with pytest.raises(ValueError, match="split"):
            render_card(card)

    def test_a_split_inconsistent_with_the_total_is_rejected(self) -> None:
        card = pair_with(43)
        card["ruler"]["split"] = [25, 99]

        with pytest.raises(ValueError, match="split"):
            render_card(card)

    def test_a_p_value_outside_the_unit_interval_is_rejected(self) -> None:
        card = pair_with(43)
        card["test"]["p_value"] = 4.2

        with pytest.raises(ValueError, match="p_value"):
            render_card(card)

    def test_an_unknown_mde_status_is_rejected(self) -> None:
        card = pair_with(43)
        card["mde"]["status"] = "probably"

        with pytest.raises(ValueError, match="status"):
            render_card(card)

    def test_no_attribute_injection_survives_validation(self) -> None:
        """Defense in depth: escaping stays, but the value never reaches the renderer."""
        card = pair_with(43)
        card["ruler"]["observed_disagreements"] = '43" onmouseover="alert(1)'

        with pytest.raises(ValueError, match="observed_disagreements"):
            render_card(card)


class TestReversedPairs:
    def reversed_pair(self):
        family = build_family_report(
            [PairCounts(name="rev", system_a="a", system_b="b", n01=25, n10=18, n_items=500)],
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
        )
        return pair_card_json(family.members[0])

    def test_the_net_edge_can_legitimately_be_negative(self) -> None:
        assert self.reversed_pair()["ruler"]["observed_net_edge"] == -7

    def test_the_ruler_position_is_never_negative(self) -> None:
        rendered = render_card(self.reversed_pair())

        assert "left: -" not in rendered

    def test_the_reading_states_the_magnitude(self) -> None:
        """Direction is already carried by the split, so the edge is reported as a size."""
        rendered = render_card(self.reversed_pair())

        assert "edge of -7" not in rendered
        assert "edge of 7" in rendered

    def test_a_reversed_pair_is_not_treated_as_an_endpoint(self) -> None:
        rendered = render_card(self.reversed_pair())

        assert "at-start" not in rendered


class TestVerdictDispatch:
    def resolved_pair(self):
        family = build_family_report(
            [PairCounts(name="wide", system_a="a", system_b="b", n01=0, n10=40, n_items=500)],
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
        )
        return pair_card_json(family.members[0])

    def test_a_resolved_card_does_not_use_the_unresolved_styling(self) -> None:
        rendered = render_card(self.resolved_pair())

        assert "is-open" not in rendered
        assert "is-resolved" in rendered

    def test_an_unresolved_card_keeps_the_amber_styling(self) -> None:
        rendered = render_card(pair_with(43))

        assert "is-open" in rendered
        assert "is-resolved" not in rendered

    def test_equivalent_is_refused_with_the_tost_message(self) -> None:
        """Matching on EQUIVALENT alone passed against the wrong error entirely.

        The verdict-versus-rule invariant fired first and reported a contradiction, which made
        the intended TOST branch unreachable while the test still went green.
        """
        card = pair_with(43)
        card["verdict"] = "EQUIVALENT"

        with pytest.raises(ValueError, match="requires TOST"):
            render_card(card)


class TestIdSafety:
    def named(self, name: str):
        family = build_family_report(
            [PairCounts(name=name, system_a="a", system_b="b", n01=1, n10=2, n_items=500)],
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
        )
        return pair_card_json(family.members[0])

    @pytest.mark.parametrize(
        "name", ["rank 3 vs rank 4", "a/b: c", "with.dots", "unicode name", "tabs\tand spaces"]
    )
    def test_ids_contain_no_whitespace_or_punctuation(self, name: str) -> None:
        import re

        rendered = render_card(self.named(name))
        referenced = re.search(r'aria-labelledby="([^"]+)"', rendered).group(1)

        assert re.fullmatch(r"[A-Za-z0-9_-]+", referenced), referenced
        assert f'id="{referenced}"' in rendered

    def test_ids_are_deterministic(self) -> None:
        assert render_card(self.named("rank 3 vs 4")) == render_card(self.named("rank 3 vs 4"))

    def test_different_names_get_different_ids(self) -> None:
        import re

        first = re.search(r'aria-labelledby="([^"]+)"', render_card(self.named("a b"))).group(1)
        second = re.search(r'aria-labelledby="([^"]+)"', render_card(self.named("a-b"))).group(1)

        assert first != second


class TestSeparableDefinitionPrefix:
    def test_the_face_states_separable_means(self) -> None:
        """D1.9 face requirement: the term is defined on the face, as in the reference."""
        rendered = render_card(family_card_json(registered_family()))

        assert "Separable means the family" in rendered


class TestCrossFieldInvariants:
    """Validated must mean renderable **and internally consistent**.

    Each field below is individually well-typed. What makes these cards wrong is the relationship
    between fields, which per-field checks cannot see.
    """

    def mutated(self, **changes):
        import copy

        card = copy.deepcopy(pair_with(43))
        for path, value in changes.items():
            block, key = path.split("__")
            card[block][key] = value
        return card

    def test_item_count_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="n_items"):
            render_card(self.mutated(comparison__n_items=0))

    def test_discordance_cannot_exceed_the_item_count(self) -> None:
        """Rendered as 43 of 20 instances, which is impossible."""
        with pytest.raises(ValueError, match="n_items|observed_disagreements"):
            render_card(self.mutated(comparison__n_items=20))

    def test_the_net_edge_must_equal_the_split_difference(self) -> None:
        """Edge 999 against a 43-wide track placed the marker at 2323 percent."""
        with pytest.raises(ValueError, match="observed_net_edge"):
            render_card(self.mutated(ruler__observed_net_edge=999))

    def test_the_net_edge_must_match_even_when_plausible(self) -> None:
        with pytest.raises(ValueError, match="observed_net_edge"):
            render_card(self.mutated(ruler__observed_net_edge=5))

    def test_the_required_edge_must_match_the_threshold(self) -> None:
        """Required 4 rendered a split of 23 to 20 while calling its net edge 4."""
        with pytest.raises(ValueError, match="required_net_edge"):
            render_card(self.mutated(ruler__required_net_edge_at_observed=4))

    def test_the_discordance_rate_must_match_the_counts(self) -> None:
        with pytest.raises(ValueError, match="discordance_rate"):
            render_card(self.mutated(mde__discordance_rate=0.5))

    def test_an_attainable_mde_needs_its_numbers(self) -> None:
        with pytest.raises(ValueError, match="instances|attainable"):
            render_card(self.mutated(mde__instances=None))

    def test_an_unattainable_mde_must_not_carry_numbers(self) -> None:
        card = self.mutated(mde__status="unattainable")

        with pytest.raises(ValueError, match="unattainable"):
            render_card(card)

    def test_a_verdict_must_agree_with_the_displayed_decision_rule(self) -> None:
        """The worst of these: a false result that validated and rendered cleanly."""
        card = pair_with(43)
        card["verdict"] = "RESOLVED"

        with pytest.raises(ValueError, match="verdict"):
            render_card(card)

    def test_the_unmutated_card_still_validates(self) -> None:
        assert render_card(pair_with(43))


class TestFamilyCrossFieldInvariants:
    def family_card(self, **overrides):
        import copy

        card = copy.deepcopy(family_card_json(registered_family()))
        for path, value in overrides.items():
            block, key = path.split("__")
            card["family_finding"][block][key] = value
        return card

    def test_resolved_cannot_exceed_separable(self) -> None:
        with pytest.raises(ValueError, match="resolved_count|separable"):
            render_card(self.family_card(observed__resolved_count=5))

    def test_separable_cannot_exceed_the_family_size(self) -> None:
        with pytest.raises(ValueError, match="separable_count|family_size"):
            render_card(self.family_card(headline__separable_count=40))

    def test_secondary_size_and_floor_must_agree_on_presence(self) -> None:
        """A size with a null floor rendered the literal text None."""
        with pytest.raises(ValueError, match="secondary"):
            render_card(self.family_card(progressive_disclosure__secondary_family_floor=None))

    def test_a_secondary_floor_without_a_size_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="secondary"):
            render_card(self.family_card(progressive_disclosure__secondary_family_size=None))

    def test_both_absent_is_allowed(self) -> None:
        family = build_family_report(
            [PairCounts(name="p", system_a="a", system_b="b", n01=1, n10=2, n_items=500)],
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
        )

        assert render_card(family_card_json(family))


class TestDecisionRuleDispatch:
    def altered(self, **changes):
        import copy

        card = copy.deepcopy(pair_with(43))
        card["test"].update(changes)
        return card

    def test_an_unknown_decision_rule_is_rejected(self) -> None:
        """Anything but the Holm string fell through to the raw-p branch and was displayed."""
        with pytest.raises(ValueError, match="decision_rule"):
            render_card(self.altered(decision_rule="bananas"))

    def test_the_holm_rule_requires_an_adjusted_p_value(self) -> None:
        with pytest.raises(ValueError, match="adjusted"):
            render_card(self.altered(adjusted_p_value=None))

    def test_the_raw_rule_must_not_carry_an_adjusted_p_value(self) -> None:
        with pytest.raises(ValueError, match="adjusted"):
            render_card(self.altered(decision_rule="p <= threshold"))

    def test_a_standalone_card_uses_the_raw_rule_cleanly(self) -> None:
        from metrology.reporting import build_pair_report

        standalone = build_pair_report(
            PairCounts(name="solo", system_a="a", system_b="b", n01=0, n10=40, n_items=500),
            instrument="hidden-tests",
            threshold=0.05,
            provenance=PROVENANCE,
        )
        card = pair_card_json(standalone)

        assert card["test"]["decision_rule"] == "p <= threshold"
        assert card["test"]["adjusted_p_value"] is None
        assert render_card(card)


class TestSecondaryProvenanceIsValidated:
    """The renderer read two fields the validated shape did not cover."""

    def card(self):
        import copy

        return copy.deepcopy(pair_with(43))

    def test_a_missing_secondary_field_is_rejected(self) -> None:
        """It validated, then rendering raised KeyError."""
        card = self.card()
        del card["provenance"]["secondary_revision"]

        with pytest.raises(ValueError, match="secondary_revision"):
            render_card(card)

    def test_a_half_populated_secondary_is_rejected(self) -> None:
        """It validated, then rendered the literal text None as an attribution."""
        card = self.card()
        card["provenance"]["secondary_source"] = "SWE-bench/experiments"

        with pytest.raises(ValueError, match="together"):
            render_card(card)

    def test_a_non_string_secondary_source_is_rejected(self) -> None:
        card = self.card()
        card["provenance"]["secondary_source"] = 42
        card["provenance"]["secondary_revision"] = "abc"

        with pytest.raises(ValueError, match="secondary_source"):
            render_card(card)

    def test_both_absent_is_valid(self) -> None:
        assert render_card(self.card())

    def test_both_present_is_valid(self) -> None:
        card = self.card()
        card["provenance"]["secondary_source"] = "SWE-bench/experiments"
        card["provenance"]["secondary_revision"] = "2f15350"

        assert render_card(card)


class TestMultiSourceFamilyRendering:
    """D7 narrows D4 to the observed figures, so the face must show it applies to them."""

    def members(self):
        return [
            PairCounts(
                name=f"p{index}",
                system_a=f"a{index}",
                system_b=f"b{index}",
                n01=15,
                n10=15,
                n_items=500,
            )
            for index in range(19)
        ]

    def multi_source_family(self):
        family = build_family_report(
            self.members(),
            instrument="hidden-tests",
            alpha=0.05,
            provenance=PROVENANCE,
            family_provenance=Provenance(
                source="SWE-bench/swe-bench.github.io",
                pinned_revision="7c4289f30aa1a1c63c2e2a25aae30c16d92b5114",
                fetch_date="2026-07-29",
                deviations=("D4 harness comparability",),
                secondary_source="SWE-bench/experiments",
                secondary_revision="2f15350cd32becc4569e0d826361048555b605c0",
            ),
            secondary_family_size=10,
        )
        return family_card_json(family)

    def test_the_observed_source_is_rendered(self) -> None:
        rendered = render_card(self.multi_source_family())

        assert "observed figures from" in rendered
        assert "SWE-bench/experiments" in rendered

    def test_the_headline_source_is_the_board(self) -> None:
        rendered = render_card(self.multi_source_family())

        assert "SWE-bench/swe-bench.github.io" in rendered

    def test_the_secondary_caveat_reaches_the_face(self) -> None:
        """It was in the JSON and invisible in the HTML."""
        rendered = render_card(self.multi_source_family())

        assert "D4 harness comparability" in rendered
        assert "observed figure caveats" in rendered

    def test_the_headline_is_marked_uncaveated(self) -> None:
        rendered = render_card(self.multi_source_family())

        assert "headline caveats" in rendered

    def test_multi_source_family_snapshot(self) -> None:
        assert_snapshot("snapshot_family_multisource.html", render_card(self.multi_source_family()))


class TestTableReference:
    """D1.3: the approved reference precedes the renderer. Committing it first means
    Task 4's snapshots target an artifact a human approved, rather than recording
    whatever the renderer happened to emit (D2.8 credits this ordering for catching a
    heading regression no assertion covered).
    """

    def test_the_reference_exists_and_is_labelled_illustrative(self) -> None:
        """The plan's `"illustrative" in text.lower()` could not fail. Delete the whole
        stamp block and nine occurrences survive: the <title>, the class name inside the
        inlined stylesheet, and the four illustrative_* pair names. One assertion stood
        between this repo and an unlabelled fixture and it passed with every labelling
        signal removed, so it asserts on the stamp block and its wording instead.
        """
        path = FIXTURES / "table_reference.html"
        assert path.is_file()
        text = path.read_text(encoding="utf-8")

        opening = '<div class="stamp-illustrative">'
        assert opening in text
        stamp = text.split(opening, 1)[1].split("</div>", 1)[0]
        assert "Illustrative fixture. Not a result." in stamp
        assert "invented" in stamp
        assert "No experiment produced them." in stamp
        assert text.index(opening) < text.index("<table")

    def test_the_illustrative_figures_cannot_be_read_as_measurements(self) -> None:
        """The stamp asserts a property of the digits, so something has to hold the digits
        to it. The first draft ran a gap column of 0, 2, 4, 6 and a discordance of 44 on
        every row, both entirely plausible for this corpus, under a sentence claiming no
        cell could be read as a measurement. A false sentence sitting on correct work is
        the harder kind to spot, so the counts are repdigits now and this is the guard.
        """
        text = (FIXTURES / "table_reference.html").read_text(encoding="utf-8")
        body = text.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        rows = [re.findall(r"<td>(.*?)</td>", row) for row in body.split("<tr>")[1:]]
        assert len(rows) == 4

        for name, gap, discordance, observed, adjusted in rows:
            assert name.startswith("illustrative_"), name
            for count in (gap, discordance):
                assert re.fullmatch(r"(\d)\1{3,}", count), f"count {count} could pass for real"
            for p_value in (observed, adjusted):
                assert re.fullmatch(r"1\.000|0\.(\d)\1\1", p_value), p_value

    def test_the_reference_shows_the_settled_columns(self) -> None:
        """D3.6 governs over D1.10's column sentence: no per-pair floor column.

        The plan searched the whole file, where four of the five strings also occur
        outside the table: "pair" 26 times, "resolved-count gap" and "observed
        discordance" in the D4 note, "observed p-value" inside a CSS comment. Only
        "Holm-adjusted p-value" was unique to the header row, so corrupting any of the
        other four left the suite green. This reads the header cells out of the table
        region and compares the whole row, which also catches an added column.
        """
        text = (FIXTURES / "table_reference.html").read_text(encoding="utf-8")
        table = text.split("<table", 1)[1].split("</table>", 1)[0]

        assert re.findall(r"<th\b[^>]*>(.*?)</th>", table, flags=re.DOTALL) == [
            "pair",
            "resolved-count gap",
            "observed discordance",
            "observed p-value",
            "Holm-adjusted p-value",
        ]
        assert "floor" not in table.lower()

    def test_the_scroll_container_is_reachable_from_the_keyboard(self) -> None:
        """Chrome and Firefox focus a scrolling container by themselves, Safari does not,
        so without these attributes a keyboard-only Safari reader cannot scroll the table
        at all. Task 4's snapshot freezes whatever this reference establishes, so the
        attributes are guarded here rather than left to the renderer to remember.
        """
        text = (FIXTURES / "table_reference.html").read_text(encoding="utf-8")
        css = (Path(__file__).resolve().parent.parent / "metrology/cards/card.css").read_text(
            encoding="utf-8"
        )

        opening = text.split("<table", 1)[0].rsplit('<div class="pair-table-scroll"', 1)
        assert len(opening) == 2, "no .pair-table-scroll container before the table"
        attributes = opening[1].split(">", 1)[0]
        assert 'tabindex="0"' in attributes
        assert 'role="region"' in attributes
        assert "aria-label=" in attributes
        assert ".pair-table-scroll:focus-visible" in css

    def test_the_reference_inlines_the_current_stylesheet(self) -> None:
        """D1.3 only works if the approved reference shows what card.css actually does.
        The copy is inlined by hand so the file opens with no server, and nothing stopped
        it drifting: verdict_reference.html inlines a copy taken before card.css gained
        its .card-rail.is-resolved block and has been quietly stale ever since. That file
        is left alone deliberately; this one is held to the current sheet.
        """
        text = (FIXTURES / "table_reference.html").read_text(encoding="utf-8")
        css = (Path(__file__).resolve().parent.parent / "metrology/cards/card.css").read_text(
            encoding="utf-8"
        )

        inlined = text.split("<style>\n", 1)[1].split("</style>", 1)[0]
        assert inlined == css

    def test_the_stylesheet_has_a_table_language(self) -> None:
        """A smoke check only: the sheet had zero table rules, so the renderer in Task 4
        would have styled the table by accident. Substring matching cannot tell a table
        language from the word table, so the real gate on this task is the visual review.
        """
        css = (Path(__file__).resolve().parent.parent / "metrology/cards/card.css").read_text(
            encoding="utf-8"
        )
        for selector in ("table", "thead", "tbody", "caption"):
            assert selector in css


REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_REFERENCE = FIXTURES / "page_reference.html"

#: The three committed corpus documents the page reference quotes. Section 12.1 inverts the
#: fixture convention for this one file: it carries real figures, so it can go stale, so every
#: figure is held to the document it came from.
CORPUS_FILES = {
    "results": REPO_ROOT / "experiments" / "swebench" / "results" / "results.json",
    "aggregates": REPO_ROOT / "experiments" / "swebench" / "derived" / "aggregates.json",
    "cards": REPO_ROOT / "experiments" / "swebench" / "results" / "cards.json",
}

#: Every numeral the finding layer prints, in document order: the pattern that locates it and the
#: source-qualified path it must equal. `literal:` marks a numeral that is part of the copy rather
#: than a corpus figure, so that the totality assertion below can still account for it.
#:
#: The two `family_size` entries are the collision spec section 10.2 warns about:
#: `aggregates:family_size` is the board, `results:primary.family_size` is the adjacent pairs.
FINDING_FIGURES = (
    (r"no neighboring top-(\d+) pair showed a reliable difference", "aggregates:family_size"),
    (r"(\d+) of \d+ neighboring pairs", "results:primary.headline.distinguishable_count"),
    (r"\d+ of (\d+) neighboring pairs", "results:primary.family_size"),
    (r"The top (\d+) creates", "aggregates:family_size"),
    (r"creates (\d+) neighboring comparisons", "results:primary.family_size"),
    (r"each measured on (\d+) tasks", "aggregates:n_items"),
    (r"largest lead (\d+) tasks", "results:primary.largest_observed_gap"),
    (r"minimum opening lead (\d+) tasks", "results:primary.first_rejection_gap_floor"),
    (r"needed a lead of at least (\d+) tasks", "results:primary.first_rejection_gap_floor"),
    (r"anywhere in the top (\d+) led by more than", "aggregates:family_size"),
    (r"led by more than (\d+)\.", "results:primary.largest_observed_gap"),
    (r"a lead of (\d+) stays under the mark", "results:primary.largest_observed_gap"),
    (r"how rank (\d+) compares", "literal:1"),
    (r"compares with rank (\d+)\.", "aggregates:family_size"),
)

#: The lead sentence, binding verbatim from the presentation contract (spec section 1.1 item 1).
LEAD_SENTENCE = (
    "Using the statistical test chosen in advance, no neighboring top-20 pair showed a "
    "reliable difference."
)

#: The analogy's scoping clause. Every superlative about a lead has to say which pairs it ranges
#: over: the largest lead between neighbors is 7, and the largest lead anywhere on the board is 24.
#: Held as a literal because dropping one word restores a false claim while every figure on the
#: page stays correct and every numeral stays pinned to its path.
NEIGHBORING_SCOPE = "No neighboring pair anywhere in the top"

#: The necessary-not-sufficient clause, which spec 10.2 makes a correctness requirement on the
#: analogy rather than a stylistic one. It carries no numeral, so the staleness walk cannot reach
#: it. Without it the page implies that reaching the mark would have demonstrated a difference.
NOT_SUFFICIENT_CLAUSE = (
    "Reaching the mark would not have settled a comparison on its own; it is the point at which "
    "the question becomes answerable at all."
)

#: Spelled-out cardinals the page's prose uses. A digit-anchored guard cannot see a spelled number,
#: so the word is derived from the corpus here rather than trusted.
SPELLED_NUMBERS = {19: "nineteen", 20: "twenty", 21: "twenty one"}


def corpus_value(qualified_path: str) -> int:
    """Resolve a source-qualified path such as `results:primary.family_size` against the corpus."""
    source, _, dotted = qualified_path.partition(":")
    if source == "literal":
        return int(dotted)
    node = json.loads(CORPUS_FILES[source].read_text(encoding="utf-8"))
    for key in dotted.split("."):
        node = node[key]
    return node


def page_reference_text() -> str:
    return PAGE_REFERENCE.read_text(encoding="utf-8")


def finding_region(text: str) -> str:
    """The finding layer fragment alone.

    Tier 1's prohibitions are properties of the first reading, and the apparatus below it states
    p-values, names systems and carries the provenance seal. Asserted against the whole page they
    would fail for the wrong reason; asserted against the page with the apparatus stripped by a
    loose split they could pass for the wrong reason.
    """
    opening = '<article class="card finding"'
    start = text.index(opening)
    end = text.index("</article>", start) + len("</article>")
    return text[start:end]


def finding_prose(text: str) -> str:
    """The finding layer with tags removed and whitespace collapsed, as a reader sees it."""
    stripped = re.sub(r"<!--.*?-->", " ", finding_region(text), flags=re.DOTALL)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def family_card_region(text: str) -> str:
    """The family card fragment alone.

    The three `0 of 19` renderings are separated only by their labels, so each label has to be
    asserted where it belongs. Whole-page membership cannot do that: swap the finding layer's
    label with the family banner's and both strings are still on the page, in each other's places.
    """
    opening = '<article class="card" aria-labelledby="family-summary">'
    start = text.index(opening)
    return text[start : text.index("</article>", start) + len("</article>")]


def non_claims_items(text: str) -> list[str]:
    """The non-claims, in order, as collapsed text.

    Neither carries a numeral of its own beyond the two ranks, so the staleness walk does not
    reach them and a deleted limit is invisible to every figure check. Spec 10.3 validates the
    list by exact length, order and value, and so does this.
    """
    region = finding_region(text)
    listing = region.split('<ul class="non-claims">', 1)[1].split("</ul>", 1)[0]
    return [
        " ".join(re.sub(r"<[^>]+>", " ", item.split("</li>", 1)[0]).split())
        for item in listing.split("<li>")[1:]
    ]


def lead_scale_rows(text: str) -> list[tuple[str, str]]:
    """The comparison's rows, in document order, as (modifier, fragment).

    The bars have to be read per row. Asserting that each flex value appears somewhere in the
    layer is order-free and row-free, so swapping the two rows' values leaves every string
    present and draws the contract's comparison backwards.

    Each row is cut at its own legend, which is its last element, so a row can never absorb the
    prose that follows the scale.
    """
    region = finding_region(text)
    rows = []
    for chunk in region.split('<div class="lead-scale-row ')[1:]:
        modifier = chunk.split('"', 1)[0]
        rows.append((modifier, chunk[: chunk.index("</p>") + len("</p>")]))
    return rows


def strip_flex(row: str, part: str) -> int | None:
    """The flex growth of one segment of a row's bar, or None when the segment is absent."""
    match = re.search(rf'<div class="strip-{part}" style="flex: (\d+);"', row)
    return None if match is None else int(match.group(1))


def apparatus_span(text: str) -> tuple[int, int]:
    """Index range of `details.technical-apparatus`, balancing the nested card disclosures.

    The family card and the pair card each carry their own `details`, so the first `</details>`
    after the opening tag closes a card's statistics block, not the apparatus.
    """
    start = text.index('<details class="technical-apparatus"')
    depth = 0
    for match in re.finditer(r"</?details\b", text[start:]):
        depth += 1 if match.group(0) == "<details" else -1
        if depth == 0:
            return start, text.index(">", start + match.end()) + 1
    raise AssertionError("details.technical-apparatus is never closed")


class TestPageReference:
    """T3.4 full-page reference: the second D1.3 gate.

    The document hierarchy and the public copy are approved here, before any renderer for the
    finding layer exists. A renderer written first would make its own assembly the baseline, which
    is the failure D1.3 exists to prevent and which the component reference already prevented once.

    Two properties are specific to this file. The apparatus must be closed, because a document that
    renders every component correctly and leaves them all immediately visible passes every other
    control and still fails the presentation contract. And the figures are real, per spec section
    12.1, so the usual fixture protection of invented numbers does not apply and staleness has to
    be guarded instead.
    """

    def test_the_reference_exists_and_says_what_it_is(self) -> None:
        """The stamp inverts, and an inverted stamp can invert too far.

        Copying the sibling fixtures' wording would put "every value on this page is invented" over
        the committed Experiment 1 figures, which is a false sentence on the one page whose purpose
        is truthful public copy. So the stamp is asserted to claim the opposite, and the sibling
        fixtures' claim is asserted absent.
        """
        assert PAGE_REFERENCE.is_file()
        text = page_reference_text()

        opening = '<div class="stamp-illustrative">'
        assert opening in text
        stamp = " ".join(text.split(opening, 1)[1].split("</div>", 1)[0].split())
        assert "Not a published result." in stamp
        assert "committed Experiment 1" in stamp
        assert "rather than invented ones" in stamp
        for sibling_claim in (
            "Every value on this page is invented",
            "No experiment has run.",
            "No experiment produced them.",
        ):
            assert sibling_claim not in stamp, sibling_claim
        assert "nineteen" in stamp
        assert "synthetic" in stamp
        assert text.index(opening) < text.index('<article class="card finding"')

    def test_the_apparatus_is_closed(self) -> None:
        """A reference that shipped the apparatus open would approve a hierarchy nobody meets.

        `open` on the element, or a second disclosure somewhere, and the reviewer sees the
        p-values, the identifiers and the provenance in the first reading, which is exactly what
        the contract moves out of it.
        """
        text = page_reference_text()
        assert text.count('<details class="technical-apparatus"') == 1

        start, _ = apparatus_span(text)
        opening_tag = text[start : text.index(">", start) + 1]
        assert "open" not in opening_tag, opening_tag
        assert "<summary>Show statistical details and audit trail</summary>" in text

    def test_no_stylesheet_rule_reveals_the_closed_apparatus(self) -> None:
        """The absence of an `open` attribute is not on its own a closed disclosure.

        A closed `details` hides its content through the engine's own rule, and CSS can override
        that: `::details-content { content-visibility: visible }`, or a `display` or `visibility`
        declaration on the apparatus's children, renders the whole technical half on the first
        screen while the markup still reads as closed and every containment assertion passes.
        Measuring the collapsed state in a browser is what proves it today, and that measurement
        does not run in CI, so the sheet is held to introducing nothing that could undo it.
        """
        rules = re.sub(r"/\*.*?\*/", " ", CARD_STYLESHEET, flags=re.DOTALL)

        assert "details-content" not in rules
        assert "content-visibility" not in rules
        for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", rules):
            if "details" in selector or "technical-apparatus" in selector:
                for property_name in ("display", "visibility", "!important"):
                    assert property_name not in body, f"{selector.strip()} sets {property_name}"

    def test_the_apparatus_holds_the_family_card_the_table_and_the_pair_card(self) -> None:
        """Siblings of the disclosure, not children of it, is the failure mode.

        Every component would render correctly and every figure would be right, and the reader
        would still meet the whole statistical apparatus on the first screen. Presence assertions
        cannot see the difference, so this one is about position.
        """
        text = page_reference_text()
        start, end = apparatus_span(text)

        for marker in (
            '<article class="card" aria-labelledby="family-summary">',
            '<div class="pair-table-block">',
            '<article class="card" aria-labelledby="pair-rank_3_vs_4',
        ):
            assert marker in text, marker
            assert start < text.index(marker) < end, f"{marker} is not inside the apparatus"

        # Nothing but the finding layer sits above the disclosure. Sliced from the body, because
        # the inlined stylesheet names every one of these classes and would answer for them.
        above = text[text.index('<main class="page">') : start]
        assert above.count('<article class="card') == 1
        assert 'class="card finding"' in above
        assert "pair-table-block" not in above

    def test_the_finding_layer_states_the_finding_and_nothing_technical(self) -> None:
        """Tier 1 prohibitions, asserted against the fragment rather than the page.

        A parenthetical p-value, a system identifier, the word Holm, a provenance line or a
        deviation label in the finding layer breaks the contract's uncontested first reading. The
        apparatus below carries all five legitimately, so the whole page cannot be the subject.
        """
        region = finding_region(page_reference_text())
        prose = finding_prose(page_reference_text())
        aggregates = json.loads(CORPUS_FILES["aggregates"].read_text(encoding="utf-8"))
        cards = json.loads(CORPUS_FILES["cards"].read_text(encoding="utf-8"))

        assert "holm" not in region.lower()
        assert "p-value" not in region.lower()
        assert re.search(r"\d\.\d", region) is None, "a decimal in the finding layer reads as a p"

        for entry in aggregates["entries"]:
            assert entry["system"] not in region, entry["system"]
        for pair in cards["pairs"].values():
            for side in ("system_a", "system_b"):
                assert pair["comparison"][side] not in region

        for banned in ("provenance", "revision", "fetched", "swe-bench", "deviation"):
            assert banned not in prose.lower(), banned
        assert cards["family"]["provenance"]["pinned_revision"] not in region

        # Total over deviation labels, not just D4. The codebase also cites D7, D1.9 and D1.11,
        # and a `D7` parenthetical is the same breach of Tier 1 as a `D4` one.
        label = re.search(r"\bd\d", prose.lower())
        assert label is None, f"a decision label in the finding layer: {label}"

    def test_the_lead_sentence_is_verbatim(self) -> None:
        """The binding sentence is the one line no later task may reword.

        It is checked on the collapsed prose rather than the raw HTML so that the fixture may wrap
        it across source lines, which is how every other fixture sets a paragraph.
        """
        assert LEAD_SENTENCE in finding_prose(page_reference_text())

    def test_the_analogy_scopes_its_superlative_to_neighboring_pairs(self) -> None:
        """Drop one word and the page states a falsehood with every figure still correct.

        The paragraph once read "The largest lead anywhere in the top 20 was 7". Measured against
        the corpus, the largest lead between neighbors is 7 and the largest lead anywhere on the
        board is 24, so that sentence was false and it contradicted the second non-claim, which
        says the result cannot speak to rank 1 against rank 20.

        No figure check reaches this. Remove "neighboring" and every numeral is still 7, still
        pinned to `results:primary.largest_observed_gap`, and still drawn correctly by the bar,
        because none of those assertions sees the subject of the sentence. Only the words do.
        """
        prose = finding_prose(page_reference_text())

        assert NEIGHBORING_SCOPE in prose, "the analogy's superlative is unscoped"
        assert "largest lead anywhere" not in prose, "the unscoped superlative is back"

    def test_the_analogy_keeps_the_necessary_not_sufficient_clause(self) -> None:
        """It carries no numeral, so the staleness walk cannot see it go.

        Spec 10.2 makes this a correctness requirement rather than a flourish: clearing the
        opening lead is necessary, not sufficient. Delete the clause and the analogy reads as if
        reaching the mark would have demonstrated a difference, which is a false claim about the
        procedure, and the rest of the paragraph still parses as ordinary prose.
        """
        prose = finding_prose(page_reference_text())

        assert NOT_SUFFICIENT_CLAUSE in prose, "the analogy now overclaims what the mark settles"

    def test_both_non_claims_are_present_in_order(self) -> None:
        """Half of contract item 5 could be deleted with the whole suite green.

        Neither limit carries a figure of its own, so no staleness anchor reaches the first one at
        all; the second survived only by the accident of naming two ranks. Spec 10.3 validates the
        list by exact length, order and value, and a limit is worth nothing if it can be dropped
        quietly, so this is exact rather than a membership check.

        The second limit says "not neighbors" rather than "non-adjacent". Tier 1 names one concept
        with one word: a general reader met "neighboring" four times and then "non-adjacent" once,
        and had to infer that the two name the same thing, inside the layer whose purpose is to
        remove inferences. The apparatus keeps "adjacent", which is the registered PREREG term and
        right for its audience.
        """
        board = corpus_value("aggregates:family_size")

        assert non_claims_items(page_reference_text()) == [
            "This does not show the systems are equivalent. Not finding a difference is not the "
            "same as showing there is none, and this experiment registered no equivalence test.",
            "This does not cover systems that are not neighbors. Only neighboring pairs were "
            f"compared, so it says nothing about how rank 1 compares with rank {board}.",
        ]

    def test_tier_1_names_one_concept_with_one_word(self) -> None:
        """Two words for one concept in the first reading is an inference the layer must not ask
        for. "adjacent" is the registered PREREG term and stays in the apparatus, where the
        audience knows it; the finding layer says "neighbors" throughout.

        The obvious way to satisfy the first half is a sweep, which would take the family card's
        registered wording with it, so the second half is asserted too. It names the strings
        rather than counting them, because a count would fail on any unrelated rewording in the
        apparatus and so would fail for the wrong reason.
        """
        text = page_reference_text()
        start, end = apparatus_span(text)
        apparatus = text[start:end]

        assert "adjacent" not in finding_region(text).lower()
        assert "Adjacent pairs only. Non-adjacent comparisons are out of scope." in apparatus
        assert "adjacent pairs separable" in apparatus
        assert "Largest observed adjacent gap" in apparatus
        assert "Every adjacent pair, as tested" in apparatus

    def test_every_finding_layer_figure_is_the_committed_corpus_value(self) -> None:
        """Spec 12.1's staleness guard, and it is total over the layer.

        A fixture carrying real numbers goes stale silently: a rerun moves the corpus, the page
        keeps quoting the old figures, and it still looks internally consistent. Checking the
        figures we happened to think of would leave the next one unguarded, so the spans the
        patterns capture are asserted to be exactly the digit runs in the layer.
        """
        prose = finding_prose(page_reference_text())

        spans = []
        for pattern, path in FINDING_FIGURES:
            match = re.search(pattern, prose)
            assert match is not None, f"no figure matched {pattern!r}"
            assert int(match.group(1)) == corpus_value(path), (
                f"{pattern!r} rendered {match.group(1)}, corpus {path} is {corpus_value(path)}"
            )
            spans.append(match.span(1))

        assert sorted(spans) == [match.span() for match in re.finditer(r"\d+", prose)], (
            "a numeral in the finding layer is not held to a source-qualified path"
        )

    def test_the_board_size_and_the_pair_family_size_are_not_swapped(self) -> None:
        """One name, two numbers, and every swapped rendering is individually plausible.

        `aggregates:family_size` is the 20 systems on the board; `results:primary.family_size` is
        the 19 adjacent pairs among them. Swapped, the page reads "top-19" and "0 of 20" with no
        type wrong and no figure absent from the corpus.
        """
        board = corpus_value("aggregates:family_size")
        pairs = corpus_value("results:primary.family_size")
        count = corpus_value("results:primary.headline.distinguishable_count")
        assert board != pairs, "the collision is gone, so this control proves nothing"

        prose = finding_prose(page_reference_text())
        assert f"no neighboring top-{board} pair" in prose
        assert f"{count} of {pairs} neighboring pairs" in prose
        assert f"The top {board} creates {pairs} neighboring comparisons" in prose

    def test_the_comparison_is_drawn_to_the_committed_figures(self) -> None:
        """The contract asks the reader to see 7 fall short of 10, so the bars carry the claim.

        Prose figures with a bar drawn to the wrong proportion is a copy defect the prose test
        cannot see: the numerals would all be correct and the picture would be wrong.

        The reverse is the same defect mirrored, and it is the one that actually happened: the
        analogy's sentence about the largest lead was wrong while every bar was right. So the
        three places the observed lead appears, the bar, the legend and the analogy prose, are
        asserted to read the one source rather than each being separately plausible.

        Each value is bound to its own row. Asserting only that `flex: 7`, `flex: 3` and
        `flex: 10` each appear somewhere in the layer is order-free and row-free: swap the two
        rows and all three strings survive, while the page draws the largest lead as a full track
        and the mark as seven tenths of one, which is the contract's comparison exactly backwards
        with both labels still correct.
        """
        prose = finding_prose(page_reference_text())
        lead = corpus_value("results:primary.largest_observed_gap")
        mark = corpus_value("results:primary.first_rejection_gap_floor")
        assert lead < mark, "the lead cleared the mark, so this page's copy no longer holds"

        rows = lead_scale_rows(page_reference_text())
        assert [modifier for modifier, _ in rows] == ["is-observed", "is-mark"]
        observed, marked = rows[0][1], rows[1][1]

        # The observed row: the fill is the lead, the remainder is what it fell short by.
        assert strip_flex(observed, "a") == lead
        assert strip_flex(observed, "b") == mark - lead
        assert f"<span>largest lead</span><span>{lead} tasks</span>" in observed

        # The mark row: one segment filling the track, so the track's end is the mark itself.
        assert strip_flex(marked, "a") == mark
        assert strip_flex(marked, "b") is None, "the mark row must fill its track"
        assert f"<span>minimum opening lead</span><span>{mark} tasks</span>" in marked

        for pattern in (r"largest lead (\d+) tasks", r"led by more than (\d+)\."):
            match = re.search(pattern, prose)
            assert match is not None, f"the observed lead is not stated by {pattern!r}"
            assert int(match.group(1)) == lead, f"{pattern!r} disagrees with the bar"

    def test_the_family_card_is_the_committed_family_card(self) -> None:
        """The apparatus quotes the engine, so it must quote it exactly.

        Hand-edited card figures inside a collapsed disclosure are the least likely thing on the
        page to be reread, and they are real values here rather than invented ones, so nothing
        about them looks wrong when they drift.

        `cards.json` is a validated intermediate and never an independent source of figures, so
        equality with the renderer alone would anchor the card to the intermediate rather than to
        the corpus. Each figure it renders is therefore also held to its path in `results.json`.
        """
        cards = json.loads(CORPUS_FILES["cards"].read_text(encoding="utf-8"))
        rendered = textwrap.indent(render_card(cards["family"]), "    ")

        assert rendered in page_reference_text()

        finding = cards["family"]["family_finding"]
        disclosure = finding["progressive_disclosure"]
        for path, value in (
            ("results:primary.separable_count", finding["headline"]["separable_count"]),
            ("results:primary.family_size", finding["headline"]["family_size"]),
            (
                "results:primary.first_rejection_gap_floor",
                finding["limit"]["first_rejection_gap_floor"],
            ),
            ("results:primary.largest_observed_gap", finding["limit"]["observed_extreme"]),
            ("results:primary.resolved_count", finding["observed"]["resolved_count"]),
            ("results:primary.first_critical", finding["criterion"]["threshold"]),
            # Not the headline counts, which are equal today and mean something else: the
            # secondary family is the pairs with a nonzero gap, and its floor is a gap.
            ("results:secondary.non_tied_family.size", disclosure["secondary_family_size"]),
            ("results:secondary.non_tied_family.gap_floor", disclosure["secondary_family_floor"]),
        ):
            assert value == corpus_value(path), f"{path} is {corpus_value(path)}, card says {value}"

    def test_the_pair_card_is_the_committed_pair_card_under_its_human_label(self) -> None:
        """Contract item 7: the first reading uses "Ranks 3 and 4", not `rank_3_vs_4`.

        The renderer still emits the raw identifier and the conversion lands in a later task, so
        the reference shows the approved target. This asserts the heading is the only difference,
        which is what stops the relabelling from becoming a licence to edit the card's figures.
        """
        cards = json.loads(CORPUS_FILES["cards"].read_text(encoding="utf-8"))
        rendered = render_card(cards["pairs"]["rank_3_vs_4"])
        relabelled = rendered.replace("Pair verdict: rank_3_vs_4", "Pair verdict: Ranks 3 and 4")
        assert relabelled != rendered, "the renderer no longer emits the raw identifier"

        text = page_reference_text()
        assert textwrap.indent(relabelled, "    ") in text

        heading = re.search(r"<h2 class=\"eyebrow\" id=\"pair-[^\"]+\">(.*?)</h2>", text)
        assert heading is not None
        assert heading.group(1) == "Pair verdict: Ranks 3 and 4"

        # Same reason as the family card: anchor the figures to the corpus, not the intermediate.
        results = json.loads(CORPUS_FILES["results"].read_text(encoding="utf-8"))
        row = next(pair for pair in results["pairs"] if pair["name"] == "rank_3_vs_4")
        card = cards["pairs"]["rank_3_vs_4"]
        assert card["ruler"]["split"] == [row["n10"], row["n01"]]
        assert card["ruler"]["observed_disagreements"] == row["n_discordant"]
        assert card["ruler"]["observed_net_edge"] == row["net_edge"]
        assert (
            card["ruler"]["required_net_edge_at_observed"] == row["required_net_edge_at_observed"]
        )
        assert card["test"]["p_value"] == row["p_value"]
        assert card["test"]["adjusted_p_value"] == row["adjusted_p_value"]
        assert card["mde"]["instances"] == row["mde"]["instances"]
        assert card["mde"]["discordance_rate"] == row["discordance_rate"]
        assert card["verdict"] == row["verdict"]

    def test_the_three_identical_figures_keep_their_distinct_labels(self) -> None:
        """Two quantities, three renderings, and on this data all three are the same characters.

        The finding layer prints the observed count, the family banner prints `separable_count`
        and the family card's observed line prints `resolved_count`. No value check can tell them
        apart, so the labels are the whole guard.

        Each label is therefore asserted in its own region and refused in the other. Whole-page
        membership is not a three-way control: swap the finding layer's label with the family
        banner's and both strings are still on the page, each in the other's place, and every
        `in text` assertion still passes.
        """
        text = page_reference_text()
        figure = (
            f"{corpus_value('results:primary.headline.distinguishable_count')} "
            f"of {corpus_value('results:primary.family_size')}"
        )
        assert corpus_value("results:primary.separable_count") == corpus_value(
            "results:primary.headline.distinguishable_count"
        )
        assert corpus_value("results:primary.resolved_count") == corpus_value(
            "results:primary.headline.distinguishable_count"
        )

        finding = finding_region(text)
        family = family_card_region(text)
        assert text.count(figure) == 3
        assert finding.count(figure) == 1
        assert family.count(figure) == 2

        observed_label = f"<b>{figure}</b> neighboring pairs showed a reliable difference"
        separable_label = f"<b>{figure}</b> adjacent pairs separable"
        resolved_label = f"<dt>Resolved by the observed test</dt><dd>{figure}</dd>"

        assert observed_label in finding
        assert separable_label not in finding
        assert resolved_label not in finding

        assert separable_label in family
        assert resolved_label in family
        assert observed_label not in family

    def test_the_reduced_table_says_it_is_reduced(self) -> None:
        """Section 1.2: a reduced row count in a fixture must establish nothing about production.

        The layout exploration that showed fewer rows is the reason this sentence is required on
        the page's face rather than left to the spec.

        The row count is spelled out in words on the page, in both the stamp and the note, and a
        digit-anchored guard cannot see a spelled number: move the pair family size and every
        numeral test would fail while "nineteen" sat there stale. So the word is derived from the
        corpus rather than hardcoded here.
        """
        text = page_reference_text()
        start, end = apparatus_span(text)
        body = text.split("<tbody>", 1)[1].split("</tbody>", 1)[0]

        family_size = corpus_value("results:primary.family_size")
        assert family_size in SPELLED_NUMBERS, f"no spelled form registered for {family_size}"
        spelled = SPELLED_NUMBERS[family_size]

        assert body.count("<tr>") == 4
        apparatus = text[start:end]
        assert spelled in apparatus
        assert "fixture convenience" in apparatus

        stamp = " ".join(
            text.split('<div class="stamp-illustrative">', 1)[1].split("</div>", 1)[0].split()
        )
        assert spelled in stamp

    def test_the_reference_inlines_the_current_stylesheet(self) -> None:
        """The same drift `verdict_reference.html` already demonstrates, on the page that fixes
        the hierarchy. That file inlines a copy taken before `card.css` gained its
        `.card-rail.is-resolved` block and has been stale ever since. A stale copy here would
        approve a layout the renderer never produces, which is worse than a stale component.
        """
        text = page_reference_text()
        inlined = text.split("<style>\n", 1)[1].split("</style>", 1)[0]

        assert inlined == CARD_STYLESHEET

    def test_the_new_rules_introduce_no_literal_colour(self) -> None:
        """Dark mode is driven entirely by tokens, so one literal silently breaks it.

        The three `:root` blocks are the only place a colour value belongs. A hardcoded hex reads
        correctly in whichever mode it was authored in and is invisible until someone opens the
        page in the other one.
        """
        rules = CARD_STYLESHEET.split(':root[data-theme="light"]', 1)[1].split("}", 1)[1]
        # Comments are prose about colour and are allowed to name one; declarations are not.
        rules = re.sub(r"/\*.*?\*/", " ", rules, flags=re.DOTALL).lower()

        assert re.search(r"#[0-9A-Fa-f]{3,8}\b", rules) is None
        assert re.search(r"\b(rgba?|hsla?)\(", rules) is None
        named = r"white|black|grey|gray|red|green|blue|orange|yellow|silver|teal|navy"
        assert re.search(rf"(?<![-\w])({named})(?![-\w])", rules) is None
