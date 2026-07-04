-- Cardiovascular disease outcomes — 5 binary flags.
-- NHANES encoding: 1=Yes, 2=No, 7=Refused, 9=Don't Know → NULL

{{ config(materialized='table') }}

SELECT
    seqn,
    cycle,
    {{ recode_cvd('mcq160b') }} AS has_heart_failure,
    {{ recode_cvd('mcq160e') }} AS has_mi,
    {{ recode_cvd('mcq160c') }} AS has_chd,
    {{ recode_cvd('mcq160d') }} AS has_angina,
    {{ recode_cvd('mcq160f') }} AS has_stroke,

    -- Composite: any of the 5 CVD conditions
    CASE
        WHEN GREATEST(
            {{ recode_cvd('mcq160b') }},
            {{ recode_cvd('mcq160e') }},
            {{ recode_cvd('mcq160c') }},
            {{ recode_cvd('mcq160d') }},
            {{ recode_cvd('mcq160f') }}
        ) = 1 THEN 1
        WHEN COALESCE(mcq160b, mcq160e, mcq160c, mcq160d, mcq160f) IS NULL THEN NULL
        ELSE 0
    END AS has_any_cvd

FROM {{ source('raw', 'cardiovascular_questionnaire') }}
