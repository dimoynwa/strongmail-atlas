# Feature Specification: SuggestAgent Self-Rewrite via Prompt Return

**Spec ID**: `006-fix-suggest-agent-self-rewrite`
**Branch**: `006-fix-suggest-agent-self-rewrite`
**Parent spec**: `006-refactor-tone-suggestion-orchestrator`
**Created**: 2026-05-26
**Status**: Draft

---

## Problem

`_call_batch_llm` makes a second Gemini API call from inside `_suggest_tone_rewrites_tool`,
which itself runs inside `SuggestAgent` — already a Gemini `LlmAgent`. This means
every tone suggestion request makes two sequential LLM calls: one for `SuggestAgent`
to reason about tool invocation, and one inside the tool to generate the actual
rewrites. The inner call was designed as an injection point for testing, with
`_default_rewrite` as a stub fallback. In production `_llm_batch_fn` is never
set, so the fallback runs, producing `[optimism tone]` annotations instead of
real rewrites.

Additionally, `_build_llm_prompt` sends keys in alphabetical order with no
reading-order context. `SuggestAgent` rewrites each key in isolation with no
awareness of the sequence in which the recipient will read them — producing
rewrites that are individually plausible but tonally incoherent across the
template as a whole.

`SuggestAgent` is the LLM. The tool should return the eligible keys ordered by
their position in the resolved template body so `SuggestAgent` reasons over them
as a coherent sequence. The full resolved body is not needed — reading order
alone is sufficient context. No nested API call is needed.

---

## Functional Requirements

**FR-001**: `_build_llm_prompt` MUST be updated to accept the resolved template
body as a third argument for ordering purposes only. The updated signature is:

```python
def _build_llm_prompt(
    eligible: dict[str, str],
    target_intent: str,
    target_profile: dict[str, float],
    resolved_body: str,           # ← used for ordering only, not included in prompt
) -> str:
```

The eligible keys MUST be ordered by their first appearance in `resolved_body`
before being serialised into the prompt. A simple substring scan is sufficient:
for each key in `eligible`, find the index of the first occurrence of the key
string in `resolved_body`. Keys found in the body are sorted by that index.
Keys not found in the body are appended at the end in their original order.

The prompt structure MUST follow this order:

```
TONE TARGET:
Intent: {target_intent}
Emotion weights: {target_profile as JSON}

KEYS TO REWRITE (in reading order):
{eligible keys and current values as JSON, ordered by position in template}

INSTRUCTIONS:
- These keys appear in sequence in the same email. Rewrite them as a
  coherent set — the tone shift must feel consistent across all keys,
  not independently optimised per key.
- For each key, produce a rewrite aligned with the tone target while
  preserving the original meaning, approximate length, and any ##TOKEN##
  references exactly as they appear.
- Do NOT append tone labels, annotations, or tags to values.
- Do NOT copy the old value into new_value unchanged.
- Return ONLY keys from the provided list.
- Respond with valid JSON only — no preamble, no explanation, no markdown
  fences. A JSON array of objects with exactly two fields: "key" and "new_value".

EXAMPLE OUTPUT FORMAT:
[
    {"key": "EN.PARAGRAPH_1", "new_value": "Rewritten prose here."},
    {"key": "EN.SUBJECT", "new_value": "Rewritten subject here."}
]
```

**FR-002**: `suggest_tone_rewrite` MUST pass `resolution.resolved_body` (the
raw resolved HTML, before plain-text extraction) to `_build_llm_prompt` as the
fourth argument — used solely for key ordering via substring scan. This is
already available from the `resolve_template` call made earlier in the function.
It MUST NOT be computed a second time. The `resolved_body` string is NOT included
in the prompt text — it is used only to determine key order.

**FR-003**: `_suggest_tone_rewrites_tool` MUST return the rewrite prompt and
metadata to `SuggestAgent` rather than calling an external LLM. The return
payload MUST include:

```python
{
    "rewrite_prompt": str,          # built by updated _build_llm_prompt
    "eligible_keys": list[str],     # keys in the tone-bearing set
    "target_emotions": dict[str, float],
    "baseline_emotions": dict[str, float],
    "suggestion_id": str,           # UUID for this batch
    "instruction": (
        "You are generating tone rewrites. The keys in rewrite_prompt are "
        "ordered by their reading sequence in the email — rewrite them as a "
        "coherent set, not independently. Return JSON only: a list of objects "
        "with 'key' and 'new_value' fields. Return ONLY keys from eligible_keys. "
        "Do not annotate, append labels, or copy values unchanged."
    ),
}
```

