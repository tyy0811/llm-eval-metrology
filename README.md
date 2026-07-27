# llm-eval-metrology

The measurement layer for LLM evaluation: certify your grader, correct its bias with a small gold
set, and report what your benchmark can and cannot resolve.

Owner: Jane Yeung. License: MIT.

## Status

**No results exist yet.** This repo is at Phase 0 (bootstrap). There is no engine code, no data, and
no findings. Nothing in this README is a measured claim about any system, benchmark, or estimator.

When results do exist, every number in this README will be written by a generator reading a results
file, never typed by hand.

## What this repo is

One repo holding a measurement engine and the experiments that validate it, in priority order:

1. **Validation evidence.** Measured operating characteristics for the estimators: does an interval
   cover the truth at the nominal rate, at what gold-set sizes, and by how much does it beat
   gold-only and cheap-only estimation.
2. **Public findings.** Analyses that stand on their own as artifacts.
3. **The engine.** `metrology/`, written once and driven by real consumers.

The credibility claim is procedural: each experiment's analysis plan is committed and pushed here
before that experiment's data exists. Git history is a deliverable, so read `git log` as part of the
evidence.

## Planned experiments

Three consumers drive the engine, easiest first. None has run.

| Order | Experiment | Role |
|---|---|---|
| 1 | SWE-bench Verified teardown | Plumbing shakedown: deterministic gold, no cheap instrument, no model calls |
| 2 | SummEval | Validation flagship: dense expert gold means the truth is known, so it measures the method |
| 3 | LLM-AggreFact | Repeats the recipe in a domain buyers care about, with a real cheap instrument |

Each gets a pre-registration (`experiments/<name>/PREREG.md`) pushed before its data is fetched.

## Layout

```
metrology/     engine core, pyodide-portable, numpy and scipy only
experiments/   one directory per experiment: PREREG.md, fetch.py, run.py, results/
docs/          recon notes, instruments.md, DECISIONS.md, generated validation report
tests/
```

## Development

```
make test           run the test suite
make lint           ruff check and format check
make dash-check     authored text contains no em dashes or en dashes
make import-check   metrology/ imports nothing beyond stdlib, numpy, scipy
make check          all of the above
make reproduce      regenerate result files from committed inputs
```

`make reproduce` fails loudly until an experiment produces results.

The import boundary exists because the engine is meant to run client-side under pyodide later, so
`metrology/` stays pure Python with numpy and scipy as its only third-party imports. Heavier
dependencies such as pandas are permitted in `experiments/` only.

## Reading order for contributors

`PLAN.md` is the single source of truth for scope and sequencing. `docs/DECISIONS.md` records what
was settled and why. `docs/instruments.md` describes which measurement families the certificate can
say something about.

## Attribution

This repo ships derived label tables, checksums, and fetch scripts. It does not republish source
texts from any dataset. Dataset licenses and attribution are recorded per experiment in that
experiment's recon note.
