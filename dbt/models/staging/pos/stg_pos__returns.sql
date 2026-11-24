with

source as (
    select * from {{ source('pos', 'returns') }}
),

renamed as (
    select
        return_id,
        store_id,
        cashier_id,
        customer_id as pos_customer_id,
        original_sale_id,
        original_online_order_id,
        original_sale_id is not null as has_store_receipt,
        original_online_order_id is not null as is_online_order_return,
        upper(currency_code) as currency_code,
        lower(reason_code) as reason_code,
        {{ to_utc('returned_at') }} as returned_at,
        {{ to_utc('created_at') }} as created_at,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
