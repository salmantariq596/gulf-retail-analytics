with

source as (
    select * from {{ source('pos', 'stores') }}
),

renamed as (
    select
        store_id,
        store_code,
        store_name_en,
        store_name_ar,
        upper(country_code) as country_code,
        city,
        lower(store_format) as store_format,
        lower(store_format) = 'online' as is_online_store,
        upper(currency_code) as currency_code,
        timezone as store_timezone,
        opened_on,
        closed_on,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
