# Decisions

Append-only. One entry per completed phase, plus an entry for any decision made mid-phase that a
later session would otherwise have to re-derive. Entries are never edited to change their meaning;
a superseded decision gets a new entry that says so.

Format: what was decided, why, what it commits us to, and whether it is still open.

---

## D0.1 One repo holds the engine and the experiments that validate it

**Date:** 2026-07-27
**Status:** settled

The measurement engine (`metrology/`) and the three validating experiments (`experiments/`) live
together rather than in separate repos.

**Why.** The engine's design risk is building machinery nothing consumes. Co-locating consumers with
the engine makes that failure visible: if a module has no caller in `experiments/`, it should not
exist yet. The rule is that no design element gets built before it has a consumer, and this layout
is what makes the rule checkable rather than aspirational.

**Commits us to.** The engine gets extracted or wrapped later (the tool repo), not now. An
experiment gets lifted into its own repo only when there is a distribution reason.

---

## D0.2 Build order is Experiment 1, then 2, then 3, chosen by consumer difficulty

**Date:** 2026-07-27
**Status:** settled

1. **SWE-bench Verified teardown.** Deterministic gold, one instrument, no cheap instrument, no
   model calls. Exercises schema, paired binary comparison, the verdict card, the generator, and
   determinism. Adds McNemar, paired bootstrap, Holm, and MDE to the engine.
2. **SummEval.** Multi-instrument labels, dense expert gold, repeated judge runs. Adds PPI, PPI++,
   the certificate, the coverage harness, directional validity, TOST, and the self-consistency and
   bias probes.
3. **LLM-AggreFact.** Same shape as 2 in a buyer-relevant domain with a real cheap instrument. Adds
   inference caching and prevalence handling.

**Why.** Experiment 1 is a plumbing shakedown on the simplest possible data, so the first pass
through the engine debugs the plumbing and not the statistics. Experiment 2 is the validation
flagship: dense expert gold means the truth is known, so the run measures the method rather than
illustrating it. Experiment 3 repeats the established recipe where clients feel the problem.

**Commits us to.** The engine grows in two increments (v0.1 in Phase 2, v0.2 in Phase 5) rather than
being written up front. PPI and the certificate are not available until Phase 5, and nothing before
then may assume them.

---

## D0.3 The label table is long format, one row per label

**Date:** 2026-07-27
**Status:** settled, normative

The boundary contract between instruments and the engine is a long-format table with columns
`item_id`, `system`, `run`, `instrument`, `label`, and optional `cost` and `category`. Uniqueness key
is (`item_id`, `system`, `run`, `instrument`).

**Why.** The alternative, one column per instrument, hardcodes the set of instruments into the
schema and makes "which column is gold" a structural property. Long format makes the anchor a role
assigned per call, so the same table serves gold-only estimation, uncorrected cheap estimation, PPI,
and certification without reshaping. Repeated measurements get a first-class home in `run` instead of
suffixed column names, and a future detector is just another `instrument` value emitting binary
labels.

**Commits us to.**

- Gold-only estimation means "rows where `instrument` equals the declared anchor".
- Naive estimation means "rows from one declared cheap instrument", always labeled uncorrected.
- PPI names both instruments explicitly. No call gets an implicit anchor.
- Certificates attach to an instrument against a declared anchor, not to a dataset.
- Multiple cheap instruments coexist in one table and can be compared.
- The loader validates key uniqueness, checks pairing when a paired estimator is invoked, and fails
  loudly when a declared anchor has no rows.
- A wide-to-long converter ships for user CSVs, because users will arrive with the other shape.

---

## D0.4 The engine's import boundary is stdlib, numpy, and scipy, enforced in CI

**Date:** 2026-07-27
**Status:** settled

`metrology/` may import the standard library, numpy, scipy, and itself. `make import-check` fails
otherwise, and CI runs it on every push. Heavier dependencies, pandas included, are permitted only in
`experiments/` scripts.

**Why.** The thinnest planned delivery layer is a browser drop-a-CSV app running this engine
client-side under pyodide. That constraint is cheap to hold from the start and expensive to
retrofit, because the violation that breaks it is usually a convenience import buried in a helper.

**Implementation note.** The check parses each module with `ast` instead of importing it, so it works
on partially written modules and needs no third-party package installed to run.

---

## D0.5 Determinism is a gate, and `make reproduce` fails loudly until it can pass honestly

