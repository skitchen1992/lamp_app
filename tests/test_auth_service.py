import importlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from services.auth_service.app.schemas import AuthResponse, TokenResponse, UserResponse
from services.auth_service.app.security import create_access_token, read_access_token

USER_ID = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)


class FakeAuthService:
    def __init__(self, module) -> None:
        self.module = module
        self.register_payload = None
        self.login_payload = None
        self.refresh_payload = None
        self.logout_token = None
        self.me_token = None

    async def register(self, payload):
        self.register_payload = payload
        return make_auth_response(email=payload.email, full_name=payload.full_name)

    async def login(self, payload):
        self.login_payload = payload
        if payload.password == "wrong":
            raise self.module.InvalidCredentials
        return make_auth_response(email=payload.email)

    async def refresh(self, payload):
        self.refresh_payload = payload
        if payload.refresh_token == "bad-refresh-token":
            raise self.module.InvalidRefreshToken
        return TokenResponse(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            expires_in=900,
        )

    async def logout(self, refresh_token: str) -> None:
        self.logout_token = refresh_token
        if refresh_token == "bad-refresh-token":
            raise self.module.InvalidRefreshToken

    async def me(self, access_token: str):
        self.me_token = access_token
        if access_token == "bad-access-token":
            raise self.module.InvalidAccessToken
        return make_user_response()


def test_register_returns_user_and_tokens(monkeypatch) -> None:
    module, service = auth_module_with_fake_service(monkeypatch)

    response = TestClient(module.app).post(
        "/register",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "fullName": "Nikita",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "user@example.com"
    assert payload["user"]["fullName"] == "Nikita"
    assert payload["accessToken"] == "access-token"
    assert payload["refreshToken"] == "refresh-token"
    assert service.register_payload.full_name == "Nikita"


def test_login_rejects_invalid_credentials(monkeypatch) -> None:
    module, _service = auth_module_with_fake_service(monkeypatch)

    response = TestClient(module.app).post(
        "/login",
        json={"email": "user@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_refresh_rotates_token(monkeypatch) -> None:
    module, service = auth_module_with_fake_service(monkeypatch)

    response = TestClient(module.app).post(
        "/refresh",
        json={"refreshToken": "refresh-token"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "new-access-token"
    assert response.json()["refreshToken"] == "new-refresh-token"
    assert service.refresh_payload.refresh_token == "refresh-token"


def test_logout_revokes_refresh_token(monkeypatch) -> None:
    module, service = auth_module_with_fake_service(monkeypatch)

    response = TestClient(module.app).post(
        "/logout",
        json={"refreshToken": "refresh-token"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"
    assert service.logout_token == "refresh-token"


def test_me_reads_bearer_token(monkeypatch) -> None:
    module, service = auth_module_with_fake_service(monkeypatch)

    response = TestClient(module.app).get(
        "/me",
        headers={"Authorization": "Bearer access-token"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    assert service.me_token == "access-token"


def test_me_requires_bearer_token(monkeypatch) -> None:
    module, _service = auth_module_with_fake_service(monkeypatch)

    response = TestClient(module.app).get("/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token is required"


def test_access_token_roundtrip() -> None:
    token = create_access_token(
        USER_ID,
        "test-secret",
        900,
        now=NOW,
    )

    assert read_access_token(token, "test-secret", now=NOW) == USER_ID


def auth_module_with_fake_service(monkeypatch):
    monkeypatch.setenv("AUTH_DATABASE_PASSWORD", "auth_password")
    module = importlib.import_module("services.auth_service.app.main")
    service = FakeAuthService(module)
    monkeypatch.setattr(module, "auth_service", service)
    return module, service


def make_auth_response(
    *,
    email: str = "user@example.com",
    full_name: str | None = None,
) -> AuthResponse:
    return AuthResponse(
        user=make_user_response(email=email, full_name=full_name),
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=900,
    )


def make_user_response(
    *,
    email: str = "user@example.com",
    full_name: str | None = None,
) -> UserResponse:
    return UserResponse(
        id=USER_ID,
        email=email,
        full_name=full_name,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
