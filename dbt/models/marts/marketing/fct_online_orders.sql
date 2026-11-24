{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='order_id',
        on_schema_change='append_new_columns'
    )
}}

-- Grain: one online order.
-- Accumulating snapshot: the row is updated in place as the order moves through
-- placed -> paid -> shipped -> delivered (or cancelled), with one date per milestone
-- and the lag between them. Incremental runs only reprocess orders with new events.
with

orders as (
    select * from {{ ref('stg_online__orders') }}
),

milestones as (
    select * from {{ ref('int_online_order_milestones') }}
    -- only orders with an event since the last load (minus the lookback window)
    where {{ incremental_lookback('last_event_published_at') }}
),

lines as (
    select * from {{ ref('stg_online__order_lines') }}
),

countries as (
    select * from {{ ref('countries') }}
),

vat as (
    select * from {{ ref('vat_rates') }}
),

fx as (
    select * from {{ ref('currency_rates') }}
),

identity as (
    select * from {{ ref('int_customer_identity_map') }}
),

stores as (
    select * from {{ ref('dim_store') }}
),

customers as (
    select * from {{ ref('dim_customer') }}
),

channels as (
    select * from {{ ref('dim_channel') }}
),

order_lines as (
    select
        order_record_id,
        count(*) as line_count,
        sum(quantity) as units,
        sum(line_total_incl_vat) as order_total_incl_vat_local
    from lines
    group by order_record_id
),

enriched as (
    select
        orders.order_id,
        orders.ship_country_code,
        orders.currency_code,
        orders.sales_channel,
        orders.payment_method,
        orders.promotion_code,
        orders.order_status as current_status,
        identity.customer_id,
        milestones.placed_at,
        milestones.paid_at,
        milestones.shipped_at,
        milestones.delivered_at,
        milestones.cancelled_at,
        milestones.last_event_published_at,
        milestones.hours_placed_to_paid,
        milestones.hours_placed_to_shipped,
        milestones.hours_shipped_to_delivered,
        milestones.hours_placed_to_delivered,
        order_lines.line_count,
        order_lines.units,
        order_lines.order_total_incl_vat_local,
        countries.utc_offset_hours,
        {{ business_date('milestones.placed_at', 'countries.utc_offset_hours') }} as placed_date,
        vat.vat_rate,
        fx.aed_per_unit
    from milestones
    inner join orders on milestones.order_id = orders.order_id
    inner join order_lines on orders.order_record_id = order_lines.order_record_id
    inner join countries on orders.ship_country_code = countries.country_code
    inner join vat
        on
            orders.ship_country_code = vat.country_code
            and {{ business_date('milestones.placed_at', 'countries.utc_offset_hours') }}
            between vat.valid_from and vat.valid_to
    inner join fx
        on
            orders.currency_code = fx.currency_code
            and {{ business_date('milestones.placed_at', 'countries.utc_offset_hours') }}
            between fx.valid_from and fx.valid_to
    left join identity
        on
            identity.source_system = 'online'
            and orders.online_customer_id = identity.source_customer_id
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['enriched.order_id']) }} as order_key,
        enriched.order_id,
        stores.store_key,
        coalesce(customers.customer_key, '-1') as customer_key,
        channels.channel_key,

        {%- for milestone in ['placed', 'paid', 'shipped', 'delivered', 'cancelled'] %}
            {%- set local_date = business_date('enriched.' ~ milestone ~ '_at', 'enriched.utc_offset_hours') %}
            cast(
                extract(year from {{ local_date }}) * 10000
                + extract(month from {{ local_date }}) * 100
                + extract(day from {{ local_date }}) as integer
            ) as {{ milestone }}_date_key,
        {%- endfor %}

        enriched.placed_date,
        enriched.placed_at,
        enriched.paid_at,
        enriched.shipped_at,
        enriched.delivered_at,
        enriched.cancelled_at,
        enriched.last_event_published_at,
        enriched.current_status,
        enriched.cancelled_at is not null as is_cancelled,
        enriched.delivered_at is not null as is_delivered,
        enriched.payment_method,
        enriched.payment_method = 'cod' as is_cash_on_delivery,
        enriched.promotion_code,
        enriched.ship_country_code,
        enriched.currency_code,

        enriched.line_count,
        enriched.units,
        {{ money('enriched.order_total_incl_vat_local') }} as order_total_incl_vat_local,
        {{ to_aed('enriched.order_total_incl_vat_local', 'enriched.aed_per_unit') }} as order_total_incl_vat_aed,
        {{ to_aed(excl_vat('enriched.order_total_incl_vat_local', 'enriched.vat_rate'), 'enriched.aed_per_unit') }}
            as order_total_excl_vat_aed,

        enriched.hours_placed_to_paid,
        enriched.hours_placed_to_shipped,
        enriched.hours_shipped_to_delivered,
        enriched.hours_placed_to_delivered
    from enriched
    inner join stores
        on
            'ONL-' || enriched.ship_country_code = stores.store_code
            and enriched.placed_at >= stores.valid_from
            and enriched.placed_at < stores.valid_to
    left join customers
        on
            enriched.customer_id = customers.customer_id
            and enriched.placed_at >= customers.valid_from
            and enriched.placed_at < customers.valid_to
    inner join channels on enriched.sales_channel = channels.channel_code
)

select * from final
