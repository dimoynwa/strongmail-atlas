from __future__ import annotations

from google.adk.agents import LlmAgent

from general_agent.models import TemplateSearchResult, clamp_limit
from shared.db import get_pool
from template_assistant.llm import get_llm_model

_ALLOWED_FIELDS = frozenset({"name", "subject", "summary"})


def _build_tsvector(fields: list[str]) -> str:
    parts: list[str] = []
    if "name" in fields:
        parts.append("coalesce(t.name, '')")
    if "subject" in fields:
        parts.append("coalesce(td.subject, '')")
    if "summary" in fields:
        parts.append("coalesce(td.summary, '')")
    return " || ' ' || ".join(parts) if parts else "''"


async def keyword_search_templates(
    query: str,
    fields: list[str] | None = None,
    limit: int = 10,
) -> list[TemplateSearchResult]:
    """Find templates by keyword/full-text match over name, subject, and summary."""
    effective_limit = clamp_limit(limit)
    search_fields = fields or ["name", "subject", "summary"]
    invalid = set(search_fields) - _ALLOWED_FIELDS
    if invalid:
        raise ValueError(f"Unsupported search fields: {sorted(invalid)}")

    tsvector_expr = _build_tsvector(search_fields)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT ON (t.id)
                t.id AS template_id,
                t.name AS template_name,
                COALESCE(td.summary, '') AS summary,
                ts_rank(
                    to_tsvector('english', {tsvector_expr}),
                    plainto_tsquery('english', $1)
                ) AS rank
            FROM template t
            JOIN template_details td ON td.template_id = t.id
            WHERE to_tsvector('english', {tsvector_expr})
                  @@ plainto_tsquery('english', $1)
            ORDER BY t.id, rank DESC
            """,
            query,
        )

    ranked = sorted(rows, key=lambda row: row["rank"], reverse=True)
    return [
        TemplateSearchResult(
            template_id=row["template_id"],
            template_name=row["template_name"],
            summary=row["summary"],
            score=float(row["rank"]),
            source="keyword_search",
        )
        for row in ranked[:effective_limit]
    ]


async def _keyword_search_templates_tool(
    query: str,
    fields: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    results = await keyword_search_templates(query, fields=fields, limit=limit)
    return [result.to_dict() for result in results]


def create_keyword_search_subagent() -> LlmAgent:
    return LlmAgent(
        name="KeywordSearchSubagent",
        model=get_llm_model("KEYWORD_SEARCH"),
        description="""
        Finds templates by exact keyword and full-text search over template name,
        subject, and summary fields. Read-only; never writes to any store.
        """,
        instruction="""
        You are the Keyword Search Subagent. You find templates that contain
        specific words or phrases in their name, subject, or summary.

        ## Your tool
        - keyword_search_templates: PostgreSQL full-text search with configurable
          fields (name, subject, summary). Default searches all three.

        ## Behaviour rules
        - Use keyword_search_templates when the user mentions exact terms or phrases.
        - Respect the limit parameter (default 10, maximum 50).
        - When no results are returned, tell the user no matching templates were found.
        - Never write to PostgreSQL or Redis.
        """,
        tools=[_keyword_search_templates_tool],
    )


KeywordSearchSubagent = create_keyword_search_subagent()
