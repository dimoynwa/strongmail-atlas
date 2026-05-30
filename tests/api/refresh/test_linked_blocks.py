from __future__ import annotations

import pytest

from api.refresh.linked_blocks import resolve_linked_blocks


async def test_resolve_linked_blocks(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM content_block_kv;
            DELETE FROM content_block_details;
            DELETE FROM template_content_block;
            DELETE FROM dynamic_content_details;
            DELETE FROM dynamic_content;
            DELETE FROM content_block;
            DELETE FROM template WHERE id = 't1';
            """
        )
        await conn.execute(
            """
            INSERT INTO template (id, name) VALUES ('t1', 'TestTemplateLinked');
            INSERT INTO content_block (id) VALUES ('cb1');
            INSERT INTO template_content_block (template_id, content_block_id)
            VALUES ('t1', 'cb1');
            INSERT INTO content_block_details (id, content_block_id) VALUES (9001, 'cb1');
            INSERT INTO dynamic_content (id, name) VALUES ('dc1', 'BRAND_LOGO');
            INSERT INTO content_block_kv (content_block_details_id, field_key, field_value)
            VALUES (9001, 'SM_RULE_BRAND_LOGO', 'value');
            """
        )

    result = await resolve_linked_blocks(db_pool, "TestTemplateLinked")
    assert result.template_id == "t1"
    assert "cb1" in result.block_ids
    assert "dc1" in result.rule_ids


async def test_resolve_linked_blocks_unknown_template(db_pool):
    with pytest.raises(ValueError, match="Template not found"):
        await resolve_linked_blocks(db_pool, "MissingTemplate")
