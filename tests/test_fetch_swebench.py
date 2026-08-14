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
    def test_existing_outputs_survive_the_start_of_a_run(self, tmp_path, monkeypatch) -> None:
        """Superseded: clearing first dirtied a clean clone on any network failure.

        Outputs are preserved until every check passes and are then replaced atomically.
        Staleness is caught downstream, where T3.2 verifies input checksums before reading.
        """
        monkeypatch.setattr(fetch, "DERIVED", tmp_path)
        existing = tmp_path / "labels.csv"
        existing.write_text("previous", encoding="utf-8")

        fetch.clear_partials()

        assert existing.read_text(encoding="utf-8") == "previous"

    def test_leftover_partials_are_removed(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(fetch, "DERIVED", tmp_path)
        leftover = tmp_path / "labels.csv.partial"
        leftover.write_text("half", encoding="utf-8")

        fetch.clear_partials()

        assert not leftover.exists()

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


class TestDerivedFilesAreNotTracked:
    """D1.4: derived upstream data is generated, never committed.

    The ignore rule named `labels.csv` specifically, so the sidecar added later was tracked and
    23 per-instance ids were committed. The rule is now deny-by-default with an allowlist, so a
    new derived file is ignored unless someone deliberately permits it.
    """

    def tracked(self) -> list[str]:
        import subprocess

        out = subprocess.run(
            ["git", "ls-files", "experiments/swebench/derived/"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in out.stdout.splitlines() if line]

    def test_the_unevaluated_sidecar_is_not_tracked(self) -> None:
        assert not any("unevaluated.json" in path for path in self.tracked())

    def test_the_label_table_is_not_tracked(self) -> None:
        assert not any("labels.csv" in path for path in self.tracked())

    def test_only_the_de_minimis_aggregates_are_tracked(self) -> None:
        assert self.tracked() == ["experiments/swebench/derived/aggregates.json"]

    def test_a_hypothetical_new_derived_file_would_be_ignored(self) -> None:
        """Deny-by-default: the next sidecar must not repeat this."""
        import subprocess

        result = subprocess.run(
            ["git", "check-ignore", "experiments/swebench/derived/something_new.json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "a new derived file would be tracked by default"


class TestManifestComparisonIsOrdered:
    def observed(self):
        return {
            "board": {"sha256": "aaa"},
            "dataset": {"sha256": "bbb"},
            "artifacts": [
                {"system": "a", "sha256": "c1"},
                {"system": "b", "sha256": "c2"},
                {"system": "c", "sha256": "c3"},
            ],
            "derived": {"labels.csv": "d", "unevaluated.json": "e", "aggregates.json": "f"},
        }

    def test_reordered_artifacts_are_caught(self) -> None:
        """Adjacency is defined by order, so an order change is a different experiment."""
        expected = self.observed()
        expected["artifacts"] = list(reversed(expected["artifacts"]))

        assert any("order" in p for p in fetch.compare_manifest(expected, self.observed()))

    def test_identical_order_reports_nothing(self) -> None:
        assert fetch.compare_manifest(self.observed(), self.observed()) == []

    def test_aggregates_are_checksummed(self) -> None:
        expected = self.observed()
        expected["derived"]["aggregates.json"] = "changed"

        assert any(
            "aggregates.json" in p for p in fetch.compare_manifest(expected, self.observed())
        )

    def test_a_missing_manifest_field_is_caught(self) -> None:
        expected = self.observed()
        del expected["derived"]["unevaluated.json"]

        assert any(
            "unevaluated.json" in p for p in fetch.compare_manifest(expected, self.observed())
        )

    def test_an_extra_manifest_field_is_caught(self) -> None:
        expected = self.observed()
        expected["derived"]["surprise.json"] = "x"

        assert any("surprise.json" in p for p in fetch.compare_manifest(expected, self.observed()))


class TestUnevaluatedIdsAreValidated:
    def canonical(self):
        return set(INSTANCES)

    def test_a_stray_no_logs_id_is_disqualified(self) -> None:
        """A sensitivity analysis cannot drop an instance that is not in the set."""
        art = artifact("sys", INSTANCES[:2], no_logs={"not-in-verified"})

        reason = fetch.disqualify(entry(1, "sys", 0.4), art, self.canonical())

        assert reason and "no_logs" in reason

    def test_a_stray_no_generation_id_is_disqualified(self) -> None:
        art = artifact("sys", INSTANCES[:2], no_generation={"not-in-verified"})

        reason = fetch.disqualify(entry(1, "sys", 0.4), art, self.canonical())

        assert reason and "no_generation" in reason

    def test_valid_unevaluated_ids_pass(self) -> None:
        art = artifact("sys", INSTANCES[:2], no_logs={INSTANCES[9]})

        assert fetch.disqualify(entry(1, "sys", 0.4), art, self.canonical()) is None

    @pytest.mark.parametrize("key", ["resolved", "no_generation", "no_logs"])
    def test_duplicate_raw_ids_are_rejected_before_the_set_hides_them(self, key: str) -> None:
        document = {"resolved": [], "no_generation": [], "no_logs": []}
        document[key] = ["a__a-1", "a__a-1"]

        with pytest.raises(fetch.GateFailure, match="duplicate"):
            fetch.parse_artifact_document(document, fetch.FORMAT_RESOLVED_LIST, "sys")


class TestDataclassInvariants:
    """D2.3, applied to the fetch dataclasses."""

    def test_a_negative_rank_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="rank"):
            fetch.Entry(rank=0, folder="a", published_rate=1.0, checked=False, date="")

    def test_a_rate_outside_the_percentage_range_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="published_rate"):
            fetch.Entry(rank=1, folder="a", published_rate=140.0, checked=False, date="")

    def test_a_malformed_digest_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="sha256"):
            fetch.Artifact(
                folder="a",
                split_dir="verified",
                artifact_format=fetch.FORMAT_RESOLVED_LIST,
                url="x",
                sha256="short",
                resolved=set(),
            )

    def test_an_id_both_resolved_and_unevaluated_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="both"):
            fetch.Artifact(
                folder="a",
                split_dir="verified",
                artifact_format=fetch.FORMAT_RESOLVED_LIST,
                url="x",
                sha256="0" * 64,
                resolved={"i1"},
                no_logs={"i1"},
            )


