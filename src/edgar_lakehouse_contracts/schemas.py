"""L2: the table list as :class:`TableSpec` objects.

Published so consumers stop vendoring it. Repo 4 kept a private copy of these specs,
and that copy is what silently disagreed with this package on every one of the thirteen
tables — a consumer that cannot import a type will reimplement it, and a reimplementation
drifts. See root ``AGENTS.md`` law 11.

**The columns are derived, never duplicated.** ``spark.schemas.COLUMN_SPECS`` remains the
single source of truth for column names, types and nullability, and the drift test
already checks it against the Liquibase changelogs. This module adds only the facts
``COLUMN_SPECS`` does not carry — layer, business key, partitioning and the changeset
that creates each table — so there is no second place for a column to go stale.

pyspark is never imported here: ``COLUMN_SPECS`` is plain tuples, so this module works
without a JVM and is safe for CI and for tooling.
"""

from __future__ import annotations

from typing import Final

from edgar_lakehouse_contracts import names
from edgar_lakehouse_contracts.models import ColumnSpec, Layer, TableSpec
from edgar_lakehouse_contracts.spark.schemas import COLUMN_SPECS

__all__ = [
    "ALL_TABLES",
    "BRONZE_METADATA_COLUMNS",
    "EXPORT_TABLES",
    "QUARANTINE_COLUMNS",
    "TABLES",
    "struct_for",
    "table",
]

#: Facts about each table that the column list does not carry. Keyed by fqn.
#:
#: ``business_key`` is the MERGE key, not a uniqueness claim about the raw feed: for
#: ``silver.financial_fact`` it deliberately includes ``accession_number``, because two
#: accessions asserting the same period must produce two rows — the difference between
#: them is the restatement.
_META: Final[dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
    # fqn: (changeset, business_key, partition_by)
    "edgar.bronze.filing_index_raw": ("010-bronze.yaml", (), ("logical_date",)),
    "edgar.bronze.company_submissions_raw": ("010-bronze.yaml", (), ("logical_date",)),
    "edgar.bronze.company_concept_raw": ("010-bronze.yaml", (), ("logical_date",)),
    "edgar.silver.filing": ("020-silver.yaml", ("accession_number",), ()),
    "edgar.silver.company": ("020-silver.yaml", ("cik",), ()),
    "edgar.silver.financial_fact": (
        "020-silver.yaml",
        (
            "cik",
            "taxonomy",
            "concept_tag",
            "unit",
            "period_start",
            "period_end",
            "period_type",
            "accession_number",
        ),
        (),
    ),
    "edgar.silver.filing_quarantine": ("030-silver-quarantine.yaml", ("_dq_record_id",), ()),
    "edgar.silver.company_quarantine": ("030-silver-quarantine.yaml", ("_dq_record_id",), ()),
    "edgar.silver.financial_fact_quarantine": (
        "030-silver-quarantine.yaml",
        ("_dq_record_id",),
        (),
    ),
    "edgar.gold.financials_current": (
        "040-gold.yaml",
        ("cik", "concept_canonical", "period_end"),
        (),
    ),
    "edgar.gold.restatement_event": ("040-gold.yaml", ("restatement_id",), ()),
    "edgar.gold.filing_activity_daily": ("040-gold.yaml", ("filed_date", "base_form_type"), ()),
    "edgar.gold.company_profile": ("040-gold.yaml", ("cik",), ()),
}

_LAYERS: Final[dict[str, Layer]] = {
    names.SCHEMA_BRONZE: Layer.BRONZE,
    names.SCHEMA_SILVER: Layer.SILVER,
    names.SCHEMA_GOLD: Layer.GOLD,
}


def _build() -> dict[str, TableSpec]:
    out: dict[str, TableSpec] = {}
    for fqn, columns in COLUMN_SPECS.items():
        catalog, schema, name = fqn.split(".")
        changeset, business_key, partition_by = _META.get(fqn, ("020-silver.yaml", (), ()))
        out[fqn] = TableSpec(
            catalog=catalog,
            schema=schema,
            name=name,
            layer=_LAYERS[schema],
            columns=tuple(ColumnSpec(name=c, type_sql=t, nullable=n) for c, t, n in columns),
            changeset=changeset,
            business_key=business_key,
            partition_by=partition_by,
        )
    return out


#: Every table in the contract, keyed by fully-qualified name.
TABLES: Final[dict[str, TableSpec]] = _build()


def table(fqn: str) -> TableSpec:
    """Return one spec, raising a message that names the alternatives.

    ``KeyError('edgar.silver.filings')`` is a typo hunt; listing the valid names turns it
    into a one-second fix.
    """
    try:
        return TABLES[fqn]
    except KeyError:
        raise KeyError(f"unknown table {fqn!r}; known tables: {sorted(TABLES)}") from None


# ---------------------------------------------------------------------------
# The rest of the consumer surface.
#
# Published because repo 4 reached for every one of these, did not find them, and
# reimplemented the lot. Enumerating what the consumer actually imports -- rather
# than guessing one symbol at a time -- is what turns four version bumps into one.
# ---------------------------------------------------------------------------

#: The metadata columns carried by every bronze table.
BRONZE_METADATA_COLUMNS: Final[tuple[ColumnSpec, ...]] = TABLES[
    "edgar.bronze.filing_index_raw"
].columns[-6:]

#: The single shape every quarantine table shares, which is what lets the DQ layer stay
#: domain-agnostic instead of growing a branch per entity.
QUARANTINE_COLUMNS: Final[tuple[ColumnSpec, ...]] = TABLES["edgar.silver.filing_quarantine"].columns

#: Every table, ordered by fqn so any listing is stable across runs.
ALL_TABLES: Final[tuple[TableSpec, ...]] = tuple(TABLES[k] for k in sorted(TABLES))

#: The gold tables repo 4 exports to Parquet and repo 5 reads. The order is fixed
#: because it is the order of the export manifest, and a manifest whose order moves
#: produces a spurious diff on every run.
EXPORT_TABLES: Final[tuple[TableSpec, ...]] = tuple(
    TABLES[f"edgar.gold.{n}"]
    for n in ("company_profile", "filing_activity_daily", "financials_current", "restatement_event")
)

# Per-table constants -- SILVER_COMPANY, GOLD_RESTATEMENT_EVENT and so on. Generated
# from TABLES rather than hand-written, so adding a table cannot leave a stale constant
# behind and removing one cannot leave a dangling name.
for _spec in TABLES.values():
    globals()[f"{_spec.schema.upper()}_{_spec.name.upper()}"] = _spec
del _spec


def struct_for(fqn: str) -> object:
    """Spark ``StructType`` for a table. Imports pyspark lazily, on this call only.

    Deliberately not a module-level import: everything above must be importable without
    a JVM so that CI, tooling and non-Spark consumers can use this package.
    """
    from edgar_lakehouse_contracts.spark.schemas import get_schema

    return get_schema(fqn)
