from datetime import datetime, timedelta, timezone
from uuid import UUID

from .repository import (
    AuthRepository,
    InvalidRefreshToken,
    UserConflict,
    UserNotFound,
)
from .schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from .security import (
    ExpiredAccessToken,
    InvalidAccessToken,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    read_access_token,
    verify_password,
)
from .settings import Settings


class InvalidCredentials(Exception):
    pass


class AuthService:
    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def register(self, payload: RegisterRequest) -> AuthResponse:
        user = await self.repository.create_user(
            email=normalize_email(payload.email),
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )
        return await self._build_auth_response(user)

    async def login(self, payload: LoginRequest) -> AuthResponse:
        try:
            user, password_hash = await self.repository.get_user_credentials(
                normalize_email(payload.email)
            )
        except UserNotFound as exc:
            raise InvalidCredentials from exc

        if not user.is_active or not verify_password(payload.password, password_hash):
            raise InvalidCredentials

        return await self._build_auth_response(user)

    async def refresh(self, payload: RefreshRequest) -> TokenResponse:
        refresh_token = generate_refresh_token()
        refresh_expires_at = self._refresh_expires_at()
        user = await self.repository.rotate_refresh_session(
            current_token_hash=hash_token(payload.refresh_token),
            new_token_hash=hash_token(refresh_token),
            new_expires_at=refresh_expires_at,
        )
        access_token = self._create_access_token(user.id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_ttl_seconds,
        )

    async def logout(self, refresh_token: str) -> None:
        await self.repository.revoke_refresh_session(hash_token(refresh_token))

    async def me(self, access_token: str) -> UserResponse:
        user_id = self.read_access_token(access_token)
        try:
            user = await self.repository.get_user(user_id)
        except UserNotFound as exc:
            raise InvalidAccessToken from exc

        if not user.is_active:
            raise InvalidAccessToken
        return user

    def read_access_token(self, access_token: str) -> UUID:
        return read_access_token(access_token, self.settings.access_token_secret)

    async def _build_auth_response(self, user: UserResponse) -> AuthResponse:
        refresh_token = generate_refresh_token()
        await self.repository.create_refresh_session(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=self._refresh_expires_at(),
        )
        return AuthResponse(
            user=user,
            access_token=self._create_access_token(user.id),
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_ttl_seconds,
        )

    def _create_access_token(self, user_id: UUID) -> str:
        return create_access_token(
            user_id,
            self.settings.access_token_secret,
            self.settings.access_token_ttl_seconds,
        )

    def _refresh_expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.refresh_token_ttl_seconds
        )


def normalize_email(email: str) -> str:
    return email.strip().lower()


__all__ = (
    "AuthService",
    "ExpiredAccessToken",
    "InvalidAccessToken",
    "InvalidCredentials",
    "InvalidRefreshToken",
    "UserConflict",
)
