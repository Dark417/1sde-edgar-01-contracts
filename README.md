# 1sde-edgar-01-contracts

**Repo 1 of 5** in the edgar-lakehouse project — the shared contract layer for a
Databricks (AWS) medallion lakehouse over SEC EDGAR filings and XBRL financial
facts. Nothing else compiles until this is published.

```
1 contracts ─► 2 infra ─► 3 ingest ─► 4 pipelines ─► 5 serving
      ▲             │
      └─ liquibase update runs after Terraform creates the catalog
```

## What this repo owns

- **Liquibase changelogs** (`changelog/`) — the DDL for every bronze/silver/gold
  Delta table. Append-only, explicit rollbacks, applied via the
  [liquibase-databricks](https://github.com/liquibase/liquibase-databricks)
  extension.
- **`edgar_lakehouse_contracts`** (`src/`) — Pydantic models, table/path name
  constants, the DQ rule registry, XBRL concept mappings, and Spark
  `StructType`s behind a lazy import (`pyspark` is *not* a runtime dependency).
- **The schema-drift test** (`tests/test_schema_drift.py`) — mechanically diffs
  the two representations above. This test is the reason the repo exists; see
  [ADR-002](docs/ADR-002-liquibase-vs-python-schemas.md).

Authoritative background: [design doc](docs/00-design-doc.md) ·
[data contracts](docs/02-data-contracts.md) ·
[migration policy](docs/MIGRATION.md) ·
**[RUNBOOK](docs/RUNBOOK.md)** (run locally, Liquibase offline/online, connect
to your workspace)

## Layout

```
src/edgar_lakehouse_contracts/
├── names.py         # L0: constants + deterministic path/id builders
├── envelope.py      # L1: landing envelope model
├── models.py        # L1: raw record models
├── concepts.py      # L1: XBRL concept set + canonical map
├── dq.py            # L2: DQCheck registry (declared here, executed by repo 4)
└── spark/schemas.py # L2 leaf: StructTypes, lazy pyspark import
changelog/           # Liquibase YAML, one file per layer
docs/                # design doc, data contracts, ADRs, migration policy
```

## Develop

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy --strict src/
pytest -m "not spark" --cov --cov-fail-under=90
pytest -m spark                      # needs a local JVM
```

## Apply the DDL

Requires repo 2's Terraform to have created the `edgar` catalog and schemas
first (the one backward edge in the build order):

```bash
cp changelog/liquibase.properties.example changelog/liquibase.properties  # gitignored; add host + PAT
liquibase validate
liquibase update-sql   # read the plan before applying
liquibase update
```

## Consumers — installing the published wheel

This repo publishes **two artifacts by two different channels**, and consumers
use only the first:

| Artifact | Channel | Consumed by |
|---|---|---|
| `edgar_lakehouse_contracts` **wheel** | GitHub release asset | repos 3, 4, 5 — `pip install` |
| **DDL** (`changelog/`) | applied to the workspace by this repo's own CI over JDBC | nobody — it produces the *tables*, which is what consumers actually read |

Latest release: **[v1.0.0](https://github.com/Dark417/1sde-edgar-01-contracts/releases/tag/v1.0.0)**

```bash
pip install https://github.com/Dark417/1sde-edgar-01-contracts/releases/download/v1.0.0/edgar_lakehouse_contracts-1.0.0-py3-none-any.whl
```

In a Databricks notebook or serverless job:

```python
%pip install https://github.com/Dark417/1sde-edgar-01-contracts/releases/download/v1.0.0/edgar_lakehouse_contracts-1.0.0-py3-none-any.whl
dbutils.library.restartPython()
```

In a consumer's `pyproject.toml` (exact pin, never a range):

```toml
dependencies = [
  "edgar-lakehouse-contracts @ https://github.com/Dark417/1sde-edgar-01-contracts/releases/download/v1.0.0/edgar_lakehouse_contracts-1.0.0-py3-none-any.whl",
]
```

The wheel carries Python only — models, names, DQ registry, Spark
`StructType`s, `py.typed`. It deliberately does **not** contain the Liquibase
changelogs: those are executed once against the workspace, not imported
(see [ADR-002](docs/ADR-002-liquibase-vs-python-schemas.md)).

Repos 2–5 pin an exact version and never read `main`. Breaking changes follow
expand → migrate → contract with the rollout order
`contracts → pipelines → ingest → serving` (see
[MIGRATION.md](docs/MIGRATION.md)).

> Built on Databricks **Free Edition**, which is not licensed for commercial
> use — this is a portfolio/demo project.
