"""T2.6: the card renderer, targeting the approved reference.

Per D1.3 the reference HTML was built and approved before this renderer existed, so these
snapshots lock output against an independently approved artifact rather than recording whatever
the renderer happened to emit.

Two pair states are covered, as specified: balanced disagreement at gap zero, which exercises the
edge-safe marker at position zero, and the nonzero-gap ruler case.
"""

from __future__ import annotations

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
