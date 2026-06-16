# Documentation

Start with [installation](installation.md) if you're setting up for the first time.

**Public repo hygiene:** never commit real API keys, production DB hosts, warehouse passwords, TLS certs, or personal AWS files under `deploy/` — see [secrets](secrets.md) and [deploy-ecs](deploy-ecs.md).

| Doc | What's in it |
|-----|----------------|
| **[Contributing & conventions](contributing.md)** | **Themes, gitignore/secrets, doc updates, UI consistency** |
| **[Catalog database](catalog-database.md)** | **Required Postgres for metadata + RAG** — connection, pgvector, migrations |
| [Installation](installation.md) | Docker or local dev, env vars, scripts |
| [Secrets](secrets.md) | `.env` and `saved_db_connections.json` — keep these local |
| [Docker](docker.md) | Compose services, external Postgres, Ollama |
| [Deploy to AWS ECS (Fargate)](deploy-ecs.md) | **AWS** production: ECR, Fargate, RDS (`deploy.example/` → gitignored `deploy/`) |
| [User guide](user-guide.md) | Catalog, datasets, RAG ingest, Ask |
| [MCP](mcp.md) | MCP server, tools, Cursor / Claude config |
| [Architecture](architecture.md) | Components and data flows |
| [Concepts](concepts.md) | RAG and MCP in plain terms |
| [Troubleshooting](troubleshooting.md) | Fixes for common problems |

Optional sample data: [finance_data warehouse](../migrations/finance_data/README.md).
