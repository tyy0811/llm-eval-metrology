"""T2.1: the long-format label table, per PLAN.md section 4.

The table is the boundary contract between instruments and the engine. Its job is to make
the anchor a role assigned per call rather than a hardcoded column, and to fail loudly on the
malformed inputs that would otherwise produce a confident wrong number.
"""

from __future__ import annotations

import numpy as np
import pytest

from metrology.schema import LabelTable, SchemaError, load_long_csv, wide_to_long


def rows_minimal() -> list[dict]:
    return [
        {"item_id": "i2", "system": "A", "instrument": "human", "label": 1},
        {"item_id": "i1", "system": "A", "instrument": "human", "label": 0},
    ]


class TestConstruction:
    def test_from_rows_exposes_row_count(self) -> None:
        table = LabelTable.from_rows(rows_minimal())

        assert table.n_rows == 2

    def test_rows_are_stored_in_canonical_key_order(self) -> None:
        """Deterministic serialization (DECISIONS D0.9 item 5) needs a sort, not input order."""
        table = LabelTable.from_rows(rows_minimal())

        assert table.item_id.tolist() == ["i1", "i2"]
        assert table.label.tolist() == [0.0, 1.0]

    def test_canonical_order_sorts_by_the_full_uniqueness_key(self) -> None:
        table = LabelTable.from_rows(
            [
                {"item_id": "i1", "system": "B", "run": 0, "instrument": "human", "label": 1},
                {"item_id": "i1", "system": "A", "run": 1, "instrument": "human", "label": 1},
                {"item_id": "i1", "system": "A", "run": 0, "instrument": "judge", "label": 1},
                {"item_id": "i1", "system": "A", "run": 0, "instrument": "human", "label": 1},
            ]
        )

        assert list(
            zip(table.system.tolist(), table.run.tolist(), table.instrument.tolist(), strict=True)
        ) == [
            ("A", 0, "human"),
            ("A", 0, "judge"),
            ("A", 1, "human"),
            ("B", 0, "human"),
        ]

    def test_run_defaults_to_zero_when_absent(self) -> None:
        table = LabelTable.from_rows(rows_minimal())

        assert table.run.tolist() == [0, 0]

    def test_labels_are_stored_as_floats(self) -> None:
        """Binary and numeric labels share one column, so the dtype must not depend on input."""
        table = LabelTable.from_rows(rows_minimal())

        assert table.label.dtype.kind == "f"

    def test_optional_columns_are_absent_by_default(self) -> None:
        table = LabelTable.from_rows(rows_minimal())

        assert table.cost is None
        assert table.category is None

    def test_optional_columns_are_preserved_when_supplied(self) -> None:
        table = LabelTable.from_rows(
            [
                {
                    "item_id": "i1",
                    "system": "A",
                    "instrument": "human",
                    "label": 1,
                    "cost": 0.5,
                    "category": "django",
                }
            ]
        )

        assert table.cost.tolist() == [0.5]
        assert table.category.tolist() == ["django"]


class TestValidation:
    def test_missing_required_column_names_the_column(self) -> None:
        with pytest.raises(SchemaError, match="instrument"):
            LabelTable.from_rows([{"item_id": "i1", "system": "A", "label": 1}])

    def test_duplicate_uniqueness_key_is_rejected(self) -> None:
        rows = [
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "human", "label": 1},
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "human", "label": 0},
        ]

        with pytest.raises(SchemaError, match="duplicate"):
            LabelTable.from_rows(rows)

    def test_duplicate_error_identifies_the_offending_key(self) -> None:
        rows = [
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "human", "label": 1},
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "human", "label": 0},
        ]

        with pytest.raises(SchemaError, match="i1"):
            LabelTable.from_rows(rows)

    def test_same_item_different_run_is_not_a_duplicate(self) -> None:
        """Repeated measurement is the point of the run column."""
        rows = [
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "judge", "label": 1},
            {"item_id": "i1", "system": "A", "run": 1, "instrument": "judge", "label": 0},
        ]

        assert LabelTable.from_rows(rows).n_rows == 2

    def test_same_item_different_instrument_is_not_a_duplicate(self) -> None:
        rows = [
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "human", "label": 1},
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "judge", "label": 0},
        ]

        assert LabelTable.from_rows(rows).n_rows == 2

    def test_non_numeric_label_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="label"):
            LabelTable.from_rows(
                [{"item_id": "i1", "system": "A", "instrument": "human", "label": "resolved"}]
            )

    def test_nan_label_is_rejected(self) -> None:
        """A silent nan propagates into every downstream estimate."""
        with pytest.raises(SchemaError, match="nan"):
            LabelTable.from_rows(
                [{"item_id": "i1", "system": "A", "instrument": "human", "label": float("nan")}]
            )

    def test_empty_table_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="no rows"):
            LabelTable.from_rows([])


