"""L2 leaf: one StructType per bronze and silver table (data contracts §2-§3).

This module and ``changelog/`` are the two representations of the lakehouse
schema. They are deliberately not generated from each other (ADR-002); the
drift test in ``tests/test_schema_drift.py`` is what keeps them identical.

pyspark is imported lazily so that ``import fin_lakehouse_contracts`` works in
environments without Spark. Does not handle: table creation (Liquibase) or any
Spark session concerns.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import TYPE_CHECKING, Any, Final

from fin_lakehouse_contracts import names

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pyspark.sql.types import DataType, StructType

# (column name, contract type string, nullable) — the contract type strings
# match the Liquibase changelog types exactly; the drift test normalizes both.
ColumnSpec = tuple[str, str, bool]

_BRONZE_META: Final[tuple[ColumnSpec, ...]] = (
    ("_source_file", "STRING", False),
    ("_ingest_ts", "TIMESTAMP", False),
    ("_batch_id", "STRING", False),
    ("_logical_date", "DATE", False),
    ("_schema_version", "STRING", False),
    ("_rescued_data", "STRING", True),
)

_SILVER_FILING: Final[tuple[ColumnSpec, ...]] = (
    ("accession_number", "STRING", False),
    # cik is a STRING, always — leading zeros are semantically meaningful in
    # EDGAR URLs; any code that makes it an int is a bug.
    ("cik", "STRING", False),
    ("company_name", "STRING", True),
    ("form_type", "STRING", False),
    ("base_form_type", "STRING", False),
    ("is_amendment", "BOOLEAN", False),
    ("filed_date", "DATE", False),
    ("source_file_name", "STRING", True),
    ("_first_seen_ts", "TIMESTAMP", False),
    ("_last_seen_ts", "TIMESTAMP", False),
    ("_batch_id", "STRING", False),
)

_SILVER_COMPANY: Final[tuple[ColumnSpec, ...]] = (
    ("cik", "STRING", False),
    ("name", "STRING", False),
    ("sic", "STRING", True),
    ("sic_description", "STRING", True),
    ("state_of_incorporation", "STRING", True),
    ("fiscal_year_end", "STRING", True),
    ("tickers", "ARRAY<STRING>", True),
    ("exchanges", "ARRAY<STRING>", True),
    ("_hash_diff", "STRING", False),
    ("valid_from", "DATE", False),
    ("valid_to", "DATE", True),
    ("is_current", "BOOLEAN", False),
    ("_first_seen_ts", "TIMESTAMP", False),
    ("_last_seen_ts", "TIMESTAMP", False),
    ("_batch_id", "STRING", False),
)

_SILVER_FACT: Final[tuple[ColumnSpec, ...]] = (
    ("cik", "STRING", False),
    ("taxonomy", "STRING", False),
    ("concept", "STRING", False),
    ("concept_canonical", "STRING", True),
    ("unit", "STRING", False),
    ("value", "DECIMAL(38,6)", False),
    ("period_start", "DATE", True),
    ("period_end", "DATE", False),
    ("period_type", "STRING", False),
    ("fy", "STRING", True),
    ("fp", "STRING", True),
    ("form", "STRING", True),
    ("accession_number", "STRING", False),
    ("filed_date", "DATE", False),
    ("_first_seen_ts", "TIMESTAMP", False),
    ("_last_seen_ts", "TIMESTAMP", False),
    ("_batch_id", "STRING", False),
)

_DQ_META: Final[tuple[ColumnSpec, ...]] = (
    ("_dq_check_name", "STRING", False),
    ("_dq_failure_reason", "STRING", False),
    ("_dq_run_id", "STRING", False),
    ("_quarantined_at", "TIMESTAMP", False),
)


def _quarantine(source: tuple[ColumnSpec, ...]) -> tuple[ColumnSpec, ...]:
    """Quarantine twin: every source column nullable, plus the DQ columns.

    Does not handle: gold tables — quarantine exists only for silver.
    """
    return tuple((name, type_str, True) for name, type_str, _ in source) + _DQ_META


COLUMN_SPECS: Final[Mapping[str, tuple[ColumnSpec, ...]]] = {
    names.table(names.SCHEMA_BRONZE, "filing_index_raw"): (
        ("company_name", "STRING", True),
        ("form_type", "STRING", True),
        ("cik", "STRING", True),
        ("date_filed", "STRING", True),
        ("file_name", "STRING", True),
        *_BRONZE_META,
    ),
    names.table(names.SCHEMA_BRONZE, "company_submissions_raw"): (
        ("cik", "STRING", True),
        ("payload_json", "STRING", True),
        *_BRONZE_META,
    ),
    names.table(names.SCHEMA_BRONZE, "company_concept_raw"): (
        ("cik", "STRING", True),
        ("taxonomy", "STRING", True),
        ("concept", "STRING", True),
        ("payload_json", "STRING", True),
        *_BRONZE_META,
    ),
    names.table(names.SCHEMA_SILVER, "filing"): _SILVER_FILING,
    names.table(names.SCHEMA_SILVER, "company"): _SILVER_COMPANY,
    names.table(names.SCHEMA_SILVER, "financial_fact"): _SILVER_FACT,
    names.table(names.SCHEMA_SILVER, "filing_quarantine"): _quarantine(_SILVER_FILING),
    names.table(names.SCHEMA_SILVER, "company_quarantine"): _quarantine(_SILVER_COMPANY),
    names.table(names.SCHEMA_SILVER, "financial_fact_quarantine"): _quarantine(_SILVER_FACT),
}


def _spark_types() -> Any:
    from pyspark.sql import types as T

    return T


def _to_spark_type(type_str: str) -> DataType:
    """Map a contract type string to a Spark DataType.

    Does not handle: types outside the contract vocabulary — raises ValueError
    so an unknown type is a loud failure, not a silent STRING.
    """
    T = _spark_types()
    match type_str:
        case "STRING":
            return T.StringType()  # type: ignore[no-any-return]
        case "DATE":
            return T.DateType()  # type: ignore[no-any-return]
        case "TIMESTAMP":
            return T.TimestampType()  # type: ignore[no-any-return]
        case "BOOLEAN":
            return T.BooleanType()  # type: ignore[no-any-return]
        case "BIGINT":
            return T.LongType()  # type: ignore[no-any-return]
        case "INT":
            return T.IntegerType()  # type: ignore[no-any-return]
        case "DECIMAL(38,6)":
            return T.DecimalType(38, 6)  # type: ignore[no-any-return]
        case "ARRAY<STRING>":
            return T.ArrayType(T.StringType())  # type: ignore[no-any-return]
        case _:
            raise ValueError(f"unknown contract type: {type_str!r}")


@cache
def _build_schemas() -> Mapping[str, StructType]:
    T = _spark_types()
    return {
        fqn: T.StructType(
            [
                T.StructField(name, _to_spark_type(type_str), nullable)
                for name, type_str, nullable in cols
            ]
        )
        for fqn, cols in COLUMN_SPECS.items()
    }


def get_schema(table_fqn: str) -> StructType:
    """Return the StructType for a fully qualified table name.

    Does not handle: gold tables — gold is created by Liquibase and read via
    the serving export; no repo compiles Spark code against gold StructTypes.
    """
    schemas = _build_schemas()
    if table_fqn not in schemas:
        known = ", ".join(sorted(schemas))
        raise KeyError(f"no schema for {table_fqn!r}; known tables: {known}")
    return schemas[table_fqn]


def __getattr__(name: str) -> Any:
    # SCHEMAS is exposed lazily so importing this module's constants (e.g.
    # COLUMN_SPECS in the drift test) does not require pyspark.
    if name == "SCHEMAS":
        return _build_schemas()
    raise AttributeError(name)
