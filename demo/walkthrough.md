# Walkthrough — seeing it work

Nothing here needs a Databricks account. Steps 1–3 run on any laptop with Python.

## 1. The check that justifies the repo

Set up and run the tests:

```bash
pip install -e ".[dev]"
pytest -m "not spark"
```

61 tests pass. The interesting one is `test_schema_drift.py`, which reads the
migration files, works out what tables they would build, and compares that
against what the code says those tables look like.

## 2. Break something on purpose

Change one column's type in a migration file — say `filed_date` from a date to
text — and run the test again. It fails with:

```
edgar.silver.filing.filed_date: type drift — changelog='string' vs StructType='date'
```

**The table, the column, and both sides.** That precision is deliberate: a
failure that only says "schemas differ" gives you a schema of 199 columns and no
starting point. The repo has a permanent test asserting the message names the
column, so the error can never quietly degrade into something vague.

## 3. The rule every data-quality check must follow

Each of the 17 quality rules has to state, in writing, the specific failure it
prevents — and a test enforces that the statement is at least twenty characters:

```python
DQCheck(
    name="fact_period_order",
    severity="reject",
    expression="period_start IS NULL OR period_end >= period_start",
    prevents="Negative-length duration periods poisoning period-scoped "
    "comparisons (instant facts pass by design)",
)
```

The point is not the character count. It is that a check whose author cannot name
what it protects against is usually cargo-culted, and should be deleted rather
than documented. A second test confirms every rule references a column that
actually exists — added after a rename made two rules silently invalid.

## 4. What the release does

Pushing a version tag runs the checks, updates the warehouse tables, and then
publishes the code package — in that order, so no program can ever install a
version whose tables have not been created yet.

You can see the result without any credentials:

```bash
pip install https://github.com/Dark417/1sde-edgar-01-contracts/releases/download/v1.2.0/edgar_lakehouse_contracts-1.2.0-py3-none-any.whl
```

```python
from edgar_lakehouse_contracts import names
from datetime import date

names.batch_id("filing_index", date(2026, 7, 29))
# 'filing_index-20260729-eb4807cfccc9'
```

That identifier is worth a second look: it is derived only from *what* is being
loaded and *which day it belongs to* — never from the current time. Run the same
load twice and you get the same name, so the second run overwrites the first
instead of silently creating a duplicate copy of the day's data.

## 5. What you cannot see here

- **The live warehouse** — 43 migrations applied, but it is a private free-tier
  workspace with no public endpoint.
- **The end-to-end demo** — the public site is a later repository in the project
  and is not deployed yet.
- **Performance numbers** — this repository defines shapes and runs tests; it
  processes no data itself.
