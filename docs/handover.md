# CardioTrace — handover

For an assistant picking this project up cold. Written 2026-09-05 against
commit `585ee2f`. Everything below was read out of the repository, not recalled.

Published site: <https://utsgjohnsonsong.github.io/cardiotrace/>
Repository: <https://github.com/UTSGJohnsonSong/cardiotrace>

---

## 0. Read this before you change anything

This project's entire failure history is **silent data loss**: code that assumed
a name, found nothing, and reported success. Nothing raised. The gaps looked
like ordinary missing values, and median imputation downstream turned them into
plausible numbers that reached a published page. If you introduce one of these
again, no test failure will tell you — that is why the rules below are absolute
rather than stylistic.

**1. Never pattern-match an NHANES identifier. Enumerate it.**
Four separate shipped defects came from this one habit:

| what was written | what it did |
|---|---|
| `^[A-Z]+Y$` to detect youth-only modules | matched `TRIGLY`, dropping 8 cycles of lipid data |
| `startswith(stem + "_")` for the cycle suffix | `L13` also matched `L13_2_B`, a second-exam replicate subsample |
| reading health insurance under one column name | `HID010` → `HIQ011`; three cycles silently blank |
| treating a renamed module as absent | `KIQ`/`KIQ020` → `KIQ_U`/`KIQ022` is the same question |

The worst instance: the original downloader hardcoded 17 module names and read a
404 as "that panel wasn't collected". CDC had renamed the laboratory modules
(`LAB13` → `L13` → `TCHOL`+`HDL`), so 1999–2004 entered the warehouse with **no
laboratory data at all** — 15,332 adults, 24.4% of the sample.

The correct pattern is already built. Use it:
`data/build_catalog.py` enumerates all 1,821 published files,
`data/apply_selection_rules.py` records one rule per file, and
`data/build_variable_crosswalk.py` maps analyte × cycle → column name and unit
factor. `src/cohort.py::assert_cycle_coverage` raises on any cycle-wide gap that
is not explicitly declared in `KNOWN_EMPTY`.

**2. `KNOWN_EMPTY` is not a place to silence a failure.**
A real rename was once filed there with a comment that was literally true and
analytically wrong ("KIQ022 is absent from the 1999-2000 module" — it was
renamed). Any entry must record *why no equivalent variable exists*.

**3. `src/models.py::prepare()` is not idempotent and refuses to run twice.**
It adds the Tobin constant to treated participants **in place**. A second call
gives them +20/+5 instead of +10/+5, the fit converges, and the result is a
plausible wrong number. The guard raises if the frame already carries
`design_cluster`. Pass `prepared=True` to the caller instead of re-preparing.

**4. Missing is not "no".** NHANES codes 7/77/777 (refused) and 9/99/999 (don't
know) are missing. Questionnaire *skip patterns* are different and decode
deterministically — never having been told you had hypertension means untreated,
not unknown. Decoding both branches of the BPQ skip took that column from 65.3%
to 0.3% missing. Do not impute what you can decode.

**5. The README's Key Findings block is generated.**
`scripts/render_readme.py` replaces everything between
`<!-- KEY_FINDINGS_START -->` and `<!-- KEY_FINDINGS_END -->` from the results
JSON. Edit the renderer, not the block. Everything outside those markers —
including the site banner at the top — is hand-written and survives.

**6. `legacy-invalid/` must never be reached by a build target.**
It holds the superseded cross-sectional pipeline, kept because the numbers it
produced were published and deleting it would leave no way to answer where they
came from. `make verify` asserts a clean rebuild does not touch it.

**7. Do not delete. Deprecate or archive.** This is a standing instruction from
the repository owner, and it is why `legacy-invalid/` and
`reports/figures/archive/` exist.

---

## 1. What the project is

Three separate studies on NHANES, deliberately **not** sharing a sample:

| | Part 1 — burden | Part 2 — pandemic | Part 3 — cohort | Part 4 — learning |
|---|---|---|---|---|
| Question | how has CVD prevalence moved over 25 years | did the pandemic deflect it | do baseline risk factors predict CVD death | what limits the model — variables or form |
| Sample | 1999–2022, 11 cycles, adults 20+ | same | 1999–2014, adults 40–79, free of CVD at baseline | Part 3 cohort |
| Weight | `WTINT2YR` (interview) | `WTINT2YR` | `WTMEC2YR` (exam) | `WTMEC2YR` |
| Method | survey-weighted prevalence, age-standardised to 2000 US | trend extrapolation with a design-based interval | cause-specific Cox, absolute risk with competing events | candidate screen, arm comparison |

The weight differs by part on purpose: take the weight of the most restrictive
component an estimate depends on. Part 1 is built from interview responses;
using the exam weight would discard the ~9% who were interviewed but never
examined.

**Why the design changed.** The first version regressed self-reported CVD on
markers measured at the same visit. Exposure never preceded outcome, so it
identified prevalent diagnoses rather than predicting risk, and treatment
effects ran backwards — statin users have *lower* cholesterol. Linking to the
National Death Index fixed the time order at the cost of a harder endpoint
(mortality, not incidence).

