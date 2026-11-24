{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='business_date',
        on_schema_change='append_new_columns',
        cluster_by=['business_date']
    )
}}

-- Grain: one product line on one completed sale, POS or online.
-- Transaction fact. Amounts in local currency and AED, with and without VAT, plus
-- cost (valid on the sale date) and margin. Returns are a separate fact.
with

sales as (
    select * from {{ ref('int_sales_lines_enriched') }}
    where {{ incremental_lookback('business_date') }}
),

stores as (
    select * from {{ ref('dim_store') }}
),

products as (
    select * from {{ ref('dim_product') }}
),

customers as (
    select * from {{ ref('dim_customer') }}
),

channels as (
    select * from {{ ref('dim_channel') }}
),

promotions as (
    select * from {{ ref('dim_promotion') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['sales.sales_line_id']) }} as sales_line_key,
        sales.sales_line_id,
        sales.source_system,
        sales.transaction_id,
        sales.line_number,

        -- dimension keys (versions valid at the time of sale)
        cast(
            extract(year from sales.business_date) * 10000
            + extract(month from sales.business_date) * 100
            + extract(day from sales.business_date) as integer
        ) as date_key,
        stores.store_key,
        products.product_key,
        coalesce(customers.customer_key, '-1') as customer_key,
        channels.channel_key,
        coalesce(promotions.promotion_key, '-1') as promotion_key,

        -- degenerate attributes
        sales.business_date,
        sales.sold_at,
        sales.sold_at_local,
        sales.country_code,
        sales.currency_code,
        sales.vat_rate,

        -- measures
        sales.quantity,
        sales.unit_price_incl_vat_local,
        sales.gross_incl_vat_local,
        sales.discount_incl_vat_local,
        sales.net_incl_vat_local,
        sales.gross_excl_vat_local,
        sales.discount_excl_vat_local,
        sales.net_excl_vat_local,
        sales.vat_local,
        sales.gross_excl_vat_aed,
        sales.discount_excl_vat_aed,
        sales.net_excl_vat_aed,
        sales.net_incl_vat_aed,
        sales.vat_aed,
        sales.unit_cost_aed,
        sales.cogs_aed,
        sales.gross_margin_aed,

        {{ dbt.current_timestamp() }} as dbt_loaded_at
    from sales
    inner join stores
        on
            sales.store_id = stores.store_id
            and sales.sold_at >= stores.valid_from
            and sales.sold_at < stores.valid_to
    inner join products
        on
            sales.sku = products.sku
            and sales.product_valid_from = products.valid_from
    left join customers
        on
            sales.customer_id = customers.customer_id
            and sales.sold_at >= customers.valid_from
            and sales.sold_at < customers.valid_to
    inner join channels on sales.sales_channel = channels.channel_code
    left join promotions on sales.promotion_code = promotions.promotion_code
)

select * from final
