from decimal import Decimal

from services.product_management_service.app.product_list_filters import (
    normalize_product_list_filters,
)
from services.product_management_service.app.repository import ProductRepository
from services.product_management_service.app.schemas import (
    ProductListResponse,
    ProductStatus,
)


class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def list_products(
        self,
        status: ProductStatus | None,
        page: int,
        limit: int,
        *,
        search_query: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
    ) -> ProductListResponse:
        normalized_query, min_p, max_p = normalize_product_list_filters(
            search_query,
            min_price,
            max_price,
        )
        return await self._repository.list_products(
            status,
            page,
            limit,
            search_query=normalized_query,
            min_price=min_p,
            max_price=max_p,
        )
