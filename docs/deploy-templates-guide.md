# AWS ECS deployment templates (DATA Pro)

Templates for deploying DATA Pro to **Amazon Web Services (AWS)** — ECS Fargate, ECR, RDS, Secrets Manager.

The `deploy.example/` folder is **checked into the public repo**. It contains generic templates only — no real AWS account IDs, ARNs, passwords, or API keys.

## Quick start

From the repository root:

```bash
./deploy.example/scripts/init-deploy.sh
```

That creates a local **`deploy/`** directory (gitignored) by copying these templates. Edit files only under **`deploy/`**, never commit that folder.

```bash
# 1. Non-secret AWS / ECS settings
cp deploy/config.env.example deploy/config.env   # if init did not rename yet
${EDITOR:-nano} deploy/config.env

# 2. Secrets (database URL, LLM keys) — NEVER commit
cp deploy/secrets.env.example deploy/secrets.env
${EDITOR:-nano} deploy/secrets.env

# 3. One-time AWS setup (ECR repos, log groups) — review script first
./deploy/scripts/create-aws-resources.sh

# 4. Build and push images to ECR
./deploy/scripts/build-and-push.sh

# 5. Register task definitions and create/update ECS services
./deploy/scripts/deploy-ecs.sh

# 6. Run database migrations (one-shot Fargate task)
./deploy/scripts/run-migrate.sh
```

## What gets deployed

| Service | Image target | Notes |
|---------|--------------|--------|
| **web** | `web-ecs` | nginx + React UI; proxies `/api` to internal API hostname |
| **api** | `api` | FastAPI on port 8080 |
| **mcp** | `mcp` | MCP server on port 8000 (optional; disable in config if unused) |
| **migrate** | `api` | One-shot task: `python scripts/migrate.py` |

Postgres is **not** bundled for ECS. Use **Amazon RDS** (or another managed Postgres with pgvector) and set `DATABASE_URL` in `deploy/secrets.env`.

## Files you customize (in `deploy/` only)

| File | Secrets? |
|------|----------|
| `config.env` | No — region, cluster name, subnet IDs, desired counts |
| `secrets.env` | **Yes** — `DATABASE_URL`, `MISTRAL_API_KEY`, etc. |
| `ecs/*.json` | Mixed — generated from templates; may contain your ARNs after deploy scripts run |

## Open-source rule

- **Commit:** changes under `deploy.example/` and `docs/deploy-ecs.md`
- **Do not commit:** anything under `deploy/`, `.env`, or production credentials

See [deploy-ecs.md](deploy-ecs.md) for architecture and RDS/pgvector notes.
