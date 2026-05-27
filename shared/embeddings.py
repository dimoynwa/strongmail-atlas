from __future__ import annotations

import asyncpg

from general_agent.models import TemplateSearchResult


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(value) for value in embedding) + "]"


async def semantic_search_by_embedding(
    pool: asyncpg.Pool,
    embedding: list[float],
    limit: int,
) -> list[TemplateSearchResult]:
    """Search templates by pgvector cosine distance over summary_embeded."""
    vector = _vector_literal(embedding)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (t.id)
                t.id AS template_id,
                t.name AS template_name,
                COALESCE(td.summary, '') AS summary,
                (td.summary_embeded <=> $1::vector) AS distance
            FROM template t
            JOIN template_details td ON td.template_id = t.id
            WHERE td.summary_embeded IS NOT NULL
            ORDER BY t.id, td.summary_embeded <=> $1::vector ASC
            """,
            vector,
        )

    ranked = sorted(rows, key=lambda row: row["distance"])
    results: list[TemplateSearchResult] = []
    for row in ranked[:limit]:
        distance = float(row["distance"])
        results.append(
            TemplateSearchResult(
                template_id=row["template_id"],
                template_name=row["template_name"],
                summary=row["summary"],
                score=max(0.0, 1.0 - distance),
                source="semantic_search",
            )
        )
    return results
