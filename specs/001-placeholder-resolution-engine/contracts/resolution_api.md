# Contract: shared/resolution Public API

*Phase 1 output — generated 2026-05-23*

This document specifies the full public API surface of the `shared/resolution` package.
Everything exported from `shared/resolution/__init__.py` is part of this contract.
Internal helpers are not listed; they are implementation detail.

---

## Types

### `ReasonCode` (enum, `shared/resolution/resolver.py`)

```python
from enum import Enum

class ReasonCode(str, Enum):
    MISSING_KEY        = "MISSING_KEY"
    CYCLE              = "CYCLE"
    BROKEN_RULE_CHAIN  = "BROKEN_RULE_CHAIN"
    INVALID_RULE       = "INVALID_RULE"
```

### `UnresolvableEntry` (dataclass, `shared/resolution/resolver.py`)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class UnresolvableEntry:
    key: str            # canonical (uppercase) placeholder key
    reason: ReasonCode  # typed reason code
    detail: str         # human-readable context (cycle path, missing target, etc.)
```

### `ResolutionResult` (dataclass, `shared/resolution/resolver.py`)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ResolutionResult:
    resolved_body: str                        # fully substituted string
    unresolvable: list[UnresolvableEntry]     # all keys that could not be resolved
```

---

## Exceptions

### `WorkingCopyUnavailableError` (`shared/resolution/resolver.py`)

Raised when the Redis working-copy store is unreachable. Silent fallback is prohibited.

```python
class WorkingCopyUnavailableError(RuntimeError):
    """Redis working-copy store is unreachable; resolution cannot proceed."""
```

### `CycleDetectedException` (`shared/resolution/resolver.py`)

Raised internally during recursive resolution when a canonical key is re-entered.
Callers do not need to catch this — the resolver catches it internally and adds the
offending key to `unresolvable` with `reason=ReasonCode.CYCLE`.

```python
class CycleDetectedException(RuntimeError):
    """A circular placeholder reference was detected."""
    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path  # e.g. ["A", "B", "A"]
        super().__init__(" → ".join(cycle_path))
```

---

## Public Functions

All functions are async and live in `shared/resolution/`.

---

### `build_resolution_graph`

*Module*: `shared/resolution/graph_builder.py`

```python
import asyncpg
import types

async def build_resolution_graph(
    pool: asyncpg.Pool,
    template_name: str,
) -> types.MappingProxyType[str, str]:
    """Build the immutable canonical-key→raw-value resolution graph for a template.

    Queries PostgreSQL to produce a dict of all placeholder key-value pairs defined
    by the template's linked content blocks. Keys are uppercased canonical strings.
    When multiple content blocks define the same key, the first by content_block_details.id
    (link order) wins; subsequent duplicates are silently discarded.

    Args:
        pool: Active asyncpg connection pool.
        template_name: The template's ``name`` column value (exact match, case-sensitive).

    Returns:
        An immutable MappingProxyType mapping canonical keys to raw values.
        Raw values may contain ##PLACEHOLDER## tokens for recursive resolution.

    Raises:
        ValueError: If ``template_name`` is not found in the database.
        asyncpg.PostgresError: On any database error.
    """
```

**Behaviour**:
- Returns an empty `MappingProxyType({})` if the template exists but has no content blocks.
- Raises `ValueError(f"Template not found: {template_name!r}")` if the template name does not
  exist in the database.
- Raises `asyncpg.PostgresError` on connection or query errors (never swallowed).

---

### `resolve_body`

*Module*: `shared/resolution/resolver.py`

```python
import asyncpg
import redis.asyncio as aioredis
import types

async def resolve_body(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    body: str,
    context: dict[str, str],
    session_id: str,
    template_name: str,
) -> ResolutionResult:
    """Resolve all ##PLACEHOLDER## tokens in a template body string.

    Replaces every ##TOKEN## in ``body`` with its fully resolved value. Nested
    placeholders are expanded recursively. Unresolvable tokens are left verbatim in
    the output and reported in the returned ``unresolvable`` list.

    Args:
        pool: Active asyncpg connection pool (for SM_RULE evaluation).
        redis_client: Async Redis client (for working-copy lookups).
        graph: Immutable resolution graph from ``build_resolution_graph``.
        body: The raw HTML or text body string containing ##PLACEHOLDER## tokens.
        context: Runtime context dict (all keys/values uppercased).
                 E.g. {"LANG_LOCAL": "EN", "PARAM_CUST_BRAND": "SKRILL"}.
        session_id: Session identifier for the working-copy Redis hash.
        template_name: Template name — used to construct the working-copy Redis key.

    Returns:
        ResolutionResult with ``resolved_body`` (fully substituted string) and
        ``unresolvable`` (list of UnresolvableEntry for every key that could not resolve).

    Raises:
        WorkingCopyUnavailableError: If Redis is unreachable. Silent fallback is prohibited.
        asyncpg.PostgresError: On database errors during SM_RULE evaluation.
    """
```

**Behaviour**:
- Bodies with no `##PLACEHOLDER##` tokens return unchanged with an empty `unresolvable` list.
- Cycle detection: re-entering a key during recursion adds it to `unresolvable` with
  `reason=CYCLE` and `detail` containing the full cycle path (e.g. `"A → B → A"`).
