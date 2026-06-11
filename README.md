# DATA Pro

Multi-domain knowledge and analytics — catalog your data, embed documents, ask questions, and optionally connect AI assistants via MCP.

**Stack:** React · FastAPI · PostgreSQL + pgvector · sentence-transformers · Mistral or Ollama

## Quick start

```bash
git clone https://github.com/siva18k/datapro_ai.git data-pro
cd data-pro
cp .env.example .env
# Set MISTRAL_API_KEY in .env (or DEFAULT_LLM_BACKEND=ollama)
# Optional: cp saved_db_connections.json.example saved_db_connections.json

docker compose up --build
```

Open **http://localhost:5173**

Local dev (no Docker): see [docs/installation.md](docs/installation.md).

## What you can do

- **Data Catalog** — domains, datasets, Postgres connections, file uploads  
- **Ask** — chat over documents (RAG) or structured SQL  
- **Analytics** — dashboards from natural language  
- **RAG** — chunk settings and embedding ingest  
- **MCP** — tools for Cursor / Claude Desktop  

New to RAG or MCP? Start with [docs/concepts.md](docs/concepts.md).

## Documentation

| Guide | Description |
|-------|-------------|
| [docs/README.md](docs/README.md) | Documentation index |
| [Installation](docs/installation.md) | Setup, credentials, scripts |
| [Secrets & local config](docs/secrets.md) | `.env` and saved connections (templates only in git) |
| [Docker](docs/docker.md) | Compose, services, Ollama |
| [User guide](docs/user-guide.md) | Domains, datasets, RAG, UI |
| [MCP](docs/mcp.md) | MCP server and client config |
| [Architecture](docs/architecture.md) | System design and data flows |
| [Troubleshooting](docs/troubleshooting.md) | Common fixes |

**Demo data:** [migrations/finance_data/README.md](migrations/finance_data/README.md)

## URLs (default)

| URL | Service |
|-----|---------|
| http://localhost:5173 | UI |
| http://localhost:8080/docs | API (OpenAPI) |
| http://127.0.0.1:8000/mcp | MCP |

## Project layout

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

This project is licensed under the [MIT License](LICENSE) — free to use, copy, modify, and distribute. Only the repository owner can push changes; everyone else can clone and use the code read-only from GitHub.
