import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID


class ProductClientError(Exception):
    """Base error for product service integration failures."""


class ProductNotFound(ProductClientError):
    pass


class ProductServiceUnavailable(ProductClientError):
    pass


@dataclass(frozen=True)
class ProductSnapshot:
    id: UUID
    sku: str
    name: str
    price: Decimal
    currency: str
    stock_qty: int
    status: str


class ProductClient:
    def __init__(self, base_url: str, timeout: float = 3.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_product(self, product_id: UUID) -> ProductSnapshot:
        return await asyncio.to_thread(self._get_product_sync, product_id)

    def _get_product_sync(self, product_id: UUID) -> ProductSnapshot:
        url = f"{self.base_url}/api/v1/products/{product_id}"
        request = Request(url, headers={"Accept": "application/json"})

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                raise ProductNotFound(f"Product {product_id} was not found") from exc
            raise ProductServiceUnavailable(
                f"Product service returned HTTP {exc.code}"
            ) from exc
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise ProductServiceUnavailable("Product service is unavailable") from exc

        return self._parse_product(product_id, payload)

    def _parse_product(
        self, requested_product_id: UUID, payload: dict
    ) -> ProductSnapshot:
        try:
            product_id = UUID(str(payload.get("id", requested_product_id)))
            price = Decimal(str(payload["price"]))
            stock_qty = int(self._field(payload, "stockQty", "stock_qty"))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ProductServiceUnavailable(
                "Product service returned an invalid product payload"
            ) from exc

        return ProductSnapshot(
            id=product_id,
            sku=str(payload.get("sku") or ""),
            name=str(payload.get("name") or ""),
            price=price,
            currency=str(payload.get("currency") or "RUB"),
            stock_qty=stock_qty,
            status=str(payload.get("status") or "active"),
        )

    @staticmethod
    def _field(payload: dict, camel_key: str, snake_key: str) -> object:
        if camel_key in payload:
            return payload[camel_key]
        return payload[snake_key]
