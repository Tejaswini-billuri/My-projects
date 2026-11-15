import pytest

from bing_pipeline.validate import ValidationError, validate_frame


def test_clean_frame_passes_and_is_typed(make_raw_frame):
    df, summary = validate_frame(make_raw_frame())
    assert summary["rows"] == 1 and summary["flag_counts"] == {}
    assert str(df["report_date"].iloc[0]) == "2026-01-11"
    assert df["impressions"].iloc[0] == 5 and df["spend"].iloc[0] == pytest.approx(0.3)
    assert df["dq_flags"].iloc[0] == ""


def test_missing_column_is_hard_failure(make_raw_frame):
    raw = make_raw_frame().drop(columns=["Clicks"])
    with pytest.raises(ValidationError, match="missing=\\['Clicks'\\]"):
        validate_frame(raw)


def test_bad_date_is_hard_failure(make_raw_frame):
    with pytest.raises(ValidationError, match="unparsable dates"):
        validate_frame(make_raw_frame({"Date": "2026-01-11"}))  # ISO, not m/d/Y


def test_non_numeric_metric_is_hard_failure(make_raw_frame):
    with pytest.raises(ValidationError, match="non-numeric values in spend"):
        validate_frame(make_raw_frame({"Spend": "$1.20"}))


def test_duplicate_grain_is_hard_failure(make_raw_frame):
    with pytest.raises(ValidationError, match="duplicated at fact grain"):
        validate_frame(make_raw_frame({}, {"Clicks": "9"}))  # same keys, different metric


def test_blank_avg_position_is_allowed(make_raw_frame):
    df, _ = validate_frame(make_raw_frame(
        {"Avg. position": "", "Impressions": "0", "Clicks": "0", "Spend": "0"}))
    assert df["avg_position"].isna().all()
    assert df["dq_flags"].iloc[0] == ""  # only flagged when impressions > 0


def test_soft_rules_flag_but_keep_rows(make_raw_frame):
    df, summary = validate_frame(make_raw_frame(
        {"Impressions": "1", "Clicks": "2"},                                 # Bing click lag
        {"Device type": "Tablet", "Clicks": "0", "Spend": "0", "Conversions": "1"},  # orphan conv.
    ))
    assert len(df) == 2
    assert df["dq_flags"].tolist() == ["CLICKS_GT_IMPRESSIONS", "CONVERSIONS_GT_CLICKS"]
    assert summary["flag_counts"] == {"CLICKS_GT_IMPRESSIONS": 1, "CONVERSIONS_GT_CLICKS": 1}
