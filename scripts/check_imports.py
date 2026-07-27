"""Enforce the engine import boundary declared in PLAN.md section 2.

`metrology/` must stay portable to pyodide, so it may import only the standard library,
numpy, scipy, and itself. Anything heavier (pandas, matplotlib, requests, datasets) belongs
in `experiments/` scripts.

The check is static: it parses each module with `ast` rather than importing it, so an
unimportable or partially written module still gets checked, and no third-party package needs
to be installed for the check to run.

Exit status is 0 when the boundary holds and 1 when it does not.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Third-party roots the engine is allowed to import. Adding to this set is a plan-level
#: decision, not a convenience: every entry must be available under pyodide.
ALLOWED_THIRD_PARTY = frozenset({"numpy", "scipy"})

#: The engine's own root package, so intra-engine absolute imports are permitted.
OWN_PACKAGE = "metrology"


@dataclass(frozen=True)
class Violation:
    """A single disallowed import."""

    path: Path
    lineno: int
    module: str

    def render(self, root: Path = REPO_ROOT) -> str:
        try:
            shown = self.path.relative_to(root)
        except ValueError:
            shown = self.path
        return f"{shown}:{self.lineno}: imports '{self.module}'"


def allowed_roots() -> frozenset[str]:
    """Top-level module names the engine may import."""
    return frozenset(sys.stdlib_module_names) | ALLOWED_THIRD_PARTY | {OWN_PACKAGE}


def imported_roots(source: str, filename: str = "<string>") -> Iterator[tuple[int, str]]:
    """Yield (lineno, top_level_module) for every absolute import in `source`.

    Relative imports (`from . import x`) are intra-package and never yielded.
    """
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 is a relative import; node.module is None for `from . import x`.
            if node.level or node.module is None:
                continue
            yield node.lineno, node.module.split(".")[0]


def violations_in_source(source: str, path: Path) -> list[Violation]:
    """Disallowed imports in a single module's source text."""
    permitted = allowed_roots()
    return [
        Violation(path=path, lineno=lineno, module=module)
        for lineno, module in imported_roots(source, filename=str(path))
        if module not in permitted
    ]


def scan(paths: Iterable[Path]) -> list[Violation]:
    """Scan every `*.py` file under each path, recursively."""
    found: list[Violation] = []
    for base in paths:
        candidates = sorted(base.rglob("*.py")) if base.is_dir() else [base]
        for module_path in candidates:
            source = module_path.read_text(encoding="utf-8")
            found.extend(violations_in_source(source, module_path))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[REPO_ROOT / OWN_PACKAGE],
        help="files or directories to check (default: metrology/)",
    )
    args = parser.parse_args(argv)

    targets = [p for p in args.paths if p.exists()]
    if not targets:
        # Phase 0 legitimately has an engine package with no modules yet. An absent
        # target is not a violation, but say so rather than reporting a silent pass.
        print("import-check: no engine modules to check yet")
        return 0

    found = scan(targets)
    if found:
        print(f"import-check FAILED: {len(found)} disallowed import(s)")
        for violation in found:
            print(f"  {violation.render()}")
        allowed = ", ".join(sorted(ALLOWED_THIRD_PARTY))
        print(f"\n{OWN_PACKAGE}/ may import only the standard library, {allowed}, and itself.")
        print("Heavier dependencies belong in experiments/ scripts (PLAN.md section 2).")
        return 1

    checked = sum(len(sorted(p.rglob("*.py"))) if p.is_dir() else 1 for p in targets)
    print(f"import-check passed: {checked} module(s), boundary holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
