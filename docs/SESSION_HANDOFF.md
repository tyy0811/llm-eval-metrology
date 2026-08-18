# Session handoff

Written 2026-08-18, updated at commit `30aff44`. Session-specific state only: what is done, what is next,
and what the next session must not re-derive. The durable record is `PLAN.md`,
`docs/DECISIONS.md`, and `experiments/swebench/PREREG.md`, which this file does not duplicate.

Delete or rewrite this file when it goes stale. It is a baton, not a document.

## Opening prompt for the next session

> Read `docs/SESSION_HANDOFF.md`, then `docs/specs/2026-08-18-t3.5-reproduce-design.md`
> (revision 2). Confirm the spec is approved, then write the T3.5 implementation plan. Do not
> touch the Makefile before the plan is approved, and do not start T3.6 until reproduction passes
> in canonical CI.

## Where the work stands

**Phases 0 to 2 complete.** Engine v0.1, closed by D2.8.

**Phase 3: T3.1, T3.2, T3.3 and T3.4 are complete and cleared by Jane.** T3.5 has a spec at
revision 2, awaiting confirmation, and no implementation.

116 commits, 859 tests, 40 DECISIONS entries, 8 PREREG deviations. Clean worktree.

**Pushed and canonical-CI green through `3e2685f`** (run 32146848927, `ubuntu-24.04`, Python
3.11.15). Two later commits are **local only and deliberately unpushed**, because they are a spec
awaiting approval: `b75fe53` (draft) and `30aff44` (revision 2).

The seven gates are `test`, `lint`, `dash-check`, `import-check`, `prose-check`, `report-check`,
and the CI-only assertion that `make reproduce` still fails. **T3.5 replaces that last one.**

## The result Experiment 1 produced

Under the pre-registered exact McNemar plus Holm procedure, **0 of the 19 adjacent top-20 pairs
are statistically distinguishable on the 500 Verified instances**. Of the 19, 9 are tie-forced and
10 admit a real test and none rejects. Gateway floor 10, largest observed adjacent gap 7.

Use that wording. Do **not** write "cannot rank its own top 20": the result concerns *adjacent*
pairs under *one* registered procedure, and rank 1 against rank 20 may well be separable. Rank 1
leads rank 20 by 24, so any superlative about leads must be scoped to neighbors.

## What T3.4 shipped

`experiments/swebench/results/cards.html`: a plain-language finding first, then a closed
`details.technical-apparatus` holding the family card, the nineteen-row table, and the two
D8-selected pair cards. Written by `report.py --write` and byte-compared by `--check`, alongside
`pairs.csv` and the README block.

Three artifacts govern its appearance and are **frozen**, carrying Jane's D1.3 approval:

- `metrology/cards/fixtures/page_reference.html` is the full page: hierarchy, typography, the
  plain-language finding, the comparison bars, the masthead, and the collapsed technical section.
  Its approved blob is `a00f42efa8b33d6dfb116ac080bfe09bf104f947`.
- `metrology/cards/fixtures/table_reference.html` governs the table component only.
- `metrology/cards/fixtures/verdict_reference.html` is the earlier reference for the family and
  pair cards. It does **not** govern page hierarchy.

Production differs from `page_reference.html` in exactly four sanctioned ways: all 19 real rows,
both D8 pair cards, real data and provenance, and no review annotations, fixture banner or
"Notes for review". Anything else is drift.

`cards.html` and `snapshot_*.html` are **generated output, never design sources.**

## Next task: T3.5, and exactly where it stands

**The spec exists at `docs/specs/2026-08-18-t3.5-reproduce-design.md`, revision 2 (`30aff44`).**
Jane reviewed revision 1, ruled on the two open questions, and required seven corrections, saying
she would approve the design with those revisions and proceed to the implementation plan.
Revision 2 applies all seven. **She has not yet confirmed revision 2, so confirm before planning.**

Her two rulings, already in the spec: keep both the Python checker and the raw `git status` step,
because the first gives artifact-specific diagnostics and the second an independent
repository-wide backstop; and keep non-canonical local runs non-fatal per D0.9, labelled clearly
as development checks and never canonical evidence.

The seven corrections, so a reader can check the spec against them rather than trusting it:
a clean-worktree preflight before the writers; verification over the whole worktree rather than a
declared artifact list; `$(PYTHON)` throughout; a corrected network model with four
distinguishable outcomes; `if: ${{ always() }}` on the raw worktree step; six tracked paths, five
artifacts plus the README; and a tightened environment banner.

**Three things in the spec that were found by reading the code, not by assuming it.** Repeat that
habit in the plan.

- `fetch.py` already verifies every committed digest through `compare_manifest`, in published
  order. T3.5 uses it rather than writing a second verifier.
- A normal `fetch.py` run already rewrites the **tracked** `derived/aggregates.json` alongside the
  two gitignored derived files, so the reproduce chain is four commands and `aggregates.json` is
  one of the six verified paths.
