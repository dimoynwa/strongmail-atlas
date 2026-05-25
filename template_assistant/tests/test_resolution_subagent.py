import types

import pytest

from template_assistant.context import SessionContextMissingError
from template_assistant.subagents.resolution_subagent import (
    get_template_structure,
    list_unresolvable_placeholders,
    resolve_full_template,
    resolve_key,
)


async def _seed_template(db_pool, template_name: str, html: str, text: str = "", kv_pairs: dict | None = None):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM content_block_kv")
        await conn.execute("DELETE FROM content_block_details")
        await conn.execute("DELETE FROM content_block")
        await conn.execute("DELETE FROM template_content_block")
        await conn.execute("DELETE FROM template_details")
        await conn.execute("DELETE FROM template")
        await conn.execute(
            "INSERT INTO template (id, name) VALUES ($1, $2)",
            "tpl-1",
            template_name,
        )
        await conn.execute(
            """
            INSERT INTO template_details (template_id, lang_local, param_cust_brand, html, text)
            VALUES ($1, $2, $3, $4, $5)
            """,
            "tpl-1",
            "EN-US",
            "BRANDX",
            html,
            text,
        )
        await conn.execute("INSERT INTO content_block (id) VALUES ('cb-1')")
        await conn.execute(
            "INSERT INTO template_content_block (template_id, content_block_id) VALUES ('tpl-1', 'cb-1')"
        )
        await conn.execute(
            "INSERT INTO content_block_details (id, content_block_id) VALUES (1, 'cb-1')"
        )
        for idx, (field_key, field_value) in enumerate((kv_pairs or {}).items(), start=1):
            await conn.execute(
                """
                INSERT INTO content_block_kv (content_block_details_id, field_key, field_value)
                VALUES (1, $1, $2)
                """,
                field_key,
                field_value,
            )


@pytest.mark.asyncio
async def test_get_template_structure_groups_keys(db_pool, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        text="Plain ##FOOTER##",
        kv_pairs={"GREETING": "Hello", "FOOTER": "Bye"},
    )
    structure = await get_template_structure(session_state)
    assert "GREETING" in structure["html"]
    assert "FOOTER" in structure["text"]


@pytest.mark.asyncio
async def test_get_template_structure_missing_context():
    with pytest.raises(SessionContextMissingError):
        await get_template_structure({"session_id": "x"})


@pytest.mark.asyncio
async def test_resolve_key_returns_value(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "Hello there, welcome aboard today."},
    )
    result = await resolve_key("GREETING", session_state)
    assert result["value"] == "Hello there, welcome aboard today."


@pytest.mark.asyncio
async def test_resolve_key_uses_working_copy(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "Original greeting message here."},
    )
    await redis_client.hset(
        "working-copy:TestTemplate:test-session-001",
        "GREETING",
        "Working copy greeting message.",
    )
    result = await resolve_key("GREETING", session_state)
    assert result["value"] == "Working copy greeting message."


@pytest.mark.asyncio
async def test_resolve_key_unresolvable(db_pool, redis_client, session_state):
    await _seed_template(db_pool, "TestTemplate", html="##MISSING##")
    result = await resolve_key("MISSING", session_state)
    assert result["value"] is None
    assert result["unresolvable"]


@pytest.mark.asyncio
async def test_resolve_key_missing_context():
    with pytest.raises(SessionContextMissingError):
        await resolve_key("GREETING", {})


@pytest.mark.asyncio
async def test_resolve_full_template(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": "Resolved preview text here."},
    )
    preview = await resolve_full_template(session_state)
    assert "Resolved preview text here." in preview
    assert preview.startswith("```html")


@pytest.mark.asyncio
async def test_resolve_full_template_missing_context():
    with pytest.raises(SessionContextMissingError):
        await resolve_full_template({})


@pytest.mark.asyncio
async def test_list_unresolvable_placeholders(db_pool, redis_client, session_state):
    await _seed_template(db_pool, "TestTemplate", html="Hello ##MISSING##")
    entries = await list_unresolvable_placeholders(session_state)
    assert len(entries) == 1
    assert entries[0].key == "MISSING"
    assert entries[0].reason == "MISSING"


@pytest.mark.asyncio
async def test_list_unresolvable_empty_when_all_resolve(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "All good here."},
    )
    entries = await list_unresolvable_placeholders(session_state)
    assert entries == []


@pytest.mark.asyncio
async def test_list_unresolvable_missing_context():
    with pytest.raises(SessionContextMissingError):
        await list_unresolvable_placeholders({})
