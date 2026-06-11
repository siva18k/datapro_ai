from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.analytics_models import AnalyticsRequest, AnalyticsResponse
from api.analytics_runner import collect_analytics_response, run_analytics_events
from api.deps import get_embedder

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/run", response_model=AnalyticsResponse)
def analytics_run(body: AnalyticsRequest):
    return collect_analytics_response(body, get_embedder())


@router.post("/stream")
def analytics_stream(body: AnalyticsRequest):
    embedder = get_embedder()

    def generate():
        try:
            for event in run_analytics_events(body, embedder):
                yield json.dumps(event) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
