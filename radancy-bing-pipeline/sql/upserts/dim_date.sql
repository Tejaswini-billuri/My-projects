-- Staging columns match the dim exactly; dates are immutable so conflicts are a no-op.
INSERT INTO bing.dim_date (date_key, full_date, year, quarter, month, month_name, day,
                           day_of_week, day_name, iso_week, is_weekend)
SELECT date_key, full_date, year, quarter, month, month_name, day,
       day_of_week, day_name, iso_week, is_weekend
FROM bing_stg.dim_date
ON CONFLICT (date_key) DO NOTHING;
