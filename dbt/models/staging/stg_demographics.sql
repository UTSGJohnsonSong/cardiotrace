-- Standardized demographics across all cycles.
-- Key decisions:
--   - Adults 20+ only (NHANES CVD questions restricted to adults)
--   - RIDRETH3 preferred (2011+, has separate Asian category); fall back to RIDRETH1
--   - Survey weight divided by number of cycles when combining (handled in mart layer)

{{ config(materialized='table') }}

SELECT
    seqn,
    cycle,

    -- Age: NHANES top-codes at 80 (privacy). Flag it.
    ridageyr                                    AS age,
    CASE WHEN ridageyr >= 80 THEN 1 ELSE 0 END AS age_topcode_flag,

    -- Gender
    CASE
        WHEN riagendr = 1 THEN 'Male'
        WHEN riagendr = 2 THEN 'Female'
        ELSE NULL
    END AS gender,

    -- Race/ethnicity: prefer RIDRETH3 (6-cat), fall back to RIDRETH1 (5-cat)
    COALESCE(ridreth3, ridreth1)                AS race_eth_code,
    CASE COALESCE(ridreth3, ridreth1)
        WHEN 1 THEN 'Mexican American'
        WHEN 2 THEN 'Other Hispanic'
        WHEN 3 THEN 'Non-Hispanic White'
        WHEN 4 THEN 'Non-Hispanic Black'
        WHEN 6 THEN 'Non-Hispanic Asian'
        WHEN 7 THEN 'Other/Multiracial'
        ELSE NULL
    END AS race_ethnicity,

    -- Socioeconomic indicators
    CASE
        WHEN dmdeduc2 IN (7, 9) THEN NULL
        ELSE dmdeduc2
    END AS education_level,

    CASE
        WHEN indfmpir > 5 THEN 5.0  -- top-coded at 5 in NHANES
        ELSE indfmpir
    END AS poverty_income_ratio,

    -- Survey design variables (required for weighted analysis)
    wtmec2yr    AS survey_weight_2yr,
    wtint2yr    AS interview_weight_2yr,
    sdmvpsu     AS psu,
    sdmvstra    AS strata

FROM {{ source('raw', 'demographics') }}
WHERE ridageyr >= 20
