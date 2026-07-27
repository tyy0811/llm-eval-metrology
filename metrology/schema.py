"""The long-format label table, normative per PLAN.md section 4.

One row per label. The uniqueness key is (`item_id`, `system`, `run`, `instrument`).

The design point is that **the anchor is a role assigned per call, never a hardcoded column**.
Gold-only estimation means "rows whose instrument equals the declared anchor", naive estimation
means "rows from one declared cheap instrument", and both name their instruments explicitly. A
wide table with one column per instrument would make "which column is gold" a structural property
instead, which is why this shape is normative rather than a preference.

Rows are stored in canonical key order so that anything serialized downstream is byte-stable,
per the deterministic-serialization rule in `docs/DECISIONS.md` D0.9.
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

#: Columns every row must carry. `run` is required by the schema but defaults to 0 on input,
#: because single-evaluation data is the common case and an explicit 0 adds no information.
REQUIRED_COLUMNS: tuple[str, ...] = ("item_id", "system", "instrument", "label")

#: The uniqueness key. Repeated measurement lives in `run`, so the same item scored twice by the
#: same instrument is legal, and the same (item, system, run, instrument) twice is not.
KEY_COLUMNS: tuple[str, ...] = ("item_id", "system", "run", "instrument")

#: Columns that may be absent entirely, but not present on only some rows.
OPTIONAL_COLUMNS: tuple[str, ...] = ("cost", "category")


class SchemaError(ValueError):
    """A label table is malformed.

    Raised rather than warned, because every failure this class reports would otherwise produce
    a confident wrong number downstream instead of a stack trace.
    """


@dataclass(frozen=True, eq=False)
class PairedLabels:
    """Two systems' labels aligned item by item under one named instrument.

    Carries the system and instrument names so that a downstream test or card cannot report a
    comparison without saying what was compared and what measured it.
    """

    item_id: np.ndarray
    label_a: np.ndarray
    label_b: np.ndarray
    system_a: str
    system_b: str
    instrument: str

    @property
    def n_items(self) -> int:
        return int(self.item_id.shape[0])


@dataclass(frozen=True, eq=False)
class LabelTable:
    """A validated long-format table of labels, in canonical key order."""

    item_id: np.ndarray
    system: np.ndarray
    run: np.ndarray
    instrument: np.ndarray
    label: np.ndarray
    cost: np.ndarray | None = None
    category: np.ndarray | None = None

    @property
    def n_rows(self) -> int:
        return int(self.item_id.shape[0])

    @property
    def instruments(self) -> tuple[str, ...]:
        """Every instrument present, sorted. Which one is the anchor is not stored here."""
        return tuple(sorted(set(self.instrument.tolist())))

    @property
    def systems(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.system.tolist())))

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.item_id.tolist())))

    def _take(self, mask: np.ndarray) -> LabelTable:
        """Rows selected by a boolean mask, preserving canonical order and optional columns."""
        return LabelTable(
            item_id=self.item_id[mask],
            system=self.system[mask],
            run=self.run[mask],
            instrument=self.instrument[mask],
            label=self.label[mask],
            cost=None if self.cost is None else self.cost[mask],
            category=None if self.category is None else self.category[mask],
        )

    def subset(self, *, instrument: str | None = None, system: str | None = None) -> LabelTable:
        """Rows matching the given instrument and system.

        An empty result is an error rather than an empty table, because every caller that
        subsets is asserting the selection exists.
        """
        mask = np.ones(self.n_rows, dtype=bool)
        if instrument is not None:
            mask &= self.instrument == instrument
        if system is not None:
            mask &= self.system == system
        if not mask.any():
            criteria = ", ".join(
                f"{name}={value!r}"
                for name, value in (("instrument", instrument), ("system", system))
                if value is not None
            )
            raise SchemaError(f"subset({criteria}) matched no rows")
        return self._take(mask)

    def require_anchor(self, anchor: str) -> LabelTable:
        """Rows produced by the declared anchor instrument.

        The anchor is a role assigned per call. This method exists so that a mistyped or absent
        anchor fails here, loudly, rather than silently estimating from an empty set.
        """
        if anchor not in self.instruments:
            available = ", ".join(repr(name) for name in self.instruments)
            raise SchemaError(
                f"declared anchor {anchor!r} has no rows; instruments present are {available}"
            )
        return self.subset(instrument=anchor)

    def paired(self, system_a: str, system_b: str, *, instrument: str) -> PairedLabels:
        """Labels for two systems aligned on the items both were scored on.

        Refuses to guess: an item missing from either system, or repeated runs that would need
        averaging, raises rather than being silently dropped or collapsed.
        """
        for system in (system_a, system_b):
            if system not in self.systems:
                available = ", ".join(repr(name) for name in self.systems)
                raise SchemaError(f"unknown system {system!r}; systems present are {available}")
        if instrument not in self.instruments:
            available = ", ".join(repr(name) for name in self.instruments)
            raise SchemaError(
                f"unknown instrument {instrument!r}; instruments present are {available}"
            )

        scoped = self.subset(instrument=instrument)
        by_system: dict[str, dict[str, float]] = {system_a: {}, system_b: {}}
        for item, system, label in zip(
            scoped.item_id.tolist(), scoped.system.tolist(), scoped.label.tolist(), strict=True
        ):
            if system not in by_system:
                continue
            if item in by_system[system]:
                raise SchemaError(
                    f"item {item!r} has more than one run for system {system!r} under "
                    f"instrument {instrument!r}; use the clustered variant rather than "
                    "averaging runs into a single paired comparison"
                )
            by_system[system][item] = label

        only_a = sorted(set(by_system[system_a]) - set(by_system[system_b]))
        only_b = sorted(set(by_system[system_b]) - set(by_system[system_a]))
        if only_a or only_b:
            raise SchemaError(
                f"broken pairing under instrument {instrument!r}: "
                f"{len(only_a)} item(s) only in {system_a!r} {only_a[:3]}, "
                f"{len(only_b)} item(s) only in {system_b!r} {only_b[:3]}"
            )

        shared = sorted(by_system[system_a])
        return PairedLabels(
            item_id=np.asarray(shared),
            label_a=np.asarray([by_system[system_a][item] for item in shared], dtype=np.float64),
            label_b=np.asarray([by_system[system_b][item] for item in shared], dtype=np.float64),
            system_a=system_a,
            system_b=system_b,
            instrument=instrument,
        )

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, object]]) -> LabelTable:
        """Build a validated table from an iterable of row mappings."""
        materialized = [dict(row) for row in rows]
        if not materialized:
            raise SchemaError("label table has no rows")

        _check_required_columns(materialized)
        optional_present = _check_optional_columns(materialized)

        item_id = [str(row["item_id"]) for row in materialized]
        system = [str(row["system"]) for row in materialized]
        instrument = [str(row["instrument"]) for row in materialized]
        run = [_as_run(row.get("run", 0), index) for index, row in enumerate(materialized)]
        label = [_as_label(row["label"], index) for index, row in enumerate(materialized)]

        keys = list(zip(item_id, system, run, instrument, strict=True))
        _check_unique(keys)

        order = sorted(range(len(keys)), key=lambda index: keys[index])

        def ordered(values: Sequence, dtype=None) -> np.ndarray:
            picked = [values[index] for index in order]
            return np.asarray(picked, dtype=dtype) if dtype else np.asarray(picked)

        return cls(
            item_id=ordered(item_id),
            system=ordered(system),
            run=ordered(run, dtype=np.int64),
            instrument=ordered(instrument),
            label=ordered(label, dtype=np.float64),
            cost=(
                ordered([float(row["cost"]) for row in materialized], dtype=np.float64)
                if "cost" in optional_present
                else None
            ),
            category=(
                ordered([str(row["category"]) for row in materialized])
                if "category" in optional_present
                else None
            ),
        )


def wide_to_long(
    rows: Iterable[Mapping[str, object]],
    *,
    instruments: Sequence[str],
    id_columns: Sequence[str] = ("item_id", "system", "run"),
) -> LabelTable:
    """Convert a wide table, one column per instrument, into the long format.

    Instruments are **named, never inferred** from the leftover columns. Inference is how a
    notes or metadata column silently becomes an instrument emitting garbage labels.

    A blank cell means unlabeled and produces no row. That is the shape PPI needs: the anchor
    labels a subset while the cheap instrument scores the whole pool, so most anchor cells are
    legitimately empty. Filling them with 0 would invent labels.
    """
    materialized = [dict(row) for row in rows]
    if not materialized:
        raise SchemaError("wide table has no rows")

    for instrument in instruments:
        missing = [index for index, row in enumerate(materialized) if instrument not in row]
        if missing:
            raise SchemaError(
                f"instrument column {instrument!r} is missing from "
                f"{len(missing)} of {len(materialized)} wide rows"
            )

    long_rows: list[dict[str, object]] = []
    for index, row in enumerate(materialized):
        base = {name: row[name] for name in id_columns if name in row}
        for instrument in instruments:
            value = row[instrument]
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            label = _wide_cell_to_label(value, instrument=instrument, index=index)
            long_rows.append({**base, "instrument": instrument, "label": label})

    if not long_rows:
        raise SchemaError("wide table produced no labels; every instrument cell was blank")
    return LabelTable.from_rows(long_rows)


def _wide_cell_to_label(value: object, *, instrument: str, index: int) -> float:
    """Convert one wide cell, naming the column when it is not a label at all.

    Numeric strings are accepted because wide tables usually arrive from CSVs. A non-numeric
    string names the offending instrument column, since the usual cause is a metadata column
    such as `notes` being declared as an instrument, and "non-numeric label" alone would leave
    the caller hunting for which column it meant.
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SchemaError(
            f"wide row {index} has a non-numeric value {value!r} under instrument "
            f"{instrument!r}; declared instrument columns must contain labels"
        ) from exc


