{{ config(severity='warn') }}
-- About 1% of ERP files go missing and are carried forward. If more than 5% of the
-- last 90 days are imputed, the feed is failing rather than glitching: warn (the
-- numbers are still usable, but someone should chase the ERP team). A 30-day window
-- is too noisy for a 1% event: three random misses would already read as 10%.
with

inventory as (
    select * from {{ ref('fct_inventory_daily') }}
),

window_start as (
    select max(snapshot_date) - 90 as start_date from inventory
),

recent as (
    select inventory.is_imputed
    from inventory
    inner join window_start on inventory.snapshot_date >= window_start.start_date
)

select
    count(*) as rows_checked,
    avg(case when is_imputed then 1.0 else 0.0 end) as imputed_share
from recent
having avg(case when is_imputed then 1.0 else 0.0 end) > 0.05
