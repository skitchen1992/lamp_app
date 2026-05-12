import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("path", "expected_name", "expected_base_url"),
    [
        (
            "/register",
            "auth-service",
            "http://auth.local",
        ),
        (
            "/me",
            "auth-service",
            "http://auth.local",
        ),
        (
            "/api/v1/products",
            "product-management-service",
            "http://product.local",
        ),
        (
            "/api/v1/products/11111111-1111-1111-1111-111111111111",
            "product-management-service",
            "http://product.local",
        ),
        (
            "/api/v1/internal/categories",
            "product-management-service",
            "http://product.local",
        ),
        (
            "/api/v1/cart/calculate",
            "order-management-service",
            "http://order.local",
        ),
        (
            "/api/v1/orders/11111111-1111-1111-1111-111111111111/status",
            "order-management-service",
            "http://order.local",
        ),
        (
            "/api/v1/internal/orders",
            "order-management-service",
            "http://order.local",
        ),
    ],
)
def test_gateway_resolves_routes_to_registered_upstreams(
    monkeypatch,
    path: str,
    expected_name: str,
    expected_base_url: str,
) -> None:
    module = gateway_module(monkeypatch)

    upstream = module.resolve_upstream(path)

    assert upstream is not None
    assert upstream.name == expected_name
    assert upstream.base_url == expected_base_url


def test_gateway_returns_404_for_unregistered_route(monkeypatch) -> None:
    module = gateway_module(monkeypatch)

    response = TestClient(module.app).get("/api/v1/payments")

    assert response.status_code == 404
    assert response.json()["detail"] == "Route is not registered in API Gateway"


def test_gateway_forwards_request_to_selected_upstream(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    captured = {}

    class FakeUpstreamResponse:
        status = 201
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["timeout"] = timeout
        return FakeUpstreamResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    response = TestClient(module.app).post(
        "/api/v1/products?query=lamp",
        json={"name": "Lamp"},
        headers={"x-request-id": "request-1"},
    )

    assert response.status_code == 201
    assert response.json() == {"ok": True}
    assert captured["url"] == "http://product.local/api/v1/products?query=lamp"
    assert captured["method"] == "POST"
    assert json.loads(captured["body"]) == {"name": "Lamp"}
    assert captured["headers"]["x-request-id"] == "request-1"
    assert captured["headers"]["x-forwarded-host"] == "testserver"
    assert captured["headers"]["x-forwarded-proto"] == "http"
    assert captured["timeout"] == 1.5


def gateway_module(monkeypatch):
    module = importlib.import_module("services.api_gateway_service.app.main")
    settings = module.Settings(
        auth_service_url="http://auth.local",
        product_service_url="http://product.local",
        order_service_url="http://order.local",
        upstream_timeout_seconds=1.5,
        _env_file=None,
    )
    monkeypatch.setattr(module, "settings", settings)
    return module
