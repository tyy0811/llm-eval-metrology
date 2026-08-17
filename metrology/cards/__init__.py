"""Static HTML renderers for the verdict and family cards.

The visual language was fixed by `fixtures/verdict_reference.html`, built and approved before this
module existed (D1.3). That ordering matters: had the renderer come first, its own output would
have become the snapshot baseline, and the tests would have been self-consistent while proving
nothing about whether the card communicates.

Output is deterministic. No timestamps, no reliance on dictionary iteration, no randomness, and
fixed numeric formatting, because `make reproduce` promises identical bytes and a card is a
committed artifact.

Standard library only. Cards are meant to render client-side under pyodide, so nothing here
reaches for a template engine.
"""

from __future__ import annotations

import hashlib
import re
from html import escape
from pathlib import Path

from ..reporting import (
    CARD_FAMILY,
    CARD_PAIR,
    PLAIN_LANGUAGE_SOURCES,
    pair_display_label,
    render_number,
    validate_card,
)

#: The approved stylesheet, kept in `card.css` as a single source of truth rather than inlined
#: here, so it is not squeezed into a Python line-length budget. A test asserts it agrees with
#: `fixtures/verdict_reference.html` on the load-bearing tokens, so the renderer cannot quietly
#: drift from the visual language that was signed off.
CARD_STYLESHEET = (Path(__file__).parent / "card.css").read_text(encoding="utf-8")


def ruler_marker_class(edge: int, total: int) -> str:
    """Edge-safe positioning class for a ruler marker.

    A marker at either extreme overhangs the track under the default centred transform, so the
    ends get explicit alignment. Returns an empty string in the interior.
    """
    if total <= 0 or edge <= 0:
        return "at-start"
    if edge >= total:
        return "at-end"
    return ""


def html_id(name: str) -> str:
    """Deterministic, ID-safe encoding of a card name.

    Card names are free text and may carry spaces or punctuation, which would break the
    `aria-labelledby` reference they are used in. Sanitizing alone could collide two distinct
    names onto one id, so a short digest of the original is appended.
    """
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "card"
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}"


def _num(value: float, places: int) -> str:
    return f"{value:.{places}f}"


def _precise(value: float) -> str:
    """Repr-grade precision, so a printed figure round-trips to the value it came from.

    .15g drops the seventeenth significant digit, which made the printed first critical
    value differ from the stored one. repr gives the shortest string that float() returns
    to the same double.
    """
    return repr(float(value))


def _marker(edge: int, total: int, label: str, kind: str) -> str:
    position = 0.0 if total <= 0 else 100.0 * edge / total
    extra = ruler_marker_class(edge, total)
    classes = f"ruler-mark {kind}" + (f" {extra}" if extra else "")
    return (
        f'          <div class="{classes}" style="left: {position:.1f}%;">\n'
        f"            <span>{escape(label)}</span><i></i>\n"
        f"          </div>"
    )


def _seal(entries: list[tuple[str, str]]) -> str:
    parts = "\n".join(
        f"        <span>{escape(label)} <b>{escape(value)}</b></span>" for label, value in entries
    )
    return f'      <div class="seal">\n{parts}\n      </div>'


def _kv(rows: list[tuple[str, str]]) -> str:
    parts = "\n".join(
        f"          <dt>{escape(key)}</dt><dd>{escape(value)}</dd>" for key, value in rows
    )
    return f'        <dl class="kv">\n{parts}\n        </dl>'


