"""LLM answer generation (Mistral, OpenAI, Claude, Gemini, OpenRouter, Ollama)."""

from __future__ import annotations

import requests

from llm_providers import API_KEY_ENV, DEFAULT_MODELS
from settings_service import get_api_key, get_llm_settings
from sql_dialect import (
    dialect_for_context,
    dialect_label,
    generation_rules,
    partial_generation_rules,
    repair_rules,
)
from sql_sanitize import normalize_llm_sql


def resolve_llm_runtime(
    *,
    backend: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str, str]:
    """Apply Settings defaults when request omits backend/model/base URL."""
    settings = get_llm_settings()
    resolved_backend = (backend or settings["default_backend"] or "mistral").strip().lower()
    resolved_model = (model or settings["default_model"] or "").strip()
    if not resolved_model:
        resolved_model = DEFAULT_MODELS.get(resolved_backend, DEFAULT_MODELS["mistral"])
    resolved_base = (base_url or settings["ollama_base_url"] or "http://localhost:11434").strip()
    return resolved_backend, resolved_model, resolved_base


def _strip_sql_response(text: str) -> str:
    return normalize_llm_sql(text)


def _sql_context_block(
    *,
    conversation_history: list[dict[str, str]] | None = None,
    prior_result=None,
) -> str:
    from conversation_context import format_conversation_block, format_prior_result_block

    history_block = format_conversation_block(conversation_history)
    prior_block = format_prior_result_block(prior_result)
    if not history_block and not prior_block:
        return ""
    return f"{history_block}{prior_block}"


def generate_sql(
    question: str,
    schema_context,
    *,
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
    gap_instructions: str = "",
    rag_supplement: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    prior_result=None,
) -> str:
    """LLM text-to-SQL from catalog schema context."""
    dialect = dialect_for_context(schema_context)
    expert = dialect_label(dialect)
    rag_block = f"\n{rag_supplement.strip()}\n" if rag_supplement.strip() else ""
    context_block = _sql_context_block(
        conversation_history=conversation_history,
        prior_result=prior_result,
    )
    prompt = f"""You are a {expert} SQL expert. Write ONE read-only SELECT query to answer the user question.

{schema_context.to_llm_prompt_block()}
{rag_block}
{context_block}User question:
{question}
{gap_instructions}

{generation_rules(dialect)}
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    return _strip_sql_response(raw)


def repair_sql(
    question: str,
    schema_context,
    failed_sql: str,
    error_message: str,
    *,
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
    gap_instructions: str = "",
    rag_supplement: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    prior_result=None,
) -> str:
    """Rewrite SQL after a validation or execution error."""
    dialect = dialect_for_context(schema_context)
    expert = dialect_label(dialect)
    rag_block = f"\n{rag_supplement.strip()}\n" if rag_supplement.strip() else ""
    context_block = _sql_context_block(
        conversation_history=conversation_history,
        prior_result=prior_result,
    )
    prompt = f"""You are a {expert} SQL expert. Fix the failed query using ONLY cataloged tables.

{schema_context.to_llm_prompt_block()}
{rag_block}
{context_block}User question:
{question}
{gap_instructions}

Failed SQL:
{failed_sql}

Error:
{error_message}

{repair_rules(dialect)}
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    return _strip_sql_response(raw)


def generate_partial_sql(
    question: str,
    schema_context,
    *,
    failed_sql: str = "",
    error_messages: list[str] | None = None,
    gap_instructions: str = "",
    rag_supplement: str = "",
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
) -> str:
    """Best-effort SQL when full question cannot be answered — skip missing elements."""
    dialect = dialect_for_context(schema_context)
    expert = dialect_label(dialect)
    errors = "\n".join(error_messages or []) or "(none)"
    rag_block = f"\n{rag_supplement.strip()}\n" if rag_supplement.strip() else ""
    prompt = f"""You are a {expert} SQL expert. The user asked a question that could not be fully answered.

{schema_context.to_llm_prompt_block()}
{rag_block}
User question:
{question}
{gap_instructions}

Previous SQL attempts failed:
{failed_sql or "(none)"}

Errors:
{errors}

Write ONE simpler read-only SELECT that answers what you CAN from the catalog only.
{partial_generation_rules(dialect)}
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    return _strip_sql_response(raw)


def _openai_compatible_chat(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    extra_headers: dict[str, str] | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    r = requests.post(
        url,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        headers=headers,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def generate_answer(
    prompt: str,
    *,
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
) -> str:
    resolved_backend, resolved_model, resolved_base = resolve_llm_runtime(
        backend=backend, model=model, base_url=base_url
    )

    if resolved_backend == "ollama":
        r = requests.post(
            f"{resolved_base.rstrip('/')}/api/generate",
            json={"model": resolved_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["response"]

    if resolved_backend == "anthropic":
        api_key = get_api_key("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (Settings → LLM)")
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": resolved_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        parts = data.get("content") or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")

    if resolved_backend == "gemini":
        api_key = get_api_key("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (Settings → LLM)")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)

    env_key = API_KEY_ENV.get(resolved_backend, "MISTRAL_API_KEY")
    api_key = get_api_key(env_key)
    if not api_key:
        raise RuntimeError(f"{env_key} is not set (Settings → LLM)")

    if resolved_backend == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        extra_headers = None
    elif resolved_backend == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        extra_headers = {
            "HTTP-Referer": "https://datapro.local",
            "X-Title": "DATA Pro",
        }
    else:
        url = "https://api.mistral.ai/v1/chat/completions"
        extra_headers = None

    return _openai_compatible_chat(
        url=url,
        api_key=api_key,
        model=resolved_model,
        prompt=prompt,
        extra_headers=extra_headers,
    )
