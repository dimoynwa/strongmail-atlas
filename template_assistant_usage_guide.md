# Template Assistant — Usage Guide

> **Location**: `template_assistant/`  
> **Framework**: Google ADK (Python)  
> **Spec**: `.specify/specs/002-template-assistant/spec.md`

---

## Overview

The Template Assistant is a conversational Google ADK agent that lets email template
authors work with a single StrongMail template within a session. It can answer
questions about resolved content, show a full HTML preview, evaluate emotional tone
using GoEmotions, suggest and apply tone rewrites, and undo those changes — all
through natural language without opening the StrongMail editor.

The agent never writes to PostgreSQL. All session edits are stored in Redis only and
are scoped to the current session. Changes do not persist when the session ends.

---

## Architecture

```
TemplateAssistantAgent (root)
├── ResolutionSubagent       — read resolved content, preview, unresolvable scan
├── WorkingCopySubagent      — read/write/reset Redis working copy
├── ToneEvaluationSubagent   — GoEmotions scoring on current resolved state
└── ToneSuggestionSubagent   — suggest rewrites, apply, undo via snapshot
```

The root agent routes user intent to the correct subagent. Subagents never
communicate with each other through ADK routing — shared logic is imported
directly from `template_assistant/ml/` and `template_assistant/utils/`.

---

## Prerequisites

### 1. System dependencies

- Python 3.11+
- PostgreSQL running at `postgresql://postgres:postgres@localhost:5434/strongmail_tov`
- Redis running on `localhost:6379` (default port)

### 2. Install Python dependencies

```bash
pip install google-adk asyncpg redis transformers trafilatura
```

### 3. Pre-download the GoEmotions model

The GoEmotions classifier (~500 MB) must be downloaded before the agent starts.
Run this once:

```bash
python -c "
from transformers import pipeline
pipeline('text-classification', model='SamLowe/roberta-base-go_emotions', top_k=None)
print('Model ready.')
"
```

The model is cached by Hugging Face locally after the first download. Subsequent
agent startups load from cache with no network call required.

---

## Session Context

The agent requires four values injected into the ADK session state before the
first user message. These come from your external auth or navigation layer —
the user never provides them manually.

| Field | Type | Example | Description |
|---|---|---|---|
| `template_name` | `str` | `"password_reset"` | Internal StrongMail template name |
| `lang_local` | `str` | `"EN"` | Language locale — always uppercase |
| `param_cust_brand` | `str` | `"SKRILL"` | Brand identifier — always uppercase |
| `session_id` | `str` | `"adk-session-abc123"` | ADK session ID — set by the runtime |

If any of these four fields are missing, the agent refuses all requests until
they are present.

### Injecting context programmatically

```python
from google.adk.sessions import InMemorySessionService

session_service = InMemorySessionService()
session = await session_service.create_session(
    app_name="template_assistant",
    user_id="user-123",
    session_id="adk-session-abc123",
    state={
        "template_name": "password_reset",
        "lang_local": "EN",
        "param_cust_brand": "SKRILL",
        "session_id": "adk-session-abc123",
    },
)
```

---

## Running the Agent

### ADK web UI (development)

```bash
cd strongmail-agents
adk web
```

