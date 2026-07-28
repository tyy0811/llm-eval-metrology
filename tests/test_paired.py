"""T2.2: paired comparison of binary labels.

Constraints registered in `experiments/swebench/PREREG.md` deviation D6 govern this module.
The two-sided exact p-value is twice the smaller binomial tail at p = 0.5, capped at 1. Mid-p is
excluded by name, because it halves the value and lowers every registered threshold by one gap.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import binomtest

from metrology.paired import (
    TWO_SIDED_CONVENTION,
    clustered_bootstrap_difference,
    mcnemar_exact,
    mcnemar_exact_from_counts,
    minimum_gap_for_threshold,
    p_value_floor,
    paired_bootstrap_difference,
)
from metrology.schema import LabelTable, PairedLabels, SchemaError


def pair_from(labels_a, labels_b):
    rows = []
    for index, (a, b) in enumerate(zip(labels_a, labels_b, strict=True)):
        item = f"i{index:03d}"
        rows.append({"item_id": item, "system": "A", "instrument": "t", "label": a})
        rows.append({"item_id": item, "system": "B", "instrument": "t", "label": b})
    return LabelTable.from_rows(rows).paired("A", "B", instrument="t")


class TestMcNemarConvention:
    def test_convention_is_the_doubled_tail_not_mid_p(self) -> None:
        assert TWO_SIDED_CONVENTION == "doubled-tail"
        assert mcnemar_exact_from_counts(n01=0, n10=7).convention == "doubled-tail"

    def test_mid_p_would_give_a_different_answer(self) -> None:
        """Registered as excluded, so the difference is asserted rather than assumed."""
        doubled = mcnemar_exact_from_counts(n01=0, n10=8).p_value
        mid_p = 2.0 ** (-8)

        assert doubled == pytest.approx(2.0**-7)
        assert doubled != pytest.approx(mid_p)

    @pytest.mark.parametrize("gap", list(range(0, 11)))
    def test_floor_is_attained_when_all_discordance_runs_one_way(self, gap: int) -> None:
        """The D6 fixture: gaps 0 to 10 under the declared convention."""
        result = mcnemar_exact_from_counts(n01=0, n10=gap)

        assert result.p_value == pytest.approx(min(1.0, 2.0 ** (1 - gap)))

    def test_gap_zero_and_gap_one_both_return_exactly_one(self) -> None:
        assert mcnemar_exact_from_counts(n01=0, n10=0).p_value == 1.0
        assert mcnemar_exact_from_counts(n01=0, n10=1).p_value == 1.0

    @pytest.mark.parametrize(
        ("n01", "n10"),
        [(0, 7), (3, 10), (5, 5), (1, 4), (12, 31), (0, 1), (2, 2)],
    )
    def test_agrees_with_scipy_for_the_symmetric_case(self, n01: int, n10: int) -> None:
        """At p = 0.5 the no-more-probable rule coincides with doubling, verified in D6."""
        expected = binomtest(min(n01, n10), n01 + n10, 0.5, alternative="two-sided").pvalue

        assert mcnemar_exact_from_counts(n01=n01, n10=n10).p_value == pytest.approx(expected)

    def test_p_value_never_exceeds_one(self) -> None:
        for n in range(0, 20):
            assert mcnemar_exact_from_counts(n01=n, n10=n).p_value <= 1.0

    def test_p_value_rises_with_discordance_at_a_fixed_gap(self) -> None:
        """D5's mechanism: spurious disagreement inflates p, it does not deflate it."""
        gap = 7
        values = [mcnemar_exact_from_counts(n01=k, n10=k + gap).p_value for k in range(0, 5)]

        assert values == sorted(values)
        assert values[0] == pytest.approx(0.015625)


class TestMcNemarCounts:
    def test_discordant_counts_are_reported(self) -> None:
        pair = pair_from([1, 1, 0, 0], [1, 0, 1, 0])

        result = mcnemar_exact(pair)

        assert (result.n10, result.n01) == (1, 1)
        assert result.n_discordant == 2

    def test_concordant_pairs_are_excluded_from_the_test(self) -> None:
        pair = pair_from([1, 1, 1, 1], [1, 1, 1, 1])

        result = mcnemar_exact(pair)

        assert result.n_discordant == 0
        assert result.p_value == 1.0

    def test_net_edge_is_the_resolved_count_difference(self) -> None:
        """n10 - n01 equals the difference in totals, which is what fixes the floor."""
        pair = pair_from([1, 1, 1, 0], [0, 0, 1, 0])

        result = mcnemar_exact(pair)

        assert result.net_edge == 2
        assert result.net_edge == int(pair.label_a.sum() - pair.label_b.sum())

    def test_systems_and_instrument_are_carried_through(self) -> None:
        result = mcnemar_exact(pair_from([1, 0], [0, 1]))

        assert (result.system_a, result.system_b, result.instrument) == ("A", "B", "t")

    def test_non_binary_labels_are_rejected(self) -> None:
        with pytest.raises(SchemaError, match="binary"):
            mcnemar_exact(pair_from([0.5, 1.0], [1.0, 0.0]))

    def test_negative_counts_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            mcnemar_exact_from_counts(n01=-1, n10=3)


