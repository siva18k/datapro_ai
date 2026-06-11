"""Editable MCP server registry (tools, resources, prompts, server config)."""

from __future__ import annotations

import ast
import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = PROJECT_DIR / "mcp_registry.json"

REGISTRY_DEFAULTS: dict[str, Any] = {
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "path": "/mcp",
        "transport": "streamable-http",
        "stateless": True,
        "instructions": (
            "DATA Pro multi-domain knowledge base (Postgres/pgvector). "
            "Domains include HR, Finance, Sales, and General. "
            "Use list_domains and list_domain_sources to discover scope, then search_documents "
            "with an optional domain filter. Answer only from retrieved context."
        ),
    },
    "tools": {
        "list_domains": {
            "description": "List enabled business domains (HR, Finance, Sales, etc.).",
            "enabled": True,
        },
        "list_domain_sources": {
            "description": "List data sources registered under a domain (by slug or name).",
            "enabled": True,
        },
        "get_rag_profile": {
            "description": "Return RAG profile settings and instructions for a data source.",
            "enabled": True,
        },
        "search_documents": {
            "description": "Semantic search over ingested chunks. Optional domain filter (slug or name).",
            "enabled": True,
        },
        "list_sources": {
            "description": "List ingested source files with chunk counts and last-ingested timestamps.",
            "enabled": True,
        },
        "get_chunk": {
            "description": "Fetch one chunk by source file name and chunk id (e.g. travel_policy.md / chunk_00).",
            "enabled": True,
        },
        "knowledge_base_stats": {
            "description": "Return total chunk count and number of ingested source files.",
            "enabled": True,
        },
        "list_available_documents": {
            "description": "List files on disk that can be ingested (may not yet be in the database).",
            "enabled": True,
        },
        "ingest_documents": {
            "description": "Ingest documents from sample_docs (or docs_path) into the knowledge base.",
            "enabled": True,
        },
    },
    "resources": {
        "ragpro://domains": {
            "name": "domains",
            "description": "All enabled business domains in the catalog.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://domains/{domain}/sources": {
            "name": "domain_sources",
            "description": "Data sources registered under a domain.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://domains/{domain}/stats": {
            "name": "domain_stats",
            "description": "Chunk counts per source within a domain.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://knowledge-base/stats": {
            "name": "knowledge_base_stats",
            "description": "Knowledge base totals, source count, and embedding model.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://knowledge-base/sources": {
            "name": "ingested_sources",
            "description": "All ingested source files with chunk counts.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://chunks/{source_file}/{chunk_id}": {
            "name": "chunk",
            "description": "A single ingested chunk from the knowledge base.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://documents/{source_file}": {
            "name": "ingested_document",
            "description": "All ingested chunks for a source file, ordered by chunk id.",
            "mime_type": "application/json",
            "enabled": True,
        },
        "ragpro://sample-docs/{file_name}": {
            "name": "sample_document",
            "description": "Raw document text from sample_docs on disk.",
            "mime_type": "text/plain",
            "enabled": True,
        },
    },
    "prompts": {
        "citation_rules": {
            "description": "Grounding and citation rules for answering from the knowledge base.",
            "template": """You are an internal knowledge assistant.
Answer only from provided document context retrieved via ragpro tools or resources.
If the answer is not supported by the context, say:
"I do not know based on the provided documents."
Always cite sources in the format [source_file - chunk_id].
Be concise, helpful, and conversational.""",
            "enabled": True,
        },
        "grounded_answer": {
            "description": "Retrieve top chunks for a question and return a grounded answer prompt.",
            "template": """{citation_rules}

User question:
{question}

Context:
{context}""",
            "enabled": True,
        },
        "summarize_document": {
            "description": "Build a prompt to summarize one ingested source file from the knowledge base.",
            "template": """Summarize the following ingested document.
Use only the text below. Cite chunk ids where helpful.

Document: {source_file}

{body}""",
            "enabled": True,
        },
        "domain_grounded_answer": {
            "description": "Retrieve domain-scoped chunks and build a grounded answer prompt.",
            "template": """{citation_rules}

Business domain: {domain_name}

User question:
{question}

Context:
{context}""",
            "enabled": True,
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_registry(*, create_if_missing: bool = True) -> dict[str, Any]:
    if REGISTRY_PATH.exists():
        with REGISTRY_PATH.open(encoding="utf-8") as handle:
            stored = json.load(handle)
        return _deep_merge(REGISTRY_DEFAULTS, stored)

    registry = copy.deepcopy(REGISTRY_DEFAULTS)
    if create_if_missing:
        save_registry(registry)
    return registry


def save_registry(registry: dict[str, Any]) -> None:
    merged = _deep_merge(REGISTRY_DEFAULTS, registry)
    with REGISTRY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2)
        handle.write("\n")


def reset_registry() -> dict[str, Any]:
    registry = copy.deepcopy(REGISTRY_DEFAULTS)
    save_registry(registry)
    return registry


def is_enabled(section: str, name: str, registry: dict[str, Any] | None = None) -> bool:
    data = (registry or load_registry()).get(section, {}).get(name, {})
    return bool(data.get("enabled", True))


def get_tool_description(name: str, registry: dict[str, Any] | None = None) -> str:
    data = (registry or load_registry())["tools"].get(name, {})
    return str(data.get("description") or REGISTRY_DEFAULTS["tools"][name]["description"])


def get_resource_meta(uri: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry or load_registry()
    defaults = REGISTRY_DEFAULTS["resources"].get(uri, {})
    data = reg.get("resources", {}).get(uri, {})
    return {
        "name": data.get("name", defaults.get("name", uri)),
        "description": data.get("description", defaults.get("description", "")),
        "mime_type": data.get("mime_type", defaults.get("mime_type", "text/plain")),
        "enabled": data.get("enabled", defaults.get("enabled", True)),
    }


def get_prompt_meta(name: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry or load_registry()
    defaults = REGISTRY_DEFAULTS["prompts"].get(name, {})
    data = reg.get("prompts", {}).get(name, {})
    return {
        "description": data.get("description", defaults.get("description", "")),
        "template": data.get("template", defaults.get("template", "")),
        "enabled": data.get("enabled", defaults.get("enabled", True)),
    }


def build_mcp_url(registry: dict[str, Any] | None = None, *, for_client: bool = True) -> str:
    server = (registry or load_registry())["server"]
    host = server.get("host", "0.0.0.0")
    port = int(server.get("port", 8000))
    path = server.get("path", "/mcp")
    if for_client and host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    path = path if path.startswith("/") else f"/{path}"
    return f"http://{host}:{port}{path}"


MCP_SERVER_PATH = PROJECT_DIR / "mcp_server.py"


@lru_cache(maxsize=1)
def _mcp_server_source() -> str:
    return MCP_SERVER_PATH.read_text(encoding="utf-8")


def get_tool_implementation(tool_name: str) -> str:
    """Return the Python source of a tool function from mcp_server.py."""
    source = _mcp_server_source()
    tree = ast.parse(source)
    candidates = {tool_name, f"{tool_name}_tool"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in candidates:
            segment = ast.get_source_segment(source, node)
            if segment:
                return segment.strip()
    return ""