def rows_paired() -> list[dict]:
    """Two systems scored by one instrument on the same two items."""
    return [
        {"item_id": "i1", "system": "A", "instrument": "hidden-tests", "label": 1},
        {"item_id": "i2", "system": "A", "instrument": "hidden-tests", "label": 0},
        {"item_id": "i1", "system": "B", "instrument": "hidden-tests", "label": 0},
        {"item_id": "i2", "system": "B", "instrument": "hidden-tests", "label": 1},
    ]


class TestInventory:
    def test_instruments_are_unique_and_sorted(self) -> None:
        table = LabelTable.from_rows(
            [
                {"item_id": "i1", "system": "A", "instrument": "judge", "label": 1},
                {"item_id": "i1", "system": "A", "instrument": "human", "label": 1},
                {"item_id": "i2", "system": "A", "instrument": "judge", "label": 1},
            ]
        )

        assert table.instruments == ("human", "judge")

    def test_systems_are_unique_and_sorted(self) -> None:
        assert LabelTable.from_rows(rows_paired()).systems == ("A", "B")

    def test_items_are_unique_and_sorted(self) -> None:
        assert LabelTable.from_rows(rows_paired()).items == ("i1", "i2")


class TestAnchor:
    def test_declared_anchor_with_no_rows_is_rejected(self) -> None:
        table = LabelTable.from_rows(rows_paired())

        with pytest.raises(SchemaError, match="human"):
            table.require_anchor("human")

    def test_anchor_error_lists_the_instruments_that_do_exist(self) -> None:
        table = LabelTable.from_rows(rows_paired())

        with pytest.raises(SchemaError, match="hidden-tests"):
            table.require_anchor("human")

    def test_declared_anchor_with_rows_returns_only_those_rows(self) -> None:
        rows = rows_paired() + [{"item_id": "i1", "system": "A", "instrument": "judge", "label": 0}]
        table = LabelTable.from_rows(rows)

        anchored = table.require_anchor("hidden-tests")

        assert anchored.n_rows == 4
        assert set(anchored.instrument.tolist()) == {"hidden-tests"}


class TestSubset:
    def test_subset_by_instrument_keeps_matching_rows(self) -> None:
        rows = rows_paired() + [{"item_id": "i1", "system": "A", "instrument": "judge", "label": 0}]

        subset = LabelTable.from_rows(rows).subset(instrument="judge")

        assert subset.n_rows == 1
        assert subset.item_id.tolist() == ["i1"]

    def test_subset_by_system_keeps_matching_rows(self) -> None:
        subset = LabelTable.from_rows(rows_paired()).subset(system="B")

        assert subset.n_rows == 2
        assert set(subset.system.tolist()) == {"B"}

    def test_subset_preserves_optional_columns(self) -> None:
        rows = [
            {"item_id": "i1", "system": "A", "instrument": "human", "label": 1, "cost": 2.0},
            {"item_id": "i2", "system": "A", "instrument": "judge", "label": 1, "cost": 3.0},
        ]

        subset = LabelTable.from_rows(rows).subset(instrument="judge")

        assert subset.cost.tolist() == [3.0]

    def test_subset_matching_nothing_is_rejected(self) -> None:
        """An empty subset is always a bug in the caller's declaration, never a valid result."""
        with pytest.raises(SchemaError, match="no rows"):
            LabelTable.from_rows(rows_paired()).subset(instrument="nonexistent")


