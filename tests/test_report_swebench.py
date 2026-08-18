"""report.py: the one IO layer for T3.3 outputs.

Both modes run validate_sources first (spec section 2): --write against a reordered
or inconsistent source must refuse to write anything, because a --write that
produces output from a bad source would be blessed by the very next --check.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "swebench_report", REPO_ROOT / "experiments" / "swebench" / "report.py"
)
report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(report)

RESULTS = json.loads(
    (REPO_ROOT / "experiments/swebench/results/results.json").read_text(encoding="utf-8")
)
AGGREGATES = json.loads(
    (REPO_ROOT / "experiments/swebench/derived/aggregates.json").read_text(encoding="utf-8")
)


def copy(document: dict) -> dict:
    return json.loads(json.dumps(document))


class TestValidateSources:
    def test_the_committed_corpus_passes(self) -> None:
        report.validate_sources(RESULTS, AGGREGATES)

    def test_a_reordered_pair_list_fails(self) -> None:
        results = copy(RESULTS)
        results["pairs"][2], results["pairs"][6] = results["pairs"][6], results["pairs"][2]
        with pytest.raises(report.ReportFailure, match="order"):
            report.validate_sources(results, AGGREGATES)

    def test_a_duplicated_pair_fails(self) -> None:
        results = copy(RESULTS)
        results["pairs"][3] = copy(results["pairs"][2])
        with pytest.raises(report.ReportFailure):
            report.validate_sources(results, AGGREGATES)

    def test_a_reordered_aggregates_array_fails(self) -> None:
        """No sorting anywhere (spec section 7): the aggregates array order is
        the authority. Shuffling the entries list, ranks left untouched, must
        be reported rather than silently repaired by sorting back into rank
        order, which would bless the exact defect this validation exists to
        catch."""
        aggregates = copy(AGGREGATES)
        entries = aggregates["entries"]
        entries[0], entries[1] = entries[1], entries[0]
        with pytest.raises(report.ReportFailure, match="rank order"):
            report.validate_sources(RESULTS, aggregates)

    def test_a_net_edge_disagreeing_with_aggregates_fails(self) -> None:
        """The gap column claims aggregate provenance; a net_edge that drifts from
        the adjacent resolved counts must halt, not render uncaveated."""
        results = copy(RESULTS)
        results["pairs"][4]["net_edge"] += 1
        with pytest.raises(report.ReportFailure, match="net edge"):
            report.validate_sources(results, AGGREGATES)

    def test_a_renamed_pair_fails(self) -> None:
        results = copy(RESULTS)
        results["pairs"][0]["name"] = "rank_1_vs_3"
        with pytest.raises(report.ReportFailure, match="name"):
            report.validate_sources(results, AGGREGATES)


class TestCsvText:
    def test_shape_and_determinism(self) -> None:
        text = report.render_csv_text(RESULTS)
        assert text == report.render_csv_text(RESULTS)
        lines = text.split("\n")
        assert lines[0] == ",".join(report.CSV_COLUMNS)
        assert len(lines) == 1 + 19 + 1
        assert lines[-1] == ""
        assert text.endswith("\n")

    def test_nothing_on_this_data_triggers_quoting(self) -> None:
        """QUOTE_MINIMAL quotes nothing today; a future field that would must fail
        here visibly instead of changing the byte format silently."""
        assert '"' not in report.render_csv_text(RESULTS)

    def test_equivalent_appears_in_no_generated_output(self) -> None:
        """Scoped to generated Experiment 1 outputs (spec section 5). Checked as its
        own assertion, not as a substring of a verdict, which is the mistake a prior
        test made against the wrong error."""
        assert "EQUIVALENT" not in report.render_csv_text(RESULTS)

    def test_row_swap_is_caught_by_the_projection(self) -> None:
        """Pairs 2 and 7 agree on every McNemar and MDE field and differ only in
        bootstrap.low and bootstrap.seed (measured; spec section 10). They also
        differ in name and systems, so swapping the two whole records is caught
        here by the name-adjacency check in validate_sources, not by the
        McNemar or MDE fields the CSV set-membership contrast is about."""
        results = copy(RESULTS)
        results["pairs"][1], results["pairs"][6] = results["pairs"][6], results["pairs"][1]
        with pytest.raises(report.ReportFailure):
            report.validate_sources(results, AGGREGATES)


class TestSplice:
    BLOCK = "generated content\n"

    def test_exactly_one_ordered_marker_pair_is_required(self) -> None:
        good = f"intro\n{report.START_MARKER}\nold\n{report.END_MARKER}\noutro\n"
        spliced = report.spliced(good, self.BLOCK)
        assert self.BLOCK in spliced
        assert "old" not in spliced
        assert spliced.startswith("intro\n")
        assert spliced.endswith("outro\n")

    def test_missing_duplicated_and_reversed_markers_each_fail(self) -> None:
        cases = (
            "no markers at all\n",
            f"{report.START_MARKER}\nunclosed\n",
            f"{report.START_MARKER}\na\n{report.END_MARKER}\n{report.START_MARKER}\n",
            f"{report.END_MARKER}\nbackwards\n{report.START_MARKER}\n",
        )
        for text in cases:
            with pytest.raises(report.ReportFailure, match="marker"):
                report.spliced(text, self.BLOCK)


class TestModes:
    def sandbox(self, tmp_path: Path, results: dict) -> dict[str, Path]:
        paths = {
            "results": tmp_path / "results.json",
            "aggregates": tmp_path / "aggregates.json",
            "readme": tmp_path / "README.md",
            "csv": tmp_path / "pairs.csv",
        }
        paths["results"].write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        paths["aggregates"].write_text(
            json.dumps(AGGREGATES, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        paths["readme"].write_text(
            f"# sandbox\n\n{report.START_MARKER}\nstale\n{report.END_MARKER}\n",
            encoding="utf-8",
        )
        return paths

    def argv(self, mode: str, paths: dict[str, Path]) -> list[str]:
        return [
            mode,
            "--results",
            str(paths["results"]),
            "--aggregates",
            str(paths["aggregates"]),
            "--readme",
            str(paths["readme"]),
            "--csv",
            str(paths["csv"]),
        ]

    def test_write_then_check_round_trips(self, tmp_path: Path) -> None:
        paths = self.sandbox(tmp_path, RESULTS)
        assert report.main(self.argv("--write", paths)) == 0
        assert report.main(self.argv("--check", paths)) == 0
        assert "stale" not in paths["readme"].read_text(encoding="utf-8")

    def test_check_fails_on_a_hand_edited_block(self, tmp_path: Path) -> None:
        paths = self.sandbox(tmp_path, RESULTS)
        report.main(self.argv("--write", paths))
        readme = paths["readme"].read_text(encoding="utf-8")
        paths["readme"].write_text(readme.replace("0 of 19", "5 of 19"), encoding="utf-8")
        assert report.main(self.argv("--check", paths)) != 0

    def test_check_fails_on_a_stale_csv(self, tmp_path: Path) -> None:
        paths = self.sandbox(tmp_path, RESULTS)
        report.main(self.argv("--write", paths))
        text = paths["csv"].read_text(encoding="utf-8")
        lines = text.split("\n")
        lines[1], lines[2] = lines[2], lines[1]
        paths["csv"].write_text("\n".join(lines), encoding="utf-8")
        assert report.main(self.argv("--check", paths)) != 0

    def test_two_swapped_columns_fail_the_check(self, tmp_path: Path) -> None:
        """n01 and n10 (columns 3 and 4) swapped in every line, header and all 19
        data rows, so the byte difference is not confined to the header alone.
        report.py --check must catch it via byte comparison against the freshly
        rendered projection."""
        paths = self.sandbox(tmp_path, RESULTS)
        assert report.main(self.argv("--write", paths)) == 0
        lines = paths["csv"].read_text(encoding="utf-8").split("\n")
        swapped_lines = []
        for line in lines:
            if not line:
                swapped_lines.append(line)
                continue
            cells = line.split(",")
            cells[3], cells[4] = cells[4], cells[3]
            swapped_lines.append(",".join(cells))
        paths["csv"].write_text("\n".join(swapped_lines), encoding="utf-8")
        assert report.main(self.argv("--check", paths)) != 0

    def test_write_refuses_and_leaves_destinations_untouched_on_a_bad_source(
        self, tmp_path: Path
    ) -> None:
        results = copy(RESULTS)
        results["pairs"][4]["net_edge"] += 1
        paths = self.sandbox(tmp_path, results)
        before_readme = paths["readme"].read_text(encoding="utf-8")
        assert report.main(self.argv("--write", paths)) != 0
        assert paths["readme"].read_text(encoding="utf-8") == before_readme
        assert not paths["csv"].exists()


class TestValidateSourcesArithmetic:
    """Jane's T3.3 review, finding 2: abs() on the gap accepted an inverted board,
    and nothing tied net_edge to the discordant counts it is supposed to summarize.
    """

    def test_an_inverted_adjacent_pair_fails(self) -> None:
        """A lower-ranked entry with MORE resolved instances passed before, because
        abs() erased the direction the published ordering asserts. Inverting at the
        final entry leaves every earlier pair untouched, so the failure is the
        inversion itself and not a knock-on mismatch."""
        results = copy(RESULTS)
        aggregates = copy(AGGREGATES)
        entries = aggregates["entries"]
        entries[-1]["resolved"] = entries[-2]["resolved"] + 8
        results["pairs"][-1]["net_edge"] = 8
        with pytest.raises(report.ReportFailure, match="nonincreasing"):
            report.validate_sources(results, aggregates)

    def test_net_edge_must_equal_n10_minus_n01(self) -> None:
        results = copy(RESULTS)
        pair = results["pairs"][2]
        pair["n01"], pair["n10"] = pair["n10"], pair["n01"]
        with pytest.raises(report.ReportFailure, match="n10 - n01"):
            report.validate_sources(results, AGGREGATES)

    def test_n_discordant_must_equal_n01_plus_n10(self) -> None:
        results = copy(RESULTS)
        results["pairs"][4]["n_discordant"] += 1
        with pytest.raises(report.ReportFailure, match="n01 [+] n10"):
            report.validate_sources(results, AGGREGATES)

    def test_n_discordant_must_not_exceed_n_items(self) -> None:
        results = copy(RESULTS)
        pair = results["pairs"][4]
        pair["n01"] = 400
        pair["n10"] = 400 + pair["net_edge"]
        pair["n_discordant"] = pair["n01"] + pair["n10"]
        with pytest.raises(report.ReportFailure, match="n_items"):
            report.validate_sources(results, AGGREGATES)


class TestCardsHtml:
    """The finding-first document. Spec sections 6, 7 and 11.

    Controls here are adversarial rather than descriptive: each one mutates the document
    or a source into the shape a reader would be misled by, because a test that only ever
    sees correct output proves the renderer ran, not that it is guarded.
    """

    def sandbox_all(self, tmp_path: Path) -> dict[str, Path]:
        paths = TestModes().sandbox(tmp_path, RESULTS)
        for name, source in (
            ("cards_json", "results/cards.json"),
            ("manifest", "manifests/upstream_digests.json"),
        ):
            target = tmp_path / Path(source).name
            target.write_text(
                (REPO_ROOT / "experiments/swebench" / source).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            paths[name] = target
        paths["cards_html"] = tmp_path / "cards.html"
        return paths

    def argv(self, mode: str, paths: dict[str, Path]) -> list[str]:
        return [
            mode,
            "--results",
            str(paths["results"]),
            "--aggregates",
            str(paths["aggregates"]),
            "--readme",
            str(paths["readme"]),
            "--csv",
            str(paths["csv"]),
            "--cards-json",
            str(paths["cards_json"]),
            "--manifest",
            str(paths["manifest"]),
            "--cards-html",
            str(paths["cards_html"]),
        ]

    def written(self, tmp_path: Path) -> tuple[dict[str, Path], str]:
        paths = self.sandbox_all(tmp_path)
        assert report.main(self.argv("--write", paths)) == 0
        return paths, paths["cards_html"].read_text(encoding="utf-8")

    def body(self, html_text: str) -> str:
        """Everything after the inlined stylesheet.

        card.css defines .pair-table-block and .technical-apparatus, and the document
        inlines it, so a class name searched over the whole file matches its own CSS rule
        in <head> before it matches any markup. The first draft of these controls did
        exactly that and reported the table ahead of the family card."""
        assert "</style>" in html_text
        return html_text[html_text.index("</style>") + len("</style>") :]

    def split(self, html_text: str) -> tuple[str, str]:
        """The first reading, and the apparatus, both taken from the body."""
        body = self.body(html_text)
        marker = '<details class="technical-apparatus"'
        assert marker in body
        at = body.index(marker)
        return body[:at], body[at:]

    def test_write_then_check_round_trips(self, tmp_path: Path) -> None:
        paths, _ = self.written(tmp_path)
        assert report.main(self.argv("--check", paths)) == 0

    def test_the_finding_leads_and_the_apparatus_is_closed(self, tmp_path: Path) -> None:
        """A divider would leave the duplicate headline, the p-values and the provenance
        in the first reading, which is what contract item 6 moves out of it. Closed means
        no `open` attribute, and holding means the components are descendants."""
        _, html_text = self.written(tmp_path)
        first, apparatus = self.split(html_text)
        assert 'class="card finding"' in first
        assert " open" not in apparatus[: apparatus.index(">")]
        end = apparatus.rindex("</details>")
        for marker in ("family-summary", "pair-table-block", "Ranks 1 and 2", "Ranks 3 and 4"):
            assert marker in apparatus[:end], marker
            assert marker not in first, marker

    def test_the_apparatus_holds_its_parts_in_the_registered_order(self, tmp_path: Path) -> None:
        """Spec 11.1 fixes the order, and nothing else tests it: the crosswalk validates
        values and cannot see document position."""
        _, html_text = self.written(tmp_path)
        body = self.body(html_text)
        positions = [
            body.index(marker)
            for marker in ("family-summary", "pair-table-block", "Ranks 1 and 2", "Ranks 3 and 4")
        ]
        assert positions == sorted(positions)

    def test_the_first_reading_states_no_apparatus(self, tmp_path: Path) -> None:
        """A reader who stops at the first screen must have a complete headline and no
        statistics. The system identifiers are read from the corpus rather than spelled
        out, so a renamed system cannot quietly drop out of the ban."""
        _, html_text = self.written(tmp_path)
        first, _ = self.split(html_text)
        body = first[first.index('class="card finding"') :].lower()
        for banned in ("holm", "p-value", "p_value", "provenance", "alpha"):
            assert banned not in body, banned
        for entry in AGGREGATES["entries"]:
            assert entry["system"].lower() not in body, entry["system"]

    def test_the_table_matches_the_readme_projection_row_for_row(self, tmp_path: Path) -> None:
        """One projection, two surfaces. A divergence between the card table and the
        README table is a defect, so this compares the full header and every row."""
        from test_cards import parse_table

        from metrology.reporting import FINDINGS_COLUMNS, findings_pair_rows

        _, html_text = self.written(tmp_path)
        parsed = parse_table(html_text)
        assert parsed.header == list(FINDINGS_COLUMNS)
        assert len(parsed.rows) == 19
        assert parsed.rows == [list(row) for row in findings_pair_rows(RESULTS)]

    def test_no_post_hoc_pair_selection(self, tmp_path: Path) -> None:
        """Spec 1.2. A layout exploration showed three rows; production carries all
        nineteen, and pair cards come only from the registered D8 rule."""
        from metrology.reporting import illustrative_pair_names

        _, html_text = self.written(tmp_path)
        entries = sorted(AGGREGATES["entries"], key=lambda entry: entry["rank"])
        assert html_text.count('class="card" aria-labelledby="pair-') == len(
            illustrative_pair_names(entries)
        )

    def test_a_hand_edited_document_fails_drift(self, tmp_path: Path) -> None:
        paths, html_text = self.written(tmp_path)
        paths["cards_html"].write_text(
            html_text.replace("Ranks 1 and 2", "Ranks 9 and 9"), encoding="utf-8"
        )
        assert report.main(self.argv("--check", paths)) != 0

    def test_a_missing_document_fails_drift(self, tmp_path: Path) -> None:
        """--check must not pass on an artifact that was never written."""
        paths, _ = self.written(tmp_path)
        paths["cards_html"].unlink()
        assert report.main(self.argv("--check", paths)) != 0

    def test_rendering_is_byte_stable(self, tmp_path: Path) -> None:
        paths, first = self.written(tmp_path)
        assert report.main(self.argv("--write", paths)) == 0
        assert paths["cards_html"].read_text(encoding="utf-8") == first

    def test_equivalent_appears_nowhere(self, tmp_path: Path) -> None:
        """EQUIVALENT is refused until Phase 5 supplies TOST fields."""
        _, html_text = self.written(tmp_path)
        assert "EQUIVALENT" not in html_text

    def test_a_forged_card_stops_the_write(self, tmp_path: Path) -> None:
        """The preflight runs the crosswalk before any byte is written, so a card that
        disagrees with its source cannot reach the document."""
        paths = self.sandbox_all(tmp_path)
        cards = json.loads(paths["cards_json"].read_text(encoding="utf-8"))
        cards["family"]["family_finding"]["headline"]["family_size"] = 99
        paths["cards_json"].write_text(
            json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        assert report.main(self.argv("--write", paths)) != 0
        assert not paths["cards_html"].exists()

    def test_a_late_validation_failure_leaves_all_three_untouched(self, tmp_path: Path) -> None:
        """Distinct sentinels in every destination: all validation and all building must
        precede the first write, so a semantic failure cannot leave one artifact
        regenerated and another stale."""
        paths = self.sandbox_all(tmp_path)
        sentinels = {
            "readme": f"README SENTINEL\n{report.START_MARKER}\nx\n{report.END_MARKER}\n",
            "csv": "CSV SENTINEL\n",
            "cards_html": "HTML SENTINEL\n",
        }
        for key, text in sentinels.items():
            paths[key].write_text(text, encoding="utf-8")
        cards = json.loads(paths["cards_json"].read_text(encoding="utf-8"))
        cards["pairs"]["rank_3_vs_4"]["ruler"]["required_net_edge_at_observed"] = 99
        paths["cards_json"].write_text(
            json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        assert report.main(self.argv("--write", paths)) != 0
        for key, text in sentinels.items():
            assert paths[key].read_text(encoding="utf-8") == text, key

    def test_a_missing_source_key_halts_rather_than_aborting(self, tmp_path: Path) -> None:
        """_dig raises KeyError, not ValueError, on a renamed source key. A preflight
        that caught only ValueError would abort mid-run instead of halting with a
        diagnosis, and --write would leave the artifacts at mixed generations."""
        paths = self.sandbox_all(tmp_path)
        results = copy(RESULTS)
        del results["primary"]["largest_observed_gap"]
        paths["results"].write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        assert report.main(self.argv("--write", paths)) != 0

    def test_the_table_heading_and_note_match_the_approved_fixture(self) -> None:
        """The approved reference governs, not the constant. If they differ the constant
        is wrong, because the fixture carries the D1.3 approval."""
        import re as _re

        fixture = (REPO_ROOT / "metrology/cards/fixtures/table_reference.html").read_text(
            encoding="utf-8"
        )

        def text_of(pattern: str) -> str:
            raw = _re.search(pattern, fixture, _re.S).group(1)
            return _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", "", raw)).strip()

        assert text_of(r"<caption[^>]*>(.*?)</caption>").startswith(report.TABLE_HEADING)
        note = text_of(r'<p class="pair-table-note"[^>]*>(.*?)</p>')
        assert note.startswith(report.TABLE_DISCLOSURE)
