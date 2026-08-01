# MIGRATION — schema and package change policy

## Semver

`edgar_lakehouse_contracts` is semver'd. Downstream repos (2, 3, 4, 5) pin an
exact version (`==`) and never read `main`.

| Bump | When | Downstream action |
|---|---|---|
| PATCH | docstrings, test-only, non-schema fixes | repin at leisure |
| MINOR | additive: new nullable column, new DQ check, new constant, new table | repin when the feature is needed |
| MAJOR | anything that breaks a consumer: rename/drop/retype a column, change nullability to NOT NULL, change a path/name constant, change envelope shape | the rollout below, in order |

## Expand → migrate → contract

Breaking changes ship as three separate releases, never one:

1. **Expand** (MINOR): add the new column/table alongside the old. New Liquibase
   changeset (append-only — never edit a shipped changeset; checksums break
   every downstream environment). Both representations updated in one commit;
   the drift test enforces it.
2. **Migrate**: consumers move to the new shape at their own cadence, each
   repinning and passing its contract-compat check in CI.
3. **Contract** (MAJOR): remove the old column/table once no pinned consumer
   references it. New changeset with explicit rollback.

## Rollout order for a MAJOR bump

```
contracts  →  pipelines  →  ingest  →  serving
   (1)           (4)          (3)         (5)
```

Pipelines first: it is the only writer of silver/gold, so it must understand
the new shape before any producer or reader changes. Ingest next (producer of
landing). Serving last (pure reader). Infra (repo 2) repins whenever the SSM
`contracts/version` parameter should advertise the new version.

## Rules that make this work

- Changelogs are **append-only**; every changeset has an explicit `rollback`.
- The published wheel for every version stays available (S3 `wheels/` prefix +
  GitHub release) — a consumer must always be able to rebuild against its pin.
- Record every published version here:

| Version | Date | Notes |
|---|---|---|
| 0.1.0 | 2026-07-31 | initial contract set (MVP2 schema) |
