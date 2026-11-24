# Business Definitions

These definitions were agreed **before any SQL was written**. Each metric in `dbt/models/semantic/` must implement exactly the definition given here. When the two disagree, this document is the one to fix, and the change has to be reviewed.

## Conventions used by every metric

| Topic | Rule |
|---|---|
| Reporting currency | AED. Local amounts are converted at fixed peg rates from the `currency_rates` seed: AED 1.000000, SAR 3.6725/3.75 = **0.979333**, QAR 3.6725/3.64 = **1.008929**, USD **3.6725** AED per unit (USD only appears in marketing exports). |
| VAT | Shelf and online prices **include VAT** (as Gulf consumer law requires). Net-of-VAT amount = gross amount / (1 + VAT rate). The rates come from the `vat_rates` seed: UAE 5%, KSA 15%, Qatar 0%. The rate used is the one valid on the transaction date. |
| Business date | The local date in the store's timezone (UAE UTC+4, KSA and Qatar UTC+3). For online orders, the ship-to country is used. |
| Sales channel | `store` (POS), `web`, `app`. |
| Online stores | Online orders are assigned to a virtual store per country (`ONL-AE`, `ONL-SA`, `ONL-QA`). This lets currency, VAT and country work the same way for stores and online. |
| Exclusions | Test and training transactions, cancelled online orders and POS duplicate lines are removed in the intermediate layer and never reach the marts. |
| Identified customer | A sale that carries a customer key: a loyalty member at the till, or a logged-in or guest-with-email online customer. Anonymous walk-in sales count towards revenue but not towards any customer metric. |

## Building blocks

| Term | Definition |
|---|---|
| **Gross sales** | Σ (quantity × unit list price charged), excluding VAT, **before** discounts. |
| **Discounts** | Σ line discount amounts (promotion and manual), excluding VAT. |
| **Returns** | Σ refund amounts of returned lines, excluding VAT, **booked on the return date** (not the original sale date). This keeps closed months stable. |
| **COGS** | Σ (quantity × product unit cost **valid on the sale date**). The cost comes from the SCD2 product dimension: `valid_from <= sale_ts < valid_to`. Returned units reverse COGS at the cost of the original sale when it is known, and otherwise at the cost valid on the return date. |
| **Units sold** | Σ quantity on sales lines (not net of returns). |
| **Transaction** | One POS sale (`sale_id`) or one online order (`order_id`). |

## Metrics (the 10 governed metrics, plus supporting ones)

### 1. Net revenue
**Net revenue = gross sales − discounts − returns, excluding VAT, in AED.**
- *Online recognition:* an online order counts on its **placed** business date. An order whose final status is `cancelled` is excluded completely. Cancellations are only allowed within 48 hours and before shipping, which is why the incremental model uses a 3-day lookback.
- *Edge case:* a return of an online order made in a store is booked to the store where the return happened, on the return date.

### 2. Gross margin
**Gross margin = net revenue − COGS (net of returned COGS).** It uses the product cost valid on the sale date from `dim_product` (SCD2), never the current cost.

### 3. Gross margin %
**Gross margin % = gross margin / net revenue.** This is a ratio metric: it is always computed from the summed numerator and denominator, never by averaging line percentages.

### 4. Units sold
**Units sold = Σ quantity on sales lines.** Net units = units sold − returned units. This is shown separately.

### 5. Average basket value (ABV)
**ABV = (gross sales − discounts) / number of transactions, excluding VAT, in AED.** Returns are excluded on purpose because ABV describes the basket at checkout.

### 6. Return rate
**Return rate = returns (refund value, ex VAT) / (gross sales − discounts) in the same period, ex VAT.** It is value-based. A unit-based variant (returned units / units sold) is provided for merchandising.
*Limitation:* returns are booked on the return date, so a month with heavy sales followed by returns in the next month will show a timing mismatch. Use quarterly windows for trend analysis.

### 7. Active customers
**Active customer = an identified customer with at least one non-cancelled, non-test purchase in the 90 days ending on the reporting date** (the window covers `reporting_date − 89` to `reporting_date`). For a month, the reporting date is the last day of that month.

### 8. Sell-through rate
**Sell-through rate = units sold in the period / (units sold in the period + closing stock units at period end)**, per product × store, and rolled up by summing numerator and denominator.
- Closing stock is the `fct_inventory_daily` row on the last day of the period. Stock is **semi-additive**: it is never summed across days.
- If the inventory file for the last day is missing, the latest available snapshot within the previous 3 days is used and flagged.

### 9. ROAS (return on ad spend)
**ROAS = attributed net revenue / marketing spend, in AED, per acquisition channel and period.**
- *Attribution:* **first-touch**. Each customer is attributed to the acquisition channel recorded when they were created (`dim_customer.acquisition_channel`, which uses the same channel codes as marketing spend). All of that customer's net revenue in the period counts towards that channel.
- *Variant:* **New-customer ROAS** only counts revenue from customers acquired in the same period.
- *Stated limitations:* (a) later touchpoints get no credit; (b) anonymous and organic/walk-in revenue is not attributed to any channel; (c) spend in one month often drives revenue in later months, so short windows understate ROAS; (d) a lifetime customer keeps crediting their first channel forever. These limitations are accepted for this project. Multi-touch attribution would need clickstream data, which we don't have.

### 10. Average delivery hours
**Average delivery hours = average of (delivered_ts − placed_ts) in hours over orders delivered in the period** (grouped by placed date). Stage lags (placed→paid, paid→shipped, shipped→delivered) are defined the same way.

### Supporting metrics
| Metric | Definition |
|---|---|
| VAT collected | Σ VAT portion of (gross sales − discounts) − VAT portion of refunds |
| Discount rate | Discounts / gross sales |
| Stock value at cost | Closing stock units × unit cost valid on the snapshot date |
| Out-of-stock days | Count of store × product × days with closing stock = 0 for products active in the catalog |
| Marketing spend | Σ spend in AED from `fct_marketing_spend` |
| CTR / CPC | Clicks / impressions; spend / clicks |
| Cohort retention | % of customers in a first-purchase month cohort who purchase again in month *n* |

## Open decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-11-22 | Returns are booked on the return date | Closed periods do not restate; this is standard retail practice |
| 2026-11-22 | Online revenue is recognised on the placed date, excluding cancelled orders | Matches how the commerce team reports; cancellations happen within 48 hours |
| 2026-11-22 | Prices are stored VAT-inclusive in the sources and the VAT split is derived | This mirrors real Gulf POS data |
| 2026-11-22 | Sales channel (`dim_channel`) is kept separate from marketing channel (`dim_campaign.marketing_channel`, `dim_customer.acquisition_channel`) | "Where the sale happened" and "how the customer was acquired" are different questions that share one word |
| 2026-11-24 | Product SCD2 versions are derived from the daily catalog export history (`int_products_versioned`); a version takes effect on the export date | The catalog keeps every export, so history can be rebuilt at any time; a dbt snapshot only sees the current state and could not backfill 3 years |
| 2026-11-24 | Stores and customers use dbt snapshots (timestamp strategy); the first version of each record is valid from 1900-01-01 | Postgres overwrites rows in place: history exists only from the first snapshot. Without an open start, facts older than the first snapshot would match no version |
| 2026-11-24 | Customers are unified on loyalty number: `L-<loyalty_number>` or `O-<online_customer_id>`; anonymous sales use the `-1` member | A loyalty member who also buys online is one customer; facts never carry a null customer key |
| 2026-11-24 | Marts carry no direct PII (no names, emails, phones) | Analytics needs segments, not identities |
