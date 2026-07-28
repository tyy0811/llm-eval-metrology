"""T2.3: prospective power and minimum detectable effect for the paired binary design.

Power is **unconditional**: it averages the registered exact McNemar rejection probability over
every possible discordance count `D ~ Binomial(n, q)`, holding the design at `n` items. It is
not conditioned on an observed discordance total, because MDE is a property of the benchmark at
its instance count rather than of one realized dataset. Each observed `n_d / n` enters instead
as a plug-in scenario for `q`.
"""

from __future__ import annotations

import math

import pytest
from scipy.stats import binom

from metrology.paired import minimum_gap_for_threshold
from metrology.power import (
    MdeResult,
    mcnemar_power,
    mde_paired_binary,
    rejection_critical_count,
)


def brute_force_power(n: int, q: float, delta: float, alpha: float) -> float:
    """Independent reference summing over the full multinomial, not over D.

    This deliberately does not reuse the D-conditioning decomposition, so it validates that
    decomposition rather than restating it.
    """
    pi10 = (q + delta) / 2.0
    pi01 = (q - delta) / 2.0
    concordant = 1.0 - q
    total = 0.0
    for n10 in range(n + 1):
        for n01 in range(n + 1 - n10):
            rest = n - n10 - n01
            weight = (
                math.factorial(n)
                / (math.factorial(n10) * math.factorial(n01) * math.factorial(rest))
                * pi10**n10
                * pi01**n01
                * concordant**rest
            )
            d = n10 + n01
            smaller = min(n10, n01)
            p_value = min(1.0, 2 * sum(math.comb(d, i) for i in range(smaller + 1)) / 2**d)
            if p_value <= alpha:
                total += weight
    return total


class TestRejectionRegion:
    def test_no_rejection_is_possible_below_the_gap_floor(self) -> None:
        """`c_d` is -1 exactly when even a fully one-sided split cannot reject."""
        floor = minimum_gap_for_threshold(0.05)

        assert rejection_critical_count(floor - 1, alpha=0.05) == -1
        assert rejection_critical_count(floor, alpha=0.05) == 0

    def test_critical_count_grows_with_discordance(self) -> None:
        counts = [rejection_critical_count(d, alpha=0.05) for d in range(0, 40)]

        assert counts == sorted(counts)

    def test_critical_count_matches_the_exact_convention(self) -> None:
        d = 20
        c = rejection_critical_count(d, alpha=0.05)

        def p_exact(k: int) -> float:
            return min(1.0, 2 * sum(math.comb(d, i) for i in range(k + 1)) / 2**d)

        assert p_exact(c) <= 0.05
        assert p_exact(c + 1) > 0.05


class TestUnconditionalPower:
    def test_size_under_the_null_does_not_exceed_alpha(self) -> None:
        """At delta = 0 the power function is the achieved size of a discrete test."""
        size = mcnemar_power(n=200, discordance_rate=0.3, rate_difference=0.0, alpha=0.05)

        assert size <= 0.05

    def test_power_rises_with_the_rate_difference(self) -> None:
        powers = [
            mcnemar_power(n=500, discordance_rate=0.3, rate_difference=d, alpha=0.05)
            for d in (0.0, 0.02, 0.05, 0.10, 0.20)
        ]

        assert powers == sorted(powers)

    def test_power_rises_with_sample_size(self) -> None:
        powers = [
            mcnemar_power(n=n, discordance_rate=0.3, rate_difference=0.05, alpha=0.05)
            for n in (100, 250, 500, 1000)
        ]

        assert powers == sorted(powers)

    def test_power_is_symmetric_in_the_sign_of_the_difference(self) -> None:
        positive = mcnemar_power(n=300, discordance_rate=0.25, rate_difference=0.06, alpha=0.05)
        negative = mcnemar_power(n=300, discordance_rate=0.25, rate_difference=-0.06, alpha=0.05)

        assert positive == pytest.approx(negative)

    def test_matches_the_brute_force_multinomial(self) -> None:
        """Small n, where enumerating the full multinomial is feasible."""
        expected = brute_force_power(n=12, q=0.5, delta=0.3, alpha=0.05)

        actual = mcnemar_power(n=12, discordance_rate=0.5, rate_difference=0.3, alpha=0.05)

        assert actual == pytest.approx(expected, abs=1e-12)

    def test_fully_one_sided_power_equals_the_gap_floor_tail(self) -> None:
        """At delta = q every disagreement runs one way, so power is P(D >= gap floor).

        This ties power.py to the floor in paired.py: the floor is the necessary condition,
        and the MDE at a target power is the sufficient one.
        """
        n, q, alpha = 500, 0.04, 0.05
        floor = minimum_gap_for_threshold(alpha)

        power = mcnemar_power(n=n, discordance_rate=q, rate_difference=q, alpha=alpha)

        assert power == pytest.approx(float(binom.sf(floor - 1, n, q)), abs=1e-12)


