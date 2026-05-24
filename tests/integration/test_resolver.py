import pytest
import asyncpg
import types
from shared.resolution.resolver import resolve_body, resolve_key, scan_unresolvable, ReasonCode, WorkingCopyUnavailableError

@pytest.mark.asyncio
async def test_resolver_missing_key(db_pool, redis_client):
    graph = types.MappingProxyType({})
    context = {"LANG_LOCAL": "EN"}
    body = "Hello ##MISSING_KEY##"
    
    res = await resolve_body(db_pool, redis_client, graph, body, context, "s1", "T1")
    assert res.resolved_body == "Hello ##MISSING_KEY##"
    assert len(res.unresolvable) == 1
    assert res.unresolvable[0].reason == ReasonCode.MISSING_KEY
    assert res.unresolvable[0].key == "MISSING_KEY"

@pytest.mark.asyncio
async def test_resolver_with_graph_value(db_pool, redis_client):
    graph = types.MappingProxyType({"NAME": "John"})
    context = {}
    body = "Hello ##NAME##"
    
    res = await resolve_body(db_pool, redis_client, graph, body, context, "s2", "T1")
    assert res.resolved_body == "Hello John"
    assert len(res.unresolvable) == 0

@pytest.mark.asyncio
async def test_resolver_with_working_copy_priority(db_pool, redis_client):
    graph = types.MappingProxyType({"NAME": "John"})
    # set working copy override
    await redis_client.hset("working-copy:T1:s3", "NAME", "Jane")
    
    context = {}
    body = "Hello ##NAME##"
    
    res = await resolve_body(db_pool, redis_client, graph, body, context, "s3", "T1")
    assert res.resolved_body == "Hello Jane"
    assert len(res.unresolvable) == 0

@pytest.mark.asyncio
async def test_resolver_cycle_detection(db_pool, redis_client):
    graph = types.MappingProxyType({
        "A": "Go to ##B##",
        "B": "Go back to ##A##"
    })
    
    res = await resolve_body(db_pool, redis_client, graph, "Start: ##A##", {}, "s4", "T1")
    assert "Start: Go to Go back to ##A##" in res.resolved_body
    assert len(res.unresolvable) == 1
    assert res.unresolvable[0].reason == ReasonCode.CYCLE

@pytest.mark.asyncio
async def test_resolve_key(db_pool, redis_client):
    graph = types.MappingProxyType({"GREETING": "Hi ##NAME##", "NAME": "Bob"})
    val, unresolvable = await resolve_key(db_pool, redis_client, graph, "GREETING", {}, "s5", "T1")
    assert val == "Hi Bob"
    assert len(unresolvable) == 0

@pytest.mark.asyncio
async def test_scan_unresolvable(db_pool, redis_client):
    graph = types.MappingProxyType({"KNOWN": "value"})
    body = "##KNOWN## and ##UNKNOWN##"
    
    unres = await scan_unresolvable(db_pool, redis_client, graph, body, {}, "s1", "T1")
    assert len(unres) == 1
    assert unres[0].key == "UNKNOWN"

@pytest.mark.asyncio
async def test_resolver_context_fallback(db_pool, redis_client):
    graph = types.MappingProxyType({})
    context = {"PARAM_CUST_BRAND": "SKRILL"}
    body = "Visit https://www.##PARAM_CUST_BRAND##.com"

    res = await resolve_body(db_pool, redis_client, graph, body, context, "s6", "T1")
    assert res.resolved_body == "Visit https://www.SKRILL.com"
    assert res.unresolvable == []

@pytest.mark.asyncio
async def test_resolver_context_fallback_empty_value_is_missing(db_pool, redis_client):
    graph = types.MappingProxyType({})
    context = {"EMPTY_PARAM": ""}
    body = "Value: ##EMPTY_PARAM##"

    res = await resolve_body(db_pool, redis_client, graph, body, context, "s7", "T1")
    assert res.resolved_body == "Value: ##EMPTY_PARAM##"
    assert len(res.unresolvable) == 1
    assert res.unresolvable[0].key == "EMPTY_PARAM"

@pytest.mark.asyncio
async def test_resolver_graph_beats_context(db_pool, redis_client):
    graph = types.MappingProxyType({"PARAM_CUST_BRAND": "from-graph"})
    context = {"PARAM_CUST_BRAND": "SKRILL"}
    body = "##PARAM_CUST_BRAND##"

    res = await resolve_body(db_pool, redis_client, graph, body, context, "s8", "T1")
    assert res.resolved_body == "from-graph"
    assert res.unresolvable == []
