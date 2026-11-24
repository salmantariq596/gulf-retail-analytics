-- One row per store version (SCD2 from snap_stores). Includes the three virtual
-- online stores, so country, currency and VAT work the same for every channel.
with

snapshot as (
    select * from {{ ref('snap_stores') }}
),

countries as (
    select * from {{ ref('countries') }}
),

versions as (
    select
        {{ dbt_utils.generate_surrogate_key(['snapshot.store_id', 'snapshot.dbt_valid_from']) }} as store_key,
        snapshot.store_id,
        snapshot.store_code,
        snapshot.store_name_en,
        snapshot.store_name_ar,
        snapshot.country_code,
        countries.country_name_en as country_name,
        snapshot.city,
        snapshot.store_format,
        snapshot.is_online_store,
        snapshot.currency_code,
        snapshot.store_timezone,
        snapshot.opened_on,
        snapshot.closed_on,
        {{ open_valid_from('snapshot.dbt_valid_from', 'snapshot.store_id') }} as valid_from,
        cast(snapshot.dbt_valid_to as timestamp) as valid_to
    from snapshot
    inner join countries on snapshot.country_code = countries.country_code
)

select
    *,
    valid_to = {{ scd_end() }} as is_current
from versions
