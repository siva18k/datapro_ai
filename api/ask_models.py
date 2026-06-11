from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str
    top_k: int = Field(default=3, ge=1, le=8)
    domain_override: str | None = None
    use_mcp: bool = False
    mcp_url: str | None = None
    backend: str | None = None
    model: str | None = None
    ollama_base_url: str | None = None
    debug: bool = False


class SourceChunk(BaseModel):
    source: str
    chunk_id: str
    text: str
    distance: float | None = None


class AskResponse(BaseModel):
    answer: str
    question: str | None = None
    domain_name: str | None = None
    routing_method: str | None = None
    routing_confidence: float | None = None
    query_kind: str | None = None
    sources: list[SourceChunk]
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list] | None = None


class AskExportRequest(BaseModel):
    format: str  # html | csv | chart
    question: str
    answer: str
    domain_name: str | None = None
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list] | None = None


class AskExportResponse(BaseModel):
    format: str
    content_type: str
    content: str
    filename: str
