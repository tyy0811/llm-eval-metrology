"""Results into card JSON, with every number machine-written.

This is the integration layer, and the one module entitled to know about both a Holm critical
threshold and a McNemar gap floor: `multiplicity` stays generic so it can serve the SummEval TOST
family, `paired` owns the floor, and the translation between them happens here.

**Three thresholds, kept apart.** They answer different questions and are numerically different,
so a card that mixes them tells a false story.

- `alpha`, the family-wise level. The verdict is `holm-adjusted p <= alpha`.
- `ruler_threshold`, the family's first critical value `alpha / m`. The ruler and the family gap
  floor both use it, so "required edge 21" and "floor 10" describe the same bar.
- `mde.alpha`, the **uncorrected** level registered in PREREG section 5 for the MDE, which is
  0.05 regardless of family size.

At 43 disagreements the required net edge is 15 at 0.05, 21 at 0.005, and 21 at 0.05/19, while the
floor is 6, 9, and 10. Quoting an edge from one and a floor from another is a category error.

**Separable is not resolved** (D1.9, refined by D2.7). Resolved means the observed Holm test
rejected. Separable means the family's Holm procedure could reject the pair under jointly
best-case overlaps, computed by running Holm over the vector of per-pair minimum attainable
p-values. It is deliberately not "the gap clears the family gateway floor": under gaps of 40 and
6 the second pair sits below the floor yet is separable, because it can follow the first through
the gateway. Every registered Experiment 1 pair fails both tests, so conflating them shows no
symptom on that data and is still wrong.

**D2.5.** A pair report is built from discordant counts, never from a precomputed discordance
rate. A tied pair has `n01 = n10`, so its gap is zero while its discordance can be large.
`build_pair_report` takes `n01`, `n10`, `n_items` and derives the rate itself, so there is no
parameter to pass the wrong thing to.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .multiplicity import holm
from .paired import (
    TWO_SIDED_CONVENTION,
    mcnemar_exact_from_counts,
    minimum_gap_for_threshold,
    p_value_floor,
)
from .power import (
    MdeResult,
    discordance_rate_from_counts,
    mde_paired_binary,
    rejection_critical_count,
)

#: The stable verdict taxonomy. `EQUIVALENT` needs TOST at a declared band, which arrives in
#: Phase 5, so nothing emits it yet.
VERDICT_RESOLVED = "RESOLVED"
VERDICT_NOT_RESOLVED = "NOT RESOLVED"
VERDICT_EQUIVALENT = "EQUIVALENT"
VERDICTS = (VERDICT_RESOLVED, VERDICT_NOT_RESOLVED, VERDICT_EQUIVALENT)

CARD_PAIR = "pair_verdict"
CARD_FAMILY = "family_summary"

#: The only two decision rules a pair card may display. An unrecognized string previously fell
#: through to the raw-p branch, so the verdict was checked against a rule the card did not show.
RULE_RAW = "p <= threshold"
RULE_HOLM = "holm-adjusted p <= alpha"
DECISION_RULES = (RULE_RAW, RULE_HOLM)

#: PREREG section 5 registers the MDE at alpha 0.05 two-sided, power 0.80. Deliberately not the
#: multiplicity-corrected threshold: the MDE describes the benchmark, not one family within it.
REGISTERED_MDE_ALPHA = 0.05
REGISTERED_TARGET_POWER = 0.80


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string, got {value!r}")
    return value


def _require_probability(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")
    return float(value)


def _require_level(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or not 0.0 < value <= 1.0:
        raise ValueError(f"{name} must be in (0, 1], got {value!r}")
    return float(value)


@dataclass(frozen=True)
class Provenance:
    """Where a number came from, carried onto every card.

    D4 created a standing disclosure obligation and D7 narrowed it to the quantities that read
    per-instance data, so a card states its source rather than leaving a reader to assume the
    numbers are unconditioned.
    """

    source: str
    pinned_revision: str
    fetch_date: str
    deviations: tuple[str, ...] = ()
    secondary_source: str | None = None
    secondary_revision: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source, "source")
        _require_text(self.pinned_revision, "pinned_revision")
        _require_text(self.fetch_date, "fetch_date")
        for entry in self.deviations:
            _require_text(entry, "deviation")
        secondary = (self.secondary_source, self.secondary_revision)
        if any(x is not None for x in secondary) and not all(x is not None for x in secondary):
            raise ValueError(
                "secondary_source and secondary_revision are present together or absent together"
            )
        for name in ("secondary_source", "secondary_revision"):
            value = getattr(self, name)
            if value is not None:
                _require_text(value, name)

    def as_json(self) -> dict:
        return {
            "source": self.source,
            "pinned_revision": self.pinned_revision,
            "fetch_date": self.fetch_date,
            "deviations": list(self.deviations),
            "secondary_source": self.secondary_source,
            "secondary_revision": self.secondary_revision,
        }


@dataclass(frozen=True)
class PairCounts:
    """The only input shape for a pair report: discordant counts, never a rate."""

    name: str
    system_a: str
    system_b: str
    n01: int
    n10: int
    n_items: int

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.system_a, "system_a")
        _require_text(self.system_b, "system_b")
        if self.system_a == self.system_b:
            raise ValueError(f"cannot compare system {self.system_a!r} with itself")
        # discordance_rate_from_counts owns the exact-integer and n01 + n10 <= n checks.
        discordance_rate_from_counts(n01=self.n01, n10=self.n10, n=self.n_items)

    @property
    def net_edge(self) -> int:
        return self.n10 - self.n01


@dataclass(frozen=True)
class PairReport:
    """One comparison, its ruler, and its own MDE."""

    name: str
    system_a: str
    system_b: str
    instrument: str
    n_items: int
    n01: int
    n10: int
    p_value: float
    threshold: float
    ruler_threshold: float
    verdict: str
    adjusted_p_value: float | None
    alpha: float | None
    discordance_rate: float
    required_net_edge: int | None
    mde: MdeResult
    provenance: Provenance

    def __post_init__(self) -> None:
        """D2.3. The verdict must agree with the rule that produced it."""
        _require_text(self.name, "name")
        _require_text(self.instrument, "instrument")
        _require_probability(self.p_value, "p_value")
        _require_level(self.threshold, "threshold")
        _require_level(self.ruler_threshold, "ruler_threshold")
        _require_probability(self.discordance_rate, "discordance_rate")

        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, got {self.verdict!r}")

        if self.adjusted_p_value is None:
            expected = VERDICT_RESOLVED if self.p_value <= self.threshold else VERDICT_NOT_RESOLVED
            rule = RULE_RAW
        else:
            _require_probability(self.adjusted_p_value, "adjusted_p_value")
            if self.alpha is None:
                raise ValueError("an adjusted p-value requires the alpha it was judged against")
            _require_level(self.alpha, "alpha")
            expected = (
                VERDICT_RESOLVED if self.adjusted_p_value <= self.alpha else VERDICT_NOT_RESOLVED
            )
            rule = RULE_HOLM

        if self.verdict != expected:
            raise ValueError(
                f"verdict {self.verdict!r} contradicts the decision rule {rule!r}, "
                f"which gives {expected!r}"
            )

    @property
    def n_discordant(self) -> int:
        return self.n01 + self.n10

    @property
    def net_edge(self) -> int:
        return self.n10 - self.n01

    @property
    def decision_rule(self) -> str:
        return RULE_HOLM if self.adjusted_p_value is not None else RULE_RAW


@dataclass(frozen=True)
class FamilyReport:
    """A pre-registered family, corrected and summarized."""

    instrument: str
    alpha: float
    members: tuple[PairReport, ...]
    adjusted: tuple[float, ...]
    rejected: tuple[bool, ...]
    first_critical: float
    first_rejection_gap_floor: int
    separable: tuple[bool, ...]
    secondary_family_size: int | None
    secondary_gap_floor: int | None
    provenance: Provenance

    def __post_init__(self) -> None:
        _require_text(self.instrument, "instrument")
        _require_level(self.alpha, "alpha")
        if not self.members:
            raise ValueError("a family report needs at least one member")
        names = [member.name for member in self.members]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"family has duplicate member names: {duplicates[:3]}")
        if not len(self.members) == len(self.adjusted) == len(self.rejected):
            raise ValueError(
                f"members, adjusted, and rejected must align: "
                f"{len(self.members)}, {len(self.adjusted)}, {len(self.rejected)}"
            )
        if len(self.separable) != len(self.members):
            raise ValueError(
                f"separability flags must align with members: "
                f"{len(self.separable)} against {len(self.members)}"
            )
        if self.first_rejection_gap_floor < 0:
            raise ValueError(
                f"gap floor must not be negative, got {self.first_rejection_gap_floor}"
            )
        if self.resolved_count > self.separable_count:
            raise ValueError(
                f"resolved_count {self.resolved_count} exceeds separable_count "
                f"{self.separable_count}; a comparison cannot reject unless rejection was "
                "reachable, so this indicates the two were computed inconsistently"
            )

    @property
    def n_tests(self) -> int:
        return len(self.members)

    @property
    def resolved_count(self) -> int:
        """How many comparisons the observed Holm test actually rejected."""
        return sum(self.rejected)

    @property
    def separable_count(self) -> int:
        """How many comparisons could reject under jointly best-case overlaps.

        Computed by running the family's own Holm procedure over the vector of per-pair minimum
        attainable p-values, `p_value_floor(|gap|)`. That respects the gateway: a pair below the
        first-rejection floor cannot open the family, but it can follow one that does, so it is
        still separable.

        Comparing each gap against the gateway floor instead would understate this and could
        report fewer separable than resolved, contradicting the definitions. Using observed
        overlaps would make a resolving-power claim depend on the results it is meant to bound.

        Observed p is at least the floor for every pair and Holm is monotone in the p vector, so
        `resolved_count <= separable_count` holds by construction.
        """
        return sum(self.separable)

    @property
    def largest_observed_gap(self) -> int:
        return max(abs(member.net_edge) for member in self.members)


def required_net_edge_at(n_discordant: int, *, threshold: float) -> int | None:
    """Net edge needed to reject **at this discordance total**, not the absolute floor.

    Rejection is `min(k, d - k) <= c_d`, so the smallest rejecting edge is `d - 2 * c_d`. D1.7
    warns that publishing the absolute floor here understates the requirement, because the floor
    is reachable only when every disagreement runs one way.

    Returns `None` when no split at this discordance rejects: what is missing is more
    disagreement, not a bigger edge.
    """
    critical = rejection_critical_count(n_discordant, alpha=threshold)
    if critical < 0:
        return None
    return n_discordant - 2 * critical


def build_pair_report(
    counts: PairCounts,
    *,
    instrument: str,
    threshold: float,
    provenance: Provenance,
    ruler_threshold: float | None = None,
    mde_alpha: float = REGISTERED_MDE_ALPHA,
    target_power: float = REGISTERED_TARGET_POWER,
    adjusted_p_value: float | None = None,
    alpha: float | None = None,
    verdict: str | None = None,
) -> PairReport:
    """Build one pair's report from its discordant counts.

    Takes no discordance rate, per D2.5. `mde_alpha` defaults to the registered uncorrected
    level rather than inheriting `threshold`, because the MDE describes the benchmark and not
    the family it happens to sit in.
    """
    rate = discordance_rate_from_counts(n01=counts.n01, n10=counts.n10, n=counts.n_items)
    outcome = mcnemar_exact_from_counts(n01=counts.n01, n10=counts.n10)
    ruler = threshold if ruler_threshold is None else ruler_threshold

    return PairReport(
        name=counts.name,
        system_a=counts.system_a,
        system_b=counts.system_b,
        instrument=instrument,
        n_items=counts.n_items,
        n01=counts.n01,
        n10=counts.n10,
        p_value=outcome.p_value,
        threshold=threshold,
        ruler_threshold=ruler,
        verdict=(
            verdict
            if verdict is not None
            else (VERDICT_RESOLVED if outcome.p_value <= threshold else VERDICT_NOT_RESOLVED)
        ),
        adjusted_p_value=adjusted_p_value,
        alpha=alpha,
        discordance_rate=rate,
        required_net_edge=required_net_edge_at(outcome.n_discordant, threshold=ruler),
        mde=mde_paired_binary(
            n=counts.n_items,
            discordance_rate=rate,
            alpha=mde_alpha,
            target_power=target_power,
        ),
        provenance=provenance,
    )


def build_family_report(
    members: list[PairCounts],
    *,
    instrument: str,
    alpha: float,
    provenance: Provenance,
    family_provenance: Provenance | None = None,
    secondary_family_size: int | None = None,
    mde_alpha: float = REGISTERED_MDE_ALPHA,
) -> FamilyReport:
    """Correct a declared family and translate its threshold into a gap floor.

    Members reach `holm` as ordered `(name, p)` tuples rather than a mapping, so duplicate names
    trip its guard instead of collapsing silently. A collapsed duplicate previously produced two
    members against one rejection flag, handing one pair another pair's verdict.

    `family_provenance` exists because a family card and its pair cards can legitimately have
    different sources. Under D1.11 the resolving-power headline derives from the published board
    alone, while the pair cards' discordance counts come from the per-instance artifacts. One
    provenance for both would name the wrong source on whichever card it did not describe.

    Verdicts come from Holm's own step-down decision. Holm loosens the bar after each rejection,
    so only the smallest p-value faces `alpha / m`; testing every member against that value is
    stricter than Holm and would let the family card count more separations than the pair cards
    showed.
    """
    if not members:
        raise ValueError("family is empty; a multiplicity correction needs at least one test")

    raw = [
        (item.name, mcnemar_exact_from_counts(n01=item.n01, n10=item.n10).p_value)
        for item in members
    ]
    corrected = holm(raw, alpha=alpha)
    outcomes = corrected.by_name()

    first_critical = corrected.first_critical
    reports = tuple(
        build_pair_report(
            item,
            instrument=instrument,
            threshold=first_critical,
            ruler_threshold=first_critical,
            mde_alpha=mde_alpha,
            provenance=provenance,
            adjusted_p_value=outcomes[item.name].adjusted,
            alpha=alpha,
            verdict=VERDICT_RESOLVED if outcomes[item.name].rejected else VERDICT_NOT_RESOLVED,
        )
        for item in members
    )

    best_case = holm(
        [(item.name, p_value_floor(abs(item.net_edge))) for item in members], alpha=alpha
    )
    best_case_by_name = best_case.by_name()

    secondary_floor = None
    if secondary_family_size:
        secondary_floor = minimum_gap_for_threshold(alpha / secondary_family_size)

    return FamilyReport(
        instrument=instrument,
        alpha=alpha,
        members=reports,
        adjusted=corrected.adjusted,
        rejected=corrected.rejected,
        first_critical=first_critical,
        first_rejection_gap_floor=minimum_gap_for_threshold(first_critical),
        separable=tuple(best_case_by_name[item.name].rejected for item in members),
        secondary_family_size=secondary_family_size,
        secondary_gap_floor=secondary_floor,
        provenance=family_provenance or provenance,
    )


def pair_card_json(report: PairReport) -> dict:
    """Card JSON for one pair. Carries a `verdict`, per D1.9."""
    return {
        "card_kind": CARD_PAIR,
        "verdict": report.verdict,
        "comparison": {
            "name": report.name,
            "system_a": report.system_a,
            "system_b": report.system_b,
            "instrument": report.instrument,
            "n_items": report.n_items,
        },
        "test": {
            "statistic": "exact_mcnemar_two_sided",
            "convention": TWO_SIDED_CONVENTION,
            "p_value": report.p_value,
            "adjusted_p_value": report.adjusted_p_value,
            "alpha": report.alpha if report.alpha is not None else report.threshold,
            "decision_rule": report.decision_rule,
        },
        "ruler": {
            "observed_disagreements": report.n_discordant,
            "split": [report.n10, report.n01],
            "observed_net_edge": report.net_edge,
            "required_net_edge_at_observed": report.required_net_edge,
            "threshold": report.ruler_threshold,
            "threshold_basis": "the family's first critical value, the same bar as the gap floor",
            "requirement_basis": "at the observed discordance, not the best-case floor",
        },
        "mde": {
            "status": report.mde.status,
            "alpha": report.mde.alpha,
            "alpha_basis": "registered uncorrected level, not the family correction",
            "target_power": report.mde.target_power,
            "max_attainable_power": report.mde.max_attainable_power,
            "rate_difference": report.mde.rate_difference,
            "instances": report.mde.instances,
            "discordance_rate": report.discordance_rate,
        },
        "provenance": report.provenance.as_json(),
    }


def family_card_json(report: FamilyReport) -> dict:
    """Card JSON for a family. Carries a `family_finding` and **no** `verdict`, per D1.9."""
    inference = (
        f"{report.separable_count} of {report.n_tests} pairs could reject under best-case "
        f"overlaps; the family gateway floor is {report.first_rejection_gap_floor} and the "
        f"largest observed gap is {report.largest_observed_gap}"
        if report.separable_count
        else (
            f"every adjacent gap sits below the gateway floor of "
            f"{report.first_rejection_gap_floor}, so no pair can open the family and none can "
            "separate at any discordance configuration"
        )
    )
    finding = {
        "claim_type": "resolving_power",
        "separability_basis": "Holm applied to per-pair minimum attainable p-values",
        "headline": {
            "separable_count": report.separable_count,
            "family_size": report.n_tests,
            "unit": "adjacent_pairs",
        },
        "observed": {
            "resolved_count": report.resolved_count,
            "decision_rule": "holm-adjusted p <= alpha",
            "note": (
                "separable asks whether rejection was reachable at all; resolved asks whether "
                "the observed test rejected, which is the stronger requirement"
            ),
        },
        "criterion": {
            "statistic": "exact_mcnemar_two_sided",
            "convention": TWO_SIDED_CONVENTION,
            "correction": "holm",
            "alpha": report.alpha,
            "threshold": report.first_critical,
        },
        "limit": {
            "first_rejection_gap_floor": report.first_rejection_gap_floor,
            "floor_label": "family gateway floor, cleared by the first rejection",
            "observed_extreme": report.largest_observed_gap,
            "observed_extreme_label": "largest observed adjacent gap",
            "inference": inference,
        },
        "scope": {
            "comparisons": "adjacent pairs only",
            "excludes": "non-adjacent comparisons are out of scope",
        },
        "definitions": {
            "separable": (
                "the family's Holm procedure could reject this pair under best-case overlaps; "
                "not separable is a stronger result than an observed test merely not rejecting"
            )
        },
        "conditionality": [
            "integrity gate 3 passes, so derived counts match published rates",
            "the coverage rule substitutes no entry",
        ],
        "disclosure": {
            "applies_to_headline": [],
            "applies_to_secondary": list(report.provenance.deviations),
        },
        "progressive_disclosure": {
            "secondary_family_size": report.secondary_family_size,
            "secondary_family_floor": report.secondary_gap_floor,
        },
    }
    return {
        "card_kind": CARD_FAMILY,
        "family_finding": finding,
        "provenance": report.provenance.as_json(),
    }


#: Required shape for a pair card: block, key, and the check the value must pass. Presence alone
#: is not enough. A card that validates must be safe to render, which means every field the
#: renderer interpolates is type-checked here rather than trusted. The split reached an unescaped
#: style attribute, so a string there produced executable markup.
_INT = "int"
_NUM = "number"
_PROB = "probability"
_LEVEL = "level"
_TEXT = "text"
_LIST = "list"

# --- The format registry (T3.3 spec section 3) -------------------------------------
#
# Every numeric path in the two-file corpus (D3.2) has exactly one declared rendering.
# The generator and the prose checker both call render_number, so the set of strings
# the checker accepts equals the set the generator can emit. There is no tolerance
# parameter anywhere: generic rounding made 0.024 and 0.95 collide with the bare
# integers 0 and 1, which appear throughout authored prose.
#
# Format keys: "int" exact integer; "pct1"/"inst1" one fixed decimal; "rate3"/"p3"/
# "pow3" three fixed decimals; "sig6" six significant digits with trailing zeros
# trimmed (safe only because no committed threshold is 0 or 1; a test bounds this).

_FORMATTERS = {
    "int": lambda value: str(int(value)),
    "pct1": lambda value: f"{value:.1f}",
    "inst1": lambda value: f"{value:.1f}",
    "rate3": lambda value: f"{value:.3f}",
    "p3": lambda value: f"{value:.3f}",
    "pow3": lambda value: f"{value:.3f}",
    "sig6": lambda value: f"{value:.6g}",
}

NUMBER_FORMATS: dict[str, str] = {
    "aggregates:entries[].no_generation": "int",
    "aggregates:entries[].no_logs": "int",
    "aggregates:entries[].published_rate": "pct1",
    "aggregates:entries[].rank": "int",
    "aggregates:entries[].resolved": "int",
    "aggregates:family_size": "int",
    "aggregates:n_items": "int",
    "results:configuration.alpha": "sig6",
    "results:configuration.bootstrap_level": "sig6",
    "results:configuration.bootstrap_resamples": "int",
    "results:configuration.master_seed": "int",
    "results:mde_grid.alpha": "sig6",
    "results:mde_grid.n_items": "int",
    "results:mde_grid.points[].discordance_rate": "rate3",
    "results:mde_grid.points[].instances": "inst1",
    "results:mde_grid.points[].max_attainable_power": "pow3",
    "results:mde_grid.target_power": "sig6",
    "results:pairs[].adjusted_p_value": "p3",
    "results:pairs[].bootstrap.estimate": "rate3",
    "results:pairs[].bootstrap.high": "rate3",
    "results:pairs[].bootstrap.level": "sig6",
    "results:pairs[].bootstrap.low": "rate3",
    "results:pairs[].bootstrap.n_resamples": "int",
    "results:pairs[].bootstrap.seed": "int",
    "results:pairs[].discordance_rate": "rate3",
    "results:pairs[].mde.instances": "inst1",
    "results:pairs[].mde.max_attainable_power": "pow3",
    "results:pairs[].mde.rate_difference": "rate3",
    "results:pairs[].n01": "int",
    "results:pairs[].n10": "int",
    "results:pairs[].n_discordant": "int",
    "results:pairs[].net_edge": "int",
    "results:pairs[].p_value": "p3",
    "results:pairs[].required_net_edge_at_observed": "int",
    "results:primary.family_size": "int",
    "results:primary.first_critical": "sig6",
    "results:primary.first_rejection_gap_floor": "int",
    "results:primary.headline.distinguishable_count": "int",
    "results:primary.headline.real_test_not_distinguishable_count": "int",
    "results:primary.headline.tie_forced_not_distinguishable_count": "int",
    "results:primary.largest_observed_gap": "int",
    "results:primary.resolved_count": "int",
    "results:primary.separable_count": "int",
    "results:secondary.harness_straddle.entries_predating_the_fix": "int",
    "results:secondary.no_logs_sensitivity.family.alpha": "sig6",
    "results:secondary.no_logs_sensitivity.family.first_critical": "sig6",
    "results:secondary.no_logs_sensitivity.family.resolved_count": "int",
    "results:secondary.no_logs_sensitivity.family.separable_count": "int",
    "results:secondary.no_logs_sensitivity.family.size": "int",
    "results:secondary.no_logs_sensitivity.pairs[].adjusted_p_value": "p3",
    "results:secondary.no_logs_sensitivity.pairs[].dropped_instances": "int",
    "results:secondary.no_logs_sensitivity.pairs[].n01": "int",
    "results:secondary.no_logs_sensitivity.pairs[].n10": "int",
    "results:secondary.no_logs_sensitivity.pairs[].n_items": "int",
    "results:secondary.no_logs_sensitivity.pairs[].p_value": "p3",
    "results:secondary.no_logs_sensitivity.pairs[].rank_a": "int",
    "results:secondary.no_logs_sensitivity.pairs[].rank_b": "int",
    "results:secondary.no_logs_sensitivity.total_pairs_affected": "int",
    "results:secondary.non_tied_family.first_critical": "sig6",
    "results:secondary.non_tied_family.gap_floor": "int",
    "results:secondary.non_tied_family.rejected": "int",
    "results:secondary.non_tied_family.size": "int",
}


def iter_numeric_leaves(source, document, prefix=""):
    """Yield (qualified_path, value) for every numeric leaf. Booleans and None are
    not numbers; list indices collapse to []. Pure, so it lives here and the prose
    checker and the tests share one walker instead of drifting copies."""
    if isinstance(document, dict):
        for key, value in document.items():
            inner = f"{prefix}.{key}" if prefix else key
            yield from iter_numeric_leaves(source, value, inner)
    elif isinstance(document, list):
        for value in document:
            yield from iter_numeric_leaves(source, value, prefix + "[]")
    elif isinstance(document, bool) or document is None:
        return
    elif isinstance(document, (int, float)):
        yield f"{source}:{prefix}", document


def render_number(qualified_path: str, value) -> str:
    """The one approved string for a corpus figure at a source-qualified path."""
    try:
        format_key = NUMBER_FORMATS[qualified_path]
    except KeyError:
        raise ValueError(
            f"no registered renderer for {qualified_path!r}; extend NUMBER_FORMATS "
            "deliberately rather than defaulting (T3.3 spec section 3)"
        ) from None
    return _FORMATTERS[format_key](value)


_PAIR_SHAPE: dict[str, tuple[tuple[str, str], ...]] = {
    "comparison": (
        ("name", _TEXT),
        ("system_a", _TEXT),
        ("system_b", _TEXT),
        ("instrument", _TEXT),
        ("n_items", _INT),
    ),
    "test": (
        ("statistic", _TEXT),
        ("convention", _TEXT),
        ("p_value", _PROB),
        ("adjusted_p_value", "probability?"),
        ("alpha", _LEVEL),
        ("decision_rule", _TEXT),
    ),
    "ruler": (
        ("observed_disagreements", _INT),
        ("split", "split"),
        ("observed_net_edge", "signed_int"),
        ("required_net_edge_at_observed", "int?"),
        ("threshold", _LEVEL),
        ("threshold_basis", _TEXT),
        ("requirement_basis", _TEXT),
    ),
    "mde": (
        ("status", "mde_status"),
        ("alpha", _LEVEL),
        ("alpha_basis", _TEXT),
        ("target_power", _LEVEL),
        ("max_attainable_power", _PROB),
        ("rate_difference", "number?"),
        ("instances", "number?"),
        ("discordance_rate", _PROB),
    ),
    "provenance": (
        ("source", _TEXT),
        ("pinned_revision", _TEXT),
        ("fetch_date", _TEXT),
        ("deviations", _LIST),
        # Optional, but the renderer reads them, so they must be present and well-typed.
        # Omitting one raised a KeyError at render time and a null one drew "source None".
        ("secondary_source", "text?"),
        ("secondary_revision", "text?"),
    ),
}

_FINDING_SHAPE: dict[str, tuple[tuple[str, str], ...]] = {
    "headline": (("separable_count", _INT), ("family_size", _INT), ("unit", _TEXT)),
    "observed": (("resolved_count", _INT), ("decision_rule", _TEXT), ("note", _TEXT)),
    "criterion": (
        ("statistic", _TEXT),
        ("convention", _TEXT),
        ("correction", _TEXT),
        ("alpha", _LEVEL),
        ("threshold", _LEVEL),
    ),
    "limit": (
        ("first_rejection_gap_floor", _INT),
        ("floor_label", _TEXT),
        ("observed_extreme", _INT),
        ("observed_extreme_label", _TEXT),
        ("inference", _TEXT),
    ),
    "scope": (("comparisons", _TEXT), ("excludes", _TEXT)),
    "definitions": (("separable", _TEXT),),
    "disclosure": (("applies_to_headline", _LIST), ("applies_to_secondary", _LIST)),
    "progressive_disclosure": (
        ("secondary_family_size", "int?"),
        ("secondary_family_floor", "int?"),
    ),
}

_MDE_STATUSES = ("attainable", "unattainable")


def _check_value(value: object, kind: str, where: str, card: dict | None = None) -> None:
    optional = kind.endswith("?")
    base = kind[:-1] if optional else kind
    if value is None:
        if optional:
            return
        raise ValueError(f"{where} must not be null")

    if base in (_INT, "signed_int"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{where} must be an integer, got {value!r}")
        if base == _INT and value < 0:
            raise ValueError(f"{where} must not be negative, got {value!r}")
    elif base in (_NUM, _PROB, _LEVEL):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{where} must be a number, got {value!r}")
        if not math.isfinite(value):
            raise ValueError(f"{where} must be finite, got {value!r}")
        if base == _PROB and not 0.0 <= value <= 1.0:
            raise ValueError(f"{where} must be in [0, 1], got {value!r}")
        if base == _LEVEL and not 0.0 < value <= 1.0:
            raise ValueError(f"{where} must be in (0, 1], got {value!r}")
    elif base == _TEXT:
        if not isinstance(value, str):
            raise ValueError(f"{where} must be a string, got {value!r}")
    elif base == _LIST:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"{where} must be a list of strings, got {value!r}")
    elif base == "mde_status":
        if value not in _MDE_STATUSES:
            raise ValueError(f"{where} must be one of {_MDE_STATUSES}, got {value!r}")
    elif base == "split":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"{where} must be a pair of counts, got {value!r}")
        for part in value:
            if isinstance(part, bool) or not isinstance(part, int) or part < 0:
                raise ValueError(f"{where} must contain nonnegative integers, got {value!r}")
        if card is not None and sum(value) != card["ruler"]["observed_disagreements"]:
            raise ValueError(
                f"{where} must sum to observed_disagreements "
                f"{card['ruler']['observed_disagreements']}, got {value!r}"
            )
    else:  # pragma: no cover - guards the table itself
        raise ValueError(f"unknown check {kind!r} for {where}")


def _require_blocks(card: dict, shape: dict, label: str, root: dict | None = None) -> None:
    for block, keys in shape.items():
        if block not in card:
            raise ValueError(f"{label} is missing the {block!r} block")
        if not isinstance(card[block], dict):
            raise ValueError(f"{label} block {block!r} must be an object")
        for key, kind in keys:
            if key not in card[block]:
                raise ValueError(f"{label} block {block!r} is missing {key!r}")
            _check_value(card[block][key], kind, f"{label}.{block}.{key}", root)


def _check_provenance(provenance: dict, label: str) -> None:
    """A mixed-source card names both sources or neither, never half of one."""
    pair = (provenance.get("secondary_source"), provenance.get("secondary_revision"))
    if any(value is not None for value in pair) and not all(value is not None for value in pair):
        raise ValueError(
            f"{label}: secondary_source and secondary_revision are present together or absent "
            f"together, got {pair!r}; the renderer would draw a partial attribution"
        )


def _check_pair_invariants(card: dict) -> None:
    """Relationships between fields, which per-field type checks cannot see.

    Each value below is individually well-typed. What makes a card wrong is the relationship:
    43 disagreements among 20 items, a net edge that contradicts its own split, a verdict that
    contradicts its own decision rule. A card that passes validation must be renderable **and**
    internally consistent, or the renderer faithfully draws a false result.
    """
    comparison, test, ruler, mde = card["comparison"], card["test"], card["ruler"], card["mde"]
    total = ruler["observed_disagreements"]
    favour_a, favour_b = ruler["split"]
    n_items = comparison["n_items"]

    if n_items < 1:
        raise ValueError(f"comparison.n_items must be at least 1, got {n_items}")
    if total > n_items:
        raise ValueError(
            f"ruler.observed_disagreements {total} cannot exceed comparison.n_items {n_items}"
        )
    if ruler["observed_net_edge"] != favour_a - favour_b:
        raise ValueError(
            f"ruler.observed_net_edge {ruler['observed_net_edge']} must equal the split "
            f"difference {favour_a} minus {favour_b}, which is {favour_a - favour_b}"
        )

    expected_required = required_net_edge_at(total, threshold=ruler["threshold"])
    if ruler["required_net_edge_at_observed"] != expected_required:
        raise ValueError(
            f"ruler.required_net_edge_at_observed {ruler['required_net_edge_at_observed']!r} "
            f"does not match the requirement at {total} disagreements and threshold "
            f"{ruler['threshold']!r}, which is {expected_required!r}"
        )

    expected_rate = total / n_items
    if not math.isclose(mde["discordance_rate"], expected_rate, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError(
            f"mde.discordance_rate {mde['discordance_rate']!r} must equal "
            f"{total} over {n_items}, which is {expected_rate!r}"
        )

    populated = [mde["rate_difference"] is not None, mde["instances"] is not None]
    if mde["status"] == "attainable" and not all(populated):
        raise ValueError(
            "mde.status is 'attainable' but rate_difference or instances is null; an attainable "
            "result must carry both"
        )
    if mde["status"] == "unattainable" and any(populated):
        raise ValueError(
            "mde.status is 'unattainable' but rate_difference or instances is present; an "
            "unattainable result must carry neither"
        )

    if card["verdict"] == VERDICT_EQUIVALENT:
        raise ValueError(
            "cannot render an EQUIVALENT verdict: it requires TOST at a declared band, which "
            "arrives in Phase 5. Rendering it now would show the NOT RESOLVED reading, which "
            "states something false about the comparison."
        )

    rule = test["decision_rule"]
    if rule not in DECISION_RULES:
        raise ValueError(
            f"test.decision_rule must be one of {DECISION_RULES}, got {rule!r}; an unrecognized "
            "rule would be displayed while the verdict was checked against a different one"
        )
    if rule == RULE_HOLM:
        if test["adjusted_p_value"] is None:
            raise ValueError(
                "the decision rule names an adjusted p-value but adjusted_p_value is null"
            )
        holds = test["adjusted_p_value"] <= test["alpha"]
    else:
        if test["adjusted_p_value"] is not None:
            raise ValueError(
                f"decision rule {RULE_RAW!r} carries an adjusted p-value; a corrected card must "
                f"display {RULE_HOLM!r} instead"
            )
        holds = test["p_value"] <= test["alpha"]
    expected_verdict = VERDICT_RESOLVED if holds else VERDICT_NOT_RESOLVED
    if card["verdict"] != expected_verdict:
        raise ValueError(
            f"verdict {card['verdict']!r} contradicts the displayed decision rule "
            f"{test['decision_rule']!r}, which gives {expected_verdict!r}"
        )


def _check_family_invariants(finding: dict) -> None:
    headline, observed = finding["headline"], finding["observed"]
    separable, resolved = headline["separable_count"], observed["resolved_count"]
    size = headline["family_size"]

    if not resolved <= separable <= size:
        raise ValueError(
            f"family counts must satisfy resolved <= separable <= family_size, got "
            f"{resolved} <= {separable} <= {size}"
        )

    disclosure = finding["progressive_disclosure"]
    present = [
        disclosure["secondary_family_size"] is not None,
        disclosure["secondary_family_floor"] is not None,
    ]
    if any(present) and not all(present):
        raise ValueError(
            "secondary_family_size and secondary_family_floor must be present together or "
            "absent together, otherwise the card renders a null"
        )


def validate_card(card: dict) -> bool:
    """Enforce the D1.9 schema and the full renderable shape. Raises rather than returning False.

    A card that passes here must be safe to render. Presence checks alone were not enough: a
    missing field surfaced as a KeyError inside the renderer, and a string where a count belonged
    reached an unescaped style attribute and produced executable markup. Escaping stays as defense
    in depth, but the value should never arrive.
    """
    kind = card.get("card_kind")

    if kind == CARD_PAIR:
        if "verdict" not in card:
            raise ValueError("a pair card must carry a verdict")
        if card["verdict"] not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, got {card['verdict']!r}")
        _require_blocks(card, _PAIR_SHAPE, "pair card", root=card)
        _check_provenance(card["provenance"], "pair card")
        _check_pair_invariants(card)
        return True

    if kind == CARD_FAMILY:
        if "verdict" in card:
            raise ValueError(
                "a family card must not carry a verdict; resolving power is a different claim "
                "type from a two-system comparison"
            )
        finding = card.get("family_finding")
        if not finding:
            raise ValueError("a family card must carry a family_finding")
        if finding.get("claim_type") != "resolving_power":
            raise ValueError("family_finding must declare its claim_type")
        if "conditionality" not in finding:
            raise ValueError("family_finding is missing the 'conditionality' block")
        _check_value(finding["conditionality"], _LIST, "family_finding.conditionality")
        _check_value(finding.get("separability_basis"), _TEXT, "family_finding.separability_basis")
        _require_blocks(finding, _FINDING_SHAPE, "family_finding")
        if "provenance" not in card:
            raise ValueError("a family card must carry a provenance block")
        _require_blocks(card, {"provenance": _PAIR_SHAPE["provenance"]}, "family card")
        _check_provenance(card["provenance"], "family card")
        _check_family_invariants(finding)
        _reject_verdict_strings(finding)
        return True

    raise ValueError(f"unknown card_kind {kind!r}")


def _reject_verdict_strings(node: object, path: str = "family_finding") -> None:
    """No verdict string may appear anywhere inside a family finding.

    The field-level split is easy to respect while the semantics quietly reappear in a rendered
    sentence, so this walks values rather than checking key names.
    """
    if isinstance(node, str):
        for verdict in VERDICTS:
            if verdict in node:
                raise ValueError(
                    f"verdict string {verdict!r} leaked into {path}; a family finding states "
                    "resolving power, not the outcome of one hypothesis"
                )
    elif isinstance(node, dict):
        for key, value in node.items():
            _reject_verdict_strings(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _reject_verdict_strings(value, f"{path}[{index}]")
