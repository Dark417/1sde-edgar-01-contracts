# Ready-to-paste posts

Three platforms, three different sets of norms. Paste as-is; do not merge them.

**Before posting:** attach `architecture.png` (2000x1040, already rendered and
in this folder — LinkedIn and Discord will not render the SVG). Check the repo
link loads while logged out.

---

## LinkedIn

> Plain text — LinkedIn renders `**` as literal asterisks. Hook lives in the
> first two lines; the rest sits behind "see more".

---

I built a schema that disagreed with itself on all eleven fields, and the tests still passed.

That is the failure I want to talk about, because it is the one nobody designs for.

I'm building a data warehouse over SEC filings, split across six repositories. Six codebases have to agree on the exact shape of the data. One writes a field called batch_id, another reads ingest_batch_id, and nothing crashes — the pipeline is built to quietly set unrecognised fields aside, so the tables fill up with empty columns and look completely normal. You find out weeks later when a number is wrong.

My first version had exactly that bug. Eleven fields, zero matches. It was caught before any data loaded, by a test that mechanically compares the two places a schema is written down: the migrations that build the tables, and the code definitions the programs use. The usual advice is to generate one from the other. I kept both by hand and made the build fail if they ever disagree by so much as one column's type.

The lesson went into the project's own docs: a schema is a guess until something real uses it. I had 43 passing tests and 100% coverage while shipping a contract that matched nothing.

Coverage measures which lines ran. It says nothing about whether anyone else agrees with you.

What's the bug your test suite was happiest to let through?

#DataEngineering #Databricks #DataQuality #Python

---

## Reddit — r/dataengineering

> Lead with the lesson, not the project. This community punishes announcements
> and rewards specifics and admitted mistakes.

---

**Title:** 100% test coverage, and my schema still disagreed with its only consumer on all 11 fields

I split a lakehouse project across six repos — contracts, infra, ingest, pipelines, serving, chatbot — with a shared package defining every table shape. Standard stuff: one repo owns the schema, everyone else pins an exact version.

The contracts repo had 43 tests and 100% line coverage. It was also completely wrong.

When I built the first consumer, the landing format it expected and the format the contract defined matched on **zero of eleven field names**. `_batch_id` vs `_ingest_batch_id`, `_schema_version` vs `_envelope_version`, and four provenance fields the contract didn't have at all.

The part that actually scared me: **it would not have failed**. Auto Loader's rescue mode parks unrecognised columns in `_rescued_data` instead of erroring, so bronze would have filled with NULLs and looked healthy. No exception, no alert. I'd have found it downstream when a report was empty.

Two things came out of it.

**One: coverage measures the wrong thing.** Every test I had asserted the package agreed with itself. Not one asserted another repo agreed with me. The test that mattered didn't exist, and coverage can't tell you about a test you never wrote.

**Two: a schema is a hypothesis until a consumer compiles against it.** I froze v0.1.0 before anything used it. The fix wasn't a patch — it was replacing all 13 tables and treating the consumer's shape as the real contract, because that one was exercised by passing tests and mine wasn't.

What I keep now is a drift test: the migrations and the Python/Spark definitions are both maintained by hand, and CI mechanically diffs them on every commit. Not codegen — generation hides drift inside a build step and makes both sides wrong in the same way. The test fails with the table, the column, and both sides named, and there's a separate test asserting the failure message stays that specific.

Then it caught a second one a week later: a rename made two data-quality rules reference columns that no longer existed. Those were checks in SQL strings — invisible to mypy, invisible to coverage.

Repo, if useful: https://github.com/Dark417/1sde-edgar-01-contracts

Runs on Databricks Free Edition, so it's a portfolio project rather than anything production. Curious whether people doing multi-repo contracts enforce agreement in CI, or just review carefully and hope.

---

## Discord

> Short, link-forward, one hook.

---

Spent the week on a schema-contract repo for a 6-repo lakehouse and got humbled: 43 passing tests, 100% coverage, and the contract disagreed with its only consumer on **all 11 field names**. Wouldn't have crashed either — the ingest layer quietly parks unknown fields aside, so the tables would've filled with NULLs and looked fine.

Fix was a drift test that diffs the SQL migrations against the Python schema definitions on every commit and fails naming the exact column.

Takeaway I keep coming back to: coverage tells you which lines ran, not whether anyone else agrees with you.

https://github.com/Dark417/1sde-edgar-01-contracts
