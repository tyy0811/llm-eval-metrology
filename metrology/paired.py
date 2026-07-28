"""Paired comparison of two systems measured by one instrument.

The exact test convention is registered, not chosen here. Per deviation D6 of
`experiments/swebench/PREREG.md`, the two-sided exact p-value is

    p = min(1, 2 * P(X <= min(n01, n10)))    with X ~ Binomial(n01 + n10, 0.5)

that is, twice the smaller tail, capped at 1. The mid-p correction is excluded **by name**: it
yields half this value and lowers every registered significance threshold by one gap, which
would silently invalidate the floor the Experiment 1 headline rests on.

The floor that follows is the reason this module exports `p_value_floor` and
`minimum_gap_for_threshold`. For a resolved-count gap `g`, the smallest attainable p-value is
`min(1, 2^(1 - g))`, attained when every disagreement runs one way. Those helpers exist so that
no report has to hand-derive the bound, per the generator rule in `docs/DECISIONS.md` D1.8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .schema import LabelTable, PairedLabels, SchemaError

#: Name of the two-sided convention, carried on every result so a downstream card cannot
#: report a p-value without saying which definition produced it.
TWO_SIDED_CONVENTION = "doubled-tail"

#: Registered in the Experiment 1 pre-registration, section 5.
DEFAULT_RESAMPLES = 10000
DEFAULT_LEVEL = 0.95


@dataclass(frozen=True)
class McNemarResult:
    """Outcome of an exact McNemar test on the discordant pairs."""

    n01: int
    n10: int
    p_value: float
    convention: str = TWO_SIDED_CONVENTION
    system_a: str | None = None
    system_b: str | None = None
    instrument: str | None = None

    @property
    def n_discordant(self) -> int:
        return self.n01 + self.n10

    @property
    def net_edge(self) -> int:
        """`n10 - n01`, which equals the difference in resolved counts and fixes the floor."""
        return self.n10 - self.n01


@dataclass(frozen=True)
class BootstrapResult:
    """A percentile bootstrap interval for a paired difference."""

    estimate: float
    low: float
    high: float
    level: float
    seed: int
    n_resamples: int
    n_units: int
    unit: str
    system_a: str | None = None
    system_b: str | None = None
    instrument: str | None = None

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def n_clusters(self) -> int:
        """Alias for `n_units` when the resampling unit is a cluster of repeated runs."""
        return self.n_units


def _exact_nonnegative_int(value: object, name: str, *, minimum: int = 0) -> int:
    """The one strict integer validator, shared by counts, gaps, and resample counts.

    Rejects bools (a bool would read as gap 1 or count 1), fractional floats (which would
    silently truncate), and non-finite values. `nan` matters most: it previously flowed through
    `p_value_floor` to return 1.0, turning missing data into a valid-looking "not separable".
    """
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not a bool, got {value!r}")
    if isinstance(value, (int, np.integer)):
        result = int(value)
    elif isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite, got {value!r}")
        if not float(value).is_integer():
            raise ValueError(f"{name} must be an exact integer, got {value!r}")
        result = int(value)
    else:
        raise TypeError(f"{name} must be an integer, got {value!r}")
    if result < minimum:
        if minimum == 0:
            raise ValueError(f"{name} must not be negative, got {value!r}")
        raise ValueError(f"{name} must be at least {minimum}, got {value!r}")
    return result


def _require_seed(seed: object) -> int:
    """Every resampling entry point takes a seed. Ambient entropy breaks the determinism gate."""
    if seed is None:
        raise ValueError("seed is required; unseeded resampling is not reproducible")
    return _exact_nonnegative_int(seed, "seed")


def mcnemar_exact_from_counts(*, n01: int, n10: int) -> McNemarResult:
    """Exact two-sided McNemar p-value from discordant counts alone.

    Computed with exact integer arithmetic rather than a floating-point survival function, so
    that the registered identity `p == 2^(1 - g)` at `n01 = 0` holds to the last bit.
    """
    n01 = _exact_nonnegative_int(n01, "n01")
    n10 = _exact_nonnegative_int(n10, "n10")
    total = n01 + n10
    smaller = min(n01, n10)
    tail = sum(math.comb(total, i) for i in range(smaller + 1))
    p_value = min(1.0, 2 * tail / 2**total)
    return McNemarResult(n01=n01, n10=n10, p_value=p_value)


def mcnemar_exact(pair: PairedLabels) -> McNemarResult:
    """Exact two-sided McNemar test on a paired binary comparison.

    Concordant pairs carry no information about which system is better and are excluded, which
    is what makes the discordance total the quantity that governs resolving power.
    """
    _require_binary(pair.label_a, pair.system_a)
    _require_binary(pair.label_b, pair.system_b)

    a = pair.label_a.astype(bool)
    b = pair.label_b.astype(bool)
    n10 = int(np.count_nonzero(a & ~b))
    n01 = int(np.count_nonzero(~a & b))

    base = mcnemar_exact_from_counts(n01=n01, n10=n10)
    return McNemarResult(
        n01=base.n01,
        n10=base.n10,
        p_value=base.p_value,
        convention=base.convention,
        system_a=pair.system_a,
        system_b=pair.system_b,
        instrument=pair.instrument,
    )


def p_value_floor(gap: int) -> float:
    """Smallest exact two-sided p-value attainable at a resolved-count gap of `gap`.

    Attained when every disagreement runs one way, that is `n01 = 0` and `n_discordant = gap`.
    Feasible discordance totals share the parity of `gap`, and p rises as the total grows, so
    this is a floor over every configuration consistent with the gap.
    """
    gap = _exact_nonnegative_int(gap, "gap")
    return min(1.0, 2.0 ** (1 - gap))


def minimum_gap_for_threshold(threshold: float, *, max_gap: int = 4096) -> int:
    """Smallest resolved-count gap whose floor clears `threshold`.

    Answers "how far apart would two systems have to be before any test could separate them",
    which is the resolving-power question the family card reports.
    """
    if not 0 < threshold <= 1:
        raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")
    max_gap = _exact_nonnegative_int(max_gap, "max_gap", minimum=1)
    for gap in range(max_gap + 1):
        if p_value_floor(gap) <= threshold:
            return gap
    raise ValueError(f"no gap below {max_gap} clears threshold {threshold!r}")


def paired_bootstrap_difference(
    pair: PairedLabels,
    *,
    seed: int,
    n_resamples: int = DEFAULT_RESAMPLES,
    level: float = DEFAULT_LEVEL,
) -> BootstrapResult:
    """Percentile bootstrap interval for the rate difference, resampling instances.

    The resampling unit is the instance, so each replicate draws whole items and keeps both
    systems' labels for the item it drew. Resampling the two label vectors independently would
    destroy the pairing that the paired design exists to exploit.
    """
    _require_level(level)
    seed = _require_seed(seed)

    differences = pair.label_a - pair.label_b
    estimate = float(differences.mean())
    draws = _bootstrap_means(differences, seed=seed, n_resamples=n_resamples)
    low, high = _percentile_bounds(draws, level)
    return BootstrapResult(
        estimate=estimate,
        low=low,
        high=high,
        level=level,
        seed=seed,
        n_resamples=n_resamples,
        n_units=int(differences.shape[0]),
        unit="instance",
        system_a=pair.system_a,
        system_b=pair.system_b,
        instrument=pair.instrument,
    )


def clustered_bootstrap_difference(
    table: LabelTable,
    system_a: str,
    system_b: str,
    *,
    instrument: str,
    seed: int,
    n_resamples: int = DEFAULT_RESAMPLES,
    level: float = DEFAULT_LEVEL,
) -> BootstrapResult:
    """Cluster bootstrap for repeated measurement, where the cluster is the item.

    `LabelTable.paired` refuses repeated runs rather than averaging them, because collapsing
    runs discards the clustering the data carries. This is the estimator that consumes it:
    each item contributes the mean of its own runs, and resampling draws whole items so that
    the correlation between an item's repeated measurements is preserved.

    Items are weighted equally. An item measured five times does not outvote one measured once.

    **Unequal run sets are rejected.** Both systems are measured by the same `instrument` here,
    so a system with fewer runs is missing evaluations rather than sampled differently by design.
    Their per-item means would be averages over different numbers of measurements, giving the
    paired difference a noise asymmetry that equal-weight clustering does not model. There is no
    opt-out: see `docs/DECISIONS.md` D2.4 for why the earlier escape hatch was withdrawn.
    """
    _require_level(level)
    seed = _require_seed(seed)
    if system_a == system_b:
        raise SchemaError(f"cannot pair system {system_a!r} with itself")

    scoped = table.subset(instrument=instrument)
    per_item: dict[str, dict[str, list[float]]] = {}
    runs_seen: dict[str, dict[str, set[int]]] = {}
    for item, system, run, label in zip(
        scoped.item_id.tolist(),
        scoped.system.tolist(),
        scoped.run.tolist(),
        scoped.label.tolist(),
        strict=True,
    ):
        if system not in (system_a, system_b):
            continue
        per_item.setdefault(item, {}).setdefault(system, []).append(label)
        runs_seen.setdefault(item, {}).setdefault(system, set()).add(int(run))

    incomplete = sorted(
        item for item, sides in per_item.items() if system_a not in sides or system_b not in sides
    )
    if incomplete:
        raise SchemaError(
            f"broken pairing under instrument {instrument!r}: "
            f"{len(incomplete)} item(s) lack rows for both systems, first are {incomplete[:3]}"
        )
    if not per_item:
        raise SchemaError(
            f"neither {system_a!r} nor {system_b!r} was scored by instrument {instrument!r}"
        )

    mismatched = sorted(
        item for item, sides in runs_seen.items() if sides.get(system_a) != sides.get(system_b)
    )
    if mismatched:
        example = mismatched[0]
        raise SchemaError(
            f"items {mismatched[:3]} have different run sets for {system_a!r} and "
            f"{system_b!r} under instrument {instrument!r}: "
            f"{sorted(runs_seen[example].get(system_a, set()))} against "
            f"{sorted(runs_seen[example].get(system_b, set()))}. "
            "Both systems share this instrument, so the shortfall is missing evaluations"
        )

    items = sorted(per_item)
    differences = np.asarray(
        [
            float(np.mean(per_item[item][system_a]) - np.mean(per_item[item][system_b]))
            for item in items
        ],
        dtype=np.float64,
    )

    draws = _bootstrap_means(differences, seed=seed, n_resamples=n_resamples)
    low, high = _percentile_bounds(draws, level)
    return BootstrapResult(
        estimate=float(differences.mean()),
        low=low,
        high=high,
        level=level,
        seed=seed,
        n_resamples=n_resamples,
        n_units=len(items),
        unit="item cluster",
        system_a=system_a,
        system_b=system_b,
        instrument=instrument,
    )


def _bootstrap_means(values: np.ndarray, *, seed: int, n_resamples: int) -> np.ndarray:
    n_resamples = _exact_nonnegative_int(n_resamples, "n_resamples", minimum=1)
    rng = np.random.default_rng(seed)
    n = values.shape[0]
    indices = rng.integers(0, n, size=(n_resamples, n))
    return values[indices].mean(axis=1)


def _percentile_bounds(draws: np.ndarray, level: float) -> tuple[float, float]:
    alpha = (1.0 - level) / 2.0
    low, high = np.quantile(draws, [alpha, 1.0 - alpha])
    return float(low), float(high)


def _require_level(level: float) -> None:
    if not 0 < level < 1:
        raise ValueError(f"level must be in (0, 1), got {level!r}")


def _require_binary(labels: np.ndarray, system: str | None) -> None:
    if not np.all((labels == 0) | (labels == 1)):
        raise SchemaError(
            f"McNemar needs binary labels, but system {system!r} has values outside "
            "{0, 1}; use a bootstrap on the mean difference for numeric labels"
        )