Open `http://localhost:8000` in your browser. Select `template_assistant` from
the agent list. The session context must be injected before you start chatting —
see [Injecting context programmatically](#injecting-context-programmatically) above
or use the Streamlit UI described in the next section.

### ADK CLI (single turn)

```bash
adk run template_assistant --session-state '{"template_name":"password_reset","lang_local":"EN","param_cust_brand":"SKRILL","session_id":"test-001"}'
```

### Streamlit UI (future)

A Streamlit frontend will provide template navigation and automatic context injection.
Until it is available, use the ADK web UI with manual context injection.

---

## What the Agent Can Do

### Query resolved content

Ask about any part of the template in natural language. The agent resolves
placeholder tokens — including any edits you have made in this session — before
answering.

```
What does the main paragraph say?
What is the current value of EN.CTA_BUTTON_TEXT?
Show me the subject line.
```

### Preview the full template

```
Show me the full HTML preview of this template.
```

Returns the complete resolved HTML body as a code block. Any placeholders that
could not be resolved are listed alongside the preview.

### Find unresolvable placeholders

```
Which placeholders in this template cannot be resolved?
```

Returns a structured list of unresolvable keys, each with a reason:

| Reason | Meaning |
|---|---|
| `MISSING` | Key not found in content blocks, working copy, or context parameters |
| `CYCLE` | Key's value references itself directly or indirectly |
| `BROKEN_RULE` | `SM_RULE_*` DSL evaluated but the branch pointed to a missing key |

### Evaluate emotional tone

```
Evaluate the tone of this template.
What emotions does this template convey?
How has the tone changed since I started editing?
```

Always runs a fresh GoEmotions evaluation against the current resolved state —
including any working copy edits. Returns confidence scores for all 28 GoEmotions
labels. The top 5 are highlighted; ask for the full breakdown if needed.

The GoEmotions model is deterministic. The same resolved text always produces the
same scores. If you ask for evaluation twice without making any changes, the scores
will be identical.

### Suggest and apply tone rewrites

```
Make this template feel more reassuring and less urgent.
Make the tone warmer.
Make this more professional.
Suggest tone improvements.
```

The agent maps your intent to a target GoEmotions emotion profile, identifies
placeholder keys whose values contain natural language text eligible for rewriting,
generates rewrites using the LLM with full template context for coherence, and
applies them to your session working copy immediately.

**Keys excluded from rewriting** (structural values):
- Keys ending in `_URL`, `_COLOR`, or `_ID`
- Values that start with `http`
- Values shorter than 20 characters

After suggestions are applied, the agent shows you a before/after diff for every
changed key. If no eligible keys are found, the agent tells you so clearly.

### Undo tone suggestions

```
Undo the tone changes you just made.
Undo only the changes to EN.PARAGRAPH_1.
Undo changes to EN.PARAGRAPH_1 and EN.CLOSING_LINE.
```

Restores affected placeholder keys to the values they had immediately before the
most recent tone suggestion batch. If you had manually edited a key before asking
for tone suggestions, undo restores your manual edit — not the original database
value.

Undo only covers the **most recent** suggestion batch. If you apply two batches,
undo restores to the state before the second batch only.

### Review your changes

```
What changes have I made so far?
Show me my working copy.
```

Lists all placeholder keys you have overridden in this session, with their current
overridden values.

### Reset changes

```
Reset EN.PARAGRAPH_1 back to its original value.
Reset all my changes.
Start over.
```

Clears one key or the entire working copy from Redis. Resets to the original
database values. This cannot be undone — use the undo tools for reversible
operations.

---

## Redis Working Copy

All edits made during a session are stored in Redis, never in PostgreSQL.

| Key | Type | Purpose |
|---|---|---|
| `working-copy:{template_name}:{session_id}` | Hash | Current session overrides |
| `working-copy-snapshot:{template_name}:{session_id}` | Hash | Pre-suggestion snapshot for undo |

Each field in the working copy hash is a canonical uppercase placeholder key
(e.g. `EN.PARAGRAPH_1`) and its value is the overridden string for this session.

When the session ends, the working copy is not automatically cleared. Your
infrastructure layer is responsible for TTL management or explicit cleanup.

---

## Shared Resolution Library

The agent delegates all placeholder resolution to the shared library at
`shared/resolution/`. It does not reimplement any resolution logic.

Resolution lookup priority (first hit wins):

1. **Redis working copy** — `working-copy:{template_name}:{session_id}`
2. **Resolution graph** — built from `content_block_kv` via `template_content_block`
3. **Context parameters** — `lang_local`, `param_cust_brand`, `session_id`, etc.

For `SM_RULE_*` keys, the DSL in `dynamic_content_details.rule_text` is evaluated
against the runtime context before lookup continues.

---

## Tone Profiles

Natural language tone intents are mapped to GoEmotions label weights in
`template_assistant/tone_profiles.py`. Built-in profiles:

| Intent | Target emotions |
|---|---|
| `"more reassuring"` | High `relief`, high `caring`, low `fear`, low `nervousness` |
| `"more urgent"` | High `desire`, high `nervousness` |
| `"warmer"` | High `joy`, high `love`, high `gratitude` |
| `"more professional"` | High `approval`, low `amusement`, low `excitement` |
| `"more encouraging"` | High `admiration`, high `optimism`, high `joy` |

For intents not in this table, the agent derives a target profile using LLM
reasoning anchored to the nearest known profile. To add new profiles, edit
`tone_profiles.py` — no other files need to change.

---

## Running Tests

```bash
# All tests
pytest template_assistant/tests/ -v

# Per subagent
pytest template_assistant/tests/test_resolution_subagent.py -v
pytest template_assistant/tests/test_working_copy_subagent.py -v
pytest template_assistant/tests/test_tone_evaluation_subagent.py -v
pytest template_assistant/tests/test_tone_suggestion_subagent.py -v

# End-to-end multi-turn conversation
pytest template_assistant/tests/test_e2e_agent.py -v

# Foundational modules
pytest template_assistant/tests/test_context.py -v
pytest template_assistant/tests/test_tone_profiles.py -v
pytest template_assistant/tests/test_utils_text.py -v
pytest template_assistant/tests/test_ml_goemotions.py -v
```

Tests connect to real PostgreSQL and Redis instances. No mocks. Ensure both
services are running before executing the test suite.

---

## Test Queries

Use these queries to validate agent behaviour end-to-end after deployment.
Run them in order — later queries depend on state built by earlier ones.

| # | Query | What it validates |
|---|---|---|
| 1 | *(open conversation)* | Agent announces template, locale, brand proactively |
| 2 | `What does EN.PARAGRAPH_1 say?` | Single key resolution via `ResolutionSubagent` |
| 3 | `Show me the full HTML preview of this template.` | Full resolution + unresolvable list |
| 4 | `Which placeholders cannot be resolved?` | Unresolvable scanner with reason codes |
| 5 | `Evaluate the emotional tone of this template.` | GoEmotions pipeline end-to-end |
| 6 | `Make this template feel more reassuring and less urgent.` | Full suggestion + apply + Redis write |
| 7 | `What changes have I made so far?` | Working copy read after tone suggestions |
| 8 | `Undo only the changes to EN.PARAGRAPH_1.` | Selective snapshot restore |
| 9 | `Make this template feel more exciting.` *(on structural-only template)* | No eligible keys edge case |
| 10 | `Reset all my changes.` | Full working copy clear + count confirmation |

---

## Known Constraints

- **Session-scoped only.** Changes do not persist across sessions. The Streamlit UI
  will eventually provide a "commit" workflow — this is not yet implemented.
- **Single template per session.** The agent cannot search across templates or switch
  templates mid-conversation. Use the General Agent for discovery, then navigate to
  the Template Assistant for a specific template.
- **Undo covers one batch.** Only the most recent tone suggestion batch can be undone.
  Multiple undo levels are not supported in this version.
- **GoEmotions is English-optimised.** Tone evaluation accuracy may be lower for
  non-English template content even when `lang_local` is set to a non-English locale.
- **No automatic tone re-evaluation.** The agent evaluates tone only when explicitly
  asked. It does not re-evaluate automatically after applying suggestions.

---

## File Reference

```
template_assistant/
├── __init__.py
├── agent.py                          # Root TemplateAssistantAgent
├── context.py                        # SessionContext, SessionContextMissingError
├── tone_profiles.py                  # Intent → GoEmotions weight mapping
├── ml/
│   ├── __init__.py
│   └── goemotions.py                 # get_classifier() singleton
├── utils/
│   ├── __init__.py
│   └── text.py                       # extract_plain_text() via trafilatura
├── subagents/
│   ├── __init__.py
│   ├── resolution_subagent.py        # ResolutionSubagent + tools
│   ├── working_copy_subagent.py      # WorkingCopySubagent + tools
│   ├── tone_evaluation_subagent.py   # ToneEvaluationSubagent + tools
│   └── tone_suggestion_subagent.py   # ToneSuggestionSubagent + tools
└── tests/
    ├── __init__.py
    ├── test_agent.py
    ├── test_context.py
    ├── test_tone_profiles.py
    ├── test_ml_goemotions.py
    ├── test_utils_text.py
    ├── test_resolution_subagent.py
    ├── test_working_copy_subagent.py
    ├── test_tone_evaluation_subagent.py
    ├── test_tone_suggestion_subagent.py
    └── test_e2e_agent.py
```

---

## Related

- `shared/resolution/` — placeholder resolution engine (Spec 001)
- `general_agent/` — cross-template discovery agent (Spec 003)
- `.specify/specs/002-template-assistant/` — full specification, plan, and tasks
- `.specify/memory/constitution.md` — project-wide architectural constraints