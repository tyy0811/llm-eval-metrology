PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help install check-python test lint fmt dash-check import-check check reproduce

help:
	@echo "targets:"
	@echo "  install       install pinned dependencies from requirements.txt"
	@echo "  check-python  fail fast if \$$(PYTHON) is older than 3.11"
	@echo "  test          run the test suite"
	@echo "  lint          ruff lint and format check"
	@echo "  fmt           apply ruff formatting"
	@echo "  dash-check    authored text contains no em dashes or en dashes"
	@echo "  import-check  metrology/ imports nothing beyond stdlib, numpy, scipy"
	@echo "  check         test, lint, dash-check, import-check"
	@echo "  reproduce     regenerate committed result files from committed inputs"
	@echo ""
	@echo "override the interpreter with: make check PYTHON=python3.11"

install:
	$(PYTHON) -m pip install -r requirements.txt

# The engine needs 3.11. On an older interpreter the scripts fail somewhere unhelpful
# (sys.stdlib_module_names is 3.10+, zip(strict=) is 3.10+), so say so here instead.
check-python:
	@$(PYTHON) -c 'import sys; \
	    v = sys.version_info; \
	    ok = v[:2] >= (3, 11); \
	    msg = "make: %s is Python %d.%d.%d, but this repo needs 3.11 or newer.\n       Try: make <target> PYTHON=python3.11" % (sys.executable, v[0], v[1], v[2]); \
	    sys.exit(0 if ok else msg)'

test: check-python
	$(PYTHON) -m pytest

lint: check-python
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

fmt:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

dash-check: check-python
	$(PYTHON) scripts/check_dashes.py

import-check: check-python
	$(PYTHON) scripts/check_imports.py

check: test lint dash-check import-check

# Loud-failing no-op until this target actually regenerates something (PLAN.md T0.2).
# T3.5 wires it to the Experiment 1 rebuild, and T8.4 chains all three experiments.
#
# The explanation below said "no experiment has produced results yet" until T3.2 committed
# Experiment 1's results and made that false. The exit code was never the problem; the reason
# was. A target that fails for a stated reason which is no longer true is the same defect as
# one that passes for no reason.
reproduce:
	@echo "make reproduce: not wired up yet."
	@echo ""
	@echo "Experiment 1 has committed results in experiments/swebench/results/, but this"
	@echo "target does not regenerate them yet, so a green exit here would prove nothing."
	@echo "It stays a deliberate loud failure rather than a passing no-op, because a green"
	@echo "reproduce is meant to be evidence that committed results rebuild from committed"
	@echo "inputs, and nothing rebuilds until the target does the fetch and the run."
	@echo ""
	@echo "It becomes real in PLAN.md T3.5 (Experiment 1) and T8.4 (all three experiments)."
	@exit 1
