from decimal import Decimal

from services.product_management_service.app.exceptions import InvalidProductListParams


def normalize_product_list_filters(
    search_query: str | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
) -> tuple[str | None, Decimal | None, Decimal | None]:
    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        raise InvalidProductListParams(
            "minPrice must be less than or equal to maxPrice",
        )
    normalized_query = (
        search_query.strip() if search_query and search_query.strip() else None
    )
    return normalized_query, min_price, max_price
