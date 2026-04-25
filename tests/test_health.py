import importlib

from fastapi.testclient import TestClient


SERVICE_MODULES = [
    "services.product_management_service.app.main",
    "services.order_management_service.app.main",
    "services.admin_panel_service.app.main",
]


def set_required_database_passwords(monkeypatch):
    monkeypatch.setenv("PRODUCT_DATABASE_PASSWORD", "product_password")
    monkeypatch.setenv("ORDER_DATABASE_PASSWORD", "order_password")
    monkeypatch.setenv("ADMIN_DATABASE_PASSWORD", "admin_password")


def test_health_endpoint_returns_service_status(monkeypatch):
    set_required_database_passwords(monkeypatch)

    async def fake_check_database(database_url: str) -> None:
        assert database_url

    for module_name in SERVICE_MODULES:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, "check_database", fake_check_database)

        response = TestClient(module.app).get("/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["database"] == "ok"
        assert payload["service"] == module.settings.service_name


def test_settings_builds_database_url_from_split_environment(monkeypatch):
    monkeypatch.delenv("PRODUCT_DATABASE_URL", raising=False)
    monkeypatch.setenv("PRODUCT_DATABASE_HOST", "product-db")
    monkeypatch.setenv("PRODUCT_DATABASE_PORT", "5432")
    monkeypatch.setenv("PRODUCT_DATABASE_NAME", "product_db")
    monkeypatch.setenv("PRODUCT_DATABASE_USER", "product_user")
    monkeypatch.setenv("PRODUCT_DATABASE_PASSWORD", "product_password")

    module = importlib.import_module("services.product_management_service.app.main")
    settings = module.Settings(_env_file=None)

    assert (
        settings.database_url
        == "postgresql://product_user:product_password@product-db:5432/product_db"
    )


def test_settings_prefers_explicit_database_url(monkeypatch):
    database_url = "postgresql://explicit_user:explicit_password@db:5432/explicit_db"

    monkeypatch.setenv("PRODUCT_DATABASE_URL", database_url)

    module = importlib.import_module("services.product_management_service.app.main")
    settings = module.Settings(_env_file=None)

    assert settings.database_url == database_url
