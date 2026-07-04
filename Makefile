# CardioTrace — end-to-end pipeline shortcuts.
# Windows: run these from Git Bash, or run the underlying commands directly.

PY := .venv/Scripts/python.exe

.PHONY: help setup up down data load dbt analyze notebooks all clean

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

notebooks:
	$(PY) scripts/build_notebooks.py
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb

all: up data load dbt analyze
	@echo "Pipeline complete. See reports/ and dashboard/data/."

clean:
	rm -rf reports/figures/*.png reports/tables/*.csv dbt/target dbt/logs