- `fetch_bytes` catches `HTTPError` and returns `None` for **404 only**. Every other status
  re-raises, and `URLError` and `socket.timeout` are not caught at all, so today a rate limit and
  an outage both surface as an unhandled traceback that reads like a repository defect.

The highest-value control in the plan: **`reproduce` must never pass `--bootstrap`**, asserted
against the Makefile text. A bootstrap inside reproduce would rewrite the manifest it is supposed
to be checked against and turn every mismatch into a silent pass.

`make reproduce` must:

1. Fetch the pinned upstream artifacts and verify their committed digests.
2. Rebuild the untracked derived table and verify its expected checksum.
3. Run `run.py`, regenerating `results.json` and `cards.json` byte for byte.
4. Run `report.py --write`, regenerating `pairs.csv`, `cards.html`, and the README block.
5. Fail if any committed artifact differs.
6. Leave the worktree clean after a successful reproduction.
7. Replace CI's "reproduce must fail" assertion with a real successful reproduction gate.

**The canonical verdict comes only from `ubuntu-24.04`, Python `3.11.15`, and the pinned
dependencies** (D0.9 items 4 to 6). A local run on Python 3.11.4 is useful for development and
**cannot** establish canonical byte identity. Do not report a local green run as reproduction.

T3.5 is the first task that runs `fetch.py` against upstream, and every prior task was forbidden
from doing so. That prohibition ends here by design, but the digests are the safety net: a fetch
that changes a committed digest is a finding, not a fix.

After T3.5 passes canonical CI: T3.6, the cross-repo dashboard handoff. Not before.

## Constraints that were expensive to establish

Do not re-derive these. Each cost at least one review cycle.

- **`q` comes from `discordance_rate_from_counts`, never from a published gap** (D2.5).
- **Separability is Holm over the vector of per-pair minimum attainable p-values** (D2.7).
- **Distinguishable is the observed count** (D3.4, D3.10, PREREG section 5). Its genuine home is
  `primary.resolved_count`, and `run.py` builds `primary.headline.distinguishable_count` from it,
  so the two are identical by construction. The forbidden conflation is with `separable_count`.
- **Three thresholds stay separate**, and the `_basis` strings name which produced each number.
- **`EQUIVALENT` is refused** until Phase 5 supplies TOST fields.
- **Holm never imports `paired`.**
- **No per-pair floor column** (D3.6, D3.8).
- **D4 attaches to observed per-instance quantities only** (D1.11).
- **Every prose figure renders through `render_number`** at a source-qualified path (D3.5).
- **`prose-check` excludes `cards.html`** on purpose; the checker's docstring records why.
- **The finding layer gates all four premises its copy asserts.** `run.py` halts rather than
  emitting a headline that says no pair showed a difference when one did.
- **`cards.json` has no byte check.** `report.py` cannot byte-regenerate it, so `validate_card_set`
  stands in its place. That is why totality there is load-bearing. **T3.5 changes this**: once
  `run.py` regenerates `cards.json` byte for byte under `make reproduce`, the crosswalk gains a
  byte check behind it. Say so in the spec rather than leaving the old limitation recorded.

## Two collisions in this corpus that no value comparison can catch

1. `aggregates:family_size` is **20** (systems on the board); `results:primary.family_size` is
   **19** (adjacent pairs).
2. `results:primary.headline.tie_forced_not_distinguishable_count` is **9 pairs**;
   `results:secondary.non_tied_family.gap_floor` is **9 tasks**, and the family card reads the
   second.

## The one lesson this stretch kept paying for

**When a guard is an enumeration, the defect moves to whatever was not enumerated.** It recurred
about a dozen times across T3.4 at every level: figures pinned and the words around them left
open; sentences pinned and their neighbourhood left open; paragraphs pinned and the paragraph
nobody named left open; one malformed-name example and a fallback tuned to its shape; four leaf
names hardcoded and a fifth field left unguarded; one premise gated of the four the copy asserts.

The antidote every time was to **derive the set from the artifact instead of restating it**, which
is the same habit as this repo's founding one: enumerate from the artifact, never from memory. A
test that restates a field list is enumerating from memory, and the artifact is right there.

Three specific forms worth carrying into T3.5, where the artifact under test is a byte-identical
rebuild:

- A **call-presence** control proves a function ran; only a **data-flow** control proves its result
  was used. A recorder that returns the real value cannot tell the two apart when the real value
  and the wrong value render the same characters.
- **When a comparison normalizes, the normalization is part of the claim.** "Identical after
  normalizing X" is only as strong as the argument that X does not matter. A structural diff
  reported the shipped page identical to its reference while stripping the very block that was
  missing, because the stripping rule was assumed rather than argued.
- **A mutation that trips a pre-existing check** makes an already-working guard look newly
  effective. Every break-it contrast must fail only on the guard it is testing.
