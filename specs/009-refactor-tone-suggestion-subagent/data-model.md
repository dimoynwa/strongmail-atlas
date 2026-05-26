# Data Model: Refactor Tone Suggestion Subagent

## Constants

### `SNAPSHOT_NONE_SENTINEL`

```python
SNAPSHOT_NONE_SENTINEL: str = "__NONE__"
```

A sentinel string stored in the Redis snapshot hash when a key existed in the
resolution graph at snapshot time but had no working copy override. Distinguishes
"key had no override — delete from working copy on undo" from "key had an empty
string override — restore empty string on undo". Defined in `services.py` and
imported by `tone_suggestion_subagent.py`. Unchanged by this refactor.

---

## Dataclasses

### `Suggestion` (session state dict shape)

Suggestions written to `session.state["suggestions"]` by `finalize_rewrites` are
plain dicts, not dataclass instances. Each dict has the following shape:

```python
{
    "key":           str,   # canonical placeholder key, e.g. "EN.PARAGRAPH_1"
    "old_value":     str,   # value at time of suggestion (working copy or graph)
    "new_value":     str,   # LLM-generated rewrite
    "suggestion_id": str,   # UUID linking this suggestion to its batch
}
```

**Naming note**: The existing `ToneSuggestion` dataclass in `models.py` uses
`current_value` and `suggested_value`. That dataclass is used by `apply_tone_suggestions`
internally. The dict shape above (with `old_value` / `new_value`) is what
`finalize_rewrites` writes to state and what the orchestrator reads for diff
presentation. Both naming conventions coexist; they are not merged by this refactor.

---

### `ServiceResolutionResult` (conditional — Branch B only)

Add to `models.py` only if the Phase 0 audit finds that `services.resolve_template`
returns its own type rather than wrapping `shared.resolution.resolver.ResolutionResult`.

```python
@dataclass
class ServiceResolutionResult:
    resolved_body: str           # fully resolved template body (HTML or text)
    resolved_keys: set[str]      # keys that appeared in the body and were resolved
    unresolvable_keys: list      # list of UnresolvableKey from shared/resolution
```

If the audit finds Branch A (wraps shared `ResolutionResult`), this dataclass is not
added. All field access in `tone_suggestion_subagent.py` updates to `resolved_text`
(not `resolved_body`) and `unresolvable_keys` (not `resolved_keys`).

---

## Redis key formats

| Key | Format | Owner |
|---|---|---|
| Working copy | `working-copy:{template_name}:{session_id}` | `WorkingCopySubagent` |
| Tone snapshot | `tone-snapshot:{template_name}:{session_id}` | `ToneSuggestionSubagent` |

Both are Redis hashes. Fields are canonical placeholder keys (e.g. `EN.PARAGRAPH_1`).
Values are raw strings. In the snapshot hash, a value of `SNAPSHOT_NONE_SENTINEL`
means the key had no working copy override at snapshot time and should be deleted from
the working copy (not restored to empty string) on undo.

---

## Session state keys

| Key | Type | Written by | Scope |
|---|---|---|---|
| `eligible_keys` | `dict[str, str]` | `load_eligible_keys` | Session — cached, invalidated by `force_reload=True` |
| `suggestions` | `list[dict]` | `finalize_rewrites` | Session — persists from suggest turn to apply turn |
| `suggestion_id` | `str` | `_suggest_tone_rewrites_tool` | Session — persists from suggest turn to apply turn |
| `tone_bearing_keys` | — | Not stored | Turn-scoped only; passed as explicit parameter |
| `structural_keys` | — | Not stored | Turn-scoped only; not passed forward |
| `pending_suggest_rewrite` | — | Removed | Was written by old implementation; silently ignored if present in live sessions |

---

## Errors

Defined in `template_assistant/context.py`, alongside the existing
`SessionContextMissingError`.

### `MissingClassificationError`

Raised by `_suggest_tone_rewrites_tool` when the `tone_bearing_keys` parameter is
absent or `None`. Indicates that `KeyClassifierAgent` did not run before `SuggestAgent`.

```python
class MissingClassificationError(Exception):
    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "MissingClassificationError",
            "message": "Key classification must run before tone suggestions can be generated.",
        }
```

**Not raised** when `tone_bearing_keys` is an empty dict `{}`. An empty dict means
all keys were classified as structural — that is a valid outcome, not an error. The
tool returns `{"message": "No eligible keys found for tone rewriting."}` in that case.

---

### `SuggestionIdMismatchError`

Raised by `_apply_tone_suggestions_tool` when the `suggestion_id` on a confirmed
suggestion does not match `session.state["suggestion_id"]`.

```python
class SuggestionIdMismatchError(Exception):
    def __init__(self, expected: str, received: str) -> None:
        self.expected = expected
        self.received = received
        super().__init__(f"Expected suggestion_id {expected!r}, got {received!r}.")

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "SuggestionIdMismatchError",
            "message": "The suggestion batch has expired. Please generate new suggestions.",
        }
```