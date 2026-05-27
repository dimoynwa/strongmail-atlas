# Implementation Plan: Tone Suggestion Validation

**Branch**: `003-tone-suggestion-validation` | **Date**: May 25, 2026 | **Spec**: [specs/003-tone-suggestion-validation/spec.md](spec.md)

**Input**: Feature specification from `/specs/003-tone-suggestion-validation/spec.md`

## Summary

Patch the ToneSuggestionSubagent to prevent hallucinated placeholder keys from being written to the Redis working copy. This involves adding strict eligibility filtering before prompting the LLM, validating the LLM response against the eligible set, and enforcing an atomic graph validation check before writing to Redis.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: `pydantic`, `redis`, `asyncio`, LLM client

**Storage**: Redis (working copy), PostgreSQL (resolution graph)

**Testing**: `pytest`, `pytest-asyncio` (real DB and Redis, no mocks). For tests covering LLM response validation in `suggest_tone_rewrite`, inject a stub that returns a pre-constructed JSON string. This isolates validation logic from LLM output quality. DB and Redis remain real in all tests.

**Target Platform**: Linux/Docker

**Project Type**: Backend AI Agent / Subagent

**Performance Goals**: N/A (Standard subagent execution time)

**Constraints**: Must not modify `shared/resolution/` or other subagents. Must reuse `build_graph()` and `KeyNotInGraphError`.

**Scale/Scope**: Targeted patch to two existing tools in `tone_suggestion_subagent.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Clear purpose: Targeted bug fix / validation enhancement.
- [x] Test-First: New test file `test_tone_suggestion_key_validation.py` required.
- [x] Integration Testing: Real DB and Redis used for tests.
- [x] Simplicity: Reusing existing error classes and graph building logic.

## Project Structure

### Documentation (this feature)

```text
specs/003-tone-suggestion-validation/
├── plan.md              # This file
├── data-model.md        # Phase 1 output
└── tasks.md             # Phase 2 output (to be generated)
```

### Source Code (repository root)

```text
template_assistant/
├── subagents/
│   └── tone_suggestion_subagent.py
└── tests/
    └── test_tone_suggestion_key_validation.py
```

**Structure Decision**: Modifying an existing subagent file and adding a new dedicated test file for the validation logic.

## Phases

- **Phase 0** — Data model additions (`EligibilityResult`, `DiscardedSuggestion` in `data-model.md`)
- **Phase 1** — `is_eligible_for_rewrite` helper (module-level in `tone_suggestion_subagent.py`, tested independently). Must implement prefix filter, `SM_RULE_*` exclusion, URL exclusion, colour code exclusion, numeric exclusion, and length exclusion. Must use working copy value if present, else graph raw value.
- **Phase 2** — `suggest_tone_rewrite` changes (eligible set derivation from graph + working copy, LLM prompt, response validation). Return schema must include `discarded_keys`.
- **Phase 3** — `apply_tone_suggestions` changes (atomic all-or-nothing graph validation gate: validate all first, write all or write none).
- **Phase 4** — Integration tests (partial write prevention: one invalid key → no keys written, end-to-end apply with valid keys). LLM stub is scoped to validation tests only; DB and Redis remain real.

