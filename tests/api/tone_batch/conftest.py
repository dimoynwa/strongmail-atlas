from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from api.refresh.redis_sync import reset_sync_redis
from shared.config import REDIS_URL, get_test_database_url
from shared.db import close_pool, init_pool
from shared.redis_client import init_redis
from shared.test_db import assert_test_database, ensure_test_database


@pytest_asyncio.fixture(scope="function")
async def db_pool():
    test_database_url = get_test_database_url()
    assert_test_database(test_database_url)
    await ensure_test_database(test_database_url)
    pool = await init_pool(test_database_url)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DROP TABLE IF EXISTS template_tone_evaluations CASCADE;
            DROP TABLE IF EXISTS template_details CASCADE;
            DROP TABLE IF EXISTS content_block_kv CASCADE;
            DROP TABLE IF EXISTS content_block_details CASCADE;
            DROP TABLE IF EXISTS content_block CASCADE;
            DROP TABLE IF EXISTS template_content_block CASCADE;
            DROP TABLE IF EXISTS template CASCADE;
            DROP TABLE IF EXISTS dynamic_content_details CASCADE;
            DROP TABLE IF EXISTS dynamic_content CASCADE;

            CREATE TABLE template (id text PRIMARY KEY, name text UNIQUE);
            CREATE TABLE template_details (
                template_id text,
                lang_local text,
                param_cust_brand text,
                subject text,
                summary text,
                html text,
                text text
            );
            CREATE TABLE template_tone_evaluations (
                template_id text,
                model_id text NOT NULL DEFAULT 'goemotions',
                lang_local text,
                param_cust_brand text,
                tones jsonb,
                evaluated_at timestamptz DEFAULT now(),
                PRIMARY KEY (template_id, model_id, lang_local, param_cust_brand)
            );
            CREATE TABLE template_content_block (
                template_id text,
                content_block_id text
            );
            CREATE TABLE content_block (id text PRIMARY KEY);
            CREATE TABLE content_block_details (
                id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                content_block_id text
            );
            CREATE TABLE content_block_kv (
                content_block_details_id bigint,
                field_key text,
                field_value text
            );
            CREATE TABLE dynamic_content (id text PRIMARY KEY, name text);
            CREATE TABLE dynamic_content_details (
                dynamic_content_id text,
                rule_ast json,
                rule_text text
            );
            """
        )
    yield pool
    await close_pool()


@pytest_asyncio.fixture(scope="function")
async def redis_client():
    os.environ["REDIS_URL"] = REDIS_URL
    reset_sync_redis()
    client = await init_redis(REDIS_URL)
    yield client
    await client.flushdb()
    await client.aclose()
    reset_sync_redis()


@pytest_asyncio.fixture(scope="function")
async def api_client(db_pool, redis_client):
    from concurrent.futures import ThreadPoolExecutor

    import api.state as state

    state.db_pool = db_pool
    state.redis_client = redis_client
    state.refresh_executor = ThreadPoolExecutor(max_workers=2)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    state.refresh_executor.shutdown(wait=False)
