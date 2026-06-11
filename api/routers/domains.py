from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from catalog_db import create_domain, delete_domain, get_domain, list_domains, update_domain

router = APIRouter(prefix="/domains", tags=["domains"])


class DomainCreate(BaseModel):
    name: str
    description: str = ""


class DomainUpdate(BaseModel):
    description: str | None = None
    name: str | None = None
    enabled: bool | None = None


@router.get("")
def list_all(enabled_only: bool = False):
    return list_domains(enabled_only=enabled_only)


@router.post("", status_code=201)
def create(body: DomainCreate):
    return create_domain(body.name, body.description)


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
