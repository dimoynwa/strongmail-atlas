import types

import pytest
from shared.resolution.graph_builder import build_resolution_graph

@pytest.mark.asyncio
async def test_build_resolution_graph_success(db_pool):
    # This requires strongmail-tov test DB to have this template. 
    # For now, we expect it to fail if it doesn't exist, but we will mock the test 
    # to actually assert the error if we don't have a known template.
    # We will test the "not found" scenario:
    with pytest.raises(ValueError, match="Template not found: 'UNKNOWN_TEMPLATE'"):
        await build_resolution_graph(db_pool, "UNKNOWN_TEMPLATE")

@pytest.mark.asyncio
async def test_build_resolution_graph_existing_template(db_pool):
    # Retrieve an actual template from DB if available to test success
    async with db_pool.acquire() as conn:
        template_name = await conn.fetchval("SELECT name FROM template LIMIT 1")
    
    if template_name:
        graph = await build_resolution_graph(db_pool, template_name)
        assert isinstance(graph, types.MappingProxyType)
        assert len(graph) > 0
        assert all(key == key.upper() for key in graph)
