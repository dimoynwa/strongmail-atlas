# Implementation Plan: Google ADK General Agent

**Branch**: `010-google-adk-general-agent` | **Date**: May 27, 2026 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-google-adk-general-agent/spec.md`

## Summary

Build a stateless Google ADK conversational agent (General Agent) to answer discovery and audit questions across the StrongMail template catalogue. It delegates to four specialized subagents (Semantic Search, Keyword Search, Structural Query, Tone Discovery) using a read-only architecture, pgvector cosine similarity over `template_details.summary_embeded`, and pre-computed data.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Google ADK, `sentence-transformers`, `pgvector`

**Storage**: PostgreSQL (read-only access). No Redis.

**Testing**: `pytest`, `pytest-asyncio` with real PostgreSQL (no mocks).

**Target Platform**: Backend Service

**Project Type**: Conversational Agent / Library

**Performance Goals**: Sub-second retrieval for semantic and keyword searches.

**Constraints**: Strictly read-only, stateless (no session context), maximum 50 results per query.

**Scale/Scope**: Entire StrongMail template catalogue.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Library-First**: Yes, built as a reusable agent module.
- **Test-First**: Yes, requires integration tests for tools and end-to-end fan-out tests.
- **Statelessness**: Yes, explicitly designed with no session context or Redis dependency.
- **Read-Only**: Yes, strictly enforced across all subagents.

## Project Structure

### Documentation (this feature)

```text
specs/010-google-adk-general-agent/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
general_agent/
├── agent.py                                 # Root GeneralAgent
├── ml/
│   └── embeddings.py                        # Encoder singleton (lazy-load get_encoder, encode_query)
└── subagents/
    ├── semantic_search_subagent.py          # SemanticSearchSubagent
    ├── keyword_search_subagent.py           # KeywordSearchSubagent
    ├── structural_query_subagent.py         # StructuralQuerySubagent
    └── tone_discovery_subagent.py           # ToneDiscoverySubagent

shared/
└── embeddings.py                            # Low-level pgvector query helpers

tests/
└── general_agent/
    ├── integration/                         # Integration tests for tools
    └── e2e/                                 # End-to-end fan-out tests
```

**Structure Decision**: A dedicated `general_agent` package containing the root agent, its subagents, and the ML embeddings singleton, with shared database helpers in the `shared` package.

## Design Notes

### ToneDiscoverySubagent
- Reads from the `template_tone_evaluations` table only.
- Never loads or calls the GoEmotions classifier at query time.
- Tone scores are pre-computed by the offline pipeline; the agent is a consumer only.

## Tool Signatures

The following tool signatures must be implemented exactly as specified. All search and discovery tools accept a `limit` parameter (default 10, max 50).

### SemanticSearchSubagent
```python
def semantic_search_templates(query: str, limit: int = 10) -> list[TemplateSearchResult]:
    ...
```

### KeywordSearchSubagent
```python
def keyword_search_templates(query: str, fields: list[str] = ["name", "subject", "summary"], limit: int = 10) -> list[TemplateSearchResult]:
    ...
```

### StructuralQuerySubagent
```python
def find_templates_by_content_block(content_block_id: str, limit: int = 10) -> list[TemplateSearchResult]:
    ...

def find_templates_by_dynamic_content_rule(rule_id: str, limit: int = 10) -> list[TemplateSearchResult]:
    ...

def get_template_resolution_health(template_name: str) -> ResolutionHealthResult:
    ...

def get_template_structure_summary(template_name: str) -> StructuralSummary:
    ...
```

### ToneDiscoverySubagent
```python
def find_templates_by_tone(emotion: str, min_score: float = 0.5, lang_local: str = "EN", param_cust_brand: str = "SKRILL", limit: int = 10) -> list[ToneDiscoveryResult]:
    ...

def rank_templates_by_emotion(emotion: str, lang_local: str = "EN", param_cust_brand: str = "SKRILL", limit: int = 10) -> list[ToneDiscoveryResult]:
    ...
```

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
