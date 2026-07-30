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
