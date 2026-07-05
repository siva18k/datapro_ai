# Podman

```bash
cp .env.example .env
# MISTRAL_API_KEY or Ollama settings
cp docker/trino/catalog/finance.properties.example docker/trino/catalog/finance.properties

podman machine start
podman compose up --build
```

UI at http://localhost:5173

## What's in the stack

| Container | Port | Does |
|-----------|------|------|
| `datapro-web` | 5173 → 80 | React + nginx, proxies `/api` |
| `datapro-api` | 8080 | FastAPI |
| `datapro-mcp` | 8000 | MCP server |
| `datapro-db` | 5432 | Postgres + pgvector (catalog metadata) |
| `datapro-trino` | 8081 → 8080 | Trino coordinator (business SQL) |
| `datapro-migrate` | — | Runs migrations once, then exits |

Postgres data sticks around in the `datapro_pgdata` volume.

## Trino only (API / UI / MCP run locally)

When catalog Postgres and the app already run outside Docker (e.g. `uvicorn` + `npm run dev`), start **only** Trino:

```bash
# finance.properties must exist (Aurora or copy from .example for local demo)
podman compose up -d trino
```

This does **not** start `db`, `api`, `web`, or `mcp`, and does **not** build anything — only pulls/runs the Trino image (~1 GB).

Local `.env` for a host-run API:

```bash
TRINO_HOST=localhost
TRINO_PORT=8081
```

Then run the app as usual:

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
cd web && npm run dev
```

Verify Trino: `curl -s http://localhost:8081/v1/info`

**Disk space:** the Trino image is large. If you see `input/output error` during pull/build, free several GB on the Mac first (`df -h`), then retry.

## Common commands

```bash
podman compose up --build          # everything
podman compose up datapro-api      # API only
podman compose up datapro-mcp      # MCP only
podman compose run --rm migrate    # re-run migrations
podman compose logs -f api         # tail API logs
podman compose down                # stop (volume kept)
```

Load the demo finance warehouse into the same Postgres (queried via Trino catalog `finance`):

```bash
podman compose run --rm api python scripts/migrate_finance_data.py --fresh
```

See **[docs/trino.md](docs/trino.md)** for Trino coordinator settings, catalog bindings, and AWS notes.

## Your own Postgres instead of `db`

Point `.env` at your catalog database — full steps in **[catalog-database.md](catalog-database.md)**. Summary:

```bash
DATABASE_URL="postgresql://user:pass@host:5432/dbname"
PGSSLMODE=require
DB_SCHEMA=ragpro
```

Run `CREATE EXTENSION IF NOT EXISTS vector;` on that database, then `podman compose run --rm migrate`. You can skip the `db` service if API and MCP only talk to your external instance.

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

## AWS ECS on AWS (production)

Production deployment is **AWS-only** (ECS Fargate, ECR, RDS). Templates live in **`deploy.example/`** (public, no secrets). Copy locally:

```bash
./deploy.example/scripts/init-deploy.sh
```

Edit **`deploy/`** only (gitignored). Full AWS guide: [docs/deploy-ecs.md](../docs/deploy-ecs.md).
