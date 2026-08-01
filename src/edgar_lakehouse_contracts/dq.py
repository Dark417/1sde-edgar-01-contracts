"""L2: the DQ check registry (data contracts §3.1-§3.3).

This module *declares* checks; repo 4 executes them. Three severities:
``reject`` quarantines the row, ``warn`` emits a metric and keeps the row,
``reject_batch`` fails the whole job (SCD-2 / grain invariants, where one bad
row means the table is structurally broken).

``reject_batch`` expressions may use window functions; row-level expressions
must not.

Does not handle: executing checks, quarantining rows, or emitting metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from edgar_lakehouse_contracts import names

_SILVER_FILING: Final[str] = names.table(names.SCHEMA_SILVER, "filing")
_SILVER_COMPANY: Final[str] = names.table(names.SCHEMA_SILVER, "company")
_SILVER_FACT: Final[str] = names.table(names.SCHEMA_SILVER, "financial_fact")


@dataclass(frozen=True, slots=True)
class DQCheck:
    """One declared data-quality check.

    ``expression`` is a Spark SQL boolean; True means the row is GOOD.
    ``prevents`` names the concrete failure this check prevents (>= 20 chars,
    enforced by test) — a check whose author cannot name the failure is cargo
    cult and must be deleted, not documented.

    Does not handle: evaluation — repo 4's ``apply_dq`` does that.
    """

    name: str
    table: str
    severity: Literal["reject", "warn", "reject_batch"]
    expression: str
    prevents: str


DQ_CHECKS: Final[tuple[DQCheck, ...]] = (
    # ── silver.filing (§3.1) ────────────────────────────────────────────────
    DQCheck(
        name="filing_accession_format",
        table=_SILVER_FILING,
        severity="reject",
        expression=r"accession_number RLIKE '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'",
        prevents=(
            "Malformed accession numbers breaking sec.gov links and the join to financial_fact"
        ),
    ),
    DQCheck(
        name="filing_cik_padded",
        table=_SILVER_FILING,
        severity="reject",
        expression=r"cik RLIKE '^[0-9]{10}$'",
        prevents=(
            "Unpadded CIKs splitting one company across multiple join keys in every"
            " downstream table"
        ),
    ),
    DQCheck(
        name="filing_form_type_present",
        table=_SILVER_FILING,
        severity="reject",
        expression="form_type IS NOT NULL AND length(form_type) > 0",
        prevents=(
            "Null form types making amendment detection and gold activity counts silently wrong"
        ),
    ),
    DQCheck(
        name="filing_filed_date_present",
        table=_SILVER_FILING,
        severity="reject",
        expression="filed_date IS NOT NULL",
        prevents=("Null filed dates breaking restatement ordering, which is ordered by filed_date"),
    ),
    DQCheck(
        name="filing_filed_date_sane",
        table=_SILVER_FILING,
        severity="warn",
        expression="filed_date >= DATE'1993-01-01' AND filed_date <= current_date()",
        prevents=(
            "Obviously wrong filed dates (pre-EDGAR or future) polluting activity trends unnoticed"
        ),
    ),
    # ── silver.company (§3.2) ───────────────────────────────────────────────
    DQCheck(
        name="company_cik_padded",
        table=_SILVER_COMPANY,
        severity="reject",
        expression=r"cik RLIKE '^[0-9]{10}$'",
        prevents=(
            "Unpadded CIKs splitting one company across multiple join keys in every"
            " downstream table"
        ),
    ),
    DQCheck(
        name="company_name_present",
        table=_SILVER_COMPANY,
        severity="reject",
        expression="name IS NOT NULL AND length(name) > 0",
        prevents="Nameless company rows rendering as blanks in the UI search panel",
    ),
    DQCheck(
        name="company_one_current_per_cik",
        table=_SILVER_COMPANY,
        severity="reject_batch",
        expression=("sum(CASE WHEN is_current THEN 1 ELSE 0 END) OVER (PARTITION BY cik) = 1"),
        prevents=(
            "Multiple current SCD-2 versions per cik fanning out every downstream join"
            " and doubling gold row counts"
        ),
    ),
    DQCheck(
        name="company_valid_range",
        table=_SILVER_COMPANY,
        severity="reject_batch",
        expression="valid_to IS NULL OR valid_to >= valid_from",
        prevents="Negative validity intervals corrupting as-of joins against the dimension",
    ),
    # ── silver.financial_fact (§3.3) ────────────────────────────────────────
    DQCheck(
        name="fact_cik_padded",
        table=_SILVER_FACT,
        severity="reject",
        expression=r"cik RLIKE '^[0-9]{10}$'",
        prevents=(
            "Unpadded CIKs splitting one company across multiple join keys in every"
            " downstream table"
        ),
    ),
    DQCheck(
        name="fact_accession_format",
        table=_SILVER_FACT,
        severity="reject",
        expression=r"accession_number RLIKE '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'",
        prevents=(
            "Malformed asserting accessions breaking the restatement self-join and sec.gov links"
        ),
    ),
    DQCheck(
        name="fact_unit_present",
        table=_SILVER_FACT,
        severity="reject",
        expression="unit IS NOT NULL AND length(unit) > 0",
        prevents=(
            "Null units letting restatement detection compare values measured in different units"
        ),
    ),
    DQCheck(
        name="fact_value_present",
        table=_SILVER_FACT,
        severity="reject",
        expression="value IS NOT NULL",
        prevents="Null fact values crashing delta computation in gold restatement detection",
    ),
    DQCheck(
        name="fact_period_end_present",
        table=_SILVER_FACT,
        severity="reject",
        expression="period_end IS NOT NULL",
        prevents=("Facts without a period end being unassignable to any reporting period in gold"),
    ),
    DQCheck(
        name="fact_period_order",
        table=_SILVER_FACT,
        severity="reject",
        expression="period_start IS NULL OR period_end >= period_start",
        prevents=(
            "Negative-length duration periods poisoning period-scoped comparisons"
            " (instant facts pass by design)"
        ),
    ),
    DQCheck(
        name="fact_grain_unique",
        table=_SILVER_FACT,
        severity="reject_batch",
        expression=(
            "count(*) OVER (PARTITION BY cik, taxonomy, concept, unit,"
            " period_start, period_end, accession_number) = 1"
        ),
        prevents=(
            "Duplicate rows at the declared grain double-counting facts and fabricating"
            " restatement events"
        ),
    ),
    DQCheck(
        name="fact_value_magnitude",
        table=_SILVER_FACT,
        severity="warn",
        expression="abs(value) < 1e15",
        prevents=(
            "Unit-scale mistakes (dollars misread as millions) flooding gold with"
            " absurd values unnoticed"
        ),
    ),
)


def checks_for(table: str) -> tuple[DQCheck, ...]:
    """Return every declared check for a fully qualified table name.

    Does not handle: unknown tables — returns an empty tuple, by design, so
    repo 4 can call it for every table it touches.
    """
    return tuple(check for check in DQ_CHECKS if check.table == table)
