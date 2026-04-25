import importlib
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values
from fastapi.testclient import TestClient


SERVICE_MODULES = [
    "services.product_management_service.app.main",
    "services.order_management_service.app.main",
    "services.admin_panel_service.app.main",
]
DATABASE_PASSWORD_ENV_NAMES = [
    "PRODUCT_DATABASE_PASSWORD",
    "ORDER_DATABASE_PASSWORD",
    "ADMIN_DATABASE_PASSWORD",
]
DOTENV_VALUES = dotenv_values(Path(__file__).resolve().parents[1] / ".env")


def required_env_value(env_name: str) -> str:
    value = os.environ.get(env_name) or DOTENV_VALUES.get(env_name)
    if not value:
        raise RuntimeError(f"{env_name} must be set in the environment or .env")
    return value


def set_required_database_passwords(monkeypatch):
    for env_name in DATABASE_PASSWORD_ENV_NAMES:
        monkeypatch.setenv(env_name, required_env_value(env_name))


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
    product_database_password = required_env_value("PRODUCT_DATABASE_PASSWORD")
    monkeypatch.setenv("PRODUCT_DATABASE_PASSWORD", product_database_password)

    module = importlib.import_module("services.product_management_service.app.main")
    settings = module.Settings(_env_file=None)

    assert (
        settings.database_url == f"postgresql://product_user:"
        f"{quote(product_database_password, safe='')}@product-db:5432/product_db"
    )


def test_settings_prefers_explicit_database_url(monkeypatch):
    database_url = (
        "postgresql://explicit_user:"
        f"{quote(required_env_value('PRODUCT_DATABASE_PASSWORD'), safe='')}"
        "@db:5432/explicit_db"
    )

    monkeypatch.setenv("PRODUCT_DATABASE_URL", database_url)

    module = importlib.import_module("services.product_management_service.app.main")
    settings = module.Settings(_env_file=None)

    assert settings.database_url == database_url
