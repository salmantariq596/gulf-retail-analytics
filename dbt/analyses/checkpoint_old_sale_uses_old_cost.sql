-- Phase 3 checkpoint: "show a product whose cost changed, and prove an old sale uses
-- the old cost". Compile with `dbt compile -s checkpoint_old_sale_uses_old_cost` and
-- run the SQL in target/compiled/, or use `dbt show`.
--
-- Picks the best-selling SKU whose unit cost changed, then shows, per product version,
-- the cost on that version and the cost actually carried by the sales in that window.
with

versions as (
    select * from {{ ref('dim_product') }}
),

sales as (
    select * from {{ ref('int_sales_lines_enriched') }}
),

cost_changes as (
    select sku
    from versions
    group by sku
    having count(distinct unit_cost_aed) > 1
),

top_sku as (
    select sales.sku
    from sales
    inner join cost_changes on sales.sku = cost_changes.sku
    group by sales.sku
    order by count(*) desc
    limit 1
)

select
    versions.sku,
    versions.version_number,
    versions.changed_on,
    versions.valid_from,
    versions.valid_to,
    versions.unit_cost_aed as version_cost_aed,
    versions.list_price_aed as version_list_price_aed,
    count(sales.sales_line_id) as sales_lines_in_window,
    min(sales.business_date) as first_sale,
    max(sales.business_date) as last_sale,
    min(sales.unit_cost_aed) as min_cost_on_sales,
    max(sales.unit_cost_aed) as max_cost_on_sales
from versions
inner join top_sku on versions.sku = top_sku.sku
left join sales
    on
        versions.sku = sales.sku
        and cast(sales.business_date as timestamp) >= versions.valid_from
        and cast(sales.business_date as timestamp) < versions.valid_to
group by all
order by versions.version_number
