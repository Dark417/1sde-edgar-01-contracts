"""L2 leaf: one StructType per bronze and silver table (data contracts §2-§3).

This module and ``changelog/`` are the two representations of the lakehouse
schema. They are deliberately not generated from each other (ADR-002); the
drift test in ``tests/test_schema_drift.py`` is what keeps them identical.

pyspark is imported lazily so that ``import edgar_lakehouse_contracts`` works in
environments without Spark. Does not handle: table creation (Liquibase) or any
Spark session concerns.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import TYPE_CHECKING, Any, Final

from edgar_lakehouse_contracts import names

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pyspark.sql.types import DataType, StructType

# (column name, contract type string, nullable) — the contract type strings
# match the Liquibase changelog types exactly; the drift test normalizes both.
ColumnSpec = tuple[str, str, bool]

COLUMN_SPECS: Final[Mapping[str, tuple[ColumnSpec, ...]]] = {
    names.table(names.SCHEMA_BRONZE, "filing_index_raw"): (
        ("logical_date", "DATE", False),
        ("resource_id", "STRING", True),
        ("fetched_at", "TIMESTAMP", True),
        ("form_type", "STRING", True),
        ("company_name", "STRING", True),
        ("cik", "STRING", True),
        ("date_filed", "STRING", True),
        ("accession_number", "STRING", True),
        ("file_name", "STRING", True),
        ("_ingest_batch_id", "STRING", False),
        ("_ingest_ts", "TIMESTAMP", False),
        ("_source_file", "STRING", False),
        ("_source_system", "STRING", False),
        ("_envelope_version", "STRING", False),
        ("_rescued_data", "STRING", True),
    ),
    names.table(names.SCHEMA_BRONZE, "company_submissions_raw"): (
        ("logical_date", "DATE", False),
        ("resource_id", "STRING", True),
        ("fetched_at", "TIMESTAMP", True),
        ("cik", "STRING", True),
        ("payload_json", "STRING", True),
        ("_ingest_batch_id", "STRING", False),
        ("_ingest_ts", "TIMESTAMP", False),
        ("_source_file", "STRING", False),
        ("_source_system", "STRING", False),
        ("_envelope_version", "STRING", False),
        ("_rescued_data", "STRING", True),
    ),
    names.table(names.SCHEMA_BRONZE, "company_concept_raw"): (
        ("logical_date", "DATE", False),
        ("resource_id", "STRING", True),
        ("fetched_at", "TIMESTAMP", True),
        ("cik", "STRING", True),
        ("taxonomy", "STRING", True),
        ("tag", "STRING", True),
        ("payload_json", "STRING", True),
        ("_ingest_batch_id", "STRING", False),
        ("_ingest_ts", "TIMESTAMP", False),
        ("_source_file", "STRING", False),
        ("_source_system", "STRING", False),
        ("_envelope_version", "STRING", False),
        ("_rescued_data", "STRING", True),
    ),
    names.table(names.SCHEMA_SILVER, "filing"): (
        ("accession_number", "STRING", False),
        ("cik", "STRING", False),
        ("company_name", "STRING", True),
        ("form_type", "STRING", False),
        ("base_form_type", "STRING", False),
        ("is_amendment", "BOOLEAN", False),
        ("filed_date", "DATE", False),
        ("primary_doc_url", "STRING", True),
        ("logical_date", "DATE", False),
        # SCD-2 (060). Filings are amended, and the previous MERGE overwrote, so the
        # pre-amendment values were lost -- which is the history restatement_event needs.
        ("filing_sk", "STRING", False),
        ("version_number", "INT", False),
        ("valid_from", "DATE", False),
        ("valid_to", "DATE", True),
        ("is_current", "BOOLEAN", False),
        ("_hash_diff", "STRING", False),
        ("_first_seen_ts", "TIMESTAMP", False),
        ("_last_seen_ts", "TIMESTAMP", False),
        ("_ingest_batch_id", "STRING", False),
        ("_source_file", "STRING", True),
    ),
    names.table(names.SCHEMA_SILVER, "company"): (
        ("cik", "STRING", False),
        ("company_name", "STRING", True),
        ("sic", "STRING", True),
        ("sic_description", "STRING", True),
        ("ein", "STRING", True),
        ("entity_type", "STRING", True),
        ("state_of_incorporation", "STRING", True),
        ("fiscal_year_end", "STRING", True),
        ("tickers", "ARRAY<STRING>", True),
        ("exchanges", "ARRAY<STRING>", True),
        ("former_names", "ARRAY<STRING>", True),
        # 060: the interval was already here; the ordinal and the surrogate key are new.
        ("company_sk", "STRING", False),
        ("version_number", "INT", False),
        ("valid_from", "DATE", False),
        ("valid_to", "DATE", True),
        ("is_current", "BOOLEAN", False),
        ("_hash_diff", "STRING", False),
        ("_first_seen_ts", "TIMESTAMP", False),
        ("_last_seen_ts", "TIMESTAMP", False),
        ("_ingest_batch_id", "STRING", False),
        ("_source_file", "STRING", True),
    ),
    names.table(names.SCHEMA_SILVER, "financial_fact"): (
        ("cik", "STRING", False),
        ("taxonomy", "STRING", False),
        ("concept_tag", "STRING", False),
        ("concept_canonical", "STRING", True),
        ("unit", "STRING", False),
        ("period_start", "DATE", True),
        ("period_end", "DATE", False),
        ("period_type", "STRING", False),
        ("accession_number", "STRING", False),
        ("value", "DECIMAL(38,6)", True),
        ("decimals", "INT", True),
        ("fiscal_year", "INT", True),
        ("fiscal_period", "STRING", True),
        ("form_type", "STRING", True),
        ("filed_date", "DATE", False),
        ("frame", "STRING", True),
        ("logical_date", "DATE", False),
        # Assertion versioning (060). A restatement is a new assertion about the same
        # period, not a correction to a row, so both are kept and ordered.
        ("fact_sk", "STRING", False),
        ("assertion_version", "INT", False),
        ("is_current_assertion", "BOOLEAN", False),
        ("superseded_by_accession", "STRING", True),
        ("_first_seen_ts", "TIMESTAMP", False),
        ("_last_seen_ts", "TIMESTAMP", False),
        ("_ingest_batch_id", "STRING", False),
        ("_source_file", "STRING", True),
    ),
    names.table(names.SCHEMA_SILVER, "filing_quarantine"): (
        ("_dq_record_id", "STRING", False),
        ("_dq_run_id", "STRING", False),
        ("_dq_check_name", "STRING", False),
        ("_dq_failure_reason", "STRING", False),
        ("_quarantined_at", "TIMESTAMP", False),
        ("_source_table", "STRING", False),
        ("_source_file", "STRING", True),
        ("_ingest_batch_id", "STRING", True),
        ("record_json", "STRING", False),
    ),
    names.table(names.SCHEMA_SILVER, "company_quarantine"): (
        ("_dq_record_id", "STRING", False),
        ("_dq_run_id", "STRING", False),
        ("_dq_check_name", "STRING", False),
        ("_dq_failure_reason", "STRING", False),
        ("_quarantined_at", "TIMESTAMP", False),
        ("_source_table", "STRING", False),
        ("_source_file", "STRING", True),
        ("_ingest_batch_id", "STRING", True),
        ("record_json", "STRING", False),
    ),
    names.table(names.SCHEMA_SILVER, "financial_fact_quarantine"): (
        ("_dq_record_id", "STRING", False),
        ("_dq_run_id", "STRING", False),
        ("_dq_check_name", "STRING", False),
        ("_dq_failure_reason", "STRING", False),
        ("_quarantined_at", "TIMESTAMP", False),
        ("_source_table", "STRING", False),
        ("_source_file", "STRING", True),
        ("_ingest_batch_id", "STRING", True),
        ("record_json", "STRING", False),
    ),
    names.table(names.SCHEMA_GOLD, "financials_current"): (
        ("cik", "STRING", False),
        ("company_name", "STRING", True),
        ("concept_canonical", "STRING", False),
        ("unit", "STRING", False),
        ("period_start", "DATE", True),
        ("period_end", "DATE", False),
        ("period_type", "STRING", False),
        ("value", "DECIMAL(38,6)", True),
        ("decimals", "INT", True),
        ("fiscal_year", "INT", True),
        ("fiscal_period", "STRING", True),
        ("accession_number", "STRING", False),
        ("form_type", "STRING", True),
        ("filed_date", "DATE", False),
        ("assertion_count", "INT", False),
        ("was_restated", "BOOLEAN", False),
        ("_generated_at", "TIMESTAMP", False),
        ("_run_id", "STRING", False),
        ("_source_version", "BIGINT", True),
    ),
    names.table(names.SCHEMA_GOLD, "restatement_event"): (
        ("restatement_id", "STRING", False),
        ("cik", "STRING", False),
        ("company_name", "STRING", True),
        ("concept_canonical", "STRING", False),
        ("unit", "STRING", False),
        ("period_start", "DATE", True),
        ("period_end", "DATE", False),
        ("period_type", "STRING", False),
        ("original_accession_number", "STRING", False),
        ("original_form_type", "STRING", True),
        ("original_filed_date", "DATE", False),
        ("original_value", "DECIMAL(38,6)", False),
        ("original_decimals", "INT", True),
        ("restated_accession_number", "STRING", False),
        ("restated_form_type", "STRING", True),
        ("restated_filed_date", "DATE", False),
        ("restated_value", "DECIMAL(38,6)", False),
        ("restated_decimals", "INT", True),
        ("delta_abs", "DECIMAL(38,6)", False),
        ("delta_pct", "DOUBLE", True),
        ("materiality_band", "STRING", False),
        ("days_to_restatement", "INT", False),
        ("_generated_at", "TIMESTAMP", False),
        ("_run_id", "STRING", False),
        ("_source_version", "BIGINT", True),
    ),
    names.table(names.SCHEMA_GOLD, "filing_activity_daily"): (
        ("filed_date", "DATE", False),
        ("base_form_type", "STRING", False),
        ("filing_count", "INT", False),
        ("amendment_count", "INT", False),
        ("distinct_cik_count", "INT", False),
        ("_generated_at", "TIMESTAMP", False),
        ("_run_id", "STRING", False),
        ("_source_version", "BIGINT", True),
    ),
    names.table(names.SCHEMA_GOLD, "company_profile"): (
        ("cik", "STRING", False),
        ("company_name", "STRING", True),
        ("sic", "STRING", True),
        ("sic_description", "STRING", True),
        ("entity_type", "STRING", True),
        ("state_of_incorporation", "STRING", True),
        ("fiscal_year_end", "STRING", True),
        ("tickers", "ARRAY<STRING>", True),
        ("exchanges", "ARRAY<STRING>", True),
        ("filing_count", "INT", False),
        ("first_filed_date", "DATE", True),
        ("last_filed_date", "DATE", True),
        ("restatement_count", "INT", False),
        ("_generated_at", "TIMESTAMP", False),
        ("_run_id", "STRING", False),
        ("_source_version", "BIGINT", True),
    ),
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
        case "DOUBLE":
            return T.DoubleType()  # type: ignore[no-any-return]
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
