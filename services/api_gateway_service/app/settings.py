from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "api-gateway-service"
    auth_service_url: str = "http://localhost:8003"
    product_service_url: str = "http://localhost:8001"
    order_service_url: str = "http://localhost:8002"
    upstream_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_file=".env",
        extra="ignore",
    )
