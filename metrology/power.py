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

#: Bisection tolerance for the MDE search, in units of rate difference. The search returns a
#: power-attaining **upper bracket** within this distance of the true threshold. It does not
#: round onto a grid, which is why this is a tolerance and not a resolution. One item out of
#: 500 is 0.002, so the default sits well below a single instance.
MDE_TOLERANCE = 1e-5

#: Reporting states. `unattainable` is a domain finding, not an error: power is capped at
#: P(D >= gap floor), so a sparse benchmark can miss the target at every effect size.
STATUS_ATTAINABLE = "attainable"
STATUS_UNATTAINABLE = "unattainable"


@dataclass(frozen=True)
class MdeResult:
    """Smallest rate difference reaching a target power, or a statement that none does.

    Unattainability is reported through `status` rather than raised. An exception should mean
    invalid input or a failed computation, whereas "this benchmark cannot reach 80 percent power
    at any effect size" is a result worth putting on a card.
    """

    n: int
    discordance_rate: float
    alpha: float
    target_power: float
    rate_difference: float | None
    instances: float | None
    achieved_power: float | None
    max_attainable_power: float
    tolerance: float

    def __post_init__(self) -> None:
        """D2.3: the invariant is enforced here, whatever built the instance."""
        _exact_positive_int(self.n, "n", minimum=1)
        _require_discordance_rate(self.discordance_rate)
        _require_unit_interval(self.alpha, "alpha")
        _require_unit_interval(self.target_power, "target_power")
        _require_positive_tolerance(self.tolerance)

        if not 0.0 <= self.max_attainable_power <= 1.0 or not math.isfinite(
            self.max_attainable_power
        ):
            raise ValueError(
                f"max_attainable_power must be in [0, 1], got {self.max_attainable_power!r}"
            )

        populated = [
            field is not None
            for field in (self.rate_difference, self.instances, self.achieved_power)
        ]
        if any(populated) and not all(populated):
            raise ValueError(
                "attainable results carry rate_difference, instances, and achieved_power "
                "together; unattainable results carry none of them"
            )

        if self.rate_difference is None:
            return

        if not math.isfinite(self.rate_difference) or not (
            0.0 <= self.rate_difference <= self.discordance_rate + 1e-12
        ):
            raise ValueError(
                f"rate_difference must be in [0, discordance_rate], got {self.rate_difference!r}"
            )
        if not math.isclose(self.instances, self.rate_difference * self.n, rel_tol=1e-9):
            raise ValueError(
                f"instances must equal rate_difference * n, got {self.instances!r} against "
                f"{self.rate_difference * self.n!r}"
            )
        if self.achieved_power < self.target_power:
            raise ValueError(
                f"achieved_power {self.achieved_power!r} is below the target "
                f"{self.target_power!r}, so this is not an attainable result"
            )

    @property
    def status(self) -> str:
        """`attainable` or `unattainable`, the reporting state consumed by T2.5."""
        return STATUS_ATTAINABLE if self.rate_difference is not None else STATUS_UNATTAINABLE

    @property
    def attainable(self) -> bool:
        return self.status == STATUS_ATTAINABLE


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


def discordance_rate_from_counts(*, n01: int, n10: int, n: int) -> float:
    """Discordance rate `q = (n01 + n10) / n`, the plug-in scenario for a real comparison.

    Exists so that no caller derives `q` from a published rate difference. A tied pair has
    `n01 = n10`, so its **gap** is zero while its **discordance** can be large: 20 against 20
    out of 500 items is a gap of 0 and a `q` of 0.08. Deriving `q` from the gap would hand 0 to
    the MDE for every tied comparison and report it as unattainable with zero power, when in
    fact there is ample disagreement to measure.

    Only total agreement, `n01 = n10 = 0`, gives `q = 0`.
    """
    n01 = _exact_positive_int(n01, "n01", minimum=0)
    n10 = _exact_positive_int(n10, "n10", minimum=0)
    n = _exact_positive_int(n, "n", minimum=1)
    if n01 + n10 > n:
        raise ValueError(f"discordant pairs ({n01} + {n10}) cannot exceed the item count ({n})")
    return (n01 + n10) / n


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
    if q == 0.0:
        # No discordant pairs can arise, so no split exists to reject on. Power is exactly
        # zero rather than undefined, and psi below would divide by zero.
        return 0.0

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

    # Clamped because this is a probability. Summing ~n float terms can overshoot 1 by an ulp,
    # and an out-of-range "probability" would then fail the MdeResult invariant downstream.
    return float(min(1.0, max(0.0, np.dot(d_probs, contribution))))


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
    tolerance: float = MDE_TOLERANCE,
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
    _require_positive_tolerance(tolerance)

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
            tolerance=tolerance,
        )

    # Power is monotone in |delta| at fixed q, so bisect for the threshold. `high` is kept as
    # an upper bracket that attains the target, so the reported effect is never optimistic.
    low, high = 0.0, q
    while high - low > tolerance:
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
        tolerance=tolerance,
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


def _require_positive_tolerance(value: float) -> None:
    """Zero or negative would not terminate the bisection; nan would exit it immediately."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"tolerance must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"tolerance must be finite and positive, got {value!r}")


def _require_unit_interval(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError(f"{name} must be in (0, 1), got {value!r}")


def _require_discordance_rate(value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"discordance_rate must be a number, got {value!r}")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"discordance_rate must be in [0, 1], got {value!r}")
