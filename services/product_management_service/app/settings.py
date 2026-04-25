from pydantic_settings import SettingsConfigDict

from services.common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "product-management-service"
    database_host: str = "localhost"
    database_port: int = 5433
    database_name: str = "product_db"
    database_user: str = "product_user"
    database_password: str = ""

    model_config = SettingsConfigDict(
        env_prefix="PRODUCT_",
        env_file=".env",
        extra="ignore",
    )
