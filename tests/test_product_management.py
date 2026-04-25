import importlib
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from services.product_management_service.app.repository import StockCannotBeNegative
from services.product_management_service.app.schemas import (
    CategoryResponse,
    ProductListResponse,
    ProductResponse,
    ProductSummaryResponse,
)

CATEGORY_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PRODUCT_ID = UUID("11111111-1111-1111-1111-111111111111")
NOW = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)


class FakeProductRepository:
    def __init__(self) -> None:
        self.list_status = None
        self.created_payload = None
        self.created_category_payload = None
        self.updated_category_payload = None
        self.deleted_category_id = None

    async def list_products(self, status, page: int, limit: int) -> ProductListResponse:
        self.list_status = status
        return ProductListResponse(
            items=[
                ProductSummaryResponse(
                    id=PRODUCT_ID,
                    category_id=CATEGORY_ID,
                    sku="LMP-021",
                    name="LED A60 12W E27 4000K",
                    slug="led-a60-12w-e27-4000k",
                    short_description="Энергоэффективная LED-лампа.",
                    price=Decimal("189.00"),
                    currency="RUB",
                    stock_qty=250,
                    status="active",
                    is_featured=False,
                    created_at=NOW,
                    updated_at=NOW,
                )
            ],
            page=page,
            limit=limit,
            total=1,
        )

    async def get_product(self, product_id: UUID) -> ProductResponse:
        return make_product_response(product_id=product_id)

    async def list_categories(self) -> list[CategoryResponse]:
        return [make_category_response()]

    async def create_category(self, payload) -> CategoryResponse:
        self.created_category_payload = payload
        return make_category_response(
            name=payload.name,
            slug=payload.slug,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )

    async def update_category(
        self,
        category_id: UUID,
        payload,
    ) -> CategoryResponse:
        self.updated_category_payload = payload
        return make_category_response(
            category_id=category_id,
            name=payload.name or "Лампы общего назначения",
            slug=payload.slug or "general-purpose-lamps",
            sort_order=payload.sort_order if payload.sort_order is not None else 10,
            is_active=payload.is_active if payload.is_active is not None else True,
        )

    async def delete_category(self, category_id: UUID) -> CategoryResponse:
        self.deleted_category_id = category_id
        return make_category_response(category_id=category_id, is_active=False)

    async def create_product(self, payload) -> ProductResponse:
        self.created_payload = payload
        return make_product_response(
            sku=payload.sku,
            name=payload.name,
            slug=payload.slug,
            price=payload.price,
            stock_qty=payload.stock_qty,
            status=payload.status,
        )

    async def update_product(self, product_id: UUID, payload) -> ProductResponse:
        return make_product_response(product_id=product_id, name=payload.name)

    async def update_stock(self, product_id: UUID, payload) -> ProductResponse:
        if payload.delta_qty < 0:
            raise StockCannotBeNegative
        return make_product_response(product_id=product_id, stock_qty=300)

    async def update_status(self, product_id: UUID, status: str) -> ProductResponse:
        return make_product_response(product_id=product_id, status=status)

    async def archive_product(self, product_id: UUID) -> ProductResponse:
        return make_product_response(product_id=product_id, status="archived")


def test_get_product_returns_order_service_fields(monkeypatch) -> None:
    module, repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).get(f"/api/v1/products/{PRODUCT_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(PRODUCT_ID)
    assert payload["sku"] == "LMP-021"
    assert payload["price"] == "189.00"
    assert payload["stockQty"] == 250
    assert payload["status"] == "active"
    assert "stock_qty" not in payload
    assert repository.created_payload is None


def test_list_products_uses_active_status_by_default(monkeypatch) -> None:
    module, repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).get("/api/v1/products")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert repository.list_status == "active"


def test_create_product_accepts_postman_payload(monkeypatch) -> None:
    module, repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).post(
        "/api/v1/internal/products",
        json={
            "categoryId": str(CATEGORY_ID),
            "sku": "LMP-021",
            "name": "LED A60 12W E27 4000K",
            "slug": "led-a60-12w-e27-4000k",
            "shortDescription": "Энергоэффективная LED-лампа общего назначения.",
            "fullDescription": "Подходит для бытового и коммерческого использования.",
            "price": 189.0,
            "currency": "RUB",
            "stockQty": 250,
            "status": "draft",
        },
    )

    assert response.status_code == 201
    assert response.json()["categoryId"] == str(CATEGORY_ID)
    assert repository.created_payload.category_id == CATEGORY_ID
    assert repository.created_payload.stock_qty == 250


def test_create_category_accepts_payload(monkeypatch) -> None:
    module, repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).post(
        "/api/v1/internal/categories",
        json={
            "name": "LED лампы",
            "slug": "led-lamps",
            "sortOrder": 20,
            "isActive": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "LED лампы"
    assert payload["slug"] == "led-lamps"
    assert payload["sortOrder"] == 20
    assert repository.created_category_payload.slug == "led-lamps"


def test_update_category_accepts_payload(monkeypatch) -> None:
    module, repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).put(
        f"/api/v1/internal/categories/{CATEGORY_ID}",
        json={
            "name": "Декоративные лампы",
            "slug": "decorative-lamps",
            "sortOrder": 30,
            "isActive": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(CATEGORY_ID)
    assert payload["name"] == "Декоративные лампы"
    assert payload["isActive"] is False
    assert repository.updated_category_payload.sort_order == 30


def test_delete_category_deactivates_category(monkeypatch) -> None:
    module, repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).delete(
        f"/api/v1/internal/categories/{CATEGORY_ID}",
    )

    assert response.status_code == 200
    assert response.json()["isActive"] is False
    assert repository.deleted_category_id == CATEGORY_ID


def test_update_stock_rejects_negative_result(monkeypatch) -> None:
    module, _repository = product_module_with_fake_repository(monkeypatch)

    response = TestClient(module.app).patch(
        f"/api/v1/internal/products/{PRODUCT_ID}/stock",
        json={"deltaQty": -1, "reason": "Корректировка"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Product stock cannot be negative"


def product_module_with_fake_repository(monkeypatch):
    monkeypatch.setenv("PRODUCT_DATABASE_PASSWORD", "product_password")
    module = importlib.import_module("services.product_management_service.app.main")
    repository = FakeProductRepository()
    monkeypatch.setattr(module, "product_repository", repository)
    return module, repository


def make_category_response(
    category_id: UUID = CATEGORY_ID,
    name: str = "Лампы общего назначения",
    slug: str = "general-purpose-lamps",
    sort_order: int = 10,
    is_active: bool = True,
) -> CategoryResponse:
    return CategoryResponse(
        id=category_id,
        name=name,
        slug=slug,
        sort_order=sort_order,
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def make_product_response(
    product_id: UUID = PRODUCT_ID,
    sku: str = "LMP-021",
    name: str | None = "LED A60 12W E27 4000K",
    slug: str = "led-a60-12w-e27-4000k",
    price: Decimal = Decimal("189.00"),
    stock_qty: int = 250,
    status: str = "active",
) -> ProductResponse:
    return ProductResponse(
        id=product_id,
        category_id=CATEGORY_ID,
        sku=sku,
        name=name or "LED A60 12W E27 4000K",
        slug=slug,
        short_description="Энергоэффективная LED-лампа.",
        full_description="Подходит для бытового и коммерческого использования.",
        price=price,
        currency="RUB",
        stock_qty=stock_qty,
        status=status,
        is_featured=False,
        created_at=NOW,
        updated_at=NOW,
        category=make_category_response(),
    )
