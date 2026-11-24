with

source as (
    select * from {{ source('pos', 'promotions') }}
),

renamed as (
    select
        promotion_id,
        upper(promotion_code) as promotion_code,
        promotion_name,
        lower(discount_type) as discount_type,
        discount_value,
        starts_on,
        ends_on,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
