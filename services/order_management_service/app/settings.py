from pydantic_settings import SettingsConfigDict

from services.common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "order-management-service"
    database_host: str = "localhost"
    database_port: int = 5434
    database_name: str = "order_db"
    database_user: str = "order_user"
    database_password: str = ""
    product_service_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_prefix="ORDER_",
        env_file=".env",
        extra="ignore",
    )