**Date:** 2026-07-27
**Status:** settled

All randomness is seeded, and `make reproduce` must regenerate byte-identical result files from
committed inputs. At Phase 0 there are no results, so the target exits nonzero with an explanation.

**Why.** A green `make reproduce` is meant to be evidence. A no-op that exits 0 would produce that
evidence while proving nothing, and the failure mode is silent: nobody notices a check that always
passes. CI asserts the nonzero exit, and a test asserts it too, so the guarantee cannot rot.

**Commits us to.** Nondeterminism is a bug to fix, not a caveat to write. The target becomes real in
T3.5 for Experiment 1 and T8.4 for all three.

**Dependency pins.** `requirements.txt` pins exact versions (recorded from the authoring environment
on 2026-07-27: Python 3.11.4, numpy 1.26.4, scipy 1.17.1, pytest 8.2.0, ruff 0.15.8) and CI installs
from it. Bumping any pin requires re-running every experiment's reproduce target and recording the
outcome here. A test asserts every requirement uses `==`.

---

## D0.6 Text style is enforced by a Python checker, not by `grep -P`

**Date:** 2026-07-27
**Status:** settled, deviation from PLAN.md recorded

The guardrail forbids em dashes and en dashes in authored text and writes numeric ranges as
"X to Y". PLAN.md section 2 states the check as `grep -rnP` over changed files. It is implemented as
`scripts/check_dashes.py` instead.

**Why the deviation.** Two reasons. `grep -P` is not available on every platform this repo is edited
on, so the plan's form is not portable. And a changed-files check can be defeated by committing a
violation in a file the diff does not touch, whereas the whole-tree check cannot.

**Related fix.** PLAN.md section 2 originally quoted the forbidden characters literally, which made
the plan violate its own rule and would have failed `make dash-check` on PLAN.md itself. That line
now states the pattern with codepoint escapes. The checker and its tests construct the characters
with `chr()` for the same reason.

---

## D0.7 Names are provisional: import path `metrology`, distribution `llm-eval-metrology`

**Date:** 2026-07-27
**Status:** open, tracked as PLAN.md open decisions 1 and 2

The engine is importable as `metrology` and the project metadata carries the provisional
distribution name `llm-eval-metrology` at version 0.0.0. Nothing is reserved on PyPI.

**Why provisional.** Open decision 2 weighs `metrology` against `llmmetrology`, which has zero
collision risk with the existing PyPI `metrology` distribution if both are ever installed together.
Open decision 1 (product and package name, front-runner `errorbars`) is unresolved.

**Commits us to nothing yet.** Renames stay cheap until a package is published. The import path is
the only stability commitment, so this decision must close before any release, and it should close
before agent-bench starts importing the engine as its fourth consumer.

---

## D0.8 Phase 0 complete

**Date:** 2026-07-27
**Status:** settled

Bootstrap delivered: public repo with MIT license, minimal README stating that no results exist,
PLAN.md committed as the single source of truth, project config with exact pins, the five make
targets, CI running all four checks plus the reproduce-fails assertion on push, this file, and
`docs/instruments.md` v1.

**Gate:** CI green on the bootstrap commit.

**What is deliberately absent.** No engine modules, no experiment directories, no data, no results.
`metrology/` holds only a package docstring and a version. Experiment directories are created in
the phase that pre-registers them, so an empty `experiments/swebench/` cannot be mistaken for work
in progress.

**Verified.** CI run 30264160697 succeeded on `main` at commit 6721989, all ten steps including the
assertion that `make reproduce` still fails. Confirmed independently by Jane.

---

## D0.9 Canonical reproduction environment

**Date:** 2026-07-27
**Status:** settled for the environment, normative for the serialization rules
**Refines:** D0.5, which pinned dependencies and named the authoring machine as the reference

Exact dependency pins are necessary for byte identity and not sufficient for it. Operating system,
wheel provenance, runner image updates, Python patch version, output formatting, timestamps, and
iteration order can each break byte identity while every pin in `requirements.txt` is satisfied.
Pinning the interpreter alone would have addressed one of those seven.

The canonical reproduction environment is therefore defined as a whole:

1. **Runner image `ubuntu-24.04`**, not `ubuntu-latest`. The `latest` label moves when GitHub rolls
   images, which would silently change the environment that defines byte identity. This pins the
   image line and not the image: the first run under this policy reported Ubuntu 24.04.4, and point
   releases will arrive inside the same label. Escalating to a digest-pinned container is the option
   if that ever proves to matter, and item 4 is what would surface it as a loud failure rather than
   a wrong number.
