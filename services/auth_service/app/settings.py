from pydantic_settings import SettingsConfigDict

from services.common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "auth-service"
    database_host: str = "localhost"
    database_port: int = 5435
    database_name: str = "auth_db"
    database_user: str = "auth_user"
    database_password: str = ""
    access_token_secret: str = "change-me-auth-access-token-secret"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        extra="ignore",
    )
