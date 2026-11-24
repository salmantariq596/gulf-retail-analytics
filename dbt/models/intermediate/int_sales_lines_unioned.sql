-- POS and online sales in one shape, ready for enrichment.
select * from {{ ref('int_pos_sale_lines_valid') }}
union all
select * from {{ ref('int_online_order_lines_valid') }}