class TestMde:
    def test_mde_reaches_the_target_power_and_just_below_does_not(self) -> None:
        result = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80)

        assert result.attainable
        assert result.achieved_power >= 0.80
        below = mcnemar_power(
            n=500,
            discordance_rate=0.3,
            rate_difference=result.rate_difference - result.tolerance,
            alpha=0.05,
        )
        assert below < 0.80

    def test_mde_is_reported_in_instances_as_well_as_a_rate(self) -> None:
        result = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80)

        assert result.instances == pytest.approx(result.rate_difference * 500)

    def test_mde_exceeds_the_gap_floor(self) -> None:
        """The floor is what could ever reject; the MDE is what rejects 80 percent of the time."""
        alpha = 0.05
        result = mde_paired_binary(n=500, discordance_rate=0.3, alpha=alpha, target_power=0.80)

        assert result.instances > minimum_gap_for_threshold(alpha)

    def test_a_stricter_alpha_needs_a_larger_effect(self) -> None:
        loose = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80)
        strict = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05 / 19, target_power=0.80)

        assert strict.rate_difference > loose.rate_difference

    def test_higher_target_power_needs_a_larger_effect(self) -> None:
        lower = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80)
        higher = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.95)

        assert higher.rate_difference > lower.rate_difference

    def test_more_items_detect_a_smaller_effect(self) -> None:
        small = mde_paired_binary(n=200, discordance_rate=0.3, alpha=0.05, target_power=0.80)
        large = mde_paired_binary(n=1000, discordance_rate=0.3, alpha=0.05, target_power=0.80)

        assert large.rate_difference < small.rate_difference

    def test_an_unattainable_mde_is_reported_not_invented(self) -> None:
        """Sparse discordance caps power below the target at every difference.

        The cap is P(D >= gap floor), reached only when all disagreement runs one way, so a
        benchmark can be unable to reach the target at any effect size. That is a finding.
        """
        result = mde_paired_binary(n=500, discordance_rate=0.005, alpha=0.05, target_power=0.80)

        assert result.attainable is False
        assert result.rate_difference is None
        assert result.instances is None
        assert result.max_attainable_power < 0.80

    def test_the_reported_cap_equals_the_fully_one_sided_power(self) -> None:
        n, q, alpha = 500, 0.005, 0.05

        result = mde_paired_binary(n=n, discordance_rate=q, alpha=alpha, target_power=0.80)

        assert result.max_attainable_power == pytest.approx(
            mcnemar_power(n=n, discordance_rate=q, rate_difference=q, alpha=alpha)
        )

    def test_inputs_are_carried_on_the_result(self) -> None:
        result = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80)

        assert isinstance(result, MdeResult)
        assert (result.n, result.discordance_rate, result.alpha, result.target_power) == (
            500,
            0.3,
            0.05,
            0.80,
        )


class TestValidation:
    def test_rate_difference_cannot_exceed_the_discordance_rate(self) -> None:
        """|delta| <= q, since pi01 = (q - delta) / 2 must stay a probability."""
        with pytest.raises(ValueError, match="discordance"):
            mcnemar_power(n=100, discordance_rate=0.1, rate_difference=0.2, alpha=0.05)

    @pytest.mark.parametrize("q", [-0.1, 1.5, float("nan")])
    def test_invalid_discordance_rate_is_rejected(self, q: float) -> None:
        """0.0 is deliberately absent: zero discordance is valid, see TestZeroDiscordance."""
        with pytest.raises(ValueError, match="discordance"):
            mcnemar_power(n=100, discordance_rate=q, rate_difference=0.0, alpha=0.05)

    @pytest.mark.parametrize("alpha", [0.0, 1.0, -0.5, float("nan")])
    def test_invalid_alpha_is_rejected(self, alpha: float) -> None:
        with pytest.raises(ValueError, match="alpha"):
            mcnemar_power(n=100, discordance_rate=0.3, rate_difference=0.1, alpha=alpha)

    @pytest.mark.parametrize("power", [0.0, 1.0, -0.2, float("nan")])
    def test_invalid_target_power_is_rejected(self, power: float) -> None:
        with pytest.raises(ValueError, match="power"):
            mde_paired_binary(n=100, discordance_rate=0.3, alpha=0.05, target_power=power)

    @pytest.mark.parametrize("n", [0, -5, 10.5, True])
    def test_invalid_item_count_is_rejected(self, n) -> None:
        with pytest.raises((ValueError, TypeError)):
            mcnemar_power(n=n, discordance_rate=0.3, rate_difference=0.1, alpha=0.05)


