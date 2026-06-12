# Docker

```bash
cp .env.example .env
# MISTRAL_API_KEY or Ollama settings

docker compose up --build
```

UI at http://localhost:5173

## What's in the stack

| Container | Port | Does |
|-----------|------|------|
| `datapro-web` | 5173 → 80 | React + nginx, proxies `/api` |
| `datapro-api` | 8080 | FastAPI |
| `datapro-mcp` | 8000 | MCP server |
| `datapro-db` | 5432 | Postgres + pgvector |
| `datapro-migrate` | — | Runs migrations once, then exits |

Postgres data sticks around in the `datapro_pgdata` volume.

## Common commands

```bash
docker compose up --build          # everything
docker compose up datapro-api      # API only
docker compose up datapro-mcp      # MCP only
docker compose run --rm migrate    # re-run migrations
docker compose logs -f api         # tail API logs
docker compose down                # stop (volume kept)
```

Load the demo finance warehouse into the same Postgres:

```bash
docker compose run --rm api python scripts/migrate_finance_data.py --fresh
```

## Your own Postgres instead of `db`

Point `.env` at it:

```bash
DATABASE_URL="postgresql://user:pass@host:5432/dbname"
PGSSLMODE=require
DB_SCHEMA=ragpro
```

Run `CREATE EXTENSION IF NOT EXISTS vector;` on that database, then `docker compose run --rm migrate`. You can skip the `db` service if API and MCP only talk to your external instance.

## Ollama on the host machine

```bash
DEFAULT_LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

On Linux, add to the `api` service in `docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## Repo files

- `Dockerfile` — multi-stage build (web, API, MCP, nginx)
- `docker-compose.yml` — service definitions
- `docker/nginx.conf` — static UI + API proxy
- `docker/init-db.sql` — enables pgvector on first DB start

See [installation.md](installation.md) and [mcp.md](mcp.md) for the rest.
