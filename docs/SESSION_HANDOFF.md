# Session handoff

Written 2026-08-14 at commit `7b4462b`. Session-specific state only: what is done, what is next,
and what the next session must not re-derive. The durable record is `PLAN.md`,
`docs/DECISIONS.md`, and `experiments/swebench/PREREG.md`, which this file does not duplicate.

Delete or rewrite this file when it goes stale. It is a baton, not a document.

## Opening prompt for the next session

> Read `docs/SESSION_HANDOFF.md`, then `docs/plans/2026-08-13-t3.4-card-set.md` and its approved
> spec `docs/specs/2026-08-13-t3.4-card-set-design.md`. Execute T3.4 with
> superpowers:subagent-driven-development, one task per subagent with a review between tasks.
> Stop at the end of Task 3 and bring the table reference to me for visual approval before any
> renderer code exists.

## Where the work stands

**Phases 0 to 2 complete.** Engine v0.1, closed by D2.8.

**Phase 3: T3.1, T3.2, and T3.3 are complete and cleared by Jane.** T3.4 has an approved spec and
an approved implementation plan, and no T3.4 code has been written.

663 tests, all seven gates green, CI green at `7b4462b`. 70 commits, 37 DECISIONS entries, 8
PREREG deviations. Clean worktree.

The seven gates are `test`, `lint`, `dash-check`, `import-check`, `prose-check`, `report-check`,
and the CI-only assertion that `make reproduce` still fails.

## The result Experiment 1 produced

Under the pre-registered exact McNemar plus Holm procedure, **0 of the 19 adjacent top-20 pairs
are statistically distinguishable on the 500 Verified instances**. Of the 19, 9 are tie-forced and
10 admit a real test and none rejects. Gateway floor 10, largest observed gap 7.

Use that wording. Do **not** write "cannot rank its own top 20": the result concerns *adjacent*
pairs under *one* registered procedure, and rank 1 against rank 20 may well be separable.

## Next task: T3.4, and how to run it

The plan is seven tasks. Read it; do not re-plan it. Two things about it that matter more than the
rest:

1. **Task 3 ends at a hard human approval gate.** It commits `table_reference.html` and a table
   language in `card.css`, and no renderer. D1.3 exists because a renderer written first makes its
   own output the snapshot baseline, and `card.css` has no table styling today, so there is no
   visual language to target yet. Do not let a subagent start Task 4 before Jane approves.
2. **No network.** The `fetch_date` migration in Task 1 is deliberately offline. A fetch run today
   cannot establish the historical date `2026-07-29`; it can only confirm the pinned bytes are
   still reachable, so re-fetching would risk the committed digests for no evidence.

After T3.4: T3.5 (`make reproduce` becomes real, and the canonical `ubuntu-24.04` plus Python
3.11.15 reproduction from D0.9 items 4 to 6), then T3.6 (cross-repo handoff).

## Constraints that were expensive to establish

Do not re-derive these. Each cost at least one review cycle.

- **`q` comes from `discordance_rate_from_counts`, never from a published gap** (D2.5). A tied pair
  has gap 0 and can have 80 disagreements.
- **Separability is Holm over the vector of per-pair minimum attainable p-values** (D2.7), not each
  gap against `alpha / m`. It was reintroduced once inside the assertion meant to guard it.
- **Distinguishable is the observed count, `resolved_count`**, never `separable_count` (D3.4,
  PREREG section 5). Both are zero on this data, so the conflation shows no symptom here.
- **Three thresholds stay separate**: family alpha for the verdict, `alpha / m` for the ruler and
  the gap floor, and the registered uncorrected 0.05 for the MDE. The `_basis` strings on a card
  name which one produced each number, so a swapped basis string is that defect relocated into a
  label with every figure still correct.
- **`EQUIVALENT` is refused** until Phase 5 supplies TOST fields.
- **Holm never imports `paired`.** The threshold-to-gap-floor translation lives in `reporting`.
- **No per-pair floor column** in any table (D3.6, and D3.8 supersedes D1.10's column sentence for
  the card set). The values are in neither corpus file and computing them would recompute in the
  reporting layer.
- **D4 attaches to observed per-instance quantities only** (D1.11), never to pair identity, the
  resolved-count gap, or the headline.
- **Every prose figure renders through `render_number`** at a source-qualified path (D3.5). The
  registry is total over the two-file corpus (D3.2) in both directions.
- **`prose-check` scope** is the README's running prose plus the notebook's markdown cells.
  `cards.html` is excluded on purpose, and T3.4 Task 6 records why in the checker's docstring.

## How this session was run, and what kept catching things

Every task went: write tests first, watch them fail, implement, run the full gate, commit with the
task ID, push, confirm CI. Then Jane reviewed and found blocking defects, and a corrective pass
followed. That happened on **every single task**, including tasks reported as verified with a
green suite and green CI. Expect it and budget for it.

The recurring failure mode, in one sentence: **a check that passes on the actual data while
encoding the wrong rule.** This session's instances were a `None` crash masked by an
all-attainable corpus, generic rounding that made the bare integers 0 and 1 members by accident, a
`PROSE_FIGURES` rule that was vacuous in eight of nine fields, a vacuous column-swap test that
asserted two different strings differ, a validator that sorted the file whose order it existed to
validate, and `abs()` on a gap that accepted an inverted leaderboard.

What catches these is never the happy path. It is negative controls: tamper with the input, revert
the fix and confirm the test fails, run the counterexample through the live entry point rather
than around it. When claiming something is guarded, break it on purpose and show the break.

Two habits worth keeping. Snapshot baselines are written and then **failed** on first generation,
so they get diffed rather than blessed. And prose gets checked as carefully as code: several
defects this session were correct code with a false sentence attached, and a wrong rationale on
working code is harder to spot than a bug.

One thing worth flagging rather than burying: **enumerate from the artifact, never from memory.**
Writing the T3.4 crosswalk from memory produced a rule set with six unmapped leaves and an
invented CSV field, and both were caught only by computing the inventory from the committed files.
The same habit found that the ruler split is `[n10, n01]`, where a reversed mapping would render
the edge favouring the wrong system with every number still individually correct.
