# ADR-002 — Two schema representations, reconciled by a drift test

**Status: ACCEPTED** (2026-07-31)

## Context

The lakehouse schema exists in two forms:

1. **Liquibase changelogs** (`changelog/*.yaml`) — the DDL that *creates* every
   bronze/silver/gold Delta table, applied via the `liquibase-databricks`
   extension over JDBC. Liquibase gives us migration history
   (`DATABASECHANGELOG`), checksummed append-only changesets, and explicit
   rollbacks.
2. **Python/Spark schema objects** (`spark/schemas.py`) — the `StructType`s
   that repo 4's Spark code compiles against, and the column vocabulary repos
   3 and 5 validate against via the contracts package.

Two representations of the same fact will drift. The question is what to do
about it.

## Options considered

**A. Generate one from the other (codegen).** Rejected. Generation couples the
release cycle of five repos to one codegen step: a changelog edit would force a
package regeneration, republish, and re-pin across every consumer even for
changes that do not affect them. Worse, it *hides* drift inside a build — when
the generator has a bug (type-mapping subtlety, nullability default), both
representations are wrong in the same way and nothing notices. The generator
itself becomes a third schema representation to maintain.

**B. Single representation, runtime reflection.** Have code read table schemas
from the workspace at runtime. Rejected: repos 3 and 5 must work with no
Databricks connectivity at all (design doc §5.4), and it makes CI depend on a
live workspace.

**C. Two hand-maintained representations + a mechanical drift test.** Chosen.
`tests/test_schema_drift.py` parses the changelog YAML, builds the implied
`{table: {column: (type, nullable)}}` map, and diffs it against the
`StructType`s — identical column sets, identical normalized types
(`STRING`≡`StringType`, `DECIMAL(38,6)`≡`DecimalType(38,6)`), identical
nullability. Any mismatch fails CI naming the table, the column, and both
sides.

## Decision

Both representations are maintained by hand. The drift test is the contract
between them and runs on every push and PR. A deliberate schema change
therefore touches both files in the same commit, which is exactly the review
signal we want.

## Consequences

- Schema changes are slightly more work (two edits) — accepted cost.
- The drift test is the single reason this repo is trustworthy; it must fail
  loudly and is verified by a fixture with a deliberately broken column type.
- Liquibase snapshot/diff features may be unavailable on Free Edition if
  `system.information_schema` is restricted (runbook §9.4 probe). `update` and
  `rollback` use `DATABASECHANGELOG` and keep working either way; CI is built
  on `liquibase validate` only and never on `liquibase diff`.
