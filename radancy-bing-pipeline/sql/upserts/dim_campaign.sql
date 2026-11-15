-- Staging carries the parent's natural key (account_number); resolve to the surrogate here.
INSERT INTO bing.dim_campaign (account_key, campaign_name, campaign_status)
SELECT a.account_key, s.campaign_name, s.campaign_status
FROM bing_stg.dim_campaign s
JOIN bing.dim_account a USING (account_number)
ON CONFLICT (account_key, campaign_name) DO UPDATE
SET campaign_status = EXCLUDED.campaign_status,
    updated_at      = now();
