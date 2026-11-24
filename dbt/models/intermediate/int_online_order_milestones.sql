-- One row per order with the time each lifecycle milestone was first reached,
-- built from the event history (never from orders.status: cash-on-delivery orders
-- are paid after they are delivered). Lags are in hours.
with

events as (
    select * from {{ ref('stg_online__order_events') }}
),

milestones as (
    select
        order_id,
        min(case when event_status = 'placed' then event_at end) as placed_at,
        min(case when event_status = 'paid' then event_at end) as paid_at,
        min(case when event_status = 'shipped' then event_at end) as shipped_at,
        min(case when event_status = 'delivered' then event_at end) as delivered_at,
        min(case when event_status = 'cancelled' then event_at end) as cancelled_at,
        max(published_at) as last_event_published_at
    from events
    group by order_id
),

final as (
    select
        *,
        {{ hours_between('placed_at', 'paid_at') }} as hours_placed_to_paid,
        {{ hours_between('placed_at', 'shipped_at') }} as hours_placed_to_shipped,
        {{ hours_between('shipped_at', 'delivered_at') }} as hours_shipped_to_delivered,
        {{ hours_between('placed_at', 'delivered_at') }} as hours_placed_to_delivered
    from milestones
)

select * from final
