with

source as (
    select * from {{ source('online', 'customers') }}
),

renamed as (
    select
        online_customer_id,
        lower(trim(email)) as email,
        first_name,
        last_name,
        nullif(upper(trim(loyalty_number)), '') as loyalty_number,
        upper(country_code) as country_code,
        lower(acquisition_channel) as acquisition_channel,
        {{ to_utc('created_at') }} as created_at,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
