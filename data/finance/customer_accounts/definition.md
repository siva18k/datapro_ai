# customer_accounts

Finance domain. Postgres table(s) for customer account balances and status — used for reporting and as a join target when you need account-level detail next to customer or transaction data.

Owned by the finance data team. Batch load runs nightly; don't hammer it with ad-hoc full scans during business hours if you're on a shared instance.

Typical joins: `customer_id` → customers dimension. `account_type` and `status` are the filters people actually use. Balances are in local currency (`currency` column).

No direct PII in this dataset beyond what's needed for account metadata — still treat it as internal-only.
