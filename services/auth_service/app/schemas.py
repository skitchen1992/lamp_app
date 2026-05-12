from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class RegisterRequest(CamelModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)


class LoginRequest(CamelModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(CamelModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(CamelModel):
    refresh_token: str = Field(min_length=1)


class UserResponse(CamelModel):
    id: UUID
    email: str
    full_name: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class AuthResponse(TokenResponse):
    user: UserResponse


class LogoutResponse(CamelModel):
    message: str = "Logged out"
