-- Grain: one store in one calendar month.
-- Pre-aggregated store P&L down to gross margin, for the executive and finance
-- dashboards. Returns are netted in the month they happen (return date).
with

sales as (
    select * from {{ ref('fct_sales_lines') }}
),

returns as (
    select * from {{ ref('fct_returns') }}
),

stores as (
    select * from {{ ref('dim_store') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

sales_monthly as (
    select
        dates.month_start_date,
        stores.store_id,
        sum(sales.gross_excl_vat_aed) as gross_sales_aed,
        sum(sales.discount_excl_vat_aed) as discounts_aed,
        sum(sales.net_excl_vat_aed) as sales_net_of_discounts_aed,
        sum(sales.cogs_aed) as cogs_aed,
        sum(sales.quantity) as units_sold,
        count(distinct sales.transaction_id) as transaction_count
    from sales
    inner join stores on sales.store_key = stores.store_key
    inner join dates on sales.date_key = dates.date_key
    group by dates.month_start_date, stores.store_id
),

returns_monthly as (
    select
        dates.month_start_date,
        stores.store_id,
        sum(returns.refund_excl_vat_aed) as returns_aed,
        sum(returns.returned_cogs_aed) as returned_cogs_aed,
        sum(returns.quantity) as units_returned
    from returns
    inner join stores on returns.store_key = stores.store_key
    inner join dates on returns.date_key = dates.date_key
    group by dates.month_start_date, stores.store_id
),

combined as (
    select
        coalesce(s.month_start_date, r.month_start_date) as month_start_date,
        coalesce(s.store_id, r.store_id) as store_id,
        coalesce(s.gross_sales_aed, 0) as gross_sales_aed,
        coalesce(s.discounts_aed, 0) as discounts_aed,
        coalesce(r.returns_aed, 0) as returns_aed,
        coalesce(s.sales_net_of_discounts_aed, 0) - coalesce(r.returns_aed, 0) as net_revenue_aed,
        coalesce(s.cogs_aed, 0) - coalesce(r.returned_cogs_aed, 0) as cogs_aed,
        coalesce(s.units_sold, 0) as units_sold,
        coalesce(r.units_returned, 0) as units_returned,
        coalesce(s.transaction_count, 0) as transaction_count,
        s.sales_net_of_discounts_aed
    from sales_monthly as s
    full outer join returns_monthly as r
        on
            s.month_start_date = r.month_start_date
            and s.store_id = r.store_id
),

final as (
    select
        combined.month_start_date,
        current_store.store_code,
        current_store.store_name_en,
        current_store.country_code,
        current_store.store_format,
        {{ money('combined.gross_sales_aed') }} as gross_sales_aed,
        {{ money('combined.discounts_aed') }} as discounts_aed,
        {{ money('combined.returns_aed') }} as returns_aed,
        {{ money('combined.net_revenue_aed') }} as net_revenue_aed,
        {{ money('combined.cogs_aed') }} as cogs_aed,
        {{ money('combined.net_revenue_aed - combined.cogs_aed') }} as gross_margin_aed,
        cast(
            round((combined.net_revenue_aed - combined.cogs_aed) / nullif(combined.net_revenue_aed, 0), 4)
            as decimal(9, 4)
        ) as gross_margin_pct,
        combined.units_sold,
        combined.units_returned,
        combined.transaction_count,
        {{ money('combined.sales_net_of_discounts_aed / nullif(combined.transaction_count, 0)') }}
            as average_basket_value_aed,
        cast(
            round(combined.returns_aed / nullif(combined.sales_net_of_discounts_aed, 0), 4) as decimal(9, 4)
        ) as return_rate
    from combined
    inner join stores as current_store
        on
            combined.store_id = current_store.store_id
            and current_store.is_current
)

select * from final
