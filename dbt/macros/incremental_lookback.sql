{#
    Late-data strategy for incremental facts (see docs/business_definitions.md).

    On an incremental run, reprocess every row whose business date falls in the last
    `lookback_days` days already loaded. Combined with delete+insert keyed on the
    business date, the whole window is replaced: late-arriving rows are added and
    rows that disappeared upstream (cancelled orders) are removed. A merge on the
    line key could add and update, but never delete.

    First run / --full-refresh: no filter, the whole history is built, except on the
    `ci` target, where slim CI builds a fresh copy in a temporary schema: there only the
    last `ci_sample_days` days are read, to keep pull-request checks cheap.
#}
{% macro incremental_lookback(date_column, alias=None) %}
    {%- set qualified = (alias ~ '.' ~ date_column) if alias else date_column -%}
    {%- if is_incremental() -%}
        {{ qualified }} >= (
            select cast({{ dbt.dateadd('day', -1 * var('lookback_days'), 'max(' ~ date_column ~ ')') }} as date)
            from {{ this }}
        )
    {%- elif target.name == 'ci' -%}
        {{ qualified }} >= cast({{ dbt.dateadd('day', -1 * var('ci_sample_days'), 'current_date') }} as date)
    {%- else -%}
        1 = 1
    {%- endif -%}
{% endmacro %}