---

## 2. Current state

**Tests:** 198 collected, 197 passed, 1 skipped, 0 failed
(`reports/test_summary.json`; re-verified 2026-09-05).

**Cohort** (`reports/cohort_results.json`):

| | |
|---|---|
| Participants | 20,736 |
| CVD deaths | 925 |
| Competing deaths | 2,711 |
| Person-years | 235,553 |
| Median / max follow-up | 10.92 / 20.75 years |

**Models** (`reports/model_results.json`):

| | |
|---|---|
| Systolic BP, per 10 mmHg | HR **1.1216** (95% CI 1.0788–1.1661); 1.097 without the Tobin adjustment |
| Prediction, 2005–2008 test @ 10y | Harrell C **0.838** weighted / 0.805 unweighted; n = 5,163, 217 deaths, 4,669 evaluable; predicted 1.96% vs observed 2.02% |
| Prediction, 2009–2014 test @ 5y | Harrell C **0.802** / 0.791; n = 8,801, 170 deaths; predicted 0.69% vs observed 0.74% |

**Design nodes** — 16 total, tracked in `docs/research-design.md`. Thirteen are
locked. Three are open, and they are the work queue:

| node | state |
|---|---|
| 11 missingness | IPCW handles censoring; **complete-case selection bias is unresolved** |
| 15 calibration & benchmark | protocol locked in `docs/pce-benchmark.md` §3.5; **the PCE head-to-head is not implemented** |
| 16 reporting | **TRIPOD checklist and reproducibility package not written** |

---

## 3. How to run it

Python 3.11. `PY := .venv/Scripts/python.exe` (Windows; adjust on POSIX).

```bash
make setup          # venv + requirements
make data           # download NHANES via the catalog-driven downloader
                    # (NOT data/download.py -- that one is in legacy-invalid/)
make cohort         # build the Part 3 cohort + STROBE ladder
make learning       # Part 4 screen and arm comparison  (~15 min)
make descriptive    # Part 1/2 tables, figures, and the report
make benchmark      # PCE cascade, four-year weight check, Tableau extract
make site           # split the report into docs/ and re-render the README
make verify         # assert a clean rebuild changes nothing tracked
make all            # up -> data -> load -> dbt -> cohort -> learning
                    #    -> descriptive -> benchmark -> site
```

**Order matters and the Makefile encodes why.** `descriptive` depends on
`cohort`, and `render_report.py` reads `reports/part4_learning_results.json` —
run `descriptive` before `learning` and the report renders against the previous
run's Part 4 artefact: no error, one cycle stale, no signal.

`cohort` and `descriptive` read from files under `data/`; the Postgres + dbt
layer (`make up`, `load`, `dbt`) is a separate target and the current analysis
chain does not read from it.

`scripts/crosscheck_survey.R` is an independent re-estimation in R's `survey`
package — the same quantities by a different implementation. It needs R; the
Python side runs without it, and `docs/crosscheck-survey.md` records the
comparison.

---

## 4. Repository map

```
data/
  build_catalog.py            enumerate all 1,821 published NHANES files
  apply_selection_rules.py    R0-R5 ladder -> selection_ledger.csv, one rule per file
  download_from_catalog.py    fetch by published URL; raises on any miss; SHA-256 manifest
  build_variable_crosswalk.py analyte x cycle -> column name + unit factor
  download_mortality.py       NCHS Linked Mortality Files
  catalog/                    the ledgers, committed so CI needs no network

src/
  cohort.py         harmonisation, skip-pattern decoding, STROBE exclusions,
                    assert_cycle_coverage
  biomarkers.py     instrument bridging (CREATININE_CALIBRATION, CDC coefficients)
  survival.py       Kaplan-Meier, Aalen-Johansen
  models.py         cause-specific Cox, absolute risk, calibration, prepare()
  descriptive.py    Part 1/2: weighted prevalence, Taylor linearisation, design df
  changepoint.py    Part 2 trend extrapolation
  ascertainment.py  self-report vs measured, the diagnosis-access analysis
  missingness.py    IPCW sensitivity
  screening.py      Part 4 candidate screen
  discrimination.py C-index machinery
  etl.py            XPT -> Postgres (the warehouse layer)

scripts/            build_*_results.py write the JSON; make_*_figures.py draw;
                    render_report.py + build_site.py + render_readme.py publish;
                    verify_clean_rebuild.py is the merge gate
tests/              198 tests; every cohort test is a regression for a shipped defect
docs/               *.html is the published site (GitHub Pages, main /docs)
                    *.md is the design record -- see section 9
reports/            figures, tables, and the results JSON the pages read from
legacy-invalid/     the superseded pipeline. Never referenced by a build target.
```

---

## 5. Invariants you must not break

**Every published number is read from a committed file.** If a committed
artefact and the code that writes it disagree, the site shows a number no script
produces and nothing says so. `scripts/verify_clean_rebuild.py` is the gate:
it rebuilds and asserts no tracked file changed. Run it before proposing a merge.

