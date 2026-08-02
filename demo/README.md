# What this is, in plain language

![Architecture](architecture.svg)

## The problem

Public companies file their financial results with the SEC. Sometimes they file
them again — a correction, months later, quietly restating a number they already
published.

Most systems that store this data overwrite the old number with the new one. The
correction disappears. Ask "what did this company originally report, and when did
they change it?" and the data cannot answer, because it only remembers the latest
version of the truth.

This project builds a data warehouse that **remembers both** — so a restatement
becomes something you can search for, rather than something you notice by
accident.

## Why that is harder than it sounds

Six separate codebases have to agree on the exact shape of the data: what a
"filing" contains, what a "financial fact" is, which fields are required. If any
two of them disagree — one writes a field called `batch_id` and another reads
`ingest_batch_id` — the data silently arrives empty. Nothing crashes. You find
out weeks later, when a report is wrong.

**That is what this repository prevents.** It is the shared rulebook the other
five follow.

## The idea worth explaining

A database schema normally lives in two places, and they drift apart:

- **The migrations** — instructions that build the tables in the warehouse.
- **The code definitions** — what the programs expect those tables to look like.

They describe the same thing, so they should always match. In practice someone
edits one and forgets the other, and nobody notices until production breaks.

The usual fix is to generate one from the other. This project does the opposite:
it keeps both written by hand, and adds **a test that mechanically compares them
on every single change**. If they disagree by so much as one column's type, the
build stops and tells you exactly which column, in which table, and what each
side thinks it should be.

That test is the reason this repository exists. Everything else is bookkeeping.

## Did it actually catch anything?

Yes — twice, and that is the honest part of the story.

The first version of the schema was written before any program used it. When the
first consumer was built, the two disagreed on **all eleven** fields of the data
format. Not one name matched. Worse, it would not have crashed: the system was
designed to quietly park unrecognised fields aside, so the tables would have
filled up with empty columns and looked fine.

The checks caught it before any data was loaded. The lesson got written into the
project's own documentation: *a schema is a guess until something real uses it.*

## What is in here

| | |
|---|---|
| **13 tables** | across raw, cleaned, and report-ready layers |
| **199 columns** | every one with a defined type and whether it can be empty |
| **43 migrations** | applied to a live warehouse, each reversible |
| **17 data-quality rules** | each naming the specific failure it prevents |
| **61 automated tests** | including the drift check and its own proof that it works |
| **3 released versions** | each one installable and pinned by the repos that use it |

## Releasing it

Publishing a new version is a single action, and it does two things in a fixed
order: first it updates the warehouse tables, then it publishes the code package.
Never the other way round — otherwise a program could install a version that
expects tables which do not exist yet.

## Honest limits

- It runs on a **free tier** of Databricks, which is not licensed for commercial
  use. This is a portfolio project, not a product.
- It covers a few hundred companies and fifteen financial measures, not the whole
  market.
- Data refreshes once a day, so a correction filed this morning shows up
  tomorrow.
- The "how serious is this restatement" rating is a **rule of thumb chosen for
  this project**, not an accounting standard, and it is labelled that way
  everywhere it appears.

## Want more detail?

- [walkthrough.md](walkthrough.md) — see the checks actually run
- [`../docs/`](../docs/) — the engineering design documents and decision records
