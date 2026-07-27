# llm-eval-metrology Implementation Plan v0.2

Owner: Jane Yeung
Repo name: `llm-eval-metrology` (settled). Inner import path: `metrology` (see open decision 2).
Single source of truth for Claude Code sessions on this repo.

**Supersedes:** eval-metrology-implementation-plan-v0.1.md in full; Phase 3 of agent-bench-implementation-plan-v0.1 (the SWE-bench teardown, which lives here as Experiment 1); and ppi-worked-examples-implementation-plan-v0.1.md in full (Experiments 2 and 3).

**Still owned by the agent-bench plan:** Phase 4 (DCI arm, behind its kill rule), Phase 5 (release and launch ops), and the dashboard finding card, which is a cross-repo dependency blocked until Experiment 1 produces results.

---

## 0. What this repo is

One repo holding a measurement engine and the experiments that validate it. Three outputs, in priority order:

1. **Validation evidence.** Measured operating characteristics for the estimators: does an interval cover the truth at the nominal rate, at what gold-set sizes, and by how much does it beat gold-only and cheap-only. This is what clears the promotion bar.
2. **Public findings.** Analyses that stand on their own as artifacts.
3. **The engine.** Written once, driven by real consumers, later wrapped by the tool repo as the package core.

The credibility claim is procedural: each experiment's analysis plan is committed and pushed to a public remote before that experiment's data exists. Git history is a deliverable.

### Build order, and why

Consumers drive the engine, easiest consumer first:

| Order | Experiment | Exercises | Adds to engine |
|---|---|---|---|
| 1 | SWE-bench Verified teardown | schema, paired binary comparison, verdict card, generator, determinism | McNemar, paired bootstrap, Holm, MDE |
| 2 | SummEval | multi-instrument labels, dense-gold validation, repeated judge runs | PPI, PPI++, certificate, coverage harness, directional validity, TOST, self-consistency and bias probes |
| 3 | LLM-AggreFact | same shape, buyer domain, real cheap instrument | inference caching, prevalence handling |

Experiment 1 is the plumbing shakedown on the simplest data (deterministic gold, no cheap instrument, no model calls). Experiment 2 is the validation flagship: dense expert gold means the truth is known, so the example measures the method rather than illustrating it. Experiment 3 repeats the recipe where clients feel it.

### Deliberately not built yet

Detectors (paraphrase invariance, groundedness checks, schema validity), the calibrate-versus-verdict mode gate, third-party harness adapters, and all delivery layers (browser app, pip packaging, CI gate integration). None of the three experiments consumes them; the rule is no design element gets built before it has a consumer. Section 9 records where each waits.

---

## 1. How to run this with Claude Code

1. One phase per session. Open with: "Read PLAN.md, DECISIONS.md, and the PREREG for the current experiment. We are executing Phase [N]. Confirm the recon facts for this phase before changing anything."
2. Every task ends with its verification run and shown, then a commit carrying the task ID.
3. Append one DECISIONS.md entry per completed phase.
4. Never start an experiment's analysis phase before its pre-registration commit is pushed.

## 2. Global guardrails (paste into every session)

- **No result exists until the analysis produces it.** Do not write a finding, a headline number, or a repo description containing a result before the run. No placeholder figures anywhere outside a clearly fenced mockup or fixture file.
- **No hand-typed numbers.** Every figure in README, report, notebook prose, or card comes from a generator reading a results file. If a number is wanted that no generator emits, extend the generator.
- **Determinism.** All randomness seeded. `make reproduce` regenerates byte-identical result files from committed inputs. Nondeterminism is a bug to fix, not a caveat to write.
- **Report what comes out.** If an estimator underperforms, if coverage misses nominal, if a comparison is uninteresting, that is the finding and it ships. Pre-registration exists so this is not decided later.
- **Pyodide compatibility.** `metrology/` is pure Python with numpy and scipy as the only third-party imports. pandas and anything heavier are permitted in `experiments/` scripts only. CI enforces the import boundary.
- **Anchor is always explicit.** No estimate or certificate runs without a declared anchor instrument. Gold is a role assigned per call, never a hardcoded column.
- **Uniform gold sampling.** Every gold subsample is uniform at random from the pool the cheap instrument scored, unless the pre-registration declares otherwise.
- **Text style.** No em dashes or en dashes in authored text (`grep -rnP "\x{2014}|\x{2013}"` on changed files returns nothing; written with codepoint escapes so this line does not violate its own rule). Numeric ranges written "X to Y". Name is "Jane Yeung".
- **No source-text republication.** Ship derived label tables, checksums, and fetch scripts only.
- **Scope fence.** No graders, no fine-tuning, no UI framework, no optimization over eval signals. A homemade instrument may exist only as a certification test subject, labeled as such (section 9).

