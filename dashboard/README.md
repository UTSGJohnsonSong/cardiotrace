# CardioTrace — Tableau Dashboard Data

This folder contains the Tableau-ready data sources for the CardioTrace public
dashboard, plus the recipes for the charts built from them. All files are
produced by `run_pipeline.py` (prevalence) and copied from `reports/tables/`.

**Live dashboard:** _(add your Tableau Public link here after publishing)_

---

## Data sources (`dashboard/data/`)

### 1. `prevalence_long.csv` — the primary source (648 rows)

Tidy/long format: one row per **cycle × gender × race × outcome**. This single
file drives the trend line, the equity bars, and the gender×outcome heatmap.

| Column | Meaning |
|--------|---------|
| `cycle` | NHANES survey cycle, e.g. `2017-2018` |
| `midyear` | Numeric midpoint of the cycle (`1999.5`) — use this for the time axis |
| `outcome` | CVD condition: Heart Failure, MI, CHD, Angina, Stroke, Any CVD |
| `gender` | Female / Male |
| `race_ethnicity` | 6 NHANES race/ethnicity groups |
| `prevalence_pct` | **Survey-weighted** prevalence, percent (main metric) |
| `n_unweighted` | Raw participant count in the cell |
| `n_cases` | Number with the condition |
| `weighted_pop` | Weighted US population represented |

### 2. `model_metrics.csv` — ML model comparison (12 rows)

One row per **model × target**. Logistic regression vs XGBoost across 6 outcomes.

| Column | Meaning |
|--------|---------|
| `model` | `logistic_regression` or `xgboost` |
| `target` | Outcome predicted (`has_any_cvd`, …) |
| `roc_auc` | ROC-AUC (discrimination; higher = better) |
| `pr_auc` | Precision-Recall AUC (better for rare outcomes) |
| `f1` | F1 at the chosen threshold |
| `prevalence` | Positive rate for that outcome |

### 3. `covid_pre_post.csv` — pandemic before/after (2 rows)

Pre- vs post-pandemic means for CVD prevalence and key risk markers (BMI,
HbA1c, blood pressure, cholesterol, glucose). Column names are `pct_*` for
prevalences and `mean_*` for continuous markers.

---

## Chart cookbook (what to build in Tableau)

| # | Chart | Source | How |
|---|-------|--------|-----|
| 1 | 25-year trend line | `prevalence_long` | Columns: `midyear` · Rows: `prevalence_pct` · Color: `outcome` |
| 2 | Equity bars by race | `prevalence_long` | Rows: `race_ethnicity` · Columns: `prevalence_pct` · sort descending; filter `outcome = Any CVD` |
| 3 | Gender × outcome heatmap | `prevalence_long` | Rows: `outcome` · Columns: `gender` · Color: `prevalence_pct` |
| 4 | Model comparison | `model_metrics` | Rows: `target` · Columns: `roc_auc` · Color: `model` |
| 5 | COVID before/after | `covid_pre_post` | Pivot the `pct_*`/`mean_*` columns; bars by `covid_period` |

Add an `outcome` **filter** to charts 1–3 so viewers can switch conditions.

Combine charts 1–3 (plus a title) into one Dashboard, then
`File → Save to Tableau Public`.

---

_Data: CDC NHANES 1999–2022, 11 cycles, 62,890 pooled adults. Prevalences are
survey-weighted. Regenerate with `python run_pipeline.py`._
