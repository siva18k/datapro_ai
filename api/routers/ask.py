from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.ask_export import build_chart_page, build_csv, build_html_page
from api.ask_models import AskExportRequest, AskExportResponse, AskRequest, AskResponse
from api.ask_runner import collect_ask_response, run_ask_events
from api.deps import get_embedder

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask(body: AskRequest):
    embedder = get_embedder()
    return collect_ask_response(body, embedder)


@router.post("/export", response_model=AskExportResponse)
def ask_export(body: AskExportRequest):
    fmt = body.format.lower().strip()
    if fmt == "csv":
        content = build_csv(
            question=body.question,
            answer=body.answer,
            columns=body.columns,
            rows=body.rows,
        )
        return AskExportResponse(
            format="csv",
            content_type="text/csv",
            content=content,
            filename="ask-export.csv",
        )
    if fmt == "html":
        content = build_html_page(
            question=body.question,
            answer=body.answer,
            columns=body.columns,
            rows=body.rows,
            sql=body.sql,
            domain_name=body.domain_name,
        )
        return AskExportResponse(
            format="html",
            content_type="text/html",
            content=content,
            filename="ask-export.html",
        )
    if fmt == "chart":
        content = build_chart_page(
            question=body.question,
            answer=body.answer,
            columns=body.columns,
            rows=body.rows,
        )
        return AskExportResponse(
            format="chart",
            content_type="text/html",
            content=content,
            filename="ask-chart.html",
        )
    raise HTTPException(400, "format must be html, csv, or chart")


@router.post("/stream")
def ask_stream(body: AskRequest):
    """NDJSON stream: `{"type":"status","message":"..."}` then `{"type":"result","data":{...}}`."""
    embedder = get_embedder()

    def generate():
        try:
            for event in run_ask_events(body, embedder):
                yield json.dumps(event) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
