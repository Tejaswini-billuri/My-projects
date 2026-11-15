-- Metric glossary as data. Column comments (003) describe single fields; this table holds the
-- definitions that span fields or carry caveats — how to roll something up, what to exclude,
-- which rows to treat with suspicion. An agent or analyst reads it with a plain SELECT.
--
-- Seeded idempotently; edit definitions here, not in the database, so they stay versioned.

CREATE TABLE IF NOT EXISTS bing.metric_definitions (
    metric_name     TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    definition      TEXT NOT NULL,        -- plain-language meaning
    sql_expression  TEXT NOT NULL,        -- how to compute it from vw_ad_performance_daily
    aggregation     TEXT NOT NULL,        -- how to roll it up: sum | ratio_of_sums | weighted_avg | none
    caveats         TEXT,                 -- gotchas an analyst or agent should mention
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE bing.metric_definitions IS
  'Glossary of metrics available on vw_ad_performance_daily: meaning, formula, how to aggregate, caveats. '
  'Query this before computing any ratio.';

INSERT INTO bing.metric_definitions
    (metric_name, display_name, definition, sql_expression, aggregation, caveats)
VALUES
  ('impressions', 'Impressions',
   'Number of times the ad was displayed on a search results page.',
   'SUM(impressions)', 'sum',
   NULL),

  ('clicks', 'Clicks',
   'Number of times a user clicked the ad.',
   'SUM(clicks)', 'sum',
   'Can exceed impressions on a single day because Bing may attribute a click to the day before its impression. Such rows carry the CLICKS_GT_IMPRESSIONS flag.'),

  ('spend', 'Spend',
   'Amount charged by Bing for clicks, in currency_code (USD).',
   'SUM(spend)', 'sum',
   'Pay-per-click: spend is always 0 when clicks are 0. Excludes agency fees and any platform discounts.'),

  ('conversions', 'Conversions',
   'Desired outcomes attributed to the ad, typically a started job application.',
   'SUM(conversions)', 'sum',
   'Attribution is last-click within Bing''s window. Rare in this dataset (single digits per week); avoid percentages on small bases.'),

  ('assists', 'Assists',
   'Journeys where this ad was clicked but a different ad received the conversion credit.',
   'SUM(assists)', 'sum',
   'Not additive with conversions (counts a different event). Use to spot ads that start journeys without finishing them.'),

  ('ctr', 'Click-through rate',
   'Share of impressions that resulted in a click.',
   'SUM(clicks)::numeric / NULLIF(SUM(impressions), 0)', 'ratio_of_sums',
   'Never average the per-row ctr column; recompute from summed counts. Can exceed 1.0 on flagged rows.'),

  ('cpc', 'Cost per click',
   'Average amount paid for one click.',
   'SUM(spend) / NULLIF(SUM(clicks), 0)', 'ratio_of_sums',
   'NULL when there are no clicks; do not treat as 0.'),

  ('cvr', 'Conversion rate',
   'Share of clicks that led to a conversion.',
   'SUM(conversions)::numeric / NULLIF(SUM(clicks), 0)', 'ratio_of_sums',
   'Small denominators make this noisy at ad level; prefer campaign or account level over at least a week.'),

  ('cost_per_conversion', 'Cost per conversion',
   'Spend divided by conversions.',
   'SUM(spend) / NULLIF(SUM(conversions), 0)', 'ratio_of_sums',
   'Undefined (NULL) for any slice with zero conversions, which is most ad-level slices.'),

  ('avg_position', 'Average position',
   'Average slot the ad occupied on the results page; 1 is the top.',
   'SUM(avg_position * impressions) / NULLIF(SUM(impressions), 0)', 'weighted_avg',
   'NOT a simple average: weight by impressions. NULL on rows with no impressions. Lower is better.'),

  ('has_dq_flag', 'Data-quality flagged',
   'Whether the row failed a soft validation rule (see dq_flags for which).',
   'has_dq_flag', 'none',
   'Flagged rows are kept so totals match the Bing UI. State whether they were included when reporting ratios.')
ON CONFLICT (metric_name) DO UPDATE
SET display_name   = EXCLUDED.display_name,
    definition     = EXCLUDED.definition,
    sql_expression = EXCLUDED.sql_expression,
    aggregation    = EXCLUDED.aggregation,
    caveats        = EXCLUDED.caveats,
    updated_at     = now();
