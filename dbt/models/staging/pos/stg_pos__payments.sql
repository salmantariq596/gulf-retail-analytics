with

source as (
    select * from {{ source('pos', 'payments') }}
    -- loads are at-least-once: drop a row re-delivered at an incremental boundary
    qualify row_number() over (partition by payment_id order by payment_id) = 1
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
