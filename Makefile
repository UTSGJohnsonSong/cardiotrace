# CardioTrace — end-to-end pipeline shortcuts.
# Windows: run these from Git Bash, or run the underlying commands directly.

PY := .venv/Scripts/python.exe

.PHONY: help setup up down data load dbt analyze descriptive learning site notebooks all clean

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
# `learning` must have run at least once before `descriptive`: render_report.py
# reads reports/part4_learning_results.json and stops with a message naming this
# target if it is absent. `site` then splits the rendered report into docs/.
descriptive:
	$(PY) scripts/build_cohort_results.py
	$(PY) scripts/build_descriptive_results.py
	$(PY) scripts/build_ascertainment_results.py
	$(PY) scripts/make_descriptive_figures.py
	$(PY) scripts/render_report.py

# ~15 minutes: the screen fits one Cox per candidate per step, and the arm
# comparison bootstraps four paired differences over whole variance units.
learning:
	$(PY) scripts/build_learning_results.py
	$(PY) scripts/make_learning_figures.py

site:
	$(PY) scripts/build_site.py
	$(PY) scripts/render_readme.py

notebooks:
	$(PY) scripts/build_notebooks.py
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb

all: up data load dbt analyze
	@echo "Pipeline complete. See reports/ and dashboard/data/."

clean:
	rm -rf reports/figures/*.png reports/tables/*.csv dbt/target dbt/logs
