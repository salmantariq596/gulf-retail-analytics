-- One row per promotion, plus a 'no promotion' member (key '-1') so sales lines
-- never carry a null promotion key.
with

promotions as (
    select * from {{ ref('stg_pos__promotions') }}
),

known as (
    select
        {{ dbt_utils.generate_surrogate_key(['promotion_code']) }} as promotion_key,
        promotion_code,
        promotion_name,
        discount_type,
        cast(discount_value as decimal(10, 2)) as discount_value,
        starts_on,
        ends_on,
        promotion_code in ('LOYALTY5', 'GIFT50') as is_always_on
    from promotions
),

no_promotion as (
    select
        '-1' as promotion_key,
        'NONE' as promotion_code,
        'No promotion' as promotion_name,
        'none' as discount_type,
        cast(0 as decimal(10, 2)) as discount_value,
        cast(null as date) as starts_on,
        cast(null as date) as ends_on,
        false as is_always_on
)

select * from known
union all
select * from no_promotion
