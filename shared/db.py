import asyncpg
from asyncpg import Pool

_pool: Pool | None = None

async def init_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> Pool:
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    return _pool

def get_pool() -> Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized — call init_pool() first")
    return _pool

async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
