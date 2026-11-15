"""The source contract: what columns the Bing export must have and what we call them.

An explicit mapping (rather than auto-snake-casing) means a renamed or reordered column in a
future export fails loudly in validate instead of silently shifting data.
"""

# Source header -> warehouse column name. Order matches the export, for easy diffing.
SOURCE_COLUMNS: dict[str, str] = {
    "Date": "report_date",
    "Customer": "customer_id",
    "Account number": "account_number",
    "Account name": "account_name",
    "Account status": "account_status",
    "Campaign name": "campaign_name",
    "Campaign status": "campaign_status",
    "Ad group ID": "ad_group_id",
    "Ad group": "ad_group_name",
    "Ad group status": "ad_group_status",
    "Ad ID": "ad_id",
    "Ad description": "ad_description",
    "Ad distribution": "ad_distribution",
    "Ad status": "ad_status",
    "Ad title": "ad_title",
    "Ad type": "ad_type",
    "Tracking Template": "tracking_template",
    "Custom Parameters": "custom_parameters",
    "Final Mobile URL": "final_mobile_url",
    "Final URL": "final_url",
    "Top vs. other": "top_vs_other",
    "Display URL": "display_url",
    "Final App URL": "final_app_url",
    "Destination URL": "destination_url",
    "Device type": "device_type",
    "Device OS": "device_os",
    "Delivered match type": "delivered_match_type",
    "BidMatchType": "bid_match_type",
    "Language": "language",
    "Network": "network",
    "Currency code": "currency_code",
    "Impressions": "impressions",
    "Clicks": "clicks",
    "Spend": "spend",
    "Avg. position": "avg_position",
    "Conversions": "conversions",
    "Assists": "assists",
}

DATE_FORMAT = "%m/%d/%Y"  # US-style, e.g. 1/11/2026

INT_METRICS = ["impressions", "clicks", "conversions", "assists"]
FLOAT_METRICS = ["spend", "avg_position"]
METRICS = INT_METRICS + FLOAT_METRICS

# Columns that must never be empty: anything that participates in a key.
REQUIRED_COLUMNS = [
    "report_date", "customer_id", "account_number", "campaign_name", "ad_group_id", "ad_id",
    "device_type", "device_os", "network", "top_vs_other", "delivered_match_type",
    "bid_match_type", "ad_distribution", "language", "currency_code",
    "impressions", "clicks", "spend", "conversions", "assists",
]

# The fact grain. Uniqueness on these columns is a hard validation rule.
GRAIN_COLUMNS = [
    "report_date", "ad_id", "device_type", "device_os", "network", "top_vs_other",
    "delivered_match_type", "bid_match_type", "ad_distribution", "language",
]

# Columns of dim_delivery (the junk dimension). position_bucket is derived in transform.
DELIVERY_COLUMNS = [
    "device_type", "device_os", "network", "position_bucket",
    "delivered_match_type", "bid_match_type", "ad_distribution", "language",
]