## 3. Repo layout

```
metrology/              engine core, pyodide-portable, numpy and scipy only
  schema.py             long-format table, loader, validation, wide-to-long helper
  estimators.py         classical, naive, PPI, PPI++ for means and rates
  paired.py             paired differences, McNemar, bootstrap, clustering
  power.py              MDE, power, gold-set sizing
  multiplicity.py       Holm and friends
  certificate.py        agreement, kappa, AC1, prevalence, rectifier, directional validity
  reporting.py          results files to markdown blocks and card JSON
  cards/                static HTML renderers
    fixtures/           reference HTML (the verdict card mockup) and snapshot baselines
experiments/
  swebench/             Experiment 1: PREREG.md, fetch.py, run.py, results/
  summeval/             Experiment 2
  aggrefact/            Experiment 3
docs/                   recon notes, instruments.md, validation report (generated), DECISIONS.md
tests/
Makefile                test, reproduce, lint, dash-check, import-check
```

## 4. The schema (normative)

Long format, one row per label:

| column | meaning |
|---|---|
| `item_id` | the experimental unit |
| `system` | which system produced the output being labeled |
| `run` | repetition index for repeated measurements |
| `instrument` | who or what produced this label (`human`, `gpt4-judge`, `minicheck-ft5`, `hidden-tests`, ...) |
| `label` | the label value (binary or numeric) |
| `cost` | optional, cost of producing this label |
| `category` | optional, item grouping |

Consequences the code must honor: gold-only estimation is "use rows where instrument equals the declared anchor"; naive estimation is "use rows from one declared cheap instrument, labeled uncorrected"; PPI names both; certificates attach to an instrument against a declared anchor; multiple cheap instruments coexist and can be compared; future detectors are just more instruments emitting binary labels. The loader validates key uniqueness on (`item_id`, `system`, `run`, `instrument`), checks pairing when paired estimators are invoked, and fails loudly when a declared anchor has no rows. A wide-to-long converter ships for user CSVs.

---

## Phase 0: Bootstrap

- [ ] T0.1 Create the repo `llm-eval-metrology`, public, MIT LICENSE, minimal README stating what the repo is and that no results exist yet.
- [ ] T0.2 Python tooling: project config, pinned dependencies, `make test`, `make lint`, `make dash-check`, `make import-check` (fails if `metrology/` imports anything beyond stdlib, numpy, scipy), `make reproduce` (initially a loud-failing no-op).
- [ ] T0.3 CI: tests, lint, dash-check, import-check on push.
- [ ] T0.4 `docs/DECISIONS.md` seeded with the build-order rationale and the schema decision from section 4.
- [ ] T0.5 Push. The public remote must exist before any pre-registration is written.
- [ ] T0.6 `docs/instruments.md` v1: the taxonomy (deterministic and execution-based; encoder judges; LLM judges; human annotation; consistency and uncertainty methods; internal-state probes; decomposition methods; detectors as a future family) and, per family, what the certificate can measure: agreement against an anchor, whether self-consistency is meaningful (sampling-based instruments yes, deterministic ones no), whether directional validity applies, access constraints (internal-state probes need white-box access), and typical failure modes. Extended later as instruments are actually used; v1 is one page.

**Gate:** CI green on the empty repo.

---

## Phase 1: Experiment 1 recon and pre-registration