**FR-004**: `SuggestAgent`'s instruction MUST be updated to handle this return
shape. When the tool returns a `rewrite_prompt`, `SuggestAgent` MUST treat the
keys as a reading-ordered sequence and produce rewrites that are tonally
coherent across the full set. It MUST NOT rewrite keys independently as if they
were unrelated strings. It MUST NOT delegate to another agent or make a tool
call to produce the rewrites.

**FR-005**: The orchestrator MUST capture `SuggestAgent`'s response text, parse
it as JSON via `_parse_llm_rewrites`, run it through `_validate_llm_rewrites`
against the `eligible_keys` list, discard any `new_value` identical to the
corresponding `old_value`, then write the validated `suggestions` and
`suggestion_id` to `session.state`.

**FR-006**: The following functions and module-level variables MUST be deleted
entirely from `tone_suggestion_subagent.py` as they only existed to support the
external LLM call path:

- `_call_batch_llm`
- `_default_rewrite`
- `_generate_rewrite`
- `_rewrite_fn` module-level variable
- `_llm_batch_fn` module-level variable
- `set_rewrite_fn`
- `set_llm_batch_fn`
- `RewriteFn` type alias
- `LlmBatchFn` type alias

**FR-007**: `_parse_llm_rewrites` and `_validate_llm_rewrites` MUST be preserved
unchanged. They validate `SuggestAgent`'s response exactly as they previously
validated the external LLM response.

**FR-008**: `_predict_delta` MUST be preserved unchanged.

**FR-009**: The `suggest_tone_rewrites` function (plural) which returns
`list[ToneSuggestion]` MUST be removed. It can no longer generate real LLM
rewrites directly — the LLM is now `SuggestAgent` itself. Tests that used it
MUST be updated to test via `_suggest_tone_rewrites_tool` instead.

**FR-010**: `suggest_tone_rewrite` (singular) — the function called by
`_suggest_tone_rewrites_tool` — MUST be updated to remove the `_call_batch_llm`
call and instead return the prompt and metadata payload defined in FR-003.
The GoEmotions baseline scoring, tone profile lookup, and `_build_llm_prompt`
call all remain. `resolution.resolved_body` is passed to `_build_llm_prompt`
as the fourth argument for key ordering. It is already available from the
`resolve_template` call — it MUST NOT be computed a second time.



## Updated Flow

```
User: "Make this more admirational"
        ↓
ToneSuggestionSubagent (orchestrator)
        ↓ before_agent_callback populates eligible_keys
        ↓ delegates
KeyClassifierAgent → writes tone_bearing_keys to session.state
        ↓ delegates
SuggestAgent
  → calls _suggest_tone_rewrites_tool("make this more admirational")
  → tool builds: GoEmotions baseline, tone profile, reading-ordered key prompt
  → tool returns: { rewrite_prompt (keys in reading order), eligible_keys, ... }
  → SuggestAgent treats keys as a reading sequence
  → SuggestAgent reasons over ALL keys together as one coherent email
  → SuggestAgent emits JSON rewrites as response text
        ↓
Orchestrator captures SuggestAgent response
  → parses JSON via _parse_llm_rewrites
  → validates via _validate_llm_rewrites
  → discards unchanged values
  → writes suggestions + suggestion_id to session.state
  → presents diff to user
```

---

## Data Model

No new session state keys. The `suggestions` and `suggestion_id` keys are
unchanged.

`_build_llm_prompt` gains one argument (`resolved_body: str`) used solely for
key ordering via substring scan. It is module-private — no external callers are
affected. The `resolved_body` string does not appear in the prompt output.

`ToneSuggestion` dataclass is unchanged. `DiscardedSuggestion` dataclass is
unchanged.

---

## SuggestAgent Instruction Update

The instruction for `SuggestAgent` MUST include the following behaviour
specification:

