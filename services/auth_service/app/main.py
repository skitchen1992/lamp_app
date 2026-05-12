from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from services.auth_service.app.repository import AuthRepository
from services.auth_service.app.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from services.auth_service.app.service import (
    AuthService,
    ExpiredAccessToken,
    InvalidAccessToken,
    InvalidCredentials,
    InvalidRefreshToken,
    UserConflict,
)
from services.auth_service.app.settings import Settings
from services.common.database import check_database
from services.common.logging import setup_logging
from services.common.schemas import HealthResponse

APP_VERSION = "0.1.0"
DATABASE_EXCEPTIONS = (SQLAlchemyError, OSError, TimeoutError)

settings = Settings()
app = FastAPI(title=settings.service_name, version=APP_VERSION)
setup_logging(app, settings.service_name)
auth_repository = AuthRepository(settings.database_url)
auth_service = AuthService(auth_repository, settings)


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


@app.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest) -> AuthResponse:
    try:
        return await auth_service.register(payload)
    except UserConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        ) from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    try:
        return await auth_service.login(payload)
    except InvalidCredentials as exc:
        raise unauthorized("Invalid email or password") from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest) -> TokenResponse:
    try:
        return await auth_service.refresh(payload)
    except InvalidRefreshToken as exc:
        raise unauthorized("Refresh token is invalid or expired") from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


@app.post("/logout", response_model=LogoutResponse)
async def logout(payload: LogoutRequest) -> LogoutResponse:
    try:
        await auth_service.logout(payload.refresh_token)
    except InvalidRefreshToken as exc:
        raise unauthorized("Refresh token is invalid or expired") from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc

    return LogoutResponse()


def extract_bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized("Bearer token is required")
    return token


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.get("/me", response_model=UserResponse)
async def me(
    access_token: Annotated[str, Depends(extract_bearer_token)],
) -> UserResponse:
    try:
        return await auth_service.me(access_token)
    except ExpiredAccessToken as exc:
        raise unauthorized("Access token is expired") from exc
    except InvalidAccessToken as exc:
        raise unauthorized("Access token is invalid") from exc
    except DATABASE_EXCEPTIONS as exc:
        raise database_unavailable() from exc


def database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable",
    )
