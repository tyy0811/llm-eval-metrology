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

Each entry below is appended, never edited, with a UTC timestamp and a reason. The body above is
frozen and is not amended by these entries, including where an entry corrects an error in it.

### D1, 2026-07-27T12:58:59Z, the primary count is analytically forced, not merely likely

**Reason.** Pre-registration review, before any data was fetched, established that the registered
headline is not "likely near zero" as section 2.2 implies. Conditional on the registered top 20
standing, it is **forced to be exactly zero**, and no per-instance data can change it.

**Derivation.** For an adjacent pair whose resolved counts differ by *g*, integrity gate 3 fixes *g*
from the published rate. Writing the discordant counts as *n01* and *n10*, the count difference
forces *n10 - n01 = g*. The exact two-sided McNemar test is a binomial test at p = 0.5 on
*n_d = n01 + n10*. The smallest attainable p-value occurs when all discordance runs one way, that is
*n01 = 0* and *n_d = g*, giving

```
p_min = 2^(1 - g)
```

and p increases monotonically as *n_d* grows beyond *g*. Verified against `scipy.stats.binomtest`
for every gap present in the registered set, and the monotonicity checked numerically.

The largest registered gap is 7 instances, so **every raw p-value in this family is at least
0.015625**. Holm requires the smallest p-value in a family of *m* to fall below alpha / *m*:

| Family | m | Threshold | Smallest attainable p |
|---|---:|---|---|
| Primary, all adjacent pairs | 19 | 0.05 / 19 = 0.002631579 | 0.015625 |
| Secondary, non-tied pairs | 10 | 0.05 / 10 = 0.005 | 0.015625 |

Neither family can reject anything, whatever the per-instance overlap turns out to be.

**What this changes.** The primary result is analytic rather than empirical. The count of
distinguishable adjacent pairs is zero by arithmetic, and the run confirms rather than determines
it. Section 2.1 already registered 9 of the 19 pairs as tie-forced; this entry extends the same
reasoning to the remaining 10, which section 2.2 had treated as merely unlikely to clear.

**What this does not change.** N, adjacency, tie handling, the four tests, the seeds, the integrity
gates, the coverage rule, and the reporting rule all stand as registered. The analysis still runs in
full, because the data are still required for the discordance counts, the paired bootstrap
intervals, the MDE, the verdict cards, and the family summary card. Only the distinguishable-pair
count is settled in advance.

**Conditionality.** The forcing holds conditional on the registered top 20 standing, which means
conditional on integrity gate 3 passing and on the coverage rule not substituting an entry. Any
substitution changes the gap vector, and this derivation must then be recomputed and appended as a
further deviation before the primary is reported.

**Effect on the finding.** This strengthens it. The claim is no longer "we tested the top 20 and
separated none of them" but "at 500 instances this benchmark cannot separate any adjacent pair in
its own published top 20, and that is decidable without running the comparison."

### D2, 2026-07-27T12:58:59Z, arithmetic error in section 2.2

**Reason.** Same review. Section 2.2 states "Ten of the pairs differ by 0 instances and the rest by
1 to 7." That is wrong and contradicts section 2.1 of the same document.

**Correction.** The registered gap vector contains **nine** zeros, not ten. Of the 19 adjacent
pairs, 9 differ by 0 instances and 10 differ by 1 to 7, which matches the "9 tie-forced, 10 admit a
real test" split registered in section 2.1. The frozen body is left as written; this entry is the
correction of record.

### D3, 2026-07-27T13:13:53Z, two corrections to D1

**Reason.** Review of D1. Deviations are append-only, so D1 is left as written and this entry is the
correction of record for both points below. Neither affects the 0.015625 bound or the forced-zero
conclusion.

**Correction 1, the closed form is not valid at g = 0.** D1 writes `p_min = 2^(1 - g)`, which
evaluates to 2 at g = 0 and is therefore not a probability. The precise expression is

```
p_min(g) = min(1, 2^(1 - g))
```

equivalently `p_min = 1` for g = 0, and `2^(1 - g)` for g >= 1. It is also worth recording what D1
left implicit: since `n_d = n01 + n10` and `n10 - n01 = g`, the feasible discordance totals are

```
n_d = g, g + 2, g + 4, ...
```

that is, `n_d = 2 * n01 + g`, so `n_d` always shares the parity of `g`. The minimum over feasible
`n_d` is attained at `n01 = 0`. Verified against `scipy.stats.binomtest` across the feasible `n_d`
for every gap in the registered set: at g = 0 and g = 1 every feasible configuration yields exactly
p = 1.0, and at g = 7 the minimum is 0.015625 at `n_d` = 7.

