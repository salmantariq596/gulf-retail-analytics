-- Net revenue (gross - discounts - returns) for a store-month should never be
-- negative: a store cannot refund more than it sells in a month unless refunds are
-- double-counted or booked to the wrong store. A store's closing month is the one
-- legitimate exception (returns keep arriving after the last sale), so stores are
-- only checked while they trade for the whole month.
-- Slim CI samples sales but not returns: there only months that start inside the sample
-- window (and so have all of their sales) are checked.
{%- set sample_window = "monthly.month_start_date > current_date - " ~ var('ci_sample_days')
    if target.name == 'ci' else "1 = 1" %}
with

monthly as (
    select * from {{ ref('rpt_store_performance_monthly') }}
),

stores as (
    select * from {{ ref('dim_store') }}
    where is_current
)

select
    monthly.month_start_date,
    monthly.store_code,
    monthly.net_revenue_aed
from monthly
inner join stores on monthly.store_code = stores.store_code
where
    monthly.net_revenue_aed < 0
    and (stores.closed_on is null or stores.closed_on > monthly.month_start_date + interval '1 month')
    and {{ sample_window }}
