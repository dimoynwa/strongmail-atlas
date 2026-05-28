from __future__ import annotations

import asyncio

from shared.db import ensure_pool


async def search_templates(
    query: str,
    lang_local: str,
    param_cust_brand: str,
    limit: int = 10,
) -> list[dict]:
    """Search templates by name or body text for the General Agent."""
    del lang_local, param_cust_brand
    pool = await ensure_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.name AS template_name,
                   COALESCE(NULLIF(td.text, ''), LEFT(td.html, 200), t.name) AS summary
            FROM template t
            LEFT JOIN template_details td ON td.template_id = t.id
            WHERE $1 = ''
               OR t.name ILIKE '%' || $1 || '%'
               OR td.text ILIKE '%' || $1 || '%'
               OR td.html ILIKE '%' || $1 || '%'
            ORDER BY t.name
            LIMIT $2
            """,
            query.strip(),
            limit,
        )
    return [
        {
            "template_name": row["template_name"],
            "summary": (row["summary"] or "")[:200],
            "distance": 0.2,
        }
        for row in rows
    ]


async def load_sidebar_metadata() -> dict[str, list[str]]:
    """Load sidebar options in one event loop to avoid pool/loop conflicts."""
    languages, brands, templates = await asyncio.gather(
        list_languages(),
        list_brands(),
        list_templates(),
    )
    return {
        "languages": languages,
        "brands": brands,
        "templates": templates,
    }


async def list_languages() -> list[str]:
    pool = await ensure_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(lang_local) AS lang_local
            FROM template_tone_evaluations
            WHERE lang_local IS NOT NULL AND lang_local <> ''
            ORDER BY 1
            """
        )
    return [row["lang_local"] for row in rows] or ["EN"]


async def list_brands() -> list[str]:
    pool = await ensure_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(param_cust_brand) AS param_cust_brand
            FROM template_tone_evaluations
            WHERE param_cust_brand IS NOT NULL AND param_cust_brand <> ''
            ORDER BY 1
            """
        )
    return [row["param_cust_brand"] for row in rows] or ["SKRILL"]


async def list_templates() -> list[str]:
    pool = await ensure_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name FROM template ORDER BY name"
        )
    return [row["name"] for row in rows]
