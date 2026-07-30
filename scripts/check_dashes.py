"""Enforce the text style guardrail declared in PLAN.md section 2.

Authored text carries no em dashes and no en dashes. Numeric ranges are written "X to Y".

The plan states this rule as `grep -rnP` over changed files. It is implemented here in Python
for two reasons: `grep -P` is not available on every platform this repo is edited on, and a
whole-tree check cannot be defeated by committing a violation in a file the diff does not
touch.

The forbidden characters are constructed with chr() and never appear literally in this file, so
the checker does not flag itself.

Exit status is 0 when authored text is clean and 1 when it is not.
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Codepoint to human-readable name. Built with chr() so that this module never contains the
#: characters it forbids and therefore never flags itself.
FORBIDDEN = {
    chr(0x2014): "em dash",
    chr(0x2013): "en dash",
}

#: Extensions treated as authored text.
TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".py",
        ".toml",
        ".txt",
        ".cfg",
        ".ini",
        ".yml",
        ".yaml",
        ".json",
        ".html",
        ".css",
        ".js",
        ".csv",
        ".ipynb",
    }
)

#: Extensionless files that are still authored text.
TEXT_FILENAMES = frozenset({"Makefile", "LICENSE", ".gitignore"})

#: Directories never scanned.
SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "env",
        ".ipynb_checkpoints",
        "node_modules",
        ".egg-info",
    }
)


@dataclass(frozen=True)
class Violation:
    """One forbidden character occurrence."""

    path: Path
    lineno: int
    column: int
    name: str
    line: str

    def render(self, root: Path = REPO_ROOT) -> str:
        try:
            shown = self.path.relative_to(root)
        except ValueError:
            shown = self.path
        excerpt = self.line.strip()
        if len(excerpt) > 90:
            excerpt = excerpt[:87] + "..."
        return f"{shown}:{self.lineno}:{self.column}: {self.name}\n      {excerpt}"


def is_text_file(path: Path) -> bool:
    """Whether this path counts as authored text."""
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES


def iter_text_files(root: Path) -> Iterator[Path]:
    """Yield authored text files under `root`, skipping build and vcs directories.

    Used for explicitly supplied paths, so a gitignored file named on the command
    line is still scanned; only default discovery consults git.
    """
    if root.is_file():
        if is_text_file(root):
            yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if is_text_file(path):
            yield path


def default_discovery() -> list[Path]:
    """Authored files git would carry: tracked plus untracked-unignored.

    An rglob walk scanned gitignored scratch and generated directories, so the
    gate failed working copies for files that could never reach the repository,
    while this form still catches a new unignored file before anyone commits it
    (Jane's T3.3 ruling on the dash checker).
    """
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files = []
    for line in listing.stdout.splitlines():
        path = REPO_ROOT / line
        if path.is_file() and is_text_file(path):
            files.append(path)
    return sorted(files)


def violations_in_text(text: str, path: Path) -> list[Violation]:
    """Forbidden characters in a single file's contents."""
    found: list[Violation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for column, char in enumerate(line, start=1):
            name = FORBIDDEN.get(char)
            if name is not None:
                found.append(
                    Violation(path=path, lineno=lineno, column=column, name=name, line=line)
                )
    return found


def scan(paths: Iterable[Path]) -> tuple[list[Violation], int]:
    """Scan authored text under each path. Returns (violations, files_checked)."""
    found: list[Violation] = []
    checked = 0
    for base in paths:
        for path in iter_text_files(base):
            checked += 1
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found.extend(violations_in_text(text, path))
    return found, checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to check (default: git-listed authored files)",
    )
    args = parser.parse_args(argv)

    if args.paths:
        found, checked = scan([p for p in args.paths if p.exists()])
    else:
        found = []
        checked = 0
        for path in default_discovery():
            checked += 1
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found.extend(violations_in_text(text, path))
    if found:
        print(f"dash-check FAILED: {len(found)} occurrence(s) in authored text")
        for violation in found:
            print(f"  {violation.render()}")
        print('\nWrite numeric ranges as "X to Y" (PLAN.md section 2).')
        return 1

    print(f"dash-check passed: {checked} file(s), no em dashes or en dashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