2. **Python 3.11.15**, exact patch. A bare `"3.11"` resolves to whatever the tool cache holds.
3. **The exact pins in `requirements.txt`**, unchanged.
4. **Checksums generated in CI are canonical.** A local run on macOS or another patch version is a
   convenience for development, not evidence. A local mismatch is not by itself a defect; a CI
   mismatch is.
5. **Deterministic serialization.** Result writers must produce stable bytes: explicit sort order on
   the schema key columns rather than dict or set iteration order, fixed float formatting rather
   than repr, sorted keys in JSON, LF line endings, and a trailing newline.
6. **No timestamps, and no other ambient state, in result files.** No wall-clock times, durations,
   hostnames, absolute paths, library versions embedded inline, or run identifiers. Provenance of
   that kind belongs in the CI log and in the card's provenance seal, not in the bytes being
   checksummed. Seeds are recorded in results because they are inputs, not ambient state.

**What is enforced now.** Items 1 to 3 are in `.github/workflows/ci.yml` as of this commit, along
with the action version updates that removed the Node 20 deprecation. CI now also records the OS,
the interpreter, and the full resolved dependency set on every run.

**What is not yet code.** Items 4 to 6 cannot be implemented at Phase 0 because no result file and
no serializer exist. They are normative for the modules that will write results: `reporting.py` in
Phase 2, then `fetch.py` and `run.py` in Phase 3. T3.5, the first phase where `make reproduce`
regenerates anything, is the deadline for all three and the point at which committed checksums
first mean something.

**Why this is worth the pedantry.** The claim this repo sells is that its numbers regenerate. A
reproduction gate that passes because nothing varied on one machine, and fails for the first
external person who runs it, is worse than no gate, because it was believed.

---

## D0.10 D0.9 item 1 was edited in place, which this file forbids

**Date:** 2026-07-27
**Status:** settled, procedural correction

Commit `b429400` edited the text of D0.9 item 1 to soften an overclaim: the original wording implied
that pinning `ubuntu-24.04` fixes the environment, when it fixes the image line while point releases
continue to arrive inside the label. The correction was right. The method was wrong.

The header of this file states that entries are never edited to change their meaning and that a
superseded decision gets a new entry saying so. Editing D0.9 in place violated that rule, and the
fact that git history preserves the change does not make the file itself honest to a reader who does
not check the log.

**What should have happened.** A new entry, D0.10, recording the correction and pointing at D0.9.

**Resolution.** This entry is that acknowledgement. The edited D0.9 text stands rather than being
reverted, because a second rewrite would compound the original error. Anyone auditing D0.9 should
read it together with this entry and with `b429400`.

**Rule reaffirmed.** Corrections to a settled entry are appended as new entries. This applies with
more force to `experiments/*/PREREG.md`, where the same discipline is the entire credibility claim,
and where the freeze is stricter: a pre-registration body is not amended at all, and corrections go
under its Deviations heading with a UTC timestamp. See D1 and D2 in
`experiments/swebench/PREREG.md`, which is how the correction of an error in a frozen document is
supposed to look.

---

## D1.1 Phase 1 complete, and Experiment 1's primary is settled analytically

**Date:** 2026-07-27
**Status:** settled

Recon (`docs/recon_swebench.md`) and pre-registration (`experiments/swebench/PREREG.md`) are
committed and pushed, after structural recon of upstream but before any committed derived-data
artifact or per-instance comparison.

**The finding that changed the experiment.** Review of the registered design established that the
primary count is not merely likely to be zero but is forced to be zero. For an adjacent pair whose
resolved counts differ by `g`, the smallest attainable exact two-sided McNemar p-value is
`min(1, 2^(1 - g))`. The largest gap in the registered top 20 is 7 instances, so no raw p-value can
fall below 0.015625, while Holm requires the smallest in the family to clear 0.05/19 = 0.002631579,
or 0.05/10 = 0.005 in the secondary. Neither family can reject at any per-instance overlap.

Recorded as deviations D1, D2, and D3 in the pre-registration rather than as edits to its body.

