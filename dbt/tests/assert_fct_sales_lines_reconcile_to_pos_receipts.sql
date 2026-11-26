-- Full-history invariant: off on the sampled slim-CI target (incremental facts read only
-- the last ci_sample_days there). It runs in the DuckDB end-to-end job and on every deploy.
{{ config(enabled=target.name != 'ci') }}

-- Reconciliation to source: for every POS receipt that counts as business (completed,
-- not training mode), the VAT-inclusive total in fct_sales_lines must equal the
-- receipt total printed by the till, minus any till-test SKU lines. Any difference
-- means lines were lost, duplicated or mis-valued between raw and the mart.
with

receipts as (
    select
        sales.sale_id,
        sales.total_incl_vat
    from {{ ref('stg_pos__sales') }} as sales
    inner join {{ ref('stg_pos__cashiers') }} as cashiers on sales.cashier_id = cashiers.cashier_id
    where
        not sales.is_voided
        and not cashiers.is_training_cashier
),

test_sku_lines as (
    select
        sale_id,
        sum(line_total_incl_vat) as test_total
    from {{ ref('int_pos_sale_lines_deduped') }}
    where is_test_sku
    group by sale_id
),

expected as (
    select
        cast(receipts.sale_id as varchar) as transaction_id,
        receipts.total_incl_vat - coalesce(test_sku_lines.test_total, 0) as expected_total
    from receipts
    left join test_sku_lines on receipts.sale_id = test_sku_lines.sale_id
),

actual as (
    select
        transaction_id,
        sum(net_incl_vat_local) as actual_total
    from {{ ref('fct_sales_lines') }}
    where source_system = 'pos'
    group by transaction_id
)

select
    coalesce(expected.transaction_id, actual.transaction_id) as transaction_id,
    expected.expected_total,
    actual.actual_total
from expected
full outer join actual on expected.transaction_id = actual.transaction_id
where abs(coalesce(expected.expected_total, 0) - coalesce(actual.actual_total, 0)) > 0.01
