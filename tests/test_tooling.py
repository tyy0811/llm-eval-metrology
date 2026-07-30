"""Phase 0 tooling guarantees: the declared make targets exist, dependencies are pinned
exactly, and `make reproduce` fails loudly rather than passing as a no-op.

A passing `make reproduce` must never be achievable while the target does not actually
regenerate anything, because a green reproduce is meant to be evidence that committed
results rebuild from committed inputs. It becomes real in PLAN.md T3.5.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RESULTS_DIR = REPO_ROOT / "experiments" / "swebench" / "results"

REQUIRED_TARGETS = ("test", "lint", "dash-check", "import-check", "reproduce")


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_makefile_declares_required_target(target: str) -> None:
    text = MAKEFILE.read_text(encoding="utf-8")

    assert f"\n{target}:" in text, f"PLAN.md T0.2 requires a '{target}' target"


def test_required_targets_are_phony() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    phony_line = next(line for line in text.splitlines() if line.startswith(".PHONY:"))

    for target in REQUIRED_TARGETS:
        assert target in phony_line.split()


def test_dependencies_are_pinned_exactly() -> None:
    lines = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert lines, "requirements.txt declares no dependencies"
    for line in lines:
        assert "==" in line, f"determinism requires an exact pin, found '{line}'"


def test_engine_runtime_dependencies_are_available() -> None:
    import numpy
    import scipy

    assert numpy.__version__
    assert scipy.__version__


def ci_config_without_comments() -> str:
    """The workflow's effective configuration.

    Comments are stripped so that prose explaining why a moving label is wrong cannot be
    mistaken for the workflow using one.
    """
    lines = CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("#"))


def test_ci_pins_an_exact_runner_image() -> None:
    """docs/DECISIONS.md D0.9 item 1: a moving image label is not a reproduction environment."""
    config = ci_config_without_comments()

    assert "runs-on: ubuntu-24.04" in config
    assert "ubuntu-latest" not in config


def test_ci_pins_an_exact_python_patch_version() -> None:
    """docs/DECISIONS.md D0.9 item 2: a bare minor version resolves to a moving patch."""
    declared = re.findall(r'python-version:\s*"([^"]+)"', ci_config_without_comments())

    assert declared, "the workflow declares no python-version"
    for version in declared:
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"'{version}' is not an exact patch version"


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
def test_reproduce_fails_loudly_while_it_is_not_wired_up() -> None:
    result = subprocess.run(
        ["make", "reproduce"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "make reproduce must not pass as a silent no-op"
    assert "not wired up" in result.stdout.lower()
    assert "t3.5" in result.stdout.lower(), "the message must name where the target becomes real"


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize(
    "stale_claim",
    ("nothing to reproduce", "no experiment has produced results", "no results exist"),
)
def test_reproduce_does_not_claim_results_are_absent(stale_claim: str) -> None:
    """The exit code was always right; the reason stopped being true at T3.2.

    Experiment 1's results are committed, so a message explaining the failure as "no results
    exist" is false, and the previous test pinned that false string. The target still fails
    because it does not regenerate anything yet, which is a different claim and the true one.
    """
    result = subprocess.run(
        ["make", "reproduce"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert stale_claim not in result.stdout.lower(), (
        f"make reproduce claims {stale_claim!r}, but "
        f"{RESULTS_DIR.relative_to(REPO_ROOT)} holds committed results"
    )


def test_the_committed_results_that_make_the_stale_message_false_exist() -> None:
    """Anchors the test above. If results ever stop being committed, this fails first."""
    assert (RESULTS_DIR / "results.json").is_file()
    assert (RESULTS_DIR / "cards.json").is_file()


class TestPythonVersionGuard:
    """The engine uses 3.11 syntax and stdlib APIs, so an older interpreter must fail clearly.

    `zip(strict=)` needs 3.10 and `sys.stdlib_module_names` needs 3.10, while pyproject declares
    3.11. On an unsupported interpreter the failure should name the version, not surface as a
    confusing AttributeError from a checker script.
    """

    def test_engine_declares_its_minimum_python(self) -> None:
        import metrology

        assert metrology.MINIMUM_PYTHON == (3, 11)

    def test_declared_minimum_matches_pyproject(self) -> None:
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        assert 'requires-python = ">=3.11"' in pyproject

    def test_makefile_guards_the_interpreter_version(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")

        assert "check-python" in text
