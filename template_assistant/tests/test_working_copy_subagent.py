import pytest

from template_assistant.context import SessionContextMissingError
from template_assistant.services import working_copy_key
from template_assistant.subagents.working_copy_subagent import (
    get_working_copy,
    reset_full_working_copy,
    reset_working_copy_key,
    set_working_copy_value,
)
from template_assistant.context import validate_session_context


@pytest.mark.asyncio
async def test_set_working_copy_value(redis_client, session_state):
    result = await set_working_copy_value("GREETING", "Hello there", session_state)
    assert result["applied"] is True
    ctx = validate_session_context(session_state)
    assert await redis_client.hget(working_copy_key(ctx), "GREETING") == "Hello there"


@pytest.mark.asyncio
async def test_set_working_copy_missing_context():
    with pytest.raises(SessionContextMissingError):
        await set_working_copy_value("GREETING", "Hi", {})


@pytest.mark.asyncio
async def test_get_working_copy(redis_client, session_state):
    await set_working_copy_value("A", "one", session_state)
    await set_working_copy_value("B", "two", session_state)
    wc = await get_working_copy(session_state)
    assert wc == {"A": "one", "B": "two"}


@pytest.mark.asyncio
async def test_get_working_copy_empty(redis_client, session_state):
    assert await get_working_copy(session_state) == {}


@pytest.mark.asyncio
async def test_get_working_copy_missing_context():
    with pytest.raises(SessionContextMissingError):
        await get_working_copy({})


@pytest.mark.asyncio
async def test_reset_working_copy_key(redis_client, session_state):
    await set_working_copy_value("GREETING", "Hello", session_state)
    result = await reset_working_copy_key("GREETING", session_state)
    assert result["reset"] is True
    assert await get_working_copy(session_state) == {}


@pytest.mark.asyncio
async def test_reset_full_working_copy(redis_client, session_state):
    await set_working_copy_value("A", "one", session_state)
    await set_working_copy_value("B", "two", session_state)
    result = await reset_full_working_copy(session_state)
    assert result["reset_all"] is True
    assert await get_working_copy(session_state) == {}


@pytest.mark.asyncio
async def test_reset_missing_key_does_not_raise(redis_client, session_state):
    await reset_working_copy_key("MISSING", session_state)


@pytest.mark.asyncio
async def test_reset_missing_context():
    with pytest.raises(SessionContextMissingError):
        await reset_full_working_copy({})
