# Trino for business data

DATA Pro uses **two database layers**:

| Layer | Purpose | Configured in |
|--------|---------|----------------|
| **Catalog Postgres** | Metadata, domains, datasets, RAG vectors | Settings → Catalog database (`.env` `DATABASE_URL`) — **PostgreSQL** via psycopg |
| **Trino** | All business/warehouse SQL (Ask, Analytics, table discovery) | Settings → Trino coordinator + catalog bindings |

Ask SQL generation picks dialect from the dataset connector: **Trino** (`catalog.schema.table`, `DATE '…'` literals) for `connector=trino`; **PostgreSQL** (`schema.table`) for legacy direct Postgres datasets. File/upload datasets use the code path, not SQL.

Trino is the preferred path for shared warehouse access, but DATA Pro also supports direct Postgres datasets when you want a native pg8000-backed connection. The catalog database (psycopg → Postgres metadata/RAG) is never queried for warehouse facts.

## Local development (Podman)

`podman compose up --build` starts:

| Service | Port | Role |
|---------|------|------|
| `datapro-db` | 5432 | Catalog Postgres + optional `finance_data` seed schema |
| `datapro-trino` | **8081** → 8080 | Trino coordinator (single-node dev) |
| `datapro-api` | 8080 | Uses `TRINO_HOST=trino` inside Compose |

### 1. Start the stack

```bash
cp .env.example .env
podman compose up --build
```

Or from **Settings** (bottom): use **Trino coordinator → Start** to run `podman compose up -d trino` only while API/UI run locally.

### 2. Load demo finance tables (optional)

```bash
podman compose run --rm api python scripts/migrate_finance_data.py --fresh
```

### 3. Configure Settings

1. Open **Settings → Database connections**
2. **Trino coordinator**: host `localhost`, port `8081` (or `trino` / `8080` from another container on the Compose network)
3. Click **Test Trino**
4. **Add connection**: pick a **warehouse type** (PostgreSQL, MySQL, Snowflake, etc.), name `Finance_DB`, catalog `finance`, schema `finance_data`, then warehouse credentials
5. Click **Test** on the binding (checks `SHOW TABLES FROM finance.finance_data`)
6. **Save catalog & service settings**

## Supported warehouse types

Each business connection is a Trino **catalog**. In **Settings → Database connections → Add connection**, choose the warehouse type; DATA Pro generates the matching `connector.name` and JDBC URL (same pattern as Metabase / Superset via Trino).

| Type | Trino connector | Notes |
|------|-----------------|-------|
| PostgreSQL | `postgresql` | Aurora Postgres, AlloyDB, RDS |
| MySQL | `mysql` | MySQL-compatible |
| MariaDB | `mariadb` | Dedicated MariaDB connector |
| SQL Server | `sqlserver` | Azure SQL, on-prem |
| Oracle | `oracle` | Service name or SID |
| Snowflake | `snowflake` | Account, database, warehouse, role |
| Amazon Redshift | `redshift` | Cluster endpoint |
| ClickHouse | `clickhouse` | OLAP |
| Custom JDBC | *(you specify)* | Any other Trino connector |

API: `GET /connections/warehouse-connectors` returns field schemas for the UI.

**Docker note:** The stock `trinodb/trino` image includes common JDBC connectors (PostgreSQL, MySQL, etc.). Cloud connectors (Snowflake, Oracle) may require extra Trino plugins in your image — use **Custom JDBC** or extend `docker/trino` for production.

### 4. Create a dataset

1. **Data Catalog → Add dataset**
2. Format: **Database (Trino)** for warehouse-backed access, or **Database (native Postgres)** for direct access
3. Pick the `Finance_DB` connection when using Trino
4. **Data** tab → **Refresh tables** → add tables to the catalog

### Trino catalog files (local)

Business database credentials live in Trino, not in DATA Pro:

```text
docker/trino/catalog/finance.properties
```

First-time Podman setup (local bundled Postgres):

```bash
cp docker/trino/catalog/finance.properties.example docker/trino/catalog/finance.properties
```

Default local catalog connects to the bundled Postgres `finance_data` schema:

```properties
connector.name=postgresql
connection-url=jdbc:postgresql://db:5432/ragpro
connection-user=ragpro
connection-password=ragpro
```

### Migrating from legacy direct Postgres connections

If `saved_db_connections.json` still has `host` / `port` / `password` rows (old format), run:

```bash
python scripts/migrate_connections_to_trino.py --migrate-datasets
```

This will:

1. Rewrite saved connections as Trino bindings (`catalog` + `schema` only).
2. Generate `docker/trino/catalog/<catalog>.properties` from the old credentials (gitignored).
3. Optionally update catalog datasets still on `connector: postgres`.

Restart Trino after migration: `podman compose restart trino`

## How queries run

1. LLM generates SQL using catalog-qualified names: `finance.finance_data.sales_orders`
2. `execute_readonly_sql` sends the query to Trino (not direct Postgres)
3. Trino routes to the connector configured for catalog `finance`

## AWS (future)

Keep the same split:

| Component | Suggested AWS placement |
|-----------|------------------------|
| Catalog Postgres | Existing Aurora/RDS (unchanged) |
| Trino coordinator + workers | ECS Fargate or EKS (internal ALB) |
| Trino catalog secrets | Secrets Manager → mounted into Trino pods/tasks |
| DATA Pro API | Same VPC private subnets; `TRINO_HOST` = internal ALB DNS |

Environment variables (same names as local):

```bash
TRINO_HOST=trino.internal.example.com
TRINO_PORT=8080
TRINO_USER=datapro
TRINO_PASSWORD=...
TRINO_HTTP_SCHEME=https
TRINO_VERIFY_SSL=true
```

Do **not** expose Trino on the public internet. Register each warehouse (Aurora, Redshift, Snowflake, etc.) as a Trino catalog on the coordinator.

## Legacy direct Postgres datasets

Existing datasets with `connector: postgres` and host/port in `config` still execute via direct `pg8000` until migrated. New datasets should use `connector: trino` with `catalog` + `schema` in config.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Test Trino fails | `podman compose ps` — is `datapro-trino` healthy? |
| Catalog test fails | Catalog file exists under `docker/trino/catalog/` and names match Settings |
| No tables on refresh | Finance seed loaded? Schema name matches binding (`finance_data`) |
| SQL mentions wrong tables | Re-discover tables; LLM prompt uses `catalog.schema.table` |
| Catalog test fails (`JDBC_ERROR`) | `finance.properties` must reach your warehouse — `db:5432` only works when the `db` Compose service is running; for Aurora, set JDBC URL to your RDS host and `podman compose restart trino` |
| `finance_data` not in catalog (Ask error) | Restart API after updates; SQL must use `finance.finance_data.<table>` for Trino |
