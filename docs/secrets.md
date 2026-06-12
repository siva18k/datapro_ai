# Secrets and local config

Don't commit real credentials. `.gitignore` already excludes the files below — use the example templates in the repo and fill in your own values.

| Local file (ignored) | Copy from | What it's for |
|----------------------|-----------|---------------|
| `.env` | `.env.example` | Catalog DB, LLM keys, embedding model, MCP URL |
| `saved_db_connections.json` | `saved_db_connections.json.example` | Named Postgres connections for datasets |
| `certs/` | — | Local TLS / proxy CA certs (e.g. corporate SSL inspection) |

Log and pid files (`.mcp_server.log`, `.api_server.log`, etc.) are ignored too.

**Safe in the public repo:** `localhost` URLs, Docker dev passwords in `.env.example` (`ragpro`/`ragpro`), placeholder hosts in `saved_db_connections.json.example`, and fictional demo data (`@demo.com`, `@example.com` in seed SQL).

**Never commit:** your real `.env`, warehouse credentials, production RDS/hostnames, internal DB usernames from your org, or TLS/proxy certs in `certs/`.

## `.env`

```bash
cp .env.example .env
```

Typical things to set:

- `MISTRAL_API_KEY` — or another provider / Ollama
- `DATABASE_URL` or `PGHOST`, `PGUSER`, `PGPASSWORD`, … for the catalog database
- `DB_SCHEMA` — usually `ragpro`

**Settings** in the UI can update a lot of this and write back to `.env`. Restart the API or MCP after catalog-related changes. Docker defaults in `.env.example` match the bundled Postgres service.

## Saved dataset connections

For **Postgres** datasets in the catalog. You can add connections in **Settings → Dataset connections** instead of editing JSON by hand.

```bash
cp saved_db_connections.json.example saved_db_connections.json
# edit host, user, password, database, schema
```

Or let the app create an empty file on first use:

```bash
echo '{"connections": []}' > saved_db_connections.json
```

Passwords stay on disk in that file. The API never sends them to the browser — you'll only see `password_set: true`.

## After cloning

1. Copy `.env.example` → `.env` and the connections example if you need it.
2. Fill in your own keys and hosts.
3. Follow [installation.md](installation.md).

Don't copy someone else's `.env` into the repo, even by mistake.
