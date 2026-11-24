-- Grain: one row per (spend date, campaign, country) per export file. Restated days
-- appear in up to three files; latest-file-wins happens in the intermediate layer.
with

source as (
    select * from {{ source('marketing', 'spend') }}
),

renamed as (
    select
        cast(date as date) as spend_date,
        campaign_id,
        campaign_name,
        lower(marketing_channel) as marketing_channel,
        upper(country_code) as country_code,
        upper(currency_code) as currency_code,
        cast(spend as decimal(18, 2)) as spend_local,
        cast(impressions as bigint) as impressions,
        cast(clicks as bigint) as clicks,
        _file_name as source_file,
        cast(_file_date as date) as file_date
    from source
)

select * from renamed
