-- Grain: one returned product line on one return receipt.
-- Transaction fact, booked on the RETURN date in the store where the item came back.
-- Links to the original sale line where it is known (receipt or online order).
with

returns as (
    select * from {{ ref('int_returns_matched') }}
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

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['returns.return_line_id']) }} as return_line_key,
        returns.return_line_id,
        returns.return_id,
        case
            when returns.original_sales_line_id is not null
                then {{ dbt_utils.generate_surrogate_key(['returns.original_sales_line_id']) }}
        end as original_sales_line_key,

        cast(
            extract(year from returns.return_date) * 10000
            + extract(month from returns.return_date) * 100
            + extract(day from returns.return_date) as integer
        ) as date_key,
        stores.store_key,
        products.product_key,
        coalesce(customers.customer_key, '-1') as customer_key,
        channels.channel_key,

        returns.customer_id,
        coalesce(customers.acquisition_channel, 'unknown') as acquisition_channel,
        returns.return_date,
        returns.returned_at,
        returns.original_sale_date,
        returns.country_code,
        returns.currency_code,
        returns.reason_code,
        returns.match_method,
        returns.match_method != 'unmatched' as has_original_sale,

        returns.quantity,
        returns.refund_incl_vat_local,
        returns.refund_excl_vat_local,
        returns.refund_incl_vat_aed,
        returns.refund_excl_vat_aed,
        {{ money('returns.refund_incl_vat_aed - returns.refund_excl_vat_aed') }} as refund_vat_aed,
        returns.unit_cost_aed,
        returns.returned_cogs_aed
    from returns
    inner join stores
        on
            returns.store_id = stores.store_id
            and returns.returned_at >= stores.valid_from
            and returns.returned_at < stores.valid_to
    inner join products
        on
            returns.sku = products.sku
            and cast(returns.return_date as timestamp) >= products.valid_from
            and cast(returns.return_date as timestamp) < products.valid_to
    left join customers
        on
            returns.customer_id = customers.customer_id
            and returns.returned_at >= customers.valid_from
            and returns.returned_at < customers.valid_to
    inner join channels on returns.sales_channel = channels.channel_code
)

select * from final
