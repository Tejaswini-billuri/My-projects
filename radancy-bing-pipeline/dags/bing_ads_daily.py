"""Airflow DAG: load one Bing Ads performance export into the warehouse.

    extract -> validate -> transform -> load_dims (parents before children) -> load_fact
            -> post_load_checks

Tasks hand each other parquet file paths (under work_dir/<run_id>/) via XCom rather than
DataFrames, so every step is restartable on its own and the intermediate data is inspectable.
All real work lives in `bing_pipeline`; this file only sequences it.

Trigger manually with a `source_file` param, or let it default to data/BING_MultiDays.csv.
Re-running for the same file is idempotent (upserts on natural keys / fact grain).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from airflow.sdk import dag, task, task_group

from bing_pipeline import checks, extract, load, transform, validate
from bing_pipeline.config import settings


@dag(
    dag_id="bing_ads_daily",
    schedule=None,  # file-driven: trigger per export (schedule once a landing bucket exists)
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    params={"source_file": str(settings.source_file)},
    default_args={"retries": 1},
    tags=["bing", "ads", "warehouse"],
    doc_md=__doc__,
)
def bing_ads_daily():

    @task
    def extract_task(params: dict, run_id: str) -> str:
        run_dir = settings.run_dir(run_id)
        return str(extract.extract(Path(params["source_file"]), run_dir / "raw.parquet"))

    @task(multiple_outputs=True)
    def validate_task(raw_path: str, run_id: str) -> dict:
        out, summary = validate.validate(Path(raw_path), settings.run_dir(run_id) / "validated.parquet")
        return {"validated_path": str(out), "dq_summary": summary}

    @task
    def transform_task(validated_path: str, run_id: str) -> dict[str, str]:
        paths = transform.transform(Path(validated_path), settings.run_dir(run_id))
        return {name: str(p) for name, p in paths.items()}

    @task
    def apply_ddl_task() -> None:
        load.apply_ddl(load.get_engine())

    @task
    def load_table_task(name: str, table_paths: dict[str, str]) -> int:
        return load.load_table(name, Path(table_paths[name]))

    @task_group
    def load_dims(table_paths: dict[str, str]):
        """dim_date and dim_delivery are independent; the account->campaign->ad_group->ad
        chain must run in order because each upsert joins to its parent's surrogate key."""
        load_table_task.override(task_id="load_dim_date")("dim_date", table_paths)
        load_table_task.override(task_id="load_dim_delivery")("dim_delivery", table_paths)
        (
            load_table_task.override(task_id="load_dim_account")("dim_account", table_paths)
            >> load_table_task.override(task_id="load_dim_campaign")("dim_campaign", table_paths)
            >> load_table_task.override(task_id="load_dim_ad_group")("dim_ad_group", table_paths)
            >> load_table_task.override(task_id="load_dim_ad")("dim_ad", table_paths)
        )

    @task
    def post_load_checks_task(validated_path: str, dq_summary: dict, run_id: str,
                              dag_run) -> None:
        checks.post_load_checks(Path(validated_path), run_id, dag_run.start_date, dq_summary)

    raw = extract_task()
    validated = validate_task(raw)
    tables = transform_task(validated["validated_path"])
    ddl = apply_ddl_task()
    dims = load_dims(tables)
    fact = load_table_task.override(task_id="load_fact")(transform.FACT_NAME, tables)
    ddl >> dims >> fact >> post_load_checks_task(validated["validated_path"], validated["dq_summary"])


bing_ads_daily()
