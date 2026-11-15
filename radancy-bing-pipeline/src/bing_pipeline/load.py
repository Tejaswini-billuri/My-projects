"""Load: stage each frame in Postgres and merge it into the warehouse with set-based SQL.

Pattern per table:
  1. pandas -> `bing_stg.<table>` (replaced every run; cheap at this volume)
  2. run `sql/upserts/<table>.sql`, an INSERT ... ON CONFLICT that resolves surrogate keys
     by joining on natural keys and updates in place (SCD1 / idempotent fact reload)

Keeping the merge logic in SQL files means a reviewer can read the load without Python, and
re-running the DAG for the same file is a no-op apart from `loaded_at`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from bing_pipeline.config import SQL_DIR, settings

log = logging.getLogger(__name__)


class LoadError(Exception):
    pass


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.dwh_url, future=True)


def _run_sql_file(engine: Engine, path: Path) -> int:
    """Execute a .sql file inside one transaction; returns rowcount of the last statement."""
    # Hand the whole file to the raw psycopg2 cursor: it runs multi-statement scripts natively,
    # semicolons inside SQL comments are harmless, and — unlike going through SQLAlchemy —
    # '%' in PL/pgSQL format() calls is not mistaken for a bind parameter.
    with engine.begin() as conn:
        cur = conn.connection.cursor()
        cur.execute(path.read_text())
        return cur.rowcount


def apply_ddl(engine: Engine) -> None:
    """(Re)create schemas, tables and views. Everything is IF NOT EXISTS / OR REPLACE."""
    for path in sorted((SQL_DIR / "ddl").glob("*.sql")):
        _run_sql_file(engine, path)
        log.info("applied %s", path.name)


def stage_frame(engine: Engine, name: str, frame: pd.DataFrame) -> int:
    frame.to_sql(name, engine, schema=settings.stg_schema, if_exists="replace",
                 index=False, method="multi", chunksize=2000)
    return len(frame)


def upsert_table(engine: Engine, name: str) -> int:
    affected = _run_sql_file(engine, SQL_DIR / "upserts" / f"{name}.sql")
    log.info("upsert %-28s affected %6d rows", name, affected)
    return affected


def load_table(name: str, parquet_path: Path, engine: Engine | None = None) -> int:
    """Stage + upsert one table. Fails if the fact lost rows to a missing dimension."""
    engine = engine or get_engine()
    frame = pd.read_parquet(parquet_path)
    staged = stage_frame(engine, name, frame)
    affected = upsert_table(engine, name)
    # Dims legitimately affect fewer rows than staged (ON CONFLICT DO NOTHING on dim_date /
    # dim_delivery). The fact must never: every staged row has to find all three dims.
    if name.startswith("fact") and affected != staged:
        raise LoadError(
            f"{name}: staged {staged} rows but upsert affected {affected} — "
            "some rows found no matching dimension row (orphan keys)"
        )
    return affected
