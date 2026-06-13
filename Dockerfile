# syntax=docker/dockerfile:1

# --- Build React UI ---
FROM node:20-alpine AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- Python API / MCP runtime ---
FROM python:3.11-slim AS python-base
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# --- Nginx serves built UI and proxies /api ---
FROM nginx:alpine AS web
COPY --from=web-build /app/web/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

# ECS / Cloud Map: set API_UPSTREAM_HOST to the internal API service hostname.
FROM nginx:alpine AS web-ecs
COPY --from=web-build /app/web/dist /usr/share/nginx/html
COPY docker/nginx.ecs.conf.template /etc/nginx/templates/default.conf.template
ENV API_UPSTREAM_HOST=api
EXPOSE 80

# --- Default image target: API ---
FROM python-base AS api
EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM python-base AS mcp
EXPOSE 8000
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_PATH=/mcp
CMD ["python", "mcp_server.py"]