```
When _suggest_tone_rewrites_tool returns a payload containing rewrite_prompt:
1. The keys in rewrite_prompt are ordered by their reading sequence in the
   email — treat them as a coherent set, not as independent strings.
2. Reason over all keys together: the tone shift must feel consistent from
   the first key to the last, as the same recipient reads them in sequence.
3. Emit your response as a JSON array only, with no preamble, no
   explanation, and no markdown fences. Each object must have exactly
   two fields: "key" (string) and "new_value" (string).
4. Return ONLY keys from the eligible_keys list in the tool result.
5. Do NOT copy the old value into new_value unchanged.
6. Do NOT append tone labels, annotations, or comments to values.
7. Do NOT call any other tool or delegate to any other agent.
```

---

## Constraints & Boundaries

- **One file only**: `template_assistant/subagents/tone_suggestion_subagent.py`.
- **No changes to** `KeyClassifierAgent`, `ApplyAgent`, `UndoAgent`, or their
  tools.
- **No changes to** `shared/resolution/`, `TemplateAssistantAgent`,
  `ResolutionSubagent`, `WorkingCopySubagent`, or `ToneEvaluationSubagent`.
- **`_parse_llm_rewrites` and `_validate_llm_rewrites` stay**: they validate
  `SuggestAgent`'s response exactly as they previously validated the external
  LLM response.
- **`resolved_body` reuses existing computation**: `resolution.resolved_body` is
  already available from the `resolve_template` call in `suggest_tone_rewrite`.
  It MUST NOT be fetched or computed a second time. It is passed to
  `_build_llm_prompt` for key ordering only and MUST NOT appear in the prompt text.

---

## Testing

Add to `template_assistant/tests/test_tone_suggestion_subagent.py`:

**`test_suggest_tool_returns_rewrite_prompt`**
Call `_suggest_tone_rewrites_tool` with a valid session state containing
`tone_bearing_keys`. Assert the return dict contains `rewrite_prompt`,
`eligible_keys`, `target_emotions`, `baseline_emotions`, `suggestion_id`,
and `instruction`. Assert `rewrite_prompt` contains the substring
`"KEYS TO REWRITE"`. Assert no `suggestions` key is present in the return
value — the tool no longer produces suggestions, `SuggestAgent` does.

**`test_suggest_tool_no_eligible_keys`**
Call `_suggest_tone_rewrites_tool` with `tone_bearing_keys` as an empty dict.
Assert the return dict contains `"message": "No eligible keys found for tone
rewriting."` and no `rewrite_prompt` key.

**`test_build_llm_prompt_keys_in_reading_order`**
Call `_build_llm_prompt` with three eligible keys where `EN.PARAGRAPH_1`
appears before `EN.GREETING` in the mock `resolved_body`, and `EN.CTA` is
absent from the body entirely. Assert that in the serialised JSON within the
prompt, `EN.PARAGRAPH_1` precedes `EN.GREETING`, and `EN.CTA` appears last.

**`test_build_llm_prompt_no_template_context_section`**
Call `_build_llm_prompt` with any valid arguments. Assert the output does NOT
contain the string `"TEMPLATE CONTEXT"` — confirming the resolved body is not
included in the prompt text.

**`test_call_batch_llm_deleted`**
Assert that the `tone_suggestion_subagent` module has no attribute
`_call_batch_llm`, `_default_rewrite`, `set_llm_batch_fn`, or `set_rewrite_fn`.

Remove any existing test that calls `suggest_tone_rewrites` (plural) directly,
as that function is deleted by FR-009.

All other existing tests must pass unchanged.

---

## Success Criteria

**SC-001**: When a user sends "Make this template more admirational", `SuggestAgent`
produces genuinely rewritten values — not the original values with `[optimism tone]`
appended.

**SC-002**: Rewrites across multiple keys read as a coherent email — the greeting,
body paragraphs, and CTA are tonally consistent with each other because they are
presented to `SuggestAgent` in reading order, not as an unordered bag of strings.

**SC-003**: Only one Gemini API call is made per suggestion turn. No nested LLM
call occurs inside `_suggest_tone_rewrites_tool`.

**SC-004**: `_suggest_tone_rewrites_tool` returns in under 100ms (excluding the
`SuggestAgent` LLM call itself) — it is pure Python computation with no I/O
beyond the DB and Redis calls already present.

**SC-005**: The `[optimism tone]` annotation pattern MUST NOT appear in any
suggestion `new_value` returned to the user.