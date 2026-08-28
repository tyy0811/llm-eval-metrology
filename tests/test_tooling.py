"""Phase 0 tooling guarantees: the declared make targets exist, dependencies are pinned
exactly, and the `reproduce` recipe holds its shape.

Until T3.5 this file asserted that `make reproduce` *failed*, because a green reproduce
must never be achievable while the target regenerates nothing. T3.5 wired it to the real
pipeline, so that assertion inverted and was retired with the loud-failing recipe it
guarded. What replaces it is asserted against the Makefile text: the recipe now reaches
upstream, and a test that shells out to it would fail whenever the network is down, for
reasons having nothing to do with its subject.
"""

from __future__ import annotations

import re
import sys
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


def declared_requirements() -> set[str]:
    """Package names declared in requirements.txt, normalized for import comparison."""
    names = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[=<>!~\[]", line, maxsplit=1)[0].strip()
        if name:
            names.add(name.lower().replace("-", "_"))
    return names


def test_every_third_party_import_outside_the_engine_is_declared() -> None:
    """An import nothing declares makes reproduction depend on the authoring machine.

    `pyarrow` was imported by fetch.py from T3.1 and declared nowhere, so `make reproduce`
    could not have run on a fresh clone. It stayed hidden because CI asserted the target
    *failed* until T3.5: the one execution that would have exposed it was the one the old
    gate guaranteed would never happen. The first canonical run found it immediately.

    `metrology/` has its own boundary (`make import-check`, stdlib plus numpy and scipy).
    This covers everything outside it, where heavier dependencies are permitted but must
    still be declared. The set is derived from the AST rather than listed, because a
    listed set cannot see the import its author did not think to add.
    """
    import check_imports

    roots: dict[str, set[str]] = {}
    for base in (REPO_ROOT / "experiments", REPO_ROOT / "scripts"):
        for path in sorted(base.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for lineno, module in check_imports.imported_roots(source, filename=str(path)):
                roots.setdefault(module, set()).add(f"{path.relative_to(REPO_ROOT)}:{lineno}")

    local = {
        p.stem for base in ("experiments", "scripts") for p in (REPO_ROOT / base).rglob("*.py")
    }
    third_party = {
        module: sites
        for module, sites in roots.items()
        if module not in sys.stdlib_module_names
        and module != check_imports.OWN_PACKAGE
        and module not in local
    }

    declared = declared_requirements()
    undeclared = {m: sites for m, sites in third_party.items() if m not in declared}

    assert not undeclared, (
        "undeclared third-party import(s) outside metrology/: "
        + "; ".join(f"{m} at {sorted(sites)}" for m, sites in sorted(undeclared.items()))
        + ". Add an exact pin to requirements.txt (D0.5)."
    )


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


def test_ci_has_no_reproduce_must_fail_assertion() -> None:
    """The old gate must not survive beside the new one.

    Two steps disagreeing about whether reproduce should pass makes the job's verdict
    depend on step order, and the one asserting failure would go red the moment
    reproduction started working, which is the outcome T3.5 exists to produce.
    """
    config = ci_config_without_comments()

    assert "make reproduce succeeded but" not in config
    assert "failed as required" not in config
    assert "loud failure" not in config


def test_ci_runs_reproduce_canonically() -> None:
    """--canonical is what makes CI's run a verdict rather than another local check.

    Reaching it through REPRODUCE_MODE means the Makefile carries one recipe, not two.
    """
    assert "REPRODUCE_MODE=--canonical" in ci_config_without_comments()


def test_ci_prints_a_diff_even_when_reproduce_fails() -> None:
    """Without always(), GitHub skips the step when make reproduce fails, which is
    precisely the case whose diff is wanted. The promise to print one would then be
    unkept in the only situation that needs it."""
    config = ci_config_without_comments()

    assert "if: ${{ always() }}" in config
    # HEAD, for the same reason check_reproduction.py uses it: a staged mismatch would
    # otherwise be reported with an empty diff.
    assert "git diff HEAD" in config


def test_the_results_reproduce_must_regenerate_are_committed() -> None:
    """Reproduction compares a rebuild against committed bytes, so the bytes must exist.

    If results ever stop being committed, `make reproduce` would compare a rebuild against
    nothing and pass, which is the no-op green the retired loud-failure test existed to
    prevent. This is what still guards that, now that the target is real.
    """
    assert (RESULTS_DIR / "results.json").is_file()
    assert (RESULTS_DIR / "cards.json").is_file()


class TestReproduceTarget:
    """A bootstrap inside reproduce rewrites the manifest it is checked against.

    Every mismatch then becomes a silent pass, so the target would report reproduction
    while proving only that it can overwrite its own expectations. This is the
    highest-value control in T3.5.

    Asserted against the Makefile text rather than by running it: the recipe reaches
    upstream, and a test that needs the network is a test that fails for reasons that
    have nothing to do with its subject.
    """

    def recipe(self) -> list[str]:
        """The reproduce recipe's lines, tab-indented, up to the next target."""
        text = MAKEFILE.read_text(encoding="utf-8")
        body = text.split("\nreproduce:", 1)[1]
        lines = []
        for line in body.splitlines()[1:]:
            if line and not line.startswith("\t"):
                break
            if line.strip():
                lines.append(line.strip())
        return lines

    def writers(self, lines: list[str]) -> list[int]:
        return [
            index
            for index, line in enumerate(lines)
            if "fetch.py" in line or "run.py" in line or "report.py" in line
        ]

    def test_the_recipe_is_not_empty(self) -> None:
        """Every other control here is vacuous against an empty list."""
        assert len(self.recipe()) >= 5

    def test_reproduce_never_passes_bootstrap(self) -> None:
        assert not any("--bootstrap" in line for line in self.recipe())

    def test_every_recipe_line_uses_the_python_variable(self) -> None:
        """A literal python3 would let check-python validate one interpreter while
        reproduction ran another, and the banner would then name the wrong one."""
        for line in self.recipe():
            assert "python3" not in line
            assert "$(PYTHON)" in line

    def test_preflight_precedes_every_writer(self) -> None:
        """The control tests/test_reproduction.py cannot supply: calling the checker alone
        never invokes a writer, so ordering can only be asserted where it is written."""
        lines = self.recipe()
        preflight = next(i for i, line in enumerate(lines) if "--preflight" in line)
        writers = self.writers(lines)

        assert writers
        assert preflight < min(writers)

    def test_verify_follows_every_writer(self) -> None:
        lines = self.recipe()
        verify = next(i for i, line in enumerate(lines) if "--verify" in line)
        writers = self.writers(lines)

        assert writers
        assert verify > max(writers)

    def test_both_checker_calls_forward_the_mode_variable(self) -> None:
        """CI sets REPRODUCE_MODE=--canonical. A checker call that dropped it would run
        the interpreter gate locally only, and never where the verdict is established."""
        checks = [line for line in self.recipe() if "check_reproduction.py" in line]

        assert len(checks) == 2
        for line in checks:
            assert "$(REPRODUCE_MODE)" in line

    def test_the_mode_variable_defaults_to_empty(self) -> None:
        """Local runs must not fail on environment, per D0.9."""
        assert "REPRODUCE_MODE ?=\n" in MAKEFILE.read_text(encoding="utf-8")


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
