# CardioTrace
### 25 Years of Cardiovascular Risk in America — an end-to-end NHANES analytics pipeline

![Python](https://img.shields.io/badge/Python-3.11-blue) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue) ![dbt](https://img.shields.io/badge/dbt-1.11-orange) ![XGBoost](https://img.shields.io/badge/XGBoost-3.2-green) ![Docker](https://img.shields.io/badge/Docker-compose-2496ED) ![SHAP](https://img.shields.io/badge/SHAP-interpretability-purple)

CardioTrace ingests **25 years of CDC NHANES data (1999–2023, 11 biennial cycles, ~60,000 examined adults)**, transforms it through a Dockerized PostgreSQL + dbt warehouse, and trains survey-weighted machine-learning models for **five cardiovascular disease outcomes** — with SHAP interpretability, a health-equity analysis, and a pre/post-COVID comparison. The entire pipeline runs from raw government files to final figures with a single command.

<!-- KEY_FINDINGS_START -->
## Key Findings

- **Any-CVD prevalence, survey-weighted:** 8.1% of US adults in 1999-2000 → 9.61% in 2021-2022 (pooled N = 62,890 adults across 11 cycles).
- **Best model:** Xgboost predicts coronary heart disease at ROC-AUC 0.8585 / PR-AUC 0.209 (5-fold cross-validated, survey design retained).
- **Top risk drivers (SHAP, Any-CVD model):** age, hypertension_flag, poverty_income_ratio.
- **Health equity (2021-2022):** Any-CVD prevalence ranges from 10.87% (Other/Multiracial) to 4.74% (Non-Hispanic Asian).
- **Pre vs post-COVID:** Any-CVD 8.67% → 9.61%; mean HbA1c 5.62 → 5.71%; mean BMI 28.76 → 29.68.

_Figures in [`reports/figures/`](reports/figures); full numbers in [`reports/results.json`](reports/results.json)._
<!-- KEY_FINDINGS_END -->

---

## Why this project is built the way it is

Every non-obvious decision here is one an interviewer would probe:

- **Survey weights, everywhere.** NHANES is a complex, stratified, multi-stage probability sample. A raw mean is biased, so all population estimates use the pooled MEC exam weight (`WTMEC2YR ÷ n_cycles`), and the strata/PSU columns are retained for design-based standard errors. `n_cycles` is computed from the data, not hardcoded.
- **No SMOTE.** CVD prevalence is ~2–6%, so classes are imbalanced ~20:1. SMOTE would fabricate minority cases and distort epidemiological prevalence — instead imbalance is handled in the loss function (`class_weight='balanced'` / per-target `scale_pos_weight`).
- **PR-AUC over accuracy.** At 5% prevalence a model that predicts "no disease" for everyone scores 95% accuracy and is useless. Models are ranked by PR-AUC, then ROC-AUC and F1 at the best threshold.
- **No participant double-counting.** The special 2017–2020 pre-pandemic file pools 2017–2018 with the partial 2019–2020 wave; including it alongside 2017–2018 would double-count people, so it is deliberately excluded. That leaves a clean gap before 2021–2023 — exactly what makes the COVID comparison valid.
- **Instruments harmonized across the series.** Oscillometric blood pressure (`BPXO`) replaced the manual cuff (`BPX`) in 2017, and high-sensitivity CRP (mg/L) replaced the legacy assay (mg/dL). The ETL maps both onto one column/unit so a single model sees a continuous 25-year series.

---

## Architecture

```
CDC NHANES public files (11 cycles × ~17 modules, 1999–2023)
      │  data/download.py — deterministic URL builder + HEAD probe
      ▼
data/raw/*.XPT
      │  src/etl.py — pyreadstat, merge files→table, harmonize instruments
      ▼
PostgreSQL  (raw schema)          ← Dockerized: docker compose up -d
      │  dbt: staging → mart
      ▼
PostgreSQL  (staging + mart schema)
      │  run_pipeline.py — survey-weighted analysis + ML + SHAP
      ▼
reports/figures/*.png · reports/tables/*.csv · reports/results.json
dashboard/data/*.csv  (Tableau-ready aggregates)
```

---

## Reproduce it end to end

Prereqs: Docker Desktop, Python 3.11. From the project root:

```bash
make setup     # create .venv, install requirements
make up        # start Dockerized Postgres on localhost:5435
make data      # download NHANES XPT files into data/raw/  (~280 MB)
make load      # load raw files into Postgres
make dbt       # build staging + mart models
make analyze   # run analysis + models → reports/
```

Or in one go: `make all`. Without `make` (e.g. Windows PowerShell), run the underlying commands shown in the [Makefile](Makefile).

The database is fully containerized (`docker-compose.yml`), so there is nothing to install or configure beyond Docker — the schema is created automatically on first start.

---

## The five cardiovascular outcomes

| Disease | NHANES Variable | Modeled |
|---------|-----------------|---------|
| Congestive Heart Failure | MCQ160B | ✅ |
| Myocardial Infarction (Heart Attack) | MCQ160E | ✅ |
| Coronary Heart Disease | MCQ160C | ✅ |
| Angina Pectoris | MCQ160D | ✅ |
| Stroke | MCQ160F | ✅ |
| _Composite: any of the above_ | derived | ✅ |

---

## Repository structure

```
CardioTrace/
├── docker-compose.yml       # Dockerized PostgreSQL 16 (localhost:5435)
├── Makefile                 # one-command pipeline
├── run_pipeline.py          # orchestrator: analysis + models + SHAP → reports/
├── data/download.py         # deterministic NHANES downloader
├── sql/schema.sql           # raw schema DDL (auto-run by Docker)
├── dbt/                     # staging + mart models, sources, profile
│   └── models/{staging,mart}/
├── src/
│   ├── etl.py               # XPT → Postgres (merge, harmonize)
│   ├── analysis.py          # survey-weighted prevalence / equity / COVID
│   ├── features.py          # 3-layer feature selection funnel
│   └── model.py             # LR + XGBoost training, SHAP, metrics
├── notebooks/               # 01 EDA · 02 feature selection · 03 modeling · 04 SHAP
├── reports/{figures,tables} # generated artifacts + results.json
└── dashboard/data/          # Tableau-ready aggregated CSVs
```

---

## Tech stack

| Layer | Tool |
|-------|------|
| Data acquisition | Python `requests` (deterministic URL builder + HEAD probe) |
| Parsing | `pyreadstat` (robust C-based XPORT reader) |
| Warehouse | PostgreSQL 16 (Dockerized) |
| Transformation | dbt-core 1.11 (staging → mart, sources, tests) |
| Analysis | pandas, NumPy, SciPy, statsmodels |
| ML | scikit-learn (Logistic Regression) + XGBoost |
| Interpretability | SHAP (TreeExplainer) |
| Visualization | Matplotlib → figures; Tableau Public (dashboard) |

---

## Data notes

- **Source**: [CDC NHANES](https://wwwn.cdc.gov/nchs/nhanes/), fully de-identified public-use data (no IRB required).
- **Cycles**: 11 non-overlapping biennial waves, 1999–2000 … 2017–2018 and 2021–2023.
- **Population**: adults 20+ (`RIDAGEYR ≥ 20`); age is top-coded at 80 for privacy.
- **Missing codes**: NHANES 7/77/777 (Refused) and 9/99/999 (Don't Know) are recoded to NULL in the staging layer.

---

## Part of the HealthTrace platform

CardioTrace is Module 1 of a planned multi-disease analytics platform on NHANES; the ETL + warehouse + modeling infrastructure is built to extend to other conditions.

| Module | Focus | Status |
|--------|-------|--------|
| **CardioTrace** | Cardiovascular disease | ✅ Built |
| NephroTrace | Kidney disease (CKD) | 📋 Planned |
| GutTrace | Digestive & nutrition | 📋 Planned |
