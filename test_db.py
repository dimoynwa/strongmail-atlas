import asyncio
import asyncpg
from shared.config import DATABASE_URL

async def main():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("Success!")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())