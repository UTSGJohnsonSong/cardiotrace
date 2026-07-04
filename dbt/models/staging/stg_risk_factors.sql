-- Consolidated risk factor staging: BP, BMI, labs, smoking, diabetes.
-- Joins all measurement tables; one row per participant per cycle.

{{ config(materialized='table') }}

SELECT
    d.seqn,
    d.cycle,

    -- Blood pressure (average of 3 readings where available)
    ROUND(
        ((COALESCE(bp.bpxsy1, 0) + COALESCE(bp.bpxsy2, 0) + COALESCE(bp.bpxsy3, 0)) /
        NULLIF(
            (CASE WHEN bp.bpxsy1 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN bp.bpxsy2 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN bp.bpxsy3 IS NOT NULL THEN 1 ELSE 0 END), 0
        ))::NUMERIC, 1) AS systolic_bp_avg,

    ROUND(
        ((COALESCE(bp.bpxdi1, 0) + COALESCE(bp.bpxdi2, 0) + COALESCE(bp.bpxdi3, 0)) /
        NULLIF(
            (CASE WHEN bp.bpxdi1 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN bp.bpxdi2 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN bp.bpxdi3 IS NOT NULL THEN 1 ELSE 0 END), 0
        ))::NUMERIC, 1) AS diastolic_bp_avg,

    -- Hypertension flag (questionnaire)
    CASE WHEN bpq.bpq020 = 1 THEN 1 WHEN bpq.bpq020 = 2 THEN 0 ELSE NULL END
        AS hypertension_diagnosed,
    CASE WHEN bpq.bpq040a = 1 THEN 1 WHEN bpq.bpq040a = 2 THEN 0 ELSE NULL END
        AS hypertension_on_meds,

    -- Body measures
    bm.bmxbmi    AS bmi,
    bm.bmxwaist  AS waist_cm,
    bm.bmxwt     AS weight_kg,
    bm.bmxht     AS height_cm,

    -- Obesity flag
    CASE WHEN bm.bmxbmi >= 30 THEN 1 WHEN bm.bmxbmi IS NOT NULL THEN 0 ELSE NULL END
        AS obese,

    -- Diabetes
    CASE
        WHEN diq.diq010 IN (7, 9) THEN NULL
        WHEN diq.diq010 = 1       THEN 1
        WHEN diq.diq010 = 3       THEN 0  -- borderline → treat as no
        WHEN diq.diq010 = 2       THEN 0
        ELSE NULL
    END AS diabetes_diagnosed,
    CASE WHEN diq.diq050 = 1 THEN 1 WHEN diq.diq050 = 2 THEN 0 ELSE NULL END
        AS on_insulin,

    -- Smoking
    CASE
        WHEN sm.smq020 IN (7, 9) THEN NULL
        WHEN sm.smq040 IN (1, 2)  THEN 1   -- current smoker
        WHEN sm.smq020 = 1        THEN 0   -- former smoker
        WHEN sm.smq020 = 2        THEN 0   -- never smoker
        ELSE NULL
    END AS current_smoker,
    sm.smd650 AS cigarettes_per_day,

    -- Cholesterol
    chol.lbxtc   AS total_cholesterol,
    chol.lbdhdd  AS hdl_cholesterol,
    chol.lbdldl  AS ldl_cholesterol,
    chol.lbxtr   AS triglycerides,

    -- Derived: non-HDL cholesterol
    CASE WHEN chol.lbxtc IS NOT NULL AND chol.lbdhdd IS NOT NULL
         THEN chol.lbxtc - chol.lbdhdd
         ELSE NULL
    END AS non_hdl_cholesterol,

    -- Glucose / HbA1c
    glu.lbxglu AS fasting_glucose,
    glu.lbxgh  AS hba1c,

    -- Inflammation
    crp.lbxcrp AS crp,

    -- Kidney (for future NephroTrace module, included here for CVD comorbidity)
    bio.lbxscr  AS creatinine,
    bio.lbxscu  AS uric_acid,

    -- Physical activity
    CASE WHEN pa.paq605 = 1 THEN 1 WHEN pa.paq605 = 2 THEN 0 ELSE NULL END
        AS vigorous_activity,
    pa.pad680 AS sedentary_minutes_per_day

FROM {{ source('raw', 'demographics') }} d
LEFT JOIN {{ source('raw', 'blood_pressure_exam') }}         bp  USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'blood_pressure_questionnaire') }} bpq USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'body_measures') }}               bm  USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'diabetes_questionnaire') }}      diq USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'smoking_questionnaire') }}       sm  USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'labs_cholesterol') }}            chol USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'labs_glucose') }}                glu USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'labs_crp') }}                    crp USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'labs_biochemistry') }}           bio USING (seqn, cycle)
LEFT JOIN {{ source('raw', 'physical_activity') }}           pa  USING (seqn, cycle)
WHERE d.ridageyr >= 20
