"""Validate: enforce the source contract and tag suspicious rows.

Two tiers of rules:

* **Hard** rules raise `ValidationError` and stop the run. They cover anything that would make
  the load wrong or ambiguous: unexpected columns, unparsable keys/dates/numbers, duplicate
  rows at the fact grain, negative metrics.
* **Soft** rules never drop a row. They append a flag to `dq_flags`, which lands on the fact
  table so analysts can exclude or investigate. Dropping rows would make the warehouse totals
  disagree with the Bing UI, which is worse than a flagged anomaly.

Output is the renamed, typed frame plus a summary dict (logged, and persisted to pipeline_run).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from bing_pipeline.schema import (
    DATE_FORMAT, FLOAT_METRICS, GRAIN_COLUMNS, INT_METRICS, METRICS, REQUIRED_COLUMNS,
    SOURCE_COLUMNS,
)

log = logging.getLogger(__name__)


class ValidationError(Exception):
    """A hard rule failed; the message says which and shows sample offenders."""


# ------------------------------------------------------------------ hard rules

def check_columns(df: pd.DataFrame) -> None:
    expected = set(SOURCE_COLUMNS)
    actual = set(df.columns) - {"source_file"}
    missing, extra = expected - actual, actual - expected
    if missing or extra:
        raise ValidationError(f"column contract broken: missing={sorted(missing)} extra={sorted(extra)}")


def check_required_not_empty(df: pd.DataFrame) -> None:
    empty = {c: int((df[c] == "").sum()) for c in REQUIRED_COLUMNS}
    offenders = {c: n for c, n in empty.items() if n}
    if offenders:
        raise ValidationError(f"empty values in required columns: {offenders}")


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Parse dates and metrics; any value that does not parse is a hard failure."""
    out = df.copy()

    parsed = pd.to_datetime(out["report_date"], format=DATE_FORMAT, errors="coerce")
    if parsed.isna().any():
        bad = out.loc[parsed.isna(), "report_date"].unique()[:5]
        raise ValidationError(f"unparsable dates (expected {DATE_FORMAT}): {list(bad)}")
    out["report_date"] = parsed.dt.date

    for col in METRICS:
        num = pd.to_numeric(out[col].replace("", None), errors="coerce")
        # blank is tolerated only for avg_position (Bing leaves it empty with 0 impressions)
        unparsable = num.isna() & (out[col] != "")
        if unparsable.any():
            raise ValidationError(f"non-numeric values in {col}: {list(out.loc[unparsable, col].unique()[:5])}")
        if col != "avg_position" and num.isna().any():
            raise ValidationError(f"blank values in {col}")
        if (num < 0).any():
            raise ValidationError(f"negative values in {col}")
        out[col] = num.astype("Int64") if col in INT_METRICS else num.astype("float64")

    return out


def check_grain_unique(df: pd.DataFrame) -> None:
    dupes = df.duplicated(subset=GRAIN_COLUMNS, keep=False)
    if dupes.any():
        sample = df.loc[dupes, GRAIN_COLUMNS].head(5).to_dict("records")
        raise ValidationError(f"{int(dupes.sum())} rows duplicated at fact grain, e.g. {sample}")


# ------------------------------------------------------------------ soft rules

def soft_checks(df: pd.DataFrame) -> pd.Series:
    """Return a comma-joined flag string per row ('' when clean)."""
    rules = {
        # Bing's known reporting lag: a click can be attributed before its impression.
        "CLICKS_GT_IMPRESSIONS": df["clicks"] > df["impressions"],
        "CONVERSIONS_GT_CLICKS": df["conversions"] > df["clicks"],
        "SPEND_WITHOUT_CLICKS": (df["spend"] > 0) & (df["clicks"] == 0),
        "AVG_POSITION_MISSING": df["avg_position"].isna() & (df["impressions"] > 0),
    }
    flags = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    for name, mask in rules.items():
        mask = mask.fillna(False)
        flags[mask] = flags[mask].apply(lambda lst, n=name: lst + [n])
        log.info("soft check %-24s flagged %5d rows", name, int(mask.sum()))
    return flags.str.join(",")


# ------------------------------------------------------------------ entry point

def validate_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    check_columns(raw)
    df = raw.rename(columns=SOURCE_COLUMNS)
    check_required_not_empty(df)
    df = coerce_types(df)
    check_grain_unique(df)
    df["dq_flags"] = soft_checks(df)

    summary = {
        "rows": int(len(df)),
        "date_min": str(df["report_date"].min()),
        "date_max": str(df["report_date"].max()),
        "flag_counts": df["dq_flags"].str.split(",").explode().replace("", None).dropna()
                        .value_counts().to_dict(),
        "totals": {m: float(df[m].sum()) for m in INT_METRICS + ["spend"]},
    }
    log.info("validation summary: %s", summary)
    return df, summary


def validate(raw_path: Path, out_path: Path) -> tuple[Path, dict]:
    df, summary = validate_frame(pd.read_parquet(raw_path))
    df.to_parquet(out_path, index=False)
    return out_path, summary
