from __future__ import annotations

from google.adk.agents import LlmAgent

from general_agent.models import (
    ResolutionHealthResult,
    StructuralSummary,
    TemplateSearchResult,
    clamp_limit,
)
from shared.db import get_pool
from template_assistant.llm import get_llm_model


async def find_templates_by_content_block(
    content_block_id: str,
    limit: int = 10,
) -> list[TemplateSearchResult]:
    """Return templates that include the given content block."""
    effective_limit = clamp_limit(limit)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT
                t.id AS template_id,
                t.name AS template_name,
                COALESCE(td.summary, '') AS summary
            FROM template t
            JOIN template_content_block tcb ON tcb.template_id = t.id
            LEFT JOIN template_details td ON td.template_id = t.id
            WHERE tcb.content_block_id = $1
            ORDER BY t.name
            LIMIT $2
            """,
            content_block_id,
            effective_limit,
        )

    return [
        TemplateSearchResult(
            template_id=row["template_id"],
            template_name=row["template_name"],
            summary=row["summary"],
            score=1.0,
            source="content_block",
        )
        for row in rows
    ]


async def find_templates_by_dynamic_content_rule(
    rule_id: str,
    limit: int = 10,
) -> list[TemplateSearchResult]:
    """Return templates referencing the given dynamic content rule."""
    effective_limit = clamp_limit(limit)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT
                t.id AS template_id,
                t.name AS template_name,
                COALESCE(td.summary, '') AS summary
            FROM template t
            JOIN template_content_block tcb ON tcb.template_id = t.id
            JOIN content_block_details cbd ON cbd.content_block_id = tcb.content_block_id
            JOIN content_block_kv kv ON kv.content_block_details_id = cbd.id
            LEFT JOIN template_details td ON td.template_id = t.id
            WHERE kv.field_value ILIKE '%' || $1 || '%'
               OR kv.field_key ILIKE '%' || $1 || '%'
               OR EXISTS (
                    SELECT 1
                    FROM dynamic_content dc
                    WHERE dc.id = $1
                      AND (
                        kv.field_value ILIKE '%' || dc.name || '%'
                        OR kv.field_value ILIKE '%SM_RULE_' || dc.name || '%'
                      )
               )
            ORDER BY t.name
            LIMIT $2
            """,
            rule_id,
            effective_limit,
        )

    return [
        TemplateSearchResult(
            template_id=row["template_id"],
            template_name=row["template_name"],
            summary=row["summary"],
            score=1.0,
            source="dynamic_content_rule",
        )
        for row in rows
    ]


async def get_template_resolution_health(template_name: str) -> ResolutionHealthResult:
    """Return resolution health based on pre-computed placeholder key data."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH template_info AS (
                SELECT t.id, t.name
                FROM template t
                WHERE t.name = $1
            ),
            graph_keys AS (
                SELECT DISTINCT UPPER(kv.field_key) AS placeholder_key
                FROM template_info ti
                JOIN template_content_block tcb ON tcb.template_id = ti.id
                JOIN content_block_details cbd ON cbd.content_block_id = tcb.content_block_id
                JOIN content_block_kv kv ON kv.content_block_details_id = cbd.id
            ),
            body_keys AS (
                SELECT DISTINCT UPPER(bpk.placeholder_key) AS placeholder_key
                FROM template_info ti
                JOIN body_placeholder_keys bpk ON bpk.template_id = ti.id
            ),
            counts AS (
                SELECT
                    (SELECT COUNT(*) FROM body_keys) AS total_keys,
                    (
                        SELECT COUNT(*)
                        FROM body_keys bk
                        LEFT JOIN graph_keys gk ON gk.placeholder_key = bk.placeholder_key
                        WHERE gk.placeholder_key IS NULL
                    ) AS unresolvable_keys
            )
            SELECT
                ti.id AS template_id,
                ti.name AS template_name,
                counts.total_keys,
                counts.unresolvable_keys
            FROM template_info ti
            CROSS JOIN counts
            """,
            template_name,
        )

    if row is None:
        raise ValueError(f"Template not found: {template_name!r}")

    total_keys = int(row["total_keys"])
    unresolvable_keys = int(row["unresolvable_keys"])
    if total_keys == 0:
        health_score = 1.0
    else:
        health_score = (total_keys - unresolvable_keys) / total_keys

    return ResolutionHealthResult(
        template_id=row["template_id"],
        template_name=row["template_name"],
        total_keys=total_keys,
        unresolvable_keys=unresolvable_keys,
        health_score=health_score,
    )


