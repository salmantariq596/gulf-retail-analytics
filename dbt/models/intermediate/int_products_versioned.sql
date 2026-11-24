-- SCD Type 2 product versions derived from the catalog export history.
-- The catalog has no reliable updated_at, so a change is detected by comparing each
-- export with the previous one (the "check" strategy), and the export date is the
-- date the change took effect. Because raw keeps every export, this can be rebuilt
-- from scratch at any time - there is no snapshot state to lose.
with

exports as (
    select * from {{ ref('stg_catalog__products') }}
),

hashed as (
    select
        *,
        {{ dbt_utils.generate_surrogate_key([
            'product_name_en', 'product_name_ar', 'category', 'subcategory', 'brand',
            'unit_cost_aed', 'list_price_aed', 'is_active'
        ]) }} as attributes_hash
    from exports
),

compared as (
    select
        *,
        lag(attributes_hash) over (partition by sku order by export_date) as previous_hash
    from hashed
),

changes as (
    select * from compared
    where previous_hash is null or previous_hash != attributes_hash
),

versioned as (
    select
        sku,
        product_name_en,
        product_name_ar,
        category,
        subcategory,
        brand,
        unit_cost_aed,
        list_price_aed,
        is_active,
        launched_on,
        is_test_sku,
        export_date as changed_on,
        row_number() over (partition by sku order by export_date) as version_number,
        {{ open_valid_from('export_date', 'sku') }} as valid_from,
        coalesce(
            cast(lead(export_date) over (partition by sku order by export_date) as timestamp),
            {{ scd_end() }}
        ) as valid_to
    from changes
)

select
    *,
    valid_to = {{ scd_end() }} as is_current
from versioned
