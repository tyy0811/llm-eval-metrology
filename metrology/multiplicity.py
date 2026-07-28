"""Multiplicity corrections over an explicitly passed family of tests.

Deliberately generic. This module operates on named p-values and knows nothing about McNemar,
discordance, binary labels, or resolving power. That keeps it reusable by the SummEval TOST
family and the AggreFact rate comparisons, neither of which has a discordance count.

The translation from a Holm critical threshold into a McNemar gap floor belongs to `reporting`,
which is the one place entitled to know about both. A test asserts this module does not import
`paired`.

**The family is always passed explicitly.** There is no discovery of "all tests run so far",
because a multiplicity correction is only meaningful against a family someone declared, and an
implicitly assembled family is how a correction quietly stops matching what was pre-registered.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

Family = Mapping[str, float] | Sequence[tuple[str, float]]


@dataclass(frozen=True)
class TestOutcome:
    """One member of a corrected family."""

    name: str
    p_value: float
    adjusted: float
    rejected: bool


@dataclass(frozen=True)
class HolmResult:
    """Outcome of the Holm step-down correction, in original family order.

    Every tuple is aligned with `family`, which preserves the order the caller supplied. The
    internal sort by p-value is an implementation detail and never leaks into the output, so a
    report can zip these against its own list of comparisons without re-deriving an order.
    """

    family: tuple[str, ...]
    p_values: tuple[float, ...]
    adjusted: tuple[float, ...]
    rejected: tuple[bool, ...]
    critical_thresholds: tuple[float, ...]
    alpha: float

    @property
    def n_tests(self) -> int:
        return len(self.family)

    @property
    def first_critical(self) -> float:
        """`alpha / m`, the threshold the smallest p-value must clear.

        This is the value a report hands to a resolving-power translation, for instance to ask
        what effect size could clear it at all. Exposed so that no report hand-derives it.
        """
        return self.critical_thresholds[0]

    @property
    def n_rejected(self) -> int:
        return sum(self.rejected)

    def by_name(self) -> dict[str, TestOutcome]:
        """Results keyed by family identifier, for callers that would otherwise index by hand."""
        return {
            name: TestOutcome(name=name, p_value=p, adjusted=adj, rejected=rej)
            for name, p, adj, rej in zip(
                self.family, self.p_values, self.adjusted, self.rejected, strict=True
            )
        }


def holm(family: Family, *, alpha: float) -> HolmResult:
    """Holm step-down correction, controlling the family-wise error rate at `alpha`.

    Adjusted p-values are the standard step-down form, `max` over the running prefix of
    `(m - j + 1) * p_(j)`, capped at 1, which makes them monotone in sorted order and lets
    rejection be read off as `adjusted <= alpha`.
    """
    names, p_values = _normalize(family)
    _validate(names, p_values, alpha)

    m = len(names)
    # Stable sort, so tied p-values keep the order the caller declared.
    order = sorted(range(m), key=lambda index: p_values[index])
    criticals = tuple(alpha / (m - rank) for rank in range(m))

    adjusted_sorted: list[float] = []
    running = 0.0
    for rank, index in enumerate(order):
        scaled = (m - rank) * p_values[index]
        running = max(running, scaled)
        adjusted_sorted.append(min(1.0, running))

    adjusted = [0.0] * m
    for rank, index in enumerate(order):
        adjusted[index] = float(adjusted_sorted[rank])

    return HolmResult(
        family=tuple(names),
        p_values=tuple(float(p) for p in p_values),
        adjusted=tuple(adjusted),
        rejected=tuple(bool(value <= alpha) for value in adjusted),
        critical_thresholds=criticals,
        alpha=float(alpha),
    )


def _normalize(family: Family) -> tuple[list[str], list[float]]:
    if isinstance(family, Mapping):
        pairs = list(family.items())
    else:
        pairs = [tuple(entry) for entry in family]  # type: ignore[misc]
    names = [str(name) for name, _ in pairs]
    p_values = [float(value) for _, value in pairs]
    return names, p_values


def _validate(names: Sequence[str], p_values: Sequence[float], alpha: float) -> None:
    if not names:
        raise ValueError("family is empty; a multiplicity correction needs at least one test")

    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"family has duplicate identifiers: {duplicates[:3]}")

    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")

    for name, value in zip(names, p_values, strict=True):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"p-value for {name!r} must be in [0, 1], got {value!r}")
