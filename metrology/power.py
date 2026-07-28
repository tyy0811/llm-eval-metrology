"""Prospective power and minimum detectable effect for the paired binary design.

**Power here is unconditional.** For `n` paired items with discordance rate `q` and rate
difference `delta`, the discordance count is itself random, `D ~ Binomial(n, q)`. Power averages
the exact McNemar rejection probability over every possible `D`:

    power = sum_d  P(D = d) * P(reject | D = d)

It is deliberately **not** conditioned on an observed discordance total. MDE is a property of
the benchmark at its instance count, so conditioning on one realized dataset would produce a
different number per comparison and stop describing the design. An observed `n_d / n` enters
instead as a plug-in scenario for `q`.

This also keeps the MDE distinct from the verdict card's ruler (`docs/DECISIONS.md` D1.7), which
asks what split would reject **at the observed discordance**. That question is conditional by
construction, and if MDE were conditional too the two would collapse into one number.

The exact test convention is the one registered in PREREG deviation D6, reached through the
rejection region rather than by recomputing p-values: `p(k, d)` depends only on `min(k, d - k)`
and rises with it, so each `d` has a single critical count `c_d` and rejection is
`min(k, d - k) <= c_d`. That makes the power sum O(n) rather than O(n^2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache

import numpy as np
from scipy.stats import binom

#: Registered in the Experiment 1 pre-registration, section 5.
DEFAULT_TARGET_POWER = 0.80

#: Grid step for the MDE search, in units of rate difference. One item out of 500 is 0.002, so
#: this resolves well below a single instance and the reported effect is not grid-limited.
MDE_RESOLUTION = 1e-5


@dataclass(frozen=True)
class MdeResult:
    """Smallest rate difference reaching a target power, or a statement that none does."""

    n: int
    discordance_rate: float
    alpha: float
    target_power: float
    rate_difference: float | None
    instances: float | None
    achieved_power: float | None
    max_attainable_power: float
    resolution: float

    @property
    def attainable(self) -> bool:
        return self.rate_difference is not None


@cache
def rejection_critical_count(d: int, *, alpha: float) -> int:
    """Largest `k` whose exact two-sided p-value at `d` discordant pairs clears `alpha`.

    Returns -1 when no split rejects, which happens exactly when `d` is below the gap floor.
    Computed in exact integer arithmetic to match `paired.mcnemar_exact_from_counts` bit for
    bit, rather than through a floating-point survival function.
    """
    d = _exact_positive_int(d, "d", minimum=0)
    _require_unit_interval(alpha, "alpha")

    critical = -1
    total = 2**d
    term = 1  # C(d, 0)
    tail = 1
    for k in range(d // 2 + 1):
        if k:
            # C(d, k) from C(d, k - 1), exact integer, avoiding a fresh math.comb per step.
            term = term * (d - k + 1) // k
            tail += term
        if min(1.0, 2 * tail / total) <= alpha:
            critical = k
        else:
            break
    return critical


def mcnemar_power(
    *, n: int, discordance_rate: float, rate_difference: float, alpha: float
) -> float:
    """Unconditional exact power at `n` items, averaging over the random discordance count."""
    n = _exact_positive_int(n, "n", minimum=1)
    _require_discordance_rate(discordance_rate)
    _require_unit_interval(alpha, "alpha")

    if not math.isfinite(rate_difference):
        raise ValueError(f"rate_difference must be finite, got {rate_difference!r}")
    if abs(rate_difference) > discordance_rate + 1e-15:
        raise ValueError(
            f"|rate_difference| must not exceed the discordance rate, got "
            f"{rate_difference!r} against {discordance_rate!r}"
        )

    q = float(discordance_rate)
    # Conditional on a pair being discordant, it favours system A with probability psi.
    psi = (q + rate_difference) / (2.0 * q)
    psi = min(1.0, max(0.0, psi))

    d_values = np.arange(n + 1)
    d_probs = binom.pmf(d_values, n, q)
    criticals = _critical_counts(n, alpha)

    # Vectorized over d. Scalar scipy calls per d dominated the runtime, and the rejection
    # region depends only on the critical count, which does not depend on psi.
    can_reject = criticals >= 0
    saturated = can_reject & (2 * criticals >= d_values)
    partial = can_reject & ~saturated

    contribution = np.zeros(n + 1, dtype=float)
    contribution[saturated] = 1.0
    if partial.any():
        d_partial = d_values[partial]
        c_partial = criticals[partial]
        lower = binom.cdf(c_partial, d_partial, psi)
        upper = binom.sf(d_partial - c_partial - 1, d_partial, psi)
        contribution[partial] = lower + upper

    return float(np.dot(d_probs, contribution))


@cache
def _critical_counts(n: int, alpha: float) -> np.ndarray:
    """Critical counts for every discordance total up to `n`, computed once per (n, alpha)."""
    counts = np.fromiter(
        (rejection_critical_count(d, alpha=alpha) for d in range(n + 1)),
        dtype=np.int64,
        count=n + 1,
    )
    counts.setflags(write=False)
    return counts


def mde_paired_binary(
    *,
    n: int,
    discordance_rate: float,
    alpha: float,
    target_power: float = DEFAULT_TARGET_POWER,
    resolution: float = MDE_RESOLUTION,
) -> MdeResult:
    """Smallest absolute rate difference whose unconditional power reaches `target_power`.

    Returns a non-attainable result rather than raising when no difference suffices. That is a
    real finding for a sparse benchmark: power is capped at `P(D >= gap floor)`, reached only
    when every disagreement runs one way, so a benchmark can be unable to reach the target at
    any effect size at all.
    """
    n = _exact_positive_int(n, "n", minimum=1)
    _require_discordance_rate(discordance_rate)
    _require_unit_interval(alpha, "alpha")
    _require_unit_interval(target_power, "target_power")

    q = float(discordance_rate)
    ceiling = mcnemar_power(n=n, discordance_rate=q, rate_difference=q, alpha=alpha)
    if ceiling < target_power:
        return MdeResult(
            n=n,
            discordance_rate=q,
            alpha=alpha,
            target_power=target_power,
            rate_difference=None,
            instances=None,
            achieved_power=None,
            max_attainable_power=ceiling,
            resolution=resolution,
        )

    # Power is monotone in |delta| at fixed q, so bisect on the smallest delta that reaches
    # the target, then round up to the grid so the reported effect is never optimistic.
    low, high = 0.0, q
    while high - low > resolution:
        middle = (low + high) / 2.0
        if (
            mcnemar_power(n=n, discordance_rate=q, rate_difference=middle, alpha=alpha)
            >= target_power
        ):
            high = middle
        else:
            low = middle

    achieved = mcnemar_power(n=n, discordance_rate=q, rate_difference=high, alpha=alpha)
    return MdeResult(
        n=n,
        discordance_rate=q,
        alpha=alpha,
        target_power=target_power,
        rate_difference=high,
        instances=high * n,
        achieved_power=achieved,
        max_attainable_power=ceiling,
        resolution=resolution,
    )


def _exact_positive_int(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not a bool, got {value!r}")
    if isinstance(value, int):
        result = int(value)
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{name} must be an exact integer, got {value!r}")
        result = int(value)
    else:
        raise TypeError(f"{name} must be an integer, got {value!r}")
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value!r}")
    return result


def _require_unit_interval(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError(f"{name} must be in (0, 1), got {value!r}")


def _require_discordance_rate(value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"discordance_rate must be a number, got {value!r}")
    if not math.isfinite(value) or not 0 < value <= 1:
        raise ValueError(f"discordance_rate must be in (0, 1], got {value!r}")
