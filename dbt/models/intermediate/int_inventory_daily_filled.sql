-- A complete daily stock series per store x SKU. About 1% of daily ERP files never
-- arrive: on those days the last known stock is carried forward and flagged
-- (is_imputed). Negative stock from ERP sync errors is floored at zero and flagged.
{%- set fill_window = 'partition by store_code, sku order by snapshot_date
    rows between unbounded preceding and current row' %}

with

stock as (
    select * from {{ ref('stg_erp__stock_on_hand') }}
),

calendar as (
    select date_day from {{ ref('dim_date') }}
),

pairs as (
    select
        store_code,
        sku,
        min(snapshot_date) as first_seen_on,
        max(snapshot_date) as last_seen_on
    from stock
    group by store_code, sku
),

grid as (
    select
        pairs.store_code,
        pairs.sku,
        calendar.date_day as snapshot_date
    from pairs
    inner join calendar
        on calendar.date_day between pairs.first_seen_on and pairs.last_seen_on
),

joined as (
    select
        grid.store_code,
        grid.sku,
        grid.snapshot_date,
        stock.qty_on_hand,
        stock.qty_on_order,
        stock.snapshot_date is null as is_imputed
    from grid
    left join stock
        on
            grid.store_code = stock.store_code
            and grid.sku = stock.sku
            and grid.snapshot_date = stock.snapshot_date
),

filled as (
    select
        store_code,
        sku,
        snapshot_date,
        is_imputed,
        {{ last_value_ignore_nulls('qty_on_hand', fill_window) }} as qty_on_hand_reported,
        {{ last_value_ignore_nulls('qty_on_order', fill_window) }} as qty_on_order
    from joined
)

select
    store_code,
    sku,
    snapshot_date,
    is_imputed,
    qty_on_hand_reported,
    qty_on_hand_reported < 0 as is_negative_reported,
    greatest(qty_on_hand_reported, 0) as qty_on_hand,
    qty_on_order
from filled
