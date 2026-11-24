with

source as (
    select * from {{ source('pos', 'sales') }}
),

renamed as (
    select
        sale_id,
        receipt_number,
        store_id,
        register_no,
        cashier_id,
        customer_id as pos_customer_id,
        upper(currency_code) as currency_code,
        total_incl_vat,
        lower(status) as sale_status,
        lower(status) = 'voided' as is_voided,
        {{ to_utc('sold_at') }} as sold_at,
        {{ to_utc('created_at') }} as created_at,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
