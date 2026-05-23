# Data Model: Placeholder Resolution Engine

*Phase 1 output — generated 2026-05-23*

---

## Runtime Types (Python Dataclasses & Enums)

These are the in-memory types the library creates, returns, and consumes. They have no ORM
backing; database rows are mapped to these types in pure Python.

---

### `RuntimeContext`

The set of parameters supplied at resolution time. Passed into every resolution call.

| Field | Type | Description |
|-------|------|-------------|
| `template_name` | `str` | Name of the template (matches `template.name` in PostgreSQL) |
| `locale` | `str` | Locale code, e.g. `"EN"`, `"AR"` — uppercased before use |
| `brand` | `str` | Brand identifier, e.g. `"SKRILL"`, `"NETELLER"` — uppercased before use |
| `session_id` | `str` | Session identifier for working-copy Redis key |

**Derived**: `context_map: dict[str, str]` — all four fields as `{LANG_LOCAL: locale, PARAM_CUST_BRAND: brand, ...}` made available for namespace prefix expansion. All keys and values are uppercased. Any additional runtime context keys can be passed by extending this map.

**Note**: `locale` and `brand` are uppercased internally. `LANG_LOCAL` and `PARAM_CUST_BRAND` are the canonical context key names, but all context keys participate in prefix expansion (FR-002).

---

### `ResolutionGraph`

An immutable mapping of canonical placeholder keys to their raw values. Returned by
`build_resolution_graph`; callers may cache it per session.

| Field | Type | Description |
|-------|------|-------------|
| (opaque) | `types.MappingProxyType[str, str]` | Canonical key → raw value. Keys are uppercased. Values are raw strings from `content_block_kv.field_value` — may contain `##PLACEHOLDER##` tokens. |

**Construction**: Built by `graph_builder.build_resolution_graph(pool, template_name)`.
Immutable after construction — no resolution call may modify it (Principle V).

**Source tables**: `template`, `template_content_block`, `content_block`,
`content_block_details`, `content_block_kv`.

**Ordering rule**: When multiple content blocks define the same `field_key`, the entry from the
content block with the lowest `content_block_details.id` wins (first content block by link order).
Duplicates are silently discarded.

---

### `ReasonCode` (enum)

Typed reason for an unresolvable placeholder. Defined in `shared/resolution/resolver.py`.

| Member | Value | Meaning |
|--------|-------|---------|
| `MISSING_KEY` | `"MISSING_KEY"` | Key not found in working copy or resolution graph |
| `CYCLE` | `"CYCLE"` | Circular reference detected (direct or indirect, or >10-hop SM_RULE chain) |
| `BROKEN_RULE_CHAIN` | `"BROKEN_RULE_CHAIN"` | SM_RULE branch target key is absent from the graph |
| `INVALID_RULE` | `"INVALID_RULE"` | SM_RULE AST has `valid: false` or AST is NULL |

---

### `UnresolvableEntry`

One entry in the unresolvable list. Returned by `resolve_body`, `resolve_key`, and
`scan_unresolvable`.

| Field | Type | Description |
|-------|------|-------------|
| `key` | `str` | Canonical (uppercase) placeholder key that could not be resolved |
| `reason` | `ReasonCode` | Typed reason code |
| `detail` | `str` | Human-readable context: full cycle path (e.g. `"A → B → A"`), missing branch target key, or error message |

---

### `ResolutionResult`

Returned by `resolve_body`. Contains exactly two fields (FR-008).

| Field | Type | Description |
|-------|------|-------------|
| `resolved_body` | `str` | Template body with all resolvable `##PLACEHOLDER##` tokens replaced |
| `unresolvable` | `list[UnresolvableEntry]` | All keys that could not be resolved, with typed reasons |

---

### `RuleAST` (read-only, internal)

The pre-parsed JSON structure read from `dynamic_content_details.rule_ast`. Not exposed as a
public type — the `sm_rule_evaluator` reads and evaluates it internally.

