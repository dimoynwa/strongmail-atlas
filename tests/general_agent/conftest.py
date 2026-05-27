import json

import pytest
import pytest_asyncio

from general_agent.ml.embeddings import encode_query
from shared.config import get_test_database_url
from shared.db import close_pool, init_pool
from shared.test_db import assert_test_database, ensure_test_database


@pytest_asyncio.fixture
async def db_pool():
    test_database_url = get_test_database_url()
    assert_test_database(test_database_url)
    await ensure_test_database(test_database_url)
    pool = await init_pool(test_database_url)
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            """
            DROP TABLE IF EXISTS template_tone_evaluations CASCADE;
            DROP TABLE IF EXISTS body_placeholder_keys CASCADE;
            DROP TABLE IF EXISTS template_details CASCADE;
            DROP TABLE IF EXISTS content_block_kv CASCADE;
            DROP TABLE IF EXISTS content_block_details CASCADE;
            DROP TABLE IF EXISTS content_block CASCADE;
            DROP TABLE IF EXISTS template_content_block CASCADE;
            DROP TABLE IF EXISTS template CASCADE;
            DROP TABLE IF EXISTS dynamic_content_details CASCADE;
            DROP TABLE IF EXISTS dynamic_content CASCADE;

            CREATE TABLE template (
                id text PRIMARY KEY,
                name text UNIQUE NOT NULL
            );
            CREATE TABLE template_details (
                template_id text REFERENCES template(id),
                lang_local text,
                param_cust_brand text,
                subject text,
                summary text,
                html text,
                text text,
                summary_embeded vector(768)
            );
            CREATE TABLE template_content_block (
                template_id text,
                content_block_id text
            );
            CREATE TABLE content_block (id text PRIMARY KEY);
            CREATE TABLE content_block_details (
                id bigint PRIMARY KEY,
                content_block_id text
            );
            CREATE TABLE content_block_kv (
                content_block_details_id bigint,
                field_key text,
                field_value text
            );
            CREATE TABLE body_placeholder_keys (
                template_id text REFERENCES template(id),
                placeholder_key text
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


async def seed_template(
    db_pool,
    *,
    template_id: str,
    template_name: str,
    subject: str = "",
    summary: str = "",
    html: str = "",
    text: str = "",
    embed_summary: str | None = None,
    content_block_id: str | None = None,
    kv_pairs: dict[str, str] | None = None,
    body_keys: list[str] | None = None,
    tones: dict[str, float] | None = None,
) -> None:
    """Insert a template row and related structural/tone data for tests."""
    vector_literal = None
    if embed_summary is not None:
        embedding = encode_query(embed_summary)
        vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO template (id, name) VALUES ($1, $2)",
            template_id,
            template_name,
        )
        if vector_literal is None:
            await conn.execute(
                """
                INSERT INTO template_details
                    (template_id, lang_local, param_cust_brand, subject, summary, html, text)
                VALUES ($1, 'EN', 'SKRILL', $2, $3, $4, $5)
                """,
                template_id,
                subject,
                summary,
                html,
                text,
            )
        else:
            await conn.execute(
                """
                INSERT INTO template_details
                    (template_id, lang_local, param_cust_brand, subject, summary, html, text, summary_embeded)
                VALUES ($1, 'EN', 'SKRILL', $2, $3, $4, $5, $6::vector)
                """,
                template_id,
                subject,
                summary,
                html,
                text,
                vector_literal,
            )

        if content_block_id:
            await conn.execute(
                "INSERT INTO content_block (id) VALUES ($1) ON CONFLICT DO NOTHING",
                content_block_id,
            )
            await conn.execute(
                """
                INSERT INTO template_content_block (template_id, content_block_id)
                VALUES ($1, $2)
                """,
                template_id,
                content_block_id,
            )
            details_id = abs(hash(f"{template_id}:{content_block_id}")) % 900000000 + 1
            await conn.execute(
                """
                INSERT INTO content_block_details (id, content_block_id)
                VALUES ($1, $2)
                ON CONFLICT (id) DO NOTHING
                """,
                details_id,
                content_block_id,
            )
            for field_key, field_value in (kv_pairs or {}).items():
                await conn.execute(
                    """
                    INSERT INTO content_block_kv
                        (content_block_details_id, field_key, field_value)
                    VALUES ($1, $2, $3)
                    """,
                    details_id,
                    field_key,
                    field_value,
                )

        for placeholder_key in body_keys or []:
            await conn.execute(
                """
                INSERT INTO body_placeholder_keys (template_id, placeholder_key)
                VALUES ($1, $2)
                """,
                template_id,
                placeholder_key,
            )

        if tones is not None:
            await conn.execute(
                """
                INSERT INTO template_tone_evaluations
                    (template_id, lang_local, param_cust_brand, tones)
                VALUES ($1, 'EN', 'SKRILL', $2::jsonb)
                """,
                template_id,
                json.dumps(tones),
            )
