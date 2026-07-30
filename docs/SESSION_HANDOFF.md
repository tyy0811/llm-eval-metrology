# Session handoff

Written 2026-07-30 at commit `54aaf96`. Session-specific state only: what is done, what is held,
and what the next session must not re-derive. The durable record is `PLAN.md`,
`docs/DECISIONS.md`, and `experiments/swebench/PREREG.md`, which this file does not duplicate.

Delete or rewrite this file when it goes stale. It is a baton, not a document.

## Where the work stands

**Phase 0 to Phase 2 complete.** Engine v0.1 is `schema`, `paired`, `power`, `multiplicity`,
`reporting`, `cards`. Closed by D2.8.

**Phase 3 in progress.** T3.1 (`fetch.py`) and T3.2 (`run.py`) are complete and cleared. **T3.3 is
held** pending review sign-off, which was the state when this session ended.

534 tests, all green. CI green at `54aaf96`. 43 commits, 31 DECISIONS entries, 8 PREREG deviations.

## The result Experiment 1 produced

Under the pre-registered exact McNemar plus Holm procedure, **none of the 19 adjacent top-20 pairs
is statistically separable on the 500 Verified instances**. Gateway floor 10, largest observed gap
7, resolved count 0.

Use that wording. Do **not** write "cannot rank its own top 20": the result concerns *adjacent*
pairs under *one* registered procedure, and rank 1 against rank 20 may well be separable.

PREREG D7 established the headline follows from published resolve rates alone, so the per-instance
work characterizes it and cannot overturn it. `run.py` asserts that analytic expectation rather
than trusting the computation.

## Next task: T3.3

Outputs. A notebook that reads `results/` rather than recomputing, a README findings block written
by a generator, and the markdown rendering that D2.6 reassigned here from T2.5.

Two things carry in that the reviewer flagged as T3.3 prerequisites:

1. **D1.8's prose-number membership check** needs a committed aggregates file that contains every
   number prose will cite, including discordance counts and computed results. `results/results.json`
   holds the computed figures and `derived/aggregates.json` holds the source ones. Decide whether
   the checker reads both or whether they are consolidated.
2. **Per D1.6 the write-up leads with the analytic result**, not a p-value table. A reader who
   derives the bound independently after seeing a table of nulls concludes arithmetic was dressed
   as an experiment.

Then T3.4 (render the card set per D1.10), T3.5 (`make reproduce` becomes real, and the canonical
`ubuntu-24.04` plus Python 3.11.15 reproduction from D0.9 items 4 to 6 gets implemented), T3.6
(cross-repo handoff).

## Open items that are not code

- **Upstream issue [#462](https://github.com/SWE-bench/experiments/issues/462)**, opened 2026-07-27,
  no reply. Two questions: redistribution rights (not a blocker, D1.4 redistributes nothing) and
  harness comparability across submission dates (bears on D4's limitation). An answer could only
  narrow D4, never widen it. Recorded in `docs/PROVENANCE.md` as O1 and O2.
- **D1.4's default stands**: no derived upstream data is committed. Only the fetch pipeline,
  digests, expected checksums, and de minimis aggregates.
- **D3.1** records an accidental commit of 23 per-instance ids and the narrow history rewrite that
  removed them. Existing forks and caches still carry the blob; that limit is disclosed, not fixed.

## Constraints that were expensive to establish

Do not re-derive these. Each cost a review cycle.

- **`q` comes from `discordance_rate_from_counts`, never from a published gap** (D2.5). A tied pair
  has gap 0 and can have 80 disagreements. Deriving `q` from the gap reports "unattainable" for
  nine of nineteen pairs while looking plausible.
- **Separability is Holm over the vector of per-pair minimum attainable p-values** (D2.7), not each
  gap against `alpha / m`. On gaps 40 and 6 the wrong version gives 1 where Holm gives 2. It was
  reintroduced once inside the assertion meant to guard it.
- **Three thresholds stay separate**: family alpha for the verdict, `alpha / m` for the ruler and
  the gap floor, and the registered uncorrected 0.05 for the MDE.
- **`EQUIVALENT` is refused** until Phase 5 supplies TOST fields. A card that lies is worse than one
  that fails to draw.
- **Holm never imports `paired`**. The threshold-to-gap-floor translation lives in `reporting`.

## How this session was run, and what kept catching things

Every task went: write tests first, watch them fail, implement, run the full gate, commit with the
task ID, push, confirm CI. Then the reviewer found blocking defects and a corrective pass followed.
That happened on **every single task**. Expect it and do not treat a green suite as done.

The recurring failure mode, in one sentence: **a check that passes on the actual data while
encoding the wrong rule.** Instances found this session were the option-1 separability definition,
the MDE computed at `alpha / m` instead of the registered alpha, a manifest that wrote its own
expected checksums, a substitution guard that ran after the work it invalidated, a validator that
type-checked fields the renderer never read while missing two it did, and a test that matched
`EQUIVALENT` as a substring and so passed against the wrong error.

What actually caught these was never the happy path. It was negative controls: tamper with the
input, revert the fix and confirm the test fails, run the counterexample through `main()` rather
than around it. When claiming something is guarded, break it on purpose and show the break.

Two habits worth keeping. Snapshot baselines are written and then **failed** on first generation, so
they get diffed rather than blessed; that caught a heading regression no assertion covered. And
prose gets checked as carefully as code, because three separate defects this session were correct
code with a false sentence attached, and a wrong rationale on working code is harder to spot than a
bug.
