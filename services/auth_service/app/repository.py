import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.common.database import make_sqlalchemy_url

from .models import Base, RefreshSession, User
from .schemas import UserResponse


class UserConflict(Exception):
    pass


class UserNotFound(Exception):
    pass


class InvalidRefreshToken(Exception):
    pass


class AuthRepository:
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

    async def create_user(
        self,
        *,
        email: str,
        full_name: str | None,
        password_hash: str,
    ) -> UserResponse:
        await self.ensure_schema()
        user_id = uuid4()

        async with self.session_factory() as session:
            try:
                async with session.begin():
                    session.add(
                        User(
                            id=user_id,
                            email=email,
                            full_name=full_name,
                            password_hash=password_hash,
                            is_active=True,
                        )
                    )
            except IntegrityError as exc:
                await session.rollback()
                raise UserConflict from exc

        return await self.get_user(user_id)

    async def get_user(self, user_id: UUID) -> UserResponse:
        await self.ensure_schema()

        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise UserNotFound
            return build_user_response(user)

    async def get_user_credentials(self, email: str) -> tuple[UserResponse, str]:
        await self.ensure_schema()

        async with self.session_factory() as session:
            user = await self._get_user_by_email(session, email)
            if user is None:
                raise UserNotFound

            return build_user_response(user), user.password_hash

    async def create_refresh_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        await self.ensure_schema()

        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    RefreshSession(
                        id=uuid4(),
                        user_id=user_id,
                        token_hash=token_hash,
                        expires_at=expires_at,
                    )
                )

    async def rotate_refresh_session(
        self,
        *,
        current_token_hash: str,
        new_token_hash: str,
        new_expires_at: datetime,
    ) -> UserResponse:
        await self.ensure_schema()
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            async with session.begin():
                refresh_session = await self._get_refresh_session_for_update(
                    session,
                    current_token_hash,
                )
                if refresh_session is None or not refresh_session_is_valid(
                    refresh_session,
                    now,
                ):
                    raise InvalidRefreshToken

                user = await session.get(User, refresh_session.user_id)
                if user is None or not user.is_active:
                    raise InvalidRefreshToken

                refresh_session.revoked_at = now
                session.add(
                    RefreshSession(
                        id=uuid4(),
                        user_id=user.id,
                        token_hash=new_token_hash,
                        expires_at=new_expires_at,
                    )
                )
                return build_user_response(user)

    async def revoke_refresh_session(self, token_hash: str) -> None:
        await self.ensure_schema()
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            async with session.begin():
                refresh_session = await self._get_refresh_session_for_update(
                    session,
                    token_hash,
                )
                if refresh_session is None or not refresh_session_is_valid(
                    refresh_session,
                    now,
                ):
                    raise InvalidRefreshToken

                refresh_session.revoked_at = now

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def _get_user_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> User | None:
        result = await session.scalars(select(User).where(User.email == email))
        return result.first()

    async def _get_refresh_session_for_update(
        self,
        session: AsyncSession,
        token_hash: str,
    ) -> RefreshSession | None:
        result = await session.scalars(
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )
        return result.first()


def build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def refresh_session_is_valid(
    refresh_session: RefreshSession,
    now: datetime,
) -> bool:
    return refresh_session.revoked_at is None and refresh_session.expires_at > now
