-- Full-history invariant: off on the sampled slim-CI target (incremental facts read only
-- the last ci_sample_days there). It runs in the DuckDB end-to-end job and on every deploy.
{{ config(enabled=target.name != 'ci') }}

-- The two online facts must agree: a non-cancelled order's total in the accumulating
-- snapshot equals the sum of its lines in the transaction fact. Cancelled orders
-- must have no sales lines at all.
with

orders as (
    select
        order_id,
        is_cancelled,
        order_total_incl_vat_local
    from {{ ref('fct_online_orders') }}
),

lines as (
    select
        transaction_id as order_id,
        sum(net_incl_vat_local) as lines_total
    from {{ ref('fct_sales_lines') }}
    where source_system = 'online'
    group by transaction_id
)

select
    orders.order_id,
    orders.is_cancelled,
    orders.order_total_incl_vat_local,
    lines.lines_total
from orders
left join lines on orders.order_id = lines.order_id
where
    (orders.is_cancelled and lines.order_id is not null)
    or (not orders.is_cancelled and abs(orders.order_total_incl_vat_local - coalesce(lines.lines_total, 0)) > 0.01)
