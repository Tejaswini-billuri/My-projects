-- Column and table descriptions, stored in the catalogue (pg_description) so that anything
-- introspecting the schema — psql \d+, BI tools, an LLM agent reading information_schema —
-- sees what each field means without opening this repo.
--
-- Source of truth is the BASE TABLE column. Postgres does not propagate comments to views,
-- so the DO block at the end copies each view column's description from the base column of
-- the same name; only derived view columns (ratios, flags) are commented explicitly after it.
--
-- Written in business language on purpose; technical notes stay in 001_schema.sql.
-- COMMENT ON replaces, so this file is safe to re-apply every run.

-- ---------------------------------------------------------------- dim_date
COMMENT ON TABLE  bing.dim_date IS 'Calendar dimension, one row per day covered by any load.';
COMMENT ON COLUMN bing.dim_date.date_key    IS 'Surrogate key in yyyymmdd form, e.g. 20260111.';
COMMENT ON COLUMN bing.dim_date.full_date   IS 'Calendar day the ad activity happened on (reporting is daily).';
COMMENT ON COLUMN bing.dim_date.day_name    IS 'Weekday name, e.g. Monday.';
COMMENT ON COLUMN bing.dim_date.day_of_week IS 'ISO weekday number: 1 = Monday ... 7 = Sunday.';
COMMENT ON COLUMN bing.dim_date.iso_week    IS 'ISO-8601 week number.';
COMMENT ON COLUMN bing.dim_date.is_weekend  IS 'TRUE for Saturday and Sunday.';

-- ---------------------------------------------------------------- dim_account
COMMENT ON TABLE  bing.dim_account IS 'Bing Ads accounts (one per employer location), with the owning Radancy customer_id.';
COMMENT ON COLUMN bing.dim_account.account_key    IS 'Surrogate key.';
COMMENT ON COLUMN bing.dim_account.account_number IS 'Bing Ads account ID, e.g. X00086N2. Natural key.';
COMMENT ON COLUMN bing.dim_account.customer_id    IS 'Radancy client number. One customer can own several ad accounts.';
COMMENT ON COLUMN bing.dim_account.account_name   IS 'Human-readable account name, usually "<city>-<employer>" or "<employer> - <site>".';
COMMENT ON COLUMN bing.dim_account.account_status IS 'Account status as of the latest load (Active in all current data).';

-- ---------------------------------------------------------------- dim_campaign
COMMENT ON TABLE  bing.dim_campaign IS 'Campaigns. Natural key is (account_key, campaign_name) because the source has no campaign ID.';
COMMENT ON COLUMN bing.dim_campaign.campaign_key    IS 'Surrogate key.';
COMMENT ON COLUMN bing.dim_campaign.campaign_name   IS 'Budget bucket within an account, named by theme (Brand, Nursing, Retail...). Names repeat across accounts; always pair with the account.';
COMMENT ON COLUMN bing.dim_campaign.campaign_status IS 'Status as of the latest load (SCD1): Active, Paused, or "Budget paused" (daily budget exhausted). Not the status on a given fact date.';

-- ---------------------------------------------------------------- dim_ad_group
COMMENT ON TABLE  bing.dim_ad_group IS 'Ad groups: folders of related keywords and ads within a campaign.';
COMMENT ON COLUMN bing.dim_ad_group.ad_group_key    IS 'Surrogate key.';
COMMENT ON COLUMN bing.dim_ad_group.ad_group_id     IS 'Bing ad group ID (numeric; the source wraps it in brackets). Natural key.';
COMMENT ON COLUMN bing.dim_ad_group.ad_group_name   IS 'Ad group name, e.g. "Nurse Jobs", "Warehouse". Names repeat across campaigns; ad_group_id is unique.';
COMMENT ON COLUMN bing.dim_ad_group.ad_group_status IS 'Status as of the latest load (Active in all current data).';

