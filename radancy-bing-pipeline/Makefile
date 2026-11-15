.PHONY: install test run db-init airflow docker-up docker-down clean

PG_URL ?= postgresql://bing:bing@localhost:5432/bing_dwh
AIRFLOW_HOME := $(CURDIR)/.airflow

install:            ## create the venv and install everything (needs uv: https://docs.astral.sh/uv/)
	uv sync --extra dev

test:               ## unit tests (no database needed)
	uv run pytest -q

db-init:            ## create the warehouse role + database on a local Postgres (idempotent)
	psql -d postgres -c "DO \$$\$$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='bing') THEN CREATE ROLE bing LOGIN PASSWORD 'bing'; END IF; END \$$\$$;"
	psql -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='bing_dwh'" | grep -q 1 || psql -d postgres -c "CREATE DATABASE bing_dwh OWNER bing;"

run:                ## run the full pipeline once, in-process (no Airflow), against $$BING_DWH_URL
	uv run python -m bing_pipeline.pipeline

airflow:            ## run Airflow standalone locally with this repo's DAG folder (UI on :8080, no login)
	AIRFLOW_HOME=$(AIRFLOW_HOME) \
	AIRFLOW__CORE__DAGS_FOLDER=$(CURDIR)/dags \
	AIRFLOW__CORE__LOAD_EXAMPLES=False \
	AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True \
	uv run airflow standalone

dags-check:         ## parse the DAG folder (no metadata DB needed) and fail on import errors
	AIRFLOW_HOME=$(AIRFLOW_HOME) uv run python -c "\
	from airflow.models.dagbag import DagBag; \
	bag = DagBag(dag_folder='dags', include_examples=False); \
	assert not bag.import_errors, bag.import_errors; \
	print('DAGs:', list(bag.dags)); \
	[print(f'  {t.task_id:28s} -> {sorted(t.downstream_task_ids)}') for t in bag.dags['bing_ads_daily'].tasks]"

dags-test:          ## execute the DAG once end-to-end with Airflow's test runner (needs Postgres up)
	AIRFLOW_HOME=$(AIRFLOW_HOME) AIRFLOW__CORE__DAGS_FOLDER=$(CURDIR)/dags AIRFLOW__CORE__LOAD_EXAMPLES=False \
	uv run airflow db migrate >/dev/null 2>&1 && \
	AIRFLOW_HOME=$(AIRFLOW_HOME) AIRFLOW__CORE__DAGS_FOLDER=$(CURDIR)/dags AIRFLOW__CORE__LOAD_EXAMPLES=False \
	uv run airflow dags test bing_ads_daily

docker-up:          ## warehouse + Airflow in containers; UI on http://localhost:8080
	docker compose up --build

docker-down:
	docker compose down -v

clean:
	rm -rf work .airflow .pytest_cache
