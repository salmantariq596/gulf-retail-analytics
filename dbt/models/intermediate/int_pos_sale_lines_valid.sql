-- POS lines that represent real business: completed sales, rung up by a real
-- cashier, for a real product. Training-mode sales, voided receipts and the till
-- test SKU are removed here (staging only flags them).
with

lines as (
    select * from {{ ref('int_pos_sale_lines_deduped') }}
),

sales as (
    select * from {{ ref('stg_pos__sales') }}
),

cashiers as (
    select * from {{ ref('stg_pos__cashiers') }}
),

stores as (
    select * from {{ ref('stg_pos__stores') }}
),

promotions as (
    select * from {{ ref('stg_pos__promotions') }}
),

joined as (
    select
        'pos' as source_system,
        cast(lines.sale_id as varchar) as transaction_id,
        lines.line_number,
        cast(lines.sale_line_id as varchar) as source_line_id,
        sales.store_id,
        stores.country_code,
        'store' as sales_channel,
        sales.pos_customer_id,
        cast(null as varchar) as online_customer_id,
        lines.sku,
        promotions.promotion_code,
        sales.currency_code,
        sales.sold_at,
        lines.quantity,
        lines.unit_price_incl_vat,
        lines.discount_incl_vat,
        lines.line_total_incl_vat
    from lines
    inner join sales on lines.sale_id = sales.sale_id
    inner join cashiers on sales.cashier_id = cashiers.cashier_id
    inner join stores on sales.store_id = stores.store_id
    left join promotions on lines.promotion_id = promotions.promotion_id
    where
        not sales.is_voided
        and not cashiers.is_training_cashier
        and not lines.is_test_sku
)

select * from joined
