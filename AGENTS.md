# Repo 1 / 5 — `1sde-databricks-edgar-01-contracts`

> **How to use this file.** Copy it to the repo root as `AGENTS.md`. It is the
> complete brief for a coding agent building this repo. Sections 0–8 are agent
> instructions. Section 9 is for **you**, by hand. Section 10 is what the next repo
> consumes — do not change it without bumping the major version.
>
> GitHub: `github.com/Dark417/1sde-databricks-edgar-01-contracts`
> Build order position: **1 of 5. Nothing else compiles until this is published.**

---

## 0. Read first

You are building the shared contract layer for a Databricks medallion lakehouse that
ingests SEC EDGAR filings and XBRL financial facts. Four other repos depend on this
one. None of them may depend on each other.

**Authoritative background docs** (place in `docs/` before starting):
`00-design-doc.md`, `02-data-contracts.md`. You may not contradict them. If this file
and those disagree, stop and report the conflict rather than picking one.

**The single idea this repo exists to enforce:** the lakehouse schema has two
representations — Liquibase changelogs (which create the tables) and Python/Spark
schema objects (which other repos' code compiles against). They will drift. A CI test
that mechanically diffs them is the reason this repo is worth having. Build that test
even if nothing else is finished.

---

## 1. Scope

### Owns
- Liquibase changelogs: the DDL for every bronze/silver/gold Delta table.
- Python package `edgar_lakehouse_contracts`: Pydantic models, Spark `StructType`s,
  table/path name constants, DQ rule registry, concept mappings.
- The schema-drift test between the two.
- Semver policy, migration policy, and the landing-transport ADR.

### Does NOT own
- Any Terraform. (repo 2)
- Any HTTP client, any Spark job, any API. (repos 3/4/5)
- Creating the catalog, schemas, or volume — Liquibase migrates *tables*; the
  catalog/schema/volume are Terraform resources in repo 2. Changelogs assume they
  exist.
- Runtime DQ *execution*. This repo declares checks; repo 4 runs them.

### Explicit non-goal
No business logic. If a function does anything other than describe or validate shape,
it belongs in another repo.

---

## 2. Prerequisites from earlier repos

None. This is repo 1.

**Human-supplied inputs you must be given before generating:**

| Input | Where it comes from | Used for |
|---|---|---|
| `ADR-001` result (`s3` or `volume`) | Runbook step 0 probe | `landing_path()` default mode |
| Free Edition `system.*` availability | Runbook step 0.5 probe | whether Liquibase snapshot/rollback features are usable |

If either is unknown, generate against `LANDING_MODE=volume` and mark the ADR
`UNRESOLVED`. Do not guess `s3`.

---

## 3. Tech baseline

```
Python        3.11
Packaging     hatchling, PEP 621 pyproject.toml
Validation    pydantic >= 2.7
Lint/format   ruff
Types         mypy --strict
Tests         pytest, pytest-cov
Liquibase     >= 4.30 + liquibase-databricks extension (OSS)
JDBC          Databricks JDBC driver
```

**Allowed runtime dependencies:** `pydantic` only.
**Allowed dev dependencies:** `pyspark`, `delta-spark`, `pytest`, `ruff`, `mypy`,
`pyyaml`.

**Hard rule:** `pyspark` must NOT be a runtime dependency. Repos 3 and 5 import this
package without Spark installed. Spark schema construction goes behind a lazy import.
A test asserts `import edgar_lakehouse_contracts` succeeds in an environment with no
`pyspark` on the path.

---

## 4. Layered structure

```
1sde-databricks-edgar-01-contracts/
├── AGENTS.md                        # this file
├── pyproject.toml
├── README.md
├── src/edgar_lakehouse_contracts/
│   ├── __init__.py                  # __version__
│   ├── py.typed
│   ├── names.py                     # L0: pure constants + path builders
│   ├── envelope.py                  # L1: landing envelope model
│   ├── models.py                    # L1: Pydantic record models
│   ├── concepts.py                  # L1: XBRL concept set + canonical map
│   ├── dq.py                        # L2: DQCheck registry
│   └── spark/
│       ├── __init__.py              # lazy import guard
│       └── schemas.py               # L2: StructType per table
├── changelog/
│   ├── db.changelog-root.yaml       # includes, in order
│   ├── 001-schemas-bootstrap.yaml   # no-op guard; documents Terraform ownership
│   ├── 010-bronze.yaml
│   ├── 020-silver.yaml
│   ├── 030-silver-quarantine.yaml
│   ├── 040-gold.yaml
│   └── liquibase.properties.example
├── docs/
│   ├── 00-design-doc.md
│   ├── 02-data-contracts.md
│   ├── ADR-001-landing-transport.md
│   ├── ADR-002-liquibase-vs-python-schemas.md
│   └── MIGRATION.md
├── tests/
└── .github/workflows/ci.yml
```

**Layer rule:** L0 imports nothing. L1 imports L0 only. L2 imports L0+L1. No cycles.
`spark/` is a leaf that nothing else in the package imports.

---

## 5. Non-negotiable rules for the agent

1. **Never invent schema.** Every column, type, and nullability comes from
   `docs/02-data-contracts.md`. If a column you need is not there, stop and report it.
2. **`cik` is `STRING`, always.** Leading zeros are semantically meaningful in EDGAR
   URLs. Any code that makes it an int is a bug. Add a comment saying so at every
   definition site — this mistake gets made repeatedly.
3. **Every `DQCheck` must have a non-empty `prevents` field ≥ 20 characters** naming
   the concrete failure it prevents. This is enforced by a test. A check whose author
   cannot name the failure is cargo cult and must be deleted, not documented.
4. **Timestamps are UTC `TIMESTAMP`. Dates are `DATE`.** No string dates escape L1.
5. **Deterministic hashing.** `batch_id` and any surrogate key use `sha256` over a
   sorted, explicitly-delimited string. Never Python's `hash()` (randomized per
   process). Never dict iteration order.
