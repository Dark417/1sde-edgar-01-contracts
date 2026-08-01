# ADR-003 — Catalog topology: one catalog with layer schemas, not catalog-per-layer

**Status: ACCEPTED** (2026-08-01)

## Context

Two common Unity Catalog topologies for a medallion lakehouse:

**A. Catalog-per-layer (enterprise pattern).** Catalogs like
`{app}_ctg_{domain}_bronze_dev` / `…_silver_dev` / `…_gold_dev`; schemas inside
are *business domains* (`entity_reference`, `instrument`, `presentation`), not
layers. The catalog axis carries layer + environment.

**B. One catalog per project/env with layer schemas (this project).**
`fin.bronze`, `fin.silver`, `fin.gold`; environment separation by catalog
prefix if ever needed.

## Why enterprises pick A

The catalog is UC's strongest boundary; four controls attach at exactly that
level:

1. **Grants at scale** — `GRANT USE CATALOG gold TO analysts` exposes all of
   gold and none of bronze in one statement.
2. **Managed storage location per catalog** — bronze and gold bytes in
   different buckets, different retention/cost policy.
3. **Workspace–catalog binding** — bronze bound only to engineering
   workspaces; BI workspaces cannot see it at all.
4. **Environment separation** — one metastore per region is shared across
   envs, so `_dev`/`_qa`/`_prod` live in the catalog name and promotion is
   catalog-to-catalog.

## Why this project picks B

Every benefit of A requires capabilities Databricks Free Edition does not
provide: there is **one workspace** (nothing to bind), **no user groups or
second personas** (no differential grants), **managed storage only** (no
per-catalog buckets), and **one environment**. Catalog-per-layer here would
triple the Terraform and Liquibase object count and deliver none of the four
controls.

## Decision

One catalog `fin`, schemas `landing`/`bronze`/`silver`/`gold`. Documented as a
demo-scale decision, not a general recommendation.

## Switch point

Adopt A when any of these become true: multiple consumer personas needing
different access, per-layer storage/retention requirements, more than one
workspace, or a real dev→prod promotion path. The contracts package isolates
the blast radius of such a move: `names.py` constants and the changelog
`catalogName`/`schemaName` fields are the only places the topology is spelled,
and every downstream repo resolves names through them.
