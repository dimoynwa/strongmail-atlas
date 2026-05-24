import redis.asyncio as aioredis
from redis.asyncio import Redis

_client: Redis | None = None

async def init_redis(url: str) -> Redis:
    global _client
    _client = await aioredis.from_url(url, decode_responses=True)
    return _client

def get_redis() -> Redis:
    if _client is None:
        raise RuntimeError("Redis client not initialized")
    return _client
