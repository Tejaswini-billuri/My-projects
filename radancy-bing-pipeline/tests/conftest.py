import pandas as pd
import pytest

from bing_pipeline.schema import SOURCE_COLUMNS

# A minimal, realistic raw row (every value a string, as extract produces it).
BASE_ROW = {
    "Date": "1/11/2026", "Customer": "43235", "Account number": "X00086N2",
    "Account name": "atlanta-ATT", "Account status": "Active", "Campaign name": "Brand",
    "Campaign status": "Active", "Ad group ID": "[2709719083]", "Ad group": "AT&T",
    "Ad group status": "Active", "Ad ID": "[6772783690]",
    "Ad description": "We're connecting the world.", "Ad distribution": "Search",
    "Ad status": "Active", "Ad title": "Jobs at AT&T", "Ad type": "Text ad",
    "Tracking Template": "", "Custom Parameters": "", "Final Mobile URL": "", "Final URL": "",
    "Top vs. other": "Bing and Yahoo! search - Top", "Display URL": "att.jobs",
    "Final App URL": "", "Destination URL": "https://connect.att.jobs",
    "Device type": "Computer", "Device OS": "Unknown", "Delivered match type": "Exact",
    "BidMatchType": "Exact", "Language": "English", "Network": "Bing and Yahoo! search",
    "Currency code": "USD", "Impressions": "5", "Clicks": "1", "Spend": "0.3",
    "Avg. position": "1.11", "Conversions": "0", "Assists": "0",
}
assert set(BASE_ROW) == set(SOURCE_COLUMNS)


def make_raw(*overrides: dict) -> pd.DataFrame:
    """Build a raw frame of N rows, each BASE_ROW with the given overrides applied."""
    rows = [{**BASE_ROW, **o, "source_file": "test.csv"} for o in (overrides or [{}])]
    return pd.DataFrame(rows, dtype=str)


@pytest.fixture
def make_raw_frame():
    return make_raw
