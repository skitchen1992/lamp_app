import asyncpg


async def check_database(database_url: str) -> None:
    connection = await asyncpg.connect(database_url, timeout=3)
    try:
        await connection.execute("SELECT 1")
    finally:
        await connection.close()
