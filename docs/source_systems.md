# Source Systems

> **How it's generated:** `najm-gen` simulates the business **one day at a time**, and a backfill is just that daily loop run many times. History (price changes, tier changes, store openings and closures) is therefore produced exactly as a daily production feed would produce it. Everything emitted for business day *d* has a timestamp between the end of day *d−1* and the end of day *d* (UAE time), so watermark-based incremental extraction never skips a row.
> File drops land in the raw schemas **as text**, plus `_file_name` and `_file_date`. Casting is staging's job.

There are five systems. Each one adds a different modeling problem. The data comes from `generator/`. The problems are injected **on purpose**: if the data were clean, the tests would prove nothing.

| # | System | Lands as | Raw schema (warehouse) | Load strategy |
|---|---|---|---|---|
| 1 | POS (store tills) | PostgreSQL `pos` schema | `raw_pos` | Incremental on `updated_at` / `created_at` |
| 2 | Online store | JSON from the mock REST API | `raw_online` | Incremental via `?updated_since=` + pagination |
| 3 | Inventory / ERP | Daily CSV files | `raw_erp` | Append new files only |
| 4 | Product catalog | Daily full CSV export | `raw_catalog` | Append each export (history is rebuilt with snapshots) |
| 5 | Marketing | Daily CSV exports per platform | `raw_marketing` | Append new files only |

---

## 1. POS — PostgreSQL

Full DDL: [generator/sql/01_pos_schema.sql](../generator/sql/01_pos_schema.sql)

Tables: `stores`, `cashiers`, `customers` (loyalty master), `promotions`, `sales`, `sale_lines`, `payments`, `returns`, `return_lines`.

| Problem it creates | How it shows up | Handled in |
|---|---|---|
| Duplicate lines after till restarts (~0.5%) | Same `(sale_id, line_number)`, new `sale_line_id`, later `created_at` | `int_pos_sale_lines_deduped` (keep the earliest) |
| Test transactions | `cashier_code LIKE 'TRN-%'`, or `sku = 'TEST-0000'` | staging filter + flag |
| Voided sales | `sales.status = 'voided'` | excluded in intermediate |
| Returns without a receipt | `original_sale_id IS NULL` | `fct_returns.original_sale_line_key` is nullable |
| Online orders returned in store | `original_online_order_id` is set | matched to online lines in intermediate |
| VAT-inclusive local prices | All `*_incl_vat` columns | VAT split + AED conversion macros |
| UTC timestamps, local business dates | `timestamptz` | convert with `stores.timezone` |
| Store opening and closure | New stores open in year 2; one store closes in year 3 (`closed_on`) | `snap_stores` (SCD2) |
| Loyalty tier changes | `customers.loyalty_tier` + `updated_at` | `snap_customers` (timestamp strategy) |

## 2. Online store — mock REST API (FastAPI)

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /customers?updated_since=&cursor=&page_size=` | Online accounts | `loyalty_number` is optional and links to the POS loyalty master; guests have none |
| `GET /orders?updated_since=&cursor=&page_size=` | Orders with embedded `lines[]` | `status` is the *furthest lifecycle stage reached*; `updated_at` changes on every event |
| `GET /order_events?updated_since=&cursor=&page_size=` | One event per status change | placed, paid, shipped, delivered, cancelled |

Pagination: `page` (offset) or `cursor` (keyset on `updated_at` + primary key, returned as `next_cursor`). dlt uses the cursor because its cost stays the same however deep the page is.

Order JSON (shape):
```json
{
  "order_id": "WEB-2025-000123", "customer_id": "c_8f2a...", "channel": "app",
  "ship_country": "SA", "currency": "SAR", "promotion_code": "WHITEFRIDAY25",
  "placed_at": "2025-11-27T19:04:11Z", "status": "shipped", "updated_at": "2025-11-28T08:00:02Z",
  "lines": [{"line_number": 1, "sku": "TV-SAM-55Q80", "quantity": 1,
             "unit_price_incl_vat": 3499.00, "discount_incl_vat": 525.00}]
}
```

| Problem it creates | How it shows up | Handled in |
|---|---|---|
| Late-arriving orders | ~2% of orders first appear 1–2 days after `placed_at` | 3-day lookback in `fct_sales_lines` |
| Order lifecycle | Status changes over days | `fct_online_orders` accumulating snapshot, built from `order_events` |
| Cancellations | ~3%, within 48 hours, before shipping | excluded from sales |
| Cash on delivery (~25%) | The `paid` event comes *after* `delivered` | Lags are computed from events, never from `status` |
| Nested JSON | `lines[]` array | dlt unnests into a child table `orders__lines` |
| Customer identity split | Online customer id ≠ POS customer id | unified on `loyalty_number` in `int_customers_unified` |

## 3. Inventory / ERP — daily CSV

`landing/erp/stock_on_hand/stock_on_hand_YYYY-MM-DD.csv`
`snapshot_date, store_code, sku, qty_on_hand, qty_on_order`

`landing/erp/purchase_orders/purchase_orders_YYYY-MM-DD.csv`
`po_number, store_code, sku, qty_ordered, ordered_on, expected_on, received_on, unit_cost, currency_code`

| Problem | How it shows up | Handled in |
|---|---|---|
| Missing days | ~1% of daily files never arrive | `fct_inventory_daily` carries the last known value forward and flags `is_imputed` |
| Negative stock | Rare sync errors give `qty_on_hand < 0` | warn-severity test + floor at 0 in marts, documented |

## 4. Product catalog — daily full CSV export

`landing/catalog/products_YYYY-MM-DD.csv`
`sku, product_name_en, product_name_ar, category, subcategory, brand, unit_cost_aed, list_price_aed, is_active, launched_on, export_date`

Prices are list prices in AED, **excluding VAT**. Changes take effect from the `export_date` on which they first appear.

There is **no `updated_at`**, so `snap_products` uses the **check** strategy on `unit_cost_aed, list_price_aed, category, subcategory, brand, is_active`.

| Problem | How it shows up |
|---|---|
| Price changes | Cost and list price change a few times a year per product |
| Re-categorisation | ~3% of products move category over the 3 years |
| Discontinued items | `is_active` flips to false; old sales still need the product |
| Test SKU | `TEST-0000` exists in the catalog |

## 5. Marketing — daily CSV per platform

`landing/marketing/<platform>/spend_YYYY-MM-DD.csv`
`date, campaign_id, campaign_name, marketing_channel, country_code, currency_code, spend, impressions, clicks`

Platforms: google_ads, meta, tiktok, snapchat, email, affiliate. Every platform reports in its own account currency, which can be USD, AED or SAR.

| Problem | How it shows up |
|---|---|
| Mixed currencies, including USD | Converted to AED with the peg rate |
| Restated days | Platforms re-export the last 3 days with corrected numbers, so the latest file wins per `(date, campaign_id, country_code)` |
| Campaign name drift | The same `campaign_id` gets renamed, so `dim_campaign` takes the latest name |
