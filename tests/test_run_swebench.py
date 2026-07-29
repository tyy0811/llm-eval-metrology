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


class TestAnalyticExpectationUsesD27:
    """The assertion had reintroduced the option-1 definition D2.7 superseded."""

    def test_the_recorded_counterexample(self) -> None:
        """Gaps 40 and 6: per-gap against alpha/m gives 1, Holm over the vector gives 2."""
        from metrology.paired import p_value_floor

        gaps = [40, 6]
        option_one = sum(1 for g in gaps if p_value_floor(g) <= 0.05 / len(gaps))

        assert option_one == 1
        assert run.analytic_separable_count(gaps, 0.05) == 2

    def test_the_registered_gaps_give_zero(self) -> None:
        """Both definitions agree here, which is why the wrong one survived."""
        gaps = [0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0]

        assert run.analytic_separable_count(gaps, 0.05) == 0

    def test_a_pair_below_the_gateway_can_still_be_separable(self) -> None:
        assert run.analytic_separable_count([40, 6], 0.05) == 2
        assert run.analytic_separable_count([6, 6], 0.05) == 0


class TestCoverageConditional:
    """PREREG D1 makes the forced-zero result conditional on no substitution."""

    class FakeFamily:
        def __init__(self, gaps, separable, alpha=0.05):
            self.alpha = alpha
            self.separable_count = separable
            self.members = [type("M", (), {"net_edge": g})() for g in gaps]

    def aggregates(self, gaps, substitutions=()):
        counts, running = [], 100
        for gap in [0, *gaps]:
            running -= gap
            counts.append(running)
        return {
            "entries": [{"resolved": c} for c in counts],
            "substitutions": list(substitutions),
        }

    def test_a_substitution_halts_the_run(self) -> None:
        family = self.FakeFamily([0, 2], 0)
        aggregates = self.aggregates([0, 2], substitutions=[{"rank": 5, "reason": "x"}])

        with pytest.raises(run.RunFailure, match="coverage rule fired"):
            run.check_analytic_expectation(family, aggregates)

    def test_a_clean_set_passes(self) -> None:
        family = self.FakeFamily([0, 2], 0)

        run.check_analytic_expectation(family, self.aggregates([0, 2]))

    def test_a_derived_gap_vector_that_drifts_is_caught(self) -> None:
        family = self.FakeFamily([0, 9], 0)

        with pytest.raises(run.RunFailure, match="gap vector"):
            run.check_analytic_expectation(family, self.aggregates([0, 2]))

    def test_a_separable_count_contradicting_the_derivation_is_caught(self) -> None:
        family = self.FakeFamily([0, 2], 1)

        with pytest.raises(run.RunFailure, match="contradicts the analytic derivation"):
            run.check_analytic_expectation(family, self.aggregates([0, 2]))


class TestIllustrativeSelectionRule:
    """D8 registers a rule, so the rule is applied rather than its output hard-coded."""

    def entries(self, resolved):
        return [
            {"rank": i + 1, "system": f"s{i}", "resolved": r, "date": "2025-06-03"}
            for i, r in enumerate(resolved)
        ]

    def test_first_pair_and_widest_gap_are_chosen(self) -> None:
        names = run.illustrative_pair_names(self.entries([100, 100, 98, 91, 90]))

        assert names == ["rank_1_vs_2", "rank_3_vs_4"]

    def test_a_maximum_gap_tie_breaks_by_earliest_rank(self) -> None:
        names = run.illustrative_pair_names(self.entries([100, 95, 90, 85]))

        assert names == ["rank_1_vs_2"] or names[1] == "rank_1_vs_2"

    def test_the_registered_family_selects_ranks_1_2_and_3_4(self) -> None:
        aggregates = json.loads(
            (EXPERIMENT / "derived" / "aggregates.json").read_text(encoding="utf-8")
        )

        assert run.illustrative_pair_names(aggregates["entries"]) == [
            "rank_1_vs_2",
            "rank_3_vs_4",
        ]


