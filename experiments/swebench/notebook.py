# %% [markdown]
# # Experiment 1: the complete registered report
#
# This notebook reads the committed results and renders every output PREREG
# registered. It computes nothing: every figure below flows from
# `results/results.json` or `derived/aggregates.json` through the format
# registry, and the tests prove it with planted sentinels. Prose cells carry
# no figures; the code cells print them.

# %%
import json
import pathlib

from metrology.reporting import render_number

HERE = pathlib.Path(__file__).resolve().parent


# %%
def load(results_path, aggregates_path):
    results = json.loads(pathlib.Path(results_path).read_text(encoding="utf-8"))
    aggregates = json.loads(pathlib.Path(aggregates_path).read_text(encoding="utf-8"))
    return results, aggregates


# %% [markdown]
# ## The three-part headline (PREREG section 2)
#
# Distinguishable means the observed Holm-adjusted p fell below the family
# alpha. Tie-forced pairs have p equal to 1 by arithmetic; the rest admitted a
# real test.


# %%
def print_headline(results):
    headline = results["primary"]["headline"]
    for key, label in (
        ("distinguishable_count", "distinguishable"),
        ("real_test_not_distinguishable_count", "not distinguishable under a real test"),
        ("tie_forced_not_distinguishable_count", "not distinguishable by tie arithmetic"),
    ):
        rendered = render_number(f"results:primary.headline.{key}", headline[key])
        print(f"{label}: {rendered}")
    floor = render_number(
        "results:primary.first_rejection_gap_floor",
        results["primary"]["first_rejection_gap_floor"],
    )
    largest = render_number(
        "results:primary.largest_observed_gap", results["primary"]["largest_observed_gap"]
    )
    print(f"family gateway floor {floor}, largest observed gap {largest}")


# %% [markdown]
# ## Per-pair detail (PREREG 5, tests 1 and 2)
#
# The discordant counts, the paired bootstrap interval, and the MDE at the
# observed discordance, per adjacent pair. These read per-instance artifacts
# and carry the D4 harness comparability caveat.


# %%
def print_pairs(results):
    print("caveat: D4 harness comparability applies to every column below")
    for pair in results["pairs"]:
        n01 = render_number("results:pairs[].n01", pair["n01"])
        n10 = render_number("results:pairs[].n10", pair["n10"])
        p = render_number("results:pairs[].p_value", pair["p_value"])
        low = render_number("results:pairs[].bootstrap.low", pair["bootstrap"]["low"])
        high = render_number("results:pairs[].bootstrap.high", pair["bootstrap"]["high"])
        level = render_number("results:pairs[].bootstrap.level", pair["bootstrap"]["level"])
        mde = render_number("results:pairs[].mde.instances", pair["mde"]["instances"])
        print(
            f"pair {pair['name']}: n01 {n01}, n10 {n10}, p {p}, "
            f"interval [{low}, {high}] at {level}, mde {mde} instances "
            f"({pair['mde']['status']})"
        )


# %% [markdown]
# ## The declared MDE grid (PREREG 5, test 4)


# %%
def print_grid(results):
    for point in results["mde_grid"]["points"]:
        rate = render_number(
            "results:mde_grid.points[].discordance_rate", point["discordance_rate"]
        )
        instances = render_number("results:mde_grid.points[].instances", point["instances"])
        print(f"grid discordance {rate}: mde {instances} instances ({point['status']})")


# %% [markdown]
# ## Data quality (PREREG 3)
#
# Per-system counts of instances with no generated patch and no evaluation
# logs, reported alongside the results as registered.


# %%
def print_data_quality(aggregates):
    for entry in sorted(aggregates["entries"], key=lambda item: item["rank"]):
        no_generation = render_number("aggregates:entries[].no_generation", entry["no_generation"])
        no_logs = render_number("aggregates:entries[].no_logs", entry["no_logs"])
        print(f"system {entry['system']}: no_generation {no_generation}, no_logs {no_logs}")


# %% [markdown]
# ## Registered secondaries


# %%
def print_secondaries(results):
    non_tied = results["secondary"]["non_tied_family"]
    size = render_number("results:secondary.non_tied_family.size", non_tied["size"])
    rejected = render_number("results:secondary.non_tied_family.rejected", non_tied["rejected"])
    gap_floor = render_number("results:secondary.non_tied_family.gap_floor", non_tied["gap_floor"])
    print(f"non-tied family: {size} pairs, gap floor {gap_floor}, rejected {rejected}")

    sensitivity = results["secondary"]["no_logs_sensitivity"]
    affected = render_number(
        "results:secondary.no_logs_sensitivity.total_pairs_affected",
        sensitivity["total_pairs_affected"],
    )
    print(f"no_logs sensitivity: {affected} pairs affected, conclusion unchanged")

    straddle = results["secondary"]["harness_straddle"]
    predating = render_number(
        "results:secondary.harness_straddle.entries_predating_the_fix",
        straddle["entries_predating_the_fix"],
    )
    print(
        f"harness straddle: {predating} analysed entries predate the "
        f"{straddle['boundary']} fix; straddling pairs: {straddle['straddling_pairs']}"
    )


# %%
def main(results_path, aggregates_path):
    results, aggregates = load(results_path, aggregates_path)
    print_headline(results)
    print_pairs(results)
    print_grid(results)
    print_data_quality(aggregates)
    print_secondaries(results)


# %%
if __name__ == "__main__":
    main(HERE / "results" / "results.json", HERE / "derived" / "aggregates.json")
