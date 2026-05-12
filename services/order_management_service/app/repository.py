import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from services.common.database import make_sqlalchemy_url

from .models import Base, Order, OrderItem, OrderStatusHistory
from .schemas import (
    CartCalculationResponse,
    CreateOrderRequest,
    OrderItemResponse,
    OrderListResponse,
    OrderResponse,
    OrderStatus,
    OrderStatusHistoryResponse,
    OrderStatusResponse,
    OrderSummaryResponse,
)


class OrderNotFound(Exception):
    pass


class OrderRepository:
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

            self._schema_initialized = True

    async def create_order(
        self,
        payload: CreateOrderRequest,
        calculation: CartCalculationResponse,
    ) -> OrderResponse:
        await self.ensure_schema()
        order_id = uuid4()
        order = Order(
            id=order_id,
            order_number=generate_order_number(),
            status="new",
            customer_name=payload.customer_name,
            company_name=payload.company_name,
            phone=payload.phone,
            email=payload.email,
            delivery_address=payload.delivery_address,
            comment=payload.comment,
            subtotal_amount=calculation.subtotal_amount,
            delivery_amount=calculation.delivery_amount,
            total_amount=calculation.total_amount,
            items=[
                OrderItem(
                    id=uuid4(),
                    product_id=item.product_id,
                    sku=item.sku or "",
                    product_name=item.product_name or "",
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in calculation.items
            ],
            status_history=[
                OrderStatusHistory(
                    id=uuid4(),
                    old_status=None,
                    new_status="new",
                    comment="Order created",
                    changed_by="order-management-service",
                )
            ],
        )

        async with self.session_factory() as session:
            session.add(order)
            await session.commit()

        return await self.get_order(order_id)

    async def get_order(self, order_id: UUID) -> OrderResponse:
        await self.ensure_schema()
        async with self.session_factory() as session:
            order = await self._get_order_model(session, order_id)
            if order is None:
                raise OrderNotFound
            return build_order_response(order)

    async def get_order_status(self, order_id: UUID) -> OrderStatusResponse:
        await self.ensure_schema()
        async with self.session_factory() as session:
            order = await session.get(Order, order_id)
            if order is None:
                raise OrderNotFound

            return OrderStatusResponse(
                id=order.id,
                order_number=order.order_number,
                status=order.status,
                updated_at=order.updated_at,
            )

    async def list_orders(
        self,
        status: OrderStatus | None,
        page: int,
        limit: int,
    ) -> OrderListResponse:
        await self.ensure_schema()
        offset = (page - 1) * limit

        async with self.session_factory() as session:
            filters = []
            if status is not None:
                filters.append(Order.status == status)

            total = await session.scalar(
                select(func.count()).select_from(Order).where(*filters)
            )
            result = await session.scalars(
                select(Order)
                .where(*filters)
                .order_by(Order.created_at.desc())
                .limit(limit)
                .offset(offset)
            )

            return OrderListResponse(
                items=[build_order_summary(order) for order in result.all()],
                page=page,
                limit=limit,
                total=total or 0,
            )

    async def update_order_status(
        self,
        order_id: UUID,
        new_status: OrderStatus,
        comment: str | None,
    ) -> OrderResponse:
        await self.ensure_schema()
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.scalars(
                    select(Order)
                    .where(Order.id == order_id)
                    .options(
                        selectinload(Order.items),
                        selectinload(Order.status_history),
                    )
                    .with_for_update()
                )
                order = result.first()
                if order is None:
                    raise OrderNotFound

                old_status = order.status
                if old_status != new_status:
                    order.status = new_status
                    order.updated_at = datetime.now(timezone.utc)
                    order.status_history.append(
                        OrderStatusHistory(
                            id=uuid4(),
                            old_status=old_status,
                            new_status=new_status,
                            comment=comment,
                            changed_by="api-gateway-service",
                        )
                    )

        return await self.get_order(order_id)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def _get_order_model(
        self,
        session: AsyncSession,
        order_id: UUID,
    ) -> Order | None:
        result = await session.scalars(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items),
                selectinload(Order.status_history),
            )
        )
        return result.first()


def build_order_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        customer_name=order.customer_name,
        company_name=order.company_name,
        phone=order.phone,
        email=order.email,
        delivery_address=order.delivery_address,
        comment=order.comment,
        subtotal_amount=order.subtotal_amount,
        delivery_amount=order.delivery_amount,
        total_amount=order.total_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                sku=item.sku,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
            for item in sorted(order.items, key=lambda item: item.id.hex)
        ],
        status_history=[
            OrderStatusHistoryResponse(
                id=history.id,
                old_status=history.old_status,
                new_status=history.new_status,
                comment=history.comment,
                changed_by=history.changed_by,
                changed_at=history.changed_at,
            )
            for history in sorted(
                order.status_history,
                key=lambda history: history.changed_at or datetime.min,
            )
        ],
    )


def build_order_summary(order: Order) -> OrderSummaryResponse:
    return OrderSummaryResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        customer_name=order.customer_name,
        company_name=order.company_name,
        phone=order.phone,
        email=order.email,
        total_amount=order.total_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def generate_order_number() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid4().hex[:8].upper()
    return f"ORD-{timestamp}-{suffix}"
