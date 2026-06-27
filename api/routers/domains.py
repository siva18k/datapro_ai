from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from catalog_db import (
    create_domain,
    create_domain_prompt,
    delete_domain,
    delete_domain_prompt,
    get_domain,
    get_domain_prompt,
    list_domain_prompts,
    list_domain_reference_docs,
    list_domains,
    update_domain,
    update_domain_prompt,
    upsert_domain_reference_doc,
)

router = APIRouter(prefix="/domains", tags=["domains"])


class DomainCreate(BaseModel):
    name: str
    description: str = ""


class DomainUpdate(BaseModel):
    description: str | None = None
    name: str | None = None
    enabled: bool | None = None


class DomainReferenceUpdate(BaseModel):
    content: str = Field(default="")


class DomainPromptCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    template: str = ""
    enabled: bool = True
    bind: bool = True


class DomainPromptUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    template: str | None = None
    enabled: bool | None = None
@router.get("")
def list_all(enabled_only: bool = False):
    return list_domains(enabled_only=enabled_only)


@router.post("", status_code=201)
def create(body: DomainCreate):
    return create_domain(body.name, body.description)


@router.get("/{domain_id}/references")
def list_references(domain_id: str):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    return list_domain_reference_docs(domain_id)


@router.put("/{domain_id}/references/{doc_type}")
def upsert_reference(domain_id: str, doc_type: str, body: DomainReferenceUpdate):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    if doc_type not in ("calendar", "glossary", "sql_notes"):
        raise HTTPException(400, "doc_type must be calendar, glossary, or sql_notes")
    try:
        return upsert_domain_reference_doc(domain_id, doc_type, body.content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{domain_id}/prompts")
def list_prompts(domain_id: str):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    return list_domain_prompts(domain_id)


@router.post("/{domain_id}/prompts", status_code=201)
def create_prompt(domain_id: str, body: DomainPromptCreate):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    try:
        return create_domain_prompt(
            domain_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            template=body.template,
            enabled=body.enabled,
            bind=body.bind,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{domain_id}/prompts/{prompt_id}")
def get_prompt(domain_id: str, prompt_id: str):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    row = get_domain_prompt(domain_id, prompt_id=prompt_id)
    if not row:
        raise HTTPException(404, "Prompt not found")
    return row


@router.patch("/{domain_id}/prompts/{prompt_id}")
def update_prompt(domain_id: str, prompt_id: str, body: DomainPromptUpdate):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    try:
        row = update_domain_prompt(
            domain_id,
            prompt_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            template=body.template,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not row:
        raise HTTPException(404, "Prompt not found")
    return row


@router.delete("/{domain_id}/prompts/{prompt_id}")
def remove_prompt(domain_id: str, prompt_id: str):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    if not delete_domain_prompt(domain_id, prompt_id):
        raise HTTPException(404, "Prompt not found")
    return {"deleted": True, "id": prompt_id}


@router.get("/{domain_id}")
def get_one(domain_id: str):
    row = get_domain(domain_id=domain_id)
    if not row:
        raise HTTPException(404, "Domain not found")
    return row


@router.patch("/{domain_id}")
def update(domain_id: str, body: DomainUpdate):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    fields = body.model_dump(exclude_none=True)
    if fields:
        update_domain(domain_id, **fields)
    return get_domain(domain_id=domain_id)


@router.delete("/{domain_id}")
def remove(domain_id: str):
    if not get_domain(domain_id=domain_id):
        raise HTTPException(404, "Domain not found")
    try:
        deleted = delete_domain(domain_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "Domain not found")
    return {"deleted": True, "id": domain_id}
