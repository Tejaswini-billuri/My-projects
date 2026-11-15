"""Run the whole pipeline in-process, without Airflow.

This is the same sequence of calls the DAG makes, wired together directly. It exists so the
pipeline can be (a) run by a reviewer in ten seconds, (b) used as an integration test, and
(c) debugged with a plain debugger. The DAG is a thin orchestration layer over these steps.

    uv run python -m bing_pipeline.pipeline [path/to/file.csv]
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bing_pipeline import checks, extract, load, transform, validate
from bing_pipeline.config import settings

log = logging.getLogger(__name__)


def run(source_file: Path, run_id: str | None = None) -> dict:
    run_id = run_id or f"local__{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)
    run_dir = settings.run_dir(run_id)
    engine = load.get_engine()

    raw_path = extract.extract(source_file, run_dir / "raw.parquet")
    validated_path, dq_summary = validate.validate(raw_path, run_dir / "validated.parquet")
    table_paths = transform.transform(validated_path, run_dir)

    load.apply_ddl(engine)
    for name in transform.DIM_NAMES:
        load.load_table(name, table_paths[name], engine)
    rows_loaded = load.load_table(transform.FACT_NAME, table_paths[transform.FACT_NAME], engine)

    checks.post_load_checks(validated_path, run_id, started_at, dq_summary, engine)
    log.info("run %s complete: %d fact rows loaded", run_id, rows_loaded)
    return {"run_id": run_id, "rows_loaded": rows_loaded, "dq_summary": dq_summary}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.source_file
    run(src)
