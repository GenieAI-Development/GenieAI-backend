from fastapi import APIRouter, Request

from app.schemas.admin import CatalogueHealthResponse

router = APIRouter(tags=["admin-catalogue"])


@router.get("/api/v1/admin/catalogue/{category}/health", response_model=CatalogueHealthResponse)
async def catalogue_health(category: str, request: Request):
    return await request.app.state.container.index_builder.health(category)

