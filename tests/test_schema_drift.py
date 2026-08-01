"""F-7 🔴 the drift test: Liquibase changelogs vs Spark StructTypes.

The lakehouse schema has two representations — the changelogs create the
tables, the StructTypes are what code compiles against. They are not generated
from each other (ADR-002); this test is what keeps them identical.

Failure messages name the table, the column, and both sides — "schemas differ"
is useless at 11 p.m.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from edgar_lakehouse_contracts.spark import schemas as spark_schemas

REPO_ROOT = Path(__file__).parents[1]
CHANGELOG_DIR = REPO_ROOT / "changelog"
# Drift scope: bronze + silver (StructTypes exist for exactly those — gold is
# created by Liquibase but no repo compiles Spark code against it, F-5).
TABLE_CHANGELOGS = ("010-bronze.yaml", "020-silver.yaml", "030-silver-quarantine.yaml")

ColumnMap = dict[str, tuple[str, bool]]  # column -> (normalized type, nullable)


def _normalize_type(type_str: str) -> str:
    return type_str.strip().lower().replace(" ", "")


def parse_changelog_tables(path: Path) -> dict[str, ColumnMap]:
    """Build {table_fqn: {column: (type, nullable)}} from one changelog file."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    tables: dict[str, ColumnMap] = {}
    for entry in doc.get("databaseChangeLog", []):
        change_set = entry.get("changeSet")
        if not change_set:
            continue
        for change in change_set.get("changes", []):
            create = change.get("createTable")
            if not create:
                continue
            fqn = f"{create['catalogName']}.{create['schemaName']}.{create['tableName']}"
            columns: ColumnMap = {}
            for wrapper in create["columns"]:
                column: dict[str, Any] = wrapper["column"]
                constraints = column.get("constraints") or {}
                nullable = constraints.get("nullable", True)
                columns[column["name"]] = (_normalize_type(str(column["type"])), bool(nullable))
            tables[fqn] = columns
    return tables


def _spark_side() -> dict[str, ColumnMap]:
    return {
        fqn: {
            field.name: (_normalize_type(field.dataType.simpleString()), field.nullable)
            for field in struct.fields
        }
        for fqn, struct in spark_schemas.SCHEMAS.items()
    }


def diff_schemas(changelog: dict[str, ColumnMap], spark: dict[str, ColumnMap]) -> list[str]:
    """Return one human-readable line per difference; empty means no drift."""
    problems: list[str] = []
    for fqn in sorted(set(changelog) - set(spark)):
        problems.append(f"{fqn}: in changelog but has no StructType in spark/schemas.py")
    for fqn in sorted(set(spark) - set(changelog)):
        problems.append(f"{fqn}: has a StructType but is missing from the changelogs")
    for fqn in sorted(set(changelog) & set(spark)):
        cl_cols, sp_cols = changelog[fqn], spark[fqn]
        for col in sorted(set(cl_cols) - set(sp_cols)):
            problems.append(f"{fqn}.{col}: in changelog only (missing from StructType)")
        for col in sorted(set(sp_cols) - set(cl_cols)):
            problems.append(f"{fqn}.{col}: in StructType only (missing from changelog)")
        for col in sorted(set(cl_cols) & set(sp_cols)):
            cl_type, cl_null = cl_cols[col]
            sp_type, sp_null = sp_cols[col]
            if cl_type != sp_type:
                problems.append(
                    f"{fqn}.{col}: type drift — changelog={cl_type!r} vs StructType={sp_type!r}"
                )
            if cl_null != sp_null:
                problems.append(
                    f"{fqn}.{col}: nullability drift — changelog nullable={cl_null}"
                    f" vs StructType nullable={sp_null}"
                )
    return problems


def test_no_drift_between_changelogs_and_spark_schemas() -> None:
    changelog: dict[str, ColumnMap] = {}
    for filename in TABLE_CHANGELOGS:
        changelog.update(parse_changelog_tables(CHANGELOG_DIR / filename))
    problems = diff_schemas(changelog, _spark_side())
    assert not problems, "schema drift detected:\n" + "\n".join(problems)


def test_drift_is_detected_and_names_the_column() -> None:
    # F-7 acceptance: a deliberately broken fixture (silver.filing.filed_date
    # declared STRING instead of DATE) must fail naming that exact column.
    broken = parse_changelog_tables(REPO_ROOT / "tests" / "fixtures" / "broken-020-silver.yaml")
    spark = {fqn: cols for fqn, cols in _spark_side().items() if fqn in broken}
    problems = diff_schemas(broken, spark)
    assert problems, "broken fixture produced no drift — the drift test is not working"
    message = "\n".join(problems)
    assert "edgar.silver.filing" in message
    assert "filed_date" in message
    assert "string" in message and "date" in message
