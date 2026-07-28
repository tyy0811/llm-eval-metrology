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

#: Columns that may be absent, on some rows or on all of them. See `_optional_columns_present`
#: for why partial presence is legal rather than an error.
OPTIONAL_COLUMNS: tuple[str, ...] = ("cost", "category")

#: Sentinel for an absent category. `cost` uses nan; category is a string column, so absence
#: needs a value that a real category would never take.
MISSING_CATEGORY: str = ""


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

    def __post_init__(self) -> None:
        """Enforce the invariant here, not at the call sites that consume it.

        `LabelTable.paired` is not the only way to build one. Without this, arrays of unequal
        length broadcast inside a downstream test and produce a plausible wrong discordance
        count rather than an error, which is the worst possible failure mode for this repo.
        """
        if self.system_a == self.system_b:
            raise SchemaError(
                f"cannot pair system {self.system_a!r} with itself; the difference is zero "
                "by construction"
            )

        for name in ("item_id", "label_a", "label_b"):
            values = np.array(getattr(self, name), copy=True)
            if values.ndim != 1:
                raise SchemaError(f"{name} must be one-dimensional, got shape {values.shape}")
            values.setflags(write=False)
            object.__setattr__(self, name, values)

        lengths = {name: getattr(self, name).shape[0] for name in ("item_id", "label_a", "label_b")}
        if len(set(lengths.values())) != 1:
            raise SchemaError(f"paired columns have mismatched length: {lengths}")
        if self.item_id.shape[0] == 0:
            raise SchemaError("paired comparison has no items")

        items = self.item_id.tolist()
        if len(set(items)) != len(items):
            duplicates = sorted({item for item in items if items.count(item) > 1})
            raise SchemaError(f"paired comparison has duplicate items: {duplicates[:3]}")

        for name in ("label_a", "label_b"):
            labels = getattr(self, name)
            if not np.all(np.isfinite(labels)):
                raise SchemaError(f"{name} contains a value that is not finite")

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

    def __post_init__(self) -> None:
        """Enforce the validated-table invariant however the instance was built.

        `from_rows` is not the only door: `_take` builds instances directly, and so can a
        caller. Validation therefore lives here rather than in the constructor helper, so that
        "this object exists" and "this object is valid" mean the same thing.

        Arrays are copied and then marked read-only. `frozen=True` protects the attribute
        binding only; without this a caller could rewrite a validated label to nan in place and
        every downstream estimate would inherit it.
        """
        for name in ("item_id", "system", "run", "instrument", "label", "cost", "category"):
            values = getattr(self, name)
            if values is None:
                continue
            copied = np.array(values, copy=True)
            copied.setflags(write=False)
            object.__setattr__(self, name, copied)

        _validate_columns(self)

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

    def paired(
        self, system_a: str, system_b: str, *, instrument: str, run: int | None = None
    ) -> PairedLabels:
        """Labels for two systems aligned on the items both were scored on.

        Refuses to guess. A system compared with itself, a system never touched by the named
        instrument, an item missing from one side, or an undeclared choice of run all raise
        rather than producing a comparison the caller did not ask for.

        `run` is optional only when the scoped rows carry exactly one run value. With repeated
        measurement present the caller must declare which run to compare, or use the clustered
        variant, because averaging runs would discard the clustering the data carries.
        """
        if system_a == system_b:
            raise SchemaError(
                f"cannot pair system {system_a!r} with itself; the difference is zero by "
                "construction and the comparison answers no question"
            )
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
        pair_mask = np.isin(scoped.system, [system_a, system_b])
        if not pair_mask.any():
            raise SchemaError(
                f"neither {system_a!r} nor {system_b!r} was scored by instrument "
                f"{instrument!r}; that instrument scored {', '.join(map(repr, scoped.systems))}"
            )
        scoped = scoped._take(pair_mask)

        for system in (system_a, system_b):
            if system not in scoped.systems:
                raise SchemaError(
                    f"system {system!r} has no rows under instrument {instrument!r}, "
                    "so there is nothing to pair against"
                )

        runs_present = sorted(set(scoped.run.tolist()))
        if run is None:
            if len(runs_present) > 1:
                raise SchemaError(
                    f"rows for {system_a!r} and {system_b!r} under instrument {instrument!r} "
                    f"span runs {runs_present}; declare run= to choose one, or use the "
                    "clustered variant, rather than averaging runs into a single comparison"
                )
        else:
            if run not in runs_present:
                raise SchemaError(
                    f"run {run!r} is absent under instrument {instrument!r}; "
                    f"runs present are {runs_present}"
                )
            scoped = scoped._take(scoped.run == run)

        by_system: dict[str, dict[str, float]] = {system_a: {}, system_b: {}}
        for item, system, label in zip(
            scoped.item_id.tolist(), scoped.system.tolist(), scoped.label.tolist(), strict=True
        ):
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
        optional_present = _optional_columns_present(materialized)

        item_id = [
            _as_key_field(row["item_id"], i, "item_id") for i, row in enumerate(materialized)
        ]
        system = [_as_key_field(row["system"], i, "system") for i, row in enumerate(materialized)]
        instrument = [
            _as_key_field(row["instrument"], i, "instrument") for i, row in enumerate(materialized)
        ]
        run = [_as_run(row.get("run", 0), index) for index, row in enumerate(materialized)]
        label = [_as_label(row["label"], index) for index, row in enumerate(materialized)]

        keys = list(zip(item_id, system, run, instrument, strict=True))
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
                ordered(
                    [_optional_cost(row, index) for index, row in enumerate(materialized)],
                    dtype=np.float64,
                )
                if "cost" in optional_present
                else None
            ),
            category=(
                ordered([str(row.get("category", MISSING_CATEGORY)) for row in materialized])
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


def _optional_columns_present(rows: Sequence[Mapping[str, object]]) -> set[str]:
    """Which optional columns appear on at least one row.

    Partial presence is legal and expected: Experiment 2 puts a costed judge and an uncosted
    human anchor in one table, so requiring every row to carry `cost` would force a caller to
    invent values for rows where the concept does not apply. Absent cells become `nan` for
    `cost` and `MISSING_CATEGORY` for `category`, both of which are distinguishable from a
    real value.
    """
    return {column for column in OPTIONAL_COLUMNS if any(column in row for row in rows)}


def _optional_cost(row: Mapping[str, object], index: int) -> float:
    if "cost" not in row or row["cost"] is None:
        return math.nan
    try:
        return float(row["cost"])  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"row {index} has a non-numeric cost {row['cost']!r}") from exc


