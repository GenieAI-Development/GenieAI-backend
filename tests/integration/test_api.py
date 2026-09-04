from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.ingestion.product_ingestion import ProductIngestion
from app.main import create_app
from app.schemas.recommendation import SmartShoppingResponse, TemporaryUnavailableResponse


class StubOrchestrator:
    async def execute(self, payload):
        return SmartShoppingResponse(
            request_id="req_test",
            session_id="00000000-0000-4000-8000-000000000001",
            request_type="product_recommendation",
            response_type="limited_results",
            message="A limited set.",
            result_count=0,
            products=[],
        )


def app_for(tmp_path):
    app = create_app(
        Settings(catalogue_dir=tmp_path / "catalogue", bm25_dir=tmp_path / "bm25")
    )
    app.state.container.orchestrator = StubOrchestrator()
    return app


def test_runtime_route_and_health(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        response = client.post(
            "/api/v1/recommendations",
            json={"request_type": "product_recommendation", "message": "romantic cake"},
        )
        assert response.status_code == 200
        assert response.json()["response_type"] == "limited_results"
        assert response.json()["request_id"] == "req_test"
        assert client.get("/healthz").json() == {"status": "ok"}


def test_temporary_unavailable_is_http_503(tmp_path):
    app = app_for(tmp_path)

    class UnavailableOrchestrator:
        async def execute(self, payload):
            return TemporaryUnavailableResponse(
                request_id="req_failure",
                session_id="00000000-0000-4000-8000-000000000001",
                request_type=payload.request_type,
                response_type="temporary_unavailable",
                message="Please try again.",
            )

    app.state.container.orchestrator = UnavailableOrchestrator()
    response = TestClient(app).post(
        "/api/v1/recommendations",
        json={"request_type": "product_recommendation", "message": "cake"},
    )
    assert response.status_code == 503
    assert response.json()["response_type"] == "temporary_unavailable"


def test_validation_uses_genieai_envelope(tmp_path):
    client = TestClient(app_for(tmp_path))
    response = client.post(
        "/api/v1/recommendations",
        json={"request_type": "unsupported", "message": "hello", "unknown": True},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["request_id"].startswith("req_")
    assert "detail" not in body


def test_malformed_json_is_400(tmp_path):
    client = TestClient(app_for(tmp_path))
    response = client.post(
        "/api/v1/recommendations",
        content=b'{"broken"',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_smart_shopping_rejects_context_and_gift_box_rejects_null(tmp_path):
    client = TestClient(app_for(tmp_path))
    smart = client.post(
        "/api/v1/recommendations",
        json={
            "request_type": "product_recommendation",
            "message": "cake",
            "workflow_context": {"theme": "romantic"},
        },
    )
    assert smart.status_code == 422
    gift = client.post(
        "/api/v1/recommendations",
        json={
            "request_type": "gift_box",
            "message": "make a box",
            "workflow_context": {"theme": None},
        },
    )
    assert gift.status_code == 422


class FakeKapruka:
    async def get_product(self, product_id):
        return {
            "id": product_id,
            "name": "Imported Cake",
            "description": "1 KG cake",
            "category": {"slug": "cakes"},
            "attributes": {"vendor": "Vendor"},
            "price": {"amount": 5000},
        }

    async def validate_delivery(self, city, delivery_date):
        return True


def test_admin_product_import_route(tmp_path):
    app = app_for(tmp_path)
    app.state.container.product_ingestion = ProductIngestion(
        app.state.container.repository, FakeKapruka()
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/admin/catalogue/products/import",
        json={"category": "cakes", "product_ids": ["C1", "C1"]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "category": "cakes",
        "imported_count": 1,
        "failed_product_ids": [],
    }
    assert app.state.container.repository.get_product("cakes", "C1") is not None
