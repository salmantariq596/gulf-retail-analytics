# Requirements — Najm Retail Analytics Warehouse

Najm Retail (fictional) sells electronics and home goods through 25 stores in the UAE, Saudi Arabia and Qatar, plus an online store (web and app).
This document records what four stakeholders need. The [bus matrix](bus_matrix.md) and the [business definitions](business_definitions.md) are derived from it.

**The core question:** *Which stores, products and channels make money after returns and discounts, how much stock are we holding, and which marketing spend brings customers who come back?*

## Global requirements

| # | Requirement |
|---|---|
| G1 | All money is reported in **AED**, the reporting currency. The original local currency (AED, SAR, QAR) stays available as well. |
| G2 | Revenue is reported **excluding VAT** by default. A VAT-inclusive figure is available on request. |
| G3 | The business date is the **local date** of the store (or of the ship-to country for online orders), not the UTC date. |
| G4 | Weekends follow the country: UAE Sat–Sun, KSA and Qatar Fri–Sat. |
| G5 | Ramadan, Eid al-Fitr, Eid al-Adha, White Friday and Dubai Shopping Festival can be selected in any report. |
| G6 | Product, store and customer attributes are reported **as they were at the time of the event**, for example the cost price or loyalty tier on the sale date. The current value is also available. |
| G7 | Test and training transactions never appear in any number. |
| G8 | The data is refreshed daily by 06:00 local time and covers the previous day. |
| G9 | Every metric has one definition, held in the semantic layer, which every dashboard uses. |

## Stakeholder 1 — CFO (finance)

| # | Question | Metric(s) | Answered by |
|---|---|---|---|
| F1 | What is net revenue by month, country, store and channel? | Net revenue | fct_sales_lines, fct_returns |
| F2 | What are gross margin and margin % by category and brand? | Gross margin, margin % | fct_sales_lines (cost valid on the sale date) |
| F3 | How much revenue do discounts and promotions cost us? | Discount amount, discount rate | fct_sales_lines, dim_promotion |
| F4 | How much VAT do we collect per country? | VAT amount | fct_sales_lines |
| F5 | Which stores are unprofitable after returns? | Net revenue, gross margin, return rate | rpt_store_performance_monthly |
| F6 | How do Ramadan and Eid compare with the same period last year? | Net revenue, YoY % | fct_sales_lines × dim_date |

## Stakeholder 2 — Merchandising

| # | Question | Metric(s) | Answered by |
|---|---|---|---|
| M1 | How much stock do we hold, in units and at cost, per store and category? | Closing stock units, stock value at cost | fct_inventory_daily |
| M2 | Which products sell through and which ones sit on the shelf? | Sell-through rate | fct_sales_lines + fct_inventory_daily |
| M3 | Which products and categories have the highest return rates? | Return rate | fct_returns, fct_sales_lines |
| M4 | What are the top 3 products per store by margin last month? | Gross margin, rank | fct_sales_lines |
| M5 | Where are we out of stock? | Days with zero stock | fct_inventory_daily |
| M6 | How did price changes affect units sold? | Units sold, average selling price | fct_sales_lines × dim_product (SCD2) |

## Stakeholder 3 — Marketing

| # | Question | Metric(s) | Answered by |
|---|---|---|---|
| K1 | How much do we spend per channel and campaign, and what do we get for it? | Spend, clicks, impressions, CTR, CPC | fct_marketing_spend |
| K2 | Which acquisition channels return the most revenue per AED spent? | ROAS (first-touch) | fct_marketing_spend, fct_sales_lines, dim_customer |
| K3 | Do customers acquired through each channel come back? | Cohort retention | rpt_customer_cohort_retention |
| K4 | How many active customers do we have, and in which loyalty tier? | Active customers | fct_sales_lines × dim_customer |
| K5 | Which customer segments are worth targeting? | RFM segment | rpt_customer_rfm |
| K6 | How fast do we deliver online orders, and where do orders get stuck? | Average delivery hours, stage lags | fct_online_orders |

## Stakeholder 4 — CEO

| # | Question | Metric(s) |
|---|---|---|
| C1 | A one-page view: net revenue, gross margin %, active customers, stock value, ROAS, each compared with the previous period and the same period last year | All of the above |
| C2 | How does online compare with stores, and is the gap growing? | Net revenue share by channel |
| C3 | Which countries are growing? | Net revenue YoY by country |

## Dashboards (Phase 6)

1. **Executive overview** (C1–C3, F1, F6)
2. **Merchandising** (M1–M6, F2)
3. **Marketing and customers** (K1–K6)

## Out of scope

- Multi-touch attribution. First-touch only; see the limitation noted under ROAS.
- Store labour, rent and operating costs. "Make money" means gross margin, not net profit.
- Supplier, warehouse-to-store logistics and purchase order fulfilment performance. Purchase orders are only used as context for stock.
- Real-time reporting. Daily batch only.
