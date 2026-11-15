INSERT INTO bing.dim_ad_group (ad_group_id, campaign_key, ad_group_name, ad_group_status)
SELECT s.ad_group_id, c.campaign_key, s.ad_group_name, s.ad_group_status
FROM bing_stg.dim_ad_group s
JOIN bing.dim_account  a ON a.account_number = s.account_number
JOIN bing.dim_campaign c ON c.account_key = a.account_key AND c.campaign_name = s.campaign_name
ON CONFLICT (ad_group_id) DO UPDATE
SET campaign_key    = EXCLUDED.campaign_key,   -- an ad group moved between campaigns: follow it
    ad_group_name   = EXCLUDED.ad_group_name,
    ad_group_status = EXCLUDED.ad_group_status,
    updated_at      = now();
