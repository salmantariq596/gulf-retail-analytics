{#
    One column per country from a long (date, country_code, value) shape.
    Used by dim_date for per-country weekends and holidays:

        {{ pivot_by_country('w.country_code', 'true', 'is_weekend', agg='bool') }}
        -> is_weekend_ae, is_weekend_sa, is_weekend_qa
#}

{% macro pivot_by_country(country_column, value_expression, prefix, agg='max') %}
    {%- for cc in var('countries') %}
        {%- if agg == 'bool' %}
    coalesce(max(case when {{ country_column }} = '{{ cc }}' then 1 end), 0) = 1 as {{ prefix }}_{{ cc | lower }}
        {%- else %}
    max(case when {{ country_column }} = '{{ cc }}' then {{ value_expression }} end) as {{ prefix }}_{{ cc | lower }}
        {%- endif %}
        {%- if not loop.last %},{% endif %}
    {%- endfor %}
{% endmacro %}
