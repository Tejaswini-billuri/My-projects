"""Post-load checks: prove the warehouse agrees with the file we just loaded.

Reconciles row counts and metric totals per day between the validated frame and the fact
table (restricted to that file's dates and source_file), then records the run in
`bing.pipeline_run`. A mismatch fails the task so the DAG run is visibly red.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from bing_pipeline.load import get_engine
from bing_pipeline.schema import INT_METRICS

log = logging.getLogger(__name__)

RECONCILE_COLS = ["rows", *INT_METRICS, "spend"]


class ReconciliationError(Exception):
    pass


def warehouse_totals(engine: Engine, source_file: str, dates: list) -> pd.DataFrame:
    sql = text("""
        SELECT d.full_date, COUNT(*) AS rows,
               SUM(f.impressions) AS impressions, SUM(f.clicks) AS clicks,
               SUM(f.conversions) AS conversions, SUM(f.assists) AS assists,
               SUM(f.spend) AS spend
        FROM bing.fact_ad_performance_daily f
        JOIN bing.dim_date d USING (date_key)
        WHERE f.source_file = :source_file AND d.full_date = ANY(:dates)
        GROUP BY d.full_date ORDER BY d.full_date
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"source_file": source_file, "dates": list(dates)})


def source_totals(validated: pd.DataFrame) -> pd.DataFrame:
    g = validated.groupby("report_date")
    out = g.size().rename("rows").to_frame()
    for m in INT_METRICS + ["spend"]:
        out[m] = g[m].sum()
    return out.reset_index().rename(columns={"report_date": "full_date"})


def reconcile(validated: pd.DataFrame, engine: Engine) -> pd.DataFrame:
    source_file = validated["source_file"].iloc[0]
    src = source_totals(validated)
    dwh = warehouse_totals(engine, source_file, src["full_date"].tolist())
    merged = src.merge(dwh, on="full_date", how="outer", suffixes=("_src", "_dwh"), indicator=True)

    problems = []
    if (merged["_merge"] != "both").any():
        problems.append(f"dates missing on one side: {merged.loc[merged._merge != 'both', 'full_date'].tolist()}")
    for col in RECONCILE_COLS:
        # spend is NUMERIC(12,2) in the DB and float in pandas: compare to the cent
        diff = (merged[f"{col}_src"].astype(float) - merged[f"{col}_dwh"].astype(float)).abs()
        if (diff > 0.005).any():
            problems.append(f"{col} differs on {merged.loc[diff > 0.005, 'full_date'].tolist()}")
    if problems:
        raise ReconciliationError("; ".join(problems))
    log.info("reconciled %d days: source and warehouse totals match", len(merged))
    return merged


def record_run(engine: Engine, run_id: str, source_file: str, started_at: datetime,
               rows_extracted: int, rows_loaded: int, dq_summary: dict) -> None:
    import json

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO bing.pipeline_run
                (run_id, source_file, started_at, rows_extracted, rows_loaded, dq_summary)
            VALUES (:run_id, :source_file, :started_at, :rows_extracted, :rows_loaded,
                    CAST(:dq_summary AS jsonb))
            ON CONFLICT (run_id) DO UPDATE
            SET finished_at = now(), rows_loaded = EXCLUDED.rows_loaded,
                dq_summary = EXCLUDED.dq_summary
        """), {"run_id": run_id, "source_file": source_file, "started_at": started_at,
               "rows_extracted": rows_extracted, "rows_loaded": rows_loaded,
               "dq_summary": json.dumps(dq_summary)})


def post_load_checks(validated_path: Path, run_id: str, started_at: datetime,
                     dq_summary: dict, engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    validated = pd.read_parquet(validated_path)
    reconcile(validated, engine)
    record_run(engine, run_id, validated["source_file"].iloc[0], started_at,
               rows_extracted=len(validated), rows_loaded=len(validated), dq_summary=dq_summary)
