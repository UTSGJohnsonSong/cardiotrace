-- mart_cv_master: final wide table for ML modeling.
-- One row per adult participant per cycle.
-- This is what Python loads for feature selection and modeling.

{{ config(materialized='table') }}

-- Survey-weight pooling: when combining k two-year cycles, NHANES guidance is
-- to divide each participant's 2-year MEC weight by k. We compute k from the
-- data (COUNT DISTINCT cycle) rather than hardcoding it, so the weight stays
-- correct if cycles are added or removed.
WITH cycle_count AS (
    SELECT COUNT(DISTINCT cycle)::NUMERIC AS n_cycles
    FROM {{ ref('stg_demographics') }}
)

SELECT
    -- IDs
    d.seqn,
    d.cycle,

    -- Demographics
    d.age,
    d.age_topcode_flag,
    d.gender,
    d.race_ethnicity,
    d.education_level,
    d.poverty_income_ratio,

    -- Survey design (keep for weighted analysis)
    d.survey_weight_2yr,
    d.psu,
    d.strata,

    -- Adjusted weight for multi-cycle pooling
    d.survey_weight_2yr / cc.n_cycles AS survey_weight_pooled,

    -- CVD Outcomes (targets)
    cv.has_heart_failure,
    cv.has_mi,
    cv.has_chd,
    cv.has_angina,
    cv.has_stroke,
    cv.has_any_cvd,

    -- Risk Factors (features)
    rf.systolic_bp_avg,
    rf.diastolic_bp_avg,
    rf.hypertension_diagnosed,
    rf.hypertension_on_meds,
    rf.bmi,
    rf.waist_cm,
    rf.obese,
    rf.diabetes_diagnosed,
    rf.on_insulin,
    rf.current_smoker,
    rf.cigarettes_per_day,
    rf.total_cholesterol,
    rf.hdl_cholesterol,
    rf.ldl_cholesterol,
    rf.triglycerides,
    rf.non_hdl_cholesterol,
    rf.fasting_glucose,
    rf.hba1c,
    rf.crp,
    rf.creatinine,
    rf.uric_acid,
    rf.vigorous_activity,
    rf.sedentary_minutes_per_day,

    -- Derived risk indicators
    CASE
        WHEN rf.systolic_bp_avg >= 130 OR rf.diastolic_bp_avg >= 80
          OR rf.hypertension_diagnosed = 1 THEN 1
        WHEN rf.systolic_bp_avg IS NULL AND rf.hypertension_diagnosed IS NULL THEN NULL
        ELSE 0
    END AS hypertension_flag,

    CASE
        WHEN rf.fasting_glucose >= 126 OR rf.hba1c >= 6.5
          OR rf.diabetes_diagnosed = 1 THEN 1
        WHEN rf.fasting_glucose IS NULL AND rf.hba1c IS NULL
          AND rf.diabetes_diagnosed IS NULL THEN NULL
        ELSE 0
    END AS diabetes_flag,

    -- COVID period flag. The 2021-2022 cycle (fielded Aug 2021-Aug 2023) is the
    -- first post-pandemic wave; every earlier cycle is pre-pandemic. The
    -- 2019-2020 wave was never released standalone, so there is a clean break.
    CASE
        WHEN d.cycle = '2021-2022' THEN 'post_pandemic'
        ELSE 'pre_pandemic'
    END AS covid_period

FROM {{ ref('stg_demographics') }}   d
JOIN {{ ref('stg_cardiovascular') }} cv USING (seqn, cycle)
JOIN {{ ref('stg_risk_factors') }}   rf USING (seqn, cycle)
CROSS JOIN cycle_count cc
