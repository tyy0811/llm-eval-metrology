# Instruments, v1

An instrument is anything that turns model output into a label: a test suite, a classifier, a
prompted judge, a human annotator. This repo does not build instruments. It accepts them and
certifies them.

That distinction is the scope fence. We take whatever produced the labels as given, measure how it
behaves against a declared anchor, and report what its labels can and cannot support. We do not tune
it, fine-tune it, or optimize anything against it.

Every instrument enters the engine the same way: as an `instrument` value in the long-format table
(see PLAN.md section 4). The anchor is a role assigned per call, never a property of the instrument
itself, so "gold" is always an argument.

This is v1 and covers the families in the taxonomy at one page. It gets extended as instruments are
actually used, and each extension should be driven by a real instrument in a real experiment rather
than by speculation.

## What a certificate can measure

A certificate attaches to one instrument against one declared anchor. The measurable properties:

- **Agreement.** Raw agreement, Cohen's kappa, and Gwet's AC1 against the anchor, plus prevalence.
  Kappa is flagged as degenerate when prevalence crosses a pre-registered threshold, which is the
  case where AC1 stays interpretable and kappa does not.
- **Rectifier.** Measured bias, the cheap instrument's mean minus the anchor's mean on shared items.
  This is the quantity PPI corrects with, so it is reported rather than assumed small.
- **Directional validity.** Whether the instrument ranks two systems the way the anchor does.
  Distinct from agreement: an instrument can be biased in level and still order systems correctly,
  or agree well on levels and still point the wrong way on a close pair. A/B verdicts depend on the
  second property, so both are reported.
- **Self-consistency.** Intraclass correlation and per-item variance across repeated runs. Defined
  only for sampling-based instruments. Requesting it on single-run data is an error, not a warning.
- **Position bias.** Order-effect rate measured on an order-swapped subset, for instruments that see
  more than one candidate at a time.
- **Verbosity sensitivity.** Correlation of the instrument-minus-anchor residual with output length.
- **Uncertainty decomposition.** How much of the final interval width comes from the unlabeled pool
  and how much from the rectifier, which is what tells you whether more gold or more cheap labels
  buys the next increment of precision.

## The families

| Family | Agreement vs anchor | Self-consistency | Directional validity | Access needed | Typical failure modes |
|---|---|---|---|---|---|
| Deterministic and execution-based | Yes | Not meaningful, output is fixed | Yes | Runnable harness and tests | Flaky or environment-dependent tests; tests that underdetermine correctness; gaming by overfitting to the suite |
| Encoder judges | Yes | Not meaningful at fixed weights and greedy decoding | Yes | Model weights or an inference endpoint | Domain shift from the training distribution; threshold set on a different prevalence; silent truncation of long inputs |
| LLM judges | Yes | Yes, and it must be measured | Yes | Sampling API, fixed prompt and settings | Position bias; verbosity preference; self-preference for own-family outputs; prompt and version drift; scale compression at the top |
| Human annotation | Yes, and it is usually the anchor | Yes, across annotators or repeats | Yes | Annotators, guidelines, adjudication | Guideline drift; annotator disagreement treated as noise when it is real ambiguity; fatigue and order effects; anchor that does not deserve the name |
| Consistency and uncertainty methods | Indirect, they score confidence rather than correctness | Yes, by construction | Only after calibration against an anchor | Repeated sampling, sometimes logits | Confidently wrong outputs are consistent; cost scales with sample count; conflates aleatoric with epistemic uncertainty |
| Internal-state probes | Yes, once trained against an anchor | Not meaningful at fixed weights | Yes | White-box access to activations | Probes learn dataset artifacts; do not transfer across model versions; unavailable for hosted models |
| Decomposition methods | Yes, at claim level and aggregated to item level | Depends on the extractor, usually yes | Yes | Extractor plus a per-claim verifier | Extraction errors propagate; claim count changes the aggregate; double counting of restated claims |
| Detectors (future family) | Not yet, no consumer | Depends on the check | Not yet established | Varies by check | Treated as alarms rather than probabilistic indicators |

## Notes per family

**Deterministic and execution-based.** Hidden tests, exact match, schema validators. The natural
anchor for benchmarks that ship them, and the instrument for Experiment 1. Because output is fixed,
self-consistency is undefined by the taxonomy, and the engine rejects the request rather than
returning a meaningless 1.0. Determinism is not correctness: a passing test suite bounds behavior
only as far as the suite reaches.

**Encoder judges.** Fine-tuned classifiers and NLI-style entailment models. Cheap, fast, and the
realistic cheap instrument for Experiment 3. Their weakness is distributional: agreement measured on
one subset does not transfer to another with different prevalence or domain, which is exactly why the
certificate is per-instrument-per-anchor and not a global score.

**LLM judges.** The cheap instrument for Experiment 2. The only family where all three bias probes
apply at once, and the reason the reliability panel exists. Any certificate for a judge is void if
the model version, prompt, or sampling settings change, so those are recorded with the predictions.

**Human annotation.** Usually the anchor, which is why its own reliability matters most. The
certificate can measure inter-annotator consistency, but it cannot tell you whether the annotation
guideline captures the construct you care about. That is validity, it is a human judgment, and it is
the one thing this repo will not automate.

**Consistency and uncertainty methods.** These score how sure a model is, not whether it is right,
so they are only usable as instruments after being calibrated against an anchor. Report them as
confidence signals until that calibration exists.

**Internal-state probes.** Require white-box access, which rules them out for hosted models. Treat a
probe as valid only for the exact model version it was fit on.

**Decomposition methods.** Claim extraction followed by per-claim verification. The certificate can
attach at either level, but the two answer different questions, and the aggregation rule from claim
level to item level is a modeling choice that must be declared.

**Detectors.** Label-free checks such as paraphrase invariance, permutation invariance, groundedness,
and schema validity. Not built, because no experiment consumes them yet. When they arrive they enter
as ordinary instruments emitting binary labels, and the open question is whether violations predict
human-judged errors, which is an experiment rather than an assumption.

## Access constraints, summarized

White-box access is needed for internal-state probes only. Sampling access is needed for LLM judges
and for anything measuring self-consistency. Everything else works from labels alone, which is why
the boundary contract is a table of labels and not a model.
