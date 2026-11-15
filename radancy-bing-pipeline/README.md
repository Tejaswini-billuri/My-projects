# Bing Ads → Warehouse pipeline

An Apache Airflow 3 pipeline that loads Bing Ads performance exports (`BING_MultiDays.csv`)
into a Postgres star schema, built for the Radancy Senior Data Engineer coding challenge.

```
extract ─▶ validate ─▶ transform ─▶ load_dims ─▶ load_fact ─▶ post_load_checks
                                    ├ dim_date                    (reconcile + audit)
                                    ├ dim_delivery
                                    └ dim_account ▶ dim_campaign ▶ dim_ad_group ▶ dim_ad
```

## Quick start

Three ways to run it, from quickest to most complete.

**1. In-process, no Airflow** (≈10 s — the same functions the DAG calls, run sequentially):

```bash
brew services start postgresql@17      # or any Postgres you have; see BING_DWH_URL below
make install                           # uv sync (needs https://docs.astral.sh/uv/)
make db-init                           # creates role bing/bing + database bing_dwh
make run                               # extract → ... → post_load_checks
psql postgresql://bing:bing@localhost:5432/bing_dwh -c "select * from bing.vw_campaign_daily limit 5"
```

**2. Airflow locally** (standalone mode, UI on http://localhost:8080, no login):

```bash
make airflow                           # then trigger `bing_ads_daily` from the UI
make dags-test                         # or: run the DAG once headlessly via `airflow dags test`
```

**3. Docker** (Postgres + Airflow, nothing else needed on the host):

```bash
docker compose up --build              # UI on :8080, warehouse on localhost:5433
```

Unit tests (no database needed): `make test`.

Configuration is via three environment variables, all with local defaults
(`src/bing_pipeline/config.py`): `BING_DWH_URL`, `BING_SOURCE_FILE`, `BING_WORK_DIR`.

## Repository layout

```
dags/bing_ads_daily.py          the DAG — orchestration only, no business logic
src/bing_pipeline/
  schema.py                     source contract: expected columns, grain, metric lists
  extract.py                    CSV → untouched parquet snapshot
  validate.py                   hard rules (raise) + soft rules (flag), typed output
  transform.py                  cleaning + one builder per dim/fact
  load.py                       stage with pandas, merge with sql/upserts/*.sql
  checks.py                     source-vs-warehouse reconciliation, run audit row
  pipeline.py                   run everything in-process (dev loop / integration test)
sql/ddl/                        001 star schema, 002 views, 003 column comments,
                                004 metric glossary — all idempotent, re-applied every run
sql/upserts/                    one INSERT … ON CONFLICT per table
tests/                          pytest, synthetic rows (see conftest.py)
data/BING_MultiDays.csv         the source file (12,497 rows, 7 days, 2026-01-11..17)
```

## Schema design

**Fact grain** — one row per *(date, ad, delivery context)*. The source has no row-level ID, so
the grain was established empirically (zero duplicates across all 12,497 rows on these columns)
and is now enforced as a hard validation rule, so a future export that breaks it fails loudly
rather than double-counting.

**Delivery context is a junk dimension** (`dim_delivery`). Device type, device OS, network,
Top/Other position bucket, both match types, distribution and language are all low-cardinality
(182 distinct combinations in this file). Folding them into one dimension keeps the fact table
at three foreign keys instead of ten text columns, and makes "by device × network" slices a
single join.

**Hierarchy** — `dim_account → dim_campaign → dim_ad_group → dim_ad`, snowflaked rather than
flattened so each level has its own natural key and status, and so an ad group that moves
between campaigns is a one-row update. Notes on the natural keys:

- Customer is folded into `dim_account` (3 customers, 9 accounts — not worth a table yet).
- Campaign has **no ID** in the export; its key is `(account, campaign_name)`. Names such as
  "Brand" and "Store" repeat across accounts, which is why the account is part of the key.
- Ad group and ad IDs arrive as `[2709719083]`; the brackets are stripped and the IDs stored
  as `BIGINT` (some are 16 digits).

**Dimensions are SCD type 1** — the latest load (and within a file, the latest date) wins.
Nothing in this dataset changes within the week, and type 2 history wasn't asked for; the
`updated_at` column is there so it can be added later without a migration.

The one attribute where point-in-time matters is **campaign status** ("Budget paused" is itself
a finding), so the fact table carries `campaign_status` *as reported on that day* alongside the
dim's current value. `vw_ad_performance_daily` exposes both (`campaign_status` = current,
`campaign_status_on_date` = that day), and the campaign rollup groups by the as-of-day value.
This answers "how much did we spend while paused?" without SCD2 machinery — in this file,
Fidelity's Brand campaign spent $276.72 across 650 rows while "Budget paused".

**Views for analytics / Insights Agents** (`sql/ddl/002_views.sql`):

| view | purpose |
|---|---|
| `bing.vw_ad_performance_daily` | fully denormalised fact with CTR / CPC / CVR / cost-per-conversion precomputed (NULL, not 0, when the denominator is 0) |
| `bing.vw_campaign_daily` | campaign × day rollup with impression-weighted average position |
| `bing.vw_dq_exceptions` | rows carrying a data-quality flag |

The ratio definitions live in one place so every consumer — dashboards or an agent writing SQL —
gets the same numbers.

**Self-describing for agents.** An LLM writing SQL discovers the schema through the catalogue,
not this README, so the documentation lives there too:

