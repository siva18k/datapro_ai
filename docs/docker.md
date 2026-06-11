# Docker

## Quick start

```bash
cp .env.example .env
# Edit .env — MISTRAL_API_KEY or Ollama settings

docker compose up --build
```

Open **http://localhost:5173**

## Services

| Container | Port | Purpose |
|-----------|------|---------|
| `datapro-web` | 5173 → 80 | React UI + nginx `/api` proxy |
| `datapro-api` | 8080 | FastAPI |
| `datapro-mcp` | 8000 | MCP server |
| `datapro-db` | 5432 | Postgres + pgvector |
| `datapro-migrate` | — | One-shot migrations (exits) |

Data persists in Docker volume `datapro_pgdata`.

## Common commands

```bash
docker compose up --build          # Start all
docker compose up datapro-api      # API only
docker compose up datapro-mcp      # MCP only
docker compose run --rm migrate    # Re-run migrations
docker compose logs -f api         # API logs
docker compose down                # Stop (keeps volume)
```

Optional demo warehouse (same Postgres):

```bash
docker compose run --rm api python scripts/migrate_finance_data.py --fresh
```

## External Postgres

Use your own database instead of bundled `db`:

1. Set in `.env`:

```bash
DATABASE_URL="postgresql://user:pass@host:5432/dbname"
PGSSLMODE=require
DB_SCHEMA=ragpro
```

2. Run `CREATE EXTENSION IF NOT EXISTS vector;` on that database.
3. Run `docker compose run --rm migrate` (or point only `api`/`mcp` at external DB and skip `db` service).

## Ollama on the host

```bash
DEFAULT_LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

On Linux, add to the `api` service in `docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## Files

| File | Role |
|------|------|
| `Dockerfile` | Multi-stage: web build, API, MCP, nginx |
| `docker-compose.yml` | Service definitions |
| `docker/nginx.conf` | Static UI + API reverse proxy |
| `docker/init-db.sql` | Enables pgvector on first DB start |

See also [Installation](installation.md) and [MCP](mcp.md).
