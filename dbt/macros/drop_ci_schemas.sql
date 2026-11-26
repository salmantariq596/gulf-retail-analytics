{#
    Drop the temporary schemas a slim CI run created (ci_pr_<number>_staging, _marts, ...).
    Called by .github/workflows/ci.yml when the job ends, pass or fail:

        dbt run-operation drop_ci_schemas --args '{prefix: ci_pr_42}' --target ci

    Guard rails: Snowflake DEV database only, and the prefix must start with ci_.
#}
{% macro drop_ci_schemas(prefix) %}
    {%- if target.type != 'snowflake' or target.database | upper != 'DEV' -%}
        {{ exceptions.raise_compiler_error("drop_ci_schemas only runs against the Snowflake DEV database") }}
    {%- endif -%}
    {%- if not (prefix | lower).startswith('ci_') -%}
        {{ exceptions.raise_compiler_error("drop_ci_schemas: prefix must start with ci_, got " ~ prefix) }}
    {%- endif -%}

    {%- set find -%}
        select schema_name
        from {{ target.database }}.information_schema.schemata
        where schema_name ilike '{{ prefix }}%'
    {%- endset -%}
    {%- set schemas = run_query(find).columns[0].values() -%}

    {%- for schema in schemas -%}
        {%- do run_query('drop schema if exists ' ~ target.database ~ '.' ~ schema ~ ' cascade') -%}
        {{ log('dropped ' ~ target.database ~ '.' ~ schema, info=True) }}
    {%- endfor -%}
    {{ log(schemas | length ~ ' CI schema(s) dropped for ' ~ prefix, info=True) }}
{% endmacro %}
