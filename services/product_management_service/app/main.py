from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError


from services.common.database import check_database
from services.common.logging import setup_logging
from services.common.schemas import HealthResponse
from services.product_management_service.app.repository import (
    CategoryConflict,
    CategoryNotFound,
    ProductConflict,
    ProductNotFound,
    ProductRepository,
    StockCannotBeNegative,
)
from services.product_management_service.app.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
    CreateProductRequest,
    ProductListResponse,
    ProductResponse,
    ProductStatus,
    UpdateCategoryRequest,
    UpdateProductRequest,
    UpdateProductStatusRequest,
    UpdateStockRequest,
)
from services.product_management_service.app.settings import Settings

APP_VERSION = "0.1.0"
DATABASE_EXCEPTIONS = (SQLAlchemyError, OSError, TimeoutError)

settings = Settings()
app = FastAPI(title=settings.service_name, version=APP_VERSION)
setup_logging(app, settings.service_name)
product_repository = ProductRepository(settings.database_url)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        await check_database(settings.database_url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return HealthResponse(
        service=settings.service_name,
        status="ok",
        database="ok",
        version=APP_VERSION,
    )


@app.get("/api/v1/products", response_model=ProductListResponse)
async def list_products(
    status_filter: ProductStatus | None = Query(default="active", alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> ProductListResponse:
    try:
        return await product_repository.list_products(status_filter, page, limit)
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.get("/api/v1/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: UUID) -> ProductResponse:
    try:
        return await product_repository.get_product(product_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.get("/api/v1/categories", response_model=list[CategoryResponse])
async def list_categories() -> list[CategoryResponse]:
    try:
        return await product_repository.list_categories()
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.post(
    "/api/v1/internal/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(payload: CreateCategoryRequest) -> CategoryResponse:
    try:
        return await product_repository.create_category(payload)
    except CategoryConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category slug already exists",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.put(
    "/api/v1/internal/categories/{category_id}",
    response_model=CategoryResponse,
)
async def update_category(
    category_id: UUID,
    payload: UpdateCategoryRequest,
) -> CategoryResponse:
    try:
        return await product_repository.update_category(category_id, payload)
    except CategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category was not found",
        ) from exc
    except CategoryConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category slug already exists",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.delete(
    "/api/v1/internal/categories/{category_id}",
    response_model=CategoryResponse,
)
async def delete_category(category_id: UUID) -> CategoryResponse:
    try:
        return await product_repository.delete_category(category_id)
    except CategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category was not found",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.post(
    "/api/v1/internal/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(payload: CreateProductRequest) -> ProductResponse:
    try:
        return await product_repository.create_product(payload)
    except CategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category was not found",
        ) from exc
    except ProductConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU or slug already exists",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.put("/api/v1/internal/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    payload: UpdateProductRequest,
) -> ProductResponse:
    try:
        return await product_repository.update_product(product_id, payload)
    except ProductNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except CategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category was not found",
        ) from exc
    except ProductConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU or slug already exists",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.patch(
    "/api/v1/internal/products/{product_id}/stock",
    response_model=ProductResponse,
)
async def update_stock(
    product_id: UUID,
    payload: UpdateStockRequest,
) -> ProductResponse:
    try:
        return await product_repository.update_stock(product_id, payload)
    except ProductNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except StockCannotBeNegative as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product stock cannot be negative",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.patch(
    "/api/v1/internal/products/{product_id}/status",
    response_model=ProductResponse,
)
async def update_status(
    product_id: UUID,
    payload: UpdateProductStatusRequest,
) -> ProductResponse:
    try:
        return await product_repository.update_status(product_id, payload.status)
    except ProductNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.delete("/api/v1/internal/products/{product_id}", response_model=ProductResponse)
async def archive_product(product_id: UUID) -> ProductResponse:
    try:
        return await product_repository.archive_product(product_id)
    except ProductNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


def database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable",
    )
