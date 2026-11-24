{#
    Convert a timezone-aware timestamp to a plain UTC timestamp (timestamp_ntz).

    Convention: every *_at column after staging is UTC without a timezone, so
    results never depend on the session timezone of whoever runs the query.
    Local business dates are derived later, from the store's timezone.
#}
{% macro to_utc(column) %}
    {{ return(adapter.dispatch('to_utc', 'najm_retail')(column)) }}
{% endmacro %}

{% macro default__to_utc(column) %}
    convert_timezone('UTC', {{ column }})::timestamp_ntz
{% endmacro %}

{% macro duckdb__to_utc(column) %}
    timezone('UTC', {{ column }})
{% endmacro %}
