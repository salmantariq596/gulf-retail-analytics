# Bus Matrix and Fact Grains

Each row is a business process and becomes a fact table. Each column is a **conformed dimension**, meaning it has the same keys and the same meaning in every fact that uses it.

## Bus matrix

| Business process (fact) | Fact type | Date | Store | Product | Customer | Channel | Promotion | Campaign |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Sales lines — `fct_sales_lines` | Transaction | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| Returns — `fct_returns` | Transaction | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| Inventory — `fct_inventory_daily` | Periodic snapshot (daily) | ✓ | ✓ | ✓ |  |  |  |  |
| Online order lifecycle — `fct_online_orders` | Accumulating snapshot | ✓ (×4 roles) | ✓¹ |  | ✓ | ✓ |  |  |
| Marketing spend — `fct_marketing_spend` | Transaction (daily) | ✓ |  |  |  |  |  | ✓² |

¹ This links to the **virtual online store** for the ship-to country (`ONL-AE/SA/QA`), which brings in country, currency and VAT through the conformed store dimension. It goes beyond the original plan. Marketing spend carries `country_code` as a degenerate attribute instead, because campaigns target countries, not stores.
² The marketing channel (google_ads, meta, tiktok, snapchat, email, affiliate) is an attribute of `dim_campaign`. `dim_channel` is the **sales** channel (store/web/app). The two are not the same thing; see the decisions log in [business_definitions.md](business_definitions.md).

## Grain of each fact, one sentence each

| Fact | Grain |
|---|---|
| `fct_sales_lines` | **One row per product line on one completed sale**: a deduplicated POS sale line or a non-cancelled online order line. |
| `fct_returns` | **One row per returned product line on one return receipt**, linked to the original sale line where known. |
| `fct_inventory_daily` | **One row per product per store per day** with the closing stock on hand at end of day. |
| `fct_online_orders` | **One row per online order**, updated in place as the order moves through placed → paid → shipped → delivered (or cancelled). |
| `fct_marketing_spend` | **One row per campaign per marketing channel per country per day.** |

## Why these grains

- **Sales at line level, not order level.** Product, promotion, discount and cost all vary per line. An order-level fact can't answer margin by category without allocating amounts, while a line-level fact can always be rolled up to order level.
- **Returns as their own fact.** A return happens on a different date, often in a different store, and often without the original receipt. Netting returns into the sale line would change history and lose the return date.
- **Inventory as a periodic snapshot.** Stock is a *level*, not a flow. The facts are semi-additive: they can be summed across stores and products, but **never across days**. Use the period-end value or the daily average.
- **Online orders as an accumulating snapshot.** The questions are about process timing (how long from paid to shipped?). One row per order with a date for each milestone makes lag calculations a simple subtraction.
- **Marketing at day × campaign × channel × country.** This is the grain of the ad platform exports. Going finer is impossible and going coarser loses information.

## Dimensions

| Dimension | Grain | SCD | Notes |
|---|---|---|---|
| `dim_date` | One calendar day | — | Gregorian + Hijri, Ramadan flag, holiday name, `is_weekend_ae`, `is_weekend_sa`, `is_weekend_qa` |
| `dim_store` | One store version | Type 2 | Includes 3 virtual online stores; format, city, country, opened/closed dates |
| `dim_product` | One product version | Type 2 | Category, brand, unit cost, list price, English + Arabic names |
| `dim_customer` | One customer version | Type 2 | Loyalty tier, country, first purchase date, acquisition channel |
| `dim_channel` | One sales channel | — | store, web, app |
| `dim_promotion` | One promotion | — | Code, type, value, start/end |
| `dim_campaign` | One campaign | — | Campaign name, marketing channel, objective |

Facts join to SCD2 dimensions on the **surrogate key of the version that was valid at event time**. Every SCD2 dimension also exposes `is_current` so reports can use current attributes.
