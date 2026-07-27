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
