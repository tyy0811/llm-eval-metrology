# Pre-registration: Experiment 1, SWE-bench Verified leaderboard teardown

Author: Jane Yeung
Status: registered. Written and pushed before any data was fetched into this repo.
Recon facts this rests on: `docs/recon_swebench.md`, observed 2026-07-27.

This document is frozen once pushed. Departures are appended to the Deviations section with a
reason and a UTC timestamp, and are never edited into the body silently.

## 1. Question

Among the top N entries of the SWE-bench Verified leaderboard ranked by published resolve rate, how
many adjacent pairs are statistically distinguishable?

The answer is a count. It is reported whatever it turns out to be, including zero and including all
of them.

This is a question about the **resolving power of the benchmark at its instance count**, not about
which coding agent is better. A pair being indistinguishable means the benchmark cannot separate
them at 500 instances, not that the systems are equally good.

## 2. N, adjacency, and ties

**N = 20.** Fixed here, from published aggregates only, before any per-instance comparison has been
computed. The reasons, all outcome-independent:

- The top 20 spans 79.2 down to 74.4 published percent, a range of 24 instances out of 500. That is
  the tight cluster where the ordering question actually bites.
- 19 adjacent pairs is a multiplicity family that Holm handles while remaining interpretable.
- Every one of the top 20 reconciles exactly to an integer resolved count out of 500, so the
  coverage rule (section 6) has no reason to fire and the analyzed set is not shaped by artifact
  availability.

**Adjacency** is defined by the published order: the array order of the `results` list for the
Verified board in `data/leaderboards.json` at the pinned commit, which recon confirmed is already
sorted by resolve rate descending. Pair *i* is (entry *i*, entry *i+1*) for *i* = 1 to 19.

**Ties are adopted as published and not reordered.** Recon established that within a tie group the
published order follows no discernible rule: dates are non-monotonic inside groups. Any tiebreak we
invented would be our artifact rather than the leaderboard's, and the object of study is the board
as published. So the published order stands, and tie-group membership is recorded for every entry.

### 2.1 A consequence of ties, declared in advance

A published rate determines the resolved count exactly, because one instance is 0.2 percent of 500.
Two tied entries therefore have **equal resolved counts**.

For a paired binary comparison, let *n10* be instances the first system resolved and the second did
not, and *n01* the reverse. Equal resolved counts force *n10 = n01*. The exact two-sided McNemar
test on discordant pairs is then a binomial test at p = 0.5 with equal counts, whose p-value is
**exactly 1**.

So every tied adjacent pair is non-distinguishable **by construction, not by evidence**. This is
arithmetic, fixed before seeing any per-instance data. It is registered here so that the resulting
p-values are not later presented as an empirical finding.

The scale of this is known in advance from published aggregates alone. Inside the top 20 there are
7 tie groups, and of the 19 adjacent pairs **9 are tie-forced and 10 admit a real test**.

The headline count is therefore reported in three parts: pairs distinguishable, pairs not
distinguishable under a real test, and the 9 pairs not distinguishable by tie arithmetic.

### 2.2 The adjacent gaps, stated before the analysis

Also known from published aggregates, and recorded here so that the eventual answer cannot be
presented as a surprise. Across the 19 adjacent pairs the published gaps in instances out of 500
are:

```
0, 2, 7, 3, 0, 0, 2, 3, 0, 1, 0, 2, 2, 0, 1, 0, 1, 0, 0
```

The largest adjacent gap anywhere in the top 20 is **7 instances**. Ten of the pairs differ by 0
instances and the rest by 1 to 7.

A paired test on differences this small is unlikely to clear any multiplicity correction, and the
MDE in section 5 exists precisely to quantify that. Registering the gaps now means the expected
outcome, a count at or near zero, is a pre-declared possibility rather than a disappointing result
that invites a change of method. Per PLAN.md section 2, that count ships as the finding.

## 3. Data

Public per-instance pass/fail artifacts from `SWE-bench/experiments` at the pinned commit, mapped
to the PLAN.md section 4 schema:

| Column | Value |
|---|---|
| `item_id` | SWE-bench Verified instance ID, 500 of them |
| `system` | the leaderboard `folder` string, which is unique and stable |
| `run` | `0`; each submission is a single evaluation |
| `instrument` | `hidden-tests`, the declared anchor and the sole instrument |
| `label` | `1` if resolved, `0` otherwise |

There is no cheap instrument in this experiment and no estimator that needs one. `hidden-tests` is
the anchor by declaration, as required by the guardrail that no estimate runs without an explicit
anchor.

**Two artifact formats are normalized to this one schema**, and the source format is recorded per
system:

- Format A, `results/results.json`: `label = 1` if the instance ID appears in `resolved`, else `0`.
- Format B, `per_instance_details.json`: `label = 1` if the per-instance `resolved` boolean is true,
  else `0`.

**`no_generation` and `no_logs` are labeled `0`.** This matches the leaderboard convention, which
computes the resolve rate over all 500 instances. The choice is declared rather than defaulted,
and the per-system counts in both categories are reported alongside the results. If any top-20
system carries a nonzero `no_logs` count, a sensitivity analysis dropping those instances pairwise
is reported as a labeled secondary.

## 4. Integrity gates, run before any test

The analysis halts and reports rather than proceeding if any gate fails:

1. Each of the 20 systems yields exactly 500 labels, one per instance ID.
2. The instance ID set is identical across all 20 systems and equals the Verified split's 500 IDs at
   the pinned dataset revision.
3. For each system, the derived resolved count equals the published rate times 5, exactly. Recon
   found eight board entries that fail this at rank 63 and below, so this gate is real.
4. The loader's uniqueness key on (`item_id`, `system`, `run`, `instrument`) holds with no
   duplicates.

## 5. Tests

All four are pre-specified. Nothing else enters the headline.

1. **Exact McNemar per adjacent pair.** Two-sided exact binomial test at p = 0.5 on the discordant
   counts (*n01*, *n10*). Exact, not the chi-square approximation and not continuity-corrected.
   Pairs with zero discordance are reported as p = 1 with the discordance count shown.
2. **Paired bootstrap interval** on the resolve-rate difference for each adjacent pair. The
   resampling unit is the instance, resampled with replacement across the 500 shared items, which
   preserves the pairing. B = 10000 replicates, percentile method, 95 percent level.
3. **Holm across the family**, FWER 0.05. The family is the 19 adjacent-pair McNemar tests, passed
   explicitly. "Distinguishable" means Holm-adjusted p below 0.05.
4. **MDE for the benchmark at its instance count.** Paired binary design, n = 500, alpha 0.05
   two-sided, power 0.80, reported across a declared discordance grid and at each pair's observed
   discordance. Every value is emitted by the generator; none is typed by hand.

**Declared secondary.** Holm re-run over only the non-tied adjacent pairs. Rationale fixed in
advance: including tie-forced tests whose p-value is 1 by arithmetic enlarges the family and
tightens Holm's threshold for the informative pairs, so the secondary shows what the multiplicity
correction costs. The primary remains all 19 pairs; the secondary is always labeled as secondary.

**Seeds.** Master seed 20260727. Per-pair bootstrap seeds derive deterministically from the master
seed and the pair index, so `make reproduce` regenerates byte-identical results.

## 6. Coverage rule

An entry lacking complete artifacts, or failing any integrity gate in section 4, is dropped and
replaced by the next entry down the published ordering. Every substitution is recorded in the
results file with the reason.

Recon found that all 180 Verified board entries have artifacts, split across two directories, and
that all top 20 reconcile exactly. So this rule is expected not to fire. If it does not fire, that
is stated in the results rather than passed over in silence.

## 7. Board precision

The analyzed artifact is the **official SWE-bench Verified leaderboard** at the pinned commit,
restricted to entries with public per-instance results. Vendor self-reported aggregates published
elsewhere are out of scope.

Entries whose artifacts live under `evaluation/bash-only/` **are in scope**, because they appear on
the Verified board and carry public per-instance results over the same 500 instances. Excluding them
would mean analyzing a board other than the published one. Their harness variant is recorded per
system and noted in the limitations.

## 8. Reporting rule

- The count of distinguishable adjacent pairs ships whatever it is, including zero and including 19.
- A verdict card is rendered per adjacent pair, plus one family summary card.
- Every number in any prose output comes from `reporting.py` reading the results file.
- Exploratory analysis is permitted, goes in an appendix labeled as exploratory, and never mixes
  into the headline or the cards.

## 9. What this experiment does not claim

- Not a claim that any system is better than another in general. The estimand is the resolve-rate
  difference on this fixed instance set under this harness.
- Not a validity claim about SWE-bench. Whether resolving these 500 instances measures software
  engineering ability is a separate question this experiment does not address.
- Not a claim about systems absent from the board, nor about the eight legacy entries whose
  published denominators differ.
- The board's population changes over time: since 2025-11-18 Verified accepts submissions only from
  academic teams and research institutions with open-source methods. Entries predate and postdate
  that change. This is a limitation, not a covariate.

## 10. Deviations

None yet. Each entry below is appended, never edited, with a UTC timestamp and a reason.