class TestCommittedCards:
    def cards(self) -> dict:
        return json.loads((EXPERIMENT / "results" / "cards.json").read_text(encoding="utf-8"))

    def test_provenance_names_the_artifact_revision_not_the_board(self) -> None:
        for card in self.cards()["pairs"].values():
            assert card["provenance"]["source"] == "SWE-bench/experiments"
            assert card["provenance"]["pinned_revision"].startswith("2f15350")

    def test_the_fetch_date_is_a_real_committed_date(self) -> None:
        import re

        for card in self.cards()["pairs"].values():
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", card["provenance"]["fetch_date"])

    def test_the_widest_gap_card_discloses_the_malformed_checked_field(self) -> None:
        """D8: the card must not quietly clean up its own source."""
        disclosures = self.cards()["pairs"]["rank_3_vs_4"]["provenance"]["deviations"]

        assert any("checked" in d and "not a boolean" in d for d in disclosures)

    def test_the_first_pair_card_carries_no_such_disclosure(self) -> None:
        disclosures = self.cards()["pairs"]["rank_1_vs_2"]["provenance"]["deviations"]

        assert not any("checked" in d for d in disclosures)

    def test_the_family_card_carries_no_verdict(self) -> None:
        assert "verdict" not in self.cards()["family"]


class TestSensitivityConclusionIsDerived:
    def sensitivity(self) -> dict:
        results = json.loads((EXPERIMENT / "results" / "results.json").read_text(encoding="utf-8"))
        return results["secondary"]["no_logs_sensitivity"]

    def test_the_family_conclusion_is_machine_derived(self) -> None:
        family = self.sensitivity()["family"]

        assert family["size"] == 19
        assert family["resolved_count"] == 0
        assert family["separable_count"] == 0

    def test_every_pair_carries_an_adjusted_value_and_a_flag(self) -> None:
        for pair in self.sensitivity()["pairs"]:
            assert "adjusted_p_value" in pair
            assert pair["rejected"] is False


class TestCoverageIsReported:
    def test_substitutions_appear_in_the_committed_result(self) -> None:
        primary = json.loads((EXPERIMENT / "results" / "results.json").read_text(encoding="utf-8"))[
            "primary"
        ]

        assert primary["substitutions"] == []
        assert primary["coverage_rule_fired"] is False


