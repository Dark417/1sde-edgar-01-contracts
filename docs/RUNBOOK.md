# RUNBOOK — running this repo locally and against Databricks

Three layers, in order: (A) pure-local Python checks, (B) Liquibase locally,
(C) Liquibase against your real workspace. A and B need **no Databricks
account at all**.

---

## A. Run the package locally (no Databricks, no Java)

```powershell
cd 1sde-edgar-01-contracts
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

.venv\Scripts\ruff check .
.venv\Scripts\ruff format --check .
.venv\Scripts\mypy --strict src/
.venv\Scripts\pytest -m "not spark" --cov --cov-fail-under=90
```

The `not spark` suite includes the **schema-drift test** (it only imports
pyspark's pure-Python type classes, no JVM). `pytest -m spark` builds a real
SparkSession and needs a JVM — a **portable Temurin 17 JRE lives in
`tools/jre`** (gitignored, no admin install), so run it with:

```powershell
$env:JAVA_HOME = "$PWD\tools\jre"; $env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
.venv\Scripts\python -m pytest -m spark
```

Quick smoke of the package as a consumer would use it:

```powershell
.venv\Scripts\python -c @"
from datetime import date
from edgar_lakehouse_contracts import names
from edgar_lakehouse_contracts.dq import checks_for
print(names.batch_id(names.Stream.FILING_INDEX, date(2026, 7, 29)))
print(names.landing_path('s3', 'filing_index', date(2026, 7, 29)))
print(names.landing_path('volume', 'filing_index', date(2026, 7, 29)))
print(names.pad_cik(320193), names.normalize_accession('000123456726000123'))
print(len(checks_for(names.table('silver', 'financial_fact'))), 'DQ checks on financial_fact')
"@
```

---

## B. Liquibase locally — yes, it runs locally

**Liquibase always runs locally.** It is a Java CLI; the only question is what
it points at. Two modes:

| Mode | URL | Needs a workspace? | What you get |
|---|---|---|---|
| Offline | `offline:databricks` | no | `validate` (changelog syntax/refs) and `update-sql` (the exact SQL plan it *would* run) |
| Online | `jdbc:databricks://…` | yes | `update` actually creates the tables |

### Option 1 — portable install in `tools/` (already set up, verified working)

`tools/` (gitignored) contains a portable Temurin 17 JRE, the Liquibase 5.0.3
CLI, and the `liquibase-databricks` extension jar in its `lib/`. Nothing was
installed system-wide. To recreate from scratch:

```powershell
mkdir tools -Force
curl.exe -sL -o tools\jre.zip "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse"
curl.exe -sL -o tools\liquibase.zip "https://github.com/liquibase/liquibase/releases/download/v5.0.3/liquibase-5.0.3.zip"
curl.exe -sL -o tools\liquibase-databricks.jar "https://github.com/liquibase/liquibase-databricks/releases/download/v5.0.3/liquibase-databricks-5.0.3.jar"
# extract jre.zip -> tools\jre, liquibase.zip -> tools\liquibase, then:
copy tools\liquibase-databricks.jar tools\liquibase\lib\
```

Run offline validate + plan (from the repo root):

```powershell
$env:JAVA_HOME = "$PWD\tools\jre"; $env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
.\tools\liquibase\liquibase.bat --changelog-file=changelog/db.changelog-root.yaml --url=offline:databricks validate
.\tools\liquibase\liquibase.bat --changelog-file=changelog/db.changelog-root.yaml --url="offline:databricks?outputLiquibaseSql=true" update-sql > tools\plan.sql
```

Verified 2026-08-01: `validate` → "No validation errors found";
`update-sql` → 13 `CREATE TABLE` statements (3 bronze, 6 silver, 4 gold).

### Option 2 — Docker (no Java at all, but Docker Desktop must be healthy)

Mount the extension jar into the official image:

```powershell

# validate — offline, no credentials
docker run --rm `
  -v "${PWD}\changelog:/liquibase/changelog" `
  -v "${PWD}\tools\liquibase-databricks.jar:/liquibase/lib/liquibase-databricks.jar" `
  liquibase/liquibase `
  --changelog-file=changelog/db.changelog-root.yaml --url=offline:databricks validate

# generate the SQL plan — READ THIS before ever applying anything
docker run --rm `
  -v "${PWD}\changelog:/liquibase/changelog" `
  -v "${PWD}\tools\liquibase-databricks.jar:/liquibase/lib/liquibase-databricks.jar" `
  liquibase/liquibase `
  --changelog-file=changelog/db.changelog-root.yaml `
  --url="offline:databricks?outputLiquibaseSql=true" update-sql
```

(Native install instead of Docker: `choco install liquibase` — pulls a JRE —
then drop the extension jar plus the Databricks JDBC driver into Liquibase's
`lib/` folder.)

### "Databricks local alternative?"

There is **no local Databricks emulator**. The honest local substitutes, and
this project already uses all three:

1. **Spark + `delta-spark`** — a local SparkSession with Delta gives you real
   Delta tables, MERGE, time travel. This is exactly how repo 4's entire test
   suite runs without a workspace, and what `pytest -m spark` uses here.
2. **`offline:databricks`** — Liquibase's plan-only mode (above): everything
   except actually executing DDL.
3. **DuckDB over exported Parquet** — repo 5's whole design; the serving layer
   never needs Databricks even in production.

What you *cannot* fake locally: Unity Catalog (grants, `system.*` tables,
volumes), serverless jobs, Auto Loader against cloud storage. Those you test
against the Free Edition workspace itself — which is the point of having one.
(Databricks Connect is not a local alternative: it tunnels to a live
workspace.)

---

## C. Connect to your Databricks account and push the DDL

### C.1 Get a workspace (Free Edition)

1. Sign up / log in at <https://login.databricks.com/> (choose the free
   edition option) — you get one workspace on serverless compute.
2. Your **host** is the workspace URL in the browser:
   `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`

### C.2 Create a PAT

Workspace → your avatar → **Settings → Developer → Access tokens →
Generate new token**. Copy it once; store it nowhere in git. (Rotate every 90
days — it's in the project calendar rules, repo 5 §9.9.)

### C.3 Find the SQL warehouse HTTP path

**SQL Warehouses → Serverless Starter Warehouse → Connection details** →
copy `HTTP path`, looks like `/sql/1.0/warehouses/<warehouse-id>`.

### C.4 Prerequisite: the catalog and schemas must exist first

Liquibase migrates **tables**; the `edgar` catalog and its four schemas are
repo 2 Terraform resources. `liquibase update` before they exist fails with
`Catalog 'edgar' does not exist` — correct behavior, not a bug.

- **Recommended:** build repo 2 first and let `terraform apply` create them.
- **Demo shortcut** (if you want tables tonight): create them by hand in the
  SQL editor, and later reconcile with `terraform import` in repo 2:

```sql
CREATE CATALOG IF NOT EXISTS edgar;
CREATE SCHEMA IF NOT EXISTS edgar.landing;
CREATE SCHEMA IF NOT EXISTS edgar.bronze;
CREATE SCHEMA IF NOT EXISTS edgar.silver;
CREATE SCHEMA IF NOT EXISTS edgar.gold;
CREATE VOLUME IF NOT EXISTS edgar.landing.edgar;
```

### C.5 Wire the credentials into Liquibase

```powershell
copy changelog\liquibase.properties.example changelog\liquibase.properties  # gitignored
```

Edit `changelog/liquibase.properties`:

```properties
url=jdbc:databricks://dbc-xxxxxxxx-xxxx.cloud.databricks.com:443/default;transportMode=http;ssl=1;httpPath=/sql/1.0/warehouses/<warehouse-id>;ConnCatalog=edgar;ConnSchema=default
username=token
password=dapiXXXXXXXXXXXXXXXX
changeLogFile=changelog/db.changelog-root.yaml
```

Online runs also need the **Databricks JDBC driver** next to the extension
jar: download `DatabricksJDBC42.jar` from
<https://www.databricks.com/spark/jdbc-drivers-download> and put it in
`tools\liquibase\lib\` (Docker route: add a third `-v` mount for it).

### C.6 Apply — order matters

Using the portable CLI from Option 1 (from the repo root, JAVA_HOME set as in §B):

```powershell
# 1. offline sanity
.\tools\liquibase\liquibase.bat --changelog-file=changelog/db.changelog-root.yaml --url=offline:databricks validate

# 2. plan against the real workspace (uses the properties file with your host/PAT)
.\tools\liquibase\liquibase.bat --defaults-file=changelog\liquibase.properties update-sql > tools\workspace-plan.sql

# 3. READ THE PLAN, then apply
.\tools\liquibase\liquibase.bat --defaults-file=changelog\liquibase.properties update
```

Verify in the workspace SQL editor:

```sql
SHOW TABLES IN edgar.bronze;   -- 3 tables
SHOW TABLES IN edgar.silver;   -- 6 (3 + 3 quarantine)
SHOW TABLES IN edgar.gold;     -- 4
SELECT id, dateexecuted FROM edgar.default.DATABASECHANGELOG ORDER BY dateexecuted;
```

### C.7 Databricks CLI (needed from repo 4 onward, set it up once)

```powershell
winget install Databricks.DatabricksCLI
databricks configure --token     # prompts for host + PAT
databricks catalogs list         # smoke test
```

The same host/PAT pair also goes into AWS Secrets Manager as
`/edgar-lakehouse/databricks/pat` when you bootstrap repo 2 (§9.2 of its spec).
