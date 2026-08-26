PYTHON ?= python3

# Empty locally: a development run must not fail on environment (D0.9). CI passes
# REPRODUCE_MODE=--canonical so the interpreter gate holds where the verdict is made.
REPRODUCE_MODE ?=

.DEFAULT_GOAL := help
.PHONY: help install check-python test lint fmt dash-check import-check prose-check report-check check reproduce

help:
	@echo "targets:"
	@echo "  install       install pinned dependencies from requirements.txt"
	@echo "  check-python  fail fast if \$$(PYTHON) is older than 3.11"
	@echo "  test          run the test suite"
	@echo "  lint          ruff lint and format check"
	@echo "  fmt           apply ruff formatting"
	@echo "  dash-check    authored text contains no em dashes or en dashes"
	@echo "  import-check  metrology/ imports nothing beyond stdlib, numpy, scipy"
	@echo "  prose-check   README and notebook prose numerals are committed corpus renderings"
	@echo "  report-check  README findings block, pairs.csv, and cards.html match the generator"
	@echo "  check         test, lint, dash-check, import-check, prose-check, report-check"
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

prose-check: check-python
	$(PYTHON) scripts/check_prose_numbers.py

report-check: check-python
	$(PYTHON) experiments/swebench/report.py --check

check: test lint dash-check import-check prose-check report-check

# Experiment 1's rebuild (PLAN.md T3.5). T8.4 chains all three experiments.
#
# The preflight comes first because all three writers overwrite tracked artifacts. Without
# it, an uncommitted edit is destroyed by a writer and the check afterwards then reports
# the clean tree that writer just created: the run would erase the evidence of its own
# invalidity and report success.
#
# Never pass --bootstrap here. That rewrites the manifest this run is checked against, so
# every mismatch would become a silent pass and the target would prove only that it can
# overwrite its own expectations.
reproduce: check-python
	$(PYTHON) scripts/check_reproduction.py --preflight $(REPRODUCE_MODE)
	$(PYTHON) experiments/swebench/fetch.py
	$(PYTHON) experiments/swebench/run.py
	$(PYTHON) experiments/swebench/report.py --write
	$(PYTHON) scripts/check_reproduction.py --verify $(REPRODUCE_MODE)
