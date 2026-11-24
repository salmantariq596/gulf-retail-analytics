-- Phase 3 checkpoint, as a test: every sale line must carry the unit cost of the
-- product version that was valid on its business date - not the current cost.
-- Returns lines where the cost differs from the matching dim_product version.
with

sales as (
    select * from {{ ref('int_sales_lines_enriched') }}
),

products as (
    select * from {{ ref('dim_product') }}
)

select
    sales.sales_line_id,
    sales.sku,
    sales.business_date,
    sales.unit_cost_aed as cost_on_line,
    products.unit_cost_aed as cost_valid_that_day
from sales
inner join products
    on
        sales.sku = products.sku
        and cast(sales.business_date as timestamp) >= products.valid_from
        and cast(sales.business_date as timestamp) < products.valid_to
where sales.unit_cost_aed != products.unit_cost_aed
