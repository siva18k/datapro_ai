# DATA Pro

Catalog your data, embed documents, ask questions across domains, and hook up Cursor or Claude via MCP if you want agents in the loop.

Built with React, FastAPI, Postgres + pgvector, sentence-transformers, and Mistral or Ollama for the LLM.

## Get running

```bash
git clone https://github.com/siva18k/datapro_ai.git data-pro
cd data-pro
cp .env.example .env
# Put your MISTRAL_API_KEY in .env — or set DEFAULT_LLM_BACKEND=ollama
# Optional: cp saved_db_connections.json.example saved_db_connections.json

docker compose up --build
```

Then open the UI (default port **5173**). Service URLs and ports are in [docs/installation.md](docs/installation.md).

Prefer running things locally without Docker? Same doc covers local setup.

## What it does

**Data Catalog** — domains, datasets, Postgres connections, file uploads.

**Ask** — chat over your documents (RAG) or structured SQL when you have Postgres datasets wired up.

**Analytics** — build dashboards from plain English.

**RAG** — chunk settings and embedding ingest.

**MCP** — same knowledge base, but callable from Cursor / Claude Desktop.

If RAG or MCP are new to you, [docs/concepts.md](docs/concepts.md) explains both in a few minutes.

## Docs

- [docs/README.md](docs/README.md) — index
- [Installation](docs/installation.md) — setup and scripts
- [Secrets](docs/secrets.md) — `.env` and saved connections (templates only in git)
- [Docker](docs/docker.md) — compose, services, Ollama on the host
- [User guide](docs/user-guide.md) — catalog, ingest, Ask
- [MCP](docs/mcp.md) — server and client config
- [Architecture](docs/architecture.md) — how the pieces fit
- [Troubleshooting](docs/troubleshooting.md) — when something breaks

Demo warehouse SQL: [migrations/finance_data/README.md](migrations/finance_data/README.md)

## Keep private

Do **not** commit real API keys, production database hosts, passwords, or TLS certs. Those belong in `.env`, `saved_db_connections.json`, and `certs/` — all gitignored. See [docs/secrets.md](docs/secrets.md).

`localhost` / `127.0.0.1` URLs in docs are local dev defaults only, not secrets.

## Layout

```
api/              FastAPI backend
web/              React UI
docs/             Documentation
migrations/       SQL schema
scripts/          migrate.py, dev.sh
mcp_server.py     MCP server
docker-compose.yml
sample_docs/      Example files
```

## License

MIT — see [LICENSE](LICENSE). Clone and use it however you like; only the repo owner can push changes upstream.
