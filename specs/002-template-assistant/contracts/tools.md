# Subagent Tool Contracts

These define the internal tools exposed by the subagents to the ADK routing layer. All tools accept the ADK `session_state` dict.

## ResolutionSubagent

```python
async def get_template_structure(session_state: dict) -> dict:
    """Returns list of placeholder keys found in the template bodies, grouped by HTML and text."""

async def resolve_key(key: str, session_state: dict) -> dict:
    """Resolves a single placeholder key using the shared resolution library."""

async def resolve_full_template(session_state: dict) -> str:
    """Resolves the complete HTML body using shared.resolution.resolver.resolve_template."""

async def list_unresolvable_placeholders(session_state: dict) -> dict:
    """Runs the unresolvable scanner from the shared library and returns a structured report."""
```

## WorkingCopySubagent

```python
async def get_working_copy(session_state: dict) -> dict[str, str]:
    """Reads all fields from the Redis working copy hash."""

async def set_working_copy_value(key: str, value: str, session_state: dict) -> bool:
    """Writes a single canonical key override to the Redis hash."""

async def reset_working_copy_key(key: str, session_state: dict) -> bool:
    """Deletes a specific key from the Redis hash."""

async def reset_full_working_copy(session_state: dict) -> bool:
    """Deletes the entire Redis hash for this session."""
```

## ToneEvaluationSubagent

```python
async def evaluate_tone(session_state: dict) -> dict[str, float]:
    """Resolves template, strips HTML via trafilatura, runs GoEmotions, returns emotion scores."""

async def get_stored_tone_scores(session_state: dict) -> dict[str, float]:
    """Reads historical scores from template_tone_evaluations."""

async def compare_tone(session_state: dict) -> dict[str, float]:
    """Runs fresh evaluation then diffs against stored scores."""
```

## ToneSuggestionSubagent

```python
async def suggest_tone_rewrites(target_intent: str, session_state: dict) -> list[dict]:
    """Generates rewrites for eligible keys to match target intent."""

async def apply_tone_suggestions(suggestions: list[dict], session_state: dict) -> bool:
    """Snapshots affected keys, then writes suggestions to Redis working copy."""

async def undo_tone_suggestions(keys: list[str] | None, session_state: dict) -> bool:
    """Resets specified keys (or all recently changed keys) in Redis to pre-suggestion snapshot values."""
```