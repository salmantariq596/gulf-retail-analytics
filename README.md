# Gulf Retail Analytics Warehouse

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

## Progress

- [x] **Phase 0** — Requirements, bus matrix, definitions, model diagram, repo + Docker Compose
- [x] **Phase 1** — Data generator + FastAPI mock + dlt ingestion into DuckDB
- [x] **Phase 2** — dbt setup, sources, seeds, staging, SQLFluff *(17 staging models, 8 seeds, 137 tests, 13 freshness checks)*
- [x] **Phase 3** — Snapshots, intermediate models, dimensions with contracts *(2 snapshots, 8 intermediate models, 7 contracted dimensions)*
- [x] **Phase 4** — Fact tables, incremental models, 100+ tests *(5 facts + 1 report, 275 data tests + 4 unit tests)*
- [ ] **Phase 5** — Snowflake: RBAC, warehouses, prod build
- [ ] **Phase 6** — MetricFlow metrics, Lightdash dashboards, Dagster
- [ ] **Phase 7** — CI/CD, docs site, launch

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

## Fact tables

| Fact | Type | Grain | Load |
|---|---|---|---|
| `fct_sales_lines` | Transaction | One product line on one completed sale (POS or online) | Incremental, 3-day lookback |
| `fct_returns` | Transaction | One returned line on one return receipt | Full rebuild |
| `fct_inventory_daily` | Periodic snapshot (semi-additive) | One product in one store on one day | Incremental, 3-day lookback |
| `fct_online_orders` | Accumulating snapshot | One online order, updated as it moves through its lifecycle | Incremental on new events |
| `fct_marketing_spend` | Transaction (daily) | One campaign × channel × country × day | Full rebuild |

**Late data:** incremental facts use `delete+insert` keyed on the business date and rebuild the last 3 days on every run. Online orders arrive up to 2 days late and can be cancelled within 48 hours. Replacing the whole window picks up late rows *and* removes cancelled ones, which a merge on the line key could not do. Rows older than the window need `dbt build --full-refresh`.

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
The full 3-year dataset (`--profile full`, ~20M POS lines) is generated for Snowflake in Phase 5.

| Generated (dev profile, 92 days) | Rows |
|---|---|
| POS sales / lines (0.5% duplicated) | ~236k / ~402k |
| POS returns (15% without a receipt, ~2k online orders returned in store) | ~19k |
| Online orders / status events (2% late, 3% cancelled, 25% cash on delivery) | ~42k / ~162k |
| Daily stock snapshots (1% of days missing) | ~700k |
| Catalog exports (prices, costs and categories change over time) | ~270k |
| Marketing spend rows (incl. restated days) | ~6k |
