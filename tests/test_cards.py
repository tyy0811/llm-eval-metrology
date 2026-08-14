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
from html.parser import HTMLParser
from pathlib import Path

import pytest

from metrology.cards import (
    CARD_STYLESHEET,
    render_card,
    render_document,
    ruler_marker_class,
)
from metrology.reporting import (
    FINDINGS_COLUMNS,
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
SPELLED_NUMBERS = {4: "four", 19: "nineteen", 20: "twenty", 21: "twenty one"}

#: The apparatus's own summary, which is the only control on the page and the whole of its
#: invitation to open the technical half. Declared here so the totality assertion below claims it.
APPARATUS_SUMMARY = "Show statistical details and audit trail"

#: The reference table's caption. Held as a whole string rather than a substring: an `in` check
#: passes an appended clause, so `Every adjacent pair, as tested` could grow `, though several were
#: later retested and reversed` with nothing failing.
TABLE_CAPTION = "Every adjacent pair, as tested"

#: The reduced table's four synthetic rows, cell by cell, in document order. Nothing read these
#: cells before: the repdigit guard that refuses a cell which could pass for a measurement is in
#: `TestTableReference`, which only ever opens the sibling fixture.
REDUCED_TABLE_ROWS = (
    ("illustrative_a_vs_b", "1111", "9999", "1.000", "1.000"),
    ("illustrative_b_vs_c", "3333", "9999", "0.888", "1.000"),
    ("illustrative_c_vs_d", "5555", "9999", "0.555", "1.000"),
    ("illustrative_d_vs_e", "7777", "9999", "0.222", "1.000"),
)

#: The table block's D4 disclosure. It states which of the five columns carry the harness
#: comparability caveat and which do not, so an edit to it changes what a reader believes about the
#: provenance of every cell above it.
PAIR_TABLE_NOTE = (
    "The observed discordance and both p-value columns read per-instance artifacts and carry the "
    "D4 harness comparability caveat: submissions do not record their harness version. The pair "
    "identity and the resolved-count gap derive from published aggregates and do not."
)

#: How many rows the reference's table shows. A fixture choice, not a corpus figure: the shipped
#: document carries every adjacent pair, and section 1.2 turns on the page saying so. Derived from
#: the declared rows so the spelled word, the `<tr>` count and the cells cannot disagree.
REDUCED_ROWS = len(REDUCED_TABLE_ROWS)

#: The page's `<title>`, which a reader meets in the tab strip and in a bookmark before meeting any
#: of the document. It sits in `<head>`, so no walk bounded by `<body>` reaches it.
PAGE_TITLE = "Card set page reference"

#: The `h1`. It carries the same words as the title today and is pinned separately, because they are
#: two regions: the tab strip and the largest type on the page.
PAGE_HEADING = "Card set page reference"

#: The stamp's headline, which is the whole of what the page says about its own status in the type
#: size a skimming reader reads.
STAMP_HEADLINE = "Layout and copy reference. Not a published result."

#: The two-line note under the `h1`.
INTRO_NOTE = (
    "The whole document, in the order a reader meets it. Notes for review are at the foot of the "
    "page."
)

#: The heading over the review commentary at the foot of the page.
REVIEW_NOTES_HEADING = "Notes for review"

#: The review commentary itself. Pinned flat, with nothing derived: every numeral in it is a fact
#: about the page rather than a corpus figure, so there is nothing here that can go stale when the
#: corpus moves. That is not true of the stamp, which is why `stamp_body_literal` exists.
REVIEW_NOTES = (
    "The question this page exists to answer: does a reader who sees only the first screen come "
    "away with a correct, complete and non-misleading understanding of the finding? Everything "
    "above the disclosure is that first reading. It states no significance value, names no system, "
    "uses the correction's name nowhere, shows no provenance and carries no deviation label, and a "
    "test asserts each of those against that fragment rather than against the page. The disclosure "
    "is closed by default and live, which is what a first-time reader meets. A reference that "
    "shipped it open would approve a hierarchy nobody encounters, and would be the same failure as "
    "approving a renderer's own output. The comparison under the headline is two measures on one "
    "scale whose full length is the mark, so the observed lead is seen to stop short of it rather "
    "than described as doing so. It reuses the discordance strip rather than the pair card's "
    "ruler, and the reason is a measurement: the ruler's marker labels are short enough to sit "
    'either side of one track and "minimum opening lead" is not, so at a 320px viewport two '
    "centred labels would overlap. The finding layer carries no review annotations, unlike the "
    "sibling fixtures. It is the copy under approval, and tags interleaved with it would change "
    "the reading being judged. The annotations on the table are the same device as in "
    "table_reference.html, for review only, and the renderer does not emit them. The pair card is "
    'headed "Ranks 3 and 4". The renderer emits "rank_3_vs_4" today; the conversion is built in a '
    "later task and the approved target is what is shown here. The document renders the same "
    "figure three times, for two different quantities: the observed count in the finding layer, "
    "the separable count on the family banner, and the resolved count on the family card's "
    "observed line. The characters are identical in all three, so only their labels tell them "
    "apart, and collapsing the apparatus is what keeps the first reading down to one of them."
)


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


def collapse(fragment: str) -> str:
    """One HTML fragment as the reader sees its words: no tags, no comments, single spaces.

    Tags become a space rather than nothing, so that two adjacent inline elements do not run their
    words together. That leaves a space before the punctuation that follows an inline element, as
    in `<code>table_reference.html</code>.`, which the reader never sees, so it is closed up again.

    Two limits, neither reachable by the copy this guards. The tag pattern is a regex, not a
    parser, so a literal `<` or `>` in prose would be misread as a tag: none exists, and none can
    while the copy carries no comparison operators. And the punctuation closeup would silently
    normalize an authored `word .` typo, which is a typographic defect rather than a change of
    meaning, which is why the substitution is limited to whitespace before `.,;:`.
    """
    stripped = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
    words = " ".join(re.sub(r"<[^>]+>", " ", stripped).split())
    return re.sub(r"\s+([.,;:])", r"\1", words)


def finding_prose(text: str) -> str:
    """The finding layer with tags removed and whitespace collapsed, as a reader sees it."""
    return collapse(finding_region(text))


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
    return [collapse(item.split("</li>", 1)[0]) for item in listing.split("<li>")[1:]]


#: Elements that hold reader-facing prose in Tier 1. Text outside one of these is text no declared
#: literal can claim, which is the condition `tier_1_text_units` exists to detect.
TEXT_UNITS = frozenset({"p", "li"})

#: The same, for the technical apparatus, which carries a disclosure control and a table as well as
#: prose. A `th` and a `td` are read aloud one at a time and are as much reader-facing text as a
#: paragraph is; the summary is the only words a reader sees before deciding to open the half.
APPARATUS_TEXT_UNITS = TEXT_UNITS | frozenset({"summary", "caption", "th", "td"})

#: The same again, for the page furniture around those two regions: the stamp is a `strong` and a
#: `span`, the page has an `h1` and the review notes an `h2`.
#:
#: A unit set is not an enumeration of what is guarded. It names what a declared literal is allowed
#: to claim; text in any element outside it lands in `unclaimed` and fails on its own. Adding a unit
#: type therefore never widens what passes, which is what separates this from a list of regions.
PAGE_TEXT_UNITS = TEXT_UNITS | frozenset({"h1", "h2", "strong", "span"})

#: Void elements, which never close. `<hr class="card-rail">` is one, and treating it as an open
#: element would unbalance the parse stack and swallow everything after it.
VOID_ELEMENTS = frozenset({"hr", "br", "img", "input", "meta", "link", "source", "wbr"})

#: Attributes that put words in front of a reader without putting them in the document text.
#: `data-element` is here because `card.css` renders it: `.eyebrow::after` and
#: `.pair-table-block [data-element]::after` both set `content: attr(data-element)`, so its value is
#: printed text in the apparatus and not markup metadata.
READER_ATTRIBUTES = frozenset({"aria-label", "alt", "title", "data-element"})

#: Attributes that can take a span the parser reads off the page a reader sees. `hidden` removes it
#: outright; `style` can carry `display: none` and beats any stylesheet rule that has no
#: `!important`. Collected rather than banned, because the comparison bars use `style` legitimately.
PRESENTATION_ATTRIBUTES = frozenset({"style", "hidden"})


class DeclaredTextReader(HTMLParser):
    """Collects every reader-facing text unit in a fragment, and any text no unit claims.

    A real parse rather than a selector list, because a selector list is an enumeration and this
    exists to stop enumerating. Text in an element nobody thought to name lands in `unclaimed`.

    Named for the property rather than for Tier 1, because both tiers use it. The unit set is a
    parameter: Tier 1 is prose only, the apparatus also holds a disclosure summary and a table.
    """

    def __init__(self, text_units: frozenset[str] = TEXT_UNITS) -> None:
        super().__init__(convert_charrefs=True)
        self.text_units = text_units
        self.stack: list[str] = []
        self.open_units: list[int] = []
        self.units: list[tuple[str, list[str]]] = []
        self.unclaimed: list[str] = []
        self.reader_attributes: list[tuple[str, str, str]] = []
        self.presentation_attributes: list[tuple[str, str, str]] = []

    def _record_attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in READER_ATTRIBUTES:
                self.reader_attributes.append((tag, name, value or ""))
            if name in PRESENTATION_ATTRIBUTES:
                self.presentation_attributes.append((tag, name, value or ""))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_attributes(tag, attrs)
        if tag in VOID_ELEMENTS:
            return
        self.stack.append(tag)
        if tag in self.text_units:
            self.units.append((tag, []))
            self.open_units.append(len(self.units) - 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_attributes(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_ELEMENTS:
            return
        while self.stack:
            popped = self.stack.pop()
            if popped in self.text_units and self.open_units:
                self.open_units.pop()
            if popped == tag:
                return

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        if self.open_units:
            self.units[self.open_units[-1]][1].append(data)
        else:
            self.unclaimed.append(" ".join(data.split()))


def parse_text_units(fragment: str, text_units: frozenset[str] = TEXT_UNITS) -> DeclaredTextReader:
    """Parse any fragment into its reader-facing units."""
    parser = DeclaredTextReader(text_units)
    parser.feed(re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL))
    parser.close()
    return parser


def declared_units(reader: DeclaredTextReader) -> list[tuple[str, str]]:
    """One reader's units as (tag, collapsed text), which is the form the pins are written in."""
    return [(tag, collapse(" ".join(chunks))) for tag, chunks in reader.units]


def tier_1_text_units(text: str) -> DeclaredTextReader:
    """Parse the finding layer into its reader-facing units."""
    return parse_text_units(finding_region(text))


def finding_readings(text: str) -> list[str]:
    """The finding layer's prose paragraphs, in order, as collapsed text.

    A substring pin guards its own characters and leaves its neighbourhood open: a hedge prepended
    to a pinned sentence, or a reversal appended after a pinned clause, changes what the paragraph
    means while the pinned span survives untouched. Returning the whole paragraph is what lets the
    assertion be `==` rather than `in`.
    """
    return [
        collapse(body)
        for body in re.findall(
            r'<p class="reading">(.*?)</p>', finding_region(text), flags=re.DOTALL
        )
    ]


def apparatus_note(text: str) -> str:
    """The reference's own note above the table, as collapsed text.

    It is fixture furniture rather than renderer output, so the family card's fragment-equality
    test does not reach it, and it is the only place the page states that the shipped table
    carries every adjacent pair. Section 1.2 rests on that sentence.
    """
    start, end = apparatus_span(text)
    notes = re.findall(r'<p class="note">(.*?)</p>', text[start:end], flags=re.DOTALL)
    assert len(notes) == 1, f"expected one note in the apparatus, found {len(notes)}"
    return collapse(notes[0])


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


def rendered_card_fragments() -> dict[str, str]:
    """The two card fragments the apparatus quotes, exactly as the renderer emits them.

    The pair card carries contract item 7's human label, which is the one edit the reference makes
    to renderer output. Built once and shared, so the excision below and the fragment-equality
    tests cannot disagree about what counts as renderer output.
    """
    cards = json.loads(CORPUS_FILES["cards"].read_text(encoding="utf-8"))
    pair = render_card(cards["pairs"]["rank_3_vs_4"])
    relabelled = pair.replace("Pair verdict: rank_3_vs_4", "Pair verdict: Ranks 3 and 4")
    assert relabelled != pair, "the renderer no longer emits the raw identifier"
    return {
        "family": textwrap.indent(render_card(cards["family"]), "    "),
        "pair": textwrap.indent(relabelled, "    "),
    }


def apparatus_outside_the_rendered_cards(text: str) -> str:
    """The apparatus with the two renderer-output fragments cut out.

    Those two regions are already total by construction: they are asserted equal to
    `render_card(...)` character for character, so nothing can be added inside them. Everything
    else in the apparatus is fixture copy that no such equality reaches, and it is what the
    totality assertion has to account for.

    The excision is only sound while each fragment really is present verbatim exactly once, so
    that is asserted rather than assumed. A silent no-op replace would leave the card text in the
    region and turn a precise failure into a confusing one.
    """
    start, end = apparatus_span(text)
    apparatus = text[start:end]
    for name, fragment in rendered_card_fragments().items():
        assert apparatus.count(fragment) == 1, (
            f"the {name} card is not renderer output in the apparatus exactly once, so fragment "
            "equality does not cover it and cutting it out here would hide an edit"
        )
        apparatus = apparatus.replace(fragment, "\n")
    return apparatus


def apparatus_text_units(text: str) -> DeclaredTextReader:
    """Parse the apparatus, minus the fragment-equality regions, into its reader-facing units."""
    return parse_text_units(apparatus_outside_the_rendered_cards(text), APPARATUS_TEXT_UNITS)


def apparatus_table(text: str) -> str:
    """The table inside `page_reference.html`, which is not the sibling fixture's table.

    Every table assertion in this file until now read `table_reference.html`. This page embeds its
    own copy, and no test had ever opened it.
    """
    apparatus = apparatus_outside_the_rendered_cards(text)
    assert apparatus.count("<table") == 1, "expected one table in the apparatus"
    return apparatus.split("<table", 1)[1].split("</table>", 1)[0]


def table_caption(text: str) -> str:
    """The embedded table's caption, whole, as a reader sees it."""
    captions = re.findall(r"<caption\b[^>]*>(.*?)</caption>", apparatus_table(text), re.DOTALL)
    assert len(captions) == 1, f"expected one caption, found {len(captions)}"
    return collapse(captions[0])


def apparatus_note_literal() -> str:
    """The reference's own note above the table, as it must read.

    One declaration, read both by the note's own test and by the totality assertion, so the
    apparatus cannot be total against one wording while the note test holds a different one.

    The row count and the family size are spelled out in words on the page, and a digit-anchored
    guard cannot see a spelled number, so both words are derived from their source rather than
    typed: move the pair family size and every numeral test would fail while "nineteen" sat stale.
    """
    family_size = corpus_value("results:primary.family_size")
    for spelled_out in (family_size, REDUCED_ROWS):
        assert spelled_out in SPELLED_NUMBERS, f"no spelled form registered for {spelled_out}"
    shipped, shown = SPELLED_NUMBERS[family_size], SPELLED_NUMBERS[REDUCED_ROWS]
    return (
        f"The shipped document carries all {shipped} adjacent pairs in this table, and both "
        f"selected pair cards. The {shown} rows below are a fixture convenience and establish "
        "nothing about which pairs ship: the table is built from every adjacent pair, and the "
        f"pair cards come from the registered selection rule. These {shown} rows and their cell "
        "figures are synthetic, as approved in table_reference.html."
    )


def stamp_body_literal() -> str:
    """The stamp's second block, as it must read.

    The stamp is the only page furniture that quotes the corpus, and it quotes it in words: the
    reduced row count and the pair family size are both spelled out, where no digit-anchored guard
    can see them. Both are derived here for the same reason `apparatus_note_literal` derives them,
    so that moving the family size fails this pin rather than leaving "nineteen" sitting stale.
    """
    family_size = corpus_value("results:primary.family_size")
    for spelled_out in (family_size, REDUCED_ROWS):
        assert spelled_out in SPELLED_NUMBERS, f"no spelled form registered for {spelled_out}"
    shipped, shown = SPELLED_NUMBERS[family_size], SPELLED_NUMBERS[REDUCED_ROWS]
    return (
        "The finding layer and both cards carry the committed Experiment 1 figures rather than "
        "invented ones, because public copy cannot be judged against quantities that are not "
        "real, and a test holds each of them to the corpus at its declared source path. The table "
        f"is the exception: its {shown} rows stand in for the {shipped} the shipped document "
        "carries, which is a fixture convenience that settles nothing about which pairs ship, and "
        "its cell figures stay synthetic."
    )


def page_body(text: str) -> str:
    """The document's `<body>`, whole.

    The bound is the body rather than the file because the inlined `<style>` block is not prose and
    `HTMLParser` hands its whole content back as text. That block is held byte-equal to `card.css`
    by `test_the_reference_inlines_the_current_stylesheet`, and `<title>` is the only other
    reader-facing string in `<head>`; it is pinned by name rather than left to this bound.
    """
    start = text.index("<body>")
    return text[start : text.index("</body>") + len("</body>")]


def body_outside_the_total_regions(text: str) -> str:
    """The body with the finding layer and the technical apparatus cut out.

    Both are already total: every reader-facing span in each is claimed by exactly one declared
    literal, so re-declaring them here would duplicate two long lists and let the page be total
    against one wording while its own region held another. The same excision pattern as
    `apparatus_outside_the_rendered_cards`, one level up.

    The excision is only sound while each region appears verbatim exactly once, so that is asserted
    rather than assumed: a silent no-op replace would leave the region's text in the residue and
    turn a precise failure into a confusing one.
    """
    body = page_body(text)
    apparatus_start, apparatus_end = apparatus_span(text)
    regions = (
        ("finding layer", finding_region(text)),
        ("technical apparatus", text[apparatus_start:apparatus_end]),
    )
    for name, fragment in regions:
        assert body.count(fragment) == 1, (
            f"the {name} does not appear in the body exactly once, so its own totality assertion "
            "does not cover it and cutting it out here would hide an edit"
        )
        body = body.replace(fragment, "\n")
    return body


def page_text_units(text: str) -> DeclaredTextReader:
    """Parse the page furniture, minus the two already-total regions, into its reader-facing units."""
    return parse_text_units(body_outside_the_total_regions(text), PAGE_TEXT_UNITS)


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

        The summary is pinned exactly, and it is read as the first one inside the disclosure so it
        is the apparatus's own rather than a card's nested `Statistics` block. Membership against
        the whole page cannot make that distinction, and the summary is the whole of what a reader
        sees before deciding whether the technical half is worth opening.
        """
        text = page_reference_text()
        assert text.count('<details class="technical-apparatus"') == 1

        start, end = apparatus_span(text)
        opening_tag = text[start : text.index(">", start) + 1]
        assert "open" not in opening_tag, opening_tag

        summaries = re.findall(r"<summary\b[^>]*>(.*?)</summary>", text[start:end], re.DOTALL)
        assert summaries, "the apparatus has no summary"
        assert collapse(summaries[0]) == APPARATUS_SUMMARY

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

    def test_the_apparatus_holds_the_family_card_the_table_and_the_pair_card_in_order(self) -> None:
        """Siblings of the disclosure, not children of it, is the failure mode.

        Every component would render correctly and every figure would be right, and the reader
        would still meet the whole statistical apparatus on the first screen. Presence assertions
        cannot see the difference, so this one is about position.

        The order is asserted too, and it is the seam between this file's two totality mechanisms.
        Spec 11.1 fixes the apparatus as the family card, then the table of every adjacent pair,
        then the pair cards: the family result bounds what any single pair can show, so a reader
        who meets a pair card first meets a specific comparison before the limit that governs it.

        Swapping the two `<article>` elements passed all 105 tests. Neither mechanism can see that
        axis. Fragment equality asks whether each card appears verbatim somewhere, not where;
        `apparatus_outside_the_rendered_cards` then deletes each fragment by exact string match
        wherever it occurs, so the residue handed to the totality parser is identical whichever
        card came first, and the declared unit list is unchanged. Containment bounded each marker
        inside the disclosure without ever ordering them against each other. It is the boundary
        between "total by fragment equality" and "total by declared literal", and nothing owned it.
        """
        text = page_reference_text()
        start, end = apparatus_span(text)

        markers = (
            '<article class="card" aria-labelledby="family-summary">',
            '<div class="pair-table-block">',
            '<article class="card" aria-labelledby="pair-rank_3_vs_4',
        )
        for marker in markers:
            assert marker in text, marker
            assert start < text.index(marker) < end, f"{marker} is not inside the apparatus"

        positions = [text.index(marker) for marker in markers]
        assert positions == sorted(positions), (
            "spec 11.1 orders the apparatus family card, then table, then pair cards; this page "
            f"orders them {[markers[i][:40] for i in sorted(range(3), key=positions.__getitem__)]}"
        )

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

    def test_every_word_a_reader_sees_in_tier_1_is_declared(self) -> None:
        """Total over the first reading: every word a reader sees in Tier 1 is claimed by exactly
        one declared literal, and nothing else is there.

        Three consecutive rounds of enumerated pins each missed a different unpinned span. Round 1
        pinned two sentences and left the text beside them open, so a prepended hedge and an
        appended reversal both passed. Round 2 pinned two paragraphs and left the lead sentence
        out because a substring check made it look guarded, so appending "Though a difference
        might still exist." to the most-read line in the document reversed its headline claim with
        the whole class green. Enumeration is the defect; each round it protects what was named
        last time and leaves whatever was not.

        So this asserts the shape rather than the members. The layer is parsed, not matched:
        every `p` and every `li` is extracted in document order with its text, the list is compared
        with `==`, and any text found outside a text unit is a violation in itself. An added,
        deleted, reordered or edited paragraph all fail, and so does prose smuggled into an element
        nobody thought to name, or into an `aria-label` where a screen reader would still read it.

        The substring pins below stay. They cost nothing and each names a specific regression;
        this sits above them rather than replacing them.
        """
        board = corpus_value("aggregates:family_size")
        pairs = corpus_value("results:primary.family_size")
        count = corpus_value("results:primary.headline.distinguishable_count")
        items = corpus_value("aggregates:n_items")
        lead = corpus_value("results:primary.largest_observed_gap")
        mark = corpus_value("results:primary.first_rejection_gap_floor")

        reader = tier_1_text_units(page_reference_text())

        assert declared_units(reader) == [
            (
                "p",
                "Using the statistical test chosen in advance, no neighboring "
                f"top-{board} pair showed a reliable difference.",
            ),
            ("p", f"{count} of {pairs} neighboring pairs showed a reliable difference"),
            (
                "p",
                f"The top {board} creates {pairs} neighboring comparisons, each measured on "
                f"{items} tasks.",
            ),
            ("p", f"largest lead {lead} tasks"),
            ("p", f"minimum opening lead {mark} tasks"),
            (
                "p",
                "It works like a qualifying mark. Before a difference between two neighboring "
                f"systems could count as reliable, that pair needed a lead of at least {mark} "
                f"tasks. No neighboring pair anywhere in the top {board} led by more than {lead}. "
                "None reached the mark, so none could qualify. Reaching the mark would not have "
                "settled a comparison on its own; it is the point at which the question becomes "
                "answerable at all.",
            ),
            (
                "p",
                "Task-by-task results add detail but cannot change this. A pair's lead sets a "
                f"ceiling on how strong its evidence can get, and a lead of {lead} stays under "
                "the mark even if every task the two systems disagreed on had gone the same way. "
                "The headline follows from the published totals alone.",
            ),
            (
                "li",
                "This does not show the systems are equivalent. Not finding a difference is not "
                "the same as showing there is none, and this experiment registered no equivalence "
                "test.",
            ),
            (
                "li",
                "This does not cover systems that are not neighbors. Only neighboring pairs were "
                f"compared, so it says nothing about how rank 1 compares with rank {board}.",
            ),
        ]

        assert reader.unclaimed == [], "Tier 1 text outside any declared unit"
        assert reader.reader_attributes == [], "Tier 1 words a declared literal does not cover"

    def test_the_tier_1_reader_detects_what_it_claims_to_detect(self) -> None:
        """Two of the assertions above compare against an empty list, and an empty list is what a
        detector that never fires also produces.

        So the detector is run against a fragment built to contain exactly what it is supposed to
        catch: text loose in a section, text in an element nobody named, and words in an
        `aria-label` that a screen reader would read out. Without this, the totality claim rests on
        collections that might simply never be populated.
        """
        reader = parse_text_units(
            '<article class="card finding">\n'
            '  <hr class="card-rail">\n'
            "  <section>\n"
            '    <p class="finding-lead">declared</p>\n'
            "    loose in a section\n"
            "    <blockquote>inside an element nobody named</blockquote>\n"
            '    <div aria-label="read aloud, printed nowhere"></div>\n'
            '    <ul class="non-claims"><li>a limit</li></ul>\n'
            "  </section>\n"
            "</article>"
        )

        assert declared_units(reader) == [("p", "declared"), ("li", "a limit")]
        assert reader.unclaimed == ["loose in a section", "inside an element nobody named"]
        assert reader.reader_attributes == [("div", "aria-label", "read aloud, printed nowhere")]

    def test_every_word_a_reader_sees_in_the_apparatus_is_declared(self) -> None:
        """Total over the technical half, on the same terms as Tier 1: every reader-facing span in
        `details.technical-apparatus` that fragment equality does not already own is claimed by
        exactly one declared literal, and nothing else is there.

        Round 3 made Tier 1 total and left the apparatus enumerated, and the same defect was alive
        in it. Inserting

            <p>A follow-up re-analysis using a less conservative correction found several of these
            pairs to be separable after all, which the family gate above does not reflect.</p>

        between the family card's `</article>` and the fixture note passed the whole class, because
        no assertion had ever looked at that region for extraneous content. It is a fabricated
        finding that contradicts the family card two lines above it, and the reader who opens the
        apparatus is precisely the reader who chose to dig past the headline to check.

        Appending to the table caption passed for the same reason one level down:
        `test_tier_1_names_one_concept_with_one_word` asked for the caption with `in`, so
        `Every adjacent pair, as tested` could grow `, though several were later retested and
        reversed` and stay green.

        The apparatus differs from Tier 1 in one way this exploits. The family card and the pair
        card are renderer output held character for character against `render_card(...)`, so they
        are already total by construction and are cut out rather than re-declared. What remains is
        fixture copy: the summary, the note, the table and anything between or around them.

        Units are widened past `p` and `li` because the apparatus is not only prose. A `th` and a
        `td` are read out one cell at a time, a `caption` names the whole table, and the summary is
        the only text a reader sees before deciding to open the half. `data-element` is a reader
        attribute here because `card.css` prints it: `.pair-table-block [data-element]::after` sets
        `content: attr(data-element)`, so its value is text on the page, not markup metadata.
        """
        reader = apparatus_text_units(page_reference_text())

        assert declared_units(reader) == [
            ("summary", APPARATUS_SUMMARY),
            ("p", apparatus_note_literal()),
            ("caption", TABLE_CAPTION),
            *[("th", column) for column in FINDINGS_COLUMNS],
            *[("td", cell) for row in REDUCED_TABLE_ROWS for cell in row],
            ("p", PAIR_TABLE_NOTE),
        ]

        assert reader.unclaimed == [], "apparatus text outside any declared unit"
        assert reader.reader_attributes == [
            ("div", "aria-label", "Pair table"),
            ("caption", "data-element", "pair table"),
            ("p", "data-element", "D4 disclosure"),
        ]

    def test_the_apparatus_reader_detects_what_it_claims_to_detect(self) -> None:
        """The apparatus totality rests on two comparisons against an empty list, and an empty list
        is also what a detector wired to nothing produces.

        The Tier 1 detector test does not cover this configuration: the unit set is wider here, so
        a `th`, a `td`, a `caption` and a `summary` have to be shown landing in `units` rather than
        in `unclaimed`, and the reverse for a `dd`, which no declared literal claims. The
        `data-element` annotation is shown being collected, because it is printed by the sheet and
        a reader sees it.

        `presentation_attributes` is asserted empty against the real apparatus too, so `style` and
        `hidden` are shown here being collected. Tier 1's declared list of them is non-empty and so
        is self-falsifying; this one would not be.
        """
        reader = parse_text_units(
            '<details class="technical-apparatus">\n'
            "  <summary>a control</summary>\n"
            "  loose in the disclosure\n"
            '  <table><caption data-element="a tag">a caption</caption>\n'
            "    <thead><tr><th>a header</th></tr></thead>\n"
            "    <tbody><tr><td>a cell</td></tr></tbody>\n"
            "  </table>\n"
            "  <dl><dt>a term</dt><dd>a definition</dd></dl>\n"
            "  <p hidden>read by the parser, never by a reader</p>\n"
            '  <div style="display: none">effaced the same way</div>\n'
            "</details>",
            APPARATUS_TEXT_UNITS,
        )

        assert declared_units(reader) == [
            ("summary", "a control"),
            ("caption", "a caption"),
            ("th", "a header"),
            ("td", "a cell"),
            ("p", "read by the parser, never by a reader"),
        ]
        assert reader.unclaimed == [
            "loose in the disclosure",
            "a term",
            "a definition",
            "effaced the same way",
        ]
        assert reader.reader_attributes == [("caption", "data-element", "a tag")]
        assert reader.presentation_attributes == [
            ("p", "hidden", ""),
            ("div", "style", "display: none"),
        ]

    def test_every_word_a_reader_sees_on_the_page_is_declared(self) -> None:
        """Total over the whole document: every reader-facing span in `<body>` that one of the two
        region assertions does not already own is claimed by exactly one declared literal, plus the
        `<title>` outside it, and nothing else is there.

        **The defect moves to whatever was not enumerated.** That is the one finding this file has
        produced, six times, and every previous round answered it by naming one more region. Round 1
        pinned two sentences, so the text beside them took the defect. Round 2 pinned two
        paragraphs, so the lead sentence took it. Round 3 made Tier 1 total, so the apparatus took
        it. Round 4 made the apparatus total, so the ordering seam between the two took it. Round 5
        closed the seam, and it moved to the four regions nobody had ever named: rewriting the `h1`
        to `Several top-20 pairs are separable after all` passed 107 of 107, and so did a fabricated
        reproduction claim under the stamp, a fabricated reversal in the notes at the foot, and a
        rewritten `<title>`.

        A sixth region check would relocate it a seventh time. So the subject here is the body, and
        the two regions that are already total are cut out rather than re-declared. What is left is
        the page furniture, and it is compared as one ordered list. Anything added, deleted,
        reordered or edited fails, and so does text in an element nobody thought to name, because
        the unit set decides what a literal may claim and not what is inspected.

        The `<title>` is named rather than walked. It lives in `<head>`, which this walk does not
        enter, because the inlined `<style>` block is not prose and `HTMLParser` returns the whole
        stylesheet as text. Naming it is the point: the `h1` survived five rounds precisely by
        sitting outside every region anyone had drawn, and a bound that quietly excluded the title
        would be the same mistake one element up.

        `report.py` emits none of this furniture, which is why the defect was reported rather than
        blocking. It is not why it is fixed. A false headline on an approved reference misleads
        every reader of the reference, and this chain has never used "cannot ship" as its bar:
        round 2's finding was the same shape on prose that was equally fixture-only at the time.
        """
        text = page_reference_text()
        reader = page_text_units(text)

        assert declared_units(reader) == [
            ("strong", STAMP_HEADLINE),
            ("span", stamp_body_literal()),
            ("h1", PAGE_HEADING),
            ("p", INTRO_NOTE),
            ("h2", REVIEW_NOTES_HEADING),
            ("p", REVIEW_NOTES),
        ]

        assert reader.unclaimed == [], "page text outside any declared unit"
        assert reader.reader_attributes == [], "page words a declared literal does not cover"

        titles = re.findall(r"<title\b[^>]*>(.*?)</title>", text, re.DOTALL)
        assert [collapse(title) for title in titles] == [PAGE_TITLE]

    def test_the_page_reader_detects_what_it_claims_to_detect(self) -> None:
        """The page totality rests on two comparisons against an empty list, and an empty list is
        also what a detector wired to nothing produces.

        Neither existing detector test covers this configuration. The unit set is wider than Tier
        1's and different from the apparatus's, so a `strong`, a `span`, an `h1` and an `h2` have
        to be shown landing in `units` rather than in `unclaimed`, and loose text in the stamp and
        text in an element nobody named have to be shown landing in `unclaimed` rather than being
        quietly dropped. The `hidden` div is here because `presentation_attributes` is asserted
        empty for this region too, one test down.
        """
        reader = parse_text_units(
            "<body>\n"
            '  <div class="stamp-illustrative">\n'
            "    <strong>a stamp headline</strong>\n"
            "    <span>a stamp body</span>\n"
            "    loose in the stamp\n"
            "  </div>\n"
            "  <div>\n"
            "    <h1>a page heading</h1>\n"
            "    <h2>a heading at the foot</h2>\n"
            '    <p title="read on hover, declared nowhere">a note</p>\n'
            "    <blockquote>inside an element nobody named</blockquote>\n"
            "  </div>\n"
            "  <div hidden>effaced the same way</div>\n"
            "</body>",
            PAGE_TEXT_UNITS,
        )

        assert declared_units(reader) == [
            ("strong", "a stamp headline"),
            ("span", "a stamp body"),
            ("h1", "a page heading"),
            ("h2", "a heading at the foot"),
            ("p", "a note"),
        ]
        assert reader.unclaimed == [
            "loose in the stamp",
            "inside an element nobody named",
            "effaced the same way",
        ]
        assert reader.reader_attributes == [("p", "title", "read on hover, declared nowhere")]
        assert reader.presentation_attributes == [("div", "hidden", "")]

    def test_no_element_hides_or_restyles_itself_inline(self) -> None:
        """A parser reads the document; a reader reads the render. This closes the two mechanisms
        that separate them without a stylesheet, and it closes nothing else.

        Both totality assertions compare parsed text, so a span that is present in the markup and
        invisible on the page satisfies them exactly. Wrapping the fixture note's last sentence in
        `<span style="display: none">` or `<span hidden>` left all 105 tests green while deleting,
        from the reader's view, the sentence that says the four table rows and their cell figures
        are synthetic. The reader then takes 1111 and 0.555 as measurements. Hiding the note's
        first sentence instead removes the only statement on the page that the shipped table
        carries all nineteen pairs, which is what section 1.2 rests on. An inline `style` beats any
        stylesheet rule carrying no `!important`, so the sheet's own guards cannot reach it.

        Declared rather than banned, because Tier 1 uses `style` legitimately: the comparison's
        three bar segments are proportional, and their proportions are the claim the contract asks
        the reader to see. The declared values are built from the corpus, so this does not become a
        third copy of the figures. The apparatus outside the renderer's output carries none at all,
        and neither does the page furniture around both regions, so those two are flat empty lists.

        **What this does not cover, stated so it is not mistaken for more than it is.** Only
        `style` and `hidden`. A reader-visible span can still be effaced by `<s>` or `<del>`
        striking it through, by `font-size: 0`, `color: transparent`, `clip-path` or
        `aria-hidden="true"` arriving through the stylesheet, or by CSS generated content adding
        words the parser never sees. Those are ledgered, deliberately unenumerated: the whole
        chain of rounds behind this file exists because an enumeration relocates the defect to
        whatever it did not list, and an enumeration that looks total is worse than a named gap.
        Deciding what a reader actually sees needs a rendering engine, which CI does not have.
        """
        text = page_reference_text()
        lead = corpus_value("results:primary.largest_observed_gap")
        mark = corpus_value("results:primary.first_rejection_gap_floor")

        # Tier 1: the two comparison rows, and nothing else. Any other inline style, and any
        # `hidden` at all, is an undeclared span between the parser and the reader.
        assert tier_1_text_units(text).presentation_attributes == [
            ("div", "style", f"flex: {lead};"),
            ("div", "style", f"flex: {mark - lead};"),
            ("div", "style", f"flex: {mark};"),
        ]

        # The apparatus, outside the two renderer-output fragments, has no reason to carry either.
        assert apparatus_text_units(text).presentation_attributes == []

        # The furniture around both regions, on the same terms. Without this the stamp's headline,
        # which is the whole of what the page says about its own status, could be wrapped in
        # `<span hidden>` with the page totality assertion green, because that assertion reads the
        # parse and the parse would still contain it.
        assert page_text_units(text).presentation_attributes == []

    def test_the_embedded_scroll_container_is_reachable_from_the_keyboard(self) -> None:
        """The same sibling-fixture-only gap as the table headers, one attribute set over.

        `TestTableReference` holds `table_reference.html`'s scroll container to `tabindex="0"`,
        `role="region"` and a label, and never opens this page. The container embedded here is the
        one the approved hierarchy actually shows, and nothing asserted anything about it.

        Chrome and Firefox focus a scrolling container by themselves and Safari does not, so
        without `tabindex` a keyboard-only Safari reader cannot scroll this table at all. The
        columns that fall outside a narrow viewport are the observed discordance and both p-value
        columns, which is precisely the audit trail the apparatus exists to make reachable.
        """
        apparatus = apparatus_outside_the_rendered_cards(page_reference_text())

        opening = apparatus.split("<table", 1)[0].rsplit('<div class="pair-table-scroll"', 1)
        assert len(opening) == 2, "no .pair-table-scroll container before the embedded table"
        attributes = opening[1].split(">", 1)[0]
        assert 'tabindex="0"' in attributes, attributes
        assert 'role="region"' in attributes, attributes
        assert "aria-label=" in attributes, attributes
        assert ".pair-table-scroll:focus-visible" in CARD_STYLESHEET

    def test_the_embedded_table_shows_the_settled_columns(self) -> None:
        """Every table assertion in this file read the sibling fixture, never this page's own copy.

        `TestTableReference` holds `table_reference.html` to `metrology.reporting.FINDINGS_COLUMNS`
        and refuses a per-pair floor column per D3.6. The table embedded here, which is the one the
        approved hierarchy actually shows, had no header check of any kind: a renamed column, a
        sixth column, or the floor column D3.6 excludes could all have entered it while the sibling
        stayed correct and the whole suite stayed green.

        The header row is read out of the table region and compared whole, in order, so a reworded
        column and an added one both fail. Comparing against the tuple the renderer will be handed
        is what makes this a drift guard rather than a second transcription.
        """
        table = apparatus_table(page_reference_text())

        assert re.findall(r"<th\b[^>]*>(.*?)</th>", table, flags=re.DOTALL) == list(
            FINDINGS_COLUMNS
        )
        assert "floor" not in table.lower(), "D3.6: no per-pair floor column"

    def test_the_analogy_and_the_task_level_note_are_verbatim(self) -> None:
        """A sentence pin cannot see the sentence next to it, which is the same defect one level
        out from the one that put the false superlative on this page.

        Two edits pass every substring pin. Prepend "In nearly all cases," to the scoped
        superlative and the pinned span is untouched, no numeral moves and the totality walk still
        balances, while the sentence now implies exceptions to a claim that holds without any.
        Append "Though in practice it usually would have." after the necessary-not-sufficient
        clause and the clause survives verbatim while the sentence after it asserts the opposite:
        that reaching the mark would have settled the comparison, which is false about the
        procedure and is exactly what spec 10.2 forbids the analogy to imply.

        So the unit is the paragraph, not the sentence, and the assertion is `==` on its whole
        text. The figures are built from the corpus rather than typed, so this pin does not become
        a second stale copy of them.
        """
        board = corpus_value("aggregates:family_size")
        lead = corpus_value("results:primary.largest_observed_gap")
        mark = corpus_value("results:primary.first_rejection_gap_floor")

        assert finding_readings(page_reference_text()) == [
            "It works like a qualifying mark. Before a difference between two neighboring systems "
            f"could count as reliable, that pair needed a lead of at least {mark} tasks. No "
            f"neighboring pair anywhere in the top {board} led by more than {lead}. None reached "
            "the mark, so none could qualify. Reaching the mark would not have settled a "
            "comparison on its own; it is the point at which the question becomes answerable at "
            "all.",
            "Task-by-task results add detail but cannot change this. A pair's lead sets a ceiling "
            f"on how strong its evidence can get, and a lead of {lead} stays under the mark even "
            "if every task the two systems disagreed on had gone the same way. The headline "
            "follows from the published totals alone.",
        ]

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

        The caption is the one of the four that is fixture copy rather than renderer output, so it
        is compared whole rather than by membership. The other three sit inside the family card,
        which fragment equality already holds character for character. Asked for with `in`, the
        caption could be appended to: `Every adjacent pair, as tested, though several were later
        retested and reversed` still contains the substring and still says "adjacent" once.
        """
        text = page_reference_text()
        start, end = apparatus_span(text)
        apparatus = text[start:end]

        assert "adjacent" not in finding_region(text).lower()
        assert "Adjacent pairs only. Non-adjacent comparisons are out of scope." in apparatus
        assert "adjacent pairs separable" in apparatus
        assert "Largest observed adjacent gap" in apparatus
        assert table_caption(text) == TABLE_CAPTION
        assert "adjacent" in TABLE_CAPTION

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

        assert rendered_card_fragments()["family"] in page_reference_text()

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

        text = page_reference_text()
        assert rendered_card_fragments()["pair"] in text

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

        The note itself is pinned whole rather than by the substrings it happens to contain. It is
        fixture furniture, so the family card's fragment-equality test does not reach it, and both
        of its load-bearing sentences could be deleted with "nineteen" and "fixture convenience"
        left standing elsewhere in the paragraph. Those two sentences are the ones that tell a
        reader the reduction is a fixture convenience rather than the shipped row count, which is
        what section 1.2 guards against being read as a post-hoc selection.
        """
        text = page_reference_text()
        body = text.split("<tbody>", 1)[1].split("</tbody>", 1)[0]

        family_size = corpus_value("results:primary.family_size")
        assert family_size in SPELLED_NUMBERS, f"no spelled form registered for {family_size}"
        shipped = SPELLED_NUMBERS[family_size]

        assert body.count("<tr>") == REDUCED_ROWS
        assert apparatus_note(text) == apparatus_note_literal()

        stamp = " ".join(
            text.split('<div class="stamp-illustrative">', 1)[1].split("</div>", 1)[0].split()
        )
        assert shipped in stamp

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