6. **No I/O anywhere in this package.** No file reads, no network, no Spark session
   creation. It is a description of shape, nothing more.
7. **Docstrings state what the function does NOT handle.** One line, mandatory, on
   every public callable.
8. **Changelogs are append-only.** Never edit a shipped changeset. Liquibase tracks
   checksums; editing an applied changeset breaks every downstream environment. Add a
   new changeset instead.
9. **Every changeset has `rollback`** — explicit, even when it is a bare `DROP TABLE`.
   Liquibase can auto-generate some rollbacks; do not rely on it for anything
   non-trivial.
10. **No `createIndex`.** Unsupported by the Databricks extension. Use
    `changeClusterColumns` (maps to Delta `CLUSTER BY`) when clustering is wanted.
11. When ambiguous, **stop and ask**. Do not guess and do not leave a `TODO`.

---

## 6. Features to generate

### F-1 · `names.py` (L0)
```python
CATALOG: Final[str] = "edgar"
SCHEMA_LANDING: Final[str] = "landing"
SCHEMA_BRONZE: Final[str] = "bronze"
SCHEMA_SILVER: Final[str] = "silver"
SCHEMA_GOLD: Final[str] = "gold"

RAW_BUCKET_DEFAULT: Final[str] = "edgar-lake-raw"
SERVING_BUCKET_DEFAULT: Final[str] = "edgar-lake-serving"
VOLUME_LANDING: Final[str] = "/Volumes/edgar/landing/edgar"


class Stream(StrEnum):
    FILING_INDEX = "filing_index"
    COMPANY_SUBMISSIONS = "company_submissions"
    COMPANY_CONCEPT = "company_concept"


def table(schema: str, name: str) -> str: ...
def batch_id(stream: str | Stream, logical_date: date) -> str: ...
def landing_path(
    mode: Literal["s3", "volume"],
    stream: str | Stream,
    logical_date: date,
    raw_bucket: str = RAW_BUCKET_DEFAULT,
) -> str: ...
def pad_cik(cik: str | int) -> str: ...  # -> 10-char zero-padded string
def normalize_accession(raw: str) -> str: ...  # -> 0001234567-26-000123
```

