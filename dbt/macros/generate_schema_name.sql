-- Use the model's +schema verbatim (e.g. `mart`, `staging`) instead of dbt's
-- default of prefixing it with the target schema (which yields `mart_mart`).
-- The downstream pipeline reads fixed schema names like mart.mart_cv_master.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
