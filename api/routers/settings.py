from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from settings_service import get_public_settings, save_settings, test_database_connection

router = APIRouter(prefix="/settings", tags=["settings"])


class DatabaseSettings(BaseModel):
    use_database_url: bool = False
    database_url: str = ""
    host: str = ""
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    schema: str = "ragpro"
    sslmode: str = "require"


class LlmSettings(BaseModel):
    default_backend: str | None = None
    default_model: str | None = None
    ollama_base_url: str | None = None
    mistral_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None


class AskSettings(BaseModel):
    conversation_turns: int | None = Field(default=None, ge=0, le=20)
    retrieval_top_k: int | None = Field(default=None, ge=1, le=8)


class SettingsUpdate(BaseModel):
    database: DatabaseSettings | None = None
    mcp_url: str | None = None
    embedding_model: str | None = None
    ask: AskSettings | None = None
    llm: LlmSettings | None = None
    # Legacy top-level key
    mistral_api_key: str | None = None


class TestDatabaseBody(BaseModel):
    database: DatabaseSettings


@router.get("")
def get_settings():
    return get_public_settings()


@router.put("")
def put_settings(body: SettingsUpdate):
    try:
        return save_settings(body.model_dump(exclude_none=True))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/test-database")
def test_db(body: TestDatabaseBody | None = None):
    overrides = body.model_dump() if body else None
    ok, message = test_database_connection(overrides)
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message}
