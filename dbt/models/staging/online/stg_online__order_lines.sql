-- dlt unnests the `lines` array into a child table that carries the parent's row id
-- (_dlt_root_id), not order_id. Staging stays join-free: order_id is attached in
-- the intermediate layer via order_record_id.
with

source as (
    select * from {{ source('online', 'orders__lines') }}
),

renamed as (
    select
        _dlt_id as order_line_record_id,
        _dlt_root_id as order_record_id,
        line_number,
        upper(trim(sku)) as sku,
        quantity,
        cast(unit_price_incl_vat as decimal(12, 2)) as unit_price_incl_vat,
        cast(discount_incl_vat as decimal(12, 2)) as discount_incl_vat,
        cast(quantity * unit_price_incl_vat - discount_incl_vat as decimal(12, 2)) as line_total_incl_vat
    from source
)

select * from renamed
