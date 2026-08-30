# Secrets and local config

Don't commit real credentials. `.gitignore` already excludes the files below — use the example templates in the repo and fill in your own values.

| Local file (ignored) | Copy from | What it's for |
|----------------------|-----------|---------------|
| `.env` | `.env.example` | Catalog DB, LLM keys, embedding model, MCP URL |
| `docs/notes` | — | Personal scratch notes (ignored; do not paste credentials) |
| `saved_db_connections.json` | `saved_db_connections.json.example` | Trino catalog bindings for datasets |
| `deploy/` | `deploy.example/` | Personal **AWS** ECS deploy config and secrets ([deploy-ecs.md](deploy-ecs.md)) |
| `certs/` | — | Local TLS / proxy CA certs (e.g. corporate SSL inspection) |

Log and pid files (`.mcp_server.log`, `.api_server.log`, etc.) are ignored too.

**Safe in the public repo:** `localhost` URLs, Docker dev passwords in `.env.example` (`ragpro`/`ragpro`), placeholder hosts in `saved_db_connections.json.example`, and fictional demo data (`@demo.com`, `@example.com` in seed SQL).

**Never commit:** your real `.env`, warehouse credentials, production RDS/hostnames, internal DB usernames from your org, TLS/proxy certs in `certs/`, or anything under **`deploy/`** (personal AWS ECS configs — see [deploy-ecs.md](deploy-ecs.md)).

## `.env`

```bash
cp .env.example .env
```

Typical things to set:

- `DATABASE_URL` or `PGHOST`, `PGUSER`, `PGPASSWORD`, … — **catalog database** (metadata + RAG). Setup guide: [catalog-database.md](catalog-database.md)
- `MISTRAL_API_KEY` — or another provider / Ollama
- `DB_SCHEMA` — usually `ragpro`

**Settings** in the UI can update a lot of this and write back to `.env`. Restart the API or MCP after catalog-related changes. Docker defaults in `.env.example` match the bundled Postgres service.

## Saved dataset connections

Trino **catalog bindings** (name + catalog + schema). Warehouse credentials live in Trino catalog files (`docker/trino/catalog/*.properties`, gitignored). Add bindings in **Settings → Database connections** or edit JSON:

```bash
cp saved_db_connections.json.example saved_db_connections.json
```

**Migrating old Postgres rows** (host/port/password in the same file):

```bash
python scripts/migrate_connections_to_trino.py --migrate-datasets
```

Passwords in legacy JSON are moved into Trino catalog property files; the saved connection file keeps only catalog + schema.

## After cloning

1. Copy `.env.example` → `.env` and the connections example if you need it.
2. Fill in your own keys and hosts.
3. Follow [installation.md](installation.md).

Don't copy someone else's `.env` into the repo, even by mistake.
