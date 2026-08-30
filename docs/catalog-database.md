# Catalog database (metadata + RAG storage)

DATA Pro uses **one PostgreSQL database** as its main backend store. Every clone should point the app at **your own** instance of this database — it is not shared across users and is **not** checked into git.

This database is sometimes called the **catalog database** or **metadata database**. It holds:

| What | Tables / objects | Used by |
|------|------------------|---------|
| **Catalog metadata** | `domains`, `data_sources`, `rag_profiles`, `mcp_servers`, `mcp_bindings`, `table_metadata`, `column_metadata`, … | Data Catalog, routing, SQL generation, MCP domain bindings |
| **RAG embeddings** | `knowledge_chunks` (+ pgvector `embedding` column) | Ask, RAG ingest, MCP search |

Migrations in `migrations/*.sql` are idempotent (`IF NOT EXISTS` / `IF EXISTS`). Apply them with `scripts/migrate.py` — do not maintain separate DDL scripts for the same objects.

The API, MCP server, and migration script all read the **same connection** from `.env` (`DATABASE_URL` or `PG*` variables). The Python driver is **psycopg 3** by default (`CATALOG_DB_DRIVER=psycopg`); set `CATALOG_DB_DRIVER=pg8000` to revert to the legacy pure-Python driver.

## Not the same as business warehouse data

When you add a **business dataset** (Trino-backed warehouse), that is a **separate database** queried at Ask/Analytics time via the Trino coordinator. Bindings live in:

- **`saved_db_connections.json`** (local, gitignored), or
- **Settings → Dataset connections** in the UI

They do **not** replace the catalog database. You typically have:

```
┌─────────────────────────────┐     ┌──────────────────────────────┐
│  Catalog DB (required)      │     │  Source DBs (optional, many) │
│  DATABASE_URL in .env       │     │  saved_db_connections.json   │
│  • domains & datasets       │     │  • customer warehouse        │
│  • knowledge_chunks/RAG     │     │  • HR postgres, etc.         │
└─────────────────────────────┘     └──────────────────────────────┘
         ▲                                       ▲
         │                                       │
    API, MCP, migrate                      Trino → warehouse (see trino.md)
```

## Requirements

- **PostgreSQL 14+** (16 recommended; matches Docker image)
- Extension **`vector`** (pgvector) — required for embeddings  
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```
- A user that can `CREATE SCHEMA` and run migrations (or use schema `ragpro` on an existing DB)
- Network access from wherever API/MCP run (localhost, Docker, ECS, etc.)

Default schema name: **`ragpro`** (override with `DB_SCHEMA` in `.env`).

## Quick setup (bring your own Postgres)

### 1. Create an empty database

On your Postgres server (local install, RDS, Aurora, Cloud SQL, etc.):

```sql
CREATE DATABASE datapro_catalog;
-- connect to datapro_catalog, then:
CREATE EXTENSION IF NOT EXISTS vector;
```

Use a dedicated database per environment (dev/staging/prod). Do not commit hostnames or passwords to the repo.

### 2. Configure the connection in `.env`

```bash
cp .env.example .env
```

**Option A — connection URL (common):**

```bash
DATABASE_URL="postgresql://myuser:mypassword@db.example.com:5432/datapro_catalog"
DB_SCHEMA="ragpro"
PGSSLMODE="require"    # use "disable" for local Docker Postgres only
```

**Option B — separate fields** (override or replace URL parts):

```bash
PGHOST="db.example.com"
PGPORT="5432"
PGUSER="myuser"
PGPASSWORD="mypassword"
PGDATABASE="datapro_catalog"
DB_SCHEMA="ragpro"
PGSSLMODE="require"
```

If both `DATABASE_URL` and `PG*` are set, individual `PG*` values override the matching parts of the URL.

You can also set these from **Settings → Database** in the UI; the app writes back to `.env`. Restart the API and MCP after changing the catalog connection.

See [secrets.md](secrets.md) — never commit `.env`.

### 3. Run migrations

Creates schema `ragpro`, catalog tables, vector table, and default domains (HR, Finance, Sales, General):

```bash
python scripts/migrate.py
```

Podman Compose runs this automatically via the `migrate` service before API/MCP start.

Verify:

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/stats      # chunk count after ingest
curl http://localhost:8080/api/readiness  # catalog + chunks checks
```

### 4. Use the app

1. **Settings** — confirm LLM and catalog DB show as connected  
2. **Data Catalog** — domains and datasets (metadata stored in catalog DB)  
3. **RAG** — ingest files → rows in `knowledge_chunks`  
4. **Ask** / **MCP** — search those chunks

Optional demo warehouse (separate SQL objects **inside** the same catalog DB or another DB depending on script): [migrations/finance_data/README.md](../migrations/finance_data/README.md).

## Podman Compose (bundled Postgres)

If you do not have Postgres yet, Compose includes a **`db`** service (pgvector/pg16):

```bash
podman compose up --build
```

Default connection (already in `.env.example`):

```bash
DATABASE_URL="postgresql://ragpro:ragpro@localhost:5432/ragpro"
PGSSLMODE="disable"
```

Data persists in the Docker volume `datapro_pgdata`. To use **your** Postgres instead, set `DATABASE_URL` in `.env` to your host and skip or stop the `db` service — see [docker.md](docker.md).

## Production (RDS / ECS)

Use a managed Postgres instance with pgvector enabled. Put the connection string in:

- **Local / VM:** `.env`  
- **ECS on AWS:** `deploy/secrets.env` → AWS Secrets Manager (see [deploy-ecs.md](deploy-ecs.md))

Always use `PGSSLMODE=require` (or stricter) for remote RDS.

## SSL and corporate proxies

| Environment | Typical `PGSSLMODE` |
|-------------|---------------------|
| Podman Compose `db` service | `disable` |
| Local Postgres on localhost | `disable` or `prefer` |
| RDS / Aurora / cloud Postgres | `require` |

If TLS inspection breaks SSL, you may need CA certs in `certs/` (gitignored) — see [secrets.md](secrets.md).

## Changing database or embedding model

- **New empty catalog DB:** point `.env` at it, run `python scripts/migrate.py`, re-ingest all datasets.  
- **Different `EMBEDDING_MODEL`:** change in Settings, then **re-ingest** everything (vector dimensions must match).  
- **Permission errors on migration 002:** see [troubleshooting.md](troubleshooting.md) — table owner must run the printed `ALTER TABLE` SQL once.

## Related docs

- [installation.md](installation.md) — full install paths  
- [secrets.md](secrets.md) — what stays out of git  
- [architecture.md](architecture.md) — catalog ER diagram and flows  
- [user-guide.md](user-guide.md) — catalog, ingest, Ask  
- [docker.md](docker.md) — Compose services and external Postgres
