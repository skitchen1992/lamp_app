from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def check_database(database_url: str) -> None:
    engine = create_async_engine(make_sqlalchemy_url(database_url), pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


def make_sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url
