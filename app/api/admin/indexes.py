from fastapi import APIRouter, Request

from app.schemas.admin import IndexBuildRequest, IndexBuildResponse

router = APIRouter(tags=["admin-catalogue"])


@router.post("/api/v1/admin/catalogue/indexes/build", response_model=IndexBuildResponse)
async def build_indexes(payload: IndexBuildRequest, request: Request):
    return await request.app.state.container.index_builder.build(payload.category, payload.rebuild)

