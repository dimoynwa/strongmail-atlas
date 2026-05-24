from enum import Enum
from dataclasses import dataclass
import asyncpg
import redis.asyncio as aioredis
import types
import re

from shared.resolution.namespace import normalize_key
from shared.resolution.preprocessors import (
    is_synthetic_context_key,
    parameters_get_ci,
    preprocess_key,
)

PLACEHOLDER_PATTERN = re.compile(
    r"##(?:/?/?\\?[A-Za-z0-9_.]+|\[F\]\[S\]\[P\]\[(?:\\)*[A-Za-z0-9_.]+\])##"
)

class ReasonCode(str, Enum):
    MISSING_KEY        = "MISSING_KEY"
    CYCLE              = "CYCLE"
    BROKEN_RULE_CHAIN  = "BROKEN_RULE_CHAIN"
    INVALID_RULE       = "INVALID_RULE"

@dataclass(frozen=True)
class UnresolvableEntry:
    key: str            # canonical (uppercase) placeholder key
    reason: ReasonCode  # typed reason code
    detail: str         # human-readable context (cycle path, missing target, etc.)

@dataclass(frozen=True)
class ResolutionResult:
    resolved_body: str                        # fully substituted string
    unresolvable: list[UnresolvableEntry]     # all keys that could not be resolved

class WorkingCopyUnavailableError(RuntimeError):
    """Redis working-copy store is unreachable; resolution cannot proceed."""

class CycleDetectedException(RuntimeError):
    """A circular placeholder reference was detected."""
    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path  # e.g. ["A", "B", "A"]
        super().__init__(" → ".join(cycle_path))


def _lookup_context_value(expanded: str, context: dict[str, str]) -> str | None:
    value = parameters_get_ci(context, expanded)
    if value is None or value == "":
        return None
    return value


async def _resolve_node(
    raw_key: str,
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    context: dict[str, str],
    session_id: str,
    template_name: str,
    visiting: list[str],
    unresolvable: list[UnresolvableEntry],
) -> str | None:
    canonical = normalize_key(raw_key)
    expanded = preprocess_key(canonical, context)

    if is_synthetic_context_key(expanded) and expanded in context:
        return context[expanded]
    
    if expanded in visiting:
        cycle_path = visiting + [expanded]
        unresolvable.append(UnresolvableEntry(expanded, ReasonCode.CYCLE, " → ".join(cycle_path)))
        return None
        
    visiting.append(expanded)
    
    try:
        # Check Redis
        hash_key = f"working-copy:{template_name}:{session_id}"
        try:
            val = await redis_client.hget(hash_key, expanded)
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            raise WorkingCopyUnavailableError("Redis unavailable") from e
            
        if val is None:
            # Check Graph
            val = graph.get(expanded)
            
            if val is None:
                # Check SM_RULE_
                if expanded.startswith("SM_RULE_"):
                    # Limit SM_RULE chaining to 10 hops
                    from shared.resolution.sm_rule_evaluator import evaluate_sm_rule
                    sm_rule_count = sum(1 for v in visiting if v.startswith("SM_RULE_"))
                    if sm_rule_count > 10:
                        unresolvable.append(UnresolvableEntry(expanded, ReasonCode.CYCLE, "SM_RULE chain > 10 hops"))
                        return None
                        
                    res = await evaluate_sm_rule(pool, expanded, context)
                    if isinstance(res, ReasonCode):
                        if res == ReasonCode.MISSING_KEY:
                            unresolvable.append(UnresolvableEntry(expanded, ReasonCode.MISSING_KEY, "Rule not found"))
                        elif res == ReasonCode.INVALID_RULE:
                            unresolvable.append(UnresolvableEntry(expanded, ReasonCode.INVALID_RULE, "Invalid rule AST"))
                        return None
                    else:
                        val = res
                        if val.startswith("SM_RULE_") or re.match(r"^[A-Z0-9_.]+$", val):
                            # It's a key or another rule, need to resolve it
                            resolved_val = await _resolve_node(val, pool, redis_client, graph, context, session_id, template_name, visiting, unresolvable)
                            if resolved_val is None:
                                unresolvable.append(UnresolvableEntry(expanded, ReasonCode.BROKEN_RULE_CHAIN, f"Target key {val} missing"))
                                return None
                            return resolved_val
                        else:
                            # It's an inline literal value 
                            pass
                else:
                    context_val = _lookup_context_value(expanded, context)
                    if context_val is not None:
                        val = context_val
                    else:
                        unresolvable.append(UnresolvableEntry(expanded, ReasonCode.MISSING_KEY, "Missing key in graph and working copy"))
                        return None
                    
        result_parts = []
        last_index = 0
        for m in PLACEHOLDER_PATTERN.finditer(val):
            result_parts.append(val[last_index:m.start()])
            inner_raw = m.group(0)
            inner_resolved = await _resolve_node(inner_raw, pool, redis_client, graph, context, session_id, template_name, visiting, unresolvable)
            if inner_resolved is not None:
                result_parts.append(inner_resolved)
            else:
                result_parts.append(inner_raw)
            last_index = m.end()
            
        result_parts.append(val[last_index:])
        return "".join(result_parts)

    finally:
        visiting.pop()

async def resolve_body(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    body: str,
    context: dict[str, str],
    session_id: str,
    template_name: str,
) -> ResolutionResult:
    unresolvable: list[UnresolvableEntry] = []
    
    result_parts = []
    last_index = 0
    for m in PLACEHOLDER_PATTERN.finditer(body):
        result_parts.append(body[last_index:m.start()])
        raw_key = m.group(0)
        resolved_val = await _resolve_node(raw_key, pool, redis_client, graph, context, session_id, template_name, [], unresolvable)
        if resolved_val is not None:
            result_parts.append(resolved_val)
        else:
            result_parts.append(raw_key)
        last_index = m.end()
        
    result_parts.append(body[last_index:])
    
    return ResolutionResult(
        resolved_body="".join(result_parts),
        unresolvable=unresolvable
    )

async def resolve_key(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    key: str,
    context: dict[str, str],
    session_id: str,
    template_name: str,
) -> tuple[str | None, list[UnresolvableEntry]]:
    unresolvable: list[UnresolvableEntry] = []
    val = await _resolve_node(key, pool, redis_client, graph, context, session_id, template_name, [], unresolvable)
    return val, unresolvable

async def scan_unresolvable(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    body: str,
    context: dict[str, str],
    session_id: str,
    template_name: str,
) -> list[UnresolvableEntry]:
    res = await resolve_body(pool, redis_client, graph, body, context, session_id, template_name)
    return res.unresolvable
