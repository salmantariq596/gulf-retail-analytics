with

source as (
    select * from {{ source('pos', 'customers') }}
),

renamed as (
    select
        customer_id as pos_customer_id,
        upper(trim(loyalty_number)) as loyalty_number,
        first_name,
        last_name,
        first_name_ar,
        last_name_ar,
        lower(trim(email)) as email,
        phone,
        upper(country_code) as country_code,
        home_store_id,
        lower(loyalty_tier) as loyalty_tier,
        lower(acquisition_channel) as acquisition_channel,
        {{ to_utc('created_at') }} as created_at,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
