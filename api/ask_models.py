from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str
    top_k: int = Field(default=3, ge=1, le=8)
    domain_override: str | None = None
    domain_overrides: list[str] | None = None
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


class PipelineChunkRef(BaseModel):
    source_file: str
    chunk_id: str
    distance: float | None = None
    domain_id: str | None = None
    source_id: str | None = None
    text_preview: str | None = None
    verify_sql: str


class PipelineTraceDetail(BaseModel):
    question: str | None = None
    top_k: int | None = None
    domain_override: str | None = None
    domain_overrides: list[str] | None = None
    domain_id: str | None = None
    domain_name: str | None = None
    routing_method: str | None = None
    routing_confidence: float | None = None
    execution_kind: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    retrieval: str | None = None
    retrieval_query: str | None = None
    mcp_url: str | None = None
    mcp_tool: str | None = None
    mcp_arguments: dict[str, Any] | None = None
    llm_prompt: str | None = None
    sql: str | None = None
    columns: list[str] | None = None
    row_count: int | None = None
    chunks: list[PipelineChunkRef] | None = None


class PipelineTraceStep(BaseModel):
    message: str
    phase: str
    detail: PipelineTraceDetail | None = None


class AskResponse(BaseModel):
    answer: str
    question: str | None = None
    domain_name: str | None = None
    routing_method: str | None = None
    routing_confidence: float | None = None
    query_kind: str | None = None
    used_rag: bool = False
    used_mcp: bool = False
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
