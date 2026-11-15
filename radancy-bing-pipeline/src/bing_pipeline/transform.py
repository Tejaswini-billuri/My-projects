"""Transform: clean the validated frame and split it into dimension + fact frames.

Each `build_*` function returns a frame whose columns match the matching `bing_stg.*` staging
table that load.py writes, and whose rows are unique on that dim's natural key.

Dims are built "last date wins": if an attribute (e.g. campaign_status) changes across days in
the same file, the row from the latest report_date is kept. That is SCD type 1 behaviour and
matches what the upsert SQL does across runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from bing_pipeline.schema import DELIVERY_COLUMNS

log = logging.getLogger(__name__)

# Frames produced, in the order they must be loaded (parents before children).
DIM_NAMES = ["dim_date", "dim_account", "dim_campaign", "dim_ad_group", "dim_ad", "dim_delivery"]
FACT_NAME = "fact_ad_performance_daily"


# ------------------------------------------------------------------ cleaning

def strip_bing_id(s: pd.Series) -> pd.Series:
    """Bing wraps IDs in brackets in CSV exports ('[2709719083]') -> 2709719083."""
    return s.str.strip().str.strip("[]").astype("int64")


def position_bucket(top_vs_other: pd.Series) -> pd.Series:
    """'Bing and Yahoo! search - Top' -> 'Top'. The network half is already its own column."""
    bucket = top_vs_other.str.rsplit(" - ", n=1).str[-1]
    unknown = ~bucket.isin(["Top", "Other"])
    if unknown.any():
        raise ValueError(f"unexpected 'Top vs. other' values: {top_vs_other[unknown].unique()[:5]}")
    return bucket


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply row-level cleaning; output still has one row per source row."""
    out = df.copy()
    out["customer_id"] = out["customer_id"].astype("int64")
    out["ad_group_id"] = strip_bing_id(out["ad_group_id"])
    out["ad_id"] = strip_bing_id(out["ad_id"])
    out["position_bucket"] = position_bucket(out["top_vs_other"])

    # Empty strings become NULL for every optional text column.
    # (report_date is object-dtyped python dates, so exclude it explicitly.)
    text_cols = (out.select_dtypes(include=["object", "string"]).columns
                 .difference(["dq_flags", "report_date"]))
    out[text_cols] = out[text_cols].apply(lambda s: s.str.strip()).replace("", None)

    # Bing moved from "Destination URL" (legacy ads) to "Final URL"; the export has exactly
    # one of the two per ad. Coalesce so consumers don't need to know the history.
    out["landing_url"] = out["final_url"].fillna(out["destination_url"])
    return out


# ------------------------------------------------------------------ dimensions

def _latest_per_key(df: pd.DataFrame, key: list[str], cols: list[str]) -> pd.DataFrame:
    """One row per natural key, taking attribute values from the latest report_date."""
    return (
        df.sort_values("report_date")
        .drop_duplicates(subset=key, keep="last")[cols]
        .reset_index(drop=True)
    )


def build_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    # Continuous range so a day with no rows in the file still exists for date joins.
    days = pd.date_range(df["report_date"].min(), df["report_date"].max(), freq="D")
    return pd.DataFrame({
        "date_key": days.strftime("%Y%m%d").astype(int),
        "full_date": days.date,
        "year": days.year,
        "quarter": days.quarter,
        "month": days.month,
        "month_name": days.strftime("%B"),
        "day": days.day,
        "day_of_week": days.day_of_week + 1,  # ISO: Monday=1
        "day_name": days.strftime("%A"),
        "iso_week": days.isocalendar().week.astype(int).values,
        "is_weekend": days.day_of_week >= 5,
    })


def build_dim_account(df: pd.DataFrame) -> pd.DataFrame:
    return _latest_per_key(df, ["account_number"],
                           ["account_number", "customer_id", "account_name", "account_status"])


def build_dim_campaign(df: pd.DataFrame) -> pd.DataFrame:
    return _latest_per_key(df, ["account_number", "campaign_name"],
                           ["account_number", "campaign_name", "campaign_status"])


def build_dim_ad_group(df: pd.DataFrame) -> pd.DataFrame:
    # account_number + campaign_name are carried so the upsert can resolve campaign_key.
    return _latest_per_key(df, ["ad_group_id"],
                           ["ad_group_id", "account_number", "campaign_name",
                            "ad_group_name", "ad_group_status"])


def build_dim_ad(df: pd.DataFrame) -> pd.DataFrame:
    return _latest_per_key(df, ["ad_id"],
                           ["ad_id", "ad_group_id", "ad_type", "ad_title", "ad_description",
                            "display_url", "landing_url", "final_url", "destination_url",
                            "tracking_template", "ad_status"])


def build_dim_delivery(df: pd.DataFrame) -> pd.DataFrame:
    return df[DELIVERY_COLUMNS].drop_duplicates().reset_index(drop=True)


def build_fact(df: pd.DataFrame) -> pd.DataFrame:
    # campaign_status is carried as-of-day on the fact (the dim only keeps the current value).
    cols = (["report_date", "ad_id", *DELIVERY_COLUMNS, "impressions", "clicks", "spend",
             "avg_position", "conversions", "assists", "currency_code", "campaign_status",
             "dq_flags", "source_file"])
    return df[cols].rename(columns={"report_date": "full_date"}).reset_index(drop=True)


BUILDERS = {
    "dim_date": build_dim_date,
    "dim_account": build_dim_account,
    "dim_campaign": build_dim_campaign,
    "dim_ad_group": build_dim_ad_group,
    "dim_ad": build_dim_ad,
    "dim_delivery": build_dim_delivery,
    FACT_NAME: build_fact,
}


# ------------------------------------------------------------------ entry point

def transform_frame(validated: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cleaned = clean(validated)
    frames = {name: build(cleaned) for name, build in BUILDERS.items()}
    for name, frame in frames.items():
        log.info("built %-28s %6d rows", name, len(frame))
    return frames


def transform(validated_path: Path, out_dir: Path) -> dict[str, Path]:
    """Write one parquet per dim/fact; returns {table_name: path} for the load tasks."""
    frames = transform_frame(pd.read_parquet(validated_path))
    paths = {}
    for name, frame in frames.items():
        paths[name] = out_dir / f"{name}.parquet"
        frame.to_parquet(paths[name], index=False)
    return paths
