# Provenance register

One row per external source: what it is, how it is pinned, its license status, what this repo
redistributes versus fetches, how it is attributed, and any open question with a date and a channel.

Updated during each experiment's recon phase, while the facts are fresh, rather than reconstructed
at publication time. A source appears here before it is used, not after.

**The standing rule** (`docs/DECISIONS.md` D1.4): this repo distributes a deterministic
fetch-and-derive pipeline plus checksums of what it must produce. It does not redistribute upstream
per-instance data. What ships is a program that reads public data, not a copy of someone else's
database.

**The acceptance criterion for a source** is not "raises no licensing question", because no source
passes that. It is "raises only licensing questions that can be designed around without compromising
the analysis". A source fails only when the analysis genuinely requires redistributing protected
content.

---

## Experiment 1, SWE-bench Verified

### S1.1 Per-instance evaluation artifacts

| Field | Value |
|---|---|
| Source | `SWE-bench/experiments` on GitHub |
| What it is | Per-instance pass/fail records for submissions to the SWE-bench leaderboards |
| Pinned at | commit `2f15350cd32becc4569e0d826361048555b605c0` (2026-03-29) |
| License status | **No LICENSE file. GitHub detects none.** Default copyright applies |
| Stated intent | The README calls the logs "publicly accessible and meant to enable greater reproducibility and transparency", which is intent, not a grant of rights |
| Redistributed | **Nothing.** No per-instance table, no logs, no trajectories, no patches, no predictions |
| Fetched at run time | `evaluation/verified/<folder>/results/results.json` and `evaluation/bash-only/<folder>/per_instance_details.json`, at the pinned commit |
| Committed instead | The fetch and derive script, upstream file digests, expected checksums of the derived table, and de minimis aggregates (per-entry resolve totals, discordance counts) |
| Attribution | SWE-bench and the individual submitting team named per entry, recorded in the derived table's provenance and in the experiment README |

**Channel for both open questions below:** `SWE-bench/experiments` issue
[#462](https://github.com/SWE-bench/experiments/issues/462), opened 2026-07-27. Status: awaiting
reply. Any answer is recorded here and, where it touches the analysis, appended as a deviation in
`experiments/swebench/PREREG.md`.

**Open question O1, rights.** Whether redistributing a derived binary outcome table would be
acceptable, and under what attribution. **Not a blocker:** under D1.4 nothing is redistributed
regardless of the answer, so a reply can only widen what is permitted, never narrow what is planned.

**Open question O2, comparability.** Whether per-instance results from submissions across different
dates are directly comparable, given that no submission records the evaluation harness version it
ran under. This one bears on the analysis rather than on rights, and it is the more important of the
two. Recorded as a limitation in deviation D4 of `experiments/swebench/PREREG.md`, which stands
whatever the reply is, unless the reply supplies a harness-version record we can condition on.

### S1.2 Leaderboard ordering

| Field | Value |
|---|---|
| Source | `SWE-bench/swe-bench.github.io`, file `data/leaderboards.json` |
| What it is | The published board, including the ordering and the resolve rate per entry |
| Pinned at | file last modified in commit `7c4289f30aa1a1c63c2e2a25aae30c16d92b5114` (2026-02-27); sha256 of the file as fetched `c3bf3a74d7d67ba7e2777e197f96894601917e8e186a078133897ed3e81566e5` |
| License status | GitHub reports NOASSERTION |
| Redistributed | **Nothing.** The published rates for the analyzed entries appear in `docs/recon_swebench.md` and in the pre-registration as recon facts, which is citation of published aggregates, not redistribution of the file |
| Fetched at run time | The whole file, verified against the recorded sha256 |
| Attribution | SWE-bench leaderboard, cited with the pinned commit |

### S1.3 Instance set

| Field | Value |
|---|---|
| Source | Hugging Face dataset `princeton-nlp/SWE-bench_Verified` |
| What it is | The 500 instance IDs of the Verified split |
| Pinned at | revision `c104f840cc67f8b6eec6f759ebc8b2693d585d4a` (modified 2025-02-18) |
| License status | **No license tag on the dataset.** The SWE-bench harness code repo is MIT, which does not automatically extend to the dataset |
| Redistributed | **Nothing.** Only the count, 500, and the ID format appear in recon notes |
| Fetched at run time | Instance IDs only. The task instances, patches, and problem statements are not needed, because Experiment 1 operates on labels |
| Attribution | SWE-bench Verified, cited with the pinned revision |

Note that Experiment 1 needs the ID set purely to validate that every system covers the same 500
items. It never reads a problem statement or a patch.

---

## Sources not yet used

Experiments 2 and 3 add their rows during their own recon phases (PLAN.md T4.1 and T7.1). Nothing is
recorded for them here in advance, because a provenance row asserting facts nobody has checked is
worse than an empty section.

Two expectations, recorded as expectations and not as findings:

- **SummEval** is the same shape as Experiment 1. Its annotations are distributed without the source
  news articles, because that corpus carries its own terms, and the plan needs labels only.
- **LLM-AggreFact** requires running a cheap instrument over subsets, so its row will need to cover
  model weights and inference outputs in addition to the label source.