**Consequence.** Experiment 1 still runs in full. The data remain necessary for discordance counts,
paired bootstrap intervals, MDE, and both card types. Only the distinguishable-pair count is settled
in advance, and the finding is stronger for it: at 500 instances the benchmark cannot separate any
adjacent pair in its own published top 20, and that is decidable without running the comparison.

**Numbering note.** Entries here are D<phase>.<n>. Deviations inside a pre-registration are numbered
D1, D2, D3 within that document. The two sequences are separate.

---

## D1.2 Upstream artifacts: seek permission, and do not redistribute by default

**Date:** 2026-07-27
**Status:** settled by Jane; the permission request itself is open
**Supersedes:** the artifact-committing half of PLAN.md T3.1

`SWE-bench/experiments`, the source of Experiment 1's per-instance artifacts, carries no explicit
license. GitHub documents that absent a license, default copyright rules apply, and that public
visibility principally grants the right to view and fork rather than broader reuse. Recon originally
concluded this did not block the experiment, which was a legal conclusion it was not positioned to
draw. That conclusion is withdrawn.

**Decision.**

1. Seek explicit permission from the upstream maintainers now.
2. Unless written permission exists by T3.1, commit **only** the pinned fetch script, the upstream
   digests, and the expected checksums. The derived label table is generated and left untracked.
3. The residual redistribution risk is **not** accepted by default. Silence from upstream means the
   restricted option, not the permissive one.

**What this changes in the plan.** PLAN.md T3.1 says to commit the derived table plus checksums.
Under the default branch of this decision the derived table is not committed, so:

- `.gitignore` must exclude the derived table.
- `make reproduce` verifies regenerated bytes against **committed expected checksums** rather than
  diffing against a committed table. This is a slightly stronger reproduction claim, since it forces
  a real fetch and rebuild rather than a comparison against a stored copy.
- A clean clone must be able to regenerate the table from the pinned upstream, which makes the
  pinning in `docs/recon_swebench.md` load-bearing rather than documentary.
- Experiment 1's results files, which are our own computed outputs and not upstream content, are
  committed as normal.

**If permission is granted**, the derived table may be committed and this entry gets a successor
recording the grant, its scope, and its date.

---

## D1.3 The verdict card reference is built and approved before any renderer exists

**Date:** 2026-07-27
**Status:** settled by Jane
**Refines:** PLAN.md T2.6

**Recorded fact:** no pre-existing verdict card mockup was available. PLAN.md T2.6 says to commit
"the existing mockup" as `metrology/cards/fixtures/verdict_reference.html`. No such file existed in
this repo or was supplied, so the premise of that instruction does not hold.

**Decision.** Phase 2 may begin with T2.1 through T2.5. Before T2.6:

1. Build a standalone HTML reference from the seven structural elements named in T2.6: the verdict
   stamp, the plain-language reading, the resolution ruler, the discordance strip, the
   what-would-it-take line, progressive disclosure, and the provenance seal.
2. Jane approves it.
3. Commit it **before** any renderer implementation exists.

**Why the ordering matters.** If the renderer were written first, its output would become the
snapshot baseline, and the fixture would record whatever the renderer happened to produce. The
tests would then be self-consistent and prove nothing about whether the card communicates what it
should. Building and approving the reference first means the renderer and its snapshots target an
independently approved artifact.

Fixture files remain the one sanctioned home for illustrative numbers, and are labeled as such.

---

## D1.4 Ship a pipeline, not a database: fetch-and-derive is the design, not the fallback

**Date:** 2026-07-27
**Status:** settled by Jane
**Supersedes:** D1.2, whose framing made fetch-only a contingency triggered by upstream silence

D1.2 treated committing the derived table as the preferred outcome and fetch-only as the fallback if
permission did not arrive. That had the dependency backwards. The licensing question exists only
because the plan proposed committing a derived table. Remove that and the question dissolves.

**Decision.** The repo distributes a **deterministic fetch-and-derive pipeline** plus committed
checksums of what it must produce. It never redistributes upstream per-instance data.

Committed:

- the fetch and derive scripts, pinned to exact upstream revisions
- digests of the upstream files consumed
- expected checksums of the derived table
- **de minimis aggregates**: per-entry resolve totals and discordance counts, enough for a reader to
  sanity-check the headline without holding the table
- our own computed results, which are not upstream content

Not committed: the derived per-instance table itself, which is generated and untracked.

**Why this is the right shape.** What ships is a program that reads public data, not a republication
of someone else's database. That is the standard pattern for benchmark analysis, and it sidesteps
both the missing upstream LICENSE and the EU sui generis database right without touching the
analysis at all.