def _pair_body(card: dict) -> str:
    comparison, ruler = card["comparison"], card["ruler"]
    total = ruler["observed_disagreements"]
    favour_a, favour_b = ruler["split"]
    # The ruler measures magnitude. A reversed pair has a negative net edge, which would place
    # the marker off the left of the track; the split already carries the direction.
    edge = abs(ruler["observed_net_edge"])
    required = ruler["required_net_edge_at_observed"]
    name_a, name_b = escape(comparison["system_a"]), escape(comparison["system_b"])

    if total == 0:
        return (
            f'      <p class="what-would-it-take">These systems agree on every instance, '
            f"0 of {comparison['n_items']} discordant, so no split can separate them.</p>"
        )

    if required is None:
        takes = (
            "At this discordance no split rejects at all. What is missing is more disagreement, "
            "not a larger edge."
        )
    else:
        high = (total + required) // 2
        takes = (
            f"To separate at this discordance the split would have to reach {high} to "
            f"{total - high}, a net edge of {required}."
        )

    markers = _marker(edge, total, f"observed {edge}", "observed")
    if required is not None:
        markers += "\n" + _marker(required, total, f"required {required}", "required")

    return (
        f'      <div class="strip" role="img" aria-label="{total} disagreements, {favour_a} '
        f'favour {name_a} and {favour_b} favour {name_b}">\n'
        f'        <div class="strip-a" style="flex: {favour_a};"></div>\n'
        f'        <div class="strip-b" style="flex: {favour_b};"></div>\n'
        f"      </div>\n"
        f'      <p class="strip-legend"><span>{favour_a} favour {name_a}</span>'
        f"<span>{favour_b} favour {name_b}</span></p>\n"
        f'      <div class="ruler">\n'
        f'        <p class="eyebrow">Net edge, against what it would take</p>\n'
        f'        <div class="ruler-track">\n'
        f'          <div class="ruler-line"></div>\n'
        f"{markers}\n"
        f"        </div>\n"
        f'        <p class="ruler-scale"><span>0, balanced</span>'
        f"<span>{total}, all one way</span></p>\n"
        f"      </div>\n"
        f'      <p class="what-would-it-take">{escape(takes)}</p>'
    )


def render_pair_card(card: dict) -> str:
    """One pair verdict card, as an `article` fragment."""
    validate_card(card)
    comparison, test, ruler, mde = card["comparison"], card["test"], card["ruler"], card["mde"]
    total = ruler["observed_disagreements"]
    favour_a, favour_b = ruler["split"]
    edge = abs(ruler["observed_net_edge"])
    slug = html_id(comparison["name"])
    label = escape(pair_display_label(comparison["name"]))

    # EQUIVALENT is refused by validate_card above, with the TOST message, so only the two
    # renderable verdicts reach here.
    rail = "is-resolved" if card["verdict"] == "RESOLVED" else "is-open"
    if card["verdict"] == "RESOLVED":
        reading = (
            f"These two systems disagree on {total} of {comparison['n_items']} instances, "
            f"running {favour_a} to {favour_b}. That edge of {edge} resolves the comparison at "
            f"this correction level."
        )
    else:
        reading = (
            f"These two systems disagree on {total} of {comparison['n_items']} instances, and "
            f"the disagreement runs {favour_a} to {favour_b}. That edge of {edge} does not "
            f"resolve the comparison at this correction level; the observed test does not "
            f"determine which system is better."
        )

    statistics = [
        ("Statistic", "exact McNemar, two-sided"),
        ("Convention", f"{test['convention']}, not mid-p"),
        ("p-value", _num(test["p_value"], 3)),
    ]
    if test["adjusted_p_value"] is not None:
        statistics.append(("Holm-adjusted p", _num(test["adjusted_p_value"], 3)))
    statistics += [
        ("Alpha", _precise(test["alpha"])),
        ("Decision rule", test["decision_rule"]),
        ("Ruler threshold", f"{_precise(ruler['threshold'])}, {ruler['threshold_basis']}"),
        (
            "Discordance rate",
            f"{_num(mde['discordance_rate'], 3)}, derived from {favour_a} plus {favour_b} over "
            f"{comparison['n_items']}",
        ),
    ]
    if mde["status"] == "attainable":
        statistics.append(
            (
                "MDE",
                f"{_num(mde['instances'], 1)} instances at alpha {_precise(mde['alpha'])}, "
                f"power {_num(mde['target_power'], 2)}",
            )
        )
    else:
        statistics.append(
            (
                "MDE",
                f"unattainable; power caps at {_num(mde['max_attainable_power'], 3)} against a "
                f"target of {_num(mde['target_power'], 2)}",
            )
        )
    statistics.append(("MDE alpha basis", mde["alpha_basis"]))

    seal = [
        ("source", card["provenance"]["source"]),
        ("revision", card["provenance"]["pinned_revision"]),
        ("fetched", card["provenance"]["fetch_date"]),
        ("instrument", comparison["instrument"]),
    ]
    if card["provenance"]["deviations"]:
        seal.append(("applies to secondary figures", ", ".join(card["provenance"]["deviations"])))

    return (
        f'<article class="card" aria-labelledby="pair-{slug}">\n'
        f'  <hr class="card-rail {rail}">\n'
        f"  <section>\n"
        f'    <h2 class="eyebrow" id="pair-{slug}">Pair verdict: {label}</h2>\n'
        f'    <p class="verdict-stamp {rail}">{escape(card["verdict"])}</p>\n'
        f'    <p class="reading">{escape(reading)}</p>\n'
        f"  </section>\n"
        f"  <section>\n"
        f'    <p class="eyebrow">Where they disagree</p>\n'
        f"{_pair_body(card)}\n"
        f"  </section>\n"
        f"  <section>\n"
        f"    <details>\n"
        f"      <summary>Statistics</summary>\n"
        f"{_kv(statistics)}\n"
        f"    </details>\n"
        f"  </section>\n"
        f"  <section>\n"
        f'    <p class="eyebrow">Provenance</p>\n'
        f"{_seal(seal)}\n"
        f"  </section>\n"
        f"</article>"
    )


