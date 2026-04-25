import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from services.common.database import make_sqlalchemy_url

from .models import Base, Category, Product, ProductImage, StockMovement
from .schemas import (
    CategoryResponse,
    CreateCategoryRequest,
    CreateProductRequest,
    ProductImageResponse,
    ProductListResponse,
    ProductResponse,
    ProductStatus,
    ProductSummaryResponse,
    UpdateCategoryRequest,
    UpdateProductRequest,
    UpdateStockRequest,
)

DEFAULT_CATEGORY_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class ProductNotFound(Exception):
    pass


class CategoryNotFound(Exception):
    pass


class CategoryConflict(Exception):
    pass


class ProductConflict(Exception):
    pass


class StockCannotBeNegative(Exception):
    pass


class ProductRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(
            make_sqlalchemy_url(database_url),
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        self._schema_initialized = False
        self._schema_lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        if self._schema_initialized:
            return

        async with self._schema_lock:
            if self._schema_initialized:
                return

            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            await self._seed_default_categories()
            self._schema_initialized = True

    async def list_products(
        self,
        status: ProductStatus | None,
        page: int,
        limit: int,
    ) -> ProductListResponse:
        await self.ensure_schema()
        offset = (page - 1) * limit

        async with self.session_factory() as session:
            filters = []
            if status is not None:
                filters.append(Product.status == status)

            total = await session.scalar(
                select(func.count()).select_from(Product).where(*filters)
            )
            result = await session.scalars(
                select(Product)
                .where(*filters)
                .options(selectinload(Product.images))
                .order_by(Product.is_featured.desc(), Product.created_at.desc())
                .limit(limit)
                .offset(offset)
            )

            return ProductListResponse(
                items=[build_product_summary(product) for product in result.all()],
                page=page,
                limit=limit,
                total=total or 0,
            )

    async def get_product(self, product_id: UUID) -> ProductResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            product = await self._get_product_model(session, product_id)
            if product is None:
                raise ProductNotFound
            return build_product_response(product)

    async def list_categories(self) -> list[CategoryResponse]:
        await self.ensure_schema()

        async with self.session_factory() as session:
            result = await session.scalars(
                select(Category)
                .where(Category.is_active.is_(True))
                .order_by(Category.sort_order, Category.name)
            )

            return [build_category_response(category) for category in result.all()]

    async def get_category(self, category_id: UUID) -> CategoryResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            category = await session.get(Category, category_id)
            if category is None:
                raise CategoryNotFound

            return build_category_response(category)

    async def create_category(
        self,
        payload: CreateCategoryRequest,
    ) -> CategoryResponse:
        await self.ensure_schema()
        category_id = uuid4()

        async with self.session_factory() as session:
            try:
                async with session.begin():
                    session.add(
                        Category(
                            id=category_id,
                            name=payload.name,
                            slug=payload.slug,
                            sort_order=payload.sort_order,
                            is_active=payload.is_active,
                        )
                    )
            except IntegrityError as exc:
                await session.rollback()
                raise CategoryConflict from exc

        return await self.get_category(category_id)

    async def update_category(
        self,
        category_id: UUID,
        payload: UpdateCategoryRequest,
    ) -> CategoryResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            try:
                async with session.begin():
                    category = await self._get_category_model_for_update(
                        session,
                        category_id,
                    )
                    if category is None:
                        raise CategoryNotFound

                    if payload.name is not None:
                        category.name = payload.name
                    if payload.slug is not None:
                        category.slug = payload.slug
                    if payload.sort_order is not None:
                        category.sort_order = payload.sort_order
                    if payload.is_active is not None:
                        category.is_active = payload.is_active
                    category.updated_at = datetime.now(timezone.utc)
            except IntegrityError as exc:
                await session.rollback()
                raise CategoryConflict from exc

        return await self.get_category(category_id)

    async def delete_category(self, category_id: UUID) -> CategoryResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            async with session.begin():
                category = await self._get_category_model_for_update(
                    session,
                    category_id,
                )
                if category is None:
                    raise CategoryNotFound

                category.is_active = False
                category.updated_at = datetime.now(timezone.utc)

        return await self.get_category(category_id)

    async def create_product(self, payload: CreateProductRequest) -> ProductResponse:
        await self.ensure_schema()
        product_id = uuid4()

        async with self.session_factory() as session:
            try:
                async with session.begin():
                    await self._ensure_category_exists(session, payload.category_id)

                    product = Product(
                        id=product_id,
                        category_id=payload.category_id,
                        sku=payload.sku,
                        name=payload.name,
                        slug=payload.slug,
                        short_description=payload.short_description,
                        full_description=payload.full_description,
                        price=payload.price,
                        currency=payload.currency.upper(),
                        stock_qty=payload.stock_qty,
                        status=payload.status,
                        is_featured=payload.is_featured,
                    )
                    session.add(product)
                    if payload.stock_qty:
                        product.stock_movements.append(
                            StockMovement(
                                id=uuid4(),
                                delta_qty=payload.stock_qty,
                                reason="Initial stock",
                                source="product-management-service",
                            )
                        )
            except IntegrityError as exc:
                await session.rollback()
                raise ProductConflict from exc

        return await self.get_product(product_id)

    async def update_product(
        self,
        product_id: UUID,
        payload: UpdateProductRequest,
    ) -> ProductResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            try:
                async with session.begin():
                    product = await self._get_product_model_for_update(
                        session,
                        product_id,
                    )
                    if product is None:
                        raise ProductNotFound

                    if payload.category_id is not None:
                        await self._ensure_category_exists(session, payload.category_id)
                        product.category_id = payload.category_id
                    if payload.sku is not None:
                        product.sku = payload.sku
                    if payload.name is not None:
                        product.name = payload.name
                    if payload.slug is not None:
                        product.slug = payload.slug
                    if "short_description" in payload.model_fields_set:
                        product.short_description = payload.short_description
                    if "full_description" in payload.model_fields_set:
                        product.full_description = payload.full_description
                    if payload.price is not None:
                        product.price = payload.price
                    if payload.currency is not None:
                        product.currency = payload.currency.upper()
                    if payload.stock_qty is not None:
                        product.stock_qty = payload.stock_qty
                    if payload.status is not None:
                        product.status = payload.status
                    if payload.is_featured is not None:
                        product.is_featured = payload.is_featured
                    product.updated_at = datetime.now(timezone.utc)
            except IntegrityError as exc:
                await session.rollback()
                raise ProductConflict from exc

        return await self.get_product(product_id)

    async def update_stock(
        self,
        product_id: UUID,
        payload: UpdateStockRequest,
    ) -> ProductResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            async with session.begin():
                product = await self._get_product_model_for_update(session, product_id)
                if product is None:
                    raise ProductNotFound

                new_stock_qty = product.stock_qty + payload.delta_qty
                if new_stock_qty < 0:
                    raise StockCannotBeNegative

                product.stock_qty = new_stock_qty
                product.updated_at = datetime.now(timezone.utc)
                product.stock_movements.append(
                    StockMovement(
                        id=uuid4(),
                        delta_qty=payload.delta_qty,
                        reason=payload.reason,
                        source=payload.source,
                    )
                )

        return await self.get_product(product_id)

    async def update_status(
        self,
        product_id: UUID,
        status: ProductStatus,
    ) -> ProductResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            async with session.begin():
                product = await self._get_product_model_for_update(session, product_id)
                if product is None:
                    raise ProductNotFound

                product.status = status
                product.updated_at = datetime.now(timezone.utc)

        return await self.get_product(product_id)

    async def archive_product(self, product_id: UUID) -> ProductResponse:
        return await self.update_status(product_id, "archived")

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def _seed_default_categories(self) -> None:
        async with self.session_factory() as session:
            category = await session.get(Category, DEFAULT_CATEGORY_ID)
            if category is not None:
                return

            session.add(
                Category(
                    id=DEFAULT_CATEGORY_ID,
                    name="Лампы общего назначения",
                    slug="general-purpose-lamps",
                    sort_order=10,
                    is_active=True,
                )
            )
            await session.commit()

    async def _ensure_category_exists(
        self,
        session: AsyncSession,
        category_id: UUID,
    ) -> None:
        category = await session.get(Category, category_id)
        if category is None:
            raise CategoryNotFound

    async def _get_category_model_for_update(
        self,
        session: AsyncSession,
        category_id: UUID,
    ) -> Category | None:
        result = await session.scalars(
            select(Category).where(Category.id == category_id).with_for_update()
        )
        return result.first()

    async def _get_product_model(
        self,
        session: AsyncSession,
        product_id: UUID,
    ) -> Product | None:
        result = await session.scalars(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
            )
        )
        return result.first()

    async def _get_product_model_for_update(
        self,
        session: AsyncSession,
        product_id: UUID,
    ) -> Product | None:
        result = await session.scalars(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
                selectinload(Product.stock_movements),
            )
            .with_for_update()
        )
        return result.first()


