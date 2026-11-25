"""Lightdash dashboards as code.

Writes chart and dashboard YAML to bi/lightdash/content/, in the format `lightdash download`
produces, then `lightdash upload` publishes them (bi/lightdash/publish.ps1).

    python bi/lightdash/dashboards.py

Every chart queries a generated mtr_* explore, so every number on these dashboards comes
from a MetricFlow metric definition (see docs/metrics_catalog.md).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import yaml

CONTENT = Path(__file__).resolve().parent / "content"
SPACE = "gulf-retail"
NS = uuid.UUID("6f1c2a4e-9d1b-4c7a-8e2f-3b5d7a9c1e01")  # stable ids for filters

SALES, MERCH, ONLINE, MKT = "mtr_sales_daily", "mtr_merchandising_monthly", "mtr_online_orders_daily", "mtr_marketing_monthly"
TIME = {SALES: "metric_date", MERCH: "metric_month", ONLINE: "metric_date", MKT: "metric_month"}


def f(table: str, field: str) -> str:
    return f"{table}_{field}"


def month(explore: str) -> str:
    return f(explore, f"{TIME[explore]}_month")


def last_completed_months(explore: str, slug: str, n: int) -> dict:
    """Filter: the last n completed calendar months (the current month is partial)."""
    return {"dimensions": {"id": str(uuid.uuid5(NS, slug)), "and": [{
        "id": str(uuid.uuid5(NS, slug + "/month")),
        "target": {"fieldId": f(explore, TIME[explore])},
        "operator": "inThePast",
        "values": [n],
        "settings": {"unitOfTime": "months", "completed": True},
    }]}}


def equals(field_id: str, value, slug: str) -> dict:
    return {"id": str(uuid.uuid5(NS, slug + field_id)), "target": {"fieldId": field_id},
            "operator": "equals", "values": [value]}


def chart(slug: str, name: str, explore: str, dims: list[str], metrics: list[str], config: dict,
          description: str = "", sorts: list[tuple[str, bool]] = (), limit: int = 500,
          filters: dict | None = None) -> dict:
    return {
        "chartConfig": config,
        "contentType": "chart",
        "description": description or None,
        "metricQuery": {
            "additionalMetrics": [], "customDimensions": [], "dimensions": dims,
            "exploreName": explore, "filters": filters or {}, "limit": limit,
            "metricOverrides": {}, "metrics": metrics,
            "sorts": [{"descending": desc, "fieldId": fid} for fid, desc in sorts],
            "tableCalculations": [], "timezone": "project_timezone",
        },
        "name": name, "slug": slug, "spaceSlug": SPACE,
        "tableConfig": {"columnOrder": dims + metrics},
        "tableName": explore, "verification": None, "version": 1,
    }


def kpi(slug: str, label: str, explore: str, metric: str, lower_is_better: bool = False) -> dict:
    """Big number: last completed month, compared with the month before."""
    m = f(explore, metric)
    return chart(
        slug, label, explore, [month(explore)], [m],
        {"type": "big_number", "config": {
            "label": label, "selectedField": m, "showComparison": True,
            "comparisonFormat": "percentage", "flipColors": lower_is_better,
        }},
        description="Last completed month, change vs the month before.",
        sorts=[(month(explore), True)], limit=2,
        filters=last_completed_months(explore, slug, 2),
    )


def cartesian(slug: str, name: str, explore: str, x: str, series: list[tuple[str, str, int]],
              horizontal: bool = False, sort_by: tuple[str, bool] | None = None,
              filters: dict | None = None, description: str = "", extra_dims: list[str] = ()) -> dict:
    """series: (metric field id, 'bar'|'line', y axis index)."""
    ys = [s[0] for s in series]
    config = {"type": "cartesian", "config": {
        "layout": {"xField": x, "yField": ys, "flipAxes": horizontal, "showIncompletePeriod": False},
        "eChartsConfig": {"series": [
            {"encode": {"xRef": {"field": x}, "yRef": {"field": y}}, "type": kind, "yAxisIndex": axis}
            for y, kind, axis in series
        ]},
    }}
    sorts = [sort_by] if sort_by else [(x, False)]
    return chart(slug, name, explore, [x, *extra_dims], ys, config, description, sorts, filters=filters)


def table(slug: str, name: str, explore: str, dims: list[str], metrics: list[str],
          sort_by: tuple[str, bool], filters: dict | None = None, description: str = "") -> dict:
    config = {"type": "table", "config": {"showTableNames": False, "hideRowNumbers": True,
                                          "showColumnCalculation": False, "showRowCalculation": False}}
    return chart(slug, name, explore, dims, metrics, config, description, [sort_by], filters=filters)


def tile(ch: dict, x: int, y: int, w: int, h: int) -> dict:
    return {"h": h, "properties": {"chartName": ch["name"], "chartSlug": ch["slug"], "hideTitle": False,
                                   "title": ""},
            "tabSlug": None, "tileSlug": ch["slug"], "type": "saved_chart", "w": w, "x": x, "y": y}


def note(text: str, x: int, y: int, w: int, h: int, title: str = "") -> dict:
    return {"h": h, "properties": {"content": text, "hideFrame": False, "title": title},
            "tabSlug": None, "type": "markdown", "w": w, "x": x, "y": y}


def dashboard(slug: str, name: str, description: str, tiles: list[dict]) -> dict:
    return {"contentType": "dashboard", "description": description,
            "filters": {"dimensions": [], "metrics": [], "tableCalculations": []},
            "name": name, "slug": slug, "spaceSlug": SPACE, "tabs": [], "tiles": tiles,
            "verification": None, "version": 1}


def kpi_row(kpis: list[dict], y: int = 0) -> list[dict]:
    w = 24 // len(kpis)
    return [tile(k, i * w, y, w, 4) for i, k in enumerate(kpis)]


# ----------------------------------------------------------------- Executive overview
def executive() -> tuple[list[dict], dict]:
    kpis = [
        kpi("exec-kpi-net-revenue", "Net revenue (AED)", SALES, "net_revenue"),
        kpi("exec-kpi-gross-margin-pct", "Gross margin %", SALES, "gross_margin_pct"),
        kpi("exec-kpi-transactions", "Transactions", SALES, "transactions"),
        kpi("exec-kpi-basket", "Average basket (AED)", SALES, "average_basket_value"),
        kpi("exec-kpi-return-rate", "Return rate", SALES, "return_rate", lower_is_better=True),
        kpi("exec-kpi-roas", "ROAS (first touch)", MKT, "roas"),
    ]
    trend = cartesian(
        "exec-net-revenue-and-margin-by-month", "Net revenue and gross margin % by month", SALES,
        month(SALES), [(f(SALES, "net_revenue"), "bar", 0), (f(SALES, "gross_margin_pct"), "line", 1)],
        description="Returns are booked in the month they come back, so margin % dips after peaks.")
    by_country = cartesian(
        "exec-net-revenue-by-country", "Net revenue by country", SALES, f("dim_store", "country_name"),
        [(f(SALES, "net_revenue"), "bar", 0)], horizontal=True, sort_by=(f(SALES, "net_revenue"), True),
        description="All amounts in AED: SAR and QAR are converted at the pegged rates.")
    by_channel = cartesian(
        "exec-net-revenue-by-channel", "Net revenue by sales channel", SALES, f("dim_channel", "channel_name"),
        [(f(SALES, "net_revenue"), "bar", 0)], horizontal=True, sort_by=(f(SALES, "net_revenue"), True))
    weekday = cartesian(
        "exec-net-revenue-by-weekday", "Net revenue by day of week", SALES, f("dim_date", "day_name"),
        [(f(SALES, "net_revenue"), "bar", 0)], sort_by=(f("dim_date", "iso_day_of_week"), False),
        extra_dims=[f("dim_date", "iso_day_of_week")],
        description="Gulf weekends: UAE Sat-Sun since 2022 (Fri-Sat before); KSA and Qatar Fri-Sat.")
    stores = table(
        "exec-store-performance", "Store performance", SALES,
        [f("dim_store", "store_name_en"), f("dim_store", "country_name"), f("dim_store", "store_format")],
        [f(SALES, m) for m in ("net_revenue", "gross_margin_pct", "transactions", "average_basket_value",
                               "return_rate")],
        sort_by=(f(SALES, "net_revenue"), True))
    charts = [*kpis, trend, by_country, by_channel, weekday, stores]
    tiles = [
        *kpi_row(kpis),
        tile(trend, 0, 4, 16, 9), tile(by_country, 16, 4, 8, 9),
        tile(by_channel, 0, 13, 12, 8), tile(weekday, 12, 13, 12, 8),
        tile(stores, 0, 21, 24, 10),
        note("Every figure is a governed MetricFlow metric (net revenue = gross sales - discounts - "
             "returns, excl. VAT, in AED). Definitions: `docs/business_definitions.md`; where each "
             "metric is served: `docs/metrics_catalog.md`.", 0, 31, 24, 2, "About these numbers"),
    ]
    return charts, dashboard("executive-overview", "Executive overview",
                             "Group performance across UAE, KSA and Qatar.", tiles)


# ----------------------------------------------------------------------- Merchandising
def merchandising() -> tuple[list[dict], dict]:
    last_month = last_completed_months(MERCH, "merch-last-month", 1)
    kpis = [
        kpi("merch-kpi-net-revenue", "Net revenue (AED)", MERCH, "net_revenue"),
        kpi("merch-kpi-gross-margin-pct", "Gross margin %", MERCH, "gross_margin_pct"),
        kpi("merch-kpi-units", "Units sold", MERCH, "units_sold"),
        kpi("merch-kpi-sell-through", "Sell-through rate", MERCH, "sell_through_rate"),
        kpi("merch-kpi-stock-value", "Closing stock at cost (AED)", MERCH, "closing_stock_value"),
    ]
    rev_cat = cartesian(
        "merch-net-revenue-by-category", "Net revenue by category", MERCH, f(MERCH, "category"),
        [(f(MERCH, "net_revenue"), "bar", 0)], horizontal=True, sort_by=(f(MERCH, "net_revenue"), True))
    gm_cat = cartesian(
        "merch-margin-by-category", "Gross margin % by category", MERCH, f(MERCH, "category"),
        [(f(MERCH, "gross_margin_pct"), "bar", 0)], horizontal=True,
        sort_by=(f(MERCH, "gross_margin_pct"), True),
        description="Cost valid on the sale date (SCD2 product history), net of returned cost.")
    st_cat = cartesian(
        "merch-sell-through-by-category", "Sell-through by category (last completed month)", MERCH,
        f(MERCH, "category"), [(f(MERCH, "sell_through_rate"), "bar", 0)], horizontal=True,
        sort_by=(f(MERCH, "sell_through_rate"), True), filters=last_month,
        description="Units sold / (units sold + stock on the last day of the month).")
    stock_trend = cartesian(
        "merch-closing-stock-by-month", "Closing stock value by month", MERCH, month(MERCH),
        [(f(MERCH, "closing_stock_value"), "line", 0)],
        description="Stock on the last day of each month, at cost. A level, not a flow: never summed over months.")
    cat_table = table(
        "merch-category-scorecard", "Category scorecard (last completed month)", MERCH, [f(MERCH, "category")],
        [f(MERCH, m) for m in ("net_revenue", "gross_margin_pct", "units_sold", "return_rate",
                               "sell_through_rate", "closing_stock_units", "closing_stock_value")],
        sort_by=(f(MERCH, "net_revenue"), True), filters=last_month)
    charts = [*kpis, rev_cat, gm_cat, st_cat, stock_trend, cat_table]
    tiles = [
        *kpi_row(kpis[:4]), tile(kpis[4], 0, 4, 6, 4),
        note("Stock and sell-through are **month-end positions**: this explore only offers a monthly "
             "time grain, and the stock charts show a single month at a time.", 6, 4, 18, 4, "Reading stock"),
        tile(rev_cat, 0, 8, 12, 9), tile(gm_cat, 12, 8, 12, 9),
        tile(st_cat, 0, 17, 12, 9), tile(stock_trend, 12, 17, 12, 9),
        tile(cat_table, 0, 26, 24, 9),
    ]
    return charts, dashboard("merchandising", "Merchandising",
                             "Category performance, margin and stock.", tiles)


# ------------------------------------------------------------- Marketing & customers
def marketing() -> tuple[list[dict], dict]:
    kpis = [
        kpi("mkt-kpi-ad-spend", "Marketing spend (AED)", MKT, "ad_spend"),
        kpi("mkt-kpi-roas", "ROAS (first touch)", MKT, "roas"),
        kpi("mkt-kpi-online-orders", "Online orders", ONLINE, "online_orders"),
        kpi("mkt-kpi-delivery-hours", "Average delivery (hours)", ONLINE, "average_delivery_hours",
            lower_is_better=True),
    ]
    paid = {"dimensions": {"id": str(uuid.uuid5(NS, "mkt-paid")),
                           "and": [equals(f(MKT, "is_paid"), True, "mkt-paid")]}}
    roas_ch = cartesian(
        "mkt-roas-by-channel", "ROAS by paid channel", MKT, f(MKT, "channel_name"),
        [(f(MKT, "roas"), "bar", 0)], horizontal=True, sort_by=(f(MKT, "roas"), True), filters=paid,
        description="Net revenue from customers first acquired by the channel / that channel's spend.")
    spend_ch = cartesian(
        "mkt-spend-by-channel", "Marketing spend by channel", MKT, f(MKT, "channel_name"),
        [(f(MKT, "ad_spend"), "bar", 0)], horizontal=True, sort_by=(f(MKT, "ad_spend"), True), filters=paid)
    rev_acq = cartesian(
        "mkt-net-revenue-by-acquisition", "Net revenue by acquisition channel", MKT, f(MKT, "channel_name"),
        [(f(MKT, "net_revenue"), "bar", 0)], horizontal=True, sort_by=(f(MKT, "net_revenue"), True),
        description="Includes organic and anonymous (walk-in) sales, which no channel can claim.")
    spend_trend = cartesian(
        "mkt-spend-and-roas-by-month", "Spend and ROAS by month", MKT, month(MKT),
        [(f(MKT, "ad_spend"), "bar", 0), (f(MKT, "roas"), "line", 1)])
    orders_trend = cartesian(
        "mkt-online-orders-by-month", "Online orders and delivery time by month", ONLINE, month(ONLINE),
        [(f(ONLINE, "online_orders"), "bar", 0), (f(ONLINE, "average_delivery_hours"), "line", 1)])
    orders_ch = cartesian(
        "mkt-online-orders-by-channel", "Online orders: web vs app", ONLINE, f("dim_channel", "channel_name"),
        [(f(ONLINE, "online_orders"), "bar", 0)], horizontal=True, sort_by=(f(ONLINE, "online_orders"), True))
    charts = [*kpis, roas_ch, spend_ch, rev_acq, spend_trend, orders_trend, orders_ch]
    tiles = [
        *kpi_row(kpis),
        tile(roas_ch, 0, 4, 12, 9), tile(spend_ch, 12, 4, 12, 9),
        tile(spend_trend, 0, 13, 12, 9), tile(rev_acq, 12, 13, 12, 9),
        tile(orders_trend, 0, 22, 12, 9), tile(orders_ch, 12, 22, 12, 9),
        note("ROAS is first-touch: a customer's lifetime net revenue counts for the channel that "
             "acquired them, so it runs high next to platform-reported ROAS. **Active customers "
             "(90 days)** is a rolling count with no pre-aggregated form; query it with "
             "`mf query --metrics active_customers --group-by metric_time__month`.",
             0, 31, 24, 3, "About these numbers"),
    ]
    return charts, dashboard("marketing-and-customers", "Marketing & customers",
                             "Spend, return on spend and the online store.", tiles)


def main() -> None:
    for sub in ("charts", "dashboards"):
        shutil.rmtree(CONTENT / sub, ignore_errors=True)
        (CONTENT / sub).mkdir(parents=True)
    (CONTENT / "spaces").mkdir(parents=True, exist_ok=True)
    (CONTENT / "spaces" / f"{SPACE}.space.yml").write_text(
        yaml.safe_dump({"contentType": "space", "slug": SPACE, "spaceName": "Gulf Retail"}, sort_keys=False),
        encoding="utf-8", newline="\n")
    n = 0
    for build in (executive, merchandising, marketing):
        charts, dash = build()
        for ch in charts:
            (CONTENT / "charts" / f"{ch['slug']}.yml").write_text(
                yaml.safe_dump(ch, sort_keys=True, allow_unicode=True), encoding="utf-8", newline="\n")
        (CONTENT / "dashboards" / f"{dash['slug']}.yml").write_text(
            yaml.safe_dump(dash, sort_keys=True, allow_unicode=True), encoding="utf-8", newline="\n")
        n += len(charts)
        print(f"{dash['name']}: {len(charts)} charts")
    print(f"wrote {n} charts and 3 dashboards to {CONTENT}")


if __name__ == "__main__":
    main()
