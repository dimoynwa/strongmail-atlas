import pytest
import types
from shared.resolution.resolver import resolve_body, ReasonCode
from shared.resolution.graph_builder import build_resolution_graph

@pytest.mark.asyncio
async def test_e2e_pipeline(db_pool, redis_client):
    # Retrieve an actual template from DB if available to test success
    async with db_pool.acquire() as conn:
        template_name = await conn.fetchval("SELECT name FROM template LIMIT 1")
        
    if template_name:
        graph = await build_resolution_graph(db_pool, template_name)
        assert graph is not None
        
        # Test resolution
        body = "Testing ##UNKNOWN_KEY_FOR_E2E##."
        res = await resolve_body(db_pool, redis_client, graph, body, {"LANG_LOCAL": "EN"}, "sess_e2e", template_name)
        
        assert res.resolved_body == "Testing ##UNKNOWN_KEY_FOR_E2E##."
        assert len(res.unresolvable) == 1
        assert res.unresolvable[0].key == "UNKNOWN_KEY_FOR_E2E"
        assert res.unresolvable[0].reason == ReasonCode.MISSING_KEY