**Acceptance**
- `batch_id(Stream.FILING_INDEX, date(2026,7,29))` equals a hardcoded expected value
  in the test. Determinism across processes is the point.
- `landing_path` produces the **same filename** in both modes; only the prefix differs.
- `normalize_accession("0001234567-26-000123")` and
  `normalize_accession("000123456726000123")` return the same value.
- `pad_cik(320193) == "0000320193"`.

### F-2 · `envelope.py` + `models.py` (L1)
`LandingEnvelope` with fields `_stream, _logical_date, _batch_id, _fetched_at,
_source_url, _schema_version, payload` (use Pydantic aliases; leading underscores are
not valid Python field names — alias them).

`FilingIndexRecord`: `company_name, form_type, cik, date_filed, file_name`. All
`str` — this is the *raw* record; typing happens in silver.

**Acceptance:** round-trip test — model → JSON → model produces a byte-identical
JSON payload. `_logical_date` serializes as `YYYY-MM-DD`, never as a datetime.

### F-3 · `concepts.py` (L1)
`CONCEPT_SET: Final[tuple[str, ...]]` — the 15 concepts from `02-data-contracts.md` §0.
`CONCEPT_CANONICAL_MAP: Final[Mapping[str, str]]` — MVP2 has exactly one canonical
target, `revenue_total`, mapping from `Revenues` and
`RevenueFromContractWithCustomerExcludingAssessedTax`.

**Acceptance:** a test asserts every key of the map is in `CONCEPT_SET`. Add a module
docstring stating that coalescing those two concepts is best-effort and that the
as-filed `concept` is always retained alongside `concept_canonical`.

### F-4 · `dq.py` (L2)
```python
@dataclass(frozen=True, slots=True)
class DQCheck:
    name: str
    table: str
    severity: Literal["reject", "warn", "reject_batch"]
    expression: str  # Spark SQL boolean; True means the row is GOOD
    prevents: str  # REQUIRED, >= 20 chars


DQ_CHECKS: Final[tuple[DQCheck, ...]] = ...


def checks_for(table: str) -> tuple[DQCheck, ...]: ...
```
Populate from `02-data-contracts.md` §3.1–3.3, every check, exactly once.

Note the three severities: `reject` quarantines the row, `warn` emits a metric and
keeps the row, `reject_batch` fails the whole job (used for the SCD-2 invariants,
where a single bad row means the dimension is structurally broken).

**Acceptance**
- Test: all `prevents` non-empty and ≥ 20 chars.
- Test: `name` values unique.
- Test: every check's `table` resolves via `names.table()`.

### F-5 · `spark/schemas.py` (L2)
One `StructType` per bronze and silver table. Module-level lazy import:
```python
def _spark_types():
    from pyspark.sql import types as T

    return T
```
Expose `SCHEMAS: Mapping[str, "StructType"]` built lazily, and
`get_schema(table_fqn: str) -> StructType`.

**Acceptance:** `import edgar_lakehouse_contracts` succeeds with `pyspark` absent
(test runs in a subprocess with a stripped `sys.path`).

### F-6 · Liquibase changelogs
YAML format, one file per layer, `db.changelog-root.yaml` includes them in order.

`010-bronze.yaml` — bronze tables. Every table gets the six metadata columns
(`_source_file, _ingest_ts, _batch_id, _logical_date, _schema_version, _rescued_data`).
`020-silver.yaml` — `filing`, `company`, `financial_fact`.
`030-silver-quarantine.yaml` — one quarantine table per silver table.
`040-gold.yaml` — the four gold tables.

Changeset conventions:
```yaml
databaseChangeLog:
  - changeSet:
      id: 020-silver-filing-create
      author: dark417
      changes:
        - createTable:
            catalogName: edgar
            schemaName: silver
            tableName: filing
            columns:
              - column: {name: accession_number, type: STRING, constraints: {nullable: false}}
              # ...
      rollback:
        - dropTable: {catalogName: edgar, schemaName: silver, tableName: filing}
```

