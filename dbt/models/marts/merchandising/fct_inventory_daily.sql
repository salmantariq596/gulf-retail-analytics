{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='snapshot_date',
        on_schema_change='append_new_columns'
    )
}}

-- Grain: one product in one store on one day (end-of-day stock).
-- Periodic snapshot. SEMI-ADDITIVE: stock can be summed across stores and products,
-- never across days - use the period-end value or the daily average.
with

stock as (
    select * from {{ ref('int_inventory_daily_filled') }}
    where {{ incremental_lookback('snapshot_date') }}
),

stores as (
    select * from {{ ref('dim_store') }}
),

products as (
    select * from {{ ref('dim_product') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['stock.snapshot_date', 'stock.store_code', 'stock.sku']) }}
            as inventory_key,
        cast(
            extract(year from stock.snapshot_date) * 10000
            + extract(month from stock.snapshot_date) * 100
            + extract(day from stock.snapshot_date) as integer
        ) as date_key,
        stores.store_key,
        products.product_key,

        stock.snapshot_date,
        stock.store_code,
        stock.sku,

        stock.qty_on_hand,
        stock.qty_on_order,
        products.unit_cost_aed,
        {{ money('stock.qty_on_hand * products.unit_cost_aed') }} as stock_value_at_cost_aed,
        stock.qty_on_hand = 0 as is_out_of_stock,
        stock.is_imputed,
        stock.is_negative_reported,
        stock.qty_on_hand_reported
    from stock
    inner join stores
        on
            stock.store_code = stores.store_code
            and cast(stock.snapshot_date as timestamp) >= stores.valid_from
            and cast(stock.snapshot_date as timestamp) < stores.valid_to
    inner join products
        on
            stock.sku = products.sku
            and cast(stock.snapshot_date as timestamp) >= products.valid_from
            and cast(stock.snapshot_date as timestamp) < products.valid_to
)

select * from final
