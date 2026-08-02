"""F-7 🔴 the drift test: Liquibase changelogs vs Spark StructTypes.

The lakehouse schema has two representations — the changelogs create the
tables, the StructTypes are what code compiles against. They are not generated
from each other (ADR-002); this test is what keeps them identical.

Failure messages name the table, the column, and both sides — "schemas differ"
is useless at 11 p.m.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from edgar_lakehouse_contracts.spark import schemas as spark_schemas

REPO_ROOT = Path(__file__).parents[1]
CHANGELOG_DIR = REPO_ROOT / "changelog"
# Drift scope: every table, gold included. Gold entered scope at v1.0.0 because
# repo 4 builds those marts and compiles against their StructTypes.
#
# ORDER MATTERS. These are applied in changelog order, and later changes mutate what
# earlier ones created: a later createTable replaces the table (how 050's
# drop-and-recreate is modelled), while addColumn/dropColumn and ALTER COLUMN edit it in
# place (how 060's additive migration is modelled). The result is the effective schema,
# exactly as Liquibase leaves the database.
TABLE_CHANGELOGS = (
    "010-bronze.yaml",
    "020-silver.yaml",
    "030-silver-quarantine.yaml",
    "040-gold.yaml",
    "050-realign-v1.yaml",
    "060-versioning-and-keys.yaml",
    "080-clustering.yaml",
)

ColumnMap = dict[str, tuple[str, bool]]  # column -> (normalized type, nullable)

# Raw-SQL changes this parser understands. Anything else raises: a statement that
# silently does nothing here is a statement whose effect on the schema is untested,
# which is the whole failure mode this file exists to prevent.
_SET_NOT_NULL = re.compile(
    r"^ALTER\s+TABLE\s+(?P<fqn>[\w.]+)\s+ALTER\s+COLUMN\s+(?P<col>\w+)\s+SET\s+NOT\s+NULL$",
    re.IGNORECASE,
)
_DROP_NOT_NULL = re.compile(
    r"^ALTER\s+TABLE\s+(?P<fqn>[\w.]+)\s+ALTER\s+COLUMN\s+(?P<col>\w+)\s+DROP\s+NOT\s+NULL$",
    re.IGNORECASE,
)
# Layout and view statements do not change column shape, so they are irrelevant here --
# but they must be recognized explicitly rather than falling through to the error.
_IGNORED_SQL = re.compile(
    r"^(ALTER\s+TABLE\s+[\w.]+\s+CLUSTER\s+BY\b|CREATE\s+OR\s+REPLACE\s+VIEW\b|DROP\s+VIEW\b)",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_type(type_str: str) -> str:
    return type_str.strip().lower().replace(" ", "")


def _column_entry(column: dict[str, Any]) -> tuple[str, tuple[str, bool]]:
    constraints = column.get("constraints") or {}
    nullable = constraints.get("nullable", True)
    return column["name"], (_normalize_type(str(column["type"])), bool(nullable))


def _apply_sql(statement: str, tables: dict[str, ColumnMap]) -> None:
    """Apply one raw-SQL change to the accumulated schema."""
    sql = " ".join(statement.split()).rstrip(";")
    if not sql or _IGNORED_SQL.match(sql):
        return
    for pattern, nullable in ((_SET_NOT_NULL, False), (_DROP_NOT_NULL, True)):
        match = pattern.match(sql)
        if match:
            fqn, col = match.group("fqn"), match.group("col")
            if fqn not in tables or col not in tables[fqn]:
                raise AssertionError(f"ALTER COLUMN targets an unknown column: {fqn}.{col}")
            current_type, _ = tables[fqn][col]
            tables[fqn][col] = (current_type, nullable)
            return
    raise AssertionError(
        f"changelog contains raw SQL this drift test does not model: {sql!r}. "
        "Teach the parser about it or express the change as a Liquibase primitive -- "
        "silently ignoring it means its effect on the schema is never checked."
    )


def parse_changelog_tables(
    path: Path, tables: dict[str, ColumnMap] | None = None
) -> dict[str, ColumnMap]:
    """Fold one changelog file into {table_fqn: {column: (type, nullable)}}.

    Pass the accumulator from a previous file to model changelogs applied in order;
    omit it to parse a file in isolation (which is what the broken-fixture test does).
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    tables = {} if tables is None else tables
    for entry in doc.get("databaseChangeLog", []):
        change_set = entry.get("changeSet")
        if not change_set:
            continue
        for change in change_set.get("changes", []):
            if create := change.get("createTable"):
                fqn = f"{create['catalogName']}.{create['schemaName']}.{create['tableName']}"
                columns: ColumnMap = {}
                for wrapper in create["columns"]:
                    name, spec = _column_entry(wrapper["column"])
                    columns[name] = spec
                tables[fqn] = columns
            elif add := change.get("addColumn"):
                fqn = f"{add['catalogName']}.{add['schemaName']}.{add['tableName']}"
                for wrapper in add["columns"]:
                    name, spec = _column_entry(wrapper["column"])
                    tables.setdefault(fqn, {})[name] = spec
            elif drop := change.get("dropColumn"):
                fqn = f"{drop['catalogName']}.{drop['schemaName']}.{drop['tableName']}"
                tables.get(fqn, {}).pop(drop["columnName"], None)
            elif "dropTable" in change:
                continue  # always paired with the createTable that replaces it
            elif "sql" in change:
                _apply_sql(str(change["sql"]["sql"]), tables)
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


