{#
    Late-data strategy for incremental facts (see docs/business_definitions.md).

    On an incremental run, reprocess every row whose business date falls in the last
    `lookback_days` days already loaded. Combined with delete+insert keyed on the
    business date, the whole window is replaced: late-arriving rows are added and
    rows that disappeared upstream (cancelled orders) are removed. A merge on the
    line key could add and update, but never delete.

    First run / --full-refresh: no filter, the whole history is built.
#}
{% macro incremental_lookback(date_column, alias=None) %}
    {%- if is_incremental() -%}
        {%- set qualified = (alias ~ '.' ~ date_column) if alias else date_column -%}
        {{ qualified }} >= (
            select cast({{ dbt.dateadd('day', -1 * var('lookback_days'), 'max(' ~ date_column ~ ')') }} as date)
            from {{ this }}
        )
    {%- else -%}
        1 = 1
    {%- endif -%}
{% endmacro %}