**Acceptance**
- `liquibase validate` passes offline.
- Every changeset has an explicit `rollback` block.
- No `createIndex` anywhere (grep gate in CI).
- Changeset ids are unique and prefixed with their file number.

### F-7 · The drift test 🔴 — *the reason this repo exists*
`tests/test_schema_drift.py`. Parse the changelog YAML, build the implied
`{table: {column: type}}` map, compare against `spark/schemas.py`.

Assert, per table:
- identical column name sets (report symmetric difference),
- identical type per column (normalize `STRING`/`StringType`, `TIMESTAMP`/
  `TimestampType`, `DECIMAL(38,6)`/`DecimalType(38,6)`),
- identical nullability.

Failure message must name the table, the column, and both sides. A message that says
only "schemas differ" is useless at 11 p.m. and will be rejected in review.

**Acceptance:** deliberately break one column type in a fixture copy of the changelog;
the test fails with a message naming that exact column.

### F-8 · Docs
- `ADR-001-landing-transport.md` — human fills the probe result; template with the
  decision table from the runbook.
- `ADR-002-liquibase-vs-python-schemas.md` — write this one fully. Content: why two
  representations exist (Liquibase creates tables; Python is what code compiles
  against), why they are not generated from each other (generation couples the release
  cycle of five repos to one codegen step and hides drift inside a build), and why the
  drift test is the chosen alternative.
- `MIGRATION.md` — expand → migrate → contract, with the rollout order
  `contracts → pipelines → ingest → serving`.

---

## 7. Testing requirements

| Requirement | Threshold |
|---|---|
| Line coverage | ≥ 90% (this package is small and pure; there is no excuse) |
| Network calls in tests | zero |
| Spark session in unit tests | only in `tests/spark/`, marked `@pytest.mark.spark` |
| No-pyspark import test | required (F-5) |
| Drift test | required, must fail loudly (F-7) |

---

## 8. CI — `.github/workflows/ci.yml`

Triggers: `push` to `main`, `pull_request`, `tag: v*`.

```
job build:
  - ruff check . && ruff format --check .
  - mypy --strict src/
  - pytest -m "not spark" --cov --cov-fail-under=90
  - pytest -m spark
  - grep gate: no "createIndex" in changelog/
  - liquibase validate (offline, no JDBC connection)
job publish (tag only):
  - python -m build
  - aws s3 cp dist/*.whl s3://$TF_BUCKET/wheels/ --acl private
  - gh release create with the wheel attached
```

Auth to AWS via OIDC (`aws-actions/configure-aws-credentials`), not long-lived keys.
The role ARN comes from repo 2 — until repo 2 exists, publish manually (§9.7).

---

## 9. EXECUTION — what you do manually

### 9.1 Create the repo
```bash
gh repo create Dark417/1sde-databricks-edgar-01-contracts \
  --private --add-readme --gitignore Python --license mit --clone
cd 1sde-databricks-edgar-01-contracts
```

### 9.2 Place the background docs 🔴
Copy `00-design-doc.md` and `02-data-contracts.md` into `docs/`, commit, **then**
point the agent at this file. The agent cannot build correct schema without them.

### 9.3 Resolve ADR-001 (runbook step 0)
Fill in `docs/ADR-001-landing-transport.md` with the probe result before generating
`names.py`. If unresolved, the agent defaults to `volume`.

### 9.4 Probe `system.*` availability (new — Liquibase depends on it)
The Databricks Liquibase extension uses Unity Catalog system tables for snapshotting
and constraint discovery. Verify in a notebook:
```sql
SELECT * FROM system.information_schema.tables LIMIT 1;
```
- **Works** → Liquibase `snapshot`, `diff`, and constraint change types are available.
- **Fails** → `update` and `rollback` still work (they use `DATABASECHANGELOG`), but
  `diff`/`snapshot` do not. Record this in `ADR-002` and do not build CI around
  `liquibase diff`.