- SM_RULE chains longer than 10 hops are treated as cycles.

---

### `resolve_key`

*Module*: `shared/resolution/resolver.py`

```python
async def resolve_key(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    key: str,
    context: dict[str, str],
    session_id: str,
    template_name: str,
) -> tuple[str | None, list[UnresolvableEntry]]:
    """Resolve a single placeholder key to its final string value.

    Args:
        pool: Active asyncpg connection pool.
        redis_client: Async Redis client.
        graph: Immutable resolution graph.
        key: The placeholder key to resolve (with or without ## wrappers; normalized internally).
        context: Runtime context dict (uppercased).
        session_id: Session identifier for working-copy lookup.
        template_name: Template name for working-copy Redis key.

    Returns:
        A tuple (resolved_value, unresolvable_entries). ``resolved_value`` is None if the key
        cannot be resolved at all; otherwise the fully expanded string. ``unresolvable_entries``
        contains entries for any failures encountered during recursive expansion.

    Raises:
        WorkingCopyUnavailableError: If Redis is unreachable.
        asyncpg.PostgresError: On database errors.
    """
```

---

### `scan_unresolvable`

*Module*: `shared/resolution/resolver.py`

```python
async def scan_unresolvable(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    graph: types.MappingProxyType[str, str],
    body: str,
    context: dict[str, str],
    session_id: str,
    template_name: str,
) -> list[UnresolvableEntry]:
    """Scan all ##PLACEHOLDER## tokens in a body and return entries for unresolvable keys.

    Inspects every token without modifying the body. Returns one entry per unresolvable
    key with ``key``, ``reason``, and ``detail``.

    Args:
        pool: Active asyncpg connection pool.
        redis_client: Async Redis client.
        graph: Immutable resolution graph.
        body: Template body string to inspect.
        context: Runtime context dict (uppercased).
        session_id: Session identifier.
        template_name: Template name for working-copy Redis key.

    Returns:
        List of UnresolvableEntry. Empty if all placeholders resolve successfully.

    Raises:
        WorkingCopyUnavailableError: If Redis is unreachable.
        asyncpg.PostgresError: On database errors.
    """
```

---

## Namespace / Key Normalization (Internal, `shared/resolution/namespace.py`)

Not re-exported publicly, but documents the normalization contract.

```python
def normalize_key(raw: str) -> str:
    """Strip placeholder wrapper patterns and uppercase the result.

    Handles: ##KEY##, ##/KEY##, ##//KEY##, ##\\KEY##.
    Keys are case-insensitive at input; output is always uppercase.

    Args:
        raw: Raw placeholder string, with or without ## wrappers.

    Returns:
        Uppercase canonical key string.
    """

def expand_namespace_prefix(
    canonical_key: str,
    context: dict[str, str],
) -> str:
    """Expand the first dot-segment of a key if it matches a runtime context key.

    Compares the first dot-segment of ``canonical_key`` (case-insensitively) against
    all keys in ``context``. If a match is found and the context value is non-empty,
    replaces the segment with the uppercased context value.

    Args:
        canonical_key: Uppercase key string, e.g. "LANG_LOCAL.PARAGRAPH_1".
        context: Runtime context dict with uppercase keys, e.g. {"LANG_LOCAL": "EN"}.

    Returns:
        Expanded key, e.g. "EN.PARAGRAPH_1". Returns ``canonical_key`` unchanged
        if no prefix match is found or the matched context value is empty.
    """
```

---

## `shared/resolution/__init__.py` Exports

```python
from .resolver import (
    resolve_body,
    resolve_key,
    scan_unresolvable,
    ResolutionResult,
    UnresolvableEntry,
    ReasonCode,
    WorkingCopyUnavailableError,
    CycleDetectedException,
)
from .graph_builder import build_resolution_graph

__all__ = [
    "build_resolution_graph",
    "resolve_body",
    "resolve_key",
    "scan_unresolvable",
    "ResolutionResult",
    "UnresolvableEntry",
    "ReasonCode",
    "WorkingCopyUnavailableError",
    "CycleDetectedException",
]
```

---

## Usage Example (Caller Pattern)

```python
from shared.db import init_pool, get_pool
from shared.redis_client import init_redis, get_redis
from shared.resolution import build_resolution_graph, resolve_body

# Agent startup — once per process
await init_pool("postgresql://postgres:postgres@localhost:5432/strongmail")
await init_redis("redis://localhost:6379/0")

pool = get_pool()
redis = get_redis()

# Per session — agent caches graph
context = {"LANG_LOCAL": "EN", "PARAM_CUST_BRAND": "SKRILL"}
graph = await build_resolution_graph(pool, template_name="CREATE_PASSWORD_EMAIL")

# Per resolution call
result = await resolve_body(
    pool=pool,
    redis_client=redis,
    graph=graph,
    body=raw_html,
    context=context,
    session_id="abc123",
    template_name="CREATE_PASSWORD_EMAIL",
)

print(result.resolved_body)
for entry in result.unresolvable:
    print(f"  UNRESOLVABLE {entry.key}: {entry.reason} — {entry.detail}")
```
