-- One row per ad campaign. Platforms let marketers rename campaigns at any time,
-- so the name is the latest one seen; the id is the stable key.
with

spend as (
    select * from {{ ref('int_marketing_spend_latest') }}
),

channels as (
    select * from {{ ref('marketing_channels') }}
),

latest_name as (
    select
        campaign_id,
        campaign_name,
        row_number() over (partition by campaign_id order by spend_date desc, latest_file_date desc) as recency
    from spend
),

activity as (
    select
        campaign_id,
        min(marketing_channel) as marketing_channel,
        min(country_code) as country_code,
        min(spend_date) as first_spend_date,
        max(spend_date) as last_spend_date
    from spend
    group by campaign_id
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['activity.campaign_id']) }} as campaign_key,
        activity.campaign_id,
        latest_name.campaign_name,
        activity.marketing_channel,
        channels.channel_name as marketing_channel_name,
        channels.channel_type as marketing_channel_type,
        channels.is_paid,
        activity.country_code,
        latest_name.campaign_name like '%Always-on%' as is_always_on,
        activity.first_spend_date,
        activity.last_spend_date
    from activity
    inner join latest_name
        on
            activity.campaign_id = latest_name.campaign_id
            and latest_name.recency = 1
    inner join channels on activity.marketing_channel = channels.marketing_channel
)

select * from final
