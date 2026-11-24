-- Grain: one row per SKU per daily export. The full history of exports is kept
-- here; the SCD2 snapshot (Phase 3) turns it into product versions.
with

source as (
    select * from {{ source('catalog', 'products') }}
),

renamed as (
    select
        upper(trim(sku)) as sku,
        product_name_en,
        product_name_ar,
        category,
        subcategory,
        brand,
        cast(unit_cost_aed as decimal(18, 2)) as unit_cost_aed,
        -- list price is in AED and EXCLUDES VAT (shelf prices are derived per country)
        cast(list_price_aed as decimal(18, 2)) as list_price_aed,
        cast(is_active as boolean) as is_active,
        cast(launched_on as date) as launched_on,
        upper(trim(sku)) = '{{ var("test_sku") }}' as is_test_sku,
        cast(export_date as date) as export_date,
        _file_name as source_file
    from source
)

select * from renamed
