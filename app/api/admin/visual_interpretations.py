from fastapi import APIRouter, HTTPException, Request

from app.schemas.admin import VisualInterpretationImportRequest, VisualInterpretationImportResponse
from app.ingestion.visual_interpretation_import import UnknownInterpretationProductError
from app.repositories.catalogue_repository import CatalogueNotFoundError

router = APIRouter(tags=["admin-catalogue"])


@router.post(
    "/api/v1/admin/catalogue/visual-interpretations/import",
    response_model=VisualInterpretationImportResponse,
)
async def import_visual_interpretations(payload: VisualInterpretationImportRequest, request: Request):
    try:
        return request.app.state.container.visual_importer.import_items(payload)
    except CatalogueNotFoundError as exc:
        raise HTTPException(status_code=404, detail="category catalogue not found") from exc
    except UnknownInterpretationProductError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
