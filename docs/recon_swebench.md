# Recon: SWE-bench Verified (Experiment 1)

Observed 2026-07-27. Every number here was read from a pinned source, not quoted from a paper or
a README. Commands are included so each fact can be re-derived.

**These are recon facts, not results.** They describe the data source and are inputs to
`experiments/swebench/PREREG.md`. No comparison between systems has been computed, and none may be
until the pre-registration is pushed. Nothing was written into the repo from these sources: all
inspection went to a scratch directory.

## Pinned sources

| Source | Identifier | Pinned at |
|---|---|---|
| Artifacts | `SWE-bench/experiments` | commit `2f15350cd32becc4569e0d826361048555b605c0`, committed 2026-03-29 |
| Leaderboard | `SWE-bench/swe-bench.github.io`, `data/leaderboards.json` | last touched in commit `7c4289f30aa1a1c63c2e2a25aae30c16d92b5114`, 2026-02-27 |
| Leaderboard file digest | sha256 `c3bf3a74d7d67ba7e2777e197f96894601917e8e186a078133897ed3e81566e5` | as fetched 2026-07-27 |
| Instance set | HF `princeton-nlp/SWE-bench_Verified` | revision `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`, modified 2025-02-18 |

`fetch.py` (T3.1) must pin these same revisions rather than tracking a branch, because both source
repos are live and the leaderboard is regenerated as submissions arrive.

## Instance set and count

The Verified split has **500 instances** in its `test` split. Confirmed without downloading the
dataset:

```
curl -s "https://datasets-server.huggingface.co/size?dataset=princeton-nlp/SWE-bench_Verified"
  -> split: test  rows: 500
```

There is no `train` or `dev` split to disambiguate. Instance IDs are strings of the form
`astropy__astropy-12907`.

## Where the per-instance artifacts live, and in two different formats

The leaderboard's Verified board has **180 entries**. Artifacts live under two directories of
`SWE-bench/experiments`, and the two directories use **incompatible file formats**. This was the
single most consequential recon finding, because a fetch script written against one format silently
excludes a fifth of the board.

**Format A**, `evaluation/verified/<folder>/results/results.json`, used by 134 folders:

```json
{"no_generation": [...], "no_logs": [...], "resolved": [...]}
```

Only resolved instance IDs are enumerated. Unresolved instances are implicit: the complement of
`resolved` within the 500. `no_generation` (no patch produced) and `no_logs` (evaluation logs
absent) are listed separately and are also absent from `resolved`.

**Format B**, `evaluation/bash-only/<folder>/per_instance_details.json`, used by the mini-SWE-agent
family:

```json
{"astropy__astropy-12907": {"cost": 0.72, "api_calls": 32, "resolved": true}, ...}
```

An explicit map over all 500 instance IDs with a boolean. This format is strictly more informative:
it distinguishes "attempted and failed" from "absent" without relying on the complement.

Both reconcile exactly to the published rate. Verified on three entries:

| Folder | Format | resolved | published |
|---|---|---|---|
| `20250928_trae_doubao_seed_code` | A | 394 of 500 | 78.8 |
| `20260217_mini-v2.0.0_claude-4-5-opus-high` | B | 384 of 500 | 76.8 |
| `20251215_livesweagent_claude-opus-4-5` | A | 396 of 500 | 79.2 |

## Coverage: every board entry has artifacts

Of the 180 Verified board entries, 133 map to a folder under `evaluation/verified/` and the other
**47 map to folders under `evaluation/bash-only/`**. Zero entries lack artifacts entirely.

```
gh api "repos/SWE-bench/experiments/git/trees/main?recursive=1" --jq '.tree[]|select(.type=="tree")|.path'
  -> all 47 otherwise-missing folders resolve under evaluation/bash-only/
```

All 134 folders under `evaluation/verified/` contain `results/results.json`. None is missing.
127 carry `metadata.yaml` and 7 carry `metadata.yml`, so metadata exists for all 134 under one
spelling or the other.

