"""Thin HTTP client for calling DATA Pro MCP retrieval tools from Streamlit."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    project_env = Path(__file__).resolve().parent / ".env"
    load_dotenv(project_env, override=False)
    load_dotenv(override=False)

DEFAULT_MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")


def get_default_mcp_url() -> str:
    return DEFAULT_MCP_URL


def _normalize_chunk(item: dict) -> dict:
    return {
        "source": item["source_file"],
        "chunk_id": item["chunk_id"],
        "text": item["text"],
        "distance": float(item["distance"]),
    }


def _parse_tool_result(result) -> list[dict]:
    if result.isError:
        message = ""
        for block in result.content:
            if hasattr(block, "text"):
                message += block.text
        raise RuntimeError(message or "MCP tool call failed")

    chunks = []
    for block in result.content:
        if not hasattr(block, "text") or not block.text:
            continue
        parsed = json.loads(block.text)
        if isinstance(parsed, list):
            chunks.extend(_normalize_chunk(item) for item in parsed)
        else:
            chunks.append(_normalize_chunk(parsed))
    return chunks


async def _call_tool_raw(url: str, tool_name: str, arguments: dict) -> Any:
    async with streamablehttp_client(url, timeout=30) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool_name, arguments)


def call_tool(url: str, tool_name: str, arguments: dict | None = None) -> Any:
    """Call any MCP tool and return the raw CallToolResult."""
    return asyncio.run(_call_tool_raw(url, tool_name, arguments or {}))


async def _call_search_documents(
    url: str, query: str, top_k: int, domain: str | None = None
) -> list[dict]:
    async with streamablehttp_client(url, timeout=30) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            args: dict = {"query": query, "top_k": top_k}
            if domain:
                args["domain"] = domain
            result = await session.call_tool("search_documents", args)
            return _parse_tool_result(result)


async def _ping_mcp(url: str) -> bool:
    try:
        async with streamablehttp_client(url, timeout=3) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return True
    except Exception:
        return False


def search_documents(
    url: str, query: str, top_k: int = 3, domain: str | None = None
) -> list[dict]:
    """Call the MCP search_documents tool and return chunks in UI format."""
    return asyncio.run(_call_search_documents(url, query, top_k, domain))


def check_mcp_server(url: str) -> bool:
    """Return True if the MCP server accepts a session at the given URL."""
    return asyncio.run(_ping_mcp(url))


def _serialize_model(item) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json", exclude_none=True)
    if isinstance(item, dict):
        return item
    return {"value": str(item)}


async def _list_capabilities(url: str) -> dict:
    async with streamablehttp_client(url, timeout=15) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [_serialize_model(t) for t in (await session.list_tools()).tools]
            resources = [_serialize_model(r) for r in (await session.list_resources()).resources]
            prompts = [_serialize_model(p) for p in (await session.list_prompts()).prompts]
            return {"tools": tools, "resources": resources, "prompts": prompts}


def list_server_capabilities(url: str) -> dict:
    """Return tools, resources, and prompts exposed by a running MCP server."""
    return asyncio.run(_list_capabilities(url))


async def _get_prompt_text(url: str, name: str, arguments: dict | None = None) -> str:
    async with streamablehttp_client(url, timeout=15) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.get_prompt(name, arguments or {})
            parts = []
            for message in result.messages:
                content = getattr(message, "content", None)
                if hasattr(content, "text"):
                    parts.append(content.text)
                elif isinstance(content, str):
                    parts.append(content)
            return "\n\n".join(parts)


def get_prompt_preview(url: str, name: str, arguments: dict | None = None) -> str:
    """Render a prompt from the live MCP server."""
    args = {key: str(value) for key, value in (arguments or {}).items()}
    return asyncio.run(_get_prompt_text(url, name, args))


async def _read_resource_text(url: str, uri: str) -> str:
    async with streamablehttp_client(url, timeout=15) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.read_resource(uri)
            parts = []
            for block in result.contents:
                if hasattr(block, "text") and block.text:
                    parts.append(block.text)
                elif hasattr(block, "blob") and block.blob:
                    parts.append(str(block.blob))
            return "\n".join(parts)


def read_resource_preview(url: str, uri: str) -> str:
    """Read a resource from the live MCP server."""
    return asyncio.run(_read_resource_text(url, uri))
