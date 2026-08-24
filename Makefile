# CardioTrace — end-to-end pipeline shortcuts.
# Windows: run these from Git Bash, or run the underlying commands directly.

PY := .venv/Scripts/python.exe

.PHONY: help setup up down data load dbt analyze cohort descriptive learning site notebooks all clean

help:
	@echo "setup      create venv + install requirements"
	@echo "up/down    start/stop Dockerized Postgres"
	@echo "data       download NHANES XPT files"
	@echo "load       load raw XPT into Postgres"
	@echo "dbt        build staging + mart models"
	@echo "analyze    run analysis + models -> reports/"
	@echo "notebooks  build and execute the four notebooks"
	@echo "all        up -> data -> load -> dbt -> analyze"

setup:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

up:
	docker compose up -d

down:
	docker compose down

data:
	$(PY) data/download.py

load:
	$(PY) -m src.etl

dbt:
	cd dbt && ../$(PY) -m dbt build --profiles-dir .

analyze:
	$(PY) run_pipeline.py

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

notebooks:
	$(PY) scripts/build_notebooks.py
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb

# `analyze` runs the DEPRECATED run_pipeline.py, which overwrites
# reports/results.json with the old XGBoost/SHAP analysis -- the one built on
# imputed laboratory values for a quarter of the sample, which
# docs/advisor-briefing.md records as not fit to show. The README used to be
# generated from that file, so `make all` silently put those numbers back on the
# repository front page after every run. render_readme.py now reads the current
# artefacts instead, and `all` no longer runs `analyze`; the target is kept so
# the old pipeline can still be reproduced deliberately, which is not the same
# thing as reproducing it by accident.
all: up data load dbt cohort learning descriptive site
	@echo "Pipeline complete. See reports/ and docs/."

clean:
	rm -rf reports/figures/*.png reports/tables/*.csv dbt/target dbt/logs