def render_family_card(card: dict) -> str:
    """The family summary card, as an `article` fragment. Carries no verdict stamp."""
    validate_card(card)
    finding = card["family_finding"]
    headline, limit, observed = finding["headline"], finding["limit"], finding["observed"]

    statistics = [
        ("Statistic", "exact McNemar, two-sided"),
        ("Convention", finding["criterion"]["convention"]),
        ("Correction", f"Holm, alpha {_precise(finding['criterion']['alpha'])}"),
        ("First critical value", _precise(finding["criterion"]["threshold"])),
    ]
    disclosure = finding["progressive_disclosure"]
    if disclosure["secondary_family_size"] is not None:
        statistics += [
            ("Secondary family size", str(disclosure["secondary_family_size"])),
            ("Secondary gateway floor", str(disclosure["secondary_family_floor"])),
        ]
    statistics.append(("Conditional on", "; ".join(finding["conditionality"])))

    seal = [
        ("source", card["provenance"]["source"]),
        ("revision", card["provenance"]["pinned_revision"]),
        ("fetched", card["provenance"]["fetch_date"]),
        ("headline caveats", ", ".join(finding["disclosure"]["applies_to_headline"]) or "none"),
        # D7 narrows D4 to the observed figures, so the card must show that it applies to them.
        # Rendering only the headline caveats made a real disclosure invisible on the face.
        (
            "observed figure caveats",
            ", ".join(finding["disclosure"]["applies_to_secondary"]) or "none",
        ),
    ]
    if card["provenance"].get("secondary_source"):
        seal.append(
            (
                "observed figures from",
                f"{card['provenance']['secondary_source']} "
                f"{card['provenance']['secondary_revision']}",
            )
        )

    floor_label = limit["floor_label"].split(",")[0]
    return (
        f'<article class="card" aria-labelledby="family-summary">\n'
        f'  <hr class="card-rail">\n'
        f"  <section>\n"
        f'    <h2 class="eyebrow" id="family-summary">Benchmark resolving power</h2>\n'
        f'    <p class="banner-figure"><b>{headline["separable_count"]} of '
        f"{headline['family_size']}</b> adjacent pairs separable</p>\n"
        f'    <p class="banner-sub">Separable means '
        f"{escape(finding['definitions']['separable'])}</p>\n"
        f'    <p class="scope-line">{escape(finding["scope"]["comparisons"].capitalize())}. '
        f"{escape(finding['scope']['excludes'].capitalize())}.</p>\n"
        f"  </section>\n"
        f"  <section>\n"
        f'    <p class="eyebrow">The limit, and what follows from it</p>\n'
        f'    <dl class="pairing">\n'
        f"      <dt>{escape(floor_label.capitalize())}</dt>"
        f"<dd>{limit['first_rejection_gap_floor']}</dd>\n"
        f"      <dt>{escape(limit['observed_extreme_label'].capitalize())}</dt>"
        f"<dd>{limit['observed_extreme']}</dd>\n"
        f"    </dl>\n"
        f'    <p class="what-would-it-take">{escape(limit["inference"].capitalize())}.</p>\n'
        f"  </section>\n"
        f"  <section>\n"
        f'    <p class="eyebrow">Observed, for contrast</p>\n'
        f'    <dl class="pairing">\n'
        f"      <dt>Resolved by the observed test</dt>"
        f"<dd>{observed['resolved_count']} of {headline['family_size']}</dd>\n"
        f"      <dt>Decision rule</dt><dd>{escape(observed['decision_rule'])}</dd>\n"
        f"      <dt>Separability basis</dt><dd>{escape(finding['separability_basis'])}</dd>\n"
        f"    </dl>\n"
        f"  </section>\n"
        f"  <section>\n"
        f"    <details>\n"
        f"      <summary>Statistics</summary>\n"
        f"{_kv(statistics)}\n"
        f"    </details>\n"
        f"  </section>\n"
        f"  <section>\n"
        f'    <p class="eyebrow">Provenance</p>\n'
        f"{_seal(seal)}\n"
        f"  </section>\n"
        f"</article>"
    )