- [ ] T1.1 Recon to `docs/recon_swebench.md`: where the public per-instance artifacts live, which entries have complete artifacts, the exact instance set and count for the Verified split, file format, license and attribution, and how leaderboard ordering is sourced, including tie representation.
- [ ] T1.2 Write `experiments/swebench/PREREG.md`:
  - **Question.** Among the top N entries by published resolve rate, how many adjacent pairs are statistically distinguishable.
  - **N and adjacency.** Fix N from recon facts. Adjacency by published ordering. Declare tie handling.
  - **Data.** Public per-instance pass/fail artifacts, shared instance set, mapped to the section 4 schema with instrument `hidden-tests` as anchor and sole instrument.
  - **Tests.** Exact McNemar per adjacent pair on discordant pairs; paired bootstrap interval on the resolve-rate difference; Holm across the family; MDE for the benchmark at its instance count.
  - **Coverage rule.** Entries lacking complete artifacts are replaced by the next entry down, with the substitution recorded in results.
  - **Reporting rule.** The count is reported whatever it is, including zero and including all.
  - **Board precision.** The analyzed artifact is the official leaderboard with public per-instance results; vendor self-reported aggregates are out of scope.
  - **Deviation policy.** Departures are appended with reason and timestamp, never edited silently.
- [ ] T1.3 Commit and push before any data is fetched.

**Verification:** the PREREG commit is on the public remote and predates the first data artifact in `git log`.

---

## Phase 2: Engine v0.1

Only what Experiment 1 needs, plus the presentation primitive, which Experiment 1 also needs.

- [ ] T2.1 `schema.py` per section 4: long-format loader, validation, wide-to-long helper.
- [ ] T2.2 `paired.py`: exact McNemar on discordant pairs; paired bootstrap intervals for rate differences; clustered variant for repeated runs per item.
- [ ] T2.3 `power.py`: MDE for paired binary comparisons at given n, power, alpha.
- [ ] T2.4 `multiplicity.py`: Holm, with the test family passed explicitly.
- [ ] T2.5 `reporting.py` v1: results files to markdown blocks and card JSON. No number reaches prose except through this module.
- [ ] T2.6 `cards/` v1: the verdict card renderer, static HTML from card JSON only. Commit the existing mockup as `cards/fixtures/verdict_reference.html`; the renderer targets its structure (verdict stamp, plain-language reading, resolution ruler, discordance strip, what-would-it-take line, progressive disclosure, provenance seal). Snapshot tests: fixed card JSON in, byte-stable HTML out. Fixture files are the one sanctioned home for illustrative numbers and are labeled as such.
- [ ] T2.7 Tests: hand-computed McNemar fixtures including zero-discordance and all-one-sided edges; bootstrap reproducibility under fixed seed; Holm against a worked example; loader long-format failure cases (duplicate keys, missing anchor, broken pairing); card snapshots.

**Verification:** `make test` and `make import-check` green.

---

## Phase 3: Experiment 1 run and outputs

- [ ] T3.1 `fetch.py`: download per-instance artifacts for the pre-registered entries, normalize to the schema, commit the derived table plus checksums, record substitutions.
- [ ] T3.2 `run.py`: execute exactly the pre-registered analysis. Exploratory extras go in a separately labeled appendix and never mix into the headline.
- [ ] T3.3 Outputs: `results/` CSV, a notebook that reads results rather than recomputing, and a README findings block written by `reporting.py`.
- [ ] T3.4 Render the verdict card per adjacent pair through `cards/`, plus one family summary card.
- [ ] T3.5 `make reproduce` regenerates byte-identical results from the committed derived table.
- [ ] T3.6 Cross-repo handoff: the agent-bench dashboard finding card is written against these results and links here. Nothing on that card exists before this phase completes.

**Verification:** every number in the README traces to `results/`; drift check fails otherwise.

---

## Phase 4: Experiment 2 recon and pre-registration

- [ ] T4.1 Recon to `docs/recon_summeval.md`:
  - the human annotation file: exact item count, systems, annotators per item, dimensions, scale. Published counts vary between releases (roughly 1,600 to 1,700 summaries depending on systems included), so record the shape of the file actually downloaded, never a quoted figure.
  - source articles: not needed for this experiment, which operates on labels only. Record that explicitly.
  - cheap labels: locate published per-item judge scores and their coverage. If only correlations were published, flag it; fallback is generating judge labels once with a fixed model and prompt, recorded as a declared deviation.
  - licenses and attribution.
