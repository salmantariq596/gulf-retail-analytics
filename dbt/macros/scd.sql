{#
    SCD2 helpers shared by every versioned dimension.

    open_valid_from: the first version of a record is valid from the beginning of
    time. History only exists from the moment we started capturing it; without
    this, facts older than the first snapshot would find no matching version.
#}

{% macro open_valid_from(valid_from, partition_by, order_by=None) %}
    case
        when row_number() over (partition by {{ partition_by }} order by {{ order_by or valid_from }}) = 1
            then cast('{{ var("scd_start") }}' as timestamp)
        else cast({{ valid_from }} as timestamp)
    end
{% endmacro %}

{% macro scd_end() %}
    cast('{{ var("scd_end") }}' as timestamp)
{% endmacro %}