class TestPairing:
    def test_paired_returns_labels_aligned_on_shared_items(self) -> None:
        table = LabelTable.from_rows(rows_paired())

        pair = table.paired("A", "B", instrument="hidden-tests")

        assert pair.item_id.tolist() == ["i1", "i2"]
        assert pair.label_a.tolist() == [1.0, 0.0]
        assert pair.label_b.tolist() == [0.0, 1.0]

    def test_paired_rejects_an_item_missing_from_one_system(self) -> None:
        rows = rows_paired() + [
            {"item_id": "i3", "system": "A", "instrument": "hidden-tests", "label": 1}
        ]
        table = LabelTable.from_rows(rows)

        with pytest.raises(SchemaError, match="i3"):
            table.paired("A", "B", instrument="hidden-tests")

    def test_paired_rejects_an_unknown_system(self) -> None:
        table = LabelTable.from_rows(rows_paired())

        with pytest.raises(SchemaError, match="Z"):
            table.paired("A", "Z", instrument="hidden-tests")

    def test_paired_rejects_repeated_runs_and_names_the_clustered_alternative(self) -> None:
        """Averaging over runs silently would discard the clustering the data carries."""
        rows = rows_paired() + [
            {"item_id": "i1", "system": "A", "run": 1, "instrument": "hidden-tests", "label": 0},
            {"item_id": "i1", "system": "B", "run": 1, "instrument": "hidden-tests", "label": 0},
        ]
        table = LabelTable.from_rows(rows)

        with pytest.raises(SchemaError, match="clustered"):
            table.paired("A", "B", instrument="hidden-tests")

    def test_paired_item_order_is_canonical(self) -> None:
        rows = [
            {"item_id": "i9", "system": "A", "instrument": "t", "label": 1},
            {"item_id": "i1", "system": "A", "instrument": "t", "label": 0},
            {"item_id": "i9", "system": "B", "instrument": "t", "label": 1},
            {"item_id": "i1", "system": "B", "instrument": "t", "label": 0},
        ]

        pair = LabelTable.from_rows(rows).paired("A", "B", instrument="t")

        assert pair.item_id.tolist() == ["i1", "i9"]


class TestWideToLong:
    def test_one_wide_row_becomes_one_row_per_instrument(self) -> None:
        table = wide_to_long(
            [{"item_id": "i1", "system": "A", "human": 1, "judge": 0}],
            instruments=("human", "judge"),
        )

        assert table.n_rows == 2
        assert table.instrument.tolist() == ["human", "judge"]
        assert table.label.tolist() == [1.0, 0.0]

    def test_instruments_must_be_named_not_inferred(self) -> None:
        """Inferring instruments from leftover columns is how a metadata column becomes one."""
        with pytest.raises(SchemaError, match="notes"):
            wide_to_long(
                [{"item_id": "i1", "system": "A", "human": 1, "notes": "looks fine"}],
                instruments=("human", "notes"),
            )

    def test_missing_instrument_column_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="judge"):
            wide_to_long([{"item_id": "i1", "system": "A", "human": 1}], instruments=("judge",))

    def test_blank_cells_are_skipped_not_zero_filled(self) -> None:
        """Gold on a subset while the cheap instrument scores everything is the PPI shape.

        A blank human cell means unlabeled, and filling it with 0 would invent a label.
        """
        table = wide_to_long(
            [
                {"item_id": "i1", "system": "A", "human": 1, "judge": 1},
                {"item_id": "i2", "system": "A", "human": None, "judge": 0},
                {"item_id": "i3", "system": "A", "human": "", "judge": 1},
            ],
            instruments=("human", "judge"),
        )

        assert table.n_rows == 4
        assert table.subset(instrument="human").item_id.tolist() == ["i1"]
        assert table.subset(instrument="judge").n_rows == 3

    def test_result_is_in_canonical_order(self) -> None:
        table = wide_to_long(
            [
                {"item_id": "i9", "system": "A", "judge": 1},
                {"item_id": "i1", "system": "A", "judge": 0},
            ],
            instruments=("judge",),
        )

        assert table.item_id.tolist() == ["i1", "i9"]


