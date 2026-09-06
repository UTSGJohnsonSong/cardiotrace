# Reproducing CardioTrace

The source repository, committed results and generated pages form the research
package. Raw NHANES files and local environments are excluded. Preserve the
commit hash and `reports/verify_receipt.json` when sharing a result; a green
test suite is different evidence from a clean rebuild.

## Environment

Use Python 3.11. The analysis constraints in `requirements-analysis-lock.txt`
pin the numerical libraries used for this release. Install the broader project
requirements with those constraints:

```sh
python -m venv .venv
# Windows:
.venv/Scripts/python.exe -m pip install -r requirements.txt -c requirements-analysis-lock.txt
# POSIX equivalent: .venv/bin/python -m pip install -r requirements.txt -c requirements-analysis-lock.txt
```

Activate the environment first, or replace each `python` below with its full
path. `make` defaults to the Windows path; on POSIX use
`make PY=.venv/bin/python <target>`. The lock is an analysis constraint file,
not a claim that every optional notebook/warehouse dependency is frozen.
The `environment` field of each scope in `reports/verify_receipt.json` records
the interpreter, platform and key package versions for that successful build.

## Offline checkout: tests and render consistency

```sh
git clone https://github.com/UTSGJohnsonSong/cardiotrace.git
cd cardiotrace
# Create and activate the environment as above.
python scripts/check_receipt.py
python -m pytest -q
python scripts/verify_clean_rebuild.py --render
```

Use a full-history clone. CI runs this scope on Linux. Tests requiring the local
cohort skip on a fresh checkout; the receipt history check fails on a shallow
CI clone. The renderer consumes committed result JSON/CSV and figures. README
prose outside the Key Findings markers is retained. The handover status block
and structured research summary are generated alongside the report and checked
for drift.

## Raw-data analysis

```sh
python data/download_from_catalog.py
python data/download_from_catalog.py --verify
python data/download_mortality.py
python data/download_mortality.py --verify
python scripts/build_cohort_results.py
python scripts/build_learning_results.py
python scripts/make_learning_figures.py
python scripts/fit_survival_models.py
python scripts/make_survival_figures.py
python scripts/pce_variable_cascade.py
python scripts/build_pce_results.py
python scripts/check_fouryear_weights.py
python scripts/build_tableau_extract.py
python scripts/build_descriptive_results.py
python scripts/build_ascertainment_results.py
python scripts/build_missingness_results.py
python scripts/make_descriptive_figures.py
python -m pytest -q
python scripts/render_report.py
python scripts/build_site.py
python scripts/render_readme.py
python scripts/render_handover.py
python scripts/render_research_summary.py
```

The catalog and selection ledger enumerate the actual published URLs; do not
guess module names. Compare downloaded mortality hashes with the committed
manifest as well as checking the newly written manifest: a downloader must not
be allowed to erase evidence of a CDC revision. In this takeover, local raw and
mortality files were copied from the original project and verified before use.
After downloading, `make analysis` orders the analysis stages without Postgres.
The benchmark adds paired PCE comparisons, model parameters and decision curves.

Inspect and commit regenerated artefacts, then run
`python scripts/verify_clean_rebuild.py --full` from a clean tree. It rebuilds
raw-file hashes and the cohort from those files, then all six named stages including Part 4.
It does not redownload data, validate source truth, run R, or test Postgres/dbt.
Its receipt is written only on success. Commit only the receipt after that run;
the receipt must refer to the same tree apart from the receipt file itself.
`python scripts/check_receipt.py` fails closed on stale evidence, missing
history or uncommitted analysis edits. CI and packaging run this gate.
Local unit tests may skip stale receipt freshness while development is underway;
that skip is not release approval. Never hand-edit `test_summary.json` to make
a renderer green: fix the tests, rerun the full suite, then regenerate pages.
PNG bytes are excluded because font/rendering environments vary; numerical
tables and generated HTML are checked. The check compares tracked text exactly,
so any cross-platform floating-point drift needs inspection rather than a
claim of bitwise numerical portability.

## Independent R check

```sh
python scripts/crosscheck_survey.py
```

R 4.5.2 with `survey` 4.4.8 and `survival` 3.8.3 was used in the original
cross-check. Set `RSCRIPT` to the local executable if necessary. The harness
exports the actual analytic rows to `data/processed/crosscheck/` and compares
Python estimates with R. `reports/tables/crosscheck_part1.csv` and
`reports/tables/crosscheck_part3.csv` are committed so rendering does not need R.
These checks cover the original survey estimators, not the new PCE adaptation.

## Tableau visual companion

The Tableau companion is a reviewed native-workbook snapshot in `docs/tableau/`.
Report/site rendering checks its source and artifact hashes without installing
Tableau. Regenerating the workbook uses separate optional dependencies and a
native Tableau visual review; see [the atlas maintenance guide](tableau-dashboard.md).
The full analysis receipt includes the source/hash gate and regenerated HTML,
not a rerun of Tableau GUI capture. The single-file report embeds the previews.

## Optional warehouse

`make up`, `make load` and `make dbt` require Docker/Postgres and the dbt profile.
The active analysis reads XPT/CSV files directly. Docker service availability
and dbt execution are separate from evidence of a successful analysis rebuild.
Never invoke the superseded pipeline in `legacy-invalid/` through a build target.

## Shareable snapshot

```sh
python scripts/package_reproduction.py --output /absolute/path/cardiotrace.zip
```

The archive contains tracked files and an additional SHA-256 manifest naming
the source commit. It refuses uncommitted tracked changes or untracked source
files, as well as a stale full receipt, so the snapshot has an unambiguous provenance. It contains no raw data,
virtual environment or credentials. The script refuses to write inside the
repository. The ZIP has no Git history: use the manifest commit with a full
Git clone for receipt ancestry checks; the extracted files can run analyses.
Unresolved investigator disclosures and scientific limitations are
listed in `docs/tripod-checklist.md`; a package is not evidence of clinical readiness.