**The cost, stated rather than hidden.** Reproduction now requires network access and continued
upstream availability. If upstream changes, the checksum mismatch reports it loudly instead of
letting a silently different table through. That trade is recorded in the README, because a
reproduction story with a network dependency should not be discovered by the first person who tries
it on a plane.

**The generalized criterion.** The test for a data source is not "does it raise no licensing
question", because nothing passes that. It is **"does it raise only licensing questions I can design
around without compromising the analysis"**. Experiment 2 is the same shape and already passes:
SummEval ships annotations without the source news articles, and the plan needs labels only.
Experiment 1 passes under this pattern. A source would fail only if the analysis genuinely required
redistributing protected content, and that is the moment to change sources, not to accept the risk.

**The permission request is still filed**, but it is now a nice-to-have rather than a gate. Nothing
blocks T3.1 on a reply.

---

## D1.5 `docs/PROVENANCE.md` is a standing register, not a one-off note

**Date:** 2026-07-27
**Status:** settled by Jane

Every external source gets a row recording license status, what is redistributed versus fetched,
attribution, and any open question with its date and channel.

**Why it belongs in this repo specifically.** For a project whose product claim is measurement
provenance, the register converts a liability into a demonstration of the discipline being sold. It
is also directly reusable as evidence in a conformity engagement, which is where the certificate and
detectors are meant to land later.

It costs about a page per experiment and is updated in the recon phase, when the facts are fresh,
rather than reconstructed at publication time.

---

## D1.6 An analytically forced result is led with, never buried under a p-value table

**Date:** 2026-07-27
**Status:** settled by Jane

Experiment 1's primary is forced, not observed (PREREG deviations D1, D3, D6). Any write-up,
findings block, or card set therefore **states the analytic result first** and presents the computed
p-values as confirmation of an already-settled conclusion.

**Why the ordering is not cosmetic.** A reader who works out the bound independently after being
shown a table of non-significant results concludes that arithmetic was dressed up as an experiment,
and says so publicly. Led with, the same content is a stronger claim than an empirical null: the
board's adjacent entries disagree on too few instances for any test at this correction level to
fire, so the leaderboard cannot rank its own top entries no matter which statistics are applied.

**Binding form.** The headline is the resolving-power claim. The p-value table is an appendix or a
disclosure, never the lead. This applies to the README findings block, the family summary card, and
any external write-up.

---

## D1.7 Card v1 gains a discordance ruler and a real provenance block

**Date:** 2026-07-27
**Status:** settled by Jane
**Refines:** PLAN.md T2.6 and D1.3, and must land in the reference HTML before the renderer exists

Two changes to the seven structural elements, decided before the reference HTML is built rather than
retrofitted after.

**1. For binary paired comparisons the resolution ruler is expressed in discordance, not in abstract
effect size.** Observed disagreements, the split, and what the split would have to be for the test
to fire, on one axis. "43 disagreements, split 25 to 18" is legible to a reader who will never read
an MDE, and it puts the instrument's limit and the observed data in the same units.

**Implementation warning, found by doing the arithmetic.** The ruler must show the requirement **at
the observed discordance total**, not the absolute floor. These differ by a lot. Illustratively, at
43 disagreements split 25 to 18, the net edge is 7 and p is 0.36; to reach the Holm threshold at
that discordance the net edge would need to be **21**, a split of 11 to 32. The absolute floor of 9
or 10 net disagreements is reachable only when every disagreement runs one way, which is
`n_d = g`. Publishing the floor as "what it would take" at a realistic discordance understates the
requirement roughly threefold. Both numbers may appear; only the at-observed one may be labeled as
the requirement.

**2. The card JSON gains a provenance block with real fields**, because D4 created a standing
disclosure obligation: source, pinned upstream revision, fetch date, and the named deviations that
qualify the result. This lands in T2.5 and T2.6, not in Phase 8, since a card rendered before the
block exists would need reissuing.

---

## D1.8 Every number in prose must be a member of the committed aggregates

**Date:** 2026-07-27
**Status:** settled by Jane
**Strengthens:** the PLAN.md section 2 guardrail on hand-typed numbers

The plan's rule is that every figure in prose comes from a generator reading a results file, which
is verified by tracing. The stronger and mechanically checkable form:

> Every number appearing in any prose output must appear in the committed aggregates file.