class TestLoadLongCsv:
    def write(self, tmp_path, text: str):
        path = tmp_path / "labels.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_a_long_csv_into_a_table(self, tmp_path) -> None:
        path = self.write(
            tmp_path,
            "item_id,system,run,instrument,label\ni1,A,0,hidden-tests,1\ni2,A,0,hidden-tests,0\n",
        )

        table = load_long_csv(path)

        assert table.n_rows == 2
        assert table.label.tolist() == [1.0, 0.0]

    def test_csv_labels_are_parsed_as_numbers(self, tmp_path) -> None:
        """Everything arrives from a CSV as a string, so the loader converts explicitly."""
        path = self.write(tmp_path, "item_id,system,instrument,label\ni1,A,human,0.75\n")

        assert load_long_csv(path).label.tolist() == [0.75]

    def test_run_column_may_be_omitted(self, tmp_path) -> None:
        path = self.write(tmp_path, "item_id,system,instrument,label\ni1,A,human,1\n")

        assert load_long_csv(path).run.tolist() == [0]

    def test_missing_required_header_is_rejected(self, tmp_path) -> None:
        path = self.write(tmp_path, "item_id,system,label\ni1,A,1\n")

        with pytest.raises(SchemaError, match="instrument"):
            load_long_csv(path)

    def test_non_numeric_label_names_the_row(self, tmp_path) -> None:
        path = self.write(tmp_path, "item_id,system,instrument,label\ni1,A,human,resolved\n")

        with pytest.raises(SchemaError, match="label"):
            load_long_csv(path)

    def test_file_order_does_not_affect_the_table(self, tmp_path) -> None:
        forward = self.write(
            tmp_path, "item_id,system,instrument,label\ni1,A,human,1\ni2,A,human,0\n"
        )
        table_forward = load_long_csv(forward)
        reversed_path = tmp_path / "reversed.csv"
        reversed_path.write_text(
            "item_id,system,instrument,label\ni2,A,human,0\ni1,A,human,1\n", encoding="utf-8"
        )

        table_reversed = load_long_csv(reversed_path)

        assert table_forward.item_id.tolist() == table_reversed.item_id.tolist()
        assert table_forward.label.tolist() == table_reversed.label.tolist()


class TestPairingRefusesMisleadingComparisons:
    def test_pairing_a_system_with_itself_is_rejected(self) -> None:
        """A self-comparison is always zero by construction and never a real question."""
        with pytest.raises(SchemaError, match="itself"):
            LabelTable.from_rows(rows_paired()).paired("A", "A", instrument="hidden-tests")

    def test_systems_absent_from_the_named_instrument_are_rejected(self) -> None:
        """Both systems exist, but neither was scored by this instrument."""
        rows = rows_paired() + [
            {"item_id": "i1", "system": "C", "instrument": "judge", "label": 1},
            {"item_id": "i1", "system": "D", "instrument": "judge", "label": 1},
        ]
        table = LabelTable.from_rows(rows)

        with pytest.raises(SchemaError, match="hidden-tests"):
            table.paired("C", "D", instrument="hidden-tests")

    def test_systems_measured_on_different_runs_do_not_silently_pair(self) -> None:
        """A run 0 against B run 1 is a cross-run comparison nobody declared."""
        rows = [
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "t", "label": 1},
            {"item_id": "i1", "system": "B", "run": 1, "instrument": "t", "label": 0},
        ]
        table = LabelTable.from_rows(rows)

        with pytest.raises(SchemaError, match="run"):
            table.paired("A", "B", instrument="t")

    def test_an_explicit_run_selects_one_measurement(self) -> None:
        rows = [
            {"item_id": "i1", "system": "A", "run": 0, "instrument": "t", "label": 1},
            {"item_id": "i1", "system": "A", "run": 1, "instrument": "t", "label": 0},
            {"item_id": "i1", "system": "B", "run": 0, "instrument": "t", "label": 0},
            {"item_id": "i1", "system": "B", "run": 1, "instrument": "t", "label": 1},
        ]

        pair = LabelTable.from_rows(rows).paired("A", "B", instrument="t", run=1)

        assert pair.label_a.tolist() == [0.0]
        assert pair.label_b.tolist() == [1.0]


class TestRunIsAnExactInteger:
    def test_fractional_run_is_rejected_rather_than_truncated(self) -> None:
        """int(1.5) is 1, which would silently merge two distinct runs."""
        with pytest.raises(SchemaError, match="run"):
            LabelTable.from_rows(
                [{"item_id": "i1", "system": "A", "run": 1.5, "instrument": "t", "label": 1}]
            )

    def test_boolean_run_is_rejected(self) -> None:
        """bool is an int subclass, so True would quietly become run 1."""
        with pytest.raises(SchemaError, match="run"):
            LabelTable.from_rows(
                [{"item_id": "i1", "system": "A", "run": True, "instrument": "t", "label": 1}]
            )

    def test_nan_run_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="run"):
            LabelTable.from_rows(
                [
                    {
                        "item_id": "i1",
                        "system": "A",
                        "run": float("nan"),
                        "instrument": "t",
                        "label": 1,
                    }
                ]
            )

    def test_integral_float_is_accepted(self) -> None:
        """CSV parsing yields floats, so 2.0 is a legitimate way to say run 2."""
        table = LabelTable.from_rows(
            [{"item_id": "i1", "system": "A", "run": 2.0, "instrument": "t", "label": 1}]
        )

        assert table.run.tolist() == [2]


