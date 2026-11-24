# Contributing

Conventions for this repo. These follow dbt Labs' recommended project structure, so anyone who has used dbt will recognise the layout.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate     # activate before committing: hooks use the venv's tools
pip install -r requirements.txt && pip install -e .
pre-commit install
cd dbt && dbt deps
```

Run dbt from the `dbt/` folder. `profiles.yml` lives there and contains no secrets; every credential comes from an environment variable.

## dbt layers

| Layer | Folder | Naming | Materialization | Rules |
|---|---|---|---|---|
| Sources | `models/staging/<source>/_<source>__sources.yml` | — | — | Every raw table is declared. Tables that change daily have freshness checks |
| Staging | `models/staging/<source>/` | `stg_<source>__<entity>` | view | **1:1 with a source table.** Rename, cast, standardise codes, convert timestamps to UTC. **No joins, no aggregations, no filtering of business rows** |
| Snapshots | `snapshots/` | `snap_<entity>` | snapshot | SCD Type 2 history |
| Intermediate | `models/intermediate/` | `int_<entity>_<verb>` | ephemeral / view | Business logic: dedupe, join channels, currency, VAT, cost on sale date |
| Marts | `models/marts/<domain>/` | `dim_*`, `fct_*` | table / incremental | The star schema. Contracts are enforced on dimensions |
| Reports | `models/marts/<domain>/` | `rpt_*` | table | Pre-aggregated tables for one dashboard |

### Why staging never joins

- A staging model is the one clean interface to its source table. Every downstream model reads the same renamed, typed and standardised columns, and staging contains no business decisions.
- If staging joined A to B, a change in B would silently change A's staging model. Debugging a wrong number would then mean digging through every layer.
- Some things look like they need a join, and they are deliberately pushed down a layer:
  - **Test sales** are identified by the training cashier, so staging *flags* them (`is_training_cashier`, `is_test_sku`) and the intermediate layer *filters* them.
  - **dlt child tables**: `orders__lines` carries the parent's row id, not `order_id`. Staging exposes `order_record_id` on both sides, and the intermediate layer joins them.

## History (SCD Type 2)

| Entity | Source behaviour | How history is kept | Strategy |
|---|---|---|---|
| Stores | Postgres row overwritten, `updated_at` reliable | `snap_stores` (dbt snapshot) | timestamp |
| Customers (loyalty) | Postgres row overwritten, `updated_at` reliable | `snap_customers` (dbt snapshot) | timestamp |
| Products | Full catalog exported daily, no reliable `updated_at` | `int_products_versioned`: compare consecutive exports | check (hash of tracked columns) |

- **Use timestamp** when the source has an `updated_at` that changes on every edit. It's cheap and exact.
- **Use check** when it doesn't. You compare the columns you care about, and changes to columns you don't track are ignored.
- **Snapshots only capture history from the day they start running.** For a source that keeps its own history (like the catalog exports), derive versions in a model instead: it can be rebuilt and it backfills.
- Every versioned dimension has `valid_from` / `valid_to` (exclusive) / `is_current`. The first version is valid from 1900-01-01, and the current one until 9999-12-31. `dbt_utils.mutually_exclusive_ranges` tests that versions never overlap or leave gaps.
- Facts join to the version valid **at event time**. Products use the business date; stores and customers use the event timestamp.

## Column conventions

| Pattern | Meaning |
|---|---|
| `*_id` | Natural/source key (`sale_id`, `sku` is the product's natural key) |
| `*_key` | Surrogate key in the marts (`dbt_utils.generate_surrogate_key`) |
| `*_at` | Timestamp, **UTC, no timezone** (converted by the `to_utc` macro) |
| `*_on` / `*_date` | Calendar date. Business dates are the **local** date of the store / ship-to country |
| `is_*` / `has_*` | Boolean |
| `*_incl_vat` / `*_excl_vat` | Amount including / excluding VAT. Sources are VAT-inclusive |
| `*_local` / `*_aed` | Amount in the transaction currency / converted to AED |
| `_file_name`, `_file_date`, `source_file`, `file_date` | Lineage columns from file-based sources |

## Tests

- **Every model:** the primary key is `unique` + `not_null`, and every foreign key has a `relationships` test.
- **Every enum-like column:** `accepted_values`.
- **Business rules:** dbt_expectations (ranges, column pairs) and singular tests in `tests/` named `assert_<what must be true>.sql`.
- **`severity: warn`:** only for **known, documented** source problems that are handled downstream (duplicate till lines, negative stock). Every warn has a comment saying why.
- Prefer tests that would catch a **wrong number**, not only a missing one. The reconciliation tests (`assert_pos_sale_total_matches_lines`) are the most valuable ones.

## SQL style

Enforced by SQLFluff (`.sqlfluff`, runs in pre-commit):
- lowercase everything, 4-space indents, lines up to 120 characters
- explicit `as` for aliases
- import CTEs first (`source`, then `renamed`), one logical step per CTE, and end with `select * from <final_cte>`

## Seeds

Seeds hold small, slowly changing reference data: currency pegs, VAT history, weekends, countries and marketing channels. The calendar seeds (`hijri_calendar`, `gulf_holidays`, `retail_events`) are **generated** from `generator/najm_gen/gulf_calendar.py`, so the warehouse and the generator share one calendar:

```bash
python -m najm_gen.seeds
```

## Commits

Keep one logical change per commit, with a short imperative subject ("Add stg_pos__sales"). Pull requests run slim CI (Phase 7).
