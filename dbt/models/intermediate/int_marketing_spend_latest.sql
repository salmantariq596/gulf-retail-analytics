-- Ad platforms restate the previous two days in every export: the latest file wins.
-- Spend is converted to AED (platform accounts bill in USD, AED or SAR).
with

spend as (
    select * from {{ ref('stg_marketing__spend') }}
),

fx as (
    select * from {{ ref('currency_rates') }}
),

latest as (
    select
        *,
        row_number() over (
            partition by spend_date, campaign_id, country_code
            order by file_date desc
        ) as version_rank
    from spend
),

final as (
    select
        latest.spend_date,
        latest.campaign_id,
        latest.campaign_name,
        latest.marketing_channel,
        latest.country_code,
        latest.currency_code,
        latest.spend_local,
        {{ to_aed('latest.spend_local', 'fx.aed_per_unit') }} as spend_aed,
        latest.impressions,
        latest.clicks,
        latest.file_date as latest_file_date
    from latest
    inner join fx
        on
            latest.currency_code = fx.currency_code
            and latest.spend_date between fx.valid_from and fx.valid_to
    where latest.version_rank = 1
)

select * from final
