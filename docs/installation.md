# Installation

You need either Podman with Compose support (easiest) or Python 3.11+ and Node 20+ for local dev. Either way you need an LLM — Mistral API key by default, or Ollama running on your machine.

**Catalog database:** one PostgreSQL instance holds all catalog metadata and RAG vectors. Podman bundles Postgres for local dev; otherwise point `.env` at your own database. Full guide: **[catalog-database.md](catalog-database.md)**.

## Podman

```bash
git clone https://github.com/siva18k/datapro_ai.git data-pro
cd data-pro
cp .env.example .env
# Edit .env — at minimum MISTRAL_API_KEY, or DEFAULT_LLM_BACKEND=ollama

podman machine start
podman compose up --build
```

UI: http://localhost:5173  
API health: http://localhost:8080/api/health  
Trino UI: http://localhost:8081  
MCP: http://127.0.0.1:8000/mcp

First startup can take a few minutes while the embedding model downloads. More compose detail in [docker.md](docker.md).

Once it's up: check **Settings** (catalog DB + Trino coordinator are pre-filled in Podman), add a Trino catalog binding (`finance` / `finance_data`) if Trino is available, or use **Database (native Postgres)** for direct pg8000 access, optionally load the finance demo (`migrate_finance_data.py`), add a domain and dataset in **Data Catalog**, then try **Ask**. See [trino.md](trino.md).

## Local development

**Python and Node**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cd web && npm install && cd ..
```

**Environment**

```bash
cp .env.example .env
```

Configure the **catalog database** connection — see **[catalog-database.md](catalog-database.md)** for creating Postgres, enabling pgvector, and `DATABASE_URL` / `PG*` settings. Also set `MISTRAL_API_KEY` (or Ollama). Minimum on your Postgres instance:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Migrations**

```bash
python scripts/migrate.py
```

That creates schema `ragpro`, default domains (HR, Finance, Sales, General), and the vector tables.

**Run the app**

Terminal 1 — API:

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
```

Terminal 2 — UI:

```bash
cd web && npm run dev
```

Or `./scripts/dev.sh` for both. MCP is optional: `python mcp_server.py`.

## Environment variables

Secrets go in `.env` (you can also edit many of them from **Settings**). Don't commit `.env` or `saved_db_connections.json` — copy from the `.example` files instead. See [secrets.md](secrets.md).

| Variable | Required? | Notes |
|----------|-----------|-------|
| `MISTRAL_API_KEY` | Usually | Skip if `DEFAULT_LLM_BACKEND=ollama` |
| `DATABASE_URL` | Yes | **Catalog DB** — metadata + RAG vectors ([catalog-database.md](catalog-database.md)) |
| `DB_SCHEMA` | No | Defaults to `ragpro` |
| `TRINO_HOST` | For warehouse SQL | Coordinator hostname (`trino` in Compose, `localhost` from host) |
| `TRINO_PORT` | No | `8081` on host (maps to 8080 in container); default `8081` in `.env.example` |
| `TRINO_USER` | No | Default `trino` |
| `TRINO_HTTP_SCHEME` | No | `http` locally, `https` on AWS internal ALB |
| `PGSSLMODE` | No | `require` for RDS, `disable` for local Podman |
| `EMBEDDING_MODEL` | No | Default `all-MiniLM-L6-v2` |
| `DEFAULT_LLM_BACKEND` | No | `mistral`, `openai`, `anthropic`, `gemini`, `openrouter`, `ollama` |
| `OLLAMA_BASE_URL` | If Ollama | e.g. `http://localhost:11434` |
| `MCP_URL` | No | Default `http://127.0.0.1:8000/mcp` |

Business warehouse access uses **Trino**: coordinator settings in `.env` / **Settings → Trino coordinator**; catalog bindings (friendly name + `catalog` + `schema`) in `saved_db_connections.json` or **Settings → Database connections**. Real database credentials live in Trino catalog config (`docker/trino/catalog/` locally). This is **separate** from the catalog Postgres — see [trino.md](trino.md) and [catalog-database.md](catalog-database.md).

## Handy scripts

- `python scripts/migrate.py` — apply migrations, seed domains
- `python scripts/migrate_finance_data.py --fresh` — optional demo warehouse
- `python mcp_server.py` — MCP on port 8000
- `./scripts/dev.sh` — API + Vite together
- `podman compose up --build` — full stack
- `python ingest.py` — old CLI path for `sample_docs/`

If you change the embedding model in Settings, re-ingest everything or your vectors won't match.

## Production frontend

```bash
cd web && npm run build
```

Output lands in `web/dist/`. The container image serves it through nginx (`docker/nginx.conf`) with `/api` proxied to FastAPI.
