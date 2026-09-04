from fastapi import APIRouter, Request

from app.schemas.admin import ProductImportRequest, ProductImportResponse

router = APIRouter(tags=["admin-catalogue"])


@router.post("/api/v1/admin/catalogue/products/import", response_model=ProductImportResponse)
async def import_products(payload: ProductImportRequest, request: Request):
    return await request.app.state.container.product_ingestion.import_products(payload)

