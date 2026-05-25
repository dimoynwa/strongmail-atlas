# Implementation Plan: Template Assistant

**Branch**: `002-template-assistant` | **Date**: 2026-05-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-template-assistant/spec.md`

## Summary

Build a Google ADK conversational agent (Template Assistant) that allows users to query, preview, edit, and improve the emotional tone of a StrongMail email template within a single session. The agent uses a multi-agent architecture with four subagents (Resolution, WorkingCopy, ToneEvaluation, ToneSuggestion) and relies on an existing shared resolution engine, Redis for session-scoped working copies, and a local GoEmotions model for tone evaluation.

## Technical Context

**Language/Version**: Python (async)

**Primary Dependencies**: `google-adk`, `transformers` (for GoEmotions), `trafilatura` (for HTML stripping), `asyncpg` (for DB), `redis-py` (for working copy)

**Storage**: 
- PostgreSQL (Read-only via `shared.db.get_pool()`)
- Redis (Read/Write via `shared.redis_client.get_redis()`)

**Testing**: `pytest` + `pytest-asyncio`

**Target Platform**: Backend Service / Agent Runtime

**Project Type**: ADK Conversational Agent

**Performance Goals**: Fast tone evaluation (model loaded once at startup as module-level singleton), efficient resolution using shared library.

**Constraints**: 
- Must use true subagents (`sub_agents=[]`), no `AgentTool`.
- Must never write to PostgreSQL.
- Must validate `session_id`, `template_name`, `lang_local`, `param_cust_brand` in `SessionContext` before processing.

**Scale/Scope**: Single conversational session scoped to a single template.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Pass**: Uses existing shared libraries (`shared.resolution`).
- **Pass**: Clear subagent boundaries and responsibilities.
- **Pass**: Test-first approach supported via `pytest` with injected `session_state`.

## Project Structure

### Documentation (this feature)

```text
specs/002-template-assistant/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (to be generated)
```

### Source Code (repository root)

```text
template_assistant/
├── __init__.py
├── agent.py                     # Root TemplateAssistantAgent definition
├── context.py                   # SessionContext dataclass, validation logic
├── tone_model.py                # GoEmotions singleton pipeline
├── tone_profiles.py             # Static intent->emotion mapping dict
├── subagents/
│   ├── __init__.py
│   ├── resolution_subagent.py   # ResolutionSubagent + its tools
│   ├── working_copy_subagent.py # WorkingCopySubagent + its tools
│   ├── tone_evaluation_subagent.py # ToneEvaluationSubagent + its tools
│   └── tone_suggestion_subagent.py # ToneSuggestionSubagent + its tools
└── tests/
    ├── test_resolution_subagent.py
    ├── test_working_copy_subagent.py
    ├── test_tone_evaluation_subagent.py
    ├── test_tone_suggestion_subagent.py
    └── test_e2e_agent.py        # End-to-end multi-turn conversation test
```

**Structure Decision**: A dedicated `template_assistant` package containing the root agent, context definitions, and a `subagents` module for the four distinct subagents. Tests are co-located in a `tests` directory.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Complexity is justified by the multi-agent orchestration requirements.