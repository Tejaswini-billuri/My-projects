INSERT INTO bing.dim_account (account_number, customer_id, account_name, account_status)
SELECT account_number, customer_id, account_name, account_status
FROM bing_stg.dim_account
ON CONFLICT (account_number) DO UPDATE
SET customer_id    = EXCLUDED.customer_id,
    account_name   = EXCLUDED.account_name,
    account_status = EXCLUDED.account_status,
    updated_at     = now();
