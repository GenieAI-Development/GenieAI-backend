from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas.recommendation import RecommendationRequest, RuntimeResponse


router = APIRouter(tags=["recommendations"])


@router.post("/api/v1/recommendations", response_model=RuntimeResponse)
async def recommendations(payload: RecommendationRequest, request: Request):
    result = await request.app.state.container.orchestrator.execute(payload)
    status_code = 503 if result.response_type == "temporary_unavailable" else 200
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))
