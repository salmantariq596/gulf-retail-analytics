-- Online order lines with their order attached (dlt stores lines in a child table
-- keyed by the parent's row id). Cancelled orders are not sales (they are cancelled
-- within 48h, before shipping) and are removed. Each order belongs to the virtual
-- online store of its ship-to country (ONL-AE / ONL-SA / ONL-QA).
with

lines as (
    select * from {{ ref('stg_online__order_lines') }}
),

orders as (
    select * from {{ ref('stg_online__orders') }}
),

stores as (
    select * from {{ ref('stg_pos__stores') }}
),

joined as (
    select
        'online' as source_system,
        orders.order_id as transaction_id,
        lines.line_number,
        lines.order_line_record_id as source_line_id,
        stores.store_id,
        orders.ship_country_code as country_code,
        orders.sales_channel,
        cast(null as bigint) as pos_customer_id,
        orders.online_customer_id,
        lines.sku,
        orders.promotion_code,
        orders.currency_code,
        orders.placed_at as sold_at,
        lines.quantity,
        lines.unit_price_incl_vat,
        lines.discount_incl_vat,
        lines.line_total_incl_vat
    from lines
    inner join orders on lines.order_record_id = orders.order_record_id
    inner join stores on 'ONL-' || orders.ship_country_code = stores.store_code
    where orders.order_status != 'cancelled'
)

select * from joined
