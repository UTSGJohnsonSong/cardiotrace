# CardioTrace — end-to-end pipeline shortcuts.
# Windows: run these from Git Bash, or run the underlying commands directly.

PY := .venv/Scripts/python.exe

.PHONY: help setup up down data load dbt cohort descriptive learning site benchmark verify all clean

help:
	@echo "setup      create venv + install requirements"
	@echo "up/down    start/stop Dockerized Postgres"
	@echo "data       download NHANES XPT files"
	@echo "load       load raw XPT into Postgres"
	@echo "dbt        build staging + mart models"
	@echo "cohort     build the Part 3 cohort + STROBE ladder"
	@echo "descriptive  Part 1/2 tables, figures and the report"
	@echo "learning   Part 4 screen and arm comparison (~15 min)"
	@echo "site       split the report into docs/ and rebuild the README"
	@echo "benchmark  PCE cascade, four-year weight check, Tableau extract"
	@echo "verify     assert a clean rebuild changes nothing tracked (Part 4 needs --full)"
	@echo "all        up -> data -> load -> dbt -> cohort -> learning -> descriptive -> benchmark -> site"

setup:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

up:
	docker compose up -d

down:
	docker compose down

# The catalog-driven downloader, not the hardcoded one. `data/download.py`
# named 17 modules by hand and treated a 404 as "nothing to download", which is
# how 1999-2004 ended up with no laboratory data at all while the run reported
# success. It now lives in legacy-invalid/ and nothing here points at it.
data:
	$(PY) data/download_from_catalog.py

load:
	$(PY) -m src.etl

dbt:
	cd dbt && ../$(PY) -m dbt build --profiles-dir .

# `analyze` is gone. It ran run_pipeline.py, which overwrote
# reports/results.json with the XGBoost/SHAP cross-sectional analysis built on
# imputed laboratory values for a quarter of the sample. render_readme.py used
# to read that file, so `make all` put those numbers back on the repository
# front page after every run -- a defect that regenerated itself. The pipeline
# is preserved in legacy-invalid/ with its own README; reproducing it now takes
# a deliberate act rather than a build.

# The Part 1 / Part 2 chain. It was outside the build entirely: two of its
# outputs had no producer in the repository at all, so nobody could regenerate
# them and nothing would have detected them drifting out of step with the code.
# The cohort is what `learning` screens and what `descriptive` reports on, so
# it is its own target: `all` has to build it, then run `learning`, and only
# then render. Running `descriptive` first renders the report against the
# PREVIOUS run's Part 4 artefact -- no error, one cycle stale, no signal.
cohort:
	$(PY) scripts/build_cohort_results.py

# `learning` must have run at least once before `descriptive`: render_report.py
# reads reports/part4_learning_results.json and stops with a message naming this
# target if it is absent. `site` then splits the rendered report into docs/.
descriptive: cohort
	$(PY) scripts/build_descriptive_results.py
	$(PY) scripts/build_ascertainment_results.py
	$(PY) scripts/build_missingness_results.py
	$(PY) scripts/make_descriptive_figures.py
	$(PY) scripts/render_report.py

# ~15 minutes: the screen fits one Cox per candidate per step, and the arm
# comparison bootstraps four paired differences over whole variance units.
learning: cohort
	$(PY) scripts/build_learning_results.py
	$(PY) scripts/make_learning_figures.py

site:
	$(PY) scripts/build_site.py
	$(PY) scripts/render_readme.py

# Three artefacts nothing else depends on, so they are their own target rather
# than a silent tail on `descriptive`: the PCE cascade, the four-year weight
# check and the Tableau extract.
benchmark: cohort
	$(PY) scripts/pce_variable_cascade.py
	$(PY) scripts/check_fouryear_weights.py
	$(PY) scripts/build_tableau_extract.py

# The check that stops a committed artefact from outliving the code that wrote
# it. Almost every published number is read out of a file in reports/ or
# data/tableau/, and those files
# are committed; if one drifts, the site shows a number no script produces and
# nothing says so. No flag here means the DEFAULT scope: cohort, descriptive,
# benchmark, models and the renderers -- everything except Part 4, which needs
# `verify_clean_rebuild.py --full` and about fifteen minutes.
verify:
	$(PY) scripts/verify_clean_rebuild.py

all: up data load dbt cohort learning descriptive benchmark site
	@echo "Pipeline complete. See reports/ and docs/."

clean:
	rm -rf reports/figures/*.png reports/tables/*.csv dbt/target dbt/logs
