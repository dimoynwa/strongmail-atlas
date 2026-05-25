# Phase 0: Research & Decisions

## Overview
The technical stack and architecture for the Template Assistant Agent were explicitly provided in the feature specification and planning input. No unknowns or `NEEDS CLARIFICATION` items were identified that required external research.

## Technical Decisions

### Framework & Architecture
- **Decision**: Google ADK (Python) with a true multi-agent architecture.
- **Rationale**: The root agent orchestrates four distinct subagents (`ResolutionSubagent`, `WorkingCopySubagent`, `ToneEvaluationSubagent`, `ToneSuggestionSubagent`) using `sub_agents=[]`. `AgentTool` is explicitly forbidden to maintain orchestration transparency.

### State & Storage
- **Decision**: PostgreSQL for read-only template data; Redis for session-scoped working copies.
- **Rationale**: PostgreSQL contains the permanent `template_details` and `template_tone_evaluations`. The agent must never write to PostgreSQL. Redis is used for fast, temporary storage of user edits (`working-copy:{template_name}:{session_id}`) and undo snapshots (`working-copy-snapshot:{template_name}:{session_id}`).

### Tone Evaluation Model
- **Decision**: `SamLowe/roberta-base-go_emotions` via `transformers` pipeline.
- **Rationale**: Provides a comprehensive 28-label emotion profile. 
- **Singleton Strategy**: The model is loaded once at the module level inside a dedicated `template_assistant/tone_model.py` module. Both `ToneEvaluationSubagent` and `ToneSuggestionSubagent` import the pipeline from this shared module to ensure the model is only loaded into memory once across the entire agent runtime. `trafilatura` is used to cleanly extract text from HTML before evaluation.

### Tone Suggestion Generation
- **Decision**: ADK's underlying LLM (Gemini).
- **Rationale**: Receives the target emotion profile, current resolved values, and context to generate rewrites. 
- **LLM Prompting**: Each eligible key's current value is passed to the LLM along with: (1) the target emotion profile as label→weight dict, (2) the surrounding resolved template context for coherence. The LLM is strictly instructed to return only the rewritten value — not the key name, not explanation, not markdown.
- **Tone Profiles**: A static mapping dict lives in `template_assistant/tone_profiles.py`. Keys are canonical intent phrases, values are `dict[emotion_label, float]` target weights. The LLM may supplement this for unmapped intents but must use the static map as anchors.

### Testing Strategy
- **Decision**: `pytest` + `pytest-asyncio` with real PostgreSQL and Redis.
- **Rationale**: Unit tests inject `session_state` directly into tools without booting the full ADK runtime. A separate E2E test validates the full multi-turn conversational flow.