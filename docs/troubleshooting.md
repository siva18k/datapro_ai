# Troubleshooting

| Issue | What to check |
|-------|----------------|
| UI shows “API offline” | Start API: `docker compose up api`, `uvicorn api.main:app --port 8080`, or **Settings → Start API** |
| Migrate fails | Postgres reachable; `CREATE EXTENSION vector`; user can CREATE schema |
| `permission denied` on migration 002 | Run DBA SQL printed by `migrate.py` as table owner |
| Empty Ask answers | Ingest files or index catalog; check `/api/stats` |
| Slow first question | Embedding model loads once per API process — normal |
| Poor retrieval | Improve definition.md, column labels, RAG instructions |
| MCP connection refused | Start MCP on port 8000 |
| Docker + Ollama | `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| Wrong vector dimension | Re-ingest all datasets after embedding model change |
| CORS errors | Use Vite dev server (5173) or nginx proxy in Docker |

More help: [Installation](installation.md) · [Docker](docker.md) · [User guide](user-guide.md)