class TestFloorHelpers:
    def test_floor_matches_the_closed_form(self) -> None:
        assert p_value_floor(0) == 1.0
        assert p_value_floor(1) == 1.0
        assert p_value_floor(7) == pytest.approx(0.015625)

    def test_floor_rejects_a_negative_gap(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            p_value_floor(-1)

    @pytest.mark.parametrize(
        ("threshold", "expected_gap"),
        [(0.05, 6), (0.05 / 10, 9), (0.05 / 19, 10), (0.05 / 9, 9)],
    )
    def test_minimum_gap_matches_the_registered_thresholds(
        self, threshold: float, expected_gap: int
    ) -> None:
        """The table pinned in PREREG deviation D6."""
        assert minimum_gap_for_threshold(threshold) == expected_gap

    def test_minimum_gap_is_the_smallest_that_clears(self) -> None:
        gap = minimum_gap_for_threshold(0.05 / 19)

        assert p_value_floor(gap) <= 0.05 / 19
        assert p_value_floor(gap - 1) > 0.05 / 19


class TestPairedBootstrap:
    def test_point_estimate_is_the_rate_difference(self) -> None:
        pair = pair_from([1, 1, 1, 0], [0, 0, 1, 0])

        result = paired_bootstrap_difference(pair, seed=1)

        assert result.estimate == pytest.approx(0.75 - 0.25)

    def test_same_seed_gives_identical_bounds(self) -> None:
        pair = pair_from([1, 0] * 20, [0, 1] * 20)

        first = paired_bootstrap_difference(pair, seed=20260727)
        second = paired_bootstrap_difference(pair, seed=20260727)

        assert (first.low, first.high) == (second.low, second.high)

    def test_the_seed_is_actually_used(self) -> None:
        """Guards against the seed being ignored in favour of a global or constant RNG.

        Deliberately not "any two seeds differ": bootstrap quantiles on binary data are
        discrete and well determined, so neighbouring seeds routinely agree. Measured here,
        seeds 1 and 2 give identical bounds while seeds 1 and 4 do not. The honest property is
        that the bounds are not constant across seeds.
        """
        pair = pair_from(
            [int((i * 7 + 3) % 5 > 1) for i in range(100)],
            [int((i * 11 + 1) % 4 > 1) for i in range(100)],
        )

        bounds = {
            (
                paired_bootstrap_difference(pair, seed=s).low,
                paired_bootstrap_difference(pair, seed=s).high,
            )
            for s in range(1, 9)
        }

        assert len(bounds) > 1

    def test_interval_contains_the_point_estimate(self) -> None:
        pair = pair_from([1, 1, 1, 0, 1, 0, 1, 1], [0, 1, 1, 0, 0, 0, 1, 0])

        result = paired_bootstrap_difference(pair, seed=7)

        assert result.low <= result.estimate <= result.high

    def test_a_wider_level_gives_a_wider_interval(self) -> None:
        pair = pair_from([1, 0] * 25, [0, 0] * 25)

        narrow = paired_bootstrap_difference(pair, seed=3, level=0.90)
        wide = paired_bootstrap_difference(pair, seed=3, level=0.99)

        assert (wide.high - wide.low) >= (narrow.high - narrow.low)

    def test_identical_labels_give_a_degenerate_interval(self) -> None:
        """No disagreement anywhere means every resample gives the same difference."""
        pair = pair_from([1, 1, 1, 1], [1, 1, 1, 1])

        result = paired_bootstrap_difference(pair, seed=5)

        assert (result.low, result.estimate, result.high) == (0.0, 0.0, 0.0)

    def test_resampling_unit_is_the_instance(self) -> None:
        """Resampling labels independently would break the pairing the design depends on."""
        pair = pair_from([1, 1, 0, 0], [1, 1, 0, 0])

        result = paired_bootstrap_difference(pair, seed=11)

        assert (result.low, result.high) == (0.0, 0.0)

    def test_seed_and_replicate_count_are_recorded(self) -> None:
        result = paired_bootstrap_difference(pair_from([1, 0], [0, 1]), seed=42, n_resamples=500)

        assert result.seed == 42
        assert result.n_resamples == 500

    def test_default_replicate_count_is_the_registered_ten_thousand(self) -> None:
        result = paired_bootstrap_difference(pair_from([1, 0], [0, 1]), seed=1)

        assert result.n_resamples == 10000

    def test_invalid_level_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="level"):
            paired_bootstrap_difference(pair_from([1, 0], [0, 1]), seed=1, level=1.5)


