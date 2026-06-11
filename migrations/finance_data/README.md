# finance_data schema migration

Loads a demo **enterprise data warehouse** into PostgreSQL schema **`finance_data`** for structured SQL / analytics testing.

## Run

**Step 1 — DBA / master (once)** if `ragpro_dev` gets `permission denied for database postgres`:

```bash
psql "$DATABASE_URL" -f migrations/finance_data/000_master_bootstrap.sql
```

Run as RDS master, not the app user. This creates schema `finance_data`, grants it to `ragpro_dev`, and enables `uuid-ossp`.

**Step 2 — App user:**

```bash
cd data-pro
source .venv/bin/activate
python scripts/migrate_finance_data.py --fresh
```

Options:

| Flag | Purpose |
|------|---------|
| `--fresh` | `DROP SCHEMA finance_data CASCADE` then rebuild |
| `--all-in-one` | Use `postgres_all_in_one_edw_agentic.sql` (large synthetic dataset, `edw` model) |
| `--dry-run` | Print statements without executing |

Default pipeline uses the **myedw** DDL/seed files with fixes (recommended for catalog demos).

## Source files used

| File | Role |
|------|------|
| `1_1_schema_core.sql` | Reference tables, calendar, extensions |
| `1_2_schema_customer_sales.sql` | Customers, inventory products, sales |
| `1_3_schema_hr_finance_support_docs.sql` | HR, finance, support, documents |
| `1_4_schema_views_sanity.sql` | Views only (sanity SELECTs skipped) |
| `02_myedw_reference_seed.sql` | Reference + calendar data |
| `03_customer_seed.sql` | ~250 customers |
| `05_sales_seed.sql` | Orders, invoices, payments (syntax fix applied) |
| `06_myedw_finance_seed.sql` | GL, AP, journals |
| `migrations/finance_data/seed_*.sql` | Fixed product, HR, support, analytics seeds |

## Source files skipped (and why)

| File | Reason |
|------|--------|
| `00_myedw_check_data.sql` | Validation SELECTs only |
| `04_inventory_ddl.sql` | Conflicts with `inventory_products` in `1_2` |
| `04_inventory_seed.sql` | Syntax errors; wrong inventory model |
| `06_schema_hr.sql` | Duplicate HR DDL |
| `07_myedw_hr_seed.sql` | Syntax errors → `seed_hr.sql` |
| `08_myedw_support_seed.sql` | Syntax errors → `seed_support.sql` |
| `09_analytics_fact_sales.sql` | → `seed_analytics.sql` |

## May require master / DBA (one-time)

If `ragpro_dev` cannot create extensions or drop schemas:

```sql
-- As RDS master / superuser
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Optional read-only role (from all-in-one script)
CREATE ROLE finance_data_ro LOGIN PASSWORD 'change-me';
GRANT USAGE ON SCHEMA finance_data TO finance_data_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA finance_data TO finance_data_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT SELECT ON TABLES TO finance_data_ro;
```

`CREATE EXTENSION "uuid-ossp"` is only required for the myedw pipeline (`1_1`). The `--all-in-one` path uses `pgcrypto` instead.

## Connect from Data Catalog

Add a Postgres dataset with:

- **Schema:** `finance_data`
- **Host / DB:** same as `DATABASE_URL` in `.env`
- Test connection → refresh tables → use in Ask (structured path, when wired)


cd data-pro
source .venv/bin/activate
cp .env.example .env   # edit MISTRAL_API_KEY, DATABASE_URL
pip install -r requirements.txt
python scripts/migrate.py
cd web && npm install && cd ..


Start Services
uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
python3 mcp_server.py
cd web &&  npm run dev


