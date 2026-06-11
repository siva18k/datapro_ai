"""LLM provider metadata and default models."""

from __future__ import annotations

EMBEDDING_MODEL_OPTIONS = (
    "all-MiniLM-L6-v2",
    "all-mpnet-base-v2",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

LLM_BACKENDS: list[dict[str, str]] = [
    {"id": "mistral", "label": "Mistral", "default_model": "mistral-small-latest"},
    {"id": "openai", "label": "OpenAI", "default_model": "gpt-4o-mini"},
    {"id": "anthropic", "label": "Claude (Anthropic)", "default_model": "claude-sonnet-4-20250514"},
    {"id": "gemini", "label": "Gemini (Google)", "default_model": "gemini-2.0-flash"},
    {"id": "openrouter", "label": "OpenRouter", "default_model": "openai/gpt-4o-mini"},
    {"id": "ollama", "label": "Ollama (local)", "default_model": "phi3:mini"},
]

DEFAULT_LLM_BACKEND = "mistral"

DEFAULT_MODELS = {b["id"]: b["default_model"] for b in LLM_BACKENDS}

API_KEY_ENV: dict[str, str] = {
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