def load_long_csv(path) -> LabelTable:
    """Read a long-format CSV into a validated table.

    CSV delivers every field as a string, so numeric columns are converted here rather than by
    loosening `LabelTable.from_rows`, which stays strict because a string label in a Python
    mapping is a caller bug rather than a format artifact.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        for column in REQUIRED_COLUMNS:
            if column not in header:
                raise SchemaError(f"csv is missing required column '{column}'; header is {header}")
        rows = [_parse_csv_row(row, index) for index, row in enumerate(reader)]

    if not rows:
        raise SchemaError(f"csv at {path} has a header but no rows")
    return LabelTable.from_rows(rows)


def _parse_csv_row(row: Mapping[str, str], index: int) -> dict[str, object]:
    parsed: dict[str, object] = {
        "item_id": row["item_id"],
        "system": row["system"],
        "instrument": row["instrument"],
        "label": _parse_number(row["label"], index, "label"),
    }
    if row.get("run") not in (None, ""):
        parsed["run"] = _parse_number(row["run"], index, "run")
    if row.get("cost") not in (None, ""):
        parsed["cost"] = _parse_number(row["cost"], index, "cost")
    if row.get("category") not in (None, ""):
        parsed["category"] = row["category"]
    return parsed


def _parse_number(text: str, index: int, column: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"csv row {index} has a non-numeric {column} {text!r}") from exc


def _check_required_columns(rows: Sequence[Mapping[str, object]]) -> None:
    for index, row in enumerate(rows):
        for column in REQUIRED_COLUMNS:
            if column not in row:
                raise SchemaError(f"row {index} is missing required column '{column}'")


def _check_optional_columns(rows: Sequence[Mapping[str, object]]) -> set[str]:
    """Optional columns must be present on every row or on none, never on some."""
    present: set[str] = set()
    for column in OPTIONAL_COLUMNS:
        count = sum(1 for row in rows if column in row)
        if count == 0:
            continue
        if count != len(rows):
            raise SchemaError(
                f"optional column '{column}' is present on {count} of {len(rows)} rows; "
                "supply it for every row or for none"
            )
        present.add(column)
    return present


def _as_run(value: object, index: int) -> int:
    try:
        run = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"row {index} has a non-integer run {value!r}") from exc
    if run < 0:
        raise SchemaError(f"row {index} has a negative run {run}")
    return run


def _as_label(value: object, index: int) -> float:
    if isinstance(value, str):
        raise SchemaError(f"row {index} has a non-numeric label {value!r}")
    try:
        label = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"row {index} has a non-numeric label {value!r}") from exc
    if math.isnan(label):
        raise SchemaError(f"row {index} has a nan label")
    if math.isinf(label):
        raise SchemaError(f"row {index} has an infinite label")
    return label


def _check_unique(keys: Sequence[tuple]) -> None:
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        shown = ", ".join(repr(key) for key in sorted(duplicates)[:3])
        raise SchemaError(
            f"duplicate rows for {len(duplicates)} key(s) on ({', '.join(KEY_COLUMNS)}): {shown}"
        )
