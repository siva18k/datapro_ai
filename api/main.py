"""FastAPI entrypoint — run: uvicorn api.main:app --reload --port 8080"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import bootstrap
from api.routers import agent_flows, agents, analytics, ask, backend, connections, datasets, domains, health, mcp, settings, trino_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap()
    yield


app = FastAPI(
    title="DATA Pro API",
    description="Multi-domain analytics catalog, RAG, and ask orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(backend.router, prefix="/api")
app.include_router(domains.router, prefix="/api")
app.include_router(datasets.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(mcp.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(agent_flows.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(connections.router, prefix="/api")
app.include_router(trino_service.router, prefix="/api")
