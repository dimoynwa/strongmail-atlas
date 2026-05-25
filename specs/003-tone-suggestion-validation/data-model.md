# Data Model: Tone Suggestion Validation

## Entities

### `EligibilityResult`
Represents the result of evaluating a placeholder key for tone rewrite eligibility. `is_eligible_for_rewrite` returns `bool` directly. `EligibilityResult` is used internally when building the ineligible key report for the `suggest_tone_rewrite` response — it is not the return type of the helper function itself.
- **Fields**:
  - `key` (str): The placeholder key.
  - `value` (str): The resolved value used for the check (working copy or raw graph).
  - `eligible` (bool): Whether the key is eligible for rewriting.
  - `reason` (str | None): The reason for ineligibility, or None if eligible.
- **Reason Values**:
  - `"sm_rule"`: Key starts with `SM_RULE_`.
  - `"url"`: Value starts with `http://` or `https://`.
  - `"colour_code"`: Value matches a CSS color pattern.
  - `"numeric"`: Value is numeric-only (ignoring whitespace).
  - `"too_short"`: Value is 20 characters or shorter (ignoring whitespace).
  - `"wrong_prefix"`: Key prefix does not match `lang_local`, `param_cust_brand`, or `GENERIC.`.
  - `None`: Key is eligible.

### `DiscardedSuggestion`
Represents a key returned by the LLM that was discarded during validation.
- **Fields**:
  - `key` (str): The hallucinated or ineligible key.
  - `reason` (str): The reason it was discarded (e.g., `"hallucinated_key"`).

## Contract Updates

### `suggest_tone_rewrite` Return Schema
The return payload is updated to include discarded keys while preserving all existing fields.
```json
{
  "suggestions": [
    {"key": "EN.PARAGRAPH_1", "new_value": "Rewritten text..."}
  ],
  "ineligible_keys": ["EN.LOGO_URL", "EN.BUTTON_COLOR"],
  "discarded_keys": [
    {"key": "BODY", "reason": "hallucinated_key"}
  ],
  "target_emotions": {"approval": 0.8, "excitement": 0.7},
  "snapshot_saved": true,
  "suggestion_id": "uuid-for-this-batch"
}
```

### `apply_tone_suggestions` Error Payload
The `KeyNotInGraphError` is updated to explicitly list invalid keys and confirm no valid keys were written.
```json
{
  "error": "KeyNotInGraphError",
  "invalid_keys": ["BODY", "SUBJECT"],
  "valid_keys_not_written": ["EN.PARAGRAPH_1"]
}
```