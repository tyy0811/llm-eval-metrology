"""Reproduction gates for `make reproduce` (PLAN.md T3.5).

Two modes bracketing the writers. `--preflight` refuses to start on a dirty worktree,
because fetch.py, run.py and report.py --write all overwrite tracked artifacts: without
it, an uncommitted edit is destroyed by a writer and the final check then reports the
clean tree it just created, so the run erases the evidence of its own invalidity.

`--verify` reads the whole worktree rather than a declared artifact list. A list cannot
see a modified source file, a staged change, or a tracked output nobody thought to
declare, which is the enumeration failure this repository has paid for repeatedly.

Exit status is 0 when the gate holds and 1 when it does not.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

#: D0.9's canonical interpreter. CI passes --canonical and fails on anything else.
CANONICAL_PYTHON = "3.11.15"

#: Every tracked path the pipeline regenerates. Used only to report a *missing* artifact
#: distinctly; everything else comes from git status over the whole tree.
TRACKED_ARTIFACTS = (
    "experiments/swebench/derived/aggregates.json",
    "experiments/swebench/results/results.json",
    "experiments/swebench/results/cards.json",
    "experiments/swebench/results/pairs.csv",
    "experiments/swebench/results/cards.html",
    "README.md",
)


def running_python() -> str:
    """Patched by tests, so the canonical controls run on any interpreter."""
    return platform.python_version()


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


def print_banner(canonical: bool) -> int:
    """The environment, printed on every run so it cannot rot into something reachable
    only in cases nobody hits.

    The closing line differs by mode because the two modes make different claims. Default
    mode is a development check and says so. Canonical mode has just gated the
    interpreter, and the workflow pins the runner image, so it reports the half it
    actually established rather than disclaiming a verdict it is part of making.
    """
    print(f"  interpreter: {sys.executable}")
    print(f"  version:     {running_python()}")
    print(f"  platform:    {platform.platform()}")
    if not canonical:
        print("  this run is a development check and is not canonical evidence (D0.9)")
        return 0
    if running_python() != CANONICAL_PYTHON:
        print(f"FAILED: --canonical requires Python {CANONICAL_PYTHON}, got {running_python()}")
        return 1
    print(
        f"  canonical interpreter check passed: Python {CANONICAL_PYTHON}. "
        "The runner image is pinned by the workflow (D0.9)."
    )
    return 0


def preflight() -> int:
    """Refuse to start unless the worktree is clean.

    `git status --porcelain` reports tracked modifications staged and unstaged, plus
    untracked non-ignored files, and stays silent about ignored ones. That is exactly the
    boundary wanted here: labels.csv and unevaluated.json are rebuilt every run and must
    not block a start, while a developer's uncommitted edit must.
    """
    dirty = git_output("status", "--porcelain").splitlines()
    if not dirty:
        return 0
    print("PREFLIGHT FAILED: the worktree is not clean, so reproduction must not start.")
    print("  A writer would overwrite these, and the check afterwards would then see the")
    print("  clean tree it had itself created, reporting success for a run whose evidence")
    print("  it had just destroyed.")
    for line in dirty:
        print(f"  {line}")
    print("\nStash or commit this work first: git stash --include-untracked")
    return 1


def verify() -> int:
    """Fail unless the rebuild reproduced the committed tree exactly.

    The whole worktree, not a declared artifact list. A list cannot see a modified source
    file, a staged change, or a tracked output nobody thought to declare, which is the
    enumeration failure this repository has paid for repeatedly: a guard that checks the
    paths its author listed cannot see the path they did not.

    TRACKED_ARTIFACTS is consulted only to name an artifact that is absent entirely. A
    deleted file also reaches porcelain as ` D`, but one that was never committed at all
    gives status nothing to report it against.
    """
    missing = [rel for rel in TRACKED_ARTIFACTS if not Path(rel).exists()]
    dirty = git_output("status", "--porcelain").splitlines()
    if not missing and not dirty:
        print("reproduction verified: every tracked artifact rebuilt to the committed bytes")
        return 0

    print("VERIFY FAILED: the rebuild did not reproduce the committed tree.")
    for rel in missing:
        print(f"  missing tracked artifact: {rel}")
    for line in dirty:
        print(f"  {line}")
    # HEAD, not the working tree, so a staged mismatch produces a diff instead of
    # silence. A byte mismatch reported with no diff shown cannot be acted on.
    diff = git_output("diff", "HEAD")
    if diff:
        print("\n--- git diff HEAD ---")
        print(diff)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="refuse to start on a dirty tree")
    mode.add_argument("--verify", action="store_true", help="verify the worktree is clean after")
    parser.add_argument(
        "--canonical",
        action="store_true",
        help=f"fail unless the interpreter is exactly Python {CANONICAL_PYTHON}",
    )
    args = parser.parse_args(argv)

    if print_banner(args.canonical) != 0:
        return 1
    return preflight() if args.preflight else verify()


if __name__ == "__main__":
    raise SystemExit(main())
