with

source as (
    select * from {{ source('online', 'order_events') }}
),

renamed as (
    select
        event_id,
        order_id,
        lower(status) as event_status,
        {{ to_utc('event_at') }} as event_at,
        -- when the event became visible in the API (later than event_at for late orders)
        {{ to_utc('updated_at') }} as published_at
    from source
)

select * from renamed
