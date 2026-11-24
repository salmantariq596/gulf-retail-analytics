-- Till restarts re-send lines: same (sale_id, line_number), new sale_line_id, a few
-- seconds later. Keep the first copy. assert_pos_sale_total_matches_lines proves
-- that one copy per line number reconciles to the receipt total.
with

lines as (
    select * from {{ ref('stg_pos__sale_lines') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by sale_id, line_number
            order by created_at, sale_line_id
        ) as copy_number
    from lines
)

select
    sale_line_id,
    sale_id,
    line_number,
    sku,
    quantity,
    unit_price_incl_vat,
    discount_incl_vat,
    promotion_id,
    line_total_incl_vat,
    is_test_sku,
    created_at
from ranked
where copy_number = 1
