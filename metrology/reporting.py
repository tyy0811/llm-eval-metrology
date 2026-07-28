"""Results into card JSON, with every number machine-written.

This is the integration layer. It is the one module entitled to know about both a Holm critical
threshold and a McNemar gap floor: `multiplicity` stays generic so it can serve the SummEval TOST
family, `paired` owns the floor, and the translation between them happens here.

Two contracts govern the shapes below.

**D1.9.** `verdict` belongs to pair cards and takes only `RESOLVED`, `NOT RESOLVED`, or
`EQUIVALENT`. Family cards carry a structured `family_finding` instead, because `verdict` answers
a question about two systems while resolving power answers whether the instrument can answer that
question at all. `validate_card` enforces both directions, including that no verdict string leaks
into a `family_finding`, which is the constraint that actually holds since the field split is easy
to respect while the semantics reappear in prose.

**D2.5.** A pair report is built from discordant counts and never from a precomputed discordance
rate. A tied pair has `n01 = n10`, so its gap is zero while its discordance can be large;
substituting the gap for `q` would report "unattainable, maximum power zero" for comparisons with
ample disagreement. `build_pair_report` therefore takes `n01`, `n10`, and `n_items`, and derives
the rate itself. There is no parameter to pass the wrong thing to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .multiplicity import holm
from .paired import (
    TWO_SIDED_CONVENTION,
    McNemarResult,
    mcnemar_exact_from_counts,
    minimum_gap_for_threshold,
)
from .power import (
    MdeResult,
    discordance_rate_from_counts,
    mde_paired_binary,
    rejection_critical_count,
)

#: The stable verdict taxonomy. `EQUIVALENT` requires TOST at a declared band, which arrives in
#: Phase 5, so nothing emits it yet.
VERDICT_RESOLVED = "RESOLVED"
VERDICT_NOT_RESOLVED = "NOT RESOLVED"
VERDICT_EQUIVALENT = "EQUIVALENT"
VERDICTS = (VERDICT_RESOLVED, VERDICT_NOT_RESOLVED, VERDICT_EQUIVALENT)

CARD_PAIR = "pair_verdict"
CARD_FAMILY = "family_summary"


@dataclass(frozen=True)
class Provenance:
    """Where a number came from, carried onto every card.

    D4 created a standing disclosure obligation, and D7 narrowed it to the quantities that read
    per-instance data. Cards therefore state their source rather than leaving a reader to assume
    the numbers are unconditioned.
    """

    source: str
    pinned_revision: str
    fetch_date: str
    deviations: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class PairReport:
    """One adjacent-pair comparison, with its ruler and its own MDE."""

    name: str
    system_a: str
    system_b: str
    instrument: str
    n_items: int
    n01: int
    n10: int
    p_value: float
    threshold: float
    verdict: str
    adjusted_p_value: float | None
    alpha: float | None
    discordance_rate: float
    required_net_edge: int | None
    mde: MdeResult
    provenance: Provenance

    @property
    def n_discordant(self) -> int:
        return self.n01 + self.n10

    @property
    def net_edge(self) -> int:
        return self.n10 - self.n01


@dataclass(frozen=True)
class FamilyReport:
    """A whole pre-registered family, corrected and summarized."""

    instrument: str
    alpha: float
    members: tuple[PairReport, ...]
    adjusted: tuple[float, ...]
    rejected: tuple[bool, ...]
    first_critical: float
    best_case_gap_floor: int
    secondary_gap_floor: int | None
    provenance: Provenance
    _names: tuple[str, ...] = field(default=())

    @property
    def n_tests(self) -> int:
        return len(self.members)

    @property
    def separable_count(self) -> int:
        return sum(self.rejected)

    @property
    def largest_observed_gap(self) -> int:
        return max(abs(member.net_edge) for member in self.members)


def required_net_edge_at(n_discordant: int, *, threshold: float) -> int | None:
    """Net edge needed to reject **at this discordance total**, not the absolute floor.

    Rejection is `min(k, d - k) <= c_d`, so the smallest rejecting edge is `d - 2 * c_d`. D1.7
    warns that publishing the absolute floor here understates the requirement, sometimes
    threefold, because the floor is reachable only when every disagreement runs one way.

    Returns `None` when no split at this discordance rejects, meaning more disagreement, not a
    bigger edge, is what is missing.
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
    target_power: float = 0.80,
    adjusted_p_value: float | None = None,
    alpha: float | None = None,
    verdict: str | None = None,
) -> PairReport:
    """Build one pair's report from its discordant counts.

    Takes no discordance rate. See D2.5: the rate is derived here so that an aggregate gap
    cannot be substituted for it.
    """
    rate = discordance_rate_from_counts(n01=counts.n01, n10=counts.n10, n=counts.n_items)
    outcome: McNemarResult = mcnemar_exact_from_counts(n01=counts.n01, n10=counts.n10)
    mde = mde_paired_binary(
        n=counts.n_items,
        discordance_rate=rate,
        alpha=threshold,
        target_power=target_power,
    )
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
        verdict=(
            verdict
            if verdict is not None
            else (VERDICT_RESOLVED if outcome.p_value <= threshold else VERDICT_NOT_RESOLVED)
        ),
        adjusted_p_value=adjusted_p_value,
        alpha=alpha,
        discordance_rate=rate,
        required_net_edge=required_net_edge_at(outcome.n_discordant, threshold=threshold),
        mde=mde,
        provenance=provenance,
    )


