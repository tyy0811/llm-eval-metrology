"""T2.6: the card renderer, targeting the approved reference.

Per D1.3 the reference HTML was built and approved before this renderer existed, so these
snapshots lock output against an independently approved artifact rather than recording whatever
the renderer happened to emit.

Two pair states are covered, as specified: balanced disagreement at gap zero, which exercises the
edge-safe marker at position zero, and the nonzero-gap ruler case.
"""

from __future__ import annotations

import re
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
