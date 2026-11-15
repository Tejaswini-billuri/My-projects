-- Resolve every surrogate key in one set-based statement. Inner joins mean a staged row whose
-- dimension is missing silently disappears — load.py compares the affected row count against
-- the staged row count and fails the task if they differ.
INSERT INTO bing.fact_ad_performance_daily
    (date_key, ad_key, delivery_key, impressions, clicks, spend, avg_position,
     conversions, assists, currency_code, campaign_status, dq_flags, source_file, loaded_at)
SELECT d.date_key, a.ad_key, dl.delivery_key,
       s.impressions, s.clicks, s.spend, s.avg_position,
       s.conversions, s.assists, s.currency_code, s.campaign_status,
       COALESCE(string_to_array(NULLIF(s.dq_flags, ''), ','), '{}'),  -- 'A,B' -> {A,B}; ''/NULL -> {}
       s.source_file, now()
FROM bing_stg.fact_ad_performance_daily s
JOIN bing.dim_date     d  ON d.full_date = s.full_date
JOIN bing.dim_ad       a  ON a.ad_id     = s.ad_id
JOIN bing.dim_delivery dl ON dl.device_type          = s.device_type
                         AND dl.device_os            = s.device_os
                         AND dl.network              = s.network
                         AND dl.position_bucket      = s.position_bucket
                         AND dl.delivered_match_type = s.delivered_match_type
                         AND dl.bid_match_type       = s.bid_match_type
                         AND dl.ad_distribution      = s.ad_distribution
                         AND dl.language             = s.language
ON CONFLICT (date_key, ad_key, delivery_key) DO UPDATE
SET impressions   = EXCLUDED.impressions,
    clicks        = EXCLUDED.clicks,
    spend         = EXCLUDED.spend,
    avg_position  = EXCLUDED.avg_position,
    conversions   = EXCLUDED.conversions,
    assists       = EXCLUDED.assists,
    currency_code = EXCLUDED.currency_code,
    campaign_status = EXCLUDED.campaign_status,
    dq_flags      = EXCLUDED.dq_flags,
    source_file   = EXCLUDED.source_file,
    loaded_at     = now();
