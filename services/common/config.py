from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    service_name: str
    database_url: str = ""
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str
    database_user: str
    database_password: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def build_database_url(self) -> "BaseServiceSettings":
        if self.database_url:
            return self

        if not self.database_password:
            raise ValueError(
                "database_password is required when database_url is not set"
            )

        database_user = quote(self.database_user, safe="")
        database_password = quote(self.database_password, safe="")
        database_name = quote(self.database_name, safe="")

        self.database_url = (
            f"postgresql://{database_user}:{database_password}"
            f"@{self.database_host}:{self.database_port}/{database_name}"
        )
        return self
