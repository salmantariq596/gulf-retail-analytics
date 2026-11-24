{#
    Money helpers. Every amount in the marts goes through these, so the VAT and
    currency rules live in exactly one place (and are unit-tested in Phase 4).

    Rules (docs/business_definitions.md):
      - source prices are VAT-inclusive  -> excl = incl / (1 + rate)
      - currency conversion uses the fixed USD-peg cross rate to AED
      - amounts are rounded to 2 decimals at each step
#}

{#- Arguments are SQL expressions (e.g. 'line_total - net_excl'): always wrap them in
    parentheses, or operator precedence silently changes the result. Caught by the
    unit test test_sales_vat_split_currency_and_cost_on_sale_date. -#}

{% macro excl_vat(amount_incl_vat, vat_rate) %}
    cast(round(({{ amount_incl_vat }}) / (1 + ({{ vat_rate }})), 2) as decimal(18, 2))
{% endmacro %}

{% macro to_aed(amount_local, aed_per_unit) %}
    cast(round(({{ amount_local }}) * ({{ aed_per_unit }}), 2) as decimal(18, 2))
{% endmacro %}

{% macro money(expression) %}
    cast(round(({{ expression }}), 2) as decimal(18, 2))
{% endmacro %}