class TestZeroDiscordance:
    """Zero observed discordance is a valid scenario, not invalid input.

    Nine of the nineteen registered adjacent pairs are tie-forced, and the pre-registration
    asks for an MDE at each pair's observed discordance, so `q = 0` will actually arrive.
    """

    def test_zero_discordance_gives_zero_power(self) -> None:
        assert mcnemar_power(n=500, discordance_rate=0.0, rate_difference=0.0, alpha=0.05) == 0.0

    def test_zero_discordance_admits_no_nonzero_difference(self) -> None:
        with pytest.raises(ValueError, match="discordance"):
            mcnemar_power(n=500, discordance_rate=0.0, rate_difference=0.01, alpha=0.05)

    def test_mde_at_zero_discordance_is_unattainable_with_zero_ceiling(self) -> None:
        result = mde_paired_binary(n=500, discordance_rate=0.0, alpha=0.05, target_power=0.80)

        assert result.status == "unattainable"
        assert result.max_attainable_power == 0.0
        assert result.rate_difference is None
        assert result.instances is None
        assert result.achieved_power is None


class TestReportingStatus:
    def test_attainable_result_reports_its_status(self) -> None:
        result = mde_paired_binary(n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80)

        assert result.status == "attainable"
        assert result.attainable is True

    def test_unattainable_result_reports_its_status(self) -> None:
        result = mde_paired_binary(n=500, discordance_rate=0.005, alpha=0.05, target_power=0.80)

        assert result.status == "unattainable"
        assert result.attainable is False


class TestTolerance:
    def test_tolerance_is_carried_on_the_result(self) -> None:
        result = mde_paired_binary(
            n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80, tolerance=1e-4
        )

        assert result.tolerance == 1e-4

    def test_bracket_is_within_tolerance_of_the_true_threshold(self) -> None:
        """The search returns a power-attaining upper bracket, it does not round onto a grid."""
        tolerance = 1e-4
        result = mde_paired_binary(
            n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80, tolerance=tolerance
        )

        assert result.achieved_power >= 0.80
        just_below = mcnemar_power(
            n=500,
            discordance_rate=0.3,
            rate_difference=result.rate_difference - tolerance,
            alpha=0.05,
        )
        assert just_below < 0.80

    @pytest.mark.parametrize("tolerance", [0.0, -1e-5, float("nan"), float("inf")])
    def test_invalid_tolerance_is_rejected(self, tolerance: float) -> None:
        """Zero or negative would not terminate; nan would return the maximum immediately."""
        with pytest.raises(ValueError, match="tolerance"):
            mde_paired_binary(
                n=500, discordance_rate=0.3, alpha=0.05, target_power=0.80, tolerance=tolerance
            )


class TestMdeResultInvariant:
    """D2.3: every dataclass carrying data validates in __post_init__."""

    def valid(self, **overrides):
        fields = {
            "n": 500,
            "discordance_rate": 0.3,
            "alpha": 0.05,
            "target_power": 0.8,
            "rate_difference": 0.07,
            "instances": 35.0,
            "achieved_power": 0.81,
            "max_attainable_power": 1.0,
            "tolerance": 1e-5,
        }
        fields.update(overrides)
        return MdeResult(**fields)

    def test_a_valid_result_still_builds(self) -> None:
        assert self.valid().status == "attainable"

    def test_partially_populated_attainable_fields_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="attainab"):
            self.valid(instances=None)

    def test_partially_populated_unattainable_fields_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="attainab"):
            self.valid(rate_difference=None, instances=None)

    def test_achieved_power_below_target_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="achieved_power"):
            self.valid(achieved_power=0.5)

    def test_instances_inconsistent_with_the_rate_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="instances"):
            self.valid(instances=999.0)

    def test_rate_difference_above_the_discordance_rate_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="rate_difference"):
            self.valid(rate_difference=0.9, instances=450.0)

    def test_invalid_max_attainable_power_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_attainable_power"):
            self.valid(max_attainable_power=1.5)

    def test_invalid_n_is_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            self.valid(n=0)

    def test_invalid_alpha_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="alpha"):
            self.valid(alpha=1.5)

    def test_a_fully_unattainable_result_builds(self) -> None:
        result = self.valid(
            rate_difference=None, instances=None, achieved_power=None, max_attainable_power=0.04
        )

        assert result.status == "unattainable"
