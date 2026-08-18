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

from html import escape  # noqa: E402

from metrology.cards import (  # noqa: E402
    render_card,
    render_document,
    render_pair_table,
    render_plain_language_finding,
)
from metrology.reporting import (  # noqa: E402
    CSV_COLUMNS,
    FINDINGS_COLUMNS,
    csv_pair_rows,
    findings_markdown,
    findings_pair_rows,
    illustrative_pair_names,
    render_number,
    validate_card_set,
)

START_MARKER = "<!-- findings:start -->"
END_MARKER = "<!-- findings:end -->"

DEFAULT_RESULTS = HERE / "results" / "results.json"
DEFAULT_AGGREGATES = HERE / "derived" / "aggregates.json"
DEFAULT_README = REPO_ROOT / "README.md"
DEFAULT_CSV = HERE / "results" / "pairs.csv"
DEFAULT_CARDS_JSON = HERE / "results" / "cards.json"
DEFAULT_MANIFEST = HERE / "manifests" / "upstream_digests.json"
DEFAULT_CARDS_HTML = HERE / "results" / "cards.html"

CARDS_TITLE = "Experiment 1: SWE-bench Verified neighboring-pair finding"

APPARATUS_SUMMARY = "Show statistical details and audit trail"

# Reconciled to the approved fixtures/table_reference.html, which governs (spec 11.4).
# The longer alternative is not adopted: a caption box is as wide as its table rather than
# as wide as the scroll container, so at a 320px viewport a longer caption is only partly
# visible until the reader scrolls sideways.
TABLE_HEADING = "Every adjacent pair, as tested"
TABLE_DISCLOSURE = (
    "The observed discordance and both p-value columns read per-instance artifacts and "
    "carry the D4 harness comparability caveat: submissions do not record their harness "
    "version. The pair identity and the resolved-count gap derive from published "
    "aggregates and do not."
)

# The masthead, held to the approved fragment in fixtures/page_reference.html (D1.3).
#
# "Experiment 1" is a structural identifier: its 1 names which experiment this is and has
# no source path. The board size beside it is a corpus figure and goes through
# render_number at aggregates:family_size, because "top 20" inside a sentence is exactly
# the shape a guard looking for isolated markup cannot see, and an earlier comment here
# claimed this masthead carried no figure at all.
#
# The note says where the apparatus is; it does not say the apparatus produced the answer.
# PREREG D7 and the committed primary.note hold that the headline follows from published
# totals alone and that the per-instance work characterizes it without being able to
# overturn it, so "everything that produced it" was a false causal claim.
MASTHEAD_EXPERIMENT = "Experiment 1"
MASTHEAD_TITLE_TEMPLATE = (
    "{experiment}: Neighboring systems in the SWE-bench Verified top {board_size}"
)
MASTHEAD_NOTE = (
    "Can the statistical test chosen in advance tell apart systems ranked next to each "
    "other on this leaderboard? The answer is summarized below. Supporting statistical "
    f'details and the audit trail are available under "{APPARATUS_SUMMARY}."'
)


def render_masthead(aggregates: dict) -> str:
    """The page's opening block: what this is, and where the answer and apparatus sit."""
    title = MASTHEAD_TITLE_TEMPLATE.format(
        experiment=MASTHEAD_EXPERIMENT,
        board_size=render_number("aggregates:family_size", aggregates["family_size"]),
    )
    return f'<div>\n<h1>{escape(title)}</h1>\n<p class="note">{escape(MASTHEAD_NOTE)}</p>\n</div>'


def render_cards_document(cards: dict, results: dict, aggregates: dict) -> str:
    """The finding first, then everything else inside a closed disclosure (spec 11.1).

    A divider was considered and rejected: it leaves the duplicate headline, the p-values,
    the identifiers and the provenance in the first reading, which is what the contract
    moves out of it. The apparatus carries no `open` attribute, so a reader who stops at
    the first screen has a correct and complete headline.
    """
    entries = sorted(aggregates["entries"], key=lambda entry: entry["rank"])
    inner = [render_card(cards["family"])]
    inner.append(
        render_pair_table(
            FINDINGS_COLUMNS,
            findings_pair_rows(results),
            heading=TABLE_HEADING,
            disclosure=TABLE_DISCLOSURE,
        )
    )
    for name in illustrative_pair_names(entries):
        inner.append(render_card(cards["pairs"][name]))
    apparatus = (
        '<details class="technical-apparatus">\n'
        f"<summary>{escape(APPARATUS_SUMMARY)}</summary>\n" + "\n\n".join(inner) + "\n</details>"
    )
    finding = render_plain_language_finding(cards["family"]["family_finding"]["plain_language"])
    masthead = render_masthead(aggregates)
    return render_document([masthead, finding, apparatus], title=CARDS_TITLE)


class ReportFailure(Exception):
    """Halt: the sources or the outputs are not in the state the contract requires."""


