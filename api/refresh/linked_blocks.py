from __future__ import annotations

import asyncpg

from api.refresh.models import LinkedBlocksResult

_BLOCK_IDS_SQL = """
    SELECT DISTINCT tcb.content_block_id
    FROM template t
    JOIN template_content_block tcb ON tcb.template_id = t.id
    WHERE t.name = $1
"""

_RULE_IDS_SQL = """
    SELECT DISTINCT dc.id
    FROM template t
    JOIN template_content_block tcb ON tcb.template_id = t.id
    JOIN content_block cb ON cb.id = tcb.content_block_id
    JOIN content_block_details cbd ON cbd.content_block_id = cb.id
    JOIN content_block_kv kv ON kv.content_block_details_id = cbd.id
    JOIN dynamic_content dc ON (
        kv.field_key ILIKE '%SM_RULE_' || dc.name || '%'
        OR kv.field_value ILIKE '%SM_RULE_' || dc.name || '%'
        OR kv.field_value ILIKE '%' || dc.name || '%'
        OR kv.field_key ILIKE '%' || dc.name || '%'
    )
    WHERE t.name = $1
"""

_TEMPLATE_ID_SQL = """
    SELECT id FROM template WHERE name = $1 LIMIT 1
"""


async def resolve_linked_blocks(
    pool: asyncpg.Pool,
    template_name: str,
) -> LinkedBlocksResult:
    async with pool.acquire() as conn:
        template_id = await conn.fetchval(_TEMPLATE_ID_SQL, template_name)
        if template_id is None:
            raise ValueError(f"Template not found: {template_name!r}")

        block_rows = await conn.fetch(_BLOCK_IDS_SQL, template_name)
        rule_rows = await conn.fetch(_RULE_IDS_SQL, template_name)

    block_ids = [str(row["content_block_id"]) for row in block_rows]
    rule_ids = [str(row["id"]) for row in rule_rows]
    return LinkedBlocksResult(
        block_ids=block_ids,
        rule_ids=rule_ids,
        template_id=str(template_id),
    )