- [ ] T4.2 Write `experiments/summeval/PREREG.md`:
  - **Estimands.** Per-system mean expert score on a named dimension (consistency first, the closest analogue to correctness), and the paired difference between a named system pair, both chosen from recon facts before any estimate exists. The paired difference also carries an equivalence estimand: TOST at a declared band, with the band fixed here and justified from scale semantics (for example a stated fraction of one scale step), never from observed estimates. This gives every Experiment 2 verdict card access to all three stamps: RESOLVED, NOT RESOLVED, EQUIVALENT.
  - **Estimators.** Gold-only, cheap-only (uncorrected), PPI, PPI++, with anchor `human` and the cheap instrument named.
  - **Coverage protocol.** Gold sizes to sweep, replicate count, seed policy, nominal level, uniform sampling.
  - **Success criteria, in advance.** PPI++ empirical coverage within Monte Carlo error of nominal; PPI++ width no wider than gold-only at every gold size; naive coverage reported whatever it is.
  - **Certificate metrics**, including the prevalence condition under which kappa is reported as degenerate.
  - **Directional validity protocol** (Phase 6, 2B).
  - **Judge reliability panel protocol** (Phase 6, 2C). Fix here: the judge model, prompt, temperature, and k repeated runs per item; the order-swapped pairwise subset and its size; the verbosity probe. Metrics: intraclass correlation and per-item variance for self-consistency; order-effect rate for position bias; correlation of judge-minus-human residual with summary length for verbosity. The panel judge must be sampling-based; deterministic instruments are excluded from self-consistency by the taxonomy.
  - **Limitations section drafted now**, filled after results.
- [ ] T4.3 Commit and push before any data is fetched.

---

## Phase 5: Engine v0.2

- [ ] T5.1 `estimators.py`, all taking the table plus explicit `instrument=` and `anchor=`:
  - classical mean and rate with intervals (anchor rows only)
  - naive mean and rate, explicitly labeled uncorrected
  - PPI: anchor-subset mean plus the weighted difference between the cheap mean over the full pool and the cheap mean over the anchor subset, variance combining the pool term and the rectifier term
  - PPI++: the same with a variance-minimizing weight estimated from the labeled subset, which produces the never-worse-than-gold-only behavior. **Do not derive the weight from memory.** Implement from the PPI++ reference and confirm numerically against `ppi_py` in T5.3.
- [ ] T5.2 `certificate.py`: raw agreement, Cohen's kappa, Gwet's AC1, prevalence, measured rectifier (cheap minus anchor bias), uncertainty decomposition (pool versus rectifier share of final interval width), kappa degeneracy flag at the pre-registered prevalence threshold, self-consistency (intraclass correlation and per-item variance across repeated runs; defined only for sampling-based instruments and rejected with a clear error on single-run data), position-bias order-effect rate from order-swapped pairs, and the verbosity probe (correlation of judge-minus-anchor residual with output length). Attaches to any instrument against any declared anchor.
- [ ] T5.3 Tests:
  - synthetic data with truth, cheap bias, and cheap-anchor correlation set by construction: estimators recover truth within tolerance
  - **coverage meta-test:** simulation asserting nominal coverage for PPI++ on synthetic data, so the estimator is validated before it validates anything else
  - numerical agreement with `ppi_py` on one mean case and one rate case
  - degenerate cases: zero anchor rows, anchor equals pool, cheap perfectly correlated, cheap pure noise
  - TOST fixtures: a clearly equivalent case, a clearly different case, and a band-straddling case that must land NOT RESOLVED; self-consistency on synthetic repeated runs with known intraclass correlation, plus the single-run rejection path
- [ ] T5.4 `power.py` extension: gold-set sizing, answering how many anchor labels are needed for a target interval width.
- [ ] T5.5 `paired.py` extension: TOST at a declared band, implemented as two one-sided tests with the interval-inclusion form, runnable on the same paired estimand under gold-only and PPI++ intervals. Verdict mapping: significance and equivalence combine into the three stamps (RESOLVED, NOT RESOLVED, EQUIVALENT), and the card JSON gains the band field.

**Verification:** `make test` green including the coverage meta-test; `make import-check` still green.

---

## Phase 6: Experiment 2 run

### 2A, coverage validation