**Correction 2, provenance wording in D1 is too strong.** D1 states that the review happened
"before any data was fetched". Structural upstream data had already been inspected during recon,
which `docs/recon_swebench.md` discloses. The accurate claim is that the review, and this
pre-registration, happened

> after structural recon, but before any committed derived-data artifact or per-instance comparison.

That is what the git history actually evidences. The same narrower wording replaces "before any
data was fetched" wherever this experiment's provenance is described, including in the status line
of this document and in any findings block generated later.

### D4, 2026-07-27T13:13:53Z, a limitation section 9 does not register

**Reason.** Section 9 registers the board's changing population as a limitation but says nothing
about whether results from different submissions are **evaluated comparably**. That is the most
obvious rebuttal to the whole analysis, and it was missed. The body is frozen, so it is recorded
here.

**The limitation.** A paired comparison assumes both systems were measured by the same instrument.
For this board that assumption is unverifiable from the artifacts:

- No submission records the evaluation harness version it ran under. Checked directly: `metadata.yaml`
  carries authors, model, org, logo, report, site, and S3 asset paths, and no version, image, or
  environment field. A tree-wide search for a harness version file returns nothing.
- The analyzed entries span roughly two years of submission dates.
- Upstream has itself documented that harness behavior changed: SWE-bench ships a note on an
  evaluation bug fixed in April 2024, and a validation re-run performed that month to check that
  task instance behavior still reproduced.

So `hidden-tests` is treated as one instrument across all systems, when it is more accurately a
family of harness versions that cannot be distinguished from the published artifacts.

**Effect on this experiment.** None on the primary, which D1 established is analytically forced and
therefore cannot be rescued or overturned by any comparability argument. It does bear on the
discordance counts, the paired intervals, and the MDE, since harness drift would inflate apparent
discordance between systems submitted far apart in time.

**Required.** This limitation appears in the findings block, the verdict cards' provenance seal, and
any public write-up, stated as an unresolved threat to comparability rather than a caveat in
passing. The question has been put to the upstream maintainers (`docs/PROVENANCE.md`, open question
O2); any answer is appended here as a further deviation.

**Not registered as an analysis change.** No test, threshold, or estimand changes. This entry adds a
disclosure obligation only.

### D5, 2026-07-27T13:41:01Z, the mechanism behind D4, and a pre-specified straddle diagnostic

**Reason.** D4 recorded the comparability threat but not its direction, and direction decides whether
the threat can overturn the null or only qualify the surrounding quantities.

**Why D4 cannot overturn the null.** The floor established in D1 and D3,
`p_min(g) = min(1, 2^(1 - g))`, is a minimum **over every feasible discordance configuration**. It
depends only on the resolved-count gap `g`, which integrity gate 3 fixes from the published rates.
Harness heterogeneity perturbs discordance, not `g`. The floor is therefore immune to it.

One refinement, because the direction is the opposite of the intuitive one and the distinction
should be on the record. For fixed `g`, the exact p-value **increases** with the discordance total
`n_d`, verified numerically: at g = 7 the p-values across feasible `n_d` of 7, 9, 11, 13, 15 are
0.015625, 0.039062, 0.065430, 0.092285, 0.118469. Spurious disagreement inflates `n_d`, so it
inflates p. Removing harness noise would move each p **downward, toward the floor and toward
significance**, never upward.

So the correct claim is that the null is **immune** to comparability, not that comparability
reinforces it. A noise-free re-evaluation could only push observed p-values down to the floor, and
the floor at the registered gaps still cannot clear either Holm threshold. The conclusion in D1
stands, by a stronger argument than "the noise was helping us".

The caveat is the one D1 already registered: this holds conditional on the published resolved counts.
If a uniform re-evaluation changed the counts themselves, `g` changes, and the derivation is redone
and appended.

**The case that does bite is systematic, not symmetric.** A documented evaluation fix partitions
submissions into a pre-boundary and a post-boundary population judged under different criteria. Two
entries straddling such a boundary could differ by artifact rather than capability, and that is
directional rather than noise.

**Pre-specified diagnostic.** Group the analyzed entries by submission date relative to the
SWE-bench evaluation fix documented for April 2024, and report which adjacent pairs straddle it.
Reported whatever the result, alongside the primary.

