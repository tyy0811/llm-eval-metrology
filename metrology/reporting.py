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

**Separable is not resolved** (D1.9). Resolved means the observed Holm test rejected. Separable
means rejection was reachable at all, which for a gap `g` means `g` clears the family floor. Every
registered Experiment 1 pair fails both, so conflating them shows no symptom on that data and is
still wrong.

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

    def __post_init__(self) -> None:
        _require_text(self.source, "source")
        _require_text(self.pinned_revision, "pinned_revision")
        _require_text(self.fetch_date, "fetch_date")
        for entry in self.deviations:
            _require_text(entry, "deviation")

    def as_json(self) -> dict:
        return {
            "source": self.source,
            "pinned_revision": self.pinned_revision,
            "fetch_date": self.fetch_date,
            "deviations": list(self.deviations),
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
            rule = "p <= threshold"
        else:
            _require_probability(self.adjusted_p_value, "adjusted_p_value")
            if self.alpha is None:
                raise ValueError("an adjusted p-value requires the alpha it was judged against")
            _require_level(self.alpha, "alpha")
            expected = (
                VERDICT_RESOLVED if self.adjusted_p_value <= self.alpha else VERDICT_NOT_RESOLVED
            )
            rule = "holm-adjusted p <= alpha"

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
        if self.adjusted_p_value is not None:
            return "holm-adjusted p <= alpha"
        return "p <= threshold"


@dataclass(frozen=True)
class FamilyReport:
    """A pre-registered family, corrected and summarized."""

    instrument: str
    alpha: float
    members: tuple[PairReport, ...]
    adjusted: tuple[float, ...]
    rejected: tuple[bool, ...]
    first_critical: float
    best_case_gap_floor: int
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
        if self.best_case_gap_floor < 0:
            raise ValueError(f"gap floor must not be negative, got {self.best_case_gap_floor}")

    @property
    def n_tests(self) -> int:
        return len(self.members)

    @property
    def resolved_count(self) -> int:
        """How many comparisons the observed Holm test actually rejected."""
        return sum(self.rejected)

    @property
    def separable_count(self) -> int:
        """How many comparisons could have rejected under some feasible configuration.

        A pair's best case is every disagreement running one way, which needs its gap to clear
        the family floor. This is the resolving-power finding, and it is a weaker condition than
        having rejected, so `resolved_count <= separable_count` always holds.
        """
        return sum(1 for member in self.members if abs(member.net_edge) >= self.best_case_gap_floor)

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
    secondary_family_size: int | None = None,
    mde_alpha: float = REGISTERED_MDE_ALPHA,
) -> FamilyReport:
    """Correct a declared family and translate its threshold into a gap floor.

    Members reach `holm` as ordered `(name, p)` tuples rather than a mapping, so duplicate names
    trip its guard instead of collapsing silently. A collapsed duplicate previously produced two
    members against one rejection flag, handing one pair another pair's verdict.

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
        best_case_gap_floor=minimum_gap_for_threshold(first_critical),
        secondary_family_size=secondary_family_size,
        secondary_gap_floor=secondary_floor,
        provenance=provenance,
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
    separates = report.largest_observed_gap >= report.best_case_gap_floor
    inference = (
        f"the largest observed gap of {report.largest_observed_gap} reaches the floor of "
        f"{report.best_case_gap_floor}, so separation is reachable"
        if separates
        else (
            f"every adjacent gap sits below the floor of {report.best_case_gap_floor}, so no "
            "pair can separate at any discordance configuration"
        )
    )
    finding = {
        "claim_type": "resolving_power",
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
            "best_case_family_floor": report.best_case_gap_floor,
            "floor_label": "best-case family floor",
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
                "rejection was reachable at all, a stronger claim than a test simply not rejecting"
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


#: Required shapes, checked before a renderer is allowed to draw anything.
_PAIR_SHAPE = {
    "comparison": ("name", "system_a", "system_b", "instrument", "n_items"),
    "test": ("statistic", "convention", "p_value", "alpha", "decision_rule"),
    "ruler": (
        "observed_disagreements",
        "split",
        "observed_net_edge",
        "required_net_edge_at_observed",
        "threshold",
    ),
    "mde": ("status", "alpha", "target_power", "max_attainable_power", "discordance_rate"),
    "provenance": ("source", "pinned_revision", "fetch_date", "deviations"),
}

_FINDING_SHAPE = {
    "headline": ("separable_count", "family_size", "unit"),
    "observed": ("resolved_count", "decision_rule"),
    "criterion": ("statistic", "convention", "correction", "alpha", "threshold"),
    "limit": (
        "best_case_family_floor",
        "floor_label",
        "observed_extreme",
        "observed_extreme_label",
        "inference",
    ),
    "scope": ("comparisons", "excludes"),
    "definitions": ("separable",),
    "disclosure": ("applies_to_headline", "applies_to_secondary"),
    "progressive_disclosure": ("secondary_family_size", "secondary_family_floor"),
}


def _require_blocks(card: dict, shape: dict, label: str) -> None:
    for block, keys in shape.items():
        if block not in card:
            raise ValueError(f"{label} is missing the {block!r} block")
        for key in keys:
            if key not in card[block]:
                raise ValueError(f"{label} block {block!r} is missing {key!r}")


def validate_card(card: dict) -> bool:
    """Enforce the D1.9 schema and the required card shape. Raises rather than returning False."""
    kind = card.get("card_kind")

    if kind == CARD_PAIR:
        if "verdict" not in card:
            raise ValueError("a pair card must carry a verdict")
        if card["verdict"] not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, got {card['verdict']!r}")
        _require_blocks(card, _PAIR_SHAPE, "pair card")
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
        _require_blocks(finding, _FINDING_SHAPE, "family_finding")
        if "provenance" not in card:
            raise ValueError("a family card must carry a provenance block")
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
