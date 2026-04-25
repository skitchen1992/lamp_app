import asyncio
from decimal import Decimal
from uuid import UUID

import pytest

from services.order_management_service.app.product_client import (
    ProductServiceUnavailable,
    ProductSnapshot,
)
from services.order_management_service.app.schemas import CartCalculationRequest
from services.order_management_service.app.service import calculate_cart


PRODUCT_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_PRODUCT_ID = UUID("44444444-4444-4444-4444-444444444444")


class FakeProductClient:
    def __init__(self, products: dict[UUID, ProductSnapshot]) -> None:
        self.products = products

    async def get_product(self, product_id: UUID) -> ProductSnapshot:
        if product_id not in self.products:
            raise ProductServiceUnavailable
        return self.products[product_id]


def test_calculate_cart_uses_current_product_data() -> None:
    payload = CartCalculationRequest(
        items=[
            {"productId": str(PRODUCT_ID), "quantity": 3},
            {"productId": str(SECOND_PRODUCT_ID), "quantity": 2},
        ],
        deliveryType="pickup",
    )
    product_client = FakeProductClient(
        {
            PRODUCT_ID: ProductSnapshot(
                id=PRODUCT_ID,
                sku="LMP-001",
                name="LED A60 7W E27 3000K",
                price=Decimal("120.50"),
                currency="RUB",
                stock_qty=10,
                status="active",
            ),
            SECOND_PRODUCT_ID: ProductSnapshot(
                id=SECOND_PRODUCT_ID,
                sku="LMP-004",
                name="LED C37 5W E14 3000K",
                price=Decimal("80.00"),
                currency="RUB",
                stock_qty=10,
                status="active",
            ),
        }
    )

    result = asyncio.run(calculate_cart(payload, product_client))

    assert result.valid is True
    assert result.subtotal_amount == Decimal("521.50")
    assert result.total_amount == Decimal("521.50")
    assert result.items[0].sku == "LMP-001"
    assert result.items[0].line_total == Decimal("361.50")


def test_calculate_cart_rejects_inactive_and_insufficient_stock() -> None:
    payload = CartCalculationRequest(
        items=[
            {"productId": str(PRODUCT_ID), "quantity": 3},
            {"productId": str(SECOND_PRODUCT_ID), "quantity": 2},
        ]
    )
    product_client = FakeProductClient(
        {
            PRODUCT_ID: ProductSnapshot(
                id=PRODUCT_ID,
                sku="LMP-001",
                name="LED A60 7W E27 3000K",
                price=Decimal("120.50"),
                currency="RUB",
                stock_qty=1,
                status="active",
            ),
            SECOND_PRODUCT_ID: ProductSnapshot(
                id=SECOND_PRODUCT_ID,
                sku="LMP-004",
                name="LED C37 5W E14 3000K",
                price=Decimal("80.00"),
                currency="RUB",
                stock_qty=10,
                status="archived",
            ),
        }
    )

    result = asyncio.run(calculate_cart(payload, product_client))

    assert result.valid is False
    assert result.subtotal_amount == Decimal("0.00")
    assert len(result.errors) == 2
    assert "Недостаточно товара" in result.items[0].error
    assert "недоступен" in result.items[1].error


def test_calculate_cart_raises_when_product_service_is_unavailable() -> None:
    payload = CartCalculationRequest(
        items=[{"productId": str(PRODUCT_ID), "quantity": 1}]
    )

    with pytest.raises(ProductServiceUnavailable):
        asyncio.run(calculate_cart(payload, FakeProductClient({})))
