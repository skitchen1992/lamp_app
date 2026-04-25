from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import SQLAlchemyError

from services.common.database import check_database
from services.common.logging import setup_logging
from services.common.schemas import HealthResponse
from services.order_management_service.app.product_client import (
    ProductClient,
    ProductServiceUnavailable,
)
from services.order_management_service.app.repository import (
    OrderNotFound,
    OrderRepository,
)
from services.order_management_service.app.schemas import (
    CartCalculationRequest,
    CartCalculationResponse,
    CreateOrderRequest,
    OrderListResponse,
    OrderResponse,
    OrderStatus,
    OrderStatusResponse,
    UpdateOrderStatusRequest,
)
from services.order_management_service.app.service import calculate_cart
from services.order_management_service.app.settings import Settings

APP_VERSION = "0.1.0"
DATABASE_EXCEPTIONS = (SQLAlchemyError, OSError, TimeoutError)

settings = Settings()
app = FastAPI(title=settings.service_name, version=APP_VERSION)
setup_logging(app, settings.service_name)
product_client = ProductClient(settings.product_service_url)
order_repository = OrderRepository(settings.database_url)


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


@app.post("/api/v1/cart/calculate", response_model=CartCalculationResponse)
async def calculate_cart_endpoint(
    payload: CartCalculationRequest,
) -> CartCalculationResponse:
    try:
        return await calculate_cart(payload, product_client)
    except ProductServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Product service is unavailable",
        ) from exc


@app.post(
    "/api/v1/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(payload: CreateOrderRequest) -> OrderResponse:
    try:
        calculation = await calculate_cart(
            CartCalculationRequest(
                items=payload.items,
                delivery_type=payload.delivery_type,
            ),
            product_client,
        )
    except ProductServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Product service is unavailable",
        ) from exc

    if not calculation.valid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Cart is not valid",
                "calculation": jsonable_encoder(
                    calculation,
                    by_alias=True,
                ),
            },
        )

    try:
        return await order_repository.create_order(payload, calculation)
    except DATABASE_EXCEPTIONS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: UUID) -> OrderResponse:
    try:
        return await order_repository.get_order(order_id)
    except OrderNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc


@app.get("/api/v1/orders/{order_id}/status", response_model=OrderStatusResponse)
async def get_order_status(order_id: UUID) -> OrderStatusResponse:
    try:
        return await order_repository.get_order_status(order_id)
    except OrderNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc


@app.get("/api/v1/internal/orders", response_model=OrderListResponse)
async def list_orders(
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> OrderListResponse:
    try:
        return await order_repository.list_orders(status_filter, page, limit)
    except DATABASE_EXCEPTIONS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc


@app.patch("/api/v1/internal/orders/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: UUID,
    payload: UpdateOrderStatusRequest,
) -> OrderResponse:
    try:
        return await order_repository.update_order_status(
            order_id,
            payload.status,
            payload.comment,
        )
    except OrderNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