One folder, `20251127_openhands_claude-opus-4-5`, has artifacts but **no Verified board entry**.
Since eligibility is defined by the board, it is out of scope. Recorded so its absence is not later
mistaken for an oversight.

**Consequence for the plan's coverage rule.** PLAN.md T1.2 anticipates entries lacking complete
artifacts being replaced by the next entry down. On this board that rule has nothing to fire on in
the top region. It stays in the pre-registration as a contingency, and its non-firing is itself
reportable.

## Leaderboard ordering and ties

The `results` array in `leaderboards.json` is **already sorted by `resolved` descending**, verified
programmatically (`vals == sorted(vals, reverse=True)` is true). So "published ordering" is the
array order, which is reproducible from the pinned file.

**Ties are pervasive, not a corner case.** In the top 30 there are 9 tie groups covering 21 of the
30 entries. Tie group sizes of 2 and 3 both occur. Within the top 20:

| Published rate | Entries tied |
|---|---|
| 79.2 | 2 |
| 76.8 | 3 |
| 75.8 | 2 |
| 75.6 | 2 |
| 74.8 | 2 |
| 74.6 | 2 |
| 74.4 | 3 (two inside the top 20) |

**Within-tie ordering follows no discernible rule.** Dates are not monotonic in either direction
inside a tie group. The 76.8 group runs 2025-09-02, then 2025-08-04, then 2026-02-17. So the
published order inside a tie group is arbitrary, and "adjacency by published ordering" is
underdetermined exactly where the systems are closest. This is the central fact the pre-registration
has to handle.

Rates are stored as percentages. Because 1 instance is 0.2 percent of 500, a published rate
determines the resolved count exactly, and equal published rates mean **equal resolved counts**.

Inside the top 20 specifically: 7 tie groups, and of the 19 adjacent pairs **9 are tied and 10 are
not**. The adjacent gaps, in instances out of 500, are

```
0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0
```

so the largest adjacent gap anywhere in the top 20 is 7 instances.

## The top 20 by published resolve rate

Read from the pinned leaderboard file. `k` is the implied resolved count, `k = rate * 5`, an exact
integer for every one of these entries.

| Rank | Rate | k/500 | Split dir | Format | `checked` | Folder |
|---:|---:|---:|---|---|---|---|
| 1 | 79.2 | 396 | verified | A | False | `20251215_livesweagent_claude-opus-4-5` |
| 2 | 79.2 | 396 | verified | A | False | `20251205_sonar-foundation-agent_claude-opus-4-5` |
| 3 | 78.8 | 394 | verified | A | False | `20250928_trae_doubao_seed_code` |
| 4 | 77.4 | 387 | verified | A | string | `20251120_livesweagent_gemini-3-pro-preview` |
| 5 | 76.8 | 384 | verified | A | False | `20250902_atlassian-rovo-dev` |
| 6 | 76.8 | 384 | verified | A | False | `20250804_epam-ai-run-claude-4-sonnet` |
| 7 | 76.8 | 384 | bash-only | B | None | `20260217_mini-v2.0.0_claude-4-5-opus-high` |
| 8 | 76.4 | 382 | verified | A | False | `20250819_ACoder` |
| 9 | 75.8 | 379 | bash-only | B | None | `20260217_mini-v2.0.0_gemini-3-flash-high` |
| 10 | 75.8 | 379 | bash-only | B | None | `20260217_mini-v2.0.0_minimax-2-5-high` |
| 11 | 75.6 | 378 | verified | A | False | `20250901_warp` |
| 12 | 75.6 | 378 | bash-only | B | None | `20260217_mini-v2.0.0_claude-4-6-opus` |
| 13 | 75.2 | 376 | verified | A | False | `20250612_trae` |
| 14 | 74.8 | 374 | verified | A | False | `20250731_harness_ai` |
| 15 | 74.8 | 374 | verified | A | False | `20251103_sonar-foundation-agent_claude-sonnet-4-5` |
| 16 | 74.6 | 373 | verified | A | False | `20250720_Lingxi-v1.5_claude-4-sonnet-20250514` |
| 17 | 74.6 | 373 | verified | A | False | `20250915_JoyCode` |
| 18 | 74.4 | 372 | verified | A | False | `20250603_Refact_Agent_claude-4-sonnet` |
| 19 | 74.4 | 372 | verified | A | False | `20251015_Prometheus_v1.2.1_gpt5` |
| 20 | 74.4 | 372 | bash-only | B | True | `20251124_mini-v1.16.0_claude-opus-4-5-20251101` |