That is set membership, not provenance tracing, so a checker can enforce it without understanding
how any number was produced. It composes with D1.4, under which the committed aggregates are exactly
the de minimis figures (per-entry resolve totals, discordance counts) plus our computed results,
while the derived per-instance table stays untracked.

`reporting.py` is therefore designed backwards from the card JSON and the findings block: the
aggregates file is the contract, and anything prose needs that the aggregates lack is a reason to
extend the generator, never a reason to type a number.

---

## D1.9 Family cards carry a `family_finding`, not a `verdict`

**Date:** 2026-07-27
**Status:** settled by Jane, approved before incorporation into the reference HTML
**Refines:** PLAN.md T2.5 and T2.6

Three options were on the table for how a family summary card states its result. Reusing
`NOT RESOLVED` was rejected as misleading, because it describes one hypothesis rather than the
resolving power of a family. Adding a fourth verdict such as `UNDERPOWERED` was rejected because it
pollutes a taxonomy that has to stay stable across three experiments.

**Decision: a dedicated family finding with its own type.**

`verdict` answers a question about two systems. Resolving power answers whether the instrument can
answer that question at all. Those are different types, and a fourth enum value would overload one
field with two semantics, which breaks the first time a family card needs to say something with no
pairwise analogue.

### The contract

- `verdict` is **restricted to pair cards** and takes exactly `RESOLVED`, `NOT RESOLVED`, or
  `EQUIVALENT`.
- Family cards carry `family_finding` and **no** `verdict`.
- The focal component of a family card is a **finding banner**, not a verdict stamp. Same visual
  language, same provenance block.

`family_finding` is **structured, not a rendered string**, because it recurs in Experiments 2 and 3
and those should reuse the contract rather than fork it:

```json
{
  "card_kind": "family_summary",
  "family_finding": {
    "claim_type": "resolving_power",
    "headline": { "separable_count": 0, "family_size": 19, "unit": "adjacent_pairs" },
    "criterion": {
      "statistic": "exact_mcnemar_two_sided_doubling",
      "correction": "holm", "alpha": 0.05, "threshold": 0.002631579
    },
    "limit": {
      "best_case_family_floor": 10,
      "floor_label": "best-case family floor",
      "observed_extreme": 7,
      "observed_extreme_label": "largest registered adjacent gap",
      "inference": "every adjacent gap sits below the floor, so no pair can separate at any discordance configuration"
    },
    "scope": { "comparisons": "adjacent pairs only", "excludes": "non-adjacent comparisons" },
    "conditionality": ["integrity gate 3 passes", "no coverage-rule substitution occurs"],
    "disclosure": { "applies_to_headline": [], "applies_to_secondary": ["D4 harness comparability"] },
    "progressive_disclosure": { "secondary_family_floor": 9, "secondary_family_size": 10 }
  }
}
```

### Card face requirements

1. **Define "separable" in one clause on the face.** It is not `NOT RESOLVED` with a different
   accent. `NOT RESOLVED` means the test did not reject. **Not separable means rejection was
   unreachable regardless of the data**, which is the stronger claim, and a different root word is
   what stops a reader collapsing the two.
2. **The floor is labeled "best-case family floor"**, never the at-observed-discordance requirement.
   Those differ by a lot (D1.7), and mislabeling understates the requirement roughly threefold.
3. **The inference is rendered, not left to the reader.** "Floor 10, largest gap 7" makes the reader
   perform the step that carries the whole argument. The `inference` field is displayed between the
   two numbers.
4. **A scope line sits under the banner.** "0 of 19 adjacent pairs separable" is correctly scoped
   but will be quoted as "the top 20 are statistically indistinguishable", which is not the claim.
   Rank 1 versus rank 20 may well be separable. The line states that non-adjacent comparisons are
   out of scope, and it costs nothing to pre-empt a misreading that would otherwise attach
   permanently.
5. **The secondary floor of 9 sits under progressive disclosure**, not on the face.
6. Pair cards keep the observed-discordance ruler from D1.7.

### Schema tests

- A family card containing `verdict` is rejected.
- A pair card missing `verdict` is rejected.
- **No value anywhere inside `family_finding` may equal `RESOLVED`, `NOT RESOLVED`, or
  `EQUIVALENT`**, so the distinction cannot leak back in through a string. This is the constraint
  that actually holds the line, since the field-level split is easy to respect while the semantics
  are quietly reintroduced in prose.

