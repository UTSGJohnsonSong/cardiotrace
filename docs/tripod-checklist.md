# CardioTrace reporting checklist

This is a reporting map, not certification of clinical validity or a completed
journal submission. Item numbers follow the current [TRIPOD+AI checklist](https://www.tripod-statement.org/wp-content/uploads/2019/12/TRIPODAI_checklist.pdf)
(Collins et al., BMJ 2024;385:e078378). TRIPOD+AI applies to regression and machine
learning; the original 2015 checklist is superseded. Labels below are abbreviated;
the linked checklist contains the full requirements. Evidence paths are relative
to the repository root. Items requiring investigator declarations are left open.

| Item | Evidence and disposition |
|---|---|
| 1 | `README.md` and the report identify prospective CVD-mortality modelling in NHANES adults; a journal manuscript title remains to be supplied. |
| 2 | `docs/research-summary.md` supplies a generated structured research summary; journal-specific formatting and investigator declarations remain. |
| 3a–c | `docs/research-design.md` defines the rationale, target and inequality context. This is research for methodological appraisal; no deployed treatment pathway or intended patient use is established. |
| 4 | `docs/research-design.md` separates burden, pandemic deviation, prospective modelling and learning comparisons. |
| 5a–b | `src/cohort.py`, `src/descriptive.py`, `data/catalog/`, and the mortality manifest specify sources, survey cycles and follow-up cutoff. Temporal splits are in `src/models.py`. |
| 6a–c | `reports/tables/strobe_part3.csv` and `src/cohort.py` specify eligibility; `src/models.py` documents treatment handling. PCE uses measured pressure and treatment status (`src/pce.py`). |
| 7 | `data/build_variable_crosswalk.py`, `src/cohort.py`, `src/biomarkers.py`, coverage guards and regression fixtures specify preprocessing. No comprehensive subgroup measurement-invariance study has been conducted. |
| 8a–c | `src/cohort.py` defines cause-of-death codes and follow-up. Outcomes derive from public mortality linkage; this project neither adjudicates events nor changes source assessors' blinding. Nonfatal events are unavailable. |
| 9a–c | `src/models.py` and `src/screening.py` declare initial features, training-only selection and transformations; the catalog and variable crosswalk supply measurement provenance. No project-level subjective adjudication is performed. |
| 10 | All eligible public observations are used. No prospective sample-size calculation was performed. Event counts and precision are reported; adequacy for all demographic subgroup comparisons is not established. |
| 11 | `src/missingness.py` and `reports/missingness_results.json` report complete-case loss and E2 completeness-weight sensitivity. No multiple imputation or identification of MNAR bias is claimed. |
| 12a–g | `src/models.py`, `src/discrimination.py`, `src/screening.py`, `src/pce.py` and their result builders specify splits, model forms, transforms, tuning, survey handling, metrics and training-only recalibration. Evaluation remains conditional on the training fits. |
| 13 | Active mortality models use survey weights; they do not use SMOTE or other synthetic class balancing. Presence of legacy ML dependencies does not imply use in the active analysis. |
| 14 | No algorithmic fairness constraint is imposed. Ethnicity restrictions and selection differences are disclosed. Equalized performance or equitable clinical impact has not been demonstrated. |
| 15 | Mortality models return horizon probabilities; PCE retains its original ASCVD endpoint. Decision thresholds are illustrative utility tradeoffs, not clinical intervention rules. |
| 16 | Same definitions and preprocessing apply across temporal splits; cycle period, follow-up support and participant composition differ. PCE comparisons use identical common samples within each split. |
| 17 | Public-use NHANES secondary analysis. A project-specific institutional ethics determination/waiver and investigator declaration are **not reported**; public availability is not substituted for an institutional decision. |
| 18a–b | Project funding and author conflicts are **not reported**; investigator confirmation required. |
| 18c–f | Protocol: `docs/research-design.md` and `docs/pce-benchmark.md`. Registration identifier: **not reported**. Public source data, download manifests, code and reconstruction steps: `docs/reproducibility.md`. |
| 19 | Patient/public involvement: **not reported**; investigator confirmation required. |
| 20a–c | STROBE ladder, cohort/missingness tables, `reports/pce_results.json` and `reports/tables/pce_participant_characteristics.csv` disclose attrition, outcomes and temporal-group characteristics. Complete subgroup reporting beyond those tables remains limited. |
| 21 | `reports/model_results.json`, `reports/part4_learning_results.json` and `reports/pce_results.json` record model-specific training/test sample sizes and events. |
| 22 | Executable model implementations and `reports/pce_parameters_*.json` supply coefficients, centering and baselines for the benchmark fits. `scripts/build_pce_results.py` specifies preprocessing and prediction integration. Research code requires an expert operator; no clinical scoring application is supplied. |
| 23a–b | Model and PCE result tables report discrimination and paired bootstrap intervals. Calibration and decision curves are point estimates. Comprehensive subgroup calibration intervals and heterogeneity analyses are **not done**. |
| 24 | `reports/pce_results.json` reports original PCE and training-only mortality adaptations on held-out cycles. No recalibration is learned from the evaluation outcomes. |
| 25 | Generated report: mortality ranking, historical benchmark and endpoint mismatch are interpreted together. Performance differences do not establish a clinical advantage. |
| 26 | Generated limitations disclose complete-case selection, four-year weight deviation, single exposure measurement, mortality rather than incidence, perturbed linkage and pre-pandemic transport limits. |
| 27a–c | Input validation fails on invalid PCE data. Use is restricted to research; no missing-input clinical workflow exists. Independent contemporary evaluation, subgroup performance, intervention definition and impact studies are future research. |

The engineering/reporting deliverable can be reproduced while the scientific
limitations and investigator disclosures remain open. Completing a checklist
does not resolve those limitations. Do not label this project TRIPOD-compliant
without addressing the incomplete items for the intended publication.
