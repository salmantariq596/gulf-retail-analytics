-- Raw file columns are text; this is where they get their types.
with

source as (
    select * from {{ source('erp', 'stock_on_hand') }}
),

renamed as (
    select
        cast(snapshot_date as date) as snapshot_date,
        upper(trim(store_code)) as store_code,
        upper(trim(sku)) as sku,
        cast(qty_on_hand as integer) as qty_on_hand,
        cast(qty_on_order as integer) as qty_on_order,
        _file_name as source_file,
        cast(_file_date as date) as file_date
    from source
)

select * from renamed
