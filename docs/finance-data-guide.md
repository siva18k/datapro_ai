# finance_data demo warehouse

Loads a fake enterprise warehouse into Postgres schema `finance_data` so you can try structured SQL and analytics without pointing at a real EDW.

## Run it

**Step 1 — one-time DBA script** if your app database user hits `permission denied for database postgres`:

```bash
psql "$DATABASE_URL" -f migrations/finance_data/000_master_bootstrap.sql
```

Run as a superuser (or RDS master), not the app user. Edit `000_master_bootstrap.sql` first if your app user is not `ragpro` (Docker default). The script creates schema `finance_data`, grants to that user, and enables `uuid-ossp`.

**Step 2 — app user:**

```bash
cd data-pro
source .venv/bin/activate
python scripts/migrate_finance_data.py --fresh
```

Flags:

- `--fresh` — drop and rebuild `finance_data`
- `--all-in-one` — single big script (`postgres_all_in_one_edw_agentic.sql`, synthetic `edw` model)
- `--dry-run` — print SQL, don't execute

Default path uses the myedw DDL/seed files with fixes applied — best for catalog demos.

## What gets loaded

Core schema from `1_1` through `1_4`, reference seeds (`02`, `03`, `05`, `06`), plus fixed seeds in `migrations/finance_data/seed_*.sql` for products, HR, support, analytics.

We skip a few upstream files on purpose:

- `00_myedw_check_data.sql` — validation SELECTs only
- `04_inventory_*` — conflicts with `inventory_products` in `1_2`
- `06_schema_hr.sql` — duplicate HR DDL
- `07_myedw_hr_seed.sql`, `08_myedw_support_seed.sql` — syntax issues; replaced by `seed_hr.sql` / `seed_support.sql`
- `09_analytics_fact_sales.sql` — replaced by `seed_analytics.sql`

## If the app user can't create extensions

Someone with superuser needs:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- optional read-only login
CREATE ROLE finance_data_ro LOGIN PASSWORD 'change-me';
GRANT USAGE ON SCHEMA finance_data TO finance_data_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA finance_data TO finance_data_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT SELECT ON TABLES TO finance_data_ro;
```

`uuid-ossp` is for the myedw pipeline (`1_1`). The `--all-in-one` path uses `pgcrypto` instead.

## Hook it up in the catalog

Add a Postgres dataset:

- schema: `finance_data`
- host/database: same as `DATABASE_URL` in `.env`

Test connection → refresh tables → use in Ask (structured path when that's wired through).
