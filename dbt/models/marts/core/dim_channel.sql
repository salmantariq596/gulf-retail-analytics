-- Sales channel: where the sale happened. (How the customer was acquired is a
-- different question: see dim_campaign.marketing_channel and
-- dim_customer.acquisition_channel.)
with

channels as (
    select
        v.channel_code,
        v.channel_name,
        v.channel_group
    from (
        values
        ('store', 'In-store', 'offline'),
        ('web', 'Web', 'online'),
        ('app', 'Mobile app', 'online')
    ) as v (channel_code, channel_name, channel_group)
)

select
    {{ dbt_utils.generate_surrogate_key(['channel_code']) }} as channel_key,
    cast(channel_code as varchar) as channel_code,
    cast(channel_name as varchar) as channel_name,
    cast(channel_group as varchar) as channel_group
from channels
