-- Grain: one row per line as received from the till, INCLUDING re-sent duplicates
-- (same sale_id + line_number, new sale_line_id). Deduplication is business logic
-- and happens in int_pos_sale_lines_deduped.
with

source as (
    select * from {{ source('pos', 'sale_lines') }}
),

renamed as (
    select
        sale_line_id,
        sale_id,
        line_number,
        upper(trim(sku)) as sku,
        quantity,
        unit_price_incl_vat,
        discount_incl_vat,
        promotion_id,
        line_total_incl_vat,
        upper(trim(sku)) = '{{ var("test_sku") }}' as is_test_sku,
        {{ to_utc('created_at') }} as created_at
    from source
)

select * from renamed
