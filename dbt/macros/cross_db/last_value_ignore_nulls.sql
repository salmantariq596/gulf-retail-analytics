{#
    last_value(... ignore nulls) over (...): the IGNORE NULLS clause sits inside the
    parentheses in DuckDB and after them in Snowflake.
#}
{% macro last_value_ignore_nulls(expression, over_clause) %}
    {{ return(adapter.dispatch('last_value_ignore_nulls', 'najm_retail')(expression, over_clause)) }}
{% endmacro %}

{% macro default__last_value_ignore_nulls(expression, over_clause) %}
    last_value({{ expression }}) ignore nulls over ({{ over_clause }})
{% endmacro %}

{% macro duckdb__last_value_ignore_nulls(expression, over_clause) %}
    last_value({{ expression }} ignore nulls) over ({{ over_clause }})
{% endmacro %}