def build_product_response(product: Product) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        category_id=product.category_id,
        sku=product.sku,
        name=product.name,
        slug=product.slug,
        short_description=product.short_description,
        full_description=product.full_description,
        price=product.price,
        currency=product.currency,
        stock_qty=product.stock_qty,
        status=product.status,
        is_featured=product.is_featured,
        created_at=product.created_at,
        updated_at=product.updated_at,
        category=build_category_response(product.category),
        images=[
            build_product_image_response(image)
            for image in sorted(product.images, key=lambda image: image.sort_order)
        ],
    )


def build_product_summary(product: Product) -> ProductSummaryResponse:
    return ProductSummaryResponse(
        id=product.id,
        category_id=product.category_id,
        sku=product.sku,
        name=product.name,
        slug=product.slug,
        short_description=product.short_description,
        price=product.price,
        currency=product.currency,
        stock_qty=product.stock_qty,
        status=product.status,
        is_featured=product.is_featured,
        created_at=product.created_at,
        updated_at=product.updated_at,
        main_image_url=main_image_url(product.images),
    )


def build_category_response(category: Category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        sort_order=category.sort_order,
        is_active=category.is_active,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def build_product_image_response(image: ProductImage) -> ProductImageResponse:
    return ProductImageResponse(
        id=image.id,
        image_url=image.image_url,
        alt_text=image.alt_text,
        sort_order=image.sort_order,
        is_main=image.is_main,
    )


def main_image_url(images: list[ProductImage]) -> str | None:
    if not images:
        return None

    sorted_images = sorted(
        images, key=lambda image: (not image.is_main, image.sort_order)
    )
    return sorted_images[0].image_url
