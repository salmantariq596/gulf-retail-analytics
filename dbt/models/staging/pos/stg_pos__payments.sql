with

source as (
    select * from {{ source('pos', 'payments') }}
),

renamed as (
    select
        payment_id,
        sale_id,
        lower(payment_method) as payment_method,
        amount as amount_local,
        upper(currency_code) as currency_code,
        {{ to_utc('paid_at') }} as paid_at
    from source
)

select * from renamed
