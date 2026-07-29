#!/usr/bin/env python3
"""T3.2: execute exactly the pre-registered analysis for Experiment 1.

**Inputs are verified before they are read.** Every derived file is checked against the committed
manifest first, because `fetch.py` deliberately preserves existing outputs when a run fails
(D3.1), which means a stale table can be sitting on disk looking current. Catching that here
rather than there is the more robust layering: the consumer checks what it is about to consume.

**The headline is settled before this runs.** PREREG deviation D7 established that the
distinguishable-pair count follows from published resolve rates alone, with no per-instance data.
This script confirms it and produces the quantities that genuinely need the data: discordance
counts, paired intervals, and MDEs. A nonzero count here would not be a discovery, it would be a
defect in the engine or the derivation, so the run asserts the analytic expectation rather than
reporting whatever it finds.

Everything registered in PREREG section 5 runs, and nothing else. Exploratory work belongs in a
separately labelled appendix and never in these outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"
RESULTS = HERE / "results"
MANIFEST_PATH = HERE / "manifests" / "upstream_digests.json"

sys.path.insert(0, str(HERE.parent.parent))

from metrology.multiplicity import holm  # noqa: E402
from metrology.paired import (  # noqa: E402
    mcnemar_exact_from_counts,
    minimum_gap_for_threshold,
    p_value_floor,
    paired_bootstrap_difference,
)
from metrology.power import mde_paired_binary  # noqa: E402
from metrology.reporting import (  # noqa: E402
    PairCounts,
    Provenance,
    build_family_report,
    family_card_json,
    pair_card_json,
)
from metrology.schema import load_long_csv  # noqa: E402

# PREREG section 5. Fixed here so a reader can check them against the registration without
# reading the code that consumes them.
ALPHA = 0.05
MASTER_SEED = 20260727
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_LEVEL = 0.95
MDE_ALPHA = 0.05
TARGET_POWER = 0.80
DISCORDANCE_GRID = (0.02, 0.05, 0.10, 0.20, 0.30, 0.50)
SECONDARY_FAMILY_SIZE = 10
INSTRUMENT = "hidden-tests"

# PREREG deviation D5. SWE-bench documents an evaluation fix in April 2024, which partitions
# submissions into populations judged under different criteria.
HARNESS_FIX_BOUNDARY = "2024-04-15"


class RunFailure(RuntimeError):
    """The analysis cannot proceed honestly. Stop rather than report around it."""


def pair_seed(index: int) -> int:
    """Deterministic per-pair seed, derived from the registered master seed and the pair index.

    Registered as "per-pair bootstrap seeds derive deterministically from the master seed and the
    pair index", so the derivation is written out rather than left to a spawning scheme whose
    output depends on library internals.
    """
    return MASTER_SEED * 100 + index


def verify_inputs() -> dict:
    """Check every derived file against the committed manifest before reading any of it."""
    if not MANIFEST_PATH.exists():
        raise RunFailure(f"no committed manifest at {MANIFEST_PATH}; run fetch.py first")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    problems = []
    for name, expected in sorted(manifest.get("derived", {}).items()):
        if name == "rows":
            continue
        path = DERIVED / name
        if not path.exists():
            problems.append(f"{name}: declared in the manifest but absent; run fetch.py")
            continue
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            problems.append(f"{name}: expected {expected}, on disk {observed}")
    if problems:
        raise RunFailure(
            "derived inputs do not match the committed manifest:\n  "
            + "\n  ".join(problems)
            + "\nA failed fetch leaves earlier outputs in place, so these may be stale. "
            "Re-run fetch.py before analysing."
        )
    return manifest


def adjacent_pairs(entries: list[dict]) -> list[tuple[dict, dict]]:
    """Pairs in published order. PREREG section 2 defines adjacency by that order."""
    return [(entries[i], entries[i + 1]) for i in range(len(entries) - 1)]


def discordant_counts(table, system_a: str, system_b: str) -> tuple[int, int]:
    """`n01` and `n10` for one adjacent pair, from the derived labels."""
    pair = table.paired(system_a, system_b, instrument=INSTRUMENT)
    a = pair.label_a.astype(bool)
    b = pair.label_b.astype(bool)
    n10 = int((a & ~b).sum())
    n01 = int((~a & b).sum())
    return n01, n10


def straddle_diagnostic(entries: list[dict]) -> dict:
    """PREREG deviation D5: which adjacent pairs cross the April 2024 harness boundary."""
    pre = [e["system"] for e in entries if e["date"] < HARNESS_FIX_BOUNDARY]
    straddling = [
        {"rank_a": a["rank"], "rank_b": b["rank"]}
        for a, b in adjacent_pairs(entries)
        if (a["date"] < HARNESS_FIX_BOUNDARY) != (b["date"] < HARNESS_FIX_BOUNDARY)
    ]
    return {
        "boundary": HARNESS_FIX_BOUNDARY,
        "entries_predating_the_fix": len(pre),
        "straddling_pairs": straddling,
        "earliest_submission_date": min(e["date"] for e in entries),
    }


def no_logs_sensitivity(table, unevaluated: dict, entries: list[dict]) -> dict:
    """PREREG section 3: drop `no_logs` instances pairwise and recompute.

    Registered as a contingency and triggered by the real data, so it runs. Dropping is pairwise,
    meaning an instance is removed from a comparison when either side failed to log it.
    """
    results = []
    for a, b in adjacent_pairs(entries):
        dropped = set(unevaluated.get(a["system"], {}).get("no_logs", [])) | set(
            unevaluated.get(b["system"], {}).get("no_logs", [])
        )
        pair = table.paired(a["system"], b["system"], instrument=INSTRUMENT)
        keep = [item not in dropped for item in pair.item_id.tolist()]
        labels_a = [int(v) for v, k in zip(pair.label_a.tolist(), keep, strict=True) if k]
        labels_b = [int(v) for v, k in zip(pair.label_b.tolist(), keep, strict=True) if k]
        n10 = sum(1 for x, y in zip(labels_a, labels_b, strict=True) if x and not y)
        n01 = sum(1 for x, y in zip(labels_a, labels_b, strict=True) if y and not x)
        outcome = mcnemar_exact_from_counts(n01=n01, n10=n10)
        results.append(
            {
                "rank_a": a["rank"],
                "rank_b": b["rank"],
                "dropped_instances": len(dropped),
                "n_items": len(labels_a),
                "n01": n01,
                "n10": n10,
                "p_value": outcome.p_value,
            }
        )
    return {
        "rule": "an instance is dropped from a comparison when either side failed to log it",
        "pairs": results,
        "total_pairs_affected": sum(1 for r in results if r["dropped_instances"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    print("verifying derived inputs against the committed manifest")
    verify_inputs()
    print("  all derived inputs match")

    aggregates = json.loads((DERIVED / "aggregates.json").read_text(encoding="utf-8"))
    unevaluated = json.loads((DERIVED / "unevaluated.json").read_text(encoding="utf-8"))
    entries = aggregates["entries"]
    table = load_long_csv(DERIVED / "labels.csv")
    print(f"  loaded {table.n_rows} labels over {len(table.systems)} systems")

    provenance = Provenance(
        source="SWE-bench/experiments",
        pinned_revision=json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["board"]["commit"],
        fetch_date=str(aggregates.get("fetched", "pinned")),
        deviations=("D4 harness comparability",),
    )

    members = []
    for a, b in adjacent_pairs(entries):
        n01, n10 = discordant_counts(table, a["system"], b["system"])
        members.append(
            PairCounts(
                name=f"rank_{a['rank']}_vs_{b['rank']}",
                system_a=a["system"],
                system_b=b["system"],
                n01=n01,
                n10=n10,
                n_items=aggregates["n_items"],
            )
        )

    family = build_family_report(
        members,
        instrument=INSTRUMENT,
        alpha=ALPHA,
        provenance=provenance,
        secondary_family_size=SECONDARY_FAMILY_SIZE,
    )
    print(f"  Holm over {family.n_tests} adjacent pairs at alpha {ALPHA}")

    # The analytic expectation from D7, asserted rather than trusted.
    gaps = [abs(m.net_edge) for m in family.members]
    expected_separable = sum(1 for gap in gaps if p_value_floor(gap) <= family.first_critical)
    if family.separable_count != expected_separable:
        raise RunFailure(
            f"separable count {family.separable_count} contradicts the gap floors, which give "
            f"{expected_separable}; the engine and the derivation disagree"
        )

    pairs = []
    for index, (member, counts) in enumerate(zip(family.members, members, strict=True)):
        pair = table.paired(counts.system_a, counts.system_b, instrument=INSTRUMENT)
        interval = paired_bootstrap_difference(
            pair,
            seed=pair_seed(index),
            n_resamples=BOOTSTRAP_RESAMPLES,
            level=BOOTSTRAP_LEVEL,
        )
        pairs.append(
            {
                "name": member.name,
                "system_a": member.system_a,
                "system_b": member.system_b,
                "n01": member.n01,
                "n10": member.n10,
                "n_discordant": member.n_discordant,
                "net_edge": member.net_edge,
                "p_value": member.p_value,
                "adjusted_p_value": member.adjusted_p_value,
                "verdict": member.verdict,
                "separable": family.separable[index],
                "discordance_rate": member.discordance_rate,
                "required_net_edge_at_observed": member.required_net_edge,
                "bootstrap": {
                    "estimate": interval.estimate,
                    "low": interval.low,
                    "high": interval.high,
                    "level": interval.level,
                    "seed": interval.seed,
                    "n_resamples": interval.n_resamples,
                    "unit": interval.unit,
                },
                "mde": {
                    "status": member.mde.status,
                    "instances": member.mde.instances,
                    "rate_difference": member.mde.rate_difference,
                    "max_attainable_power": member.mde.max_attainable_power,
                },
            }
        )

    non_tied = {m.name: m.p_value for m in family.members if m.net_edge != 0}
    secondary = holm(non_tied, alpha=ALPHA) if non_tied else None

    mde_grid = []
    for rate in DISCORDANCE_GRID:
        result = mde_paired_binary(
            n=aggregates["n_items"],
            discordance_rate=rate,
            alpha=MDE_ALPHA,
            target_power=TARGET_POWER,
        )
        mde_grid.append(
            {
                "discordance_rate": rate,
                "status": result.status,
                "instances": result.instances,
                "max_attainable_power": result.max_attainable_power,
            }
        )

    results = {
        "primary": {
            "question": "how many adjacent pairs among the top N are statistically separable",
            "separable_count": family.separable_count,
            "resolved_count": family.resolved_count,
            "family_size": family.n_tests,
            "first_critical": family.first_critical,
            "first_rejection_gap_floor": family.first_rejection_gap_floor,
            "largest_observed_gap": family.largest_observed_gap,
            "separability_basis": "Holm applied to per-pair minimum attainable p-values",
            "needs_per_instance_data": False,
            "note": (
                "PREREG D7: the count follows from published resolve rates alone. The "
                "per-instance work below characterizes it and cannot overturn it."
            ),
        },
        "pairs": pairs,
        "secondary": {
            "non_tied_family": (
                {
                    "size": secondary.n_tests,
                    "first_critical": secondary.first_critical,
                    "gap_floor": minimum_gap_for_threshold(secondary.first_critical),
                    "rejected": secondary.n_rejected,
                }
                if secondary
                else None
            ),
            "harness_straddle": straddle_diagnostic(entries),
            "no_logs_sensitivity": no_logs_sensitivity(table, unevaluated, entries),
        },
        "mde_grid": {
            "alpha": MDE_ALPHA,
            "target_power": TARGET_POWER,
            "n_items": aggregates["n_items"],
            "points": mde_grid,
        },
        "configuration": {
            "alpha": ALPHA,
            "master_seed": MASTER_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_level": BOOTSTRAP_LEVEL,
            "instrument": INSTRUMENT,
        },
    }

    RESULTS.mkdir(exist_ok=True)
    payload = json.dumps(results, indent=2, sort_keys=True) + "\n"
    (RESULTS / "results.json").write_text(payload, encoding="utf-8")

    cards = {
        "family": family_card_json(family),
        "pairs": {
            member.name: pair_card_json(member)
            for member in family.members
            if member.name in {f"rank_{1}_vs_{2}", f"rank_{3}_vs_{4}"}
        },
    }
    (RESULTS / "cards.json").write_text(
        json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        f"\n  separable {family.separable_count} of {family.n_tests}, "
        f"resolved {family.resolved_count}"
    )
    print(
        f"  gateway floor {family.first_rejection_gap_floor}, "
        f"largest observed gap {family.largest_observed_gap}"
    )
    print(f"  results written to {RESULTS.name}/")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunFailure as failure:
        print(f"\nSTOPPED: {failure}", file=sys.stderr)
        raise SystemExit(1) from failure
