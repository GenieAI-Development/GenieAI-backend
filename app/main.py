from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.admin.catalogue import router as catalogue_router
from app.api.admin.indexes import router as indexes_router
from app.api.admin.products import router as products_router
from app.api.admin.visual_interpretations import router as visuals_router
from app.api.runtime.recommendations import router as recommendations_router
from app.config.settings import Settings, get_settings
from app.dependencies import build_container
from app.observability.logging import configure_logging
from app.observability.tracing import new_request_id


def _validation_details(exc: RequestValidationError):
    details = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error["loc"] if part not in {"body"})
        details.append({"field": path or "request", "issue": error["msg"]})
    return details


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    container = build_container(settings or get_settings())

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        await container.close()

    application = FastAPI(
        title="GenieAI Recommendation Service", version="0.1.0", lifespan=lifespan
    )
    application.state.container = container

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        malformed = any(error["type"] == "json_invalid" for error in exc.errors())
        session_id = None
        if isinstance(exc.body, dict) and isinstance(exc.body.get("session_id"), str):
            supplied = exc.body["session_id"]
            if await application.state.container.sessions.get(supplied):
                session_id = supplied
        body = {
            "request_id": new_request_id(),
            "session_id": session_id,
            "error": {
                "code": "INVALID_REQUEST",
                "message": "The request contains invalid fields.",
                "details": _validation_details(exc),
            },
        }
        if session_id is None:
            body.pop("session_id")
        return JSONResponse(status_code=400 if malformed else 422, content=body)

    application.include_router(recommendations_router)
    application.include_router(products_router)
    application.include_router(visuals_router)
    application.include_router(indexes_router)
    application.include_router(catalogue_router)

    @application.get("/healthz", tags=["health"])
    async def healthz():
        return {"status": "ok"}

    return application


app = create_app()