```python
# Logical structure (not a dataclass — deserialized from JSON at query time)
{
    "schema_version": int,          # always 1
    "kind": str,                    # always "strongmail_dynamic_content_rule"
    "valid": bool,                  # False → INVALID_RULE, do not evaluate
    "condition": {
        "combiner": str,            # "or" or "and"
        "clauses": [
            {
                "variable_expr": str,   # full dot-expression (informational)
                "variable_key": str,    # uppercased last dot-segment — lookup key in context
                "operator": str,        # natural-language operator (see below)
                "value": str            # comparison value or list like "(A, B, C)"
            }
        ]
    },
    "then": str,                    # branch result if condition is true
    "else": str | None              # branch result if condition is false; may be null
}
```

**Supported operators** (case-insensitive): `"is equal to"`, `"is not equal to"`,
`"contains"`, `"does not contain"`, `"is greater than"`, `"is greater than or equal to"`,
`"is less than"`, `"is less than or equal to"`, `"is null"`, `"is not null"`,
`"is one of"`, `"is not one of"`.

---

## Database Tables (Read-Only Reference)

The library reads from the following tables. It never writes to PostgreSQL.

### `template`
| Column | Type | Used |
|--------|------|------|
| `id` | `text` | PK — used to join `template_content_block` |
| `name` | `text` | Lookup key for graph building (`WHERE name = $1`) |

### `template_content_block`
| Column | Type | Used |
|--------|------|------|
| `template_id` | `text` | FK → `template.id` |
| `content_block_id` | `text` | FK → `content_block.id` |

### `content_block`
| Column | Type | Used |
|--------|------|------|
| `id` | `text` | PK — join key |

### `content_block_details`
| Column | Type | Used |
|--------|------|------|
| `id` | `bigint` | PK — ordering key for duplicate resolution (lower = higher priority) |
| `content_block_id` | `text` | FK → `content_block.id` |

### `content_block_kv`
| Column | Type | Used |
|--------|------|------|
| `content_block_details_id` | `bigint` | FK → `content_block_details.id` |
| `field_key` | `text` | Canonical placeholder key (already in expanded, uppercase form in DB) |
| `field_value` | `text` | Raw value; may contain `##PLACEHOLDER##` tokens |

### `dynamic_content`
| Column | Type | Used |
|--------|------|------|
| `id` | `text` | PK — joined to `dynamic_content_details` |
| `name` | `text` | Rule name WITHOUT `SM_RULE_` prefix in most rows (strip before querying) |

### `dynamic_content_details`
| Column | Type | Used |
|--------|------|------|
| `dynamic_content_id` | `text` | FK → `dynamic_content.id` |
| `rule_ast` | `json` | Pre-parsed rule AST; evaluated by `sm_rule_evaluator` |
| `rule_text` | `text` | Raw rule DSL text — NOT used by this library (AST is authoritative) |

---

## Redis Key Structure

| Key pattern | Type | Description |
|-------------|------|-------------|
| `working-copy:{template_name}:{session_id}` | Hash | Per-session overrides. Fields are canonical (uppercase) placeholder keys; values are the override strings. |

Working copy operations: `HGET` (read one), `HSET` (write one), `HDEL` (delete one),
`HGETALL` (read all for bulk pre-fetch).

---

## State Transitions

```
Resolution pipeline per placeholder token:

             ┌─── strip wrapper → uppercase canonical key
             │
             ├─── namespace prefix expansion (context keys)
             │
             ├─── working copy check (Redis HGET)
             │      ├── HIT  → use override value → recursive expand
             │      └── MISS → continue
             │         (ERROR if Redis unavailable → WorkingCopyUnavailableError)
             │
             ├─── graph lookup (MappingProxyType)
             │      ├── HIT  → use raw value → recursive expand
             │      └── MISS → check if SM_RULE_
             │
             ├─── SM_RULE_ evaluation (dynamic_content_details.rule_ast)
             │      ├── valid AST → evaluate condition → normalize branch result
             │      │      ├── starts with SM_RULE_ → chain (max 10 hops)
             │      │      ├── key-like pattern     → graph lookup
             │      │      └── literal              → return as-is
             │      ├── invalid AST (valid: false or NULL) → INVALID_RULE
             │      └── rule name not found in DB   → MISSING_KEY
             │
             └─── not found anywhere → MISSING_KEY

Cycle detection: maintain `visiting: set[str]` per resolution call.
Re-entering a key already in `visiting` → CYCLE (CycleDetectedException with full path).
SM_RULE hop counter > 10 → CYCLE.
```
