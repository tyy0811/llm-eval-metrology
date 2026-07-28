"""T2.4: Holm correction over an explicitly passed family.

Holm is generic multiplicity machinery over named p-values. It knows nothing about McNemar,
discordance, or binary labels, and a test below enforces that by inspecting its imports. The
translation from a Holm threshold into a McNemar gap floor belongs to T2.5 reporting, which is
the only place that legitimately knows about both.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from metrology.multiplicity import HolmResult, holm

REPO_ROOT = Path(__file__).resolve().parent.parent


def naive_holm_rejections(p_values: list[float], alpha: float) -> list[bool]:
    """Independent step-down reference, written to disagree with the implementation if wrong."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    rejected = [False] * m
    for rank, index in enumerate(order):
        if p_values[index] <= alpha / (m - rank):
            rejected[index] = True
        else:
            break
    return rejected


class TestWorkedExample:
    """Hand-computed. m = 3, alpha = 0.05, p = [0.01, 0.04, 0.03] in family order.

    Sorted: 0.01, 0.03, 0.04 against criticals 0.05/3, 0.05/2, 0.05/1.
    Step 1: 0.01 <= 0.016667, reject. Step 2: 0.03 > 0.025, stop.
    Adjusted, sorted: 3*0.01 = 0.03; max(0.03, 2*0.03) = 0.06; max(0.06, 1*0.04) = 0.06.
    """

    def family(self) -> dict[str, float]:
        return {"pair_1_2": 0.01, "pair_2_3": 0.04, "pair_3_4": 0.03}

    def test_rejections_follow_the_step_down(self) -> None:
        result = holm(self.family(), alpha=0.05)

        assert result.rejected == (True, False, False)

    def test_adjusted_p_values_match_the_hand_computation(self) -> None:
        result = holm(self.family(), alpha=0.05)

        assert result.adjusted == pytest.approx((0.03, 0.06, 0.06))

    def test_results_come_back_in_original_family_order(self) -> None:
        """Internal sorting must not leak into the output ordering."""
        result = holm(self.family(), alpha=0.05)

        assert result.family == ("pair_1_2", "pair_2_3", "pair_3_4")
        assert result.p_values == pytest.approx((0.01, 0.04, 0.03))

    def test_identifiers_stay_attached_to_their_own_results(self) -> None:
        result = holm(self.family(), alpha=0.05)

        assert result.by_name()["pair_2_3"].p_value == pytest.approx(0.04)
        assert result.by_name()["pair_2_3"].adjusted == pytest.approx(0.06)
        assert result.by_name()["pair_2_3"].rejected is False


class TestCriticalThresholds:
    def test_ordered_criticals_are_alpha_over_remaining_tests(self) -> None:
        result = holm({"a": 0.001, "b": 0.5, "c": 0.02, "d": 0.9}, alpha=0.05)

        assert result.critical_thresholds == pytest.approx((0.05 / 4, 0.05 / 3, 0.05 / 2, 0.05))

    def test_first_critical_is_alpha_over_family_size(self) -> None:
        """This is the value T2.5 hands to the gap-floor translation."""
        result = holm({f"t{i}": 0.5 for i in range(19)}, alpha=0.05)

        assert result.first_critical == pytest.approx(0.05 / 19)
        assert result.n_tests == 19

    def test_first_critical_for_the_registered_families(self) -> None:
        primary = holm({f"t{i}": 0.5 for i in range(19)}, alpha=0.05)
        secondary = holm({f"t{i}": 0.5 for i in range(10)}, alpha=0.05)

        assert primary.first_critical == pytest.approx(0.002631578947368421)
        assert secondary.first_critical == pytest.approx(0.005)


