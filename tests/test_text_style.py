"""Authored text carries no em dashes or en dashes, and the checker that enforces it works.

The forbidden characters are built with chr() here for the same reason as in the checker: a
literal occurrence in this file would be a violation of the rule under test.
"""

from __future__ import annotations

from pathlib import Path

import check_dashes

REPO_ROOT = Path(__file__).resolve().parent.parent

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def test_repo_authored_text_is_clean() -> None:
    found, checked = check_dashes.scan([REPO_ROOT])

    assert checked > 0, "the checker walked no files, so a pass would be meaningless"
    assert [v.render() for v in found] == []


def test_checker_exits_zero_on_the_real_repo() -> None:
    assert check_dashes.main([str(REPO_ROOT)]) == 0


def test_em_dash_is_flagged(tmp_path: Path) -> None:
    doc = tmp_path / "note.md"
    doc.write_text(f"a sentence {EM_DASH} with a dash\n", encoding="utf-8")

    found, _ = check_dashes.scan([doc])

    assert len(found) == 1
    assert found[0].name == "em dash"
    assert found[0].lineno == 1


def test_en_dash_is_flagged(tmp_path: Path) -> None:
    doc = tmp_path / "range.md"
    doc.write_text(f"1,600{EN_DASH}1,700 summaries\n", encoding="utf-8")

    found, _ = check_dashes.scan([doc])

    assert [v.name for v in found] == ["en dash"]


def test_range_written_with_to_is_clean(tmp_path: Path) -> None:
    doc = tmp_path / "ok.md"
    doc.write_text("roughly 1,600 to 1,700 summaries\n", encoding="utf-8")

    found, _ = check_dashes.scan([doc])

    assert found == []


def test_hyphen_and_minus_are_not_flagged(tmp_path: Path) -> None:
    doc = tmp_path / "hyphens.md"
    doc.write_text("gold-only, cheap-only, and a table separator |---|\n", encoding="utf-8")

    found, _ = check_dashes.scan([doc])

    assert found == []


def test_violations_are_located_by_line_and_column(tmp_path: Path) -> None:
    doc = tmp_path / "multi.md"
    doc.write_text(f"clean line\nab{EM_DASH}cd\n", encoding="utf-8")

    found, _ = check_dashes.scan([doc])

    assert (found[0].lineno, found[0].column) == (2, 3)


def test_checker_exits_nonzero_when_text_is_dirty(tmp_path: Path) -> None:
    doc = tmp_path / "dirty.md"
    doc.write_text(f"bad {EM_DASH} text\n", encoding="utf-8")

    assert check_dashes.main([str(doc)]) == 1


def test_binary_and_unknown_extensions_are_skipped(tmp_path: Path) -> None:
    blob = tmp_path / "image.png"
    blob.write_bytes(EM_DASH.encode("utf-8"))

    found, checked = check_dashes.scan([tmp_path])

    assert found == []
    assert checked == 0