15 of the top 20 use format A and 5 use format B. The whole top 20 spans 79.2 down to 74.4, a range
of 4.8 percentage points, which is 24 instances out of 500.

## Data quality findings

**The `checked` field is not a usable filter.** Across all 180 entries it takes four different value
types: `False` (97), `True` (60), `None` (17), and a **string** (6) reading
`"false (See README.md for info on how to get your results verified)"`. A boolean test on this field
would treat that non-empty string as true, silently inverting the intended meaning for those 6
entries. If audit status is ever used as a criterion it must be parsed defensively.

**The `warning` field is empty for all 180 entries**, so it carries no exclusion signal at this
revision, despite the project having published a post about detecting cheating.

**Eight entries do not reconcile to k/500.** Their stored rates carry two decimals (64.93, 39.58,
28.73, 23.94, 21.62, 21.04, 13.52, 9.06) and imply non-500 denominators. For
`20250726_mini-v1.0.0_claude-sonnet-4-20250514` the artifact contains all 500 keys with 324
resolved, which is 64.80 percent, while the board publishes 64.93, matching 324/499 instead. The
denominator convention for these legacy entries differs from the rest of the board.

All eight sit at **rank 63 or lower**, so none is in the top region. This matters anyway: it means a
reconciliation check between artifact and published rate is a real integrity gate, not a formality,
and `fetch.py` must run it and fail loudly rather than trusting the board.

## Licensing and attribution

| Repo | GitHub-detected license |
|---|---|
| `SWE-bench/SWE-bench` (harness code) | MIT |
| `SWE-bench/experiments` (the artifacts we read) | **none detected** |
| `SWE-bench/swe-bench.github.io` (the leaderboard) | NOASSERTION |
| HF `princeton-nlp/SWE-bench_Verified` | no license tag |

The artifact repo carries **no explicit license**. Its README states the logs are "publicly
accessible and meant to enable greater reproducibility and transparency", which is a statement of
intent and not a grant of rights.

This does not block the experiment, and the reason is the guardrail already in PLAN.md section 2:
ship derived label tables, checksums, and fetch scripts only. What Experiment 1 commits is a table
of binary resolved/not-resolved outcomes keyed by instance ID and system, which are facts about
public benchmark runs, together with a script that re-derives them from the pinned upstream. No
logs, trajectories, patches, or source texts are copied into this repo. Attribution to SWE-bench and
to each submitting team is recorded in the derived table's provenance and in the experiment README.

If any rights question is ever raised, the fetch script plus checksums reproduce everything from
upstream, so the derived table can be removed without the experiment becoming unreproducible.

**Submission policy note.** Since 2025-11-18 the Verified board accepts submissions only from
academic teams and research institutions with open-source methods and peer-reviewed publications.
Entries predating that date were accepted under the previous policy. This changes what the board's
population represents over time and belongs in the limitations, not in the analysis.

## Open questions carried into the pre-registration

1. Adjacency inside a tie group is underdetermined by the published order. The pre-registration must
   declare a rule and must state that tied adjacent pairs have equal marginals.
2. Two artifact formats must be normalized to one schema, with the format recorded per system.
3. `no_generation` and `no_logs` must be assigned a label explicitly rather than by default.
