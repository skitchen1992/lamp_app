from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OrderStatus = Literal[
    "new", "confirmed", "processing", "shipped", "completed", "canceled"
]
DeliveryType = Literal["pickup", "delivery"]


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class CartItemRequest(CamelModel):
    product_id: UUID
    quantity: int = Field(gt=0)


class CartCalculationRequest(CamelModel):
    items: list[CartItemRequest] = Field(min_length=1)
    delivery_type: DeliveryType = "pickup"


class CartCalculationItem(CamelModel):
    product_id: UUID
    quantity: int
    sku: str | None = None
    product_name: str | None = None
    unit_price: Decimal | None = None
    line_total: Decimal = Decimal("0.00")
    available: bool
    error: str | None = None


class CartCalculationResponse(CamelModel):
    valid: bool
    items: list[CartCalculationItem]
    subtotal_amount: Decimal
    delivery_amount: Decimal
    total_amount: Decimal
    currency: str = "RUB"
    errors: list[str] = Field(default_factory=list)


class CreateOrderRequest(CamelModel):
    customer_name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    phone: str = Field(min_length=1, max_length=32)
    email: str = Field(min_length=3, max_length=255)
    delivery_address: str | None = Field(default=None, max_length=500)
    comment: str | None = None
    delivery_type: DeliveryType = "delivery"
    items: list[CartItemRequest] = Field(min_length=1)


class OrderItemResponse(CamelModel):
    id: UUID
    product_id: UUID
    sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderStatusHistoryResponse(CamelModel):
    id: UUID
    old_status: OrderStatus | None = None
    new_status: OrderStatus
    comment: str | None = None
    changed_by: str
    changed_at: datetime


class OrderResponse(CamelModel):
    id: UUID
    order_number: str
    status: OrderStatus
    customer_name: str
    company_name: str | None = None
    phone: str
    email: str
    delivery_address: str | None = None
    comment: str | None = None
    subtotal_amount: Decimal
    delivery_amount: Decimal
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
    status_history: list[OrderStatusHistoryResponse]


class OrderSummaryResponse(CamelModel):
    id: UUID
    order_number: str
    status: OrderStatus
    customer_name: str
    company_name: str | None = None
    phone: str
    email: str
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime


class OrderListResponse(CamelModel):
    items: list[OrderSummaryResponse]
    page: int
    limit: int
    total: int


class OrderStatusResponse(CamelModel):
    id: UUID
    order_number: str
    status: OrderStatus
    updated_at: datetime


class UpdateOrderStatusRequest(CamelModel):
    status: OrderStatus
    comment: str | None = Field(default=None, max_length=500)
