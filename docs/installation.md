# Installation

You need either Docker Desktop (easiest) or Python 3.11+ and Node 20+ for local dev. Either way you need an LLM — Mistral API key by default, or Ollama running on your machine.

**Catalog database:** one PostgreSQL instance holds all catalog metadata and RAG vectors. Docker bundles Postgres for local dev; otherwise point `.env` at your own database. Full guide: **[catalog-database.md](catalog-database.md)**.

## Docker

```bash
git clone https://github.com/siva18k/datapro_ai.git data-pro
cd data-pro
cp .env.example .env
# Edit .env — at minimum MISTRAL_API_KEY, or DEFAULT_LLM_BACKEND=ollama

docker compose up --build
```

UI: http://localhost:5173  
API health: http://localhost:8080/api/health  
MCP: http://127.0.0.1:8000/mcp

First startup can take a few minutes while the embedding model downloads. More compose detail in [docker.md](docker.md).

Once it's up: check **Settings** (LLM + DB are mostly pre-filled in Docker), add a domain and dataset in **Data Catalog**, ingest something, then try **Ask**.

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
| `PGSSLMODE` | No | `require` for RDS, `disable` for local Docker |
| `EMBEDDING_MODEL` | No | Default `all-MiniLM-L6-v2` |
| `DEFAULT_LLM_BACKEND` | No | `mistral`, `openai`, `anthropic`, `gemini`, `openrouter`, `ollama` |
| `OLLAMA_BASE_URL` | If Ollama | e.g. `http://localhost:11434` |
| `MCP_URL` | No | Default `http://127.0.0.1:8000/mcp` |

Warehouse Postgres connections (the databases you query in Ask) live in `saved_db_connections.json` or **Settings → Dataset connections**, not in `.env`. They are **separate** from the catalog database — see [catalog-database.md](catalog-database.md).

## Handy scripts

- `python scripts/migrate.py` — apply migrations, seed domains
- `python scripts/migrate_finance_data.py --fresh` — optional demo warehouse
- `python mcp_server.py` — MCP on port 8000
- `./scripts/dev.sh` — API + Vite together
- `docker compose up --build` — full stack
- `python ingest.py` — old CLI path for `sample_docs/`

If you change the embedding model in Settings, re-ingest everything or your vectors won't match.

## Production frontend

```bash
cd web && npm run build
```

Output lands in `web/dist/`. The Docker image serves it through nginx (`docker/nginx.conf`) with `/api` proxied to FastAPI.
