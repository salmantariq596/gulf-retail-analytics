-- One customer, two systems: the loyalty number links a POS member to their online
-- account. Unified customer_id:
--   L-<loyalty_number>        loyalty members (with or without an online account)
--   O-<online_customer_id>    online-only accounts
with

pos_customers as (
    select * from {{ ref('stg_pos__customers') }}
),

online_customers as (
    select * from {{ ref('stg_online__customers') }}
),

pos_ids as (
    select
        'pos' as source_system,
        cast(pos_customer_id as varchar) as source_customer_id,
        'L-' || loyalty_number as customer_id
    from pos_customers
),

online_ids as (
    select
        'online' as source_system,
        online_customers.online_customer_id as source_customer_id,
        case
            when pos_customers.loyalty_number is not null then 'L-' || pos_customers.loyalty_number
            else 'O-' || online_customers.online_customer_id
        end as customer_id
    from online_customers
    left join pos_customers on online_customers.loyalty_number = pos_customers.loyalty_number
)

select * from pos_ids
union all
select * from online_ids
