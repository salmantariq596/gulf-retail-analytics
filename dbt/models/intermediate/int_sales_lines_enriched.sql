-- Every sales line with the numbers the business needs:
--   * business date in the store's (or ship-to country's) local time
--   * VAT split using the rate valid on that date
--   * local and AED amounts (fixed USD-peg cross rates)
--   * the unified customer id
--   * the product cost valid on the sale date (SCD2), and gross margin
with

sales as (
    select * from {{ ref('int_sales_lines_unioned') }}
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

identity as (
    select * from {{ ref('int_customer_identity_map') }}
),

products as (
    select * from {{ ref('int_products_versioned') }}
),

localised as (
    select
        sales.*,
        {{ to_local('sales.sold_at', 'countries.utc_offset_hours') }} as sold_at_local,
        {{ business_date('sales.sold_at', 'countries.utc_offset_hours') }} as business_date,
        coalesce(cast(sales.pos_customer_id as varchar), sales.online_customer_id) as source_customer_id
    from sales
    inner join countries on sales.country_code = countries.country_code
),

priced as (
    select
        localised.*,
        vat.vat_rate,
        fx.aed_per_unit,
        identity.customer_id,
        products.valid_from as product_valid_from,
        products.unit_cost_aed,
        {{ excl_vat('localised.quantity * localised.unit_price_incl_vat', 'vat.vat_rate') }}
            as gross_excl_vat_local,
        {{ excl_vat('localised.discount_incl_vat', 'vat.vat_rate') }} as discount_excl_vat_local
    from localised
    inner join vat
        on
            localised.country_code = vat.country_code
            and localised.business_date between vat.valid_from and vat.valid_to
    inner join fx
        on
            localised.currency_code = fx.currency_code
            and localised.business_date between fx.valid_from and fx.valid_to
    left join identity
        on
            localised.source_system = identity.source_system
            and localised.source_customer_id = identity.source_customer_id
    inner join products
        on
            localised.sku = products.sku
            and cast(localised.business_date as timestamp) >= products.valid_from
            and cast(localised.business_date as timestamp) < products.valid_to
),

amounts as (
    select
        *,
        {{ money('gross_excl_vat_local - discount_excl_vat_local') }} as net_excl_vat_local
    from priced
),

final as (
    select
        source_system || '-' || transaction_id || '-' || cast(line_number as varchar) as sales_line_id,
        source_system,
        transaction_id,
        line_number,
        source_line_id,
        store_id,
        country_code,
        sales_channel,
        customer_id,
        sku,
        product_valid_from,
        promotion_code,
        currency_code,
        sold_at,
        sold_at_local,
        business_date,
        quantity,
        vat_rate,
        aed_per_unit,

        -- local currency (net = after discount; VAT = what the customer paid minus net excl. VAT)
        {{ money('unit_price_incl_vat') }} as unit_price_incl_vat_local,
        {{ money('quantity * unit_price_incl_vat') }} as gross_incl_vat_local,
        {{ money('discount_incl_vat') }} as discount_incl_vat_local,
        {{ money('line_total_incl_vat') }} as net_incl_vat_local,
        gross_excl_vat_local,
        discount_excl_vat_local,
        net_excl_vat_local,
        {{ money('line_total_incl_vat - net_excl_vat_local') }} as vat_local,

        -- AED (reporting currency)
        {{ to_aed('gross_excl_vat_local', 'aed_per_unit') }} as gross_excl_vat_aed,
        {{ to_aed('discount_excl_vat_local', 'aed_per_unit') }} as discount_excl_vat_aed,
        {{ to_aed('net_excl_vat_local', 'aed_per_unit') }} as net_excl_vat_aed,
        {{ to_aed('line_total_incl_vat', 'aed_per_unit') }} as net_incl_vat_aed,
        {{ to_aed('line_total_incl_vat - net_excl_vat_local', 'aed_per_unit') }} as vat_aed,

        -- cost valid on the sale date, and margin
        unit_cost_aed,
        {{ money('quantity * unit_cost_aed') }} as cogs_aed,
        {{ money(to_aed('net_excl_vat_local', 'aed_per_unit') ~ ' - quantity * unit_cost_aed') }}
            as gross_margin_aed
    from amounts
)

select * from final
