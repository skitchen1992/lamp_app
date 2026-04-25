from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProductStatus = Literal["draft", "active", "archived"]


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class CategoryResponse(CamelModel):
    id: UUID
    name: str
    slug: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateCategoryRequest(CamelModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=150)
    sort_order: int = 0
    is_active: bool = True


class UpdateCategoryRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=150)
    sort_order: int | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UpdateCategoryRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class ProductImageResponse(CamelModel):
    id: UUID
    image_url: str
    alt_text: str | None = None
    sort_order: int
    is_main: bool


class ProductResponse(CamelModel):
    id: UUID
    category_id: UUID
    sku: str
    name: str
    slug: str
    short_description: str | None = None
    full_description: str | None = None
    price: Decimal
    currency: str
    stock_qty: int
    status: ProductStatus
    is_featured: bool
    created_at: datetime
    updated_at: datetime
    category: CategoryResponse | None = None
    images: list[ProductImageResponse] = Field(default_factory=list)


class ProductSummaryResponse(CamelModel):
    id: UUID
    category_id: UUID
    sku: str
    name: str
    slug: str
    short_description: str | None = None
    price: Decimal
    currency: str
    stock_qty: int
    status: ProductStatus
    is_featured: bool
    created_at: datetime
    updated_at: datetime
    main_image_url: str | None = None


class ProductListResponse(CamelModel):
    items: list[ProductSummaryResponse]
    page: int
    limit: int
    total: int


class CreateProductRequest(CamelModel):
    category_id: UUID
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    short_description: str | None = Field(default=None, max_length=500)
    full_description: str | None = None
    price: Decimal = Field(ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    stock_qty: int = Field(default=0, ge=0)
    status: ProductStatus = "draft"
    is_featured: bool = False


class UpdateProductRequest(CamelModel):
    category_id: UUID | None = None
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    short_description: str | None = Field(default=None, max_length=500)
    full_description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stock_qty: int | None = Field(default=None, ge=0)
    status: ProductStatus | None = None
    is_featured: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UpdateProductRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class UpdateStockRequest(CamelModel):
    delta_qty: int
    reason: str = Field(min_length=1, max_length=255)
    source: str = Field(default="product-management-service", max_length=50)

    @field_validator("delta_qty")
    @classmethod
    def delta_qty_cannot_be_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("deltaQty must not be zero")
        return value


class UpdateProductStatusRequest(CamelModel):
    status: ProductStatus
