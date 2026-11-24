with

source as (
    select * from {{ source('pos', 'return_lines') }}
),

renamed as (
    select
        return_line_id,
        return_id,
        original_sale_line_id,
        upper(trim(sku)) as sku,
        quantity,
        refund_incl_vat,
        {{ to_utc('created_at') }} as created_at
    from source
)

select * from renamed
