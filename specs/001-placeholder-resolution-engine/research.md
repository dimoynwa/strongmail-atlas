# Research: Placeholder Resolution Engine

*Phase 0 output — generated 2026-05-23*

All NEEDS CLARIFICATION items from the Technical Context are resolved below. Findings come from
live database inspection (Docker container `strongmail_postgres`, database `strongmail`),
reading `samples/rule_engine.py`, and the authoritative spec clarifications.

---

## 1. Database Schema — Join Path for Graph Building

**Decision**: Build the resolution graph by joining `template` → `template_content_block` →
`content_block` → `content_block_details` → `content_block_kv`. Order by
`content_block_details.id ASC` so that the first content block (lowest `cbd.id`) wins for
duplicate keys.

**Rationale**: The schema has no explicit `link_order` column. `content_block_details.id` is a
bigint sequence that reflects insertion order, which corresponds to the "link order" described in
the spec. Live data confirms templates can have 6–12 content blocks; the largest templates have
~8,400 distinct KV pairs. Duplicate keys (`COUNT(*) > 1`) appear in real templates — the first
row by `cbd.id ASC` is the authoritative value.

**Concrete SQL** (parameterized, $1 = template_name):
```sql
SELECT DISTINCT ON (kv.field_key) kv.field_key, kv.field_value
FROM template t
JOIN template_content_block tcb ON tcb.template_id = t.id
JOIN content_block cb           ON cb.id = tcb.content_block_id
JOIN content_block_details cbd  ON cbd.content_block_id = cb.id
JOIN content_block_kv kv        ON kv.content_block_details_id = cbd.id
WHERE t.name = $1
ORDER BY kv.field_key, cbd.id ASC
```

`DISTINCT ON (kv.field_key) ... ORDER BY kv.field_key, cbd.id ASC` selects the row with the
lowest `cbd.id` for each key — i.e., the first content block wins.

**Template existence check** (must raise on unknown name):
```sql
SELECT id FROM template WHERE name = $1
```

**Alternatives considered**: Ordering by `content_block_kv.id` or by `template_content_block`
insertion order. Rejected because `content_block_details.id` is the only stable sequence
reflecting the original link order.

---

## 2. SM_RULE Lookup — dynamic_content.name Convention

**Decision**: When the resolver encounters key `SM_RULE_BRAND_COLOR`, strip the `SM_RULE_`
prefix and query `dynamic_content WHERE name = 'BRAND_COLOR'`. If that returns no rows, retry
with the full key `SM_RULE_BRAND_COLOR` (handles a small number of legacy entries that include
the prefix in their name).

**Rationale**: Live inspection of 400+ `dynamic_content` rows shows almost all names are stored
WITHOUT the `SM_RULE_` prefix (e.g., `BRAND_COLOR`, `GENERAL_BRAND_LOGO`, `FRN_TRN_ID_STYLE`).
One legacy entry `SM_RULE_STATE_FOOTER_LANG` retains the prefix. The two-attempt strategy handles
both cases without a schema change.

**Concrete SQL** (try stripped name first; $1 = stripped name, $2 = full key):
```sql
SELECT dcd.rule_ast
FROM dynamic_content d
JOIN dynamic_content_details dcd ON dcd.dynamic_content_id = d.id
WHERE d.name = $1 OR d.name = $2
ORDER BY (d.name = $1) DESC
LIMIT 1
```

**Alternatives considered**: Always strip prefix (fails for legacy entries); always use full key
(fails for the 99%+ majority). Two-attempt OR query is simplest.

---

## 3. rule_ast JSON Structure (Confirmed from Live Data)

**Decision**: Evaluate the pre-parsed `rule_ast` JSONB column — do not parse `rule_text`.

**Confirmed AST schema** (`BRAND_COLOR` example):
```json
{
  "schema_version": 1,
  "kind": "strongmail_dynamic_content_rule",
  "valid": true,
  "condition": {
    "combiner": "or",
    "clauses": [
      {
        "variable_expr": "Final - Refund.param_cust_brand",
        "variable_key": "PARAM_CUST_BRAND",
        "operator": "is equal to",
        "value": "Neteller"
      }
    ]
  },
  "then": "###255F11##",
  "else": "BRAND_COLOR_BUSINESS_WALLET"
}
```

**Branch result normalization** (from `samples/rule_engine.py::_normalize_return_value`):
1. Replace `####` with `##`
2. Strip leading `\`
3. If matches `^[A-Z_]+$` → return `SM_RULE_{value}` (triggers chained rule lookup)
4. If wrapped in `##...##` → extract inner key for graph lookup
5. Otherwise → return as literal inline string (e.g., CSS color `#255F11`)

**Alternatives considered**: Parsing `rule_text` at runtime — rejected by spec assumption
("the library reads and evaluates the AST — it does not parse raw rule text").

---

## 4. SM_RULE Branch Result — Literal vs. Key Distinction

**Decision**: After `_normalize_return_value`, the sm_rule_evaluator returns a plain string. The
resolver applies this dispatch:
1. Result starts with `SM_RULE_` → recurse into that rule (chained evaluation)
2. Result matches placeholder key pattern (`^[A-Z0-9_.]+$`, no special chars) → look up in graph
3. Otherwise (contains `#`, spaces, HTML, etc.) → treat as literal inline value