### 9.5 Set up Liquibase locally
```bash
brew install liquibase
# extension + JDBC driver into the Liquibase lib dir:
#   liquibase-databricks-<ver>.jar   (github.com/liquibase/liquibase-databricks releases)
#   DatabricksJDBC42.jar             (Databricks JDBC driver download)

cp changelog/liquibase.properties.example changelog/liquibase.properties  # gitignored
```
`liquibase.properties`:
```properties
url=jdbc:databricks://<workspace-host>:443/default;transportMode=http;ssl=1;\
httpPath=/sql/1.0/warehouses/<warehouse-id>;ConnCatalog=edgar;ConnSchema=default
username=token
password=<PAT>
changeLogFile=changelog/db.changelog-root.yaml
```
🔴 `liquibase.properties` is gitignored. The PAT never enters the repo.

### 9.6 First run — order matters
```bash
liquibase validate                    # offline, no connection
liquibase update-sql > /tmp/plan.sql  # READ THIS BEFORE APPLYING
liquibase update
```
**Do not run `update` before repo 2 has created the catalog and schemas.** Liquibase
migrates tables, not catalogs. Expected first-time failure if you skip that:
`Catalog 'edgar' does not exist`. That is the correct behavior, not a bug.

Chicken-and-egg resolution: run repo 2's `terraform apply` for the catalog/schema
resources first, then come back here.

### 9.7 Publish v0.1.0 by hand (before repo 2 CI exists)
The target bucket is created by repo 2 §9.1's hand bootstrap — run that first. It is
a by-hand step and does not require repo 2's Terraform to exist yet.
```bash
python -m build
aws s3 cp dist/edgar_lakehouse_contracts-0.1.0-py3-none-any.whl \
  s3://<tf-bucket>/wheels/
git tag v0.1.0 && git push --tags
```

### 9.8 Record the published version
Every downstream repo pins this exact string. Write it down:
```
CONTRACTS_VERSION=0.1.0
```

---

## 10. Published outputs — what repos 2–5 consume

| Output | Form | Consumed by |
|---|---|---|
| `edgar_lakehouse_contracts` wheel | `s3://<tf-bucket>/wheels/*.whl` + GitHub release | 3, 4, 5 |
| `CONTRACTS_VERSION` | semver string, pinned | 2 (SSM), 3, 4, 5 (pyproject) |
| `changelog/` | applied by Liquibase | 4 (job depends on tables existing) |
| `names.py` constants | catalog/schema/volume/bucket names | 2 (Terraform must match these exactly) |
| `DQ_CHECKS` | registry | 4 (executes them) |
| `ADR-001` result | `s3` \| `volume` | 2, 3, 4 |

**Contract with downstream repos:** they pin an exact version. They never read
`main`. A `MAJOR` bump requires the rollout in `MIGRATION.md`.

---

## 11. Definition of done

- [ ] `ruff`, `mypy --strict`, `pytest` all green locally
- [ ] Coverage ≥ 90%
- [ ] `import edgar_lakehouse_contracts` works without pyspark
- [ ] `liquibase validate` passes
- [ ] `liquibase update` applied against the real workspace, `DATABASECHANGELOG`
      populated
- [ ] Drift test fails when a changelog type is deliberately broken
- [ ] Every `DQCheck.prevents` names a real failure
- [ ] ADR-001 and ADR-002 filled in, not templates
- [ ] `v0.1.0` tagged, wheel published, `CONTRACTS_VERSION` recorded

---

## 12. References

1. `liquibase/liquibase-databricks` — https://github.com/liquibase/liquibase-databricks
2. Using Liquibase with Databricks — https://docs.liquibase.com/start/tutorials/databricks.html
3. Liquibase YAML changelog reference — https://docs.liquibase.com/concepts/changelogs/yaml-format.html
4. Databricks JDBC driver — https://docs.databricks.com/aws/en/integrations/jdbc/
5. Unity Catalog table types (managed vs external) — https://docs.databricks.com/aws/en/tables/types
6. Pydantic v2 — https://docs.pydantic.dev/latest/