def render_pair_table(columns, rows, *, heading: str, disclosure: str) -> str:
    """The pair table as an HTML fragment, in the approved fixtures/table_reference.html shape.

    Takes already-rendered row strings from reporting.findings_pair_rows, so the README markdown
    table and this table are two renderings of one projection and cannot disagree about a pair.
    The block wrapper is not decoration: render_document joins fragments into a flex column with a
    gap, so a page-level note would sit away from its own table and outside the surface that
    qualifies it.

    The reference also names the table's parts with `data-element`, for review only; those
    attributes are review annotations rather than renderer output (the accompanying comment in
    card.css makes the same point for the block), so nothing here emits them.
    """
    columns = tuple(columns)
    if len(set(columns)) != len(columns):
        raise ValueError(f"duplicate column names: {columns!r}")
    # Materialized once, up front. rows is untyped and may be a generator; enumerate() below
    # would otherwise drain it before the body comprehension further down ever saw it, which let
    # a generator argument through validation for free and rendered an empty <tbody>, silently.
    rows = [tuple(row) for row in rows]
    for index, row in enumerate(rows):
        if len(row) != len(columns):
            raise ValueError(
                f"row {index} has width {len(row)}, expected {len(columns)} to match the columns"
            )
    # columns and rows are untyped and may hand back non-string cells (an int rank, say), so each
    # is coerced through str() before escape(); heading and disclosure are typed str in the
    # signature above and need no such coercion.
    header = "".join(f'<th scope="col">{escape(str(name))}</th>' for name in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        '<div class="pair-table-block">'
        '<div class="pair-table-scroll" tabindex="0" role="region" '
        'aria-label="Pair table">'
        '<table class="pair-table">'
        f"<caption>{escape(heading)}</caption>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
        f'<p class="pair-table-note">{escape(disclosure)}</p>'
        "</div>"
    )


