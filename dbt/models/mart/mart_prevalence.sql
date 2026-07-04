-- mart_prevalence: aggregated prevalence rates by cycle and demographic group.
-- Used directly by Tableau for trend charts.
-- NOTE: These are UNWEIGHTED counts. Apply survey weights in Tableau or Python
--       for publication-quality prevalence estimates.

{{ config(materialized='table') }}

SELECT
    cycle,
    gender,
    race_ethnicity,
    covid_period,

    -- Age groups
    CASE
        WHEN age BETWEEN 20 AND 39 THEN '20-39'
        WHEN age BETWEEN 40 AND 59 THEN '40-59'
        WHEN age BETWEEN 60 AND 79 THEN '60-79'
        WHEN age >= 80             THEN '80+'
        ELSE NULL
    END AS age_group,

    COUNT(*)                                    AS n_total,
    SUM(has_heart_failure)                      AS n_heart_failure,
    SUM(has_mi)                                 AS n_mi,
    SUM(has_chd)                                AS n_chd,
    SUM(has_angina)                             AS n_angina,
    SUM(has_stroke)                             AS n_stroke,
    SUM(has_any_cvd)                            AS n_any_cvd,

    ROUND(100.0 * AVG(has_heart_failure), 2)    AS pct_heart_failure,
    ROUND(100.0 * AVG(has_mi), 2)               AS pct_mi,
    ROUND(100.0 * AVG(has_chd), 2)              AS pct_chd,
    ROUND(100.0 * AVG(has_angina), 2)           AS pct_angina,
    ROUND(100.0 * AVG(has_stroke), 2)           AS pct_stroke,
    ROUND(100.0 * AVG(has_any_cvd), 2)          AS pct_any_cvd

FROM {{ ref('mart_cv_master') }}
WHERE has_any_cvd IS NOT NULL
GROUP BY 1, 2, 3, 4, 5
