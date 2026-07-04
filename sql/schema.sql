-- CardioTrace PostgreSQL Schema (pure DDL — schemas + raw tables).
--
-- This file is run automatically inside the `cardiotrace` database:
--   * By Docker on first start (mounted into docker-entrypoint-initdb.d).
--   * Manually against an existing database:
--        createdb cardiotrace                       # once
--        psql -d cardiotrace -f sql/schema.sql
--
-- It intentionally does NOT `CREATE DATABASE` / `\c` so it is safe to run
-- inside an already-connected session (which is how both paths above work).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;

-- ─────────────────────────────────────────
-- RAW LAYER
-- One row per participant per cycle.
-- Column names match NHANES codebook exactly.
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw.demographics (
    seqn        BIGINT,
    cycle       VARCHAR(10),
    ridageyr    FLOAT,   -- age in years (80 = 80+)
    riagendr    FLOAT,   -- 1=Male, 2=Female
    ridreth1    FLOAT,   -- race/ethnicity (5 categories)
    ridreth3    FLOAT,   -- race/ethnicity (6 categories, 2011+)
    dmdeduc2    FLOAT,   -- education (adults 20+)
    indfmpir    FLOAT,   -- poverty income ratio
    wtmec2yr    FLOAT,   -- 2-year MEC exam weight (USE FOR PREVALENCE)
    wtint2yr    FLOAT,   -- 2-year interview weight
    sdmvpsu     FLOAT,   -- primary sampling unit
    sdmvstra    FLOAT,   -- masked variance pseudo-stratum
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.cardiovascular_questionnaire (
    seqn     BIGINT,
    cycle    VARCHAR(10),
    mcq160b  FLOAT,   -- congestive heart failure (1=Yes, 2=No, 7=Refused, 9=DK)
    mcq160e  FLOAT,   -- heart attack / MI
    mcq160c  FLOAT,   -- coronary heart disease
    mcq160d  FLOAT,   -- angina pectoris
    mcq160f  FLOAT,   -- stroke
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.blood_pressure_exam (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    bpxsy1  FLOAT,   -- systolic BP, 1st reading
    bpxdi1  FLOAT,   -- diastolic BP, 1st reading
    bpxsy2  FLOAT,
    bpxdi2  FLOAT,
    bpxsy3  FLOAT,
    bpxdi3  FLOAT,
    bpxpls  FLOAT,   -- pulse (60 sec)
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.blood_pressure_questionnaire (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    bpq020  FLOAT,   -- ever told high blood pressure
    bpq040a FLOAT,   -- taking prescription for hypertension
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.body_measures (
    seqn      BIGINT,
    cycle     VARCHAR(10),
    bmxwt     FLOAT,   -- weight (kg)
    bmxht     FLOAT,   -- height (cm)
    bmxbmi    FLOAT,   -- BMI
    bmxwaist  FLOAT,   -- waist circumference (cm)
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.diabetes_questionnaire (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    diq010  FLOAT,   -- ever told have diabetes (1=Yes, 2=No, 3=Borderline)
    diq050  FLOAT,   -- taking insulin
    diq070  FLOAT,   -- taking diabetes pills
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.smoking_questionnaire (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    smq020  FLOAT,   -- smoked at least 100 cigarettes in life
    smq040  FLOAT,   -- current smoker (1=Every day, 2=Some days, 3=Not at all)
    smd030  FLOAT,   -- age started smoking
    smd650  FLOAT,   -- avg cigarettes per day (current smokers)
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.labs_cholesterol (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    lbxtc   FLOAT,   -- total cholesterol (mg/dL)
    lbdhdd  FLOAT,   -- HDL cholesterol (mg/dL)
    lbdldl  FLOAT,   -- LDL cholesterol (mg/dL, Friedewald)
    lbxtr   FLOAT,   -- triglycerides (mg/dL)
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.labs_glucose (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    lbxglu  FLOAT,   -- fasting plasma glucose (mg/dL)
    lbxgh   FLOAT,   -- HbA1c (%)
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.labs_biochemistry (
    seqn     BIGINT,
    cycle    VARCHAR(10),
    lbxscr   FLOAT,   -- creatinine (mg/dL) — key for kidney function
    lbxscu   FLOAT,   -- uric acid (mg/dL)
    lbxstp   FLOAT,   -- total protein
    lbxsal   FLOAT,   -- albumin
    lbxsca   FLOAT,   -- calcium
    lbxsnasi FLOAT,   -- sodium
    lbxsksi  FLOAT,   -- potassium
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.labs_crp (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    lbxcrp  FLOAT,   -- C-reactive protein (mg/dL)
    PRIMARY KEY (seqn, cycle)
);

CREATE TABLE IF NOT EXISTS raw.physical_activity (
    seqn    BIGINT,
    cycle   VARCHAR(10),
    paq605  FLOAT,   -- vigorous recreational activity (1=Yes, 2=No)
    paq620  FLOAT,   -- moderate recreational activity
    pad680  FLOAT,   -- sedentary activity (minutes per day)
    PRIMARY KEY (seqn, cycle)
);

-- ─────────────────────────────────────────
-- INDEXES (for join performance)
-- ─────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_demo_seqn    ON raw.demographics (seqn);
CREATE INDEX IF NOT EXISTS idx_demo_cycle   ON raw.demographics (cycle);
CREATE INDEX IF NOT EXISTS idx_cv_seqn      ON raw.cardiovascular_questionnaire (seqn);
CREATE INDEX IF NOT EXISTS idx_bp_seqn      ON raw.blood_pressure_exam (seqn);
CREATE INDEX IF NOT EXISTS idx_bm_seqn      ON raw.body_measures (seqn);