def render_plain_language_finding(block: dict) -> str:
    """The finding layer, as an `article` fragment, in the approved fixtures/page_reference.html
    Tier 1 shape. Spec sections 10 and 11.

    Every figure prints through render_number at the path PLAIN_LANGUAGE_SOURCES declares for it,
    the same mapping the crosswalk builds its rules from, so a rendered figure and a validated
    figure cannot come from different places while both look right.

    The comparison is two `.lead-scale-row` elements, one `is-observed` and one `is-mark`, each
    wrapping its own `.strip` and `.strip-legend`: the observed lead and the mark are drawn on one
    scale whose full length is the mark, so the reader sees the lead stop short of it rather than
    reading that it does. card.css keys the observed colour off `.lead-scale-row.is-observed
    .strip-a`, so the modifier belongs on the row, not on the strip itself.
    """

    def figure(leaf: str, value) -> str:
        return escape(render_number(PLAIN_LANGUAGE_SOURCES[leaf], value))

    headline, comparison = block["headline"], block["comparison"]
    lead = figure("comparison.largest_lead", comparison["largest_lead"])
    mark = figure("comparison.opening_lead", comparison["opening_lead"])
    # The shortfall is a layout quantity, drawn but never read as a figure: it has no legend of
    # its own and so no declared source path to print it through render_number. It also bypasses
    # escape(): the subtraction runs on the two type-checked ints above rather than on
    # caller-supplied text (and raises on anything that is not numeric), so the result can only
    # ever be a plain integer, and there is nothing in an integer's str() for escape() to touch.
    shortfall = comparison["opening_lead"] - comparison["largest_lead"]
    unit = escape(comparison["unit"])
    non_claims = "".join(f"<li>{escape(text)}</li>" for text in block["non_claims"])
    return (
        '<article class="card finding" aria-labelledby="finding-lead">\n'
        '  <hr class="card-rail">\n'
        "  <section>\n"
        f'    <p class="finding-lead" id="finding-lead">{escape(block["lead"])}</p>\n'
        f'    <p class="banner-figure"><b>{figure("headline.count", headline["count"])} of '
        f"{figure('headline.of', headline['of'])}</b> {escape(headline['unit'])} "
        "showed a reliable difference</p>\n"
        f'    <p class="scope-line">{escape(block["scope"])}</p>\n'
        "  </section>\n"
        "  <section>\n"
        '    <div class="lead-scale">\n'
        '      <div class="lead-scale-row is-observed">\n'
        '        <div class="strip" aria-hidden="true">\n'
        f'          <div class="strip-a" style="flex: {lead};"></div>\n'
        f'          <div class="strip-b" style="flex: {shortfall};"></div>\n'
        "        </div>\n"
        f'        <p class="strip-legend"><span>{escape(comparison["largest_lead_label"])}'
        f"</span><span>{lead} {unit}</span></p>\n"
        "      </div>\n"
        '      <div class="lead-scale-row is-mark">\n'
        '        <div class="strip" aria-hidden="true">\n'
        f'          <div class="strip-a" style="flex: {mark};"></div>\n'
        "        </div>\n"
        f'        <p class="strip-legend"><span>{escape(comparison["opening_lead_label"])}'
        f"</span><span>{mark} {unit}</span></p>\n"
        "      </div>\n"
        "    </div>\n"
        f'    <p class="reading">{escape(block["analogy"])}</p>\n'
        f'    <p class="reading">{escape(block["task_level_note"])}</p>\n'
        "  </section>\n"
        "  <section>\n"
        f'    <ul class="non-claims">{non_claims}</ul>\n'
        "  </section>\n"
        "</article>"
    )


def render_card(card: dict) -> str:
    """Render whichever card kind was passed."""
    kind = card.get("card_kind")
    if kind == CARD_PAIR:
        return render_pair_card(card)
    if kind == CARD_FAMILY:
        return render_family_card(card)
    raise ValueError(f"unknown card_kind {kind!r}")


def render_document(fragments: list[str], *, title: str) -> str:
    """Wrap rendered cards in a self-contained page.

    Self-contained is a requirement rather than a convenience: cards are screenshot-ready
    artifacts, and an external stylesheet would render them differently depending on where the
    file was opened.
    """
    body = "\n\n".join(fragments)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>\n{CARD_STYLESHEET}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<main class="page">\n{body}\n</main>\n'
        "</body>\n"
        "</html>\n"
    )