def _effective_changelog_schema() -> dict[str, ColumnMap]:
    """Fold every changelog in order into the schema Liquibase actually leaves behind."""
    changelog: dict[str, ColumnMap] = {}
    for filename in TABLE_CHANGELOGS:
        parse_changelog_tables(CHANGELOG_DIR / filename, changelog)
    return changelog


def test_no_drift_between_changelogs_and_spark_schemas() -> None:
    problems = diff_schemas(_effective_changelog_schema(), _spark_side())
    assert not problems, "schema drift detected:\n" + "\n".join(problems)


def test_every_changelog_in_the_root_is_covered_by_this_test() -> None:
    """A changelog nobody folds in is a changelog whose schema effect is unchecked.

    Without this, adding `090-something.yaml` to the root and forgetting to list it in
    TABLE_CHANGELOGS makes the drift test quietly stop covering it -- the same shape of
    failure as a gate that compares against nothing.
    """
    root = yaml.safe_load((CHANGELOG_DIR / "db.changelog-root.yaml").read_text(encoding="utf-8"))
    included = [
        entry["include"]["file"] for entry in root["databaseChangeLog"] if "include" in entry
    ]
    # 001 creates schemas, not tables; 070 creates views, which have no StructType.
    schema_only = {"001-schemas-bootstrap.yaml", "070-gold-views.yaml"}
    expected = [f for f in included if f not in schema_only]
    assert expected == list(TABLE_CHANGELOGS), (
        f"changelogs in the root but not folded into the drift test: "
        f"{sorted(set(expected) - set(TABLE_CHANGELOGS))}"
    )


def test_unmodelled_raw_sql_is_rejected_rather_than_ignored() -> None:
    """The parser must refuse SQL it does not understand."""
    tables: dict[str, ColumnMap] = {}
    with pytest.raises(AssertionError, match="does not model"):
        _apply_sql("ALTER TABLE edgar.silver.company ADD COLUMN sneaky STRING", tables)


def test_set_not_null_is_actually_applied() -> None:
    tables: dict[str, ColumnMap] = {"edgar.silver.company": {"version_number": ("int", True)}}
    _apply_sql("ALTER TABLE edgar.silver.company ALTER COLUMN version_number SET NOT NULL", tables)
    assert tables["edgar.silver.company"]["version_number"] == ("int", False)


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
