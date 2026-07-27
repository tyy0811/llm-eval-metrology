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
   images, which would silently change the environment that defines byte identity.
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
