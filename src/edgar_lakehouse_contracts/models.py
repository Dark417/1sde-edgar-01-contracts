"""L1: raw record models (data contracts §2).

Does not handle: typing or cleaning values — these are *raw* records; typing
happens in silver (repo 4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class FilingIndexRecord(BaseModel):
    """One row of the EDGAR daily form index, all fields as-published strings.

    All str by design: this is the raw record. cik stays a string — leading
    zeros are semantically meaningful in EDGAR URLs (never make it an int).

    Does not handle: date parsing, CIK padding, accession normalization.
    """

    model_config = ConfigDict(frozen=True)

    company_name: str
    form_type: str
    cik: str
    date_filed: str
    file_name: str
    #: The accession number, sliced out of ``file_name``. This is extraction, not
    #: normalization: the .idx file has no accession column, but every ``file_name``
    #: embeds one (``edgar/data/<cik>/<accession>.txt``). Bronze needs it as the
    #: filing's natural key and cannot re-derive it without parsing a path, which is
    #: exactly the kind of source-format knowledge that belongs in the ingest parser.
    accession_number: str


# ---------------------------------------------------------------------------
# Table specifications.
#
# Published so consumers stop vendoring them. Repo 4 carried a private copy of
# these types and of the table list; that copy is what silently disagreed with
# this package on all eleven envelope field names and on every one of the
# thirteen tables. A consumer that cannot import a type will reimplement it.
#
# The column data itself is NOT duplicated here -- `schemas.TABLES` derives it
# from `spark.schemas.COLUMN_SPECS`, which stays the single source of truth and
# is what the drift test already checks against the changelogs.
# ---------------------------------------------------------------------------


class Layer(StrEnum):
    """Medallion layer a table belongs to."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """One column of a contract table."""

    name: str
    type_sql: str
    nullable: bool = True
    comment: str = ""

    def ddl(self) -> str:
        not_null = "" if self.nullable else " NOT NULL"
        return f"{self.name} {self.type_sql}{not_null}"


@dataclass(frozen=True, slots=True)
class TableSpec:
    """A table in the contract.

    ``changeset`` names the Liquibase file that creates it, so a consumer can turn
    "table not found" into "changeset 020-silver.yaml was never applied" -- a
    one-line diagnosis instead of a bisect.
    """

    catalog: str
    schema: str
    name: str
    layer: Layer
    columns: tuple[ColumnSpec, ...]
    changeset: str
    business_key: tuple[str, ...] = ()
    partition_by: tuple[str, ...] = ()
    comment: str = ""

    @property
    def fqn(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.name}"

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    def column(self, name: str) -> ColumnSpec:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"{self.fqn} has no column {name!r}")

    def with_catalog(self, catalog: str) -> TableSpec:
        """Return a copy bound to another catalog (used by local test harnesses)."""
        return replace(self, catalog=catalog)
