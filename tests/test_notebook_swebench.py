"""The notebook is a thin presentation consumer: it reads results, renders, and
proves it by sentinel flow (spec section 9). It never recomputes.

Markdown cells stay figure-free by design: prose describes, code prints corpus
figures. That is what lets the D1.8 checker scan notebook prose trivially.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = REPO_ROOT / "experiments" / "swebench" / "notebook.py"

_SPEC = importlib.util.spec_from_file_location("swebench_notebook", NOTEBOOK)
notebook = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(notebook)

RESULTS_PATH = REPO_ROOT / "experiments/swebench/results/results.json"
AGGREGATES_PATH = REPO_ROOT / "experiments/swebench/derived/aggregates.json"

ALLOWED_MODULES = {"json", "pathlib"}
ALLOWED_FROM = {("metrology.reporting", "render_number")}

# (json path into the document, sentinel value, expected rendered string)
SENTINELS = (
    ("results", ("primary", "headline", "tie_forced_not_distinguishable_count"), 777, "777"),
    ("results", ("pairs", 0, "p_value"), 0.777, "0.777"),
    ("results", ("pairs", 0, "bootstrap", "high"), 0.666, "0.666"),
    ("results", ("pairs", 0, "mde", "instances"), 55.5, "55.5"),
    ("results", ("mde_grid", "points", 0, "instances"), 66.6, "66.6"),
    ("aggregates", ("entries", 0, "no_logs"), 888, "888"),
    ("results", ("secondary", "non_tied_family", "gap_floor"), 444, "444"),
    ("results", ("secondary", "harness_straddle", "entries_predating_the_fix"), 555, "555"),
    ("results", ("secondary", "no_logs_sensitivity", "total_pairs_affected"), 666, "666"),
)


def run_notebook(capsys, results_path=RESULTS_PATH, aggregates_path=AGGREGATES_PATH) -> str:
    notebook.main(results_path, aggregates_path)
    return capsys.readouterr().out


class TestImports:
    def test_only_the_symbol_allowlist(self) -> None:
        """Module allowlisting is not enough: metrology.reporting also exposes
        build_family_report. Only render_number may cross the boundary."""
        tree = ast.parse(NOTEBOOK.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in ALLOWED_MODULES, f"forbidden import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert (node.module, alias.name) in ALLOWED_FROM, (
                        f"forbidden import from {node.module}: {alias.name}"
                    )


class TestStructure:
    def test_row_counts(self, capsys) -> None:
        out = run_notebook(capsys)
        assert sum(1 for line in out.splitlines() if line.startswith("pair ")) == 19
        assert sum(1 for line in out.splitlines() if line.startswith("grid ")) == 6
        assert sum(1 for line in out.splitlines() if line.startswith("system ")) == 20

    def test_required_fields_per_pair_row(self, capsys) -> None:
        out = run_notebook(capsys)
        pair_lines = [line for line in out.splitlines() if line.startswith("pair ")]
        for line in pair_lines:
            for field in ("n01", "n10", "interval", "mde"):
                assert field in line, f"{field} missing from {line!r}"

    def test_each_secondary_is_individually_present(self, capsys) -> None:
        out = run_notebook(capsys)
        assert "non-tied family" in out
        assert "no_logs sensitivity" in out
        assert "harness straddle" in out

    def test_d4_scope_is_precise(self, capsys) -> None:
        """D4 qualifies the observed per-instance quantities only; pair identity
        derives from published aggregates and must not be swept in by an
        unscoped 'every column' phrasing (spec section 5)."""
        out = run_notebook(capsys)
        assert "pair identity derives from published aggregates" in out
        assert "applies to every column" not in out

    def test_equivalent_never_appears(self, capsys) -> None:
        out = run_notebook(capsys)
        assert "EQUIVALENT" not in out

    def test_sensitivity_prints_one_line_per_affected_pair(self, capsys) -> None:
        """total_pairs_affected is 5 (measured); each affected pair gets its own
        line rather than being reported only as an aggregate count (review
        minor 11, spec section 9 item 5)."""
        out = run_notebook(capsys)
        lines = [line for line in out.splitlines() if line.startswith("sensitivity pair ")]
        assert len(lines) == 5

    def test_the_three_part_headline_leads(self, capsys) -> None:
        out = run_notebook(capsys)
        first_figure_line = out.index("distinguishable")
        assert first_figure_line < out.index("pair ")

    def test_d4_scope_is_stated(self, capsys) -> None:
        out = run_notebook(capsys)
        assert "D4 harness comparability" in out


class TestSentinelFlow:
    def test_every_output_class_flows_from_storage(self, tmp_path, capsys) -> None:
        documents = {
            "results": json.loads(RESULTS_PATH.read_text(encoding="utf-8")),
            "aggregates": json.loads(AGGREGATES_PATH.read_text(encoding="utf-8")),
        }
        for source, path, sentinel, _ in SENTINELS:
            node = documents[source]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = sentinel
        for source, document in documents.items():
            (tmp_path / f"{source}.json").write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        out = run_notebook(capsys, tmp_path / "results.json", tmp_path / "aggregates.json")
        for source, path, _, rendered in SENTINELS:
            assert rendered in out, f"sentinel for {source}:{path} did not flow to output"


class TestAlternativeResults:
    """Jane's T3.3 review, finding 3: the notebook crashed on an unattainable MDE
    (instances is None, a state the engine explicitly validates) and hardcoded the
    no_logs conclusion as "unchanged" whatever the stored family result said.
    """

    def sandbox(self, tmp_path):
        results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        aggregates = json.loads(AGGREGATES_PATH.read_text(encoding="utf-8"))
        results["pairs"][0]["mde"] = {
            "status": "unattainable",
            "instances": None,
            "rate_difference": None,
            "max_attainable_power": 0.04,
        }
        results["mde_grid"]["points"][0]["instances"] = None
        results["mde_grid"]["points"][0]["status"] = "unattainable"
        results["secondary"]["no_logs_sensitivity"]["family"]["resolved_count"] = 1
        results["secondary"]["no_logs_sensitivity"]["family"]["separable_count"] = 2
        results["secondary"]["harness_straddle"]["straddling_pairs"] = [{"rank_a": 3, "rank_b": 4}]
        (tmp_path / "results.json").write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (tmp_path / "aggregates.json").write_text(
            json.dumps(aggregates, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return tmp_path / "results.json", tmp_path / "aggregates.json"

    def test_unattainable_mde_renders_na_not_a_crash(self, tmp_path, capsys) -> None:
        out = run_notebook(capsys, *self.sandbox(tmp_path))
        pair_line = next(line for line in out.splitlines() if line.startswith("pair "))
        assert "mde n/a" in pair_line
        assert "(unattainable)" in pair_line
        grid_line = next(line for line in out.splitlines() if line.startswith("grid "))
        assert "mde n/a" in grid_line

    def test_the_sensitivity_conclusion_is_read_not_asserted(self, tmp_path, capsys) -> None:
        out = run_notebook(capsys, *self.sandbox(tmp_path))
        assert "conclusion unchanged" not in out
        assert "separable 2, resolved 1" in out

    def test_a_nonempty_straddle_list_renders_pair_identifiers(self, tmp_path, capsys) -> None:
        """The registered straddle shape is a list of rank dictionaries; joining
        them raised TypeError (Jane's T3.3 follow-up, finding 1). The ranks render
        through the aggregate rank path, the same registry contract as every other
        figure."""
        out = run_notebook(capsys, *self.sandbox(tmp_path))
        assert "straddling pairs: rank_3_vs_4" in out

    def test_the_committed_conclusion_is_also_read(self, capsys) -> None:
        out = run_notebook(capsys)
        assert "conclusion unchanged" not in out
        assert "separable 0, resolved 0" in out