class TestClusteredBootstrap:
    def rows_with_runs(self) -> list[dict]:
        rows = []
        for index in range(6):
            for run in (0, 1):
                rows.append(
                    {
                        "item_id": f"i{index}",
                        "system": "A",
                        "run": run,
                        "instrument": "judge",
                        "label": 1 if index % 2 == 0 else 0,
                    }
                )
                rows.append(
                    {
                        "item_id": f"i{index}",
                        "system": "B",
                        "run": run,
                        "instrument": "judge",
                        "label": 0,
                    }
                )
        return rows

    def test_handles_repeated_runs_that_paired_refuses(self) -> None:
        table = LabelTable.from_rows(self.rows_with_runs())

        with pytest.raises(SchemaError, match="run"):
            table.paired("A", "B", instrument="judge")

        result = clustered_bootstrap_difference(table, "A", "B", instrument="judge", seed=1)

        assert result.n_clusters == 6

    def test_point_estimate_uses_per_item_means(self) -> None:
        """Equal weight per item, so an item measured twice does not count twice."""
        table = LabelTable.from_rows(self.rows_with_runs())

        result = clustered_bootstrap_difference(table, "A", "B", instrument="judge", seed=1)

        assert result.estimate == pytest.approx(0.5)

    def test_same_seed_gives_identical_bounds(self) -> None:
        table = LabelTable.from_rows(self.rows_with_runs())

        first = clustered_bootstrap_difference(table, "A", "B", instrument="judge", seed=99)
        second = clustered_bootstrap_difference(table, "A", "B", instrument="judge", seed=99)

        assert (first.low, first.high) == (second.low, second.high)

    def test_clusters_are_items_not_rows(self) -> None:
        table = LabelTable.from_rows(self.rows_with_runs())

        result = clustered_bootstrap_difference(table, "A", "B", instrument="judge", seed=2)

        assert result.n_clusters == len(table.items)

    def test_an_item_missing_from_one_system_is_rejected(self) -> None:
        rows = self.rows_with_runs()
        rows.append(
            {"item_id": "extra", "system": "A", "run": 0, "instrument": "judge", "label": 1}
        )
        table = LabelTable.from_rows(rows)

        with pytest.raises(SchemaError, match="extra"):
            clustered_bootstrap_difference(table, "A", "B", instrument="judge", seed=1)


class TestOutputRegression:
    def test_bootstrap_bounds_are_stable_values(self) -> None:
        """An output regression fixture, which is weaker than it first appears.

        Golden values recorded from a run, not derived. They are not independently correct;
        they must simply not change. This catches a switched resampling unit, a changed
        percentile rule, or a reworked estimator.

        It is **not** an RNG stream lock. Percentile bounds are coarse, so a different stream
        can easily produce the same quantiles and pass this test. `TestRngStreamLock` asserts
        the raw draws and is the check that actually pins the stream.

        Recorded 2026-07-28 under the pinned environment in `requirements.txt`. Changing these
        values is a determinism event and requires a DECISIONS entry, per D0.5.
        """
        pair = pair_from([1, 1, 1, 0, 0, 1, 0, 1, 1, 0], [0, 1, 0, 0, 1, 1, 0, 0, 1, 0])

        result = paired_bootstrap_difference(pair, seed=20260727, n_resamples=1000)

        assert math.isfinite(result.low) and math.isfinite(result.high)
        assert np.isclose(result.estimate, 0.2)
        assert result.low == pytest.approx(-0.2, abs=1e-12)
        assert result.high == pytest.approx(0.6, abs=1e-12)


class TestSeedIsAlwaysRequired:
    """An unseeded resample draws ambient entropy and silently breaks the determinism gate."""

    def rows(self) -> list[dict]:
        rows = []
        for index in range(4):
            rows.append({"item_id": f"i{index}", "system": "A", "instrument": "j", "label": 1})
            rows.append({"item_id": f"i{index}", "system": "B", "instrument": "j", "label": 0})
        return rows

    def test_clustered_bootstrap_rejects_a_missing_seed(self) -> None:
        table = LabelTable.from_rows(self.rows())

        with pytest.raises(ValueError, match="seed"):
            clustered_bootstrap_difference(table, "A", "B", instrument="j", seed=None)

    def test_paired_bootstrap_rejects_a_missing_seed(self) -> None:
        with pytest.raises(ValueError, match="seed"):
            paired_bootstrap_difference(pair_from([1, 0], [0, 1]), seed=None)


