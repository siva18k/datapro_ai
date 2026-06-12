-- Run once as superuser / database owner if the app user cannot CREATE SCHEMA.
-- Replace ragpro below with your app DB user (Docker Compose default: ragpro).
-- After this, run: python scripts/migrate_finance_data.py --fresh

CREATE SCHEMA IF NOT EXISTS finance_data AUTHORIZATION ragpro;

GRANT USAGE, CREATE ON SCHEMA finance_data TO ragpro;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA finance_data TO ragpro;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA finance_data TO ragpro;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT ALL ON TABLES TO ragpro;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT ALL ON SEQUENCES TO ragpro;

-- Required by 1_1_schema_core.sql (myedw pipeline)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Optional: read-only role for BI tools
-- CREATE ROLE finance_data_ro LOGIN PASSWORD 'change-me';
-- GRANT USAGE ON SCHEMA finance_data TO finance_data_ro;
-- GRANT SELECT ON ALL TABLES IN SCHEMA finance_data TO finance_data_ro;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT SELECT ON TABLES TO finance_data_ro;
