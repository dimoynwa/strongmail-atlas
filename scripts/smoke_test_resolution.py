import asyncio

from shared.config import DATABASE_URL, REDIS_URL
from shared.db import close_pool, get_pool, init_pool
from shared.redis_client import get_redis, init_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import resolve_body

TEMPLATE_NAME = "NFY_PASSWORD_CREATED"


async def smoke_test() -> None:
    await init_pool(DATABASE_URL)
    redis = await init_redis(REDIS_URL)

    try:
        pool = get_pool()

        async with pool.acquire() as conn:
            body = await conn.fetchval(
                """
                SELECT td.html
                FROM template t
                JOIN template_details td ON td.template_id = t.id
                WHERE t.name = $1
                LIMIT 1
                """,
                TEMPLATE_NAME,
            )

        if not body:
            raise SystemExit(f"No HTML body found for template {TEMPLATE_NAME!r}")

        graph = await build_resolution_graph(
            pool=pool,
            template_name=TEMPLATE_NAME,
        )

        result = await resolve_body(
            pool=pool,
            redis_client=redis,
            graph=graph,
            body=body,
            context={
                "LANG_LOCAL": "EN",
                "PARAM_CUST_BRAND": "SKRILL",
                "PARAM_CUST_ACC_URL": "https://www.skrill.com",
                "CAMPAIGN_NAME": "SKRILL_CAMPAIGN",
            },
            session_id="test-session-123",
            template_name=TEMPLATE_NAME,
        )

        print(result.resolved_body)
        for entry in result.unresolvable:
            print(f"{entry.key}: {entry.reason.value} — {entry.detail}")
    finally:
        await close_pool()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(smoke_test())
