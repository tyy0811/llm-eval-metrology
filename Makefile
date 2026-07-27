PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help install test lint fmt dash-check import-check check reproduce

help:
	@echo "targets:"
	@echo "  install       install pinned dependencies from requirements.txt"
	@echo "  test          run the test suite"
	@echo "  lint          ruff lint and format check"
	@echo "  fmt           apply ruff formatting"
	@echo "  dash-check    authored text contains no em dashes or en dashes"
	@echo "  import-check  metrology/ imports nothing beyond stdlib, numpy, scipy"
	@echo "  check         test, lint, dash-check, import-check"
	@echo "  reproduce     regenerate committed result files from committed inputs"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

fmt:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

dash-check:
	$(PYTHON) scripts/check_dashes.py

import-check:
	$(PYTHON) scripts/check_imports.py

check: test lint dash-check import-check

# Loud-failing no-op until an experiment produces results (PLAN.md T0.2).
# Phase 3 replaces this with the Experiment 1 regeneration, and Phase 8 chains all three.
reproduce:
	@echo "make reproduce: nothing to reproduce."
	@echo ""
	@echo "No experiment has produced results yet, so there is nothing to regenerate."
	@echo "This target is a deliberate loud failure, not a passing no-op, so that a green"
	@echo "reproduce can never be mistaken for evidence that results are reproducible."
	@echo ""
	@echo "It becomes real in PLAN.md T3.5 (Experiment 1) and T8.4 (all three experiments)."
	@exit 1