---

## D1.10 Nineteen full pair cards are not rendered

**Date:** 2026-07-27
**Status:** settled
**Supersedes:** the per-pair half of PLAN.md T3.4

T3.4 says to render a verdict card per adjacent pair plus one family summary card. Nineteen cards
reading `NOT RESOLVED` teach a reader nothing, and repeating the at-observed ruler nineteen times
spends its complexity where it earns least.

**Decision.** The Experiment 1 card set is:

- one family summary card per D1.9,
- a compact nineteen-row table of gap, best-case floor, and observed discordance,
- full pair cards for one or two illustrative cases only, chosen to show the ruler doing real work.

The nineteen-row table still reports every pair, so nothing is hidden and the reporting rule in the
pre-registration is satisfied. The ruler keeps its complexity where it communicates.

Reversible: if the illustrative cases turn out to under-serve the finding, rendering the full set
costs one generator run.

---

## D1.11 The headline is provenance-free, and D4's caveat attaches only to the secondary

**Date:** 2026-07-27
**Status:** settled
**Cross-reference:** deviation D7 in `experiments/swebench/PREREG.md`

Experiment 1's headline derives from published resolve rates alone: the gap vector follows from the
rates, the floor from the declared convention, the threshold from alpha and family size. Verified by
computing the separable count from the pinned leaderboard file with no per-instance data: 0 of 19.

**Why this matters beyond Experiment 1.** It means the strongest claim this repo publishes first is
one that any reader can re-derive from a public file with a calculator, with no fetch, no derived
table, and no licensing question. That is the ideal shape for a project whose credibility argument
is procedural, and it is worth looking for in Experiments 2 and 3: the part of a finding that needs
no privileged data is the part that survives every objection to the data.

**Consequence for disclosure.** The D4 harness-comparability caveat attaches to the discordance
counts, intervals, and MDE, which read per-instance data. It does **not** attach to the headline.
Attaching it there would invite the inference that the headline is contingent on it. The write-up
says instead that the per-instance work characterizes the finding but cannot overturn it.

---

## D1.12 The two illustrative pair cards are chosen by a registered rule, not after the fact

**Date:** 2026-07-27
**Status:** settled by Jane
**Closes:** the choice D1.10 left open
**Cross-reference:** deviation D8 in `experiments/swebench/PREREG.md`, which is the binding record

D1.10 settled that only one or two pairs get full cards but not which. That gap mattered: selecting
the illustrative pairs after seeing discordance would be post-hoc selection presented as
illustration, which is the same failure the pre-registration exists to prevent, just relocated from
the analysis to the presentation.

**The rule, registered before any per-instance data exists:** render the first published adjacent
pair, and the adjacent pair with the largest published resolved-count gap, breaking any
maximum-gap tie by earliest published rank.

It currently selects ranks 1 and 2 at gap 0, and ranks 3 and 4 at gap 7, the unique maximum. The
two carry the halves of the finding that neither shows alone: gap 0 shows that equal aggregate
counts can hide substantial disagreement, and gap 7 shows that the strongest edge on the board still
cannot reach the floor.

**Why the rule and not just the names.** A named selection is unfalsifiable if the set changes. A
rule reapplies mechanically under substitution, and it is checkable by a reader against the
published file.

**The general principle, since it recurs.** Presentation choices that select which cases a reader
sees are analysis choices wearing different clothes, and belong in the pre-registration on the same
terms. Experiments 2 and 3 should register their illustrative selections the same way rather than
picking the most striking example once results exist.

---

## D2.1 Schema contracts settled during the T2.1 corrective pass

**Date:** 2026-07-28
**Status:** settled
**Refines:** the section 4 schema in PLAN.md, which says "optional" without saying optional per table or per row

Review of T2.1 found four boundary defects and one underspecified contract. The defects were
fixed with regression tests; the contract needed a decision, recorded here.

### Optional columns may be partial, with explicit missing values

The first implementation required `cost` and `category` on every row or on none. That is stricter
than the plan and would obstruct Experiment 2, which puts a costed judge and an uncosted human
anchor in one table: an all-or-none rule forces the caller to invent a cost for rows where the
concept does not apply, and an invented zero is indistinguishable from a real one.

