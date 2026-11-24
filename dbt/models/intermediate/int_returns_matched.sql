-- Every returned line, matched to the sale line it reverses where possible:
--   receipt       POS return with a receipt -> the exact original till line
--   online_order  online order returned in a store -> first line of that order with the same SKU
--   unmatched     no receipt: the original sale is unknown
-- Returns are booked on the RETURN date, in the store where the item came back.
with

return_lines as (
    select * from {{ ref('stg_pos__return_lines') }}
),

returns as (
    select * from {{ ref('stg_pos__returns') }}
),

stores as (
    select * from {{ ref('stg_pos__stores') }}
),

countries as (
    select * from {{ ref('countries') }}
),

vat as (
    select * from {{ ref('vat_rates') }}
),

fx as (
    select * from {{ ref('currency_rates') }}
),

pos_lines as (
    select * from {{ ref('int_pos_sale_lines_deduped') }}
),

online_lines as (
    select * from {{ ref('int_online_order_lines_valid') }}
),

sales as (
    select * from {{ ref('int_sales_lines_enriched') }}
),

identity as (
    select * from {{ ref('int_customer_identity_map') }}
),

products as (
    select * from {{ ref('int_products_versioned') }}
),

online_match as (
    select
        transaction_id as order_id,
        sku,
        min(line_number) as line_number
    from online_lines
    group by transaction_id, sku
),

matched as (
    select
        return_lines.return_line_id,
        returns.return_id,
        returns.store_id,
        stores.country_code,
        returns.currency_code,
        returns.reason_code,
        returns.returned_at,
        returns.pos_customer_id,
        return_lines.sku,
        return_lines.quantity,
        return_lines.refund_incl_vat,
        case
            when pos_lines.sale_line_id is not null
                then 'pos-' || cast(pos_lines.sale_id as varchar) || '-' || cast(pos_lines.line_number as varchar)
            when online_match.order_id is not null
                then 'online-' || online_match.order_id || '-' || cast(online_match.line_number as varchar)
        end as original_sales_line_id,
        case
            when pos_lines.sale_line_id is not null then 'receipt'
            when online_match.order_id is not null then 'online_order'
            else 'unmatched'
        end as match_method
    from return_lines
    inner join returns on return_lines.return_id = returns.return_id
    inner join stores on returns.store_id = stores.store_id
    left join pos_lines on return_lines.original_sale_line_id = pos_lines.sale_line_id
    left join online_match
        on
            returns.original_online_order_id = online_match.order_id
            and return_lines.sku = online_match.sku
),

localised as (
    select
        matched.*,
        {{ business_date('matched.returned_at', 'countries.utc_offset_hours') }} as return_date
    from matched
    inner join countries on matched.country_code = countries.country_code
),

final as (
    select
        localised.return_line_id,
        localised.return_id,
        localised.store_id,
        localised.country_code,
        localised.currency_code,
        localised.reason_code,
        localised.match_method,
        localised.original_sales_line_id,
        sales.sales_channel as original_sales_channel,
        sales.business_date as original_sale_date,
        coalesce(sales.sales_channel, 'store') as sales_channel,
        coalesce(sales.customer_id, identity.customer_id) as customer_id,
        localised.sku,
        localised.returned_at,
        localised.return_date,
        localised.quantity,
        vat.vat_rate,
        fx.aed_per_unit,
        {{ money('localised.refund_incl_vat') }} as refund_incl_vat_local,
        {{ excl_vat('localised.refund_incl_vat', 'vat.vat_rate') }} as refund_excl_vat_local,
        {{ to_aed(excl_vat('localised.refund_incl_vat', 'vat.vat_rate'), 'fx.aed_per_unit') }} as refund_excl_vat_aed,
        {{ to_aed('localised.refund_incl_vat', 'fx.aed_per_unit') }} as refund_incl_vat_aed,
        -- returned stock is valued at the cost of the original sale when known,
        -- otherwise at the cost valid on the return date
        coalesce(sales.unit_cost_aed, products.unit_cost_aed) as unit_cost_aed,
        {{ money('localised.quantity * coalesce(sales.unit_cost_aed, products.unit_cost_aed)') }}
            as returned_cogs_aed
    from localised
    inner join vat
        on
            localised.country_code = vat.country_code
            and localised.return_date between vat.valid_from and vat.valid_to
    inner join fx
        on
            localised.currency_code = fx.currency_code
            and localised.return_date between fx.valid_from and fx.valid_to
    left join sales on localised.original_sales_line_id = sales.sales_line_id
    left join identity
        on
            identity.source_system = 'pos'
            and cast(localised.pos_customer_id as varchar) = identity.source_customer_id
    inner join products
        on
            localised.sku = products.sku
            and cast(localised.return_date as timestamp) >= products.valid_from
            and cast(localised.return_date as timestamp) < products.valid_to
)

select * from final
