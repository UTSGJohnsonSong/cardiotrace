-- NHANES yes/no recode: 1=Yes, 2=No, 7=Refused, 9=Don't Know → NULL
{% macro recode_cvd(col) %}
    CASE
        WHEN {{ col }} IN (7, 9) THEN NULL
        WHEN {{ col }} = 1       THEN 1
        WHEN {{ col }} = 2       THEN 0
        ELSE NULL
    END
{% endmacro %}