def _as_key_field(value: object, index: int, column: str) -> str:
    """Identifiers must be real, not stringified absences.

    `str(None)` is `"None"`, which looks like a perfectly good item id and would silently join
    every missing identifier into one bucket.
    """
    if value is None:
        raise SchemaError(f"row {index} has a null {column}")
    if isinstance(value, bool):
        raise SchemaError(f"row {index} has a boolean {column} {value!r}")
    text = str(value)
    if not text.strip():
        raise SchemaError(f"row {index} has a blank {column}")
    return text


def _as_run(value: object, index: int) -> int:
    """Run indices are exact nonnegative integers.

    `int()` would truncate 1.5 to 1 and coerce True to 1, either of which merges two distinct
    runs into one and corrupts the uniqueness key without any error surfacing.
    """
    if isinstance(value, bool):
        raise SchemaError(f"row {index} has a boolean run {value!r}; run must be an integer")
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError as exc:
            raise SchemaError(f"row {index} has a non-integer run {value!r}") from exc
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SchemaError(f"row {index} has a non-finite run {value!r}")
        if not value.is_integer():
            raise SchemaError(
                f"row {index} has a fractional run {value!r}; run must be an exact integer"
            )
        value = int(value)
    if not isinstance(value, int):
        raise SchemaError(f"row {index} has a non-integer run {value!r}")
    if value < 0:
        raise SchemaError(f"row {index} has a negative run {value}")
    return int(value)


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


def _validate_columns(table: LabelTable) -> None:
    """The structural invariant, checked however the table was constructed."""
    lengths = {
        name: getattr(table, name).shape[0]
        for name in ("item_id", "system", "run", "instrument", "label")
    }
    for name in ("cost", "category"):
        values = getattr(table, name)
        if values is not None:
            lengths[name] = values.shape[0]
    if len(set(lengths.values())) != 1:
        raise SchemaError(f"columns have mismatched length: {lengths}")

    if table.n_rows == 0:
        raise SchemaError("label table has no rows")

    if not np.all(np.isfinite(table.label)):
        offending = int(np.argmax(~np.isfinite(table.label)))
        raise SchemaError(f"row {offending} has a nan or infinite label {table.label[offending]!r}")

    for name in ("item_id", "system", "instrument"):
        values = getattr(table, name).tolist()
        blank = [index for index, text in enumerate(values) if not str(text).strip()]
        if blank:
            raise SchemaError(f"rows {blank[:3]} have a blank {name}")

    _check_unique(
        list(
            zip(
                table.item_id.tolist(),
                table.system.tolist(),
                table.run.tolist(),
                table.instrument.tolist(),
                strict=True,
            )
        )
    )
