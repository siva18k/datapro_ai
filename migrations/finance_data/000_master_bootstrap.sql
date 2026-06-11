-- Run once as RDS master / database owner (ragpro_dev cannot CREATE SCHEMA on postgres DB).
-- After this, run: python scripts/migrate_finance_data.py --fresh

CREATE SCHEMA IF NOT EXISTS finance_data AUTHORIZATION ragpro_dev;

GRANT USAGE, CREATE ON SCHEMA finance_data TO ragpro_dev;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA finance_data TO ragpro_dev;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA finance_data TO ragpro_dev;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT ALL ON TABLES TO ragpro_dev;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT ALL ON SEQUENCES TO ragpro_dev;

-- Required by 1_1_schema_core.sql (myedw pipeline)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Optional: read-only role for BI tools
-- CREATE ROLE finance_data_ro LOGIN PASSWORD 'change-me';
-- GRANT USAGE ON SCHEMA finance_data TO finance_data_ro;
-- GRANT SELECT ON ALL TABLES IN SCHEMA finance_data TO finance_data_ro;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA finance_data GRANT SELECT ON TABLES TO finance_data_ro;