def validate_sources(results: dict, aggregates: dict) -> None:
    """Cross-file consistency before any projection (spec sections 2, 6, 7).

    Order is validated against aggregates adjacency, never repaired by sorting: a
    same-file comparison cannot see a results.json whose pair list was reordered
    before this module ever ran. The net-edge check is what lets the gap column
    render uncaveated by D4: it proves the per-instance figure equals the
    aggregate-derived gap, which integrity gate 3 promised and this re-verifies.

    No sorting anywhere (spec section 7): the aggregates array order is itself the
    authority, so a reordered aggregates array is exactly the defect this function
    must report. Sorting it back into rank order would repair the defect silently
    instead, which is why rank order is checked first, against the array as given.
    """
    entries = aggregates["entries"]
    for index, entry in enumerate(entries):
        expected_rank = index + 1
        if entry["rank"] != expected_rank:
            raise ReportFailure(
                f"aggregates entries[{index}] has rank {entry['rank']!r}, expected "
                f"{expected_rank!r}; rank order is validated against the array as given, "
                "never repaired by sorting"
            )
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
        # Signed, not abs(): the published board is nonincreasing in resolved count
        # by construction, and abs() would accept an inverted adjacent pair, the
        # exact defect this check exists to report (Jane's T3.3 review, finding 2).
        gap = first["resolved"] - second["resolved"]
        if gap < 0:
            raise ReportFailure(
                f"published resolved counts increase from rank {first['rank']} "
                f"({first['resolved']}) to rank {second['rank']} ({second['resolved']}); "
                "the board must be nonincreasing and order is validated, not repaired"
            )
        if pair["net_edge"] != gap:
            raise ReportFailure(
                f"pair {index} net edge {pair['net_edge']} disagrees with the adjacent "
                f"published resolved counts ({first['resolved']} to {second['resolved']}); "
                "the gap column may not render as aggregate-derived"
            )
        # The discordance identities tie the summary fields to the counts they
        # summarize, at the same boundary the cross-file checks run.
        if pair["net_edge"] != pair["n10"] - pair["n01"]:
            raise ReportFailure(
                f"pair {index} net edge {pair['net_edge']} does not equal n10 - n01 "
                f"({pair['n10']} - {pair['n01']})"
            )
        if pair["n_discordant"] != pair["n01"] + pair["n10"]:
            raise ReportFailure(
                f"pair {index} n_discordant {pair['n_discordant']} does not equal "
                f"n01 + n10 ({pair['n01']} + {pair['n10']})"
            )
        if pair["n_discordant"] > aggregates["n_items"]:
            raise ReportFailure(
                f"pair {index} n_discordant {pair['n_discordant']} exceeds n_items "
                f"{aggregates['n_items']}"
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
    parser.add_argument("--cards-json", type=Path, default=DEFAULT_CARDS_JSON)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cards-html", type=Path, default=DEFAULT_CARDS_HTML)
    options = parser.parse_args(argv)

    try:
        results = json.loads(options.results.read_text(encoding="utf-8"))
        aggregates = json.loads(options.aggregates.read_text(encoding="utf-8"))
        cards = json.loads(options.cards_json.read_text(encoding="utf-8"))
        manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
        validate_sources(results, aggregates)
        try:
            validate_card_set(cards, results, aggregates, manifest)
        except (ValueError, KeyError) as failure:
            # KeyError as well as ValueError: a missing or renamed key in results.json
            # surfaces from _dig as a KeyError, and a preflight that let that escape
            # uncaught would abort mid-run rather than halting with a diagnosis.
            raise ReportFailure(f"card set validation failed: {failure}") from failure

        expected_csv = render_csv_text(results)
        block = findings_markdown(results, aggregates)
        readme_text = options.readme.read_text(encoding="utf-8")
        expected_readme = spliced(readme_text, block)
        expected_cards_html = render_cards_document(cards, results, aggregates)

        if options.write:
            _write_atomically(options.csv, expected_csv)
            _write_atomically(options.readme, expected_readme)
            _write_atomically(options.cards_html, expected_cards_html)
            print(f"wrote {options.csv}, {options.cards_html}, and spliced {options.readme}")
            return 0

        problems = []
        if not options.csv.exists() or options.csv.read_text(encoding="utf-8") != expected_csv:
            problems.append(f"{options.csv} does not match the rendered projection")
        if readme_text != expected_readme:
            problems.append(f"{options.readme} findings block does not match the generator")
        if (
            not options.cards_html.exists()
            or options.cards_html.read_text(encoding="utf-8") != expected_cards_html
        ):
            problems.append(f"{options.cards_html} does not match the rendered document")
        if problems:
            raise ReportFailure("drift:\n  " + "\n  ".join(problems))
        print("report check: findings block, CSV, and card set match the corpus")
        return 0
    except ReportFailure as failure:
        print(f"STOPPED: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
