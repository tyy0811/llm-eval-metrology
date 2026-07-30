"""D1.8: every numeral in running prose must be a member of the committed corpus,
rendered exactly as the format registry renders it (T3.3 spec sections 3 and 4).

Scans the entire running prose of each named file. Markdown files are scanned
directly; .py files are treated as percent-format notebooks and only their
markdown cells are scanned. Exemptions are structural and verified against the
repository, never shape-only: a path must be git-tracked, a make target declared,
a system name present in the aggregates.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from metrology.reporting import (  # noqa: E402
    iter_numeric_leaves,
    render_number,
)

FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`([^`]+)`")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
URL = re.compile(r"https?://\S+")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.Z]+)?\b")
HEX_HASH = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
VERSION = re.compile(r"\bv?\d+(?:\.\d+){2,}\b")
TASK_ID = re.compile(r"\b[TD]\d+(?:\.\d+)?\b")
SYSTEM_NAME = re.compile(r"\b\d{8}_[\w.-]+\b")
HEADING = re.compile(r"^#+\s", re.MULTILINE)
TABLE_DIVIDER = re.compile(r"^\|[\s:|-]+\|$", re.MULTILINE)
ORDERED_MARKER = re.compile(r"^(\s*)\d+\.\s", re.MULTILINE)
LABEL = re.compile(r"\b(?:Phase|Experiment|Layer|section|item)\s+\d+(?!\.\d)\b")
NUMERAL = re.compile(r"(?<![\w.-])-?\d+(?:\.\d+)?(?![\w.-])")
# Inside a scanned span the word-boundary protection is deliberately dropped: the
# span already failed whole-token verification, so digits buried in identifiers
# (`fake999`, `solve-everything-42`) are exactly what must surface. In running
# prose the boundary stays, or every hyphenated name would false-positive.
SPAN_NUMERAL = re.compile(r"\d+(?:\.\d+)?")
BARE_NUMERIC_SPAN = re.compile(r"^[\d\s.,%+-]+$")
RUNNER_LABELS = frozenset({"ubuntu-24.04"})


def build_context(repo_root: Path) -> dict:
    """Everything the structural exemptions verify against."""
    tracked = set(
        subprocess.run(
            ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    )
    makefile_text = (repo_root / "Makefile").read_text(encoding="utf-8")
    make_targets = set(re.findall(r"^([A-Za-z][\w-]*):", makefile_text, re.MULTILINE))
    documents = {
        "results": json.loads(
            (repo_root / "experiments/swebench/results/results.json").read_text(encoding="utf-8")
        ),
        "aggregates": json.loads(
            (repo_root / "experiments/swebench/derived/aggregates.json").read_text(encoding="utf-8")
        ),
    }
    corpus_strings = set()
    for source, document in documents.items():
        for qualified_path, value in iter_numeric_leaves(source, document):
            corpus_strings.add(render_number(qualified_path, value))
    systems = {entry["system"] for entry in documents["aggregates"]["entries"]}
    return {
        "tracked": tracked,
        "make_targets": make_targets,
        "corpus": corpus_strings,
        "systems": systems,
    }


def _strip_atomic_tokens(text: str) -> str:
    for pattern in (URL, LINK_TARGET, DATE, SYSTEM_NAME, VERSION, HEX_HASH, TASK_ID):
        text = pattern.sub(" ", text)
    return text


def _span_is_whole_token(content: str, context: dict) -> bool:
    content = content.strip()
    if content in context["tracked"] or content in context["systems"]:
        return True
    if content in RUNNER_LABELS:
        return True
    if content.startswith("make ") and content.removeprefix("make ") in context["make_targets"]:
        return True
    if content in context["make_targets"]:
        return True
    return any(pattern.fullmatch(content) for pattern in (DATE, HEX_HASH, VERSION, TASK_ID))


def _scan_span(content: str, context: dict, violations: list[str]) -> None:
    """A span that is not a verified whole token gets an aggressive scan: strip the
    grammar-safe atomics (never SYSTEM_NAME, whose shape is checkable but whose
    membership was already refused by the whole-token step), then every remaining
    digit run must be a corpus rendering, word boundaries or not."""
    for pattern in (DATE, HEX_HASH, VERSION, TASK_ID):
        content = pattern.sub(" ", content)
    for match in SPAN_NUMERAL.finditer(content):
        if match.group(0) not in context["corpus"]:
            violations.append(
                f"numeral {match.group(0)!r} inside a code span is not a corpus rendering"
            )


def check_text(text: str, context: dict) -> list[str]:
    violations: list[str] = []
    text = FENCE.sub(" ", text)

    def handle_span(match: re.Match) -> str:
        content = match.group(1)
        if BARE_NUMERIC_SPAN.fullmatch(content):
            violations.append(f"bare numeric code span `{content}`: figures may not pose as code")
        elif not _span_is_whole_token(content, context):
            _scan_span(content, context, violations)
        return " "

    text = INLINE_CODE.sub(handle_span, text)
    text = _strip_atomic_tokens(text)
    text = HEADING.sub(" ", text)
    text = TABLE_DIVIDER.sub(" ", text)
    text = ORDERED_MARKER.sub(r"\1", text)
    text = LABEL.sub(" ", text)

    for match in NUMERAL.finditer(text):
        token = match.group(0).lstrip("-")
        if token not in context["corpus"]:
            violations.append(f"numeral {match.group(0)!r} is not a committed corpus rendering")
    return violations


def markdown_cells(notebook_text: str) -> str:
    """Prose cells of a percent-format notebook: lines between a markdown marker
    and the next cell marker, with the leading comment stripped."""
    cells: list[str] = []
    collecting = False
    for line in notebook_text.splitlines():
        if line.startswith("# %% [markdown]"):
            collecting = True
            continue
        if line.startswith("# %%"):
            collecting = False
            continue
        if collecting and line.startswith("#"):
            cells.append(line.lstrip("#").strip())
    return "\n".join(cells)


def main(argv: list[str] | None = None) -> int:
    targets = argv if argv else ["README.md", "experiments/swebench/notebook.py"]
    context = build_context(REPO_ROOT)
    failures = 0
    for target in targets:
        path = Path(target)
        if not path.is_absolute():
            path = REPO_ROOT / path
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            text = markdown_cells(text)
        for violation in check_text(text, context):
            print(f"{target}: {violation}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"prose-check failed: {failures} violation(s)", file=sys.stderr)
        return 1
    print(f"prose-check passed: {len(targets)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
