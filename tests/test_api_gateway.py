import importlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.auth_service.app.security import create_access_token

ORDER_ID = "11111111-1111-1111-1111-111111111111"
ADMIN_ID = UUID("22222222-2222-2222-2222-222222222222")
ACCESS_TOKEN_SECRET = "test-access-token-secret"


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
            f"/api/v1/products/{ORDER_ID}",
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
            f"/api/v1/orders/{ORDER_ID}/status",
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

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["timeout"] = timeout
        return FakeResponse(status_code=201, body=b'{"ok": true}')

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


def test_gateway_requires_admin_token_for_internal_routes(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    urlopen_was_called = False

    def fake_urlopen(request, timeout):
        nonlocal urlopen_was_called
        urlopen_was_called = True
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    response = TestClient(module.app).post(
        "/api/v1/internal/products",
        json={"name": "Admin lamp"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token is required"
    assert response.headers["www-authenticate"] == "Bearer"
    assert not urlopen_was_called


def test_gateway_authorizes_admin_before_forwarding(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    access_token = make_access_token()
    captured = {"urls": []}

    def fake_urlopen(request, timeout):
        captured["urls"].append(request.full_url)
        headers = {key.lower(): value for key, value in request.header_items()}

        captured["upstream_url"] = request.full_url
        captured["upstream_method"] = request.get_method()
        captured["upstream_body"] = request.data
        captured["upstream_auth_header"] = headers["authorization"]
        return FakeResponse(status_code=201, body=b'{"ok": true}')

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    response = TestClient(module.app).post(
        "/api/v1/internal/products",
        json={"name": "Admin lamp"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 201
    assert response.json() == {"ok": True}
    assert captured["urls"] == ["http://product.local/api/v1/internal/products"]
    assert captured["upstream_auth_header"] == f"Bearer {access_token}"
    assert captured["upstream_method"] == "POST"
    assert json.loads(captured["upstream_body"]) == {"name": "Admin lamp"}


def test_gateway_rejects_invalid_admin_token(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    captured_urls = []

    def fake_urlopen(request, timeout):
        captured_urls.append(request.full_url)
        return FakeResponse(status_code=401, body=b'{"detail": "invalid"}')

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    response = TestClient(module.app).patch(
        f"/api/v1/internal/orders/{ORDER_ID}/status",
        json={"status": "confirmed"},
        headers={"Authorization": "Bearer bad-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Access token is invalid"
    assert captured_urls == []


def test_gateway_rejects_expired_admin_token(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    urlopen_was_called = False

    def fake_urlopen(request, timeout):
        nonlocal urlopen_was_called
        urlopen_was_called = True
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    response = TestClient(module.app).patch(
        f"/api/v1/internal/orders/{ORDER_ID}/status",
        json={"status": "confirmed"},
        headers={"Authorization": f"Bearer {make_expired_access_token()}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Access token is expired"
    assert not urlopen_was_called


def test_gateway_protects_full_order_details(monkeypatch) -> None:
    module = gateway_module(monkeypatch)

    response = TestClient(module.app).get(f"/api/v1/orders/{ORDER_ID}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token is required"


def test_gateway_keeps_order_creation_and_status_public(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    captured_urls = []

    def fake_urlopen(request, timeout):
        captured_urls.append(request.full_url)
        return FakeResponse(body=b'{"ok": true}')

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    client = TestClient(module.app)
    create_response = client.post(
        "/api/v1/orders",
        json={"items": []},
    )
    status_response = client.get(f"/api/v1/orders/{ORDER_ID}/status")

    assert create_response.status_code == 200
    assert status_response.status_code == 200
    assert captured_urls == [
        "http://order.local/api/v1/orders",
        f"http://order.local/api/v1/orders/{ORDER_ID}/status",
    ]


def test_gateway_requires_admin_token_for_registration(monkeypatch) -> None:
    module = gateway_module(monkeypatch)
    client = TestClient(module.app)

    for path in ("/register", "/register/"):
        response = client.post(
            path,
            json={"email": "admin@example.com", "password": "strong-password"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Bearer token is required"


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.status = status_code
        self.headers = headers or {"content-type": "application/json"}
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self._body


def gateway_module(monkeypatch):
    module = importlib.import_module("services.api_gateway_service.app.main")
    settings = module.Settings(
        auth_service_url="http://auth.local",
        product_service_url="http://product.local",
        order_service_url="http://order.local",
        upstream_timeout_seconds=1.5,
        access_token_secret=ACCESS_TOKEN_SECRET,
        _env_file=None,
    )
    monkeypatch.setattr(module, "settings", settings)
    return module


def make_access_token() -> str:
    return create_access_token(
        ADMIN_ID,
        ACCESS_TOKEN_SECRET,
        900,
    )


def make_expired_access_token() -> str:
    return create_access_token(
        ADMIN_ID,
        ACCESS_TOKEN_SECRET,
        1,
        now=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