- `sql/ddl/003_comments.sql` — `COMMENT ON` for every dim and fact column, in business
  language (what `assists` means, that `avg_position` must be impression-weighted, that
  `campaign_status` is current-state not as-of-day). Postgres doesn't propagate comments to
  views, so a `DO` block at the end copies each view column's description from the base column
  of the same name; only derived columns (`ctr`, `cpc`, `has_dq_flag`…) are commented on the
  view directly. One source of truth, visible via `\d+`, `information_schema` /
  `col_description()`, and any schema-introspection tool.
- `bing.metric_definitions` (`004_metric_definitions.sql`) — a queryable glossary: meaning,
  SQL expression, how to aggregate (`sum` / `ratio_of_sums` / `weighted_avg`), and caveats
  for each metric. Seeded idempotently from the repo so it stays versioned.

```sql
select metric_name, sql_expression, caveats from bing.metric_definitions where metric_name = 'ctr';
select col_description('bing.vw_ad_performance_daily'::regclass, ordinal_position), column_name
  from information_schema.columns where table_name = 'vw_ad_performance_daily';
```

## Data quality: what the file actually contains

Profiling the export before modelling it turned up the following, each handled explicitly:

| finding | handling |
|---|---|
| 11 rows with **clicks > impressions** | Known Bing reporting lag. Loaded, flagged `CLICKS_GT_IMPRESSIONS`. |
| 1 row with a **conversion but 0 clicks** | Loaded, flagged `CONVERSIONS_GT_CLICKS`. |
| 1 row with **blank Avg. position** (0 impressions) | Nullable; only flagged when impressions > 0. |
| `Ad title` blank for every *Expanded text ad* (7,109 rows) | Nullable; the title lives elsewhere for that ad type. |
| `Final URL` vs `Destination URL` are mutually exclusive | Coalesced into `landing_url`; both raw columns kept. |
| `Top vs. other` = `Network + " - Top/Other"` | Split into `position_bucket`; the network half is already its own column. |
| `Custom Parameters`, `Final Mobile URL`, `Final App URL` 100 % empty; 6 columns single-valued | Kept in the contract (must be present) but not modelled. |
| UTF-8 BOM on the header; en-dash in one account name | `utf-8-sig`; text columns are `TEXT`. |

Soft rules **flag rather than drop**: dropping rows would make warehouse totals disagree with
the Bing UI, which is a worse outcome than a flagged anomaly. Hard rules (column contract,
unparsable dates/numbers, empty keys, duplicate grain, negative metrics) stop the run.

## Pipeline architecture

- **Tasks exchange file paths, not DataFrames.** Each step writes parquet to
  `work/<run_id>/` and passes the path through XCom, so any task can be re-run alone and the
  intermediate data is inspectable.
- **The DAG contains no logic.** Every task is a one-line call into `bing_pipeline`, which has
  no Airflow imports. The same functions are run by `pipeline.py` (no scheduler) and by the
  unit tests. This is also why the warehouse connection is a plain `BING_DWH_URL` env var
  rather than an Airflow Connection / `PostgresHook`: the package must work without Airflow.
  In a shared deployment the DAG would read the URL from a Connection and pass it in.
- **Loads are set-based SQL.** Each table is staged with `to_sql` and merged with an
  `INSERT … ON CONFLICT` in `sql/upserts/`. Surrogate keys are resolved by joining on natural
  keys inside the statement; the fact load fails if any staged row lost its dimension.
- **Idempotent.** Re-running for the same file upserts on natural keys / fact grain — a no-op
  apart from `loaded_at`. Re-running for a corrected export overwrites the affected days.
- **Verified at the end.** `post_load_checks` reconciles row counts and metric totals per day
  between the validated frame and the fact table, then writes a `bing.pipeline_run` audit row
  with the DQ flag counts.

## Verified

All three run paths were executed on a clean state (macOS, Colima/Docker 29, Postgres 16/17):

```
rows:   dim_date 7 · dim_account 9 · dim_campaign 54 · dim_ad_group 234 · dim_ad 484
        dim_delivery 182 · fact_ad_performance_daily 12,497
totals: 63,997 impressions · 2,149 clicks · $1,853.16 spend · 8 conversions  (match source)
dq:     CLICKS_GT_IMPRESSIONS 11 · CONVERSIONS_GT_CLICKS 1
tests:  11 passed
docker: `docker compose up --build` → DAG triggered → 12 tasks green in 11 s → warehouse reconciled
```

Re-running any path is idempotent: the fact row count stays at 12,497.

## What I'd do next (deliberately out of MVP scope)

- Land files in object storage and trigger the DAG with a sensor / dataset event instead of a
  manual param; partition `work/` by file hash so re-deliveries are detected.
- A `COPY`-based loader for volumes where `to_sql` becomes the bottleneck.
- Promote the soft-rule thresholds to a config table so analysts can tune them.
- SCD2 on `dim_campaign` / `dim_ad` status once history matters; `dim_customer` once there
  are enough customers to make it a real dimension.
- Great Expectations / dbt tests on the views, and a CI job running `make test` + `make dags-check`.

## Tooling note

Built with Claude Code as a pair: profiling the CSV, drafting the schema and SQL, and iterating
on the pandas-3 / SQLAlchemy-2 / Airflow-3 version matrix. Design decisions are mine.
