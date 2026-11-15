-- Analytics views on top of the star schema. These are what BI tools and Insights Agents
-- should query: fully denormalised, with the standard paid-search ratios precomputed so every
-- consumer gets the same CTR / CPC / CVR definition (and the same divide-by-zero handling).

-- Drop first: CREATE OR REPLACE VIEW can only append columns, never insert or reorder them.
-- Views hold no data and 003_comments.sql re-applies their descriptions every run, so a
-- drop/recreate is free. CASCADE takes the two dependent views with it; they are rebuilt below.
DROP VIEW IF EXISTS bing.vw_ad_performance_daily CASCADE;
DROP VIEW IF EXISTS bing.vw_campaign_daily;
DROP VIEW IF EXISTS bing.vw_dq_exceptions;

CREATE VIEW bing.vw_ad_performance_daily AS
SELECT
    d.full_date,
    d.day_name,
    d.is_weekend,
    a.customer_id,
    a.account_number,
    a.account_name,
    c.campaign_name,
    c.campaign_status,                       -- current (from the dim)
    f.campaign_status AS campaign_status_on_date,  -- as reported on full_date (from the fact)
    g.ad_group_id,
    g.ad_group_name,
    ad.ad_id,
    ad.ad_type,
    ad.ad_title,
    ad.ad_description,
    ad.landing_url,
    dl.device_type,
    dl.device_os,
    dl.network,
    dl.position_bucket,
    dl.delivered_match_type,
    dl.bid_match_type,
    f.impressions,
    f.clicks,
    f.spend,
    f.avg_position,
    f.conversions,
    f.assists,
    f.currency_code,
    -- ratios: NULL (not 0) when the denominator is 0 so averages aren't dragged down
    ROUND(f.clicks::numeric      / NULLIF(f.impressions, 0), 4) AS ctr,
    ROUND(f.spend                / NULLIF(f.clicks, 0), 2)      AS cpc,
    ROUND(f.conversions::numeric / NULLIF(f.clicks, 0), 4)      AS cvr,
    ROUND(f.spend                / NULLIF(f.conversions, 0), 2) AS cost_per_conversion,
    f.dq_flags,
    cardinality(f.dq_flags) > 0 AS has_dq_flag
FROM bing.fact_ad_performance_daily f
JOIN bing.dim_date      d  ON d.date_key      = f.date_key
JOIN bing.dim_ad        ad ON ad.ad_key       = f.ad_key
JOIN bing.dim_ad_group  g  ON g.ad_group_key  = ad.ad_group_key
JOIN bing.dim_campaign  c  ON c.campaign_key  = g.campaign_key
JOIN bing.dim_account   a  ON a.account_key   = c.account_key
JOIN bing.dim_delivery  dl ON dl.delivery_key = f.delivery_key;

-- Campaign x day rollup: the most common question shape ("how did campaign X do this week?").
CREATE VIEW bing.vw_campaign_daily AS
SELECT
    full_date,
    account_name,
    campaign_name,
    campaign_status_on_date,   -- a daily rollup wants the status that applied that day
    SUM(impressions)  AS impressions,
    SUM(clicks)       AS clicks,
    SUM(spend)        AS spend,
    SUM(conversions)  AS conversions,
    SUM(assists)      AS assists,
    ROUND(SUM(clicks)::numeric      / NULLIF(SUM(impressions), 0), 4) AS ctr,
    ROUND(SUM(spend)                / NULLIF(SUM(clicks), 0), 2)      AS cpc,
    ROUND(SUM(conversions)::numeric / NULLIF(SUM(clicks), 0), 4)      AS cvr,
    -- impression-weighted average position (a plain AVG over rows would be misleading)
    ROUND(SUM(avg_position * impressions) / NULLIF(SUM(impressions), 0), 2) AS avg_position
FROM bing.vw_ad_performance_daily
GROUP BY full_date, account_name, campaign_name, campaign_status_on_date;

-- Rows that failed a soft validation rule. Kept in the fact (so totals reconcile with the
-- source) but exposed here so analysts / agents can exclude or investigate them.
CREATE VIEW bing.vw_dq_exceptions AS
SELECT full_date, account_name, campaign_name, ad_id, device_type, network,
       impressions, clicks, spend, avg_position, conversions, dq_flags
FROM bing.vw_ad_performance_daily
WHERE has_dq_flag;
