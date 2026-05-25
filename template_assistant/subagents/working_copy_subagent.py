from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from template_assistant.llm import get_llm_model

from template_assistant.context import validate_session_context
from template_assistant.services import working_copy_key


async def get_working_copy(session_state: dict) -> dict[str, str]:
    """Read all overrides from the session working copy Redis hash."""
    from shared.redis_client import get_redis

    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    data = await redis_client.hgetall(working_copy_key(session_context))
    return dict(data)


async def set_working_copy_value(key: str, value: str, session_state: dict) -> dict:
    """Write a single canonical key override to the Redis working copy hash."""
    from shared.redis_client import get_redis

    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    await redis_client.hset(working_copy_key(session_context), key.upper(), value)
    return {"key": key.upper(), "applied": True}


async def reset_working_copy_key(key: str, session_state: dict) -> dict:
    """Delete one field from the working copy hash."""
    from shared.redis_client import get_redis

    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    await redis_client.hdel(working_copy_key(session_context), key.upper())
    return {"key": key.upper(), "reset": True}


async def reset_full_working_copy(session_state: dict) -> dict:
    """Delete the entire working copy hash for this session."""
    from shared.redis_client import get_redis

    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    await redis_client.delete(working_copy_key(session_context))
    return {"reset_all": True}


async def _get_working_copy_tool(tool_context: ToolContext) -> dict[str, str]:
    return await get_working_copy(tool_context.state.to_dict())


async def _set_working_copy_value_tool(
    key: str, value: str, tool_context: ToolContext
) -> dict:
    return await set_working_copy_value(key, value, tool_context.state.to_dict())


async def _reset_working_copy_key_tool(key: str, tool_context: ToolContext) -> dict:
    return await reset_working_copy_key(key, tool_context.state.to_dict())


async def _reset_full_working_copy_tool(tool_context: ToolContext) -> dict:
    return await reset_full_working_copy(tool_context.state.to_dict())


def create_working_copy_subagent() -> LlmAgent:
    return LlmAgent(
        name="WorkingCopySubagent",
        model=get_llm_model("WORKING_COPY"),
        description="""
        Manages the session-scoped Redis working copy for the loaded template.
        Reads all current overrides, writes individual key overrides, resets
        specific keys, and resets the entire working copy. This subagent is
        the only subagent allowed to perform general-purpose reads and writes
        to the working copy hash outside of the tone suggestion flow.
        """,
        instruction="""
        You are the Working Copy Subagent. You manage the temporary, session-scoped
        overrides for placeholder values in the loaded template.

        The working copy is stored in Redis at:
        working-copy:{{template_name}}:{{session_id}}

        Each field in this hash is a canonical placeholder key (e.g. EN.PARAGRAPH_1)
        and its value is the user-edited override for this session only. Changes
        never persist to PostgreSQL.

        ## Your tools
        - get_working_copy: reads all fields from the working copy Redis hash and
          returns them as a dict of canonical key → current override value.
          Returns an empty dict when no overrides exist.
        - set_working_copy_value: writes a single canonical key override to the
          working copy Redis hash.
        - reset_working_copy_key: deletes one specific key from the working copy
          hash, restoring that placeholder to its original graph value.
        - reset_full_working_copy: deletes the entire working copy Redis hash for
          this session, restoring all placeholders to their original graph values.

        ## Behaviour rules
        - Always validate SessionContext as the first action in every tool call.
        - Never query PostgreSQL — your only data store is Redis.
        - Never call the resolution library — you do not resolve placeholders.
        - When get_working_copy returns an empty dict, tell the user clearly that
          no changes have been made in this session — do not return a blank response.
        - When reset_working_copy_key is called for a key that does not exist in
          the working copy, confirm success anyway — a missing key is already
          in its original state.
        - When reset_full_working_copy is called, always confirm to the user
          exactly how many keys were cleared.
        - Never expose raw Redis key names (the full working-copy:... string)
          in your responses — refer to overrides by their placeholder key names only.
        """,
        tools=[
            _get_working_copy_tool,
            _set_working_copy_value_tool,
            _reset_working_copy_key_tool,
            _reset_full_working_copy_tool,
        ],
    )


WorkingCopySubagent = create_working_copy_subagent()