class TestTraversalAndFailureHandling:
    def test_traversal_continues_past_many_failures(self, monkeypatch) -> None:
        """Eleven unusable entries, then twenty good ones. A fixed lookahead would have stopped."""
        entries = [entry(i + 1, f"bad{i}", 0.4) for i in range(11)]
        entries += [entry(12 + i, f"good{i}", 0.4) for i in range(20)]

        def stub(folder: str):
            if folder.startswith("bad"):
                return None
            return artifact(folder, INSTANCES[:2])

        monkeypatch.setattr(fetch, "fetch_artifact", stub)
        chosen, artifacts, substitutions = fetch.select_lazily(entries, set(INSTANCES))

        assert len(chosen) == 20
        assert len(substitutions) == 11
        assert all(s["reason"].startswith("no artifact") for s in substitutions)

    def test_a_failed_run_leaves_existing_outputs_untouched(self, tmp_path, monkeypatch) -> None:
        """Clearing first dirtied a clean clone whenever the network failed."""
        monkeypatch.setattr(fetch, "DERIVED", tmp_path)
        monkeypatch.setattr(fetch, "MANIFESTS", tmp_path)
        monkeypatch.setattr(fetch, "MANIFEST_PATH", tmp_path / "upstream_digests.json")
        (tmp_path / "upstream_digests.json").write_text("{}", encoding="utf-8")
        survivor = tmp_path / "aggregates.json"
        survivor.write_text('{"kept": true}', encoding="utf-8")

        def boom(url: str):
            raise OSError("network down")

        monkeypatch.setattr(fetch, "fetch_bytes", boom)
        with pytest.raises(OSError):
            fetch.main([])

        assert survivor.read_text(encoding="utf-8") == '{"kept": true}'


class TestFetchDate:
    """T3.4 spec section 2: fetch_date needs one committed source. It was a literal in
    run.py and absent from the manifest, so validating a card against a second literal
    in report.py would have created the duplicate the check exists to catch.

    Offline migration on purpose: a fetch run today cannot establish the historical
    date, only that the pinned bytes are still reachable, so re-fetching would risk the
    committed digests for no evidence.
    """

    def manifest(self) -> dict:
        path = (
            Path(__file__).resolve().parent.parent
            / "experiments/swebench/manifests/upstream_digests.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_manifest_carries_the_fetch_date(self) -> None:
        assert self.manifest()["fetch_date"] == "2026-07-29"

    def test_bootstrap_requires_an_explicit_fetch_date(self, tmp_path, monkeypatch, capsys) -> None:
        """--bootstrap must never invent a date, and must reject before any network call.

        `fetch_bytes` is patched to blow up loudly if reached, so a regression that lets the
        guard fall through fails on `boom`'s message rather than performing a live fetch that
        overwrites the committed manifest, as the unguarded RED-phase run of this test once did.
        """

        def boom(url: str):
            raise AssertionError("guard did not fire, network reached")

        monkeypatch.setattr(fetch, "fetch_bytes", boom)
        monkeypatch.setattr(fetch, "MANIFEST_PATH", tmp_path / "m.json")

        with pytest.raises(SystemExit):
            fetch.main(["--bootstrap"])

        # pytest.raises(SystemExit) alone passes for any argparse failure, so renaming or
        # deleting --bootstrap would keep the test green. Pin the actual reason.
        assert "--bootstrap requires --fetch-date" in capsys.readouterr().err

    def test_bootstrap_with_a_fetch_date_reaches_past_the_guard(
        self, tmp_path, monkeypatch
    ) -> None:
        """The positive control: the guard rejects the missing-date case and only that case."""

        def boom(url: str):
            raise AssertionError("reached the network")

        monkeypatch.setattr(fetch, "fetch_bytes", boom)
        monkeypatch.setattr(fetch, "MANIFEST_PATH", tmp_path / "m.json")

        with pytest.raises(AssertionError, match="reached the network"):
            fetch.main(["--bootstrap", "--fetch-date", "2026-07-29"])

    def test_a_malformed_fetch_date_is_rejected_before_the_fetch(
        self, tmp_path, monkeypatch
    ) -> None:
        """`--bootstrap` requiring *some* value for --fetch-date is not the same guard as
        requiring a *canonical* one; a non-canonical value must not reach the network either.
        """

        def boom(url: str):
            raise AssertionError("reached the network with a malformed date still unrejected")

        monkeypatch.setattr(fetch, "fetch_bytes", boom)
        monkeypatch.setattr(fetch, "MANIFEST_PATH", tmp_path / "m.json")

        with pytest.raises(ValueError, match="canonical"):
            fetch.main(["--bootstrap", "--fetch-date", "2026-7-29"])

    def test_fetch_date_must_be_canonical(self) -> None:
        from metrology.reporting import require_canonical_date

        for bad in ("2026-13-01", "2026-7-29", "20260729", "not-a-date", ""):
            with pytest.raises(ValueError, match="canonical"):
                require_canonical_date(bad, "fetch_date")
        for wrong_type in (20260729, None):
            with pytest.raises(TypeError, match="string"):
                require_canonical_date(wrong_type, "fetch_date")
        assert require_canonical_date("2026-07-29", "fetch_date") == "2026-07-29"
