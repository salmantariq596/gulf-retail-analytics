{#
    Schema naming per environment, so dev, CI and prod can never write to each other:

      target   custom schema   ->  result
      prod     marts               marts                   (PROD.MARTS: clean names for consumers)
      lightdash  (read-only BI connection: resolves to the same PROD schemas)
      dev      marts               <target.schema>_marts   (DEV.DBT_SALMAN_MARTS, or dev_marts on DuckDB)
      ci       marts               <target.schema>_marts   (DEV.CI_PR_42_MARTS)

    Prod also lives in its own database (PROD), so even a misconfigured dev target
    cannot overwrite production objects.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif target.name in ('prod', 'lightdash') -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