**`reports/verify_receipt.json` records what was verified, when, at which
commit, over which scope** — `full` (everything including Part 4) and `render`
(report, site, README only). It exists because a merge gate whose evidence is a
recollection is not a gate. When you change a renderer or a results producer,
regenerate the receipt.

**CI runs two jobs** (`.github/workflows/ci.yml`): `pytest -q`, and a clean
rebuild via `verify_clean_rebuild.py --render` that prints the diff if there is
one. Both need full git history.

**`tests/test_doc_consistency.py`** (467 lines) checks that the prose and the
numbers agree — that the README, the report and the design doc do not drift
apart from the JSON. If you change a number, that file will tell you what else
claims it.

---

## 6. Known deviations, stated because they bound the claims

- **1999–2002 does not use the four-year weight.** NCHS guidance says it should.
  The cost is quantified in `scripts/check_fouryear_weights.py`; the deviation
  is recorded at node 12 in `docs/research-design.md`.
- **The aetiologic estimate is an association, not a total causal effect.** The
  measured pressure is already the product of unobserved treatment history, the
  Tobin constant is a convention rather than an identification strategy, and the
  survey selects on being alive. `src/models.py` says this in its own docstring;
  do not upgrade the language.
- **One measurement per person.** NHANES is a series of independent
  cross-sections; the linkage adds an outcome, not repeated exposures. This
  supports baseline risk prediction — the same design as Framingham, PCE,
  SCORE2, QRISK3 — but not dynamic risk updating or time-varying causal effects.
- **Mortality, not incidence.** Non-fatal MI and stroke are invisible, so the
  estimand blends incidence with case fatality.
- **Follow-up ends 2019-12-31.** Training and validation are entirely
  pre-pandemic; transportability after 2020 cannot be tested with public data.
- **Part 2 has one post-pandemic observation**, on an updated NCHS sample
  design. It is reported as an exploratory deviation from an extrapolation, not
  as a quasi-experimental estimate.
- **Public-use mortality linkage is perturbed.** NCHS substitutes synthetic
  follow-up time or cause of death for a small number of records.

---

## 7. Open work, in the order it should be done

1. **PCE head-to-head** (node 15). The protocol is already written in
   `docs/pce-benchmark.md` §3.5 — four specified comparisons, locked 2026-08-19.
   The coefficients and their provenance are in the same file. **Do not write
   PCE coefficients from memory**; that file exists precisely because that is
   how they get wrong.

   **Do not swap the comparator.** PCE stopped being the clinical standard
   during this project (verified 2026-08-22): the 2026 ACC/AHA dyslipidaemia
   guideline and the 2025 hypertension guideline both move to PREVENT-ASCVD,
   and ACC's own calculator now says the pooled cohort equations are no longer
   supported by its clinical policy. The project's response was deliberate and
   is recorded in `docs/pce-benchmark.md` §0: **keep PCE, rename it.** It is now
   a *prespecified historical benchmark*, because the protocol and the
   coefficient transcription were both completed before the guideline moved, and
   changing comparators after seeing which way the field went is choosing a
   design with the answer in view. PREVENT-ASCVD is recorded as the current
   standard and a future comparison — not this round's work, and not a drop-in
   substitution: it needs eGFR, drops the race input, extends down to age 30,
   and defines its outcome differently.
2. **Complete-case selection bias** (node 11). IPCW currently addresses
   censoring only. `src/missingness.py` and
   `reports/tables/part3_missing_sensitivity.csv` are the starting point.
3. **TRIPOD checklist and reproducibility package** (node 16).
4. **Decision-curve analysis** — net benefit, closer to clinical use than the
   C-index, and rarely done.

---

## 8. Working conventions

- Code, comments, docstrings, commit messages: **English**. Explanations to the
  repository owner: **Chinese**.
- Assertions about this codebase must cite the file they came from.
- Conclusions go into files, not only into chat.
- Do not declare one of several candidate documents to be the authoritative one
  without asking; report the conflict instead.
- Commit messages here explain *why*, not *what* — see `git log` for the house
  style. They are part of the artefact: the project's value to a reader includes
  the record of what went wrong and how it was found.

---

## 9. Where the authority lives

| question | file |
|---|---|
| Why is anything the way it is? | `docs/research-design.md` — the protocol, 16 nodes, decision log, reversed decisions struck through rather than deleted |
| What was wrong with the first version? | `docs/methodology-review.md` |
| Did a defect contaminate a published number? | `docs/impact-tracking.md` — per defect, the merge gate |
| Do Python and R agree? | `docs/crosscheck-survey.md` |
| Where do the PCE coefficients come from? | `docs/pce-benchmark.md` |
| The narrative version, for a supervisor | `docs/advisor-briefing.md` |
| What the pages say | `docs/*.html`, generated — edit the renderer, not the HTML |

`docs/consistency-audit.md` is a **proposal that has not been executed**; do not
treat its recommendations as applied.

The repository is the authority for design decisions. The owner also keeps
progress notes in an Obsidian vault at
`D:\A. Obsidian\04 造物\03 HealthTrace\`, which mirrors status but not
rationale — if the two disagree, the repository wins.
