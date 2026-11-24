-- One row per customer version (SCD2).
--   * loyalty members: versioned from snap_customers (tier, home store changes)
--   * online-only accounts: one version (the online platform has no tier)
--   * one 'unknown' member (key '-1') for anonymous walk-in and guest sales
-- No names, emails or phone numbers: the marts carry no direct PII.
with

snapshot as (
    select * from {{ ref('snap_customers') }}
),

online_customers as (
    select * from {{ ref('stg_online__customers') }}
),

identity as (
    select * from {{ ref('int_customer_identity_map') }}
),

sales as (
    select * from {{ ref('int_sales_lines_enriched') }}
),

online_links as (
    select distinct loyalty_number
    from online_customers
    where loyalty_number is not null
),

first_purchases as (
    select
        customer_id,
        min(business_date) as first_purchase_date
    from sales
    where customer_id is not null
    group by customer_id
),

loyalty_versions as (
    select
        'L-' || snapshot.loyalty_number as customer_id,
        'loyalty' as customer_type,
        snapshot.loyalty_number,
        snapshot.country_code,
        snapshot.home_store_id,
        snapshot.loyalty_tier,
        snapshot.acquisition_channel,
        cast(snapshot.created_at as date) as customer_since,
        true as is_loyalty_member,
        online_links.loyalty_number is not null as has_online_account,
        {{ open_valid_from('snapshot.dbt_valid_from', 'snapshot.pos_customer_id') }} as valid_from,
        cast(snapshot.dbt_valid_to as timestamp) as valid_to
    from snapshot
    left join online_links on snapshot.loyalty_number = online_links.loyalty_number
),

online_only as (
    select
        identity.customer_id,
        'online_only' as customer_type,
        cast(null as varchar) as loyalty_number,
        online_customers.country_code,
        cast(null as bigint) as home_store_id,
        'none' as loyalty_tier,
        online_customers.acquisition_channel,
        cast(online_customers.created_at as date) as customer_since,
        false as is_loyalty_member,
        true as has_online_account,
        cast('{{ var("scd_start") }}' as timestamp) as valid_from,
        {{ scd_end() }} as valid_to
    from online_customers
    inner join identity
        on
            identity.source_system = 'online'
            and online_customers.online_customer_id = identity.source_customer_id
    where identity.customer_id like 'O-%'
),

customers as (
    select * from loyalty_versions
    union all
    select * from online_only
),

known as (
    select
        {{ dbt_utils.generate_surrogate_key(['customers.customer_id', 'customers.valid_from']) }} as customer_key,
        customers.customer_id,
        customers.customer_type,
        customers.loyalty_number,
        customers.country_code,
        customers.home_store_id,
        customers.loyalty_tier,
        customers.acquisition_channel,
        customers.customer_since,
        first_purchases.first_purchase_date,
        customers.is_loyalty_member,
        customers.has_online_account,
        customers.valid_from,
        customers.valid_to,
        customers.valid_to = {{ scd_end() }} as is_current
    from customers
    left join first_purchases on customers.customer_id = first_purchases.customer_id
),

unknown_member as (
    select
        '-1' as customer_key,
        'UNKNOWN' as customer_id,
        'anonymous' as customer_type,
        cast(null as varchar) as loyalty_number,
        cast(null as varchar) as country_code,
        cast(null as bigint) as home_store_id,
        'none' as loyalty_tier,
        'unknown' as acquisition_channel,
        cast(null as date) as customer_since,
        cast(null as date) as first_purchase_date,
        false as is_loyalty_member,
        false as has_online_account,
        cast('{{ var("scd_start") }}' as timestamp) as valid_from,
        {{ scd_end() }} as valid_to,
        true as is_current
)

select * from known
union all
select * from unknown_member
