# CardioTrace
### 25 Years of Cardiovascular Risk in America — an end-to-end NHANES analytics pipeline

![Python](https://img.shields.io/badge/Python-3.11-blue) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue) ![dbt](https://img.shields.io/badge/dbt-1.11-orange) ![XGBoost](https://img.shields.io/badge/XGBoost-3.2-green) ![Docker](https://img.shields.io/badge/Docker-compose-2496ED) ![SHAP](https://img.shields.io/badge/SHAP-interpretability-purple)

CardioTrace ingests **25 years of CDC NHANES data (1999–2023, 11 biennial cycles, ~60,000 examined adults)** plus the **NCHS Linked Mortality File**, and builds a prospective cohort of adults free of cardiovascular disease at baseline to study **death from cardiovascular causes** over up to 20 years of follow-up.

Survey weights are applied to all population estimates. Competing risks are handled explicitly (deaths from other causes outnumber CVD deaths 2.9 : 1). Every file the pipeline keeps or drops is recorded with the rule that decided it.

<!-- KEY_FINDINGS_START -->
## Key Findings

### Prospective cohort — CVD mortality (current)

NHANES 1999–2014 linked to the National Death Index, adults 40–79 who were free of
cardiovascular disease at baseline. **20,736 participants · 925 CVD deaths · 2,711
competing deaths · 235,553 person-years.**

- **Blood pressure gradient.** Survey-weighted 15-year cumulative incidence of CVD
  death rises monotonically with baseline systolic BP: **2.40%** (<120 mmHg) → 3.14%
  → 4.78% → 6.31% → **11.58%** (≥160 mmHg). A **4.8×** spread.
- **Competing risk matters.** Treating deaths from other causes as censoring
  (1 − Kaplan-Meier) overstates 15-year CVD risk by 0.30 pp — **7.4% relative** —
  against the Aalen-Johansen estimator. Competing deaths outnumber CVD deaths 2.9 : 1.
- **Primary vs secondary prevention.** Excluded participants (CVD at baseline) die of
  CVD at **19.1 per 1,000 person-years** against **3.9** in the retained cohort — a
  4.9× gap, which is why the two cannot be pooled into one model.

**Aetiologic model** — cause-specific Cox, survey-weighted, robust variance clustered
on stratum × PSU. Blood pressure is Tobin-adjusted (+10 mmHg for treated participants)
so the exposure approximates the untreated level rather than a post-treatment value.

| | HR (95% CI) |
|---|---|
| **Systolic BP, per 10 mmHg** | **1.121 (1.079–1.166)** |
| Current smoker | 2.45 (1.97–3.05) |
| Male | 2.01 (1.65–2.44) |
| Non-Hispanic Black | 1.38 (1.15–1.65) |
| Poverty-income ratio, per unit | 0.84 (0.78–0.89) |

**Prediction model** — two cause-specific Cox fits combined into absolute risk, so a
participant who dies of something else is not counted as if they could still die of
CVD. Trained on 1999–2004 and applied **forward in time**; the split is on survey
cycle, not at random, because same-PSU participants are correlated and a random fold
would leak them across the boundary.

| Test set | n | Harrell's C | Predicted | Observed |
|---|---|---|---|---|
| 2005–2008, 10-year risk | 5,163 | **0.804** | 2.82% | 2.76% |
| 2009–2014, 5-year risk | 8,801 | **0.797** | 0.92% | 0.89% |

Discrimination barely decays on the further-out test set, and mean predicted risk sits
within 0.06 pp of observed in both. Calibration by decile is in
[`reports/figures/calibration.png`](reports/figures/calibration.png).

_Figures in [`reports/figures/`](reports/figures); participant flow in
[`reports/tables/strobe_part3.csv`](reports/tables/strobe_part3.csv)._

### ⚠️ Earlier cross-sectional results — withdrawn, being rebuilt

The prevalence-trend, health-equity and pre/post-COVID numbers previously published
here, and the cross-sectional classification models, are **withdrawn**. Two reasons:

1. **A data defect.** The original downloader hardcoded 17 NHANES module names and
   treated an HTTP 404 as "that panel wasn't collected". CDC had renamed the
   laboratory modules (`LAB13` → `L13` → `TCHOL`+`HDL`), so 1999–2004 entered the
   warehouse with **no laboratory data at all** — 15,332 adults, 24.4% of the sample —
   whose lipids, glucose and HbA1c were then median-imputed. Those fabricated values
   reached the published figures. Fixed in `data/download_from_catalog.py`; the
   affected cycles have been re-downloaded.
2. **A design problem.** The outcome (`MCQ160B–F`) asks whether a doctor *ever* said
   you had the condition, while the risk markers are measured at the same visit. The
   exposure does not precede the outcome, so the models were identifying prevalent
   diagnoses rather than predicting risk — and treatment effects run backwards
   (statin users have *lower* cholesterol). See
   [`docs/methodology-review.md`](docs/methodology-review.md).

The descriptive and COVID analyses are being rebuilt on the corrected data with
age standardisation and design-based confidence intervals.
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
