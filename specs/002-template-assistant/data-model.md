# Phase 1: Data Model

## Entities

### 1. SessionContext
Represents the required context injected into the agent session before the first user message.

**Fields**:
- `template_name` (str): The identifier of the template being edited.
- `lang_local` (str): The locale (always uppercase, e.g., 'EN-US').
- `param_cust_brand` (str): The brand context (always uppercase).
- `session_id` (str): ADK session ID.

**Validation**:
- All four fields MUST be present. If any are missing, tools MUST raise `SessionContextMissingError`.

### 2. ResolutionResult (Reference from shared lib)
The output of the shared resolution engine.

**Fields**:
- `resolved_text` (str): The fully resolved template string.
- `unresolvable_keys` (list[UnresolvableKey]): List of keys that could not be resolved.

### 3. UnresolvableKey (Reference from shared lib)
Represents a single placeholder that failed resolution.

**Fields**:
- `key` (str): The placeholder key.
- `reason` (UnresolvableReason): Enum indicating failure reason (`MISSING` | `CYCLE` | `BROKEN_RULE`).

### 4. ToneEvaluationResult
The output of the tone evaluation process.

**Fields**:
- `scores` (dict[str, float]): 28 GoEmotions labels mapped to confidence scores.
- `evaluated_at` (datetime): Timestamp of evaluation.
- `source` (Literal["working_copy", "graph"]): Indicates if the working copy was active during evaluation.

### 5. ToneSuggestion
A proposed rewrite for a specific placeholder value.

**Fields**:
- `key` (str): canonical placeholder key.
- `current_value` (str): value before suggestion.
- `suggested_value` (str): LLM-generated rewrite.
- `predicted_delta` (dict[str, float]): expected emotion score change.

### 6. WorkingCopySnapshot
A temporary record of placeholder values captured immediately before applying a set of tone suggestions.

**Fields**:
- `keys` (dict[str, str | None]): key → pre-suggestion value (None = was not in WC).
- `captured_at` (datetime): Timestamp of capture.

## Redis Key Formats

- **Working Copy**: `working-copy:{template_name}:{session_id}` → hash
- **Working Copy Snapshot**: `working-copy-snapshot:{template_name}:{session_id}` → hash

## Eligibility Heuristics
A placeholder key is eligible for natural language rewriting if its resolved value:
1. Length > 20 characters
2. Does NOT match a URL pattern (e.g., starts with `http`)
3. Does NOT match a hex color pattern
4. Does NOT match a pure numeric value
5. Does NOT end in `_URL`, `_COLOR`, or `_ID`