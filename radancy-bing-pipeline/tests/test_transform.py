import pandas as pd
import pytest

from bing_pipeline.schema import DELIVERY_COLUMNS
from bing_pipeline.transform import (
    DIM_NAMES, FACT_NAME, clean, position_bucket, strip_bing_id, transform_frame,
)
from bing_pipeline.validate import validate_frame


def test_strip_bing_id():
    assert strip_bing_id(pd.Series(["[2709719083]", " [1223756464181231] "])).tolist() == [
        2709719083, 1223756464181231]


def test_position_bucket_splits_on_last_dash():
    s = pd.Series(["Bing and Yahoo! search - Top", "Syndicated search partners - Other"])
    assert position_bucket(s).tolist() == ["Top", "Other"]
    with pytest.raises(ValueError):
        position_bucket(pd.Series(["Bing and Yahoo! search - Sidebar"]))


def test_clean_coalesces_landing_url_and_nulls_blanks(make_raw_frame):
    validated, _ = validate_frame(make_raw_frame(
        {"Final URL": "", "Destination URL": "https://legacy.example"},
        {"Device type": "Tablet", "Final URL": "https://new.example", "Destination URL": ""},
    ))
    out = clean(validated)
    assert out["landing_url"].tolist() == ["https://legacy.example", "https://new.example"]
    assert out["tracking_template"].isna().all()       # "" -> NULL
    assert out["ad_group_id"].dtype == "int64"


def test_transform_produces_every_table_with_unique_keys(make_raw_frame):
    # Two days, same ad; campaign status changes on day 2 -> dim takes the latest value.
    validated, _ = validate_frame(make_raw_frame(
        {"Date": "1/11/2026", "Campaign status": "Active"},
        {"Date": "1/13/2026", "Campaign status": "Paused"},
    ))
    frames = transform_frame(validated)
    assert set(frames) == {*DIM_NAMES, FACT_NAME}

    assert frames["dim_date"]["full_date"].astype(str).tolist() == [
        "2026-01-11", "2026-01-12", "2026-01-13"]            # continuous range, gap filled
    assert len(frames["dim_account"]) == 1
    assert frames["dim_campaign"]["campaign_status"].tolist() == ["Paused"]
    assert len(frames["dim_ad"]) == 1 and frames["dim_ad"]["ad_id"].iloc[0] == 6772783690
    assert not frames["dim_delivery"].duplicated(DELIVERY_COLUMNS).any()
    assert len(frames[FACT_NAME]) == 2
    assert frames[FACT_NAME]["source_file"].eq("test.csv").all()
    # as-of-day status is kept on the fact even though the dim only holds the latest
    assert frames[FACT_NAME]["campaign_status"].tolist() == ["Active", "Paused"]
