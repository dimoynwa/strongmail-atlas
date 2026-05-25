from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from template_assistant.llm import get_llm_model

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import resolve_key as shared_resolve_key
from template_assistant.context import SessionContext, build_resolution_context, validate_session_context
from template_assistant.models import UnresolvableKey
from template_assistant.services import (
    extract_placeholder_keys,
    fetch_template_bodies,
    map_unresolvable_reason,
    resolve_template,
)


async def get_template_structure(session_state: dict) -> dict:
    """Return placeholder keys grouped by HTML and text template bodies."""
    session_context = validate_session_context(session_state)
    pool = get_pool()
    html_body, text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    return {
        "html": extract_placeholder_keys(html_body),
        "text": extract_placeholder_keys(text_body),
    }


async def resolve_key(key: str, session_state: dict) -> dict:
    """Resolve a single placeholder key using the shared resolution library."""
    session_context = validate_session_context(session_state)
    pool = get_pool()
    redis_client = get_redis()
    graph = await build_resolution_graph(pool, session_context.template_name)
    context = build_resolution_context(session_context)
    value, unresolvable = await shared_resolve_key(
        pool,
        redis_client,
        graph,
        key,
        context,
        session_context.session_id,
        session_context.template_name,
    )
    return {
        "key": key,
        "value": value,
        "unresolvable": [
            {"key": entry.key, "reason": map_unresolvable_reason(entry.reason), "detail": entry.detail}
            for entry in unresolvable
        ],
    }


async def resolve_full_template(session_state: dict) -> str:
    """Return the fully resolved HTML body as a markdown code block."""
    session_context = validate_session_context(session_state)
    result = await resolve_template(session_context)
    unresolvable_lines = [
        f"- {entry.key}: {map_unresolvable_reason(entry.reason)}"
        for entry in result.unresolvable
    ]
    suffix = ""
    if unresolvable_lines:
        suffix = "\n\nUnresolvable placeholders:\n" + "\n".join(unresolvable_lines)
    return f"```html\n{result.resolved_body}\n```{suffix}"


async def list_unresolvable_placeholders(session_state: dict) -> list[UnresolvableKey]:
    """Return placeholders that cannot be resolved under the current context."""
    session_context = validate_session_context(session_state)
    result = await resolve_template(session_context)
    return [
        UnresolvableKey(key=entry.key, reason=map_unresolvable_reason(entry.reason))
        for entry in result.unresolvable
    ]


async def _get_template_structure_tool(tool_context: ToolContext) -> dict:
    return await get_template_structure(tool_context.state.to_dict())


async def _resolve_key_tool(key: str, tool_context: ToolContext) -> dict:
    return await resolve_key(key, tool_context.state.to_dict())


async def _resolve_full_template_tool(tool_context: ToolContext) -> str:
    return await resolve_full_template(tool_context.state.to_dict())


async def _list_unresolvable_placeholders_tool(tool_context: ToolContext) -> list[dict]:
    entries = await list_unresolvable_placeholders(tool_context.state.to_dict())
    return [{"key": entry.key, "reason": entry.reason} for entry in entries]


def create_resolution_subagent() -> LlmAgent:
    return LlmAgent(
        name="ResolutionSubagent",
        model=get_llm_model("RESOLUTION"),
        description="""
        Handles all read-only content operations for the loaded template.
        Resolves individual placeholder keys, returns the full resolved HTML
        preview, and reports which placeholders cannot be resolved under the
        current session context. Never writes to Redis or PostgreSQL.
        """,
        instruction="""
        You are the Resolution Subagent. You answer read-only questions about
        the content of the template loaded in the current session.

        ## Your tools
        - get_template_structure: returns all placeholder keys found in the
          template's HTML and text bodies, grouped by body type.
        - resolve_key: resolves a single placeholder key to its final string
          value, respecting the Redis working copy for this session.
        - resolve_full_template: resolves the complete HTML body of the template,
          replacing all ##PLACEHOLDER## tokens with their final values. Returns
          the resolved HTML as a code block and lists any keys that could not
          be resolved.
        - list_unresolvable_placeholders: returns all placeholder keys in the
          template that cannot be resolved under the current context, with a
          reason code for each (MISSING, CYCLE, or BROKEN_RULE).

        ## Behaviour rules
        - Always validate SessionContext as the first action in every tool call.
          Raise SessionContextMissingError immediately if any field is absent.
        - Never resolve placeholders manually — always call the shared resolution
          library. You are a thin interface over that library.
        - When resolve_full_template returns unresolvable keys alongside the
          resolved HTML, always surface both to the caller — do not suppress
          the unresolvable list even when the HTML looks complete.
        - When the resolved value of a key is empty string, report it as empty —
          do not report it as unresolvable.
        - Always return working copy values when they exist — the resolution
          library handles this automatically, but confirm in your response
          when a value came from the working copy (i.e. it was user-edited).
        """,
        tools=[
            _get_template_structure_tool,
            _resolve_key_tool,
            _resolve_full_template_tool,
            _list_unresolvable_placeholders_tool,
        ],
    )

ResolutionSubagent = create_resolution_subagent()
