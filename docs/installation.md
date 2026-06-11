# Installation

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **Docker Desktop** (recommended) | Postgres, API, UI, MCP in one command |
| **Or** Python 3.11+ and Node 20+ | Local development |
| **LLM** | [Mistral](https://console.mistral.ai/) API key (default) or [Ollama](https://ollama.com/) locally |
| **PostgreSQL + pgvector** | Included in Docker; otherwise your own instance |

---

## Option A — Docker (recommended)

```bash
git clone <your-repo-url> data-pro
cd data-pro
cp .env.example .env
# Edit .env — set MISTRAL_API_KEY (or DEFAULT_LLM_BACKEND=ollama)

docker compose up --build
```

Open **http://localhost:5173**

| URL | Service |
|-----|---------|
| http://localhost:5173 | UI |
| http://localhost:8080/api/health | API |
| http://127.0.0.1:8000/mcp | MCP |

First run may take a few minutes (embedding model download).

More detail: [Docker guide](docker.md).

### First steps after start

1. **Settings** — LLM provider and API key (DB is pre-configured in Docker).
2. **Data Catalog** — domain + dataset → ingest data ([user guide](user-guide.md)).
3. **Ask** — try a question.

---

## Option B — Local development

### 1. Python and Node

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cd web && npm install && cd ..
```

### 2. Environment

```bash
cp .env.example .env
```

Set `DATABASE_URL` (or `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) and `MISTRAL_API_KEY`.

On your Postgres database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Migrations

```bash
python scripts/migrate.py
```

Creates schema `ragpro`, default domains (HR, Finance, Sales, General), and vector tables.

### 4. Run

**Terminal 1 — API**

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
```

**Terminal 2 — UI**

```bash
cd web && npm run dev
```

Or both: `./scripts/dev.sh`

**Optional — MCP**

```bash
python mcp_server.py
```

---

## Environment variables

Secrets live in `.env` (also editable from **Settings**). See [Secrets & local config](secrets.md) — **do not commit** `.env` or `saved_db_connections.json`; use [`.env.example`](../.env.example) and [`saved_db_connections.json.example`](../saved_db_connections.json.example).

| Variable | Required | Purpose |
|----------|----------|---------|
| `MISTRAL_API_KEY` | Yes* | Default LLM |
| `DATABASE_URL` | Yes | Catalog + vectors |
| `DB_SCHEMA` | No | Default `ragpro` |
| `PGSSLMODE` | No | `require` (RDS) or `disable` (local Docker) |
| `EMBEDDING_MODEL` | No | Default `all-MiniLM-L6-v2` |
| `DEFAULT_LLM_BACKEND` | No | `mistral`, `openai`, `anthropic`, `gemini`, `openrouter`, `ollama` |
| `OLLAMA_BASE_URL` | If Ollama | e.g. `http://localhost:11434` |
| `MCP_URL` | No | Default `http://127.0.0.1:8000/mcp` |

\*Or set `DEFAULT_LLM_BACKEND=ollama` with no cloud key.

**Source databases** (warehouse Postgres) use **`saved_db_connections.json`** (local, gitignored) or **Settings → Dataset connections** in the UI — not `.env`. See [Secrets & local config](secrets.md).

---

## Scripts

| Command | Purpose |
|---------|---------|
| `python scripts/migrate.py` | Apply schema migrations + seed domains |
| `python scripts/migrate_finance_data.py --fresh` | Optional demo warehouse |
| `python mcp_server.py` | Start MCP on port 8000 |
| `./scripts/dev.sh` | API + Vite together |
| `docker compose up --build` | Full Docker stack |
| `python ingest.py` | Legacy CLI ingest of `sample_docs/` |

After changing **embedding model** in Settings, re-ingest all datasets.

---

## Production frontend build

```bash
cd web && npm run build
```

Output: `web/dist/`. Serve with nginx (`docker/nginx.conf`) proxying `/api` to FastAPI.
