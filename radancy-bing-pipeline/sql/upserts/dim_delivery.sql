-- Pure junk dimension: the natural key is every column, so there is nothing to update.
INSERT INTO bing.dim_delivery (device_type, device_os, network, position_bucket,
                               delivered_match_type, bid_match_type, ad_distribution, language)
SELECT device_type, device_os, network, position_bucket,
       delivered_match_type, bid_match_type, ad_distribution, language
FROM bing_stg.dim_delivery
ON CONFLICT DO NOTHING;