def build_family_report(
    members: list[PairCounts],
    *,
    instrument: str,
    alpha: float,
    provenance: Provenance,
    secondary_family_size: int | None = None,
) -> FamilyReport:
    """Correct a declared family and translate its threshold into a gap floor.

    The family is passed explicitly, as `multiplicity.holm` requires.

    **Verdicts come from Holm's own step-down decision, not from comparing each p-value to
    `alpha / m`.** Holm loosens the bar after each rejection, so only the smallest p-value faces
    `alpha / m`. Testing every member against that value is stricter than Holm and can reject
    fewer pairs than the family card counts, which would put a `separable_count` of 2 on the
    family card while only one pair card read RESOLVED. Each member therefore carries its
    adjusted p-value and the decision rule that produced its verdict.
    """
    if not members:
        raise ValueError("family is empty; a multiplicity correction needs at least one test")

    raw = {
        item.name: mcnemar_exact_from_counts(n01=item.n01, n10=item.n10).p_value for item in members
    }
    corrected = holm(raw, alpha=alpha)

    outcomes = corrected.by_name()
    reports = tuple(
        build_pair_report(
            item,
            instrument=instrument,
            threshold=corrected.first_critical,
            provenance=provenance,
            adjusted_p_value=outcomes[item.name].adjusted,
            alpha=alpha,
            verdict=(VERDICT_RESOLVED if outcomes[item.name].rejected else VERDICT_NOT_RESOLVED),
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
        first_critical=corrected.first_critical,
        best_case_gap_floor=minimum_gap_for_threshold(corrected.first_critical),
        secondary_gap_floor=secondary_floor,
        provenance=provenance,
        _names=corrected.family,
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
            "alpha": report.alpha,
            "threshold": report.threshold,
            "decision_rule": (
                "holm-adjusted p <= alpha"
                if report.adjusted_p_value is not None
                else "p <= threshold"
            ),
        },
        "ruler": {
            "observed_disagreements": report.n_discordant,
            "split": [report.n10, report.n01],
            "observed_net_edge": report.net_edge,
            "required_net_edge_at_observed": report.required_net_edge,
            "requirement_basis": "at the observed discordance, not the best-case floor",
        },
        "mde": {
            "status": report.mde.status,
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
    finding = {
        "claim_type": "resolving_power",
        "headline": {
            "separable_count": report.separable_count,
            "family_size": report.n_tests,
            "unit": "adjacent_pairs",
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
            "inference": (
                f"every adjacent gap sits below the floor of "
                f"{report.best_case_gap_floor}, so no pair can separate at any "
                "discordance configuration"
            )
            if report.largest_observed_gap < report.best_case_gap_floor
            else (
                f"the largest observed gap of {report.largest_observed_gap} reaches the "
                f"floor of {report.best_case_gap_floor}, so separation is possible"
            ),
        },
        "scope": {
            "comparisons": "adjacent pairs only",
            "excludes": "non-adjacent comparisons are out of scope",
        },
        "definitions": {
            "separable": (
                "rejection was reachable at all, which is a stronger claim than a test "
                "simply not rejecting"
            )
        },
        "progressive_disclosure": {
            "secondary_family_floor": report.secondary_gap_floor,
        },
    }
    return {
        "card_kind": CARD_FAMILY,
        "family_finding": finding,
        "provenance": report.provenance.as_json(),
    }


def validate_card(card: dict) -> bool:
    """Enforce the D1.9 schema constraints. Raises rather than returning False."""
    kind = card.get("card_kind")
    if kind == CARD_PAIR:
        if "verdict" not in card:
            raise ValueError("a pair card must carry a verdict")
        if card["verdict"] not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, got {card['verdict']!r}")
        return True

    if kind == CARD_FAMILY:
        if "verdict" in card:
            raise ValueError(
                "a family card must not carry a verdict; resolving power is a different "
                "claim type from a two-system comparison"
            )
        finding = card.get("family_finding")
        if not finding:
            raise ValueError("a family card must carry a family_finding")
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