async def get_template_structure_summary(template_name: str) -> StructuralSummary:
    """Return aggregate structural composition for a template."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH template_info AS (
                SELECT t.id, t.name
                FROM template t
                WHERE t.name = $1
            ),
            graph_keys AS (
                SELECT DISTINCT UPPER(kv.field_key) AS placeholder_key
                FROM template_info ti
                JOIN template_content_block tcb ON tcb.template_id = ti.id
                JOIN content_block_details cbd ON cbd.content_block_id = tcb.content_block_id
                JOIN content_block_kv kv ON kv.content_block_details_id = cbd.id
            ),
            body_keys AS (
                SELECT DISTINCT UPPER(bpk.placeholder_key) AS placeholder_key
                FROM template_info ti
                JOIN body_placeholder_keys bpk ON bpk.template_id = ti.id
            )
            SELECT
                ti.id AS template_id,
                ti.name AS template_name,
                (
                    SELECT COUNT(DISTINCT tcb.content_block_id)
                    FROM template_content_block tcb
                    WHERE tcb.template_id = ti.id
                ) AS content_block_count,
                (SELECT COUNT(*) FROM body_keys) AS placeholder_count,
                (
                    SELECT COUNT(*)
                    FROM body_keys bk
                    LEFT JOIN graph_keys gk ON gk.placeholder_key = bk.placeholder_key
                    WHERE gk.placeholder_key IS NULL
                ) AS unresolvable_count
            FROM template_info ti
            """,
            template_name,
        )

    if row is None:
        raise ValueError(f"Template not found: {template_name!r}")

    return StructuralSummary(
        template_id=row["template_id"],
        template_name=row["template_name"],
        content_block_count=int(row["content_block_count"]),
        placeholder_count=int(row["placeholder_count"]),
        unresolvable_count=int(row["unresolvable_count"]),
    )


async def _find_templates_by_content_block_tool(
    content_block_id: str,
    limit: int = 10,
) -> list[dict]:
    results = await find_templates_by_content_block(content_block_id, limit=limit)
    return [result.to_dict() for result in results]


async def _find_templates_by_dynamic_content_rule_tool(
    rule_id: str,
    limit: int = 10,
) -> list[dict]:
    results = await find_templates_by_dynamic_content_rule(rule_id, limit=limit)
    return [result.to_dict() for result in results]


async def _get_template_resolution_health_tool(template_name: str) -> dict:
    return (await get_template_resolution_health(template_name)).to_dict()


async def _get_template_structure_summary_tool(template_name: str) -> dict:
    return (await get_template_structure_summary(template_name)).to_dict()


def create_structural_query_subagent() -> LlmAgent:
    return LlmAgent(
        name="StructuralQuerySubagent",
        model=get_llm_model("STRUCTURAL_QUERY"),
        description="""
        Answers structural audit questions about template composition, content block
        dependencies, dynamic content rules, and resolution health. Read-only SQL only.
        """,
        instruction="""
        You are the Structural Query Subagent. You audit template structure and
        resolution health using pre-computed database data — never live resolution.

        ## Your tools
        - find_templates_by_content_block: list templates using a content block ID.
        - find_templates_by_dynamic_content_rule: list templates referencing a rule ID.
        - get_template_resolution_health: count resolvable vs unresolvable placeholder keys.
        - get_template_structure_summary: aggregate block, placeholder, and issue counts.

        ## Behaviour rules
        - Never run the resolution engine — use SQL counts only.
        - Respect limit parameters on list tools (default 10, maximum 50).
        - Never write to PostgreSQL or Redis.
        """,
        tools=[
            _find_templates_by_content_block_tool,
            _find_templates_by_dynamic_content_rule_tool,
            _get_template_resolution_health_tool,
            _get_template_structure_summary_tool,
        ],
    )


StructuralQuerySubagent = create_structural_query_subagent()
