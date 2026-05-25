import pytest
import pytest_asyncio
from shared.config import REDIS_URL, get_test_database_url
from shared.db import init_pool, close_pool
from shared.redis_client import init_redis
from shared.test_db import assert_test_database, ensure_test_database

@pytest_asyncio.fixture(scope="function")
async def db_pool():
    test_database_url = get_test_database_url()
    assert_test_database(test_database_url)
    await ensure_test_database(test_database_url)
    pool = await init_pool(test_database_url)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS template (id text PRIMARY KEY, name text);
            CREATE TABLE IF NOT EXISTS template_content_block (template_id text, content_block_id text);
            CREATE TABLE IF NOT EXISTS content_block (id text PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS content_block_details (id bigint PRIMARY KEY, content_block_id text);
            CREATE TABLE IF NOT EXISTS content_block_kv (content_block_details_id bigint, field_key text, field_value text);
            CREATE TABLE IF NOT EXISTS dynamic_content (id text PRIMARY KEY, name text);
            CREATE TABLE IF NOT EXISTS dynamic_content_details (dynamic_content_id text, rule_ast json, rule_text text);
        """)
    yield pool
    await close_pool()

@pytest_asyncio.fixture(scope="function")
async def redis_client():
    client = await init_redis(REDIS_URL)
    yield client
    await client.aclose()