**Rationale**: The `then: "###255F11##"` branch of `BRAND_COLOR` normalizes to `"#255F11"` — a
CSS color literal, not a graph key. Since it fails both the SM_RULE_ and key-pattern checks, it
must be returned as-is. This matches the reference implementation in `samples/rule_engine.py`,
which returns the normalized result directly to its caller.

**Alternatives considered**: Always treating the result as a graph key and reporting MISSING for
literals. Rejected because it would misclassify valid inline content fragments as errors.

---

## 5. asyncpg Connection Pool — Module-Level Pattern

**Decision**: `shared/db.py` holds a module-level `Pool | None` singleton, initialized lazily by
`async def init_pool(dsn: str, ...)` and accessed by `def get_pool() -> asyncpg.Pool`. Callers
call `init_pool` once at agent startup.

**Rationale**: asyncpg pools are created with `await asyncpg.create_pool(dsn)` and must be
explicitly closed with `await pool.close()`. A module-level singleton avoids re-creating the pool
on every resolution call while keeping `shared/db.py` infrastructure-only (no business logic).

**Pattern**:
```python
import asyncpg
from asyncpg import Pool

_pool: Pool | None = None

async def init_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> Pool:
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    return _pool

def get_pool() -> Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized — call init_pool() first")
    return _pool

async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
```

Usage: `async with get_pool().acquire() as conn: ...`

**Alternatives considered**: Passing the pool as a parameter to every function — rejected because
the constitution designates `db.py` as the pool owner and callers should not construct it.
Context-variable pool — rejected (Principle VI — premature abstraction).

---

## 6. redis-py Async — Working Copy Hash Operations

**Decision**: Use `redis.asyncio.from_url(url)` to create a module-level Redis client. Hash key
is `working-copy:{template_name}:{session_id}`; field keys are canonical (uppercase) placeholder
keys.

**Pattern**:
```python
import redis.asyncio as aioredis
from redis.asyncio import Redis

_client: Redis | None = None

async def init_redis(url: str) -> Redis:
    global _client
    _client = await aioredis.from_url(url, decode_responses=True)
    return _client

def get_redis() -> Redis:
    if _client is None:
        raise RuntimeError("Redis client not initialized")
    return _client
```

**Working copy operations**:
```python
hash_key = f"working-copy:{template_name}:{session_id}"

await client.hget(hash_key, canonical_key)     # get one field
await client.hset(hash_key, canonical_key, value)  # set one field
await client.hdel(hash_key, canonical_key)     # delete one field
await client.hgetall(hash_key)                 # get all fields (dict)
```

**Unavailability handling**: Catch `redis.exceptions.ConnectionError` and
`redis.exceptions.TimeoutError` and raise `WorkingCopyUnavailableError` (typed exception from
`shared/resolution/resolver.py`). Per FR-005 and the spec clarification, silent fallback to
graph-only resolution is prohibited.

**Alternatives considered**: `redis.asyncio.StrictRedis` — functionally identical to `Redis`;
`from_url` is preferred for DSN-based configuration. Per-call client creation — rejected (pool
connection overhead).

---

## 7. Namespace / Key Normalization Algorithm

**Decision**: Two-step normalization before any lookup:

**Step 1 — Strip wrapper and uppercase**:
```
##KEY##    → KEY (uppercase)
##/KEY##   → KEY (strip leading /)
##//KEY##  → KEY (strip leading //)
##\KEY##   → KEY (strip leading \)
```
Result is the raw key string, uppercased.

**Step 2 — Namespace prefix expansion**:
- Split the raw key on `.` (first segment only)
- If the first segment exactly matches (case-insensitive) any key in the runtime context,
  replace that segment with the uppercased context value
- Example: raw key `LANG_LOCAL.PARAGRAPH_1`, context `{LANG_LOCAL: "en"}` → `EN.PARAGRAPH_1`
- Example: raw key `PARAM_CUST_BRAND.BRAND_LOGO`, context `{PARAM_CUST_BRAND: "skrill"}` → `SKRILL.BRAND_LOGO`
- If the first segment matches no context key, return the raw key unchanged (no error)
- If the matched context value is empty string, treat as missing (no prefix expansion, no silent substitution)

**Key stored in DB**: `field_key` values are already in expanded form (e.g., `AR.2FACTOR_AUTH_LINK`,
`BG.CC_VERIFY_DEBIT_HELP_TEXT`) — they are the resolved form with locale codes, not the template
variable names. The graph stores keys as-is from `content_block_kv.field_key` (already uppercase
in real data; normalized to uppercase at build time to be safe).

**Alternatives considered**: Full dot-segment scan — rejected (only the first segment is a
namespace prefix; inner dots are part of the key name).

---

## 8. Database Connection

**Decision**: Use `postgresql://postgres:postgres@localhost:5432/strongmail` — the single
database created by `docker-compose.yml`. This is the authoritative database for both
development and integration testing.

---

## 9. pyproject.toml Python Version

**Finding**: `pyproject.toml` specifies `requires-python = ">=3.14"`. The spec and constitution
require Python 3.11+. The `.python-version` file should be checked and `pyproject.toml` updated
to `requires-python = ">=3.11"` (or the appropriate installed version).

**Resolution**: Update `pyproject.toml` and verify the installed Python matches the spec.
