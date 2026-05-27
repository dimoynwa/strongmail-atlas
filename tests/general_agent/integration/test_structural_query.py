import pytest

from general_agent.subagents.structural_query_subagent import (
    find_templates_by_content_block,
    find_templates_by_dynamic_content_rule,
    get_template_resolution_health,
    get_template_structure_summary,
)
from tests.general_agent.conftest import seed_template


@pytest.mark.asyncio
async def test_find_templates_by_content_block(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-1",
        template_name="UsesBlock",
        content_block_id="cb-123",
    )
    await seed_template(
        db_pool,
        template_id="tpl-2",
        template_name="OtherTemplate",
        content_block_id="cb-999",
    )

    results = await find_templates_by_content_block("cb-123", limit=10)

    assert len(results) == 1
    assert results[0].template_name == "UsesBlock"
    assert results[0].source == "content_block"


@pytest.mark.asyncio
async def test_find_templates_by_dynamic_content_rule(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO dynamic_content (id, name) VALUES ('rule-456', 'BRAND_LOGO')"
        )

    await seed_template(
        db_pool,
        template_id="tpl-rule",
        template_name="RuleTemplate",
        content_block_id="cb-rule",
        kv_pairs={"LOGO": "##SM_RULE_BRAND_LOGO##"},
    )

    results = await find_templates_by_dynamic_content_rule("rule-456", limit=10)

    assert len(results) == 1
    assert results[0].template_name == "RuleTemplate"


@pytest.mark.asyncio
async def test_get_template_structure_summary(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-struct",
        template_name="StructTemplate",
        content_block_id="cb-1",
        kv_pairs={"PARAGRAPH_1": "Hello"},
        body_keys=["PARAGRAPH_1", "MISSING_KEY"],
    )

    summary = await get_template_structure_summary("StructTemplate")

    assert summary.template_name == "StructTemplate"
    assert summary.content_block_count == 1
    assert summary.placeholder_count == 2
    assert summary.unresolvable_count == 1


@pytest.mark.asyncio
async def test_get_template_resolution_health_perfect_score(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-healthy",
        template_name="HealthyTemplate",
        content_block_id="cb-healthy",
        kv_pairs={"PARAGRAPH_1": "Resolved text"},
        body_keys=["PARAGRAPH_1"],
    )

    health = await get_template_resolution_health("HealthyTemplate")

    assert health.health_score == 1.0
    assert health.total_keys == 1
    assert health.unresolvable_keys == 0