class TestPairedLabelsInvariant:
    def build(self, **overrides):
        fields = {
            "item_id": np.asarray(["i1", "i2"]),
            "label_a": np.asarray([1.0, 0.0]),
            "label_b": np.asarray([0.0, 1.0]),
            "system_a": "A",
            "system_b": "B",
            "instrument": "t",
        }
        fields.update(overrides)
        return PairedLabels(**fields)

    def test_unequal_label_lengths_are_rejected(self) -> None:
        """Broadcasting would silently produce a plausible wrong discordance count."""
        with pytest.raises(SchemaError, match="length"):
            self.build(label_b=np.asarray([0.0]))

    def test_item_id_length_must_match_the_labels(self) -> None:
        with pytest.raises(SchemaError, match="length"):
            self.build(item_id=np.asarray(["i1"]))

    def test_duplicate_items_are_rejected(self) -> None:
        with pytest.raises(SchemaError, match="duplicate"):
            self.build(item_id=np.asarray(["i1", "i1"]))

    def test_non_finite_labels_are_rejected(self) -> None:
        with pytest.raises(SchemaError, match="finite"):
            self.build(label_a=np.asarray([1.0, float("nan")]))

    def test_a_system_paired_with_itself_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="itself"):
            self.build(system_b="A")

    def test_two_dimensional_arrays_are_rejected(self) -> None:
        with pytest.raises(SchemaError, match="one-dimensional"):
            self.build(label_a=np.asarray([[1.0], [0.0]]))

    def test_empty_pair_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="no items"):
            self.build(
                item_id=np.asarray([], dtype="<U2"),
                label_a=np.asarray([]),
                label_b=np.asarray([]),
            )

    def test_labels_are_read_only(self) -> None:
        pair = self.build()

        with pytest.raises(ValueError, match="read-only"):
            pair.label_a[0] = 99.0

    def test_source_arrays_are_copied(self) -> None:
        source = np.asarray([1.0, 0.0])
        pair = self.build(label_a=source)

        source[0] = 99.0

        assert pair.label_a.tolist() == [1.0, 0.0]

    def test_a_valid_pair_still_builds(self) -> None:
        assert self.build().n_items == 2


class TestStrictIntegerValidation:
    @pytest.mark.parametrize("gap", [6.5, float("nan"), float("inf"), True, "3", None])
    def test_p_value_floor_requires_an_exact_integer(self, gap) -> None:
        """nan previously returned 1.0, turning missing data into a not-separable conclusion."""
        with pytest.raises((ValueError, TypeError)):
            p_value_floor(gap)

    def test_integral_float_gap_is_accepted(self) -> None:
        assert p_value_floor(7.0) == pytest.approx(0.015625)

    @pytest.mark.parametrize("count", [True, 2.5, float("nan"), "2"])
    def test_counts_require_exact_integers(self, count) -> None:
        with pytest.raises((ValueError, TypeError)):
            mcnemar_exact_from_counts(n01=count, n10=3)

    def test_max_gap_requires_an_exact_integer(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            minimum_gap_for_threshold(0.05, max_gap=10.5)

    @pytest.mark.parametrize("n_resamples", [10.5, True, 0, -1])
    def test_resample_count_requires_a_positive_exact_integer(self, n_resamples) -> None:
        with pytest.raises((ValueError, TypeError)):
            paired_bootstrap_difference(pair_from([1, 0], [0, 1]), seed=1, n_resamples=n_resamples)


class TestUnequalRunSets:
    def rows(self) -> list[dict]:
        rows = []
        for index in range(4):
            for run in (0, 1):
                rows.append(
                    {
                        "item_id": f"i{index}",
                        "system": "A",
                        "run": run,
                        "instrument": "j",
                        "label": 1 if run == 0 else 0,
                    }
                )
            rows.append(
                {"item_id": f"i{index}", "system": "B", "run": 0, "instrument": "j", "label": 0}
            )
        return rows

    def test_unequal_run_sets_are_rejected_by_default(self) -> None:
        """A measured twice against B measured once is an asymmetry nobody declared."""
        table = LabelTable.from_rows(self.rows())

        with pytest.raises(SchemaError, match="run"):
            clustered_bootstrap_difference(table, "A", "B", instrument="j", seed=1)

    def test_unequal_run_sets_are_allowed_when_declared(self) -> None:
        table = LabelTable.from_rows(self.rows())

        result = clustered_bootstrap_difference(
            table, "A", "B", instrument="j", seed=1, allow_unequal_runs=True
        )

        assert result.estimate == pytest.approx(0.5)


class TestRngStreamLock:
    def test_numpy_generator_stream_is_pinned(self) -> None:
        """A true stream lock, unlike the output fixture below.

        Quantile bounds can survive a stream change, so they do not prove the stream is stable.
        This asserts the raw draws. Recorded under numpy 1.26.4; a change here means the
        resampling stream moved and every published interval must be regenerated (D0.5).
        """
        draws = np.random.default_rng(20260727).integers(0, 10, size=8).tolist()

        assert draws == [9, 1, 2, 9, 4, 8, 9, 4]
