-- Grain: one row per PO line per event. A line appears once in the file of the day it
-- was ordered (received_on empty) and again in the file of the day it was received.
with

source as (
    select * from {{ source('erp', 'purchase_orders') }}
),

renamed as (
    select
        po_number,
        upper(trim(store_code)) as store_code,
        upper(trim(sku)) as sku,
        cast(qty_ordered as integer) as qty_ordered,
        cast(ordered_on as date) as ordered_on,
        cast(expected_on as date) as expected_on,
        cast(received_on as date) as received_on,
        case when received_on is null then 'ordered' else 'received' end as po_line_event,
        cast(unit_cost as decimal(18, 2)) as unit_cost,
        upper(currency_code) as currency_code,
        _file_name as source_file,
        cast(_file_date as date) as file_date
    from source
)

select * from renamed
