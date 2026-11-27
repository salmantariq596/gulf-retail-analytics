# Snowflake cost note

Trial budget: $400 of credits / 30 days. Guardrails: X-Small warehouses only, 60-second auto-suspend, and a resource monitor (`najm_trial_monitor`, 120 credits) that suspends at 75%.

Measured 2026-11-27/28 on the full 3-year dataset: 14M POS sales, 23.8M sales lines, 2.7M online orders, 41.6M daily stock rows.

| Run | Warehouse | Duration | Credits | Notes |
|---|---|---|---|---|
| Full 3-year load (dlt) | LOAD_WH | 71 min | 0.59 | Most of the time is extraction on the laptop; the warehouse only runs while dlt copies staged files |
| Full build `dbt build --full-refresh` | TRANSFORM_WH | 5.5 min | ≈ 0.2 | 354 nodes, PASS=348 WARN=3. Slowest: `fct_inventory_daily` 137 s, `fct_sales_lines` 93 s, `fct_returns` 78 s |
| One incremental day (dlt + dbt) | LOAD_WH + TRANSFORM_WH | 2.8 + 5.1 min | ≈ 0.07 + 0.10 | Load reads only new rows (32k sales lines); facts rewrite their 3-day window only (see below) |
| Slim CI run (Phase 7) | TRANSFORM_WH | 1–2 min | < 0.05 | `state:modified+`, incremental facts read 30 days |

Credits come from `information_schema.warehouse_metering_history`. A run's share of an hour is estimated from billed minutes, where an X-Small costs 1 credit per hour, with a 60-second minimum on every resume.

**Whole project so far:** 1.83 credits, about 1.5% of the monitor quota, at the end of the full load (2026-11-28).

**Projected monthly cost of running this daily:** about 0.17 credits a day × 30 = **about 5 credits a month**. At Enterprise list prices of roughly $3 per credit, that is about **$15 a month**, plus storage (about 3 GB compressed).

## Clustering `fct_sales_lines`

The table is clustered on `business_date` (`cluster_by` in the model). The test query was
one month of net revenue by country, with the result cache off:

| Table | Partitions scanned | Data scanned | Time |
|---|---|---|---|
| `fct_sales_lines` (clustered) | 3 of 68 | 2.8 MB | 0.23 s |
| Same rows, unclustered copy | 85 of 85 | 115 MB | 0.66 s |

Clustering cuts the data scanned by about 40× for date-filtered dashboards. Clustering depth
is 2.0. The table is built in date order and the incremental runs append in date order, so
automatic reclustering has almost nothing to do.

## Incremental runs: what was rewritten

| Model | Rows rewritten | Time | Full-refresh rows / time |
|---|---|---|---|
| `fct_sales_lines` | 164k (3-day window + new day) | 42 s | 23.9M / 93 s |
| `fct_online_orders` | 27k | 13 s | 2.7M / 13 s |
| `fct_inventory_daily` | 198k (5 days × 39.6k) | **110 s** | 41.6M / 137 s |

**Tuning opportunity:** `fct_inventory_daily` rewrites only 5 days, but it costs almost as
much as a full build. It reads `int_inventory_daily_filled`, a view that builds the full
store × SKU × day grid and carries stock forward with a window over the whole history.
Snowflake cannot push the 3-day filter below that window. The fix is to limit the stock rows
read on incremental runs to a short carry-forward margin, for example the cutoff minus 14 days.
That would take the model from about 110 s to a few seconds. It is worth about 0.03 credits a
day, so it is noted here rather than changed.
