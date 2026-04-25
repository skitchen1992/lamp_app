import asyncio
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from .product_client import (
    ProductClient,
    ProductNotFound,
    ProductServiceUnavailable,
    ProductSnapshot,
)
from .schemas import (
    CartCalculationItem,
    CartCalculationRequest,
    CartCalculationResponse,
    DeliveryType,
)

MONEY_QUANT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


async def calculate_cart(
    payload: CartCalculationRequest,
    product_client: ProductClient,
) -> CartCalculationResponse:
    requested_quantities = _requested_quantities(payload)
    products = await _fetch_products(list(requested_quantities), product_client)

    response_items: list[CartCalculationItem] = []
    errors: list[str] = []
    subtotal_amount = Decimal("0.00")
    currency = "RUB"

    for item in payload.items:
        product = products.get(item.product_id)
        item_errors: list[str] = []

        if product is None:
            item_errors.append("Товар не найден")
        else:
            currency = product.currency
            if product.status != "active":
                item_errors.append("Товар недоступен для заказа")
            if product.stock_qty < requested_quantities[item.product_id]:
                item_errors.append(
                    f"Недостаточно товара на складе: доступно {product.stock_qty}"
                )

        if product is None or item_errors:
            error = "; ".join(item_errors)
            errors.append(f"{item.product_id}: {error}")
            response_items.append(
                CartCalculationItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    available=False,
                    error=error,
                )
            )
            continue

        line_total = money(product.price * item.quantity)
        subtotal_amount += line_total
        response_items.append(
            CartCalculationItem(
                product_id=item.product_id,
                quantity=item.quantity,
                sku=product.sku,
                product_name=product.name,
                unit_price=money(product.price),
                line_total=line_total,
                available=True,
            )
        )

    subtotal_amount = money(subtotal_amount)
    delivery_amount = calculate_delivery_amount(payload.delivery_type, subtotal_amount)
    total_amount = money(subtotal_amount + delivery_amount)

    return CartCalculationResponse(
        valid=not errors,
        items=response_items,
        subtotal_amount=subtotal_amount,
        delivery_amount=delivery_amount,
        total_amount=total_amount,
        currency=currency,
        errors=errors,
    )


def calculate_delivery_amount(
    delivery_type: DeliveryType,
    subtotal_amount: Decimal,
) -> Decimal:
    return Decimal("0.00")


def _requested_quantities(payload: CartCalculationRequest) -> dict[UUID, int]:
    requested_quantities: dict[UUID, int] = defaultdict(int)
    for item in payload.items:
        requested_quantities[item.product_id] += item.quantity
    return dict(requested_quantities)


async def _fetch_products(
    product_ids: list[UUID],
    product_client: ProductClient,
) -> dict[UUID, ProductSnapshot]:
    async def fetch(product_id: UUID) -> tuple[UUID, ProductSnapshot | None]:
        try:
            return product_id, await product_client.get_product(product_id)
        except ProductNotFound:
            return product_id, None

    results = await asyncio.gather(
        *(fetch(product_id) for product_id in product_ids),
        return_exceptions=True,
    )

    products: dict[UUID, ProductSnapshot] = {}
    for result in results:
        if isinstance(result, ProductServiceUnavailable):
            raise result
        if isinstance(result, Exception):
            raise ProductServiceUnavailable(
                "Product service is unavailable"
            ) from result

        product_id, product = result
        if product is not None:
            products[product_id] = product

    return products
