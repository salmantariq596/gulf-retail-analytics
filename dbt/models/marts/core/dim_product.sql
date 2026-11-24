-- One row per product version (SCD2). Facts link to the version valid on the
-- business date of the event, so an old sale keeps the cost it had at the time.
with

versions as (
    select * from {{ ref('int_products_versioned') }}
    where not is_test_sku
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['sku', 'valid_from']) }} as product_key,
        sku,
        product_name_en,
        product_name_ar,
        category,
        subcategory,
        brand,
        unit_cost_aed,
        list_price_aed,
        cast(
            round((list_price_aed - unit_cost_aed) / nullif(list_price_aed, 0), 4) as decimal(9, 4)
        ) as list_margin_pct,
        case
            when list_price_aed < 100 then '1. under 100'
            when list_price_aed < 500 then '2. 100-499'
            when list_price_aed < 2000 then '3. 500-1,999'
            when list_price_aed < 5000 then '4. 2,000-4,999'
            else '5. 5,000+'
        end as price_band,
        is_active,
        launched_on,
        cast(version_number as integer) as version_number,
        changed_on,
        valid_from,
        valid_to,
        is_current
    from versions
)

select * from final
