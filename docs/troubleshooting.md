# Troubleshooting

**"API offline" in the UI** — API isn't running. `docker compose up api`, or `uvicorn api.main:app --port 8080`, or **Settings → Start API**.

**Migrate fails** — Postgres not reachable, or `vector` extension missing, or the DB user can't `CREATE` the schema. Run `CREATE EXTENSION IF NOT EXISTS vector;` as a superuser if needed. See [catalog-database.md](catalog-database.md).

**`permission denied` on migration 002** — Run the DBA SQL that `migrate.py` prints, as the table owner.

**Ask returns nothing useful** — Probably no ingest yet. Index files or catalog metadata, check `/api/stats` for chunk count.

**First question is slow** — Embedding model loads once per API process. Normal.

**Bad retrieval** — Improve `definition.md`, column labels, RAG profile instructions. Garbage in, garbage out.

**MCP connection refused** — Start MCP: `python mcp_server.py` or `docker compose up datapro-mcp`.

**Docker can't reach Ollama** — `OLLAMA_BASE_URL=http://host.docker.internal:11434`. On Linux add `extra_hosts` (see [docker.md](docker.md)).

**Wrong vector dimension errors** — You changed embedding model without re-ingesting. Re-ingest all datasets.

**CORS errors in dev** — Use the Vite dev server on 5173, or nginx in Docker — don't open the API origin directly in the browser for the UI.

More context: [installation.md](installation.md), [docker.md](docker.md), [user-guide.md](user-guide.md).