-- ---------------------------------------------------------------- dim_ad
COMMENT ON TABLE  bing.dim_ad IS 'Individual adverts with their copy and landing URL.';
COMMENT ON COLUMN bing.dim_ad.ad_key            IS 'Surrogate key.';
COMMENT ON COLUMN bing.dim_ad.ad_id             IS 'Bing ad ID (numeric; the source wraps it in brackets). Natural key.';
COMMENT ON COLUMN bing.dim_ad.ad_type           IS '"Text ad" (legacy format) or "Expanded text ad" (newer format whose headlines are not in this export, so ad_title is NULL).';
COMMENT ON COLUMN bing.dim_ad.ad_title          IS 'Headline shown in the ad. NULL for every Expanded text ad.';
COMMENT ON COLUMN bing.dim_ad.ad_description    IS 'One-line pitch shown under the headline.';
COMMENT ON COLUMN bing.dim_ad.display_url       IS 'Friendly web address shown in the ad, e.g. att.jobs.';
COMMENT ON COLUMN bing.dim_ad.landing_url       IS 'Where a click actually goes. Coalesced from final_url (new ads) and destination_url (legacy ads).';
COMMENT ON COLUMN bing.dim_ad.final_url         IS 'Raw "Final URL" from the source; NULL for legacy ads.';
COMMENT ON COLUMN bing.dim_ad.destination_url   IS 'Raw "Destination URL" from the source; NULL for newer ads.';
COMMENT ON COLUMN bing.dim_ad.tracking_template IS 'Click-tracking wrapper URL (DoubleClick) applied before redirecting to landing_url; NULL when none.';
COMMENT ON COLUMN bing.dim_ad.ad_status         IS 'Status as of the latest load (Active in all current data).';

-- ---------------------------------------------------------------- dim_delivery
COMMENT ON TABLE  bing.dim_delivery IS 'Junk dimension: every distinct combination of device, OS, network, page position and match types an ad was served in.';
COMMENT ON COLUMN bing.dim_delivery.delivery_key         IS 'Surrogate key.';
COMMENT ON COLUMN bing.dim_delivery.device_type          IS 'Computer, Smartphone or Tablet.';
COMMENT ON COLUMN bing.dim_delivery.device_os            IS 'Operating system of the device: Windows, iOS, Android, BlackBerry, Other, Unknown.';
COMMENT ON COLUMN bing.dim_delivery.network              IS 'Search engine that showed the ad: "Bing and Yahoo! search", "AOL search", or "Syndicated search partners" (smaller partner sites).';
COMMENT ON COLUMN bing.dim_delivery.position_bucket      IS '"Top" = above the organic results; "Other" = sidebar or below. Derived from the source "Top vs. other" field.';
COMMENT ON COLUMN bing.dim_delivery.delivered_match_type IS 'How closely the user''s search matched the keyword when the ad was shown: Exact, Phrase or Broad.';
COMMENT ON COLUMN bing.dim_delivery.bid_match_type       IS 'Match type the advertiser bid on. Can be looser than delivered_match_type.';
COMMENT ON COLUMN bing.dim_delivery.ad_distribution      IS 'Bing network type; "Search" in all current data.';
COMMENT ON COLUMN bing.dim_delivery.language             IS 'Ad language; "English" in all current data.';

-- ---------------------------------------------------------------- fact
COMMENT ON TABLE  bing.fact_ad_performance_daily IS 'Daily ad metrics. Grain: (date_key, ad_key, delivery_key). Prefer vw_ad_performance_daily for queries.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.impressions   IS 'Number of times the ad was shown. Additive.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.clicks        IS 'Number of clicks on the ad. Additive. Can exceed impressions on a given day due to Bing attribution lag (flagged CLICKS_GT_IMPRESSIONS).';
COMMENT ON COLUMN bing.fact_ad_performance_daily.spend         IS 'Amount charged by Bing, in currency_code. Pay-per-click, so 0 when clicks = 0. Additive.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.avg_position  IS 'Average slot on the results page; 1 is best. NULL when there were no impressions. NOT additive: weight by impressions to aggregate.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.conversions   IS 'Desired outcomes attributed to this ad, typically a started job application. Additive.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.assists       IS 'Times this ad was clicked earlier in a journey where a different ad got credit for the conversion. Additive.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.currency_code IS 'ISO currency of spend. USD throughout the current data.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.campaign_status IS 'Campaign status as reported on this day: Active, Paused, or "Budget paused". Use this (not dim_campaign.campaign_status) for point-in-time questions such as spend while paused.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.dq_flags      IS 'Data-quality warnings on this row, e.g. {CLICKS_GT_IMPRESSIONS}. Empty array when clean. Row is still counted in totals so they match the Bing UI.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.source_file   IS 'Name of the export file this row was last loaded from.';
COMMENT ON COLUMN bing.fact_ad_performance_daily.loaded_at     IS 'When this row was last written by the pipeline.';

COMMENT ON TABLE bing.pipeline_run IS 'One row per pipeline run: which file, how many rows, and data-quality flag counts. Use max(finished_at) for freshness.';

