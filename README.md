# Gulf Retail Analytics Warehouse

[![CI](https://github.com/salmantariq596/gulf-retail-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/salmantariq596/gulf-retail-analytics/actions/workflows/ci.yml)
[![Deploy](https://github.com/salmantariq596/gulf-retail-analytics/actions/workflows/deploy.yml/badge.svg)](https://github.com/salmantariq596/gulf-retail-analytics/actions/workflows/deploy.yml)
[![dbt docs](https://img.shields.io/badge/dbt_docs-live-FF694B?logo=dbt&logoColor=white)](https://salmantariq596.github.io/gulf-retail-analytics/)

A dbt project that models **Najm Retail**, a fictional electronics and home goods chain with 25 stores across the UAE, Saudi Arabia and Qatar plus an online store. The model is a tested Kimball star schema with SCD Type 2 history and a MetricFlow semantic layer. It is developed on DuckDB and deployed to Snowflake.

> **Business question:** Which stores, products and channels make money after returns and discounts, how much stock are we holding, and which marketing spend brings customers who come back?

**Users:** CFO (revenue, margin), Merchandising (stock, sell-through), Marketing (ROAS, retention), CEO (one-page overview). See [docs/requirements.md](docs/requirements.md).

## Architecture

```
POS (Postgres) ─┐
Online API ─────┤                 ┌── staging ──► intermediate ──► marts (star schema) ──► MetricFlow ──► Lightdash
Inventory CSV ──┼── dlt ──► raw ──┤
Catalog CSV ────┤                 └── snapshots (SCD2) ─────────────────┘
Marketing CSV ──┘          DuckDB (dev) · Snowflake (prod) · orchestrated by Dagster · CI on GitHub Actions
```

## Design docs (Phase 0)

| Doc | What it covers |
|---|---|
| [Requirements](docs/requirements.md) | Stakeholder questions mapped to metrics and facts |
| [Business definitions](docs/business_definitions.md) | Net revenue, margin, ROAS, etc., agreed before any SQL |
| [Bus matrix](docs/bus_matrix.md) | Facts × conformed dimensions, plus the grain of every fact |
| [Source systems](docs/source_systems.md) | The five sources and the problems each one injects |
| [Data model](docs/data_model.md) | Lineage and the star-schema ERD |
| [dbt v2 comparison](docs/dbt_v2_comparison.md) | dbt 1.11 vs the Rust dbt v2 engine on this project: 7× faster parse, same build time, identical output |

## Progress

- [x] **Phase 0** — Requirements, bus matrix, definitions, model diagram, repo + Docker Compose
- [x] **Phase 1** — Data generator + FastAPI mock + dlt ingestion into DuckDB
- [x] **Phase 2** — dbt setup, sources, seeds, staging, SQLFluff *(17 staging models, 8 seeds, 137 tests, 13 freshness checks)*
- [x] **Phase 3** — Snapshots, intermediate models, dimensions with contracts *(2 snapshots, 8 intermediate models, 7 contracted dimensions)*
- [x] **Phase 4** — Fact tables, incremental models, 100+ tests *(5 facts + 1 report, 275 data tests + 4 unit tests)*
- [x] **Phase 5** — Snowflake: RBAC, warehouses, prod build *(3 years, ~115M raw rows loaded in 71 min; full prod build 5.5 min ≈ 0.2 credits; daily run ≈ 0.17 credits. See [docs/cost.md](docs/cost.md))*
- [ ] **Phase 6** — MetricFlow metrics, Lightdash dashboards, Dagster *(25 metrics, 4 generated metric tables, 3 dashboards as code, exposures, Dagster daily job)*
- [ ] **Phase 7** — CI/CD, docs site, launch *(PR checks, slim CI, deploy + docs site; launch pending)*

## Run locally

```bash
cp .env.example .env
python -m venv .venv && .venv/Scripts/activate      # Windows (use bin/activate on Linux/macOS)
pip install -r requirements.txt && pip install -e .
docker compose up -d                                 # Postgres (POS schema auto-created) + mock API on :8000

# 1. Generate ~3 months of messy source data (~7 min): POS -> Postgres, online -> API, rest -> CSV
najm-gen backfill --profile dev

# 2. Load everything into DuckDB raw schemas (raw_pos, raw_online, raw_erp, raw_catalog, raw_marketing)
najm-ingest all

# 3. Daily mode: simulate the next day, then load only what changed
najm-gen run --days 1 && najm-ingest all

# 4. Transform and test with dbt (DuckDB)
cd dbt && dbt deps && dbt source freshness && dbt build
```

## Orchestration (Dagster)

One asset graph runs from the source systems to the governed metrics
([orchestration/najm_orchestration/definitions.py](orchestration/najm_orchestration/definitions.py)):

```
source_systems_day ─► pos/* online/* erp/* catalog/* marketing/*  (dlt, one asset per raw table)
                   ─► dbt seeds, snapshots, staging ─► intermediate ─► marts  (286 tests as asset checks)
                   ─► metricflow_reconciliation  (Lightdash metrics == mf query)
```

- **Lineage:** dlt tables are keyed like the dbt sources (`pos/sales`), so lineage is unbroken from Postgres, the API and the files through to the dashboards' tables.
- **Freshness gate:** `dbt source freshness` runs before `dbt build`, so stale raw data stops the run instead of publishing old numbers.
- **Schedule:** the `daily_refresh` job runs at 06:00 Asia/Dubai. The schedule ships switched off; turn it on in the UI.

```powershell
$env:DAGSTER_HOME = "$PWD\data\dagster_home"
dagster dev                                   # UI on http://localhost:3000
dagster job execute -m najm_orchestration.definitions -j daily_refresh
# against Snowflake: $env:DBT_TARGET = "prod"; $env:NAJM_WAREHOUSE = "snowflake"
```

## Metrics and dashboards

MetricFlow (`dbt/models/semantic/`) is the single definition of every metric. Open-source
Lightdash cannot query MetricFlow, so the BI layer is **generated** from it and **proved equal** to it:

```powershell
python scripts/semantic_export.py      # MetricFlow YAML -> mtr_* tables + Lightdash metrics + docs/metrics_catalog.md
cd dbt; dbt build -s path:models/marts/metrics; cd ..
python scripts/reconcile_metrics.py    # every exported metric vs `mf query`, month by month

.\bi\lightdash\up.ps1                  # Lightdash on http://localhost:8080 (login in bi/lightdash/.env)
.\bi\lightdash\deploy.ps1              # publish the marts and metrics (reads Snowflake PROD as lightdash_user)
.\bi\lightdash\publish.ps1             # dashboards as code: bi/lightdash/dashboards.py -> content/*.yml -> Lightdash
```

24 of 25 metrics are available in Lightdash. Month-end stock is exported per month only,
and averages are stored as sum and count. Active customers (a rolling 90 days) stays
MetricFlow-only; [docs/metrics_catalog.md](docs/metrics_catalog.md) lists where each metric is served.
A pre-commit hook fails if the generated files drift from the MetricFlow definitions.

## Fact tables

| Fact | Type | Grain | Load |
|---|---|---|---|
| `fct_sales_lines` | Transaction | One product line on one completed sale (POS or online) | Incremental, 3-day lookback |
| `fct_returns` | Transaction | One returned line on one return receipt | Full rebuild |
| `fct_inventory_daily` | Periodic snapshot (semi-additive) | One product in one store on one day | Incremental, 3-day lookback |
| `fct_online_orders` | Accumulating snapshot | One online order, updated as it moves through its lifecycle | Incremental on new events |
| `fct_marketing_spend` | Transaction (daily) | One campaign × channel × country × day | Full rebuild |

**Late data:** incremental facts use `delete+insert` keyed on the business date and rebuild the last 3 days on every run. Online orders arrive up to 2 days late and can be cancelled within 48 hours. Replacing the whole window picks up late rows *and* removes cancelled ones, which a merge on the line key could not do. Rows older than the window need `dbt build --full-refresh`.

## CI/CD

| Workflow | When | What it does |
|---|---|---|
| [CI](.github/workflows/ci.yml) · lint | every pull request | pre-commit: SQLFluff, MetricFlow-export sync, YAML, private-key scan, unit tests |
| CI · e2e-duckdb | every pull request | Generates a 5-week sample → Postgres, API and files → dlt → DuckDB → `dbt build` → MetricFlow reconciliation, plus the Dagster graph test. No credentials needed. |
| CI · slim-ci | every pull request | Snowflake: `dbt build --select state:modified+ --defer` against the production manifest, in a temporary `ci_pr_<n>` schema (incremental facts read only 30 days), dropped afterwards |
| [Deploy](.github/workflows/deploy.yml) | merge to `main` | Builds the changed models in PROD, regenerates the [dbt docs site](https://salmantariq596.github.io/gulf-retail-analytics/) and publishes it to GitHub Pages |

- **Production state:** the docs site's `manifest.json` is what slim CI compares pull requests against.
- **CI login:** CI signs in to Snowflake as its own service user, `github_ci`. Its key exists only as a GitHub secret ([snowflake/setup_github_ci.py](snowflake/setup_github_ci.py) creates and rotates it).

## Testing strategy

| Kind | Count | What it protects |
|---|---|---|
| Generic (unique, not_null, relationships, accepted_values) | 204 | Keys, joins, and code values at every layer |
| dbt_utils / dbt_expectations | 62 | SCD2 ranges never overlap, value ranges, column pairs, and statistical drift monitors (warn) |
| Singular | 9 | **Reconciliation**: fact totals equal POS receipt totals and online order totals. Cost on sale date, Gulf calendar facts, net revenue ≥ 0 |
| Unit tests | 4 | VAT split + FX + local date + cost on sale date, return matching, order lag maths, inventory gap filling |

`warn` severity is used only on purpose: for known source problems handled downstream (duplicate till lines, negative stock) and for drift monitors that should alert someone without blocking a load.

DuckDB allows a single writer: don't run `najm-ingest` and `dbt` at the same time. See [CONTRIBUTING.md](CONTRIBUTING.md) for layer and naming conventions.

Without Docker, the API also runs locally: `uvicorn mock_api.main:app --app-dir generator --port 8000`.
The full 3-year dataset (`--profile full`: 14M sales, 23.8M POS lines, 41M stock rows) is generated and loaded into Snowflake by [snowflake/full_load.ps1](snowflake/full_load.ps1).

| Generated (dev profile, 92 days) | Rows |
|---|---|
| POS sales / lines (0.5% duplicated) | ~236k / ~402k |
| POS returns (15% without a receipt, ~2k online orders returned in store) | ~19k |
| Online orders / status events (2% late, 3% cancelled, 25% cash on delivery) | ~42k / ~162k |
| Daily stock snapshots (1% of days missing) | ~700k |
| Catalog exports (prices, costs and categories change over time) | ~270k |
| Marketing spend rows (incl. restated days) | ~6k |
