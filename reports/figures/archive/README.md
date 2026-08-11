# Archived figures — do not cite

These four figures were produced by the pre-2026-08 pipeline and are **withdrawn**.
They are kept for provenance, not for reference.

| figure | what it showed |
|---|---|
| `prevalence_trend.png` | 25-year survey-weighted CVD prevalence |
| `equity_by_race.png` | Any-CVD prevalence by race/ethnicity |
| `model_performance.png` | PR-AUC for 12 cross-sectional classifiers |
| `shap_has_any_cvd.png` | SHAP feature importance, Any-CVD model |

Two reasons they cannot be used:

1. **The inputs were partly fabricated.** The 1999–2004 cycles reached the warehouse
   with no laboratory data at all — CDC had renamed the lab modules and the downloader
   read a 404 as "not collected" — so cholesterol, glucose, HbA1c and creatinine were
   median-imputed for 15,332 adults, 24.4% of the sample. `shap_has_any_cvd.png` ranks
   `total_cholesterol` sixth; that column was among the imputed ones.

2. **The design did not support the claim.** The outcome asked whether a doctor had
   *ever* said you had the condition, while the risk markers were measured at the same
   visit. Exposure never preceded outcome, so the models identified prevalent diagnoses
   rather than predicting risk.

See `docs/methodology-review.md` and the `data: fix silent loss of all 1999-2004
laboratory data` commit.