class TestKeyFieldsAreRealIdentifiers:
    def test_none_item_id_is_rejected_not_stringified(self) -> None:
        """str(None) is 'None', a plausible-looking identifier for a missing one."""
        with pytest.raises(SchemaError, match="item_id"):
            LabelTable.from_rows([{"item_id": None, "system": "A", "instrument": "t", "label": 1}])

    def test_blank_system_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="system"):
            LabelTable.from_rows([{"item_id": "i1", "system": "", "instrument": "t", "label": 1}])

    def test_whitespace_instrument_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="instrument"):
            LabelTable.from_rows(
                [{"item_id": "i1", "system": "A", "instrument": "   ", "label": 1}]
            )


class TestValidatedTableIsImmutable:
    def test_labels_cannot_be_mutated_after_validation(self) -> None:
        """frozen=True protects the attribute binding, not the array contents."""
        table = LabelTable.from_rows(rows_minimal())

        with pytest.raises(ValueError, match="read-only"):
            table.label[0] = float("nan")

    def test_identifiers_cannot_be_mutated_after_validation(self) -> None:
        table = LabelTable.from_rows(rows_minimal())

        with pytest.raises(ValueError, match="read-only"):
            table.item_id[0] = "tampered"

    def test_mutating_the_source_array_does_not_change_the_table(self) -> None:
        source = np.asarray([1.0, 0.0])
        table = LabelTable(
            item_id=np.asarray(["i1", "i2"]),
            system=np.asarray(["A", "A"]),
            run=np.asarray([0, 0]),
            instrument=np.asarray(["t", "t"]),
            label=source,
        )

        source[0] = 99.0

        assert table.label.tolist() == [1.0, 0.0]

    def test_direct_construction_validates_column_lengths(self) -> None:
        with pytest.raises(SchemaError, match="length"):
            LabelTable(
                item_id=np.asarray(["i1", "i2"]),
                system=np.asarray(["A"]),
                run=np.asarray([0]),
                instrument=np.asarray(["t"]),
                label=np.asarray([1.0]),
            )

    def test_direct_construction_rejects_a_nan_label(self) -> None:
        with pytest.raises(SchemaError, match="nan"):
            LabelTable(
                item_id=np.asarray(["i1"]),
                system=np.asarray(["A"]),
                run=np.asarray([0]),
                instrument=np.asarray(["t"]),
                label=np.asarray([float("nan")]),
            )

    def test_direct_construction_rejects_duplicate_keys(self) -> None:
        with pytest.raises(SchemaError, match="duplicate"):
            LabelTable(
                item_id=np.asarray(["i1", "i1"]),
                system=np.asarray(["A", "A"]),
                run=np.asarray([0, 0]),
                instrument=np.asarray(["t", "t"]),
                label=np.asarray([1.0, 0.0]),
            )


class TestOptionalColumnsMayBePartial:
    def test_cost_present_on_some_rows_is_allowed(self) -> None:
        """Experiment 2 mixes a costed judge with uncosted human rows in one table."""
        table = LabelTable.from_rows(
            [
                {"item_id": "i1", "system": "A", "instrument": "human", "label": 1},
                {"item_id": "i1", "system": "A", "instrument": "judge", "label": 1, "cost": 0.02},
            ]
        )

        costs = table.cost.tolist()
        assert costs[1] == 0.02
        assert costs[0] != costs[0], "missing cost is nan, not zero"

    def test_category_present_on_some_rows_is_allowed(self) -> None:
        table = LabelTable.from_rows(
            [
                {"item_id": "i1", "system": "A", "instrument": "human", "label": 1},
                {
                    "item_id": "i2",
                    "system": "A",
                    "instrument": "human",
                    "label": 1,
                    "category": "django",
                },
            ]
        )

        assert table.category.tolist() == ["", "django"]