class TestProcedureProperties:
    def test_all_reject_when_every_p_is_tiny(self) -> None:
        result = holm({"a": 1e-9, "b": 1e-9, "c": 1e-9}, alpha=0.05)

        assert result.rejected == (True, True, True)

    def test_none_reject_when_every_p_is_large(self) -> None:
        result = holm({"a": 0.9, "b": 0.8, "c": 0.7}, alpha=0.05)

        assert result.rejected == (False, False, False)

    def test_a_single_test_is_uncorrected(self) -> None:
        assert holm({"only": 0.04}, alpha=0.05).adjusted == pytest.approx((0.04,))
        assert holm({"only": 0.04}, alpha=0.05).rejected == (True,)
        assert holm({"only": 0.06}, alpha=0.05).rejected == (False,)

    def test_adjusted_values_are_capped_at_one(self) -> None:
        result = holm({"a": 0.6, "b": 0.7, "c": 0.8}, alpha=0.05)

        assert max(result.adjusted) <= 1.0

    def test_adjusted_values_are_monotone_in_sorted_order(self) -> None:
        result = holm({"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.9}, alpha=0.05)
        by_p = sorted(zip(result.p_values, result.adjusted, strict=True))

        assert [adj for _, adj in by_p] == sorted(adj for _, adj in by_p)

    def test_rejection_agrees_with_adjusted_against_alpha(self) -> None:
        result = holm({"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.9}, alpha=0.05)

        assert result.rejected == tuple(adj <= 0.05 for adj in result.adjusted)

    @pytest.mark.parametrize(
        "p_values",
        [
            [0.01, 0.04, 0.03],
            [0.001, 0.002, 0.003, 0.004],
            [0.5, 0.5, 0.5],
            [0.0, 1.0, 0.5],
            [0.049, 0.0001, 0.02, 0.9, 0.3, 0.007],
        ],
    )
    def test_matches_an_independent_step_down_reference(self, p_values: list[float]) -> None:
        family = {f"t{i}": p for i, p in enumerate(p_values)}

        result = holm(family, alpha=0.05)

        assert list(result.rejected) == naive_holm_rejections(p_values, 0.05)

    def test_ties_keep_original_family_order(self) -> None:
        result = holm({"first": 0.02, "second": 0.02, "third": 0.02}, alpha=0.05)

        assert result.family == ("first", "second", "third")

    def test_a_p_value_of_one_never_rejects(self) -> None:
        result = holm({"a": 1.0, "b": 1.0}, alpha=0.05)

        assert result.rejected == (False, False)
        assert result.adjusted == pytest.approx((1.0, 1.0))

    def test_accepts_a_sequence_of_pairs(self) -> None:
        result = holm([("a", 0.01), ("b", 0.04)], alpha=0.05)

        assert result.family == ("a", "b")


class TestValidation:
    def test_empty_family_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            holm({}, alpha=0.05)

    def test_duplicate_identifiers_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            holm([("a", 0.01), ("a", 0.02)], alpha=0.05)

    @pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan"), float("inf")])
    def test_p_values_outside_the_unit_interval_are_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="p-value"):
            holm({"a": 0.01, "b": bad}, alpha=0.05)

    @pytest.mark.parametrize("alpha", [0.0, 1.0, -0.5, 2.0, float("nan")])
    def test_invalid_alpha_is_rejected(self, alpha: float) -> None:
        with pytest.raises(ValueError, match="alpha"):
            holm({"a": 0.01}, alpha=alpha)

    def test_error_names_the_offending_member(self) -> None:
        with pytest.raises(ValueError, match="b"):
            holm({"a": 0.01, "b": 2.0}, alpha=0.05)


class TestModuleBoundary:
    def test_holm_does_not_import_the_paired_module(self) -> None:
        """Role boundary: Holm is generic and must stay reusable.

        Importing `paired` would couple a generic correction to binary paired comparisons and
        block reuse by the SummEval TOST family and the AggreFact rate comparisons, neither of
        which has a discordance count. The translation from a Holm threshold to a McNemar gap
        floor belongs to T2.5 reporting, which may know about both.
        """
        source = (REPO_ROOT / "metrology" / "multiplicity.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imported.update(alias.name for alias in node.names)

        assert not any("paired" in name for name in imported), imported

    def test_result_is_serializable_without_numpy_scalars(self) -> None:
        """T2.5 writes card JSON, so plain floats and bools keep serialization deterministic."""
        result = holm({"a": 0.01, "b": 0.04}, alpha=0.05)

        assert isinstance(result, HolmResult)
        assert all(type(value) is float for value in result.adjusted)
        assert all(type(flag) is bool for flag in result.rejected)