- [ ] T6.1 Build the long-format table: instrument `human` = per-item mean of expert annotations; the judge as the named cheap instrument; one dimension per run of the experiment.
- [ ] T6.2 Compute the truth: full-anchor mean per system, and the full-anchor paired difference for the pre-registered pair.
- [ ] T6.3 Coverage sweep per the pre-registered grid: per replicate, draw the anchor subset uniformly, compute all four estimators with intervals, record containment of the truth.
- [ ] T6.4 Metrics per gold size: empirical coverage with its own Monte Carlo interval, mean width, and the **gold-label equivalence figure**: how many anchor labels the classical estimator would need to match PPI++ width at that size. That figure converts statistics into labeling budget.
- [ ] T6.5 Repeat the sweep for the paired system difference, the estimand the verdict card renders.
- [ ] T6.6 Figures: coverage versus gold size against the nominal line; width versus gold size for all four estimators; one interval strip at a single gold size.

### 2B, directional validity

- [ ] T6.7 For every system pair, compute the judge's mean difference and the human mean difference on shared items.
- [ ] T6.8 Report the correlation between judge deltas and human deltas, sign-agreement rate, and the pairs where the judge points the wrong way.
- [ ] T6.9 Contrast against the same judge's level agreement, both recorded on the certificate. Level agreement and directional validity are different quantities; A/B verdicts depend on the second.

### 2C, judge reliability panel

- [ ] T6.10 Run the pre-registered judge k times per item at the declared temperature on the declared item set; cache predictions with model name, version, prompt hash, and settings. This inference happens regardless of whether published per-item scores exist for 2A; if they do not, run 1 of this panel serves as the 2A cheap instrument under the declared deviation from T4.1.
- [ ] T6.11 Self-consistency: intraclass correlation and per-item variance across the k runs, recorded on the certificate. This also gives the clustered machinery from T2.2 its first real consumer in this repo.
- [ ] T6.12 Position bias: run the order-swapped pairwise subset per the pre-registered protocol; report the order-effect rate on the certificate.
- [ ] T6.13 Verbosity probe: correlation of judge-minus-human residual with summary length; no new inference required.

---

## Phase 7: Experiment 3, LLM-AggreFact

- [ ] T7.1 Recon to `docs/recon_aggrefact.md`: per-subset item counts, label balance, which subsets carry model attribution, cheap-instrument sizes and hardware fit, expected inference runtime, licenses.
- [ ] T7.2 `experiments/aggrefact/PREREG.md`: estimands (groundedness rate per subset; difference between two named generators where attribution exists), estimators with anchor `human` and the instrument named, gold-simulation protocol, certificate metrics with prevalence-skew handling, success criteria. Commit and push before inference.
- [ ] T7.3 Run the cheap instrument over the selected subsets once; cache predictions with model name, version, and settings recorded.
- [ ] T7.4 Build the table; run the certificate. This is the prevalence-skew case where kappa misleads and AC1 does not, so the degeneracy flag gets its first real exercise.
- [ ] T7.5 Estimate groundedness rates via all four estimators, anchor simulated as a small uniform subsample of the human labels while the instrument scores everything. Report the gold-label equivalence figure.
- [ ] T7.6 Where attribution exists, compute the paired generator difference and render it as a verdict card case.
- [ ] T7.7 Optional, only if it does not delay Phase 8: apply the Experiment 1 treatment to that benchmark's public leaderboard, with its own pre-registration.

---

## Phase 8: Certificate card, report, publication readiness

- [ ] T8.1 `cards/` v2: the certificate card renderer in the same visual language. Rows: agreement, self-consistency where measurable, prevalence, rectifier, directional validity, uncertainty decomposition. Snapshot tests as in T2.6.
- [ ] T8.2 Generate `docs/validation_report.md`: method, pre-registration references, coverage tables, width comparisons, gold-label equivalence, directional validity, limitations (drafted in Phase 4, filled here).
- [ ] T8.3 README written by generator, findings blocks included, each linking its PREREG.
- [ ] T8.4 `make reproduce` from a clean clone: fetch, run, regenerate, verify checksums, all three experiments.
- [ ] T8.5 Repo description and topics; social preview from the coverage figure.
- [ ] T8.6 **Human task (Jane):** read the limitations section adversarially and add what code cannot know, particularly whether the gold labels deserve the name in each dataset. That is the validity question, and it is what the audit sells.

---