**Measured now, from published submission dates only.** Zero of the registered top 20 predate
2024-04-15. The earliest submission date in the analyzed set is 2025-06-03, more than a year after
the fix, and **no adjacent pair straddles the boundary**. For contrast, 8 of the 180 board entries
do predate it, all far below the analyzed region. The directional case is therefore inert for this
particular analysis, which is a fact worth reporting rather than a reason to drop the diagnostic:
the general threat in D4 stands, because harness changes after April 2024 remain possible and remain
unrecorded.

**Also asked upstream** in `SWE-bench/experiments` issue
[#462](https://github.com/SWE-bench/experiments/issues/462): whether archived artifacts reflect the
original evaluation or a post-fix re-run. If everything was re-evaluated under a single harness, D4
largely dissolves. Any answer is appended here.

### D6, 2026-07-27T13:41:01Z, the exact test convention is declared, not left to the implementation

**Reason.** The floor `min(1, 2^(1 - g))` holds only under a particular definition of the two-sided
exact p-value. Leaving the convention implicit would let `paired.py` and its fixtures disagree by
definition while looking like a bug.

**Declared convention.** `paired.py` implements the two-sided exact McNemar test as **twice the
smaller binomial tail at p = 0.5, capped at 1**:

```
p = min(1, 2 * P(X <= min(n01, n10)))    with X ~ Binomial(n01 + n10, 0.5)
```

**Explicitly not used:** the mid-p correction, and any convention that would alter the floor.

Recorded from verification rather than assumed: for the symmetric case p = 0.5 the "sum of all
outcomes no more probable than the observed" rule, which is what `scipy.stats.binomtest` implements
for `alternative="two-sided"`, **coincides exactly** with the doubling rule at every gap from 0 to
10. The two conventions are interchangeable here, and either satisfies the floor.

The mid-p correction does not. It yields `2^(-g)`, exactly half the doubling value, which lowers
every threshold below by one gap. Mid-p is a defensible choice in other contexts and is excluded
here because it would break the registered bound.

**Pinned thresholds.** The minimum resolved-count gap at which the floor can clear a threshold at
all:

| Correction | Threshold | Minimum gap, declared convention | Minimum gap, mid-p |
|---|---|---:|---:|
| Uncorrected, alpha 0.05 | 0.05 | 6 | 5 |
| Holm, m = 10 (secondary family) | 0.005 | 9 | 8 |
| Holm, m = 19 (primary family) | 0.002631579 | 10 | 9 |

The largest gap in the registered top 20 is **7**. It does not reach 9, let alone 10. This is the
same forced-zero conclusion as D1, expressed as a hard floor on the gap rather than as a bound on p.

**Fixture requirement for T2.2.** The `paired.py` test suite pins the exact p-value at gaps 0
through 10 under the declared convention, with gap 0 and gap 1 both returning exactly 1, and
asserts the convention by name so that a future switch to mid-p fails loudly rather than silently
shifting every threshold.

### D7, 2026-07-27T13:53:49Z, the headline needs no upstream artifacts, and D4's disclosure narrows

**Reason.** Review noted a property of the primary that neither D1 nor D6 stated, and that changes
where the D4 caveat attaches.

**The headline depends on published resolve rates and nothing else.** Its three inputs are the
adjacent gap vector, which follows from the published rates because one instance is 0.2 percent of
500; the floor `min(1, 2^(1 - g))` under the convention declared in D6; and the Holm threshold, which
follows from alpha and the family size. Confirmed by computing the separable count from the pinned
leaderboard file alone: **0 of 19**, every gap below the primary floor of 10.

Consequences worth stating plainly:

- The primary requires **no per-instance artifacts, no fetch, and no derived table**. It would stand
  if the fetch never ran.
- It therefore raises **no licensing question at all**, which is a stronger position than the one
  D1.4 already secured by shipping a pipeline rather than a database.
- **D4 cannot touch it**, not merely as a matter of direction (D5) but because harness comparability
  is a property of per-instance evaluation, and the headline reads none.
- Anyone can verify it from the public leaderboard with a calculator in a few minutes, which makes
  it the most defensible claim this experiment can publish.

**Narrowed disclosure obligation.** D4 required its limitation to appear in the findings block, the
cards' provenance seal, and any write-up. That scope is now too broad and would mislead: a reader
seeing the harness caveat attached to the headline would infer the headline is contingent on it.
D4's disclosure attaches to the **secondary quantities only**, being the discordance counts, the
paired bootstrap intervals, and the MDE, all of which do read per-instance data.

The headline instead carries a positive statement of its own provenance: that it derives from
published resolve rates alone. The write-up says explicitly that the per-instance work
**characterizes the finding but cannot overturn it**.

D4 is otherwise unchanged and its diagnostic under D5 still runs.
