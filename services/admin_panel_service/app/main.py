from fastapi import FastAPI, HTTPException, status
from pydantic_settings import SettingsConfigDict

from services.common.config import BaseServiceSettings
from services.common.database import check_database
from services.common.logging import setup_logging
from services.common.schemas import HealthResponse

APP_VERSION = "0.1.0"


class Settings(BaseServiceSettings):
    service_name: str = "admin-panel-service"
    database_host: str = "localhost"
    database_port: int = 5435
    database_name: str = "admin_db"
    database_user: str = "admin_user"
    database_password: str = ""

    model_config = SettingsConfigDict(
        env_prefix="ADMIN_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
app = FastAPI(title=settings.service_name, version=APP_VERSION)
setup_logging(app, settings.service_name)


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
