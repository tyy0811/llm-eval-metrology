"""T3.2 analysis logic, exercised without network or a real fetch.

T3.1 shipped with no tests and two defects survived because nothing could fail. The pure half of
`run.py` is tested here for the same reason: input verification, the pairing arithmetic, the
straddle diagnostic, the pairwise drop, and the seed derivation.

The committed results file is also checked against the registered expectations, so a rerun that
silently changes the headline fails here rather than in a write-up.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT = REPO_ROOT / "experiments" / "swebench"


def load_run():
    spec = importlib.util.spec_from_file_location("swebench_run", EXPERIMENT / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run = load_run()


def entry(rank: int, system: str, date: str) -> dict:
    return {"rank": rank, "system": system, "date": date}


class TestInputVerification:
    """Inputs are checked before they are read, because a failed fetch preserves stale outputs."""

    def setup_manifest(self, tmp_path, digests: dict) -> None:
        (tmp_path / "manifests").mkdir(exist_ok=True)
        (tmp_path / "derived").mkdir(exist_ok=True)
        (tmp_path / "manifests" / "upstream_digests.json").write_text(
            json.dumps({"derived": digests}), encoding="utf-8"
        )

    def point_at(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(run, "DERIVED", tmp_path / "derived")
        monkeypatch.setattr(run, "MANIFEST_PATH", tmp_path / "manifests" / "upstream_digests.json")

    def test_a_matching_input_passes(self, tmp_path, monkeypatch) -> None:
        body = b"item_id,system\n"
        digest = hashlib.sha256(body).hexdigest()
        self.setup_manifest(tmp_path, {"labels.csv": digest, "rows": 1})
        (tmp_path / "derived" / "labels.csv").write_bytes(body)
        self.point_at(tmp_path, monkeypatch)

        assert run.verify_inputs()["derived"]["labels.csv"] == digest

    def test_a_stale_input_is_rejected(self, tmp_path, monkeypatch) -> None:
        self.setup_manifest(tmp_path, {"labels.csv": "0" * 64})
        (tmp_path / "derived" / "labels.csv").write_bytes(b"different")
        self.point_at(tmp_path, monkeypatch)

        with pytest.raises(run.RunFailure, match="labels.csv"):
            run.verify_inputs()

    def test_a_missing_input_is_rejected(self, tmp_path, monkeypatch) -> None:
        self.setup_manifest(tmp_path, {"labels.csv": "0" * 64})
        self.point_at(tmp_path, monkeypatch)

        with pytest.raises(run.RunFailure, match="absent"):
            run.verify_inputs()

    def test_a_missing_manifest_is_rejected(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(run, "MANIFEST_PATH", tmp_path / "nope.json")

        with pytest.raises(run.RunFailure, match="manifest"):
            run.verify_inputs()


class TestAdjacency:
    def test_pairs_follow_published_order(self) -> None:
        entries = [entry(i + 1, f"s{i}", "2025-01-01") for i in range(4)]

        pairs = run.adjacent_pairs(entries)

        assert [(a["rank"], b["rank"]) for a, b in pairs] == [(1, 2), (2, 3), (3, 4)]

    def test_a_family_of_n_has_n_minus_one_pairs(self) -> None:
        entries = [entry(i + 1, f"s{i}", "2025-01-01") for i in range(20)]

        assert len(run.adjacent_pairs(entries)) == 19


class TestStraddleDiagnostic:
    def test_no_straddle_when_every_entry_postdates_the_fix(self) -> None:
        entries = [entry(i + 1, f"s{i}", "2025-06-03") for i in range(3)]

        result = run.straddle_diagnostic(entries)

        assert result["entries_predating_the_fix"] == 0
        assert result["straddling_pairs"] == []

    def test_a_crossing_pair_is_reported(self) -> None:
        entries = [
            entry(1, "old", "2024-01-01"),
            entry(2, "new", "2025-01-01"),
            entry(3, "newer", "2025-02-01"),
        ]

        result = run.straddle_diagnostic(entries)

        assert result["entries_predating_the_fix"] == 1
        assert result["straddling_pairs"] == [{"rank_a": 1, "rank_b": 2}]

    def test_the_boundary_is_the_documented_fix_date(self) -> None:
        assert run.HARNESS_FIX_BOUNDARY == "2024-04-15"


class TestSeedDerivation:
    def test_seeds_are_deterministic(self) -> None:
        assert run.pair_seed(3) == run.pair_seed(3)

    def test_seeds_differ_by_pair(self) -> None:
        assert len({run.pair_seed(i) for i in range(19)}) == 19

    def test_seeds_derive_from_the_registered_master(self) -> None:
        assert run.MASTER_SEED == 20260727
        assert run.pair_seed(0) == run.MASTER_SEED * 100


class TestRegisteredConfiguration:
    """The constants a reader checks against the pre-registration."""

    def test_the_registered_parameters_are_unchanged(self) -> None:
        assert (run.ALPHA, run.BOOTSTRAP_RESAMPLES, run.BOOTSTRAP_LEVEL) == (0.05, 10000, 0.95)
        assert (run.MDE_ALPHA, run.TARGET_POWER) == (0.05, 0.80)
        assert run.SECONDARY_FAMILY_SIZE == 10


class TestCommittedResults:
    """The published result must not drift silently between runs."""

    def results(self) -> dict:
        return json.loads((EXPERIMENT / "results" / "results.json").read_text(encoding="utf-8"))

    def test_the_headline_is_zero_of_nineteen(self) -> None:
        primary = self.results()["primary"]

        assert primary["separable_count"] == 0
        assert primary["resolved_count"] == 0
        assert primary["family_size"] == 19

    def test_the_headline_matches_the_analytic_derivation(self) -> None:
        """PREREG D7: the count follows from published rates alone."""
        primary = self.results()["primary"]

        assert primary["largest_observed_gap"] < primary["first_rejection_gap_floor"]
        assert primary["first_rejection_gap_floor"] == 10
        assert primary["needs_per_instance_data"] is False

    def test_every_pair_carries_its_registered_quantities(self) -> None:
        for pair in self.results()["pairs"]:
            assert pair["bootstrap"]["n_resamples"] == 10000
            assert pair["bootstrap"]["unit"] == "instance"
            assert pair["mde"]["status"] in {"attainable", "unattainable"}
            assert pair["adjusted_p_value"] is not None

    def test_tied_pairs_still_have_real_discordance(self) -> None:
        """D2.5 on real data: gap zero does not mean nothing to measure."""
        tied = [p for p in self.results()["pairs"] if p["net_edge"] == 0]

        assert tied, "the registered family contains tied pairs"
        assert all(p["n_discordant"] > 0 for p in tied)
        assert all(p["mde"]["status"] == "attainable" for p in tied)

    def test_the_no_logs_sensitivity_ran(self) -> None:
        """Registered as a contingency and triggered by the real data."""
        sensitivity = self.results()["secondary"]["no_logs_sensitivity"]

        assert sensitivity["total_pairs_affected"] > 0
        for pair in sensitivity["pairs"]:
            assert pair["n_items"] == 500 - pair["dropped_instances"]

    def test_the_straddle_diagnostic_ran_and_found_nothing(self) -> None:
        straddle = self.results()["secondary"]["harness_straddle"]

        assert straddle["entries_predating_the_fix"] == 0
        assert straddle["straddling_pairs"] == []

    def test_the_secondary_family_is_the_non_tied_pairs(self) -> None:
        secondary = self.results()["secondary"]["non_tied_family"]

        assert secondary["size"] == 10
        assert secondary["gap_floor"] == 9
        assert secondary["rejected"] == 0
