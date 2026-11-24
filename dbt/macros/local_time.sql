{#
    UTC -> local time and business date. Gulf countries have no daylight saving,
    so a fixed offset (from the `countries` seed) is exact.
#}

{% macro to_local(utc_timestamp, utc_offset_hours) %}
    {{ dbt.dateadd('hour', utc_offset_hours, utc_timestamp) }}
{% endmacro %}

{% macro business_date(utc_timestamp, utc_offset_hours) %}
    cast({{ to_local(utc_timestamp, utc_offset_hours) }} as date)
{% endmacro %}