-- ---------------------------------------------------------------- propagate to views
-- For every column of every view in the schema, copy the description of the base-table
-- column with the same name (fact first, then dims). Columns with no base match are skipped
-- and must be commented explicitly below.
DO $$
DECLARE
    v     record;
    c     record;
    descr text;
BEGIN
    FOR v IN SELECT table_name FROM information_schema.views WHERE table_schema = 'bing' LOOP
        FOR c IN SELECT column_name FROM information_schema.columns
                 WHERE table_schema = 'bing' AND table_name = v.table_name LOOP
            SELECT col_description(format('bing.%I', t.table_name)::regclass, t.ordinal_position)
              INTO descr
              FROM information_schema.columns t
             WHERE t.table_schema = 'bing' AND t.column_name = c.column_name
               AND t.table_name IN ('fact_ad_performance_daily', 'dim_date', 'dim_account',
                                    'dim_campaign', 'dim_ad_group', 'dim_ad', 'dim_delivery')
             ORDER BY (t.table_name = 'fact_ad_performance_daily') DESC
             LIMIT 1;
            IF descr IS NOT NULL THEN
                EXECUTE format('COMMENT ON COLUMN bing.%I.%I IS %L', v.table_name, c.column_name, descr);
            END IF;
        END LOOP;
    END LOOP;
END $$;

-- ---------------------------------------------------------------- view-only columns
COMMENT ON VIEW bing.vw_ad_performance_daily IS
  'One row per day x ad x delivery context (device, OS, network, page position, match types). '
  'Start here for any question. Ratios are precomputed; sum the raw counts to roll up, never '
  'average the ratios. avg_position must be weighted by impressions when aggregated.';
COMMENT ON COLUMN bing.vw_ad_performance_daily.ctr                 IS 'Click-through rate = clicks / impressions. NULL when impressions = 0.';
COMMENT ON COLUMN bing.vw_ad_performance_daily.cpc                 IS 'Cost per click = spend / clicks. NULL when clicks = 0.';
COMMENT ON COLUMN bing.vw_ad_performance_daily.cvr                 IS 'Conversion rate = conversions / clicks. NULL when clicks = 0.';
COMMENT ON COLUMN bing.vw_ad_performance_daily.cost_per_conversion IS 'spend / conversions. NULL when conversions = 0.';
COMMENT ON COLUMN bing.vw_ad_performance_daily.has_dq_flag         IS 'TRUE when dq_flags is non-empty. Filter on this to exclude anomalous rows.';
-- campaign_status exists on both fact and dim; the view takes the dim's (current) value, so
-- override the by-name copy (which would have picked the fact's comment).
COMMENT ON COLUMN bing.vw_ad_performance_daily.campaign_status         IS 'CURRENT campaign status from the dimension (SCD1): Active, Paused, or "Budget paused". For the status on full_date use campaign_status_on_date.';
COMMENT ON COLUMN bing.vw_ad_performance_daily.campaign_status_on_date IS 'Campaign status as reported on full_date. Use for point-in-time questions such as "spend while paused".';

COMMENT ON VIEW bing.vw_campaign_daily IS
  'Campaign x day rollup of vw_ad_performance_daily with ratios recomputed from summed counts '
  'and avg_position weighted by impressions. Use for "how did campaign X do this week" questions.';
COMMENT ON COLUMN bing.vw_campaign_daily.avg_position IS 'Impression-weighted average position for the campaign-day. Lower is better.';
COMMENT ON COLUMN bing.vw_campaign_daily.campaign_status_on_date IS 'Campaign status as reported on full_date (Active, Paused, "Budget paused"). Part of the grouping, so a campaign whose status changed mid-week appears once per status.';
COMMENT ON COLUMN bing.vw_campaign_daily.ctr          IS 'Click-through rate for the campaign-day = sum(clicks) / sum(impressions).';
COMMENT ON COLUMN bing.vw_campaign_daily.cpc          IS 'Cost per click for the campaign-day = sum(spend) / sum(clicks).';
COMMENT ON COLUMN bing.vw_campaign_daily.cvr          IS 'Conversion rate for the campaign-day = sum(conversions) / sum(clicks).';

COMMENT ON VIEW bing.vw_dq_exceptions IS
  'Rows from vw_ad_performance_daily that carry at least one data-quality flag. '
  'Use to explain anomalies or to decide what to exclude.';
