# CardioTrace
### A prospective cohort study of cardiovascular mortality, built from linked NHANES cycles

![Python](https://img.shields.io/badge/Python-3.11-blue) ![lifelines](https://img.shields.io/badge/lifelines-survival-6f42c1) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue) ![dbt](https://img.shields.io/badge/dbt-1.11-orange) ![pytest](https://img.shields.io/badge/tests-194%20passing-brightgreen)

CardioTrace ingests **CDC NHANES 1999–2023** and the **NCHS Linked Mortality File**, and
builds a prospective cohort of adults who were free of cardiovascular disease at
baseline, to study **death from cardiovascular causes** over up to 20 years of follow-up.

Survey weights are applied to every population estimate. Competing risks are modelled
rather than censored — deaths from other causes outnumber CVD deaths 2.9 : 1. Every one
of the 1,821 published NHANES files is recorded with the rule that kept or dropped it.

<!-- KEY_FINDINGS_START -->
## Key Findings

- **Crude prevalence rose and age-standardised prevalence fell.** Self-reported cardiovascular disease among US adults 20+ went from 8.0% to 9.4% crude, and from 8.7% to 8.0% once age is standardised to the 2000 US population — across 11 NHANES cycles, N = 62,877, interview weights, design-based intervals. **The reversal is the finding**; the rise is the population ageing.
- **The standardised trend is -0.59 pp per decade** (95% CI -1.22 to +0.04, t(8)). It contains zero: with ten pre-pandemic points and a dispersion estimated from the same ten, the decline is consistent in direction and not established at 95%. The normal-quantile interval, which the earlier version reported, is -1.12 to -0.06.
- **No detectable pandemic deviation.** 2021-2022 sits +0.45 pp from the pre-pandemic trend extrapolated 5.1 years past 2017-2018 (95% CI -0.76 to +1.66). This is an exploratory deviation from an extrapolation, not a quasi-experimental estimate: there is one post-pandemic observation, and NCHS reports that cycle on an updated sample design.
- **Baseline systolic blood pressure predicts later cardiovascular death.** HR 1.122 per 10 mmHg (95% CI 1.078–1.166), survey-design-based on the stratified PSU design via R `survey::svycoxph`, Tobin-adjusted for treatment. Reported as an association with treatment-adjusted baseline pressure, not as a total causal effect.
- **Prediction, validated forward in time:** Harrell C 0.838 at 10 years on held-out later cycles (n = 5,163), survey-weighted and censored at the horizon; 0.805 unweighted. Competing risks modelled, never censored away.
- **What limits that model is the variable set, not its form.** A screen of 15 laboratory candidates against the eleven selected 1 (`log_uacr`), worth +0.0176 in C (95% CI +0.0074 to +0.0275). Gradient boosting on the same eleven is worth -0.0542 — worse than a Cox model on age and sex alone.

_Figures in [`reports/figures/`](reports/figures). Numbers in [`reports/descriptive_results.json`](reports/descriptive_results.json), [`reports/model_results.json`](reports/model_results.json) and [`reports/tables/`](reports/tables). The superseded pipeline and everything it produced are in [`legacy-invalid/`](legacy-invalid), which no build target reaches._
<!-- KEY_FINDINGS_END -->

---

## Why this project is built the way it is

Every non-obvious decision has a written reason in
[`docs/research-design.md`](docs/research-design.md). The ones a reviewer probes first:

- **The outcome had to change.** Linking to the National Death Index fixes the time
  order — exposure at the exam, death observed afterwards — at the cost of a harder
  endpoint. Without it the design cannot support the word "prediction" at all.
- **Baseline CVD becomes an exclusion, not a covariate.** It is a mediator between
  blood pressure and CVD death, so adjusting for it is a Table 2 fallacy; leaving it in
  pools two populations whose death rates differ 4.9-fold into an average with no
  clinical counterpart. Excluding it also makes the cohort comparable to the ASCVD
  Pooled Cohort Equations.
- **Competing risks are modelled, not censored.** Treating other deaths as censoring
  answers "what fraction would die of CVD if it were impossible to die of anything
  else" — a question nobody asks.
- **Validation splits on survey cycle, not at random.** Participants from the same
  primary sampling unit share a neighbourhood, a provider mix and an interviewer, so a
  random K-fold puts correlated people on both sides of the boundary. Splitting on
  cycle also asks whether the score still works on people surveyed later.
- **The cohort stops at 2014 for a measured reason.** From 2015 CDC collapses the
  cause-of-death groups, so cerebrovascular deaths disappear into "other" and the
  outcome definition would change mid-series. Those cycles contribute only ~4% of
  events anyway, because follow-up is short.
- **Survey weights, everywhere, and the right one each time.** NHANES is a stratified
  multi-stage probability sample. The rule is to take the weight of the most restrictive
  component an estimate depends on: the Part 1 prevalence series is built from interview
  responses, so it carries `WTINT2YR`, and Part 3 and the ascertainment series need a
  measured blood pressure, so they carry `WTMEC2YR`. Using the exam weight for an
  interview-only estimate discards the ~9% of respondents who were interviewed but never
  examined, and NCHS's own guidance is to weight to the smallest component. Variance is
  robust and clustered on the masked variance units NCHS releases (`SDMVSTRA` ×
  `SDMVPSU`), which stand in for the true strata and PSUs withheld for disclosure
  control — masked units, not counties.

### What went wrong, and how it was caught

The first version of this pipeline published fabricated numbers, for the reason in the
withdrawal note above. Four separate defects turned out to share one cause:
**pattern-matching identifiers instead of enumerating them.**

| defect | consequence |
|---|---|
| `^[A-Z]+Y$` for youth-only modules | matched `TRIGLY`, dropping 8 cycles of lipid data |
| prefix match for the cycle suffix | `L13` also matched `L13_2_B`, a second-exam replicate subsample |
| health insurance read under one name | `HID010` → `HIQ011`; three cycles blank |
| kidney module treated as absent | `KIQ`/`KIQ020` → `KIQ_U`/`KIQ022`, same question renamed |

None of them raised. Each looked like ordinary missing data, and median imputation
downstream turned the gaps into plausible numbers.

The pipeline now enumerates all 1,821 published files before selecting any, records one
rule per file, resolves column names through a verified per-cycle crosswalk, and fails
the run on any cycle-wide gap that is not explicitly declared. The 194 tests are
regressions for defects that actually shipped.

---

## Architecture

```
CDC NHANES public files, 11 cycles           NCHS Linked Mortality File
      │  build_catalog.py                          │  download_mortality.py
      │    enumerate all 1,821 files               │    SEQN → National Death Index
      │  apply_selection_rules.py                  │    cause of death, months of
      │    R0–R5 ladder → 225 kept                 │    follow-up from the exam
      │  download_from_catalog.py                  │
      │    fetch by published URL, hash, verify    │
      ▼                                            ▼
data/raw/*.XPT                              data/raw_mortality/*.dat
      │                                            │
      │  build_variable_crosswalk.py               │
      │    analyte × cycle → column, unit factor   │
      └──────────────────┬─────────────────────────┘
                         ▼
              src/cohort.py    harmonise · decode skip patterns ·
                               exclude with STROBE accounting
                         ▼
              src/survival.py  Kaplan-Meier · Aalen-Johansen
              src/models.py    cause-specific Cox · absolute risk · calibration
                         ▼
              reports/figures · reports/tables · reports/model_results.json
```

Harmonisation lives in Python rather than SQL because selecting a different column per
cycle is awkward in SQL and untestable without a database. The Dockerized
PostgreSQL + dbt layer remains for the descriptive analyses.

---

## Reproduce it

Prereqs: Python 3.11.

```bash
make setup                                  # .venv + requirements
python data/build_catalog.py                # enumerate every published file
python data/apply_selection_rules.py        # R0-R5 ladder -> selection ledger
python data/download_from_catalog.py        # fetch the 225 kept files (~1 GB)
python data/download_mortality.py           # linked mortality files (~5 MB)
python data/build_variable_crosswalk.py     # resolve per-cycle column names
python -c "from src.cohort import build_cohort; build_cohort()"
python scripts/make_survival_figures.py     # descriptive curves
python scripts/fit_survival_models.py       # Cox + absolute risk + calibration
pytest tests/ -q                            # 194 tests
```

Every download writes a SHA-256 manifest; `--verify` re-hashes against it. CDC revises
public-use files in place without renaming them, so the digests are what prove two runs
read the same bytes.

The test suite needs no downloaded data — fixtures write synthetic XPT files that round
-trip through the same reader the pipeline uses.

---

## Cohort

| | |
|---|---|
| Source | NHANES 1999–2014, 8 cycles, linked to the National Death Index through 2019-12-31 |
| Population | Adults 40–79 (the ASCVD PCE applicability range), free of self-reported CVD at baseline |
| Outcome | Death from diseases of the heart or cerebrovascular disease (`UCOD_LEADING` ∈ {1, 5}) |
| Competing event | Death from any other cause |
| Time origin | The MEC examination, so follow-up starts when the exposures were measured |
| Size | **20,736 participants · 925 CVD deaths · 2,711 competing deaths · 235,553 person-years** |

Participant flow with every exclusion counted:
[`reports/tables/strobe_part3.csv`](reports/tables/strobe_part3.csv).

---

## Repository structure

```
CardioTrace/
├── data/
│   ├── build_catalog.py            # Stage 0: enumerate all 1,821 published files
│   ├── apply_selection_rules.py    # R0-R5 ladder, one rule per file
│   ├── download_from_catalog.py    # fetch by published URL; fails on any miss
│   ├── build_variable_crosswalk.py # analyte x cycle -> column name, unit factor
│   ├── download_mortality.py       # NCHS linked mortality files
│   └── catalog/                    # the ledgers, committed so CI needs no network
├── src/
│   ├── cohort.py                   # harmonisation, skip-pattern decoding, STROBE
│   ├── survival.py                 # Kaplan-Meier, Aalen-Johansen
│   └── models.py                   # cause-specific Cox, absolute risk, calibration
├── scripts/
│   ├── pce_variable_cascade.py     # what each PCE alignment filter costs
│   ├── make_survival_figures.py    # descriptive curves
│   └── fit_survival_models.py      # fit, validate forward in time, calibrate
├── tests/                          # 194 regressions for defects that shipped
├── docs/
│   ├── research-design.md          # the protocol: estimands, node status, decision log
│   ├── impact-tracking.md          # per defect: did it contaminate a published number?
│   ├── methodology-review.md       # the audit that started the rework
│   ├── pce-benchmark.md            # PCE coefficients: provenance and benchmark design
│   └── advisor-briefing.md         # the narrative version
├── dbt/                            # staging + mart, for the descriptive analyses
├── reports/{figures,tables}        # generated artifacts
└── legacy-invalid/                 # the superseded pipeline, kept and never run
```

`legacy-invalid/` holds the first version of this project: a cross-sectional XGBoost model
that regressed self-reported cardiovascular disease on variables measured at the same
visit, on a sample where a quarter of the laboratory values had been imputed because the
downloader treated a 404 as an empty module. It is kept rather than deleted, because the
numbers it produced were published and deleting it would leave no way to answer where they
came from. No build target reaches it, `make verify` proves a clean rebuild does not touch
it, and [`legacy-invalid/README.md`](legacy-invalid/README.md) says what replaced each
file.

---

## Tech stack

| Layer | Tool |
|-------|------|
| Acquisition | `requests`, catalog-driven, SHA-256 manifests |
| Parsing | `pyreadstat` (XPT), fixed-width reader (mortality) |
| Harmonisation | pandas, driven by a verified per-cycle crosswalk |
| Survival | `lifelines` (Cox); Kaplan-Meier and Aalen-Johansen implemented directly |
| Warehouse | PostgreSQL 16 + dbt-core (descriptive layer) |
| Figures | Matplotlib, colourblind-validated palette |
| Testing | pytest, synthetic XPT fixtures |

---

## Limitations

Stated because they bound what the numbers mean, not as a disclaimer.

- **One measurement per person.** NHANES is a series of independent cross-sections; the
  linkage adds an outcome, not repeated exposures. This supports baseline risk
  prediction — the same design as Framingham, PCE, SCORE2 and QRISK3 — but not dynamic
  risk updating or time-varying causal effects. A single measurement also attenuates
  associations through regression dilution.
- **Mortality, not incidence.** Non-fatal myocardial infarction and stroke are
  invisible, so the estimand blends incidence with case fatality.
- **Survivor and institutionalisation bias.** NHANES samples the living,
  non-institutionalised population; people who died young of CVD were never eligible.
- **Self-reported baseline CVD.** Sensitivity is roughly 60–80%, so some true patients
  remain in a cohort described as primary-prevention, biasing effects toward the null.
- **Follow-up ends 2019-12-31.** The model is trained and validated entirely on
  pre-pandemic data; its transportability after 2020 cannot be tested with public data.
- **Two design-based estimators, still 1.2% apart.** Intervals are design-based
  throughout: Taylor linearisation for the prevalence series, `survey::svycoxph` for the
  exposure model. The Python cluster-robust sandwich run beside it differs by a median of
  1.2% on the standard errors, because it does not stratify the ultimate clusters. No term
  changes whether its interval covers the null. See
  [`docs/crosscheck-survey.md`](docs/crosscheck-survey.md).
- **Eight cycles pooled on two-year weights.** NCHS releases four-year examination weights for
  1999–2002 and its guidance is to use them for an analysis spanning those cycles; this one does
  not. The cost was measured rather than assumed: the four-year weights disagree with the
  two-year weights sharply per person (20.6% of participants by more than a fifth) but almost
  cancel in aggregate, moving the blood-pressure hazard ratio from 1.1216 to 1.1233 and no
  coefficient by more than 0.91%. Reproduce with `python scripts/check_fouryear_weights.py`.
- **Complete-case selection is not fully resolved.** The prediction model requires all
  eleven inputs, which drops 10.6% of the cohort (20,736 → 18,529) but 14.6% of the CVD
  deaths (925 → 790) — the people dropped are not a random sample of the cohort.
  [`docs/`](docs/) reports an IPCW sensitivity analysis, but IPCW here reweights for
  CENSORING; it does not repair selection into the complete-case subsample, which remains
  an open limitation rather than a corrected one. Costs per filter:
  [`reports/tables/pce_cascade.csv`](reports/tables/pce_cascade.csv).
- **Diet is unmeasured.** It sits in the causal graph as an unmeasured confounder of the
  blood-pressure effect.

---

## Data

- **Source**: [CDC NHANES](https://wwwn.cdc.gov/nchs/nhanes/) and the
  [NCHS Public-Use Linked Mortality Files](https://www.cdc.gov/nchs/data-linkage/mortality-public.htm).
  Fully de-identified public-use data; no IRB required.
- **Perturbation**: NCHS substitutes synthetic follow-up time or cause of death for a
  small number of records in the public-use linkage, to prevent re-identification.
- **Missing codes**: 7/77/777 (refused) and 9/99/999 (don't know) become missing, never
  "no". Questionnaire skip patterns are decoded deterministically instead — never
  having been told you had hypertension means untreated, not unknown, and decoding both
  skip branches took that column from 65.3% to 0.3% missing.

---

## Part of the HealthTrace platform

CardioTrace is Module 1 of a multi-disease analytics platform on NHANES. The catalog,
rule ladder and variable crosswalk are disease-agnostic and carry over directly.

| Module | Focus | Status |
|--------|-------|--------|
| **CardioTrace** | Cardiovascular disease | ✅ Prospective cohort built |
| NephroTrace | Kidney disease (CKD) | 📋 Planned |
| GutTrace | Digestive & nutrition | 📋 Planned |
