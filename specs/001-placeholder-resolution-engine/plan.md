# Implementation Plan: Placeholder Resolution Engine

**Branch**: `001-placeholder-resolution-engine` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-placeholder-resolution-engine/spec.md`

## Summary

Build `shared/resolution/` — a pure async Python library that resolves `##PLACEHOLDER##` tokens
in StrongMail email template bodies. The library queries PostgreSQL via asyncpg to build an
immutable resolution graph (canonical key → raw value from `content_block_kv`), checks Redis for
per-session working-copy overrides before every lookup, evaluates `SM_RULE_*` conditional content
rules against the runtime context, and recursively expands nested placeholders with cycle
detection. Results are returned as a `ResolutionResult` dataclass carrying the fully resolved
string and a structured list of all unresolvable entries with typed reason codes.

## Technical Context

**Language/Version**: Python 3.11+ (pyproject.toml currently specifies `>=3.14` — update to `>=3.11`)

**Primary Dependencies**:
- `asyncpg` — async PostgreSQL driver (raw parameterized SQL, no ORM)
- `redis[asyncio]` — redis-py async client (`redis.asyncio`)
- `pytest`, `pytest-asyncio` — test stack only

**Storage**:
- PostgreSQL (read-only) via asyncpg connection pool — source of truth for templates, content
  blocks (`content_block_kv`), and SM_RULE ASTs (`dynamic_content_details.rule_ast`)
- Redis (read/write) via `redis.asyncio` — per-session working-copy overrides stored as a Redis
  hash under key `working-copy:{template_name}:{session_id}`; fields are canonical placeholder keys

**Testing**: `pytest` + `pytest-asyncio`; real PostgreSQL at
`postgresql://postgres:postgres@localhost:5432/strongmail`; real Redis; no mocks

**Target Platform**: Linux server (library imported by ADK agents; no web framework, no CLI)

**Project Type**: Python library (`shared/` package)

**Performance Goals**: Full-body resolution of a 200-placeholder template in ≤500 ms

**Constraints**:
- No ORM; raw asyncpg parameterized SQL only
- No web framework inside `shared/`
- Resolution graph is immutable after construction (`types.MappingProxyType`)
- Library does not cache graphs — caller caches per session
- Redis unavailability raises `WorkingCopyUnavailableError`; no silent fallback to graph-only

**Scale/Scope**: Largest templates have ~8,400 distinct KV pairs; bodies contain up to 200
`##PLACEHOLDER##` tokens; SM_RULE chains are capped at 10 hops

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Multi-Agent Architecture & State Isolation | ✅ PASS | Library lives under `shared/` — not an ADK agent. No direct cross-agent state. PostgreSQL read-only. Redis write-only. |
| II. Data Access — PostgreSQL Read-Only, Redis Write-Only | ✅ PASS | asyncpg + raw parameterized SQL. No ORM. No INSERT/UPDATE/DELETE. Working copy exclusively through Redis hash. |
| III. Async-First with Code Quality Standards | ✅ PASS | All I/O async (asyncpg pool + redis.asyncio). Type hints and docstrings required on all public functions. Typed exceptions or structured returns — no silent swallowing. |
| IV. Test-First with Real Infrastructure (NON-NEGOTIABLE) | ✅ PASS | pytest + pytest-asyncio against real PostgreSQL + Redis. No mocking. TDD cycle enforced for every public function. |
| V. Resolution Integrity & Immutability | ✅ PASS | Fresh implementation (no legacy code reuse). `MappingProxyType` graph. Resolution priority: Redis > graph. `CycleDetectedException` on cycles. `ResolutionResult` always returned. |
| VI. Simplicity First | ✅ PASS | Flat module structure; no base classes, mixins, or generic factories. Each module has a single named responsibility. No feature flags or backwards-compat shims. |

**Post-design re-check**: Checked after Phase 1 design — no new violations introduced by the
module structure or interface contracts.

## Project Structure

### Documentation (this feature)

```text
specs/001-placeholder-resolution-engine/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output (/speckit-plan)
├── data-model.md        # Phase 1 output (/speckit-plan)
├── contracts/           # Phase 1 output (/speckit-plan)
│   └── resolution_api.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
shared/
├── __init__.py
├── db.py                    ← asyncpg pool factory (create_pool, get_pool, close_pool)
├── redis_client.py          ← working-copy HGET / HSET / HDEL / HGETALL helpers
└── resolution/
    ├── __init__.py          ← re-exports public API (see contracts/resolution_api.md)
    ├── namespace.py         ← normalize_key(), expand_namespace_prefix()
    ├── graph_builder.py     ← build_resolution_graph(pool, template_name) → MappingProxyType
    ├── sm_rule_evaluator.py ← evaluate_sm_rule(pool, rule_name, context) → str
    └── resolver.py          ← resolve_body(), resolve_key(), scan_unresolvable()

tests/
└── integration/
    ├── conftest.py          ← pool + Redis client fixtures (scope=session)
    ├── test_graph_builder.py
    ├── test_namespace.py
    ├── test_sm_rule_evaluator.py
    └── test_resolver.py
```

**Structure Decision**: Single project. `shared/` lives at the repo root alongside `main.py`.
Tests live under `tests/integration/` — no unit or contract subdirectory because the real-infra
integration tests are the only permitted test layer (Principle IV).

## Complexity Tracking

> *(No constitution violations — table omitted)*
