"""Runtime settings, all overridable via environment variables.

Kept as a plain dataclass (no pydantic) so the module imports fast inside the Airflow DAG parser.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"


@dataclass(frozen=True)
class Settings:
    dwh_url: str = field(
        default_factory=lambda: os.environ.get(
            "BING_DWH_URL", "postgresql+psycopg2://bing:bing@localhost:5432/bing_dwh"
        )
    )
    source_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get("BING_SOURCE_FILE", PROJECT_ROOT / "data" / "BING_MultiDays.csv")
        )
    )
    # Intermediate parquet files between tasks live under work_dir/<run_id>/
    work_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("BING_WORK_DIR", PROJECT_ROOT / "work"))
    )
    dwh_schema: str = "bing"
    stg_schema: str = "bing_stg"

    def run_dir(self, run_id: str) -> Path:
        # Airflow run_ids contain ':' and '+' which are legal on POSIX but ugly; keep them anyway
        # so a run's artefacts are trivially matched to its UI entry.
        d = self.work_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()