## 9. Design outline v2 (product context and implementation mapping)

The product this repo serves, with every element tagged by where it is implemented: **[here]** this repo, **[agent-bench]** the agent-bench plan, **[tool]** the future tool repo, **[waiting]** no consumer yet, so not built.

**Thesis.** LLM output is a probabilistic measurement, and the industry ships decisions on unqualified point estimates. The differentiators are the presentation, the certification of whoever did the grading, and published operating characteristics.

**Architecture: three layers, one loop, one gate.**

- Layer 1, measurement (text to numbers): instruments we never build, only accept and certify. Taxonomy and acceptance surface in `docs/instruments.md`. [here, as acceptance surface only]
- Layer 1b, detectors: label-free checks (paraphrase invariance, permutation invariance, groundedness, schema validity). Probabilistic indicators, not alarms. [waiting; natural Experiment 4: do violations predict human-judged errors; first consumer agent-bench or a client]
- Layer 2, statistical: the engine. [here]
- Layer 3, presentation: the cards. [here as primitives; the tool repo productizes them]
- Calibration loop, statistics back into the instrument. [here via the certificate; item analysis and judge-prompt selection wait for a consumer]
- Calibrate-versus-verdict mode gate, keeping tuning separate from claiming. [tool]
- Boundary contract: the section 4 long-format table, one row per label, each row a mini experiment. [here]

**Product surface, question-first:**

| Question | Machinery | Locus |
|---|---|---|
| Which is better? | paired tests, clustered intervals, Holm, verdict card | here |
| Are they equivalent? | TOST at a declared band | here; pre-registered on the SummEval paired estimand |
| Is my judge reliable? | certificate: agreement, AC1 and kappa with degeneracy flag, rectifier, directional validity, uncertainty decomposition | here |
| | self-consistency and bias probes | here; Experiment 2C judge reliability panel |
| How much data, and how often? | power, MDE, gold-set sizing | here |
| | loop bandwidth (critical drift frequency) | waiting; needs time-series eval data |
| What broke? | detector-to-component attribution | waiting |

**Presentation.** Two cards, one visual language: the verdict card [here, Phase 2 renderer with the mockup as fixture] and the instrument certificate [here, Phase 8]. Principles: question-first entry, verdict in five seconds, statistics behind a click, every number machine-written, screenshot-ready.

**Delivery, thinnest first.** Browser drop-a-CSV app running this engine client-side under pyodide (hence the import guardrail), pip package plus CI gate posting cards as PR comments, third-party adapters, dogfooding chain. All [tool], created after the validation bar clears. Continuous evaluation on operational signals. [waiting; operator territory]

**Trust layer: published operating characteristics.** Coverage validation against known truth, the estimator coverage meta-test, and directional validity. [here] Naive-versus-rigorous audit on campaign data, type I error simulation calibrated to measured variance structure, and graded injections with a localization check. [agent-bench validation program] The organic external comparison, the DCI arm. [agent-bench]

**Scope fences.** No graders (the exemplar bank only ever as a certification test subject, labeled as such), no fine-tuning, no optimization over eval signals, no SaaS, no UI framework here, no new corpora.

**Commercial fit.** The tool quantifies reliability; validity remains human judgment, which is what the audit sells. The free tool feeds the services engine; the certificate and detectors map onto Article 15 evidence and post-market monitoring later.

**Extraction and naming.** agent-bench becomes the engine's fourth consumer after validation, importing `metrology` instead of carrying its own statistics, which also satisfies the extraction gate. An experiment that earns its own front door gets lifted into a standalone repo depending on the engine, when there is a distribution reason, not preemptively. Renames stay cheap until a package is published; the import path is the only stability commitment, and reserving the likely package name on PyPI costs minutes.

## 10. Open decisions

1. Product and pip package name (front-runner `errorbars`; decide whether to reserve now).
2. Inner import path: `metrology` (default) or `llmmetrology` (zero collision risk with the existing PyPI `metrology` distribution if both ever end up installed).
3. Whether PPI ships in the tool's first release or stays validation-only.
4. Whether the validation report gates public promotion or ships as its own finding.
5. N for Experiment 1, and the dimension and system pair for Experiment 2, chosen in their pre-registration phases from recon facts, before any estimate exists.
