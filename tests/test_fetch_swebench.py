"""T3.1 derivation logic, exercised without network.

CI previously ran only the Phase 2 suite, so nothing here was covered at all. That is why a
malformed boolean and a discarded sensitivity id set both stayed green: no test existed to fail.

Every function below is the pure half of `fetch.py`. Network I/O lives in separate functions, so
the parsing, the coverage rule, and the gates can be driven from fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FETCH_PATH = REPO_ROOT / "experiments" / "swebench" / "fetch.py"


def load_fetch():
    spec = importlib.util.spec_from_file_location("swebench_fetch", FETCH_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


fetch = load_fetch()

INSTANCES = [f"repo__pkg-{index:04d}" for index in range(fetch.EXPECTED_INSTANCES)]


def entry(rank: int, folder: str, rate: float) -> object:
    return fetch.Entry(rank=rank, folder=folder, published_rate=rate, checked=False, date="")


def artifact(folder: str, resolved, fmt=fetch.FORMAT_RESOLVED_LIST, **extra):
    return fetch.Artifact(
        folder=folder,
        split_dir="verified",
        artifact_format=fmt,
        url="https://example.invalid",
        sha256="0" * 64,
        resolved=set(resolved),
        **extra,
    )


class TestFormatBRequiresRealBooleans:
    """A string reached the resolved set through truthiness."""

    def test_a_string_false_is_rejected(self) -> None:
        document = {"a__a-1": {"resolved": "false"}}

        with pytest.raises(fetch.GateFailure, match="not a boolean"):
            fetch.parse_artifact_document(document, fetch.FORMAT_INSTANCE_MAP, "sys")

    def test_a_string_true_is_rejected(self) -> None:
        document = {"a__a-1": {"resolved": "true"}}

        with pytest.raises(fetch.GateFailure, match="not a boolean"):
            fetch.parse_artifact_document(document, fetch.FORMAT_INSTANCE_MAP, "sys")

    @pytest.mark.parametrize("value", [1, 0, None, [], {}, 1.0])
    def test_no_other_type_is_accepted(self, value) -> None:
        with pytest.raises(fetch.GateFailure, match="not a boolean|no 'resolved'"):
            fetch.parse_artifact_document(
                {"a__a-1": {"resolved": value}}, fetch.FORMAT_INSTANCE_MAP, "sys"
            )

    def test_real_booleans_classify_correctly(self) -> None:
        document = {
            "a__a-1": {"resolved": True},
            "a__a-2": {"resolved": False},
        }

        parsed = fetch.parse_artifact_document(document, fetch.FORMAT_INSTANCE_MAP, "sys")

        assert parsed["resolved"] == {"a__a-1"}
        assert parsed["covered"] == {"a__a-1", "a__a-2"}

    def test_a_record_without_a_resolved_field_is_rejected(self) -> None:
        with pytest.raises(fetch.GateFailure, match="no 'resolved'"):
            fetch.parse_artifact_document(
                {"a__a-1": {"cost": 0.2}}, fetch.FORMAT_INSTANCE_MAP, "sys"
            )

    def test_a_non_object_record_is_rejected(self) -> None:
        with pytest.raises(fetch.GateFailure, match="not an object"):
            fetch.parse_artifact_document({"a__a-1": True}, fetch.FORMAT_INSTANCE_MAP, "sys")


class TestFormatAParsing:
    def test_identities_are_preserved_not_counted(self) -> None:
        """The registered pairwise-drop sensitivity needs ids; a count cannot be dropped."""
        document = {
            "resolved": ["a__a-1"],
            "no_generation": ["a__a-2"],
            "no_logs": ["a__a-3", "a__a-4"],
        }

        parsed = fetch.parse_artifact_document(document, fetch.FORMAT_RESOLVED_LIST, "sys")

        assert parsed["no_logs"] == {"a__a-3", "a__a-4"}
        assert parsed["no_generation"] == {"a__a-2"}

    def test_a_non_list_field_is_rejected(self) -> None:
        with pytest.raises(fetch.GateFailure, match="list of instance ids"):
            fetch.parse_artifact_document({"resolved": "a__a-1"}, fetch.FORMAT_RESOLVED_LIST, "sys")

    def test_an_id_both_resolved_and_unevaluated_is_rejected(self) -> None:
        document = {"resolved": ["a__a-1"], "no_logs": ["a__a-1"], "no_generation": []}

        with pytest.raises(fetch.GateFailure, match="both resolved and unevaluated"):
            fetch.parse_artifact_document(document, fetch.FORMAT_RESOLVED_LIST, "sys")

    def test_missing_optional_fields_default_to_empty(self) -> None:
        parsed = fetch.parse_artifact_document(
            {"resolved": ["a__a-1"]}, fetch.FORMAT_RESOLVED_LIST, "sys"
        )

        assert parsed["no_logs"] == set()


class TestCoverageRule:
    def canonical(self):
        return set(INSTANCES)

    def test_a_matching_entry_is_accepted(self) -> None:
        item = entry(1, "sys", 0.4)

        assert fetch.disqualify(item, artifact("sys", INSTANCES[:2]), self.canonical()) is None

    def test_a_count_mismatch_is_disqualified(self) -> None:
        item = entry(1, "sys", 0.4)

        reason = fetch.disqualify(item, artifact("sys", INSTANCES[:5]), self.canonical())

        assert "gate 3" in reason

    def test_a_missing_artifact_is_disqualified(self) -> None:
        assert "no artifact" in fetch.disqualify(entry(1, "sys", 0.4), None, self.canonical())

    def test_a_non_exact_rate_is_disqualified(self) -> None:
        reason = fetch.disqualify(entry(1, "sys", 64.93), artifact("sys", []), self.canonical())

        assert "exact count" in reason

    def test_ids_outside_the_instance_set_are_disqualified(self) -> None:
        item = entry(1, "sys", 0.4)

        reason = fetch.disqualify(item, artifact("sys", ["stranger", "other"]), self.canonical())

        assert "gate 2" in reason

    def test_a_partial_instance_map_is_disqualified(self) -> None:
        item = entry(1, "sys", 0.4)
        art = artifact(
            "sys", INSTANCES[:2], fmt=fetch.FORMAT_INSTANCE_MAP, covered=set(INSTANCES[:10])
        )

        assert "gate 2" in fetch.disqualify(item, art, self.canonical())


class TestGatesAndRows:
    def two_systems(self):
        chosen = [entry(1, "a", 0.4), entry(2, "b", 0.2)]
        artifacts = {
            "a": artifact("a", INSTANCES[:2]),
            "b": artifact("b", INSTANCES[:1]),
        }
        return chosen, artifacts

    def test_rows_cover_every_system_and_instance(self) -> None:
        chosen, artifacts = self.two_systems()

        rows = fetch.build_rows(chosen, artifacts, INSTANCES)

        assert len(rows) == 2 * fetch.EXPECTED_INSTANCES

    def test_rows_are_in_canonical_order(self) -> None:
        chosen, artifacts = self.two_systems()

        rows = fetch.build_rows(chosen, artifacts, INSTANCES)
        keys = [(r["item_id"], r["system"]) for r in rows]

        assert keys == sorted(keys)

    def test_gates_pass_on_consistent_data(self) -> None:
        chosen, artifacts = self.two_systems()
        rows = fetch.build_rows(chosen, artifacts, INSTANCES)

        fetch.run_gates(chosen, artifacts, rows, INSTANCES)

    def test_gate_3_catches_a_count_that_drifts(self) -> None:
        chosen, artifacts = self.two_systems()
        rows = fetch.build_rows(chosen, artifacts, INSTANCES)
        for row in rows:
            if row["system"] == "a":
                row["label"] = 0

        with pytest.raises(fetch.GateFailure, match="gate 3"):
            fetch.run_gates(chosen, artifacts, rows, INSTANCES)

    def test_gate_1_catches_a_short_system(self) -> None:
        chosen, artifacts = self.two_systems()
        rows = [
            r
            for r in fetch.build_rows(chosen, artifacts, INSTANCES)
            if r["item_id"] != INSTANCES[0]
        ]

        with pytest.raises(fetch.GateFailure, match="gate 1"):
            fetch.run_gates(chosen, artifacts, rows, INSTANCES)

    def test_gate_4_catches_duplicates(self) -> None:
        """Isolated, because gates 1 to 3 see a duplicate as a count problem first.

        Appending a row makes a system 501 long, so gate 1 fires before gate 4 is reached.
        Gate 4 guards the uniqueness key independently of the per-system checks, so it is
        exercised with no systems declared, where only it can speak.
        """
        row = {
            "item_id": INSTANCES[0],
            "system": "a",
            "run": 0,
            "instrument": fetch.INSTRUMENT,
            "label": 1,
        }

        with pytest.raises(fetch.GateFailure, match="gate 4"):
            fetch.run_gates([], {}, [row, dict(row)], INSTANCES)


class TestManifestIsAnInput:
    """The fetcher used to write its own expected checksums from what it had just observed."""

    def observed(self):
        return {
            "board": {"sha256": "aaa"},
            "dataset": {"sha256": "bbb"},
            "artifacts": [{"system": "a", "sha256": "ccc"}],
            "derived": {"labels.csv": "ddd", "rows": 10},
        }

    def test_an_identical_manifest_reports_no_problems(self) -> None:
        assert fetch.compare_manifest(self.observed(), self.observed()) == []

    def test_a_changed_upstream_artifact_is_caught(self) -> None:
        expected = self.observed()
        expected["artifacts"] = [{"system": "a", "sha256": "different"}]

        assert any("artifact a" in p for p in fetch.compare_manifest(expected, self.observed()))

    def test_a_changed_dataset_is_caught(self) -> None:
        expected = self.observed()
        expected["dataset"] = {"sha256": "different"}

        assert any("dataset" in p for p in fetch.compare_manifest(expected, self.observed()))

    def test_a_changed_derived_table_is_caught(self) -> None:
        expected = self.observed()
        expected["derived"] = {"labels.csv": "different", "rows": 10}

        assert any("labels.csv" in p for p in fetch.compare_manifest(expected, self.observed()))

    def test_a_changed_selection_is_caught(self) -> None:
        expected = self.observed()
        expected["artifacts"] = [{"system": "z", "sha256": "ccc"}]

        assert any(
            "selected systems differ" in p
            for p in fetch.compare_manifest(expected, self.observed())
        )

    def test_row_count_alone_does_not_trigger(self) -> None:
        """`rows` is descriptive; the digest is the check."""
        expected = self.observed()
        expected["derived"]["rows"] = 999

        assert fetch.compare_manifest(expected, self.observed()) == []


class TestOutputStaging:
    def test_a_run_starts_from_no_derived_files(self, tmp_path, monkeypatch) -> None:
        """A failed fetch left the previous table readable as current."""
        monkeypatch.setattr(fetch, "DERIVED", tmp_path)
        stale = tmp_path / "labels.csv"
        stale.write_text("stale", encoding="utf-8")

        fetch.clear_outputs()

        assert not stale.exists()

    def test_writes_are_atomic_and_leave_no_partial(self, tmp_path) -> None:
        target = tmp_path / "out.csv"

        digest = fetch.atomic_write(target, "a,b\n1,2\n")

        assert target.read_text(encoding="utf-8") == "a,b\n1,2\n"
        assert not (tmp_path / "out.csv.partial").exists()
        assert len(digest) == 64


class TestBoardSelection:
    def test_the_named_board_is_selected(self) -> None:
        document = {
            "leaderboards": [
                {"name": "Lite", "results": [{"resolved": 1.0}]},
                {"name": "Verified", "results": [{"resolved": 2.0}]},
            ]
        }

        assert fetch.select_board(document)[0]["resolved"] == 2.0

    def test_a_missing_board_is_rejected(self) -> None:
        with pytest.raises(fetch.GateFailure, match="no board named"):
            fetch.select_board({"leaderboards": [{"name": "Lite", "results": []}]})

    def test_a_malformed_file_is_rejected(self) -> None:
        with pytest.raises(fetch.GateFailure, match="leaderboards"):
            fetch.select_board({"nothing": True})

    def test_published_order_is_preserved(self) -> None:
        results = [{"resolved": 10.0, "folder": "c"}, {"resolved": 90.0, "folder": "a"}]

        entries = fetch.entries_in_published_order(results)

        assert [e.folder for e in entries] == ["c", "a"]
        assert [e.rank for e in entries] == [1, 2]


class TestCommittedManifestMatchesTheRealRun:
    """Ties the committed artifacts to the checked-in manifest without touching the network."""

    def test_the_manifest_lists_the_registered_family(self) -> None:
        manifest = json.loads(
            (
                REPO_ROOT / "experiments" / "swebench" / "manifests" / "upstream_digests.json"
            ).read_text(encoding="utf-8")
        )

        assert len(manifest["artifacts"]) == fetch.N_TOP
        assert manifest["board"]["sha256"] == fetch.BOARD_SHA256
        assert manifest["derived"]["rows"] == fetch.N_TOP * fetch.EXPECTED_INSTANCES

    def test_the_aggregates_match_the_registered_gap_vector(self) -> None:
        aggregates = json.loads(
            (REPO_ROOT / "experiments" / "swebench" / "derived" / "aggregates.json").read_text(
                encoding="utf-8"
            )
        )
        counts = [e["resolved"] for e in aggregates["entries"]]
        gaps = [counts[i] - counts[i + 1] for i in range(len(counts) - 1)]

        assert gaps == [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]
