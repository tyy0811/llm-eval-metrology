"""T3.3 reporting IO: the CSV projection and the README findings block.

Reads results/results.json and derived/aggregates.json, recomputes nothing. Both
modes run validate_sources first; --write refuses to write anything from a source
that fails it, in the check_no_substitutions spirit of halting before the work.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from metrology.reporting import (  # noqa: E402
    CSV_COLUMNS,
    csv_pair_rows,
    findings_markdown,
)

START_MARKER = "<!-- findings:start -->"
END_MARKER = "<!-- findings:end -->"

DEFAULT_RESULTS = HERE / "results" / "results.json"
DEFAULT_AGGREGATES = HERE / "derived" / "aggregates.json"
DEFAULT_README = REPO_ROOT / "README.md"
DEFAULT_CSV = HERE / "results" / "pairs.csv"


class ReportFailure(Exception):
    """Halt: the sources or the outputs are not in the state the contract requires."""


def validate_sources(results: dict, aggregates: dict) -> None:
    """Cross-file consistency before any projection (spec sections 2, 6, 7).

    Order is validated against aggregates adjacency, never repaired by sorting: a
    same-file comparison cannot see a results.json whose pair list was reordered
    before this module ever ran. The net-edge check is what lets the gap column
    render uncaveated by D4: it proves the per-instance figure equals the
    aggregate-derived gap, which integrity gate 3 promised and this re-verifies.
    """
    entries = sorted(aggregates["entries"], key=lambda entry: entry["rank"])
    pairs = results["pairs"]
    if len(pairs) != len(entries) - 1:
        raise ReportFailure(
            f"expected {len(entries) - 1} pairs from {len(entries)} entries, got {len(pairs)}"
        )
    for index, pair in enumerate(pairs):
        first, second = entries[index], entries[index + 1]
        expected_name = f"rank_{first['rank']}_vs_{second['rank']}"
        if pair["name"] != expected_name:
            raise ReportFailure(
                f"pair {index} name {pair['name']!r} does not match the aggregate "
                f"adjacency {expected_name!r}; source order is validated, not repaired"
            )
        if pair["system_a"] != first["system"] or pair["system_b"] != second["system"]:
            raise ReportFailure(f"pair {index} systems do not match the aggregate adjacency order")
        gap = first["resolved"] - second["resolved"]
        if pair["net_edge"] != abs(gap):
            raise ReportFailure(
                f"pair {index} net edge {pair['net_edge']} disagrees with the adjacent "
                f"published resolved counts ({first['resolved']} to {second['resolved']}); "
                "the gap column may not render as aggregate-derived"
            )


def render_csv_text(results: dict) -> str:
    """Deterministic bytes: QUOTE_MINIMAL, comma, LF, trailing newline (D0.9)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    writer.writerows(csv_pair_rows(results))
    return buffer.getvalue()


def spliced(readme_text: str, block: str) -> str:
    """Replace the content between exactly one ordered marker pair."""
    starts = readme_text.count(START_MARKER)
    ends = readme_text.count(END_MARKER)
    if starts != 1 or ends != 1:
        raise ReportFailure(
            f"expected exactly one marker pair, found {starts} start and {ends} end markers"
        )
    start = readme_text.index(START_MARKER)
    end = readme_text.index(END_MARKER)
    if end < start:
        raise ReportFailure("markers are in reverse order; refusing to splice")
    return readme_text[: start + len(START_MARKER)] + "\n" + block + readme_text[end:]


def _write_atomically(path: Path, text: str) -> None:
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--aggregates", type=Path, default=DEFAULT_AGGREGATES)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    options = parser.parse_args(argv)

    try:
        results = json.loads(options.results.read_text(encoding="utf-8"))
        aggregates = json.loads(options.aggregates.read_text(encoding="utf-8"))
        validate_sources(results, aggregates)

        expected_csv = render_csv_text(results)
        block = findings_markdown(results, aggregates)
        readme_text = options.readme.read_text(encoding="utf-8")
        expected_readme = spliced(readme_text, block)

        if options.write:
            _write_atomically(options.csv, expected_csv)
            _write_atomically(options.readme, expected_readme)
            print(f"wrote {options.csv} and spliced {options.readme}")
            return 0

        problems = []
        if not options.csv.exists() or options.csv.read_text(encoding="utf-8") != expected_csv:
            problems.append(f"{options.csv} does not match the rendered projection")
        if readme_text != expected_readme:
            problems.append(f"{options.readme} findings block does not match the generator")
        if problems:
            raise ReportFailure("drift:\n  " + "\n  ".join(problems))
        print("report check: findings block and CSV match the corpus")
        return 0
    except ReportFailure as failure:
        print(f"STOPPED: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
