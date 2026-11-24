{#
    Elapsed hours between two timestamps, to 2 decimals; null if either is null.
    Uses dbt's cross-database datediff in seconds so DuckDB and Snowflake agree.
#}
{% macro hours_between(start_ts, end_ts) %}
    cast(round({{ dbt.datediff(start_ts, end_ts, 'second') }} / 3600.0, 2) as decimal(10, 2))
{% endmacro %}
