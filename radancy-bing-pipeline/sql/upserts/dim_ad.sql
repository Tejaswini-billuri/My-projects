INSERT INTO bing.dim_ad (ad_id, ad_group_key, ad_type, ad_title, ad_description, display_url,
                         landing_url, final_url, destination_url, tracking_template, ad_status)
SELECT s.ad_id, g.ad_group_key, s.ad_type, s.ad_title, s.ad_description, s.display_url,
       s.landing_url, s.final_url, s.destination_url, s.tracking_template, s.ad_status
FROM bing_stg.dim_ad s
JOIN bing.dim_ad_group g USING (ad_group_id)
ON CONFLICT (ad_id) DO UPDATE
SET ad_group_key      = EXCLUDED.ad_group_key,
    ad_type           = EXCLUDED.ad_type,
    ad_title          = EXCLUDED.ad_title,
    ad_description    = EXCLUDED.ad_description,
    display_url       = EXCLUDED.display_url,
    landing_url       = EXCLUDED.landing_url,
    final_url         = EXCLUDED.final_url,
    destination_url   = EXCLUDED.destination_url,
    tracking_template = EXCLUDED.tracking_template,
    ad_status         = EXCLUDED.ad_status,
    updated_at        = now();
