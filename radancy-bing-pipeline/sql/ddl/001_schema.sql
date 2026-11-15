-- Bing Ads performance warehouse: star schema.
--
-- Grain of the fact: one row per (date, ad, delivery context). "Delivery context" is the
-- combination of device / OS / network / position bucket / match types — modelled as a junk
-- dimension (dim_delivery) so the fact carries 3 foreign keys instead of 10 low-cardinality
-- text columns. Verified unique on the source file in validate.py (hard check).
--
-- Hierarchy: customer -> account -> campaign -> ad_group -> ad. Customer is folded into
-- dim_account (only 3 customers; a separate dim would be a 1:1 row-per-account for most).
-- Campaign has no ID in the export, so its natural key is (account, campaign_name).
--
-- All dims are SCD type 1 (last load wins). Every DDL statement is idempotent so it can be
-- re-applied on every run.

CREATE SCHEMA IF NOT EXISTS bing;      -- warehouse (dims, facts, views, run audit)
CREATE SCHEMA IF NOT EXISTS bing_stg;  -- per-run staging tables, truncated/replaced each run

-- ---------------------------------------------------------------- dimensions

CREATE TABLE IF NOT EXISTS bing.dim_date (
    date_key      INTEGER PRIMARY KEY,          -- yyyymmdd, human-readable surrogate
    full_date     DATE NOT NULL UNIQUE,
    year          SMALLINT NOT NULL,
    quarter       SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    month_name    TEXT NOT NULL,
    day           SMALLINT NOT NULL,
    day_of_week   SMALLINT NOT NULL,            -- 1 = Monday ... 7 = Sunday (ISO)
    day_name      TEXT NOT NULL,
    iso_week      SMALLINT NOT NULL,
    is_weekend    BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS bing.dim_account (
    account_key     SERIAL PRIMARY KEY,
    account_number  TEXT NOT NULL UNIQUE,       -- natural key, e.g. 'X00086N2'
    customer_id     BIGINT NOT NULL,
    account_name    TEXT NOT NULL,
    account_status  TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bing.dim_campaign (
    campaign_key     SERIAL PRIMARY KEY,
    account_key      INTEGER NOT NULL REFERENCES bing.dim_account (account_key),
    campaign_name    TEXT NOT NULL,
    campaign_status  TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_key, campaign_name)         -- names repeat across accounts ("Brand", "Store")
);

CREATE TABLE IF NOT EXISTS bing.dim_ad_group (
    ad_group_key     SERIAL PRIMARY KEY,
    ad_group_id      BIGINT NOT NULL UNIQUE,    -- Bing's ID, brackets stripped from source
    campaign_key     INTEGER NOT NULL REFERENCES bing.dim_campaign (campaign_key),
    ad_group_name    TEXT NOT NULL,
    ad_group_status  TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bing.dim_ad (
    ad_key             SERIAL PRIMARY KEY,
    ad_id              BIGINT NOT NULL UNIQUE,  -- Bing's ID, brackets stripped from source
    ad_group_key       INTEGER NOT NULL REFERENCES bing.dim_ad_group (ad_group_key),
    ad_type            TEXT NOT NULL,           -- 'Text ad' | 'Expanded text ad'
    ad_title           TEXT,                    -- NULL for every Expanded text ad in the export
    ad_description     TEXT,
    display_url        TEXT,
    landing_url        TEXT,                    -- COALESCE(final_url, destination_url)
    final_url          TEXT,                    -- raw, kept for lineage
    destination_url    TEXT,                    -- raw, legacy ads only
    tracking_template  TEXT,
    ad_status          TEXT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Junk dimension: every distinct combination of the low-cardinality delivery attributes.
CREATE TABLE IF NOT EXISTS bing.dim_delivery (
    delivery_key          SERIAL PRIMARY KEY,
    device_type           TEXT NOT NULL,        -- Computer | Smartphone | Tablet
    device_os             TEXT NOT NULL,
    network               TEXT NOT NULL,        -- Bing and Yahoo! search | AOL search | Syndicated
    position_bucket       TEXT NOT NULL,        -- Top | Other  (derived from "Top vs. other")
    delivered_match_type  TEXT NOT NULL,
    bid_match_type        TEXT NOT NULL,
    ad_distribution       TEXT NOT NULL,
    language              TEXT NOT NULL,
    UNIQUE (device_type, device_os, network, position_bucket,
            delivered_match_type, bid_match_type, ad_distribution, language)
);

-- ---------------------------------------------------------------- fact

CREATE TABLE IF NOT EXISTS bing.fact_ad_performance_daily (
    date_key       INTEGER NOT NULL REFERENCES bing.dim_date (date_key),
    ad_key         INTEGER NOT NULL REFERENCES bing.dim_ad (ad_key),
    delivery_key   INTEGER NOT NULL REFERENCES bing.dim_delivery (delivery_key),
    impressions    INTEGER NOT NULL,
    clicks         INTEGER NOT NULL,
    spend          NUMERIC(12, 2) NOT NULL,
    avg_position   NUMERIC(6, 2),               -- nullable: blank in source when no impressions
    conversions    INTEGER NOT NULL,
    assists        INTEGER NOT NULL,
    currency_code  CHAR(3) NOT NULL,
    -- Status as reported on this day. The dim holds the *current* status (SCD1); keeping the
    -- as-of-day value here answers "spend while paused?" without SCD2 machinery.
    campaign_status TEXT,
    dq_flags       TEXT[] NOT NULL DEFAULT '{}', -- soft validation failures, e.g. CLICKS_GT_IMPRESSIONS
    source_file    TEXT NOT NULL,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date_key, ad_key, delivery_key)
);

-- Additive migrations for databases created before a column existed (no-ops on fresh installs).
ALTER TABLE bing.fact_ad_performance_daily ADD COLUMN IF NOT EXISTS campaign_status TEXT;

CREATE INDEX IF NOT EXISTS ix_fact_ad_perf_ad        ON bing.fact_ad_performance_daily (ad_key);
CREATE INDEX IF NOT EXISTS ix_fact_ad_perf_delivery  ON bing.fact_ad_performance_daily (delivery_key);

-- ---------------------------------------------------------------- run audit

CREATE TABLE IF NOT EXISTS bing.pipeline_run (
    run_id          TEXT PRIMARY KEY,           -- Airflow run_id (or a uuid for local runs)
    source_file     TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    rows_extracted  INTEGER NOT NULL,
    rows_loaded     INTEGER NOT NULL,
    dq_summary      JSONB NOT NULL              -- counts per soft-check flag
);
