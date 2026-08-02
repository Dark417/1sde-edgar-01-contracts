# Project notes — edgar-lakehouse build log (compacted)

> Running digest of problems hit, trade-offs taken, and decisions still open.
> Sessions: 2026-07-31 → 2026-08-01. Interview prep target: ~week of 2026-08-03.

## Where things stand

| Repo | State |
|---|---|
| 01-contracts | **DONE & RELEASED: v0.1.0**, wheel on the GitHub release (public repo = the registry stand-in; S3 plan dropped). Release-on-tag pipeline: build -> liquibase update (CI, idempotent) -> publish. Only ADR-001 probe remains (needs raw bucket). |
| 02-infra | Terraform on `main` (`d53aad5`), not yet applied. Needs §9 hand bootstrap: state bucket, 2 secrets, budget alarm → `plan`/`apply` → `imports.tf` adopts hand-created catalog. |
| 03-ingest / 04-pipelines / 05-serving | AGENTS.md specs only; not generated. |
| Databricks | Catalog `edgar` + 4 schemas + volume + 13 tables, Liquibase 14/14 changesets, idempotency verified. `fin` dropped. Host `<DBX_WORKSPACE_ID>`, warehouse `<WAREHOUSE_ID>`. |
| AWS | Dedicated account `<AWS_ACCOUNT_ID>`, profile `edgar`, us-east-2. **Nothing bootstrapped.** |

## Key decisions made (and the trade-off behind each)

1. **Two schema representations + mechanical drift test** (changelogs vs StructTypes), not codegen — codegen couples five repos' release cycles and hides drift inside a build (ADR-002). Cost: schema changes touch two files; that's the desired review signal.
2. **One `edgar` catalog with layer schemas**, not the enterprise catalog-per-layer topology the user's real team runs (`{app}_ctg_{domain}_{layer}_{env}`). Free Edition has one workspace/no groups/no per-catalog storage, so catalog-per-layer buys nothing here. Switch point documented in ADR-003 — interview material.
3. **Full rename fin → edgar (2026-08-01)** — repos (`1sde-edgar-*`), package (`edgar_lakehouse_contracts`), catalog, buckets (`edgar-lake-raw/-serving`), SSM (`/edgar-lakehouse/*`). Done pre-publish so nothing downstream ever pins the old name. Old `fin` catalog verified empty, dropped.
4. **Secrets: AWS Secrets Manager, hand-created** (`/edgar-lakehouse/databricks/pat`, `/edgar-lakehouse/sec/user-agent`); Terraform reads via `data` only (a `secret_version` resource writes plaintext to state). Config vs secrets split: SSM Parameter Store for names/hosts, Secrets Manager for the two real secrets.
5. **PATs have no scopes** — token is full-privilege-as-user; mitigations are lifetime (90d) + rotation. Current PAT was pasted in chat → **rotate when creating the AWS secret**.
6. **Portable toolchain over installs**: `tools/` holds Temurin 17 JRE + Liquibase 5.0.3 + databricks extension + Simba JDBC 2.7.3 (gitignored, no admin). Docker was rejected in practice — Desktop engine wouldn't start. Also unblocked local `pytest -m spark`.
7. **Local "Databricks alternative"** = three substitutes, no emulator: local Spark+delta-spark (repo 4 tests), Liquibase `offline:databricks` (plan-only), DuckDB over Parquet (repo 5's whole design).
8. **`/liquibase` skill** (`.claude/skills/liquibase/`) wraps validate/plan/update/status/history; rule: never `update` without a shown `plan`.

## Problems hit → fixes (gotcha list)

- **Authoritative docs didn't exist** (`00-design-doc.md`, `02-data-contracts.md` cited by all five specs) → authored them in repo 1, including the 15-concept set and all 17 DQ checks; other repos copy from repo 1.
- **`pip --find-links s3://…` doesn't work** (pip can't read s3) → `aws s3 cp` first; specs fixed.
- **YAML flow-map comma**: `{type: DECIMAL(38,6)}` splits at the comma → quote it: `type: "DECIMAL(38,6)"`.
- **Grep gate self-trip**: CI failed because a changelog *comment* contained the word `createIndex` → reword comments; repo 2's gates are comment-aware (`grep -v '#'`), the better pattern.
- **PowerShell `>` writes UTF-16** → grep on redirected output silently finds nothing; use `Select-String` or re-encode.
- **Windows dir renames blocked** by another session's open handles → workaround: `mkdir` new + move contents + rmdir old.
- **Liquibase offline mode drops `databasechangelog.csv`** in cwd → gitignore it.
- **Concurrent-session race**: a second Claude session generated repo 2 into the *old* dir name mid-rename, splitting output across two dirs; its Terraform initially said `fin`. Consolidated (by that session) + renamed. **Rule going forward: one session per repo.**

## Decisions still open / next actions (in order)

1. **AWS §9.1 bootstrap** (human or either session, profile `edgar`): tfstate bucket `edgar-lakehouse-tfstate-<AWS_ACCOUNT_ID>` + DynamoDB lock, the two secrets (with a **fresh, rotated PAT**), $10 budget alarm.
2. **Repo 2 `terraform plan` → hand-check → `apply`**, with `imports.tf` adopting the hand-created catalog/schemas/volume. Verify: schedule DISABLED, zero destroys, no plaintext secrets in plan.
3. ~~Publish wheel~~ DONE: CONTRACTS_VERSION=0.1.0, install URL: https://github.com/Dark417/1sde-edgar-01-contracts/releases/download/v0.1.0/edgar_lakehouse_contracts-0.1.0-py3-none-any.whl . Still open: run the ADR-001 probe (`dbutils.fs.ls("s3://edgar-lake-raw/")`) and fill the ADR (`s3` vs `volume`; default stays `volume` until probed).
4. **Generate repo 3 (ingest)** — needs a hand-collected `.idx` fixture (spec §9.3) and the SEC user-agent secret.
5. **Bucket-name reality check**: `edgar-lake-raw`/`-serving` are global-namespace S3 names and may be taken → repo 2 may suffix with the account id; contracts is immune (bucket is a parameter, constants are defaults).
6. **Scale question for the interview**: stay on the 500-CIK REST fan-out; answer scaling verbally (XBRL `frames` ≈ 6k filers/request; DERA bulk ZIPs ≈ 300M facts) — same contracts either way.
7. Weekly ops once live: click the demo link, check `_manifest.json` freshness; rotate PAT every 90 days.

- **Release process (2026-08-02):** one env, so tag = release button. Merge to main only validates; `v*` tag runs build -> `liquibase update` -> wheel to GitHub release, in that order (DDL lands before the version is installable). Gotchas hit: liquibase GH action lacks the Simba JDBC driver (install CLI+jars directly); Git Bash mangles leading-slash secrets (`MSYS_NO_PATHCONV=1 gh secret set ...`). Repo 4 must now swap its vendored contracts copy for the ==0.1.0 pin.
