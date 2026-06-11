# Secrets and local config

**Never commit real credentials to git.** DATA Pro keeps secrets in local files that are listed in `.gitignore`. Use the **example** files in the repo as templates.

## Files overview

| Local file (gitignored) | Template (safe to commit) | Purpose |
|-------------------------|---------------------------|---------|
| `.env` | [`.env.example`](../.env.example) | Catalog DB, LLM API keys, embedding model, MCP URL |
| `saved_db_connections.json` | [`saved_db_connections.json.example`](../saved_db_connections.json.example) | Named Postgres connections for **Settings → Dataset connections** and Postgres datasets |

Optional runtime files (also gitignored): `.mcp_server.log`, `.api_server.log`, `.mcp_server.pid`, `.api_server.pid`.

## Setup

### 1. Environment (`.env`)

```bash
cp .env.example .env
```

Edit `.env` with your values:

- **`MISTRAL_API_KEY`** (or another LLM provider / Ollama)
- **`DATABASE_URL`** or `PGHOST`, `PGUSER`, `PGPASSWORD`, etc. — catalog + vector store Postgres
- **`DB_SCHEMA`** — usually `ragpro`

The **Settings** page can update many of these and write back to `.env`. Restart the API or MCP server after catalog-related changes.

For Docker, defaults in `.env.example` match the bundled Postgres service.

### 2. Saved dataset connections (optional)

Used when you add **Postgres** datasets in the Data Catalog. You can create connections in the UI (**Settings → Dataset connections**) instead of editing JSON by hand.

To seed from the template:

```bash
cp saved_db_connections.json.example saved_db_connections.json
# Edit host, user, password, database, schema
```

Or start with an empty store — the app creates `{"connections": []}` on first use:

```bash
echo '{"connections": []}' > saved_db_connections.json
```

Passwords are stored in this file locally. The API never returns passwords to the browser (`password_set: true` only).

## What not to commit

- `.env`, `.env.local`, or any `.env.*` except `.env.example`
- `saved_db_connections.json`
- Any file containing API keys, DB passwords, or private hostnames you do not want public
- Log and PID files under the project root

## Sharing the project

When you clone or fork:

1. Copy both example files to their local names.
2. Fill in your own credentials.
3. Run [Installation](installation.md) (migrate, start servers).

Do not copy another developer’s `.env` or `saved_db_connections.json` into the repository.
