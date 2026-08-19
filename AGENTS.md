# DATA Pro — Agent Instructions

## Run / Dev

```bash
# Local dev (no Docker):
scripts/dev.sh          # starts uvicorn on :8080 + vite on :5173

# Docker/Podman:
podman machine start
podman compose up --build   # db → migrate → api → web → mcp

# Migrate manually:
python scripts/migrate.py
```

## Env & Secrets

- Copy `.env.example` → `.env`; never commit `.env`. Pre-commit hook blocks it.
- Saved DB connections: `saved_db_connections.json` (gitignored; template is `.example`).
- AWS deploy files go in local `deploy/` (copy from `deploy.example/`, gitignored).

## Architecture at a glance

| Layer | Entry point | Notes |
|-------|------------|-------|
| API | `api/main.py` → routers in `api/routers/` | FastAPI, lifespan calls `bootstrap()` from `api/deps.py` |
| Web | `web/` (Vite + React 19 + TS) | `npm run dev`, `npm run build` → nginx serves dist |
| MCP server | `mcp_server.py` | Tools/resources/prompts registered via decorators; metadata merged from `mcp_registry.json` over `mcp_registry.py` defaults |
| Catalog/DB | `catalog_db.py`, `db.py` | PostgreSQL + pgvector. Migrations are numbered SQL in `migrations/`, run via `scripts/migrate.py` |
| Connectors | `dataset_connectors/` | Base class + postgres, file, trino implementations; registry in `registry.py` |

Key service files (not routers): `orchestrator.py`, `ingest_service.py`, `connections_service.py`, `mcp_reference_service.py`, `structured_trino.py`, `query_planner.py`.

## MCP extension

- **Add a tool/resource:** one entry in `mcp_registry.py` defaults + handler in `mcp_server.py`. Restart MCP.
- **Override metadata without code edit:** change `mcp_registry.json` (deep-merged on load).
- **External MCP servers** (e.g. `email_mcp_server.py`) register independently — no changes to `mcp_server.py` needed.
- Ask/Analytics auto-attach reference resources via `DEFAULT_MCP_BINDINGS` in `catalog_db.py`.

## Migrations

Numbered SQL files in `migrations/` (000–015). Run with:
```bash
python scripts/migrate.py
```
Finance demo data: `podman compose run --rm api python scripts/migrate_finance_data.py --fresh`

## UI conventions

- **Must support both light/dark themes.** Use tokens from `web/src/index.css` (`--color-surface`, `--color-border`, etc.). Never hardcode `bg-zinc-*` or `text-zinc-*`.
- Reuse shared classes: `.card`, `.btn`, `.input`, `.sidebar-panel`, themed variants like `.mcp-themed-box`.
- Layout patterns: `PageHeader`, sidebar panels (AskRetrievalPanel), `.field` + `.label` for forms.

## What's missing

- No test framework is configured. There are no pytest/unittest files in the repo.
- No lint/formatter config beyond TypeScript typecheck (`tsc -b`) and Vite build.
- No CI workflow files present.
