"""The published TableSpec API (v1.3.0).

These specs exist so consumers stop vendoring the contract, so the tests that matter are
the ones pinning the *published surface*: that every table resolves, that the derived
columns are identical to ``COLUMN_SPECS``, and that the accessors consumers actually call
behave. A drifting copy is the failure this API was added to prevent.
"""

from __future__ import annotations

import re

import pytest

from edgar_lakehouse_contracts import schemas
from edgar_lakehouse_contracts.models import ColumnSpec, Layer, TableSpec
from edgar_lakehouse_contracts.spark.schemas import COLUMN_SPECS


class TestTables:
    def test_every_published_table_has_a_spec(self) -> None:
        assert set(schemas.TABLES) == set(COLUMN_SPECS)

    def test_columns_are_derived_not_retyped(self) -> None:
        """The whole point: one source of truth for column data.

        If this ever fails, someone has started maintaining the columns in two places --
        which is exactly the drift this module was written to remove.
        """
        for fqn, spec in schemas.TABLES.items():
            derived = [(c.name, c.type_sql, c.nullable) for c in spec.columns]
            assert derived == [tuple(c) for c in COLUMN_SPECS[fqn]]

    @pytest.mark.parametrize("fqn", sorted(COLUMN_SPECS))
    def test_every_table_carries_its_layer_and_changeset(self, fqn: str) -> None:
        spec = schemas.TABLES[fqn]
        assert spec.layer is Layer(spec.schema)
        assert spec.changeset.endswith(".yaml")

    @pytest.mark.parametrize("fqn", sorted(COLUMN_SPECS))
    def test_business_keys_name_real_columns(self, fqn: str) -> None:
        """A business key naming a column that does not exist is a MERGE that fails at
        runtime in whichever repo consumes it."""
        spec = schemas.TABLES[fqn]
        for key in spec.business_key:
            assert key in spec.column_names, f"{fqn} business key {key!r} is not a column"

    @pytest.mark.parametrize("fqn", sorted(COLUMN_SPECS))
    def test_partition_columns_are_real_columns(self, fqn: str) -> None:
        spec = schemas.TABLES[fqn]
        for column in spec.partition_by:
            assert column in spec.column_names

    def test_fqn_round_trips_the_key(self) -> None:
        for fqn, spec in schemas.TABLES.items():
            assert spec.fqn == fqn


class TestLookup:
    def test_table_returns_the_spec(self) -> None:
        assert schemas.table("edgar.silver.company").name == "company"

    def test_unknown_table_names_the_alternatives(self) -> None:
        """A bare KeyError on a typo is a hunt; listing the valid names is a fix."""
        with pytest.raises(KeyError, match=re.escape("edgar.silver.filing")):
            schemas.table("edgar.silver.filings")


class TestTableSpec:
    def test_column_names_matches_columns(self) -> None:
        spec = schemas.TABLES["edgar.silver.company"]
        assert spec.column_names == tuple(c.name for c in spec.columns)

    def test_column_lookup(self) -> None:
        assert schemas.TABLES["edgar.silver.company"].column("cik").type_sql == "STRING"

    def test_unknown_column_raises(self) -> None:
        with pytest.raises(KeyError):
            schemas.TABLES["edgar.silver.company"].column("nope")

    def test_with_catalog_rebinds_and_leaves_the_original_alone(self) -> None:
        """Local harnesses run against a different catalog; the original must not move."""
        spec = schemas.TABLES["edgar.silver.company"]
        moved = spec.with_catalog("spark_catalog")
        assert moved.fqn == "spark_catalog.silver.company"
        assert spec.fqn == "edgar.silver.company"
        assert moved.columns == spec.columns

    def test_specs_are_frozen(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - dataclass raises FrozenInstanceError
            schemas.TABLES["edgar.silver.company"].name = "other"  # type: ignore[misc]


class TestColumnSpec:
    def test_ddl_marks_not_null(self) -> None:
        assert ColumnSpec("cik", "STRING", nullable=False).ddl() == "cik STRING NOT NULL"

    def test_ddl_omits_not_null_when_nullable(self) -> None:
        assert ColumnSpec("sic", "STRING").ddl() == "sic STRING"

    def test_nullable_defaults_to_true(self) -> None:
        assert ColumnSpec("x", "STRING").nullable is True


class TestLayer:
    def test_layer_is_its_schema_name(self) -> None:
        """Layer is a StrEnum so it interpolates into a table name unchanged."""
        assert f"{Layer.SILVER}" == "silver"
        assert Layer("gold") is Layer.GOLD

    def test_every_layer_has_at_least_one_table(self) -> None:
        present = {s.layer for s in schemas.TABLES.values()}
        assert present == set(Layer)


def test_the_types_are_importable_from_the_package_root_path() -> None:
    """Consumers import these; a rename here is a breaking change for repos 3-5."""
    assert TableSpec.__name__ == "TableSpec"
    assert ColumnSpec.__name__ == "ColumnSpec"
    assert Layer.__name__ == "Layer"
