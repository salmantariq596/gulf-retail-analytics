-- Grain: one campaign on one marketing channel in one country on one day.
-- Transaction fact (daily). Latest platform restatement only; spend in AED.
with

spend as (
    select * from {{ ref('int_marketing_spend_latest') }}
),

campaigns as (
    select * from {{ ref('dim_campaign') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['spend.spend_date', 'spend.campaign_id', 'spend.country_code']) }}
            as marketing_spend_key,
        cast(
            extract(year from spend.spend_date) * 10000
            + extract(month from spend.spend_date) * 100
            + extract(day from spend.spend_date) as integer
        ) as date_key,
        campaigns.campaign_key,
        spend.spend_date,
        spend.marketing_channel,
        spend.country_code,
        spend.currency_code,
        spend.spend_local,
        spend.spend_aed,
        spend.impressions,
        spend.clicks
    from spend
    inner join campaigns on spend.campaign_id = campaigns.campaign_id
)

select * from final
