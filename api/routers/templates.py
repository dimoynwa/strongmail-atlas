from __future__ import annotations

from fastapi import APIRouter

from api.models.responses import BrandsResponse, LocalesResponse, TemplateListItem, TemplateListResponse
from shared.db import get_pool

router = APIRouter(prefix="/templates", tags=["templates"])

# Production DB uses 'Approved'; spec alias 'ACTIVE' included for forward compatibility.
_ACTIVE_TEMPLATE_STATUSES = ("Approved", "ACTIVE")


def _format_last_modified(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    iso = value.replace(tzinfo=None).isoformat()  # type: ignore[union-attr]
    return iso if iso.endswith("Z") else f"{iso}Z"


@router.get("", response_model=TemplateListResponse)
async def list_templates() -> TemplateListResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.name, t.id, t.last_modified_date,
                   COUNT(cbkv.field_key) AS key_count,
                   td.summary
            FROM template t
            JOIN template_content_block tcb ON tcb.template_id = t.id
            JOIN content_block_details cbd ON cbd.content_block_id = tcb.content_block_id
            JOIN content_block_kv cbkv ON cbkv.content_block_details_id = cbd.id
            LEFT JOIN template_details td ON td.template_id = t.id
            WHERE t.template_status = ANY($1::text[])
            GROUP BY t.name, t.id, t.last_modified_date, td.summary
            ORDER BY t.last_modified_date DESC NULLS LAST
            """,
            list(_ACTIVE_TEMPLATE_STATUSES),
        )

    templates = [
        TemplateListItem(
            name=row["name"],
            id=row["id"],
            key_count=row["key_count"],
            last_modified=_format_last_modified(row["last_modified_date"]),
            summary=row["summary"],
        )
        for row in rows
    ]
    return TemplateListResponse(templates=templates, total=len(templates))


@router.get("/locales", response_model=LocalesResponse)
async def list_locales() -> LocalesResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(lang_local) AS lang_local
            FROM template_tone_evaluations
            WHERE lang_local IS NOT NULL AND lang_local <> ''
            ORDER BY lang_local
            """
        )
    locales = [row["lang_local"] for row in rows] or ["EN"]
    return LocalesResponse(locales=locales)


@router.get("/brands", response_model=BrandsResponse)
async def list_brands() -> BrandsResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(param_cust_brand) AS param_cust_brand
            FROM template_tone_evaluations
            WHERE param_cust_brand IS NOT NULL AND param_cust_brand <> ''
            ORDER BY param_cust_brand
            """
        )
    brands = [row["param_cust_brand"] for row in rows] or ["SKRILL"]
    return BrandsResponse(brands=brands)