**Decision.** Partial presence is legal. An absent `cost` is `nan` and an absent `category` is the
empty string, exported as `MISSING_CATEGORY`. Both are distinguishable from a real value, which is
the property that matters: `nan` propagates loudly through arithmetic instead of silently biasing a
cost total downward.

`label` is deliberately not given the same treatment. A missing label is not a label, and the
long format already expresses absence by having no row at all. That is why `wide_to_long` skips
blank cells rather than emitting `nan` labels.

### A LabelTable is valid because it exists

Validation lives in `__post_init__`, not in `from_rows`, because `from_rows` is not the only door:
`_take` constructs instances directly and so can any caller. Construction now validates column
lengths, label finiteness, blank identifiers, and key uniqueness however the instance was built.

Arrays are copied on construction and marked read-only. `frozen=True` protects only the attribute
binding, so without this a caller could rewrite a validated label to `nan` in place and every
downstream estimate would inherit it. This was confirmed reachable before the fix.

### Identifiers must be real, and runs must be exact integers

`str(None)` is `"None"`, a plausible-looking identifier that would silently merge every missing id
into one bucket, so null and blank key fields are rejected. `int()` truncates 1.5 to 1 and coerces
`True` to 1, either of which merges two distinct runs and corrupts the uniqueness key without any
error surfacing, so `run` requires an exact, finite, nonnegative integer. Integral floats are
accepted because CSV parsing produces them.

### `paired` refuses four comparisons it used to accept

A system paired with itself, a pair where neither system was scored by the named instrument, a
pair where one side has no rows under it, and an undeclared choice of run. The last one is the
subtle one: system A at run 0 could align against system B at run 1, producing a cross-run
comparison nobody asked for. `paired` now takes an optional `run=`, required whenever the scoped
rows span more than one run.

### Interpreter version is guarded, not assumed

`metrology` raises on import below Python 3.11, and `make check-python` gates every check target
with a message naming the interpreter and the fix. The engine uses `zip(strict=)` and the checker
scripts use `sys.stdlib_module_names`, both 3.10 or newer, so an older interpreter otherwise fails
somewhere unhelpful. Verified against the 3.9.4 interpreter present on the development machine.

---

## D2.2 Unequal run sets are rejected unless declared

**Date:** 2026-07-28
**Status:** settled

`clustered_bootstrap_difference` weights items equally, each contributing the mean of its own
runs. That leaves a case the first implementation accepted silently: system A measured on runs
{0, 1} against system B measured only on run {0}.

**Decision.** Reject by default. `allow_unequal_runs=True` declares the asymmetry deliberate.

**Why not simply allow it.** The per-item means are then averages over different numbers of
measurements, so the paired difference carries a per-item noise asymmetry that equal-weight
clustering does not model. More practically, that pattern is almost always missing data rather
than a design choice, and the failure is silent: the estimate looks fine and the interval is
quietly too narrow on the side measured more often.

**Why not simply forbid it.** A genuine design can measure a cheap instrument many times and an
expensive anchor once. That is the Experiment 2 shape, so the capability has a real consumer and
refusing outright would force a caller to pre-average and lose the clustering.

This follows the pattern already set by `LabelTable.paired(run=...)`: refuse the ambiguous case,
provide an explicit way to say what was meant.

---

## D2.3 Validation lives at the type boundary, and one validator owns integer inputs

**Date:** 2026-07-28
**Status:** settled

Two review passes found the same shape of defect twice: a validated-looking object that was
never validated, and a numeric input that silently coerced. The rules that follow:

**Every dataclass carrying data enforces its invariant in `__post_init__`.** `LabelTable` got
this in the T2.1 corrective pass; `PairedLabels` now has it too. Unequal label lengths were
broadcasting inside `mcnemar_exact` and the bootstrap, producing a plausible wrong discordance
count rather than an error. Arrays are copied and marked read-only, lengths must match, items
must be unique, labels must be finite, and the two systems must differ.

**One validator owns exact-integer inputs**, used for discordance counts, gaps, `max_gap`,
`n_resamples`, and seeds. It rejects bools, fractional floats, and non-finite values.

The `nan` case is why this matters more than it sounds. `p_value_floor(nan)` previously returned
1.0, which reads as "not separable" and would have turned missing data into a confident negative
finding, the exact failure this repo exists to prevent.

**Every resampling entry point requires a seed.** `clustered_bootstrap_difference` accepted
`seed=None`, and numpy then draws ambient entropy, which breaks the determinism gate in D0.5
without any visible symptom.
