-- Every sale line must point to the product version that was valid on its business
-- date - not just to some version of the same SKU. A relationships test only proves
-- the key exists; this proves it is the right one.
select
    sales.sales_line_id,
    sales.business_date,
    products.sku,
    products.valid_from,
    products.valid_to
from {{ ref('fct_sales_lines') }} as sales
inner join {{ ref('dim_product') }} as products on sales.product_key = products.product_key
where
    cast(sales.business_date as timestamp) < products.valid_from
    or cast(sales.business_date as timestamp) >= products.valid_to