class TestMainWiring:
    """Exercised through `main()`, because a helper can be correct and never called.

    The D2.7 fix was written, tested in isolation, and reported done while `main()` still ran the
    superseded per-gap calculation. Unit tests on the helper could not see that; only a test that
    goes through the live path can.
    """

    def build_inputs(self, tmp_path, resolved: list[int], substitutions=()):
        """A miniature experiment on disk: labels, aggregates, sidecar, and a matching manifest."""
        n_items = 500
        instances = [f"repo__pkg-{i:04d}" for i in range(n_items)]
        systems = [f"sys{i}" for i in range(len(resolved))]

        rows = ["item_id,system,run,instrument,label"]
        pairs = []
        for item in instances:
            for system, count in zip(systems, resolved, strict=True):
                label = 1 if int(item.split("-")[1]) < count else 0
                pairs.append((item, system, label))
        for item, system, label in sorted(pairs):
            rows.append(f"{item},{system},0,hidden-tests,{label}")
        labels = "\n".join(rows) + "\n"

        aggregates = (
            json.dumps(
                {
                    "board": "Verified",
                    "family_size": len(systems),
                    "n_items": n_items,
                    "instrument": "hidden-tests",
                    "entries": [
                        {
                            "rank": index + 1,
                            "system": system,
                            "date": "2025-06-03",
                            "resolved": count,
                            "published_rate": 100.0 * count / n_items,
                            "artifact_format": "resolved-id-list",
                            "split_dir": "verified",
                            "no_generation": 0,
                            "no_logs": 0,
                            "checked": False,
                            "checked_is_malformed": False,
                            "checked_raw": None,
                        }
                        for index, (system, count) in enumerate(zip(systems, resolved, strict=True))
                    ],
                    "substitutions": list(substitutions),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        unevaluated = (
            json.dumps(
                {s: {"no_generation": [], "no_logs": []} for s in systems}, indent=2, sort_keys=True
            )
            + "\n"
        )

        derived = tmp_path / "derived"
        derived.mkdir()
        (derived / "labels.csv").write_text(labels, encoding="utf-8")
        (derived / "aggregates.json").write_text(aggregates, encoding="utf-8")
        (derived / "unevaluated.json").write_text(unevaluated, encoding="utf-8")

        manifests = tmp_path / "manifests"
        manifests.mkdir()
        (manifests / "upstream_digests.json").write_text(
            json.dumps(
                {
                    "board": {"commit": "b" * 40, "sha256": "0" * 64},
                    "artifacts": [
                        {
                            "system": systems[0],
                            "url": "https://x/experiments/a" * 1 + "/y",
                            "sha256": "0" * 64,
                        }
                    ],
                    "derived": {
                        name: hashlib.sha256((derived / name).read_bytes()).hexdigest()
                        for name in ("labels.csv", "aggregates.json", "unevaluated.json")
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return derived, manifests

    def point_at(self, tmp_path, monkeypatch, derived, manifests) -> None:
        monkeypatch.setattr(run, "DERIVED", derived)
        monkeypatch.setattr(run, "MANIFEST_PATH", manifests / "upstream_digests.json")
        monkeypatch.setattr(run, "RESULTS", tmp_path / "results")

    def test_the_counterexample_runs_through_main(self, tmp_path, monkeypatch) -> None:
        """Gaps 40 and 6. The superseded calculation raised "gives 1" here; D2.7 gives 2."""
        derived, manifests = self.build_inputs(tmp_path, [100, 60, 54])
        self.point_at(tmp_path, monkeypatch, derived, manifests)

        assert run.main([]) == 0

        results = json.loads((tmp_path / "results" / "results.json").read_text(encoding="utf-8"))
        assert results["primary"]["separable_count"] == 2

    def test_a_substitution_halts_main_before_any_analysis(self, tmp_path, monkeypatch) -> None:
        derived, manifests = self.build_inputs(
            tmp_path, [100, 60, 54], substitutions=[{"rank": 4, "reason": "no artifact"}]
        )
        self.point_at(tmp_path, monkeypatch, derived, manifests)

        with pytest.raises(run.RunFailure, match="coverage rule fired"):
            run.main([])

        assert not (tmp_path / "results").exists()

    def test_a_stale_input_halts_main(self, tmp_path, monkeypatch) -> None:
        derived, manifests = self.build_inputs(tmp_path, [100, 60, 54])
        (derived / "labels.csv").write_text("tampered\n", encoding="utf-8")
        self.point_at(tmp_path, monkeypatch, derived, manifests)

        with pytest.raises(run.RunFailure, match="labels.csv"):
            run.main([])


class TestFamilyCardProvenance:
    """D1.11: the headline derives from the board, so the family card must name the board."""

    def family_card(self) -> dict:
        return json.loads((EXPERIMENT / "results" / "cards.json").read_text(encoding="utf-8"))[
            "family"
        ]

    def test_the_headline_source_is_the_leaderboard(self) -> None:
        provenance = self.family_card()["provenance"]

        assert provenance["source"] == "SWE-bench/swe-bench.github.io"
        assert provenance["pinned_revision"].startswith("7c4289f")

    def test_the_observed_figures_name_the_artifact_source(self) -> None:
        """The card also shows resolved counts, which do read per-instance data."""
        provenance = self.family_card()["provenance"]

        assert provenance["secondary_source"] == "SWE-bench/experiments"
        assert provenance["secondary_revision"].startswith("2f15350")

    def test_d4_does_not_qualify_the_headline(self) -> None:
        disclosure = self.family_card()["family_finding"]["disclosure"]

        assert disclosure["applies_to_headline"] == []
        assert "D4 harness comparability" in disclosure["applies_to_secondary"]

    def test_pair_cards_still_name_the_artifact_source_alone(self) -> None:
        cards = json.loads((EXPERIMENT / "results" / "cards.json").read_text(encoding="utf-8"))

        for card in cards["pairs"].values():
            assert card["provenance"]["source"] == "SWE-bench/experiments"
            assert card["provenance"]["secondary_source"] is None
