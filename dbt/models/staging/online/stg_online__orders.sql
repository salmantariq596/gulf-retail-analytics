with

source as (
    select * from {{ source('online', 'orders') }}
),

renamed as (
    select
        order_id,
        customer_id as online_customer_id,
        lower(channel) as sales_channel,
        upper(ship_country) as ship_country_code,
        upper(currency) as currency_code,
        lower(payment_method) as payment_method,
        nullif(upper(trim(promotion_code)), '') as promotion_code,
        -- furthest lifecycle stage reached; use stg_online__order_events for timings
        lower(status) as order_status,
        {{ to_utc('placed_at') }} as placed_at,
        {{ to_utc('updated_at') }} as updated_at,
        -- dlt row id: the key order lines point to (see stg_online__order_lines)
        _dlt_id as order_record_id
    from source
)

select * from renamed
