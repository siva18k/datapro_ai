# Deploying to AWS (Amazon ECS Fargate)

This guide covers deployment to **Amazon Web Services (AWS)** using **ECS Fargate**, **ECR**, **RDS**, and **Secrets Manager**. It is for **your own AWS account**. The public repo ships **templates only** under `deploy.example/`. Your filled-in configs live in **`deploy/`**, which is **gitignored** and must never be committed.

## Open-source safety

| Location | Committed? | Contents |
|----------|------------|----------|
| `deploy.example/` | Yes | Generic scripts, placeholder task defs, example env files |
| `deploy/` | **No** | Your account ID, subnet IDs, Secrets Manager ARNs, `secrets.env` |
| `.env` | **No** | Local dev secrets |

Do not put production RDS hostnames, passwords, or API keys in any tracked file. Use placeholders in `deploy.example/` and real values only in local `deploy/`.

## Architecture (typical)

```
                    ┌─────────────┐
   Users ──────────►│     ALB     │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       ┌────────────┐            ┌────────────┐
       │  web (ECS) │  /api ──►  │ api (ECS)  │
       │  nginx+UI  │  internal  │  FastAPI   │
       └────────────┘            └──────┬─────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
             ┌────────────┐      ┌────────────┐      ┌──────────────┐
             │ mcp (ECS)  │      │ RDS Postgres│      │ Secrets Mgr  │
             │ optional   │      │ + pgvector  │      │ DATABASE_URL │
             └────────────┘      └─────────────┘      └──────────────┘
```

- **web** uses Docker target `web-ecs` — nginx proxies `/api` to `API_UPSTREAM_HOST` (Cloud Map DNS for the API service).
- **api** and **mcp** share the same catalog database on RDS.
- **migrate** is a one-shot Fargate task (same API image, runs `scripts/migrate.py`).

Local Docker Compose (Postgres in a container) is documented in [docker.md](docker.md). ECS production expects **RDS** or another managed Postgres.

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity`)
- Docker
- ECS cluster (Fargate)
- VPC with subnets and security groups
- RDS PostgreSQL with **pgvector** (`CREATE EXTENSION vector;`)
- IAM roles: `ecsTaskExecutionRole`, `ecsTaskRole` (standard ECS roles; execution role needs Secrets Manager read)

## Setup

```bash
# 1. Create local deploy/ from templates
./deploy.example/scripts/init-deploy.sh

# 2. Edit non-secret config
nano deploy/config.env

# 3. Edit secrets (never commit)
nano deploy/secrets.env

# 4. Optional: push secrets to AWS Secrets Manager
./deploy/scripts/sync-secrets-to-aws.sh
# Copy printed ARNs into deploy/config.env

# 5. ECR + CloudWatch log groups
./deploy/scripts/create-aws-resources.sh

# 6. Build and push images
./deploy/scripts/build-and-push.sh

# 7. Create ECS cluster (if needed)
aws ecs create-cluster --cluster-name datapro --region us-east-1

# 8. Register tasks and create/update services
./deploy/scripts/deploy-ecs.sh

# 9. Run migrations
./deploy/scripts/run-migrate.sh
```

## Docker images

The root `Dockerfile` defines:

| Target | Use |
|--------|-----|
| `api` | FastAPI |
| `web` | Local compose (proxies to `http://api:8080`) |
| `web-ecs` | ECS — set `API_UPSTREAM_HOST` env var |
| `mcp` | MCP server |

Build locally:

```bash
docker build --target api -t datapro-api .
docker build --target web-ecs -t datapro-web .
docker build --target mcp -t datapro-mcp .
```

## RDS / pgvector

1. Create a PostgreSQL 16 instance (or compatible).
2. As a superuser: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Set `DATABASE_URL` in `deploy/secrets.env` with `PGSSLMODE=require`.
4. Run `./deploy/scripts/run-migrate.sh` after the API image is pushed.

## Service discovery

The web task must reach the API by hostname. Options:

- **AWS Cloud Map** private DNS namespace (e.g. `datapro.local`) — register the API service; set `API_UPSTREAM_HOST=api.datapro.local` in `deploy/config.env`.
- **Service Connect** (ECS native) — configure in the AWS console/CloudFormation and align `API_UPSTREAM_HOST` with the connect DNS name.

## Updating a release

```bash
# bump tag in deploy/config.env if desired
./deploy/scripts/build-and-push.sh
./deploy/scripts/deploy-ecs.sh
```

## Troubleshooting

- **Task fails health check** — check `/ecs/datapro/api` logs; embedding model download on first start can take 1–2 minutes.
- **Web 502 on /api** — verify `API_UPSTREAM_HOST` and security groups (web → api on 8080).
- **Migration fails** — RDS security group must allow ingress from ECS tasks on 5432.

See also [secrets.md](secrets.md) and [docker.md](docker.md).
