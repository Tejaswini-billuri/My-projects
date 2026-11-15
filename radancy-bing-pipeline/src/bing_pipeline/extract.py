"""Extract: read the Bing export exactly as delivered and snapshot it to parquet.

No cleaning happens here on purpose. Every column is read as a string so that the snapshot
is a faithful copy of the source; validate/transform decide what each value means.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def read_source(path: Path) -> pd.DataFrame:
    """Load the CSV with every column as text, preserving empty strings.

    - `utf-8-sig` strips the BOM that Bing's export puts in front of the first header.
    - `keep_default_na=False` stops pandas turning "" / "NA" into NaN: we want to see what
      the source actually contained, and convert deliberately later.
    """
    if not path.exists():
        raise FileNotFoundError(f"source file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"source file has a header but no rows: {path}")
    log.info("read %s rows x %s columns from %s", len(df), df.shape[1], path.name)
    return df


def extract(source_file: Path, out_path: Path) -> Path:
    """Read the CSV and write an untouched parquet snapshot for the downstream tasks."""
    df = read_source(source_file)
    df["source_file"] = source_file.name  # lineage column, carried through to the fact table
    df.to_parquet(out_path, index=False)
    log.info("wrote raw snapshot -> %s", out_path)
    return out_path
