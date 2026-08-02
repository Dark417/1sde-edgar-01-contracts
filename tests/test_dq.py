"""Tests for the DQ registry (repo rules 3 and F-4 acceptance)."""

from __future__ import annotations

import re

from edgar_lakehouse_contracts import names
from edgar_lakehouse_contracts.dq import DQ_CHECKS, checks_for


def test_every_prevents_is_meaningful() -> None:
    # A check whose author cannot name the failure it prevents is cargo cult.
    offenders = [c.name for c in DQ_CHECKS if len(c.prevents.strip()) < 20]
    assert not offenders, f"checks with prevents < 20 chars: {offenders}"


def test_names_unique() -> None:
    seen = [c.name for c in DQ_CHECKS]
    assert len(seen) == len(set(seen))


def test_every_table_resolves_via_names_table() -> None:
    for check in DQ_CHECKS:
        catalog, schema, table_name = check.table.split(".")
        assert check.table == names.table(schema, table_name)
        assert catalog == names.CATALOG
        assert schema in {names.SCHEMA_SILVER, names.SCHEMA_BRONZE, names.SCHEMA_GOLD}


def test_severities_are_valid() -> None:
    assert {c.severity for c in DQ_CHECKS} <= {"reject", "warn", "reject_batch"}


def test_checks_for_returns_only_that_table() -> None:
    fact_table = names.table(names.SCHEMA_SILVER, "financial_fact")
    checks = checks_for(fact_table)
    assert checks
    assert all(c.table == fact_table for c in checks)


def test_checks_for_unknown_table_is_empty() -> None:
    assert checks_for(names.table(names.SCHEMA_GOLD, "company_profile")) == ()


def test_scd2_invariants_are_reject_batch() -> None:
    by_name = {c.name: c for c in DQ_CHECKS}
    assert by_name["company_one_current_per_cik"].severity == "reject_batch"
    assert by_name["fact_grain_unique"].severity == "reject_batch"


def test_every_dq_expression_references_real_columns() -> None:
    """The check that would have caught the v0.1.0 drift.

    A DQ expression naming a column that does not exist fails at runtime, inside
    repo 4's job, hours after merge. Comparing the identifiers in each expression
    against the contract's own column set turns that into a unit-test failure
    here. `silver.company.name` -> `company_name` and
    `financial_fact.concept` -> `concept_tag` both slipped through before this
    existed.
    """
    from edgar_lakehouse_contracts.spark.schemas import COLUMN_SPECS

    # Bare words in a Spark SQL boolean that are NOT column references.
    sql_words = {
        "and",
        "or",
        "not",
        "is",
        "null",
        "case",
        "when",
        "then",
        "else",
        "end",
        "over",
        "partition",
        "by",
        "rlike",
        "date",
        "select",
        "from",
        "true",
        "false",
        "sum",
        "count",
        "length",
        "abs",
        "greatest",
        "current_date",
        "cast",
        "as",
    }
    offenders: list[str] = []
    for check in DQ_CHECKS:
        columns = {name for name, _, _ in COLUMN_SPECS[check.table]}
        # strip string literals, then take bare identifiers
        expr = re.sub(r"'[^']*'", " ", check.expression)
        for token in re.findall(r"\b[a-z_][a-z0-9_]*\b", expr):
            if token in sql_words or token in columns:
                continue
            offenders.append(f"{check.name}: '{token}' is not a column of {check.table}")
    assert not offenders, "DQ expressions reference unknown columns:\n" + "\n".join(offenders)
