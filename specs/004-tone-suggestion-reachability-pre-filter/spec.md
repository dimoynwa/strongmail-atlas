# Spec: Tone Suggestion Reachability Pre-Filter

**Spec ID**: 004-tone-suggestion-reachability-filter
**Branch**: `004-tone-suggestion-reachability-filter`  
**Date**: May 25, 2026  
**Status**: Implemented (manual)  
**Related specs**: 003-tone-suggestion-validation (Tone Suggestion Key Validation)

---

## Problem

After implementing the eligibility filter (`is_eligible_for_rewrite`) in 003-tone-suggestion-validation,
the candidate key set passed to the LLM for tone rewriting was still approximately
250 keys per template invocation.

The root cause: `build_graph()` returns every key from every content block linked
to the template — including keys that are never referenced in the template HTML or
text bodies. StrongMail content blocks are shared across many templates. A single
content block may define 50–100 keys, but a given template may only use 5 of them
via `##KEY##` tokens in its HTML or text body.

The eligibility filter (`is_eligible_for_rewrite`) operates on key/value content
alone — it has no knowledge of whether a key is actually used by the template. It
cannot distinguish between a reachable key and an unreachable one. As a result,
250+ keys passed the content-based eligibility checks, producing an oversized
candidate set that:

1. Sent far more content to the LLM than necessary, increasing token usage and
   latency.
2. Caused the LLM to generate rewrites for keys whose values would never appear
   in the rendered template, producing meaningless suggestions for the user.
3. Made the suggestion diff noisy and difficult to review.

### Observed failure

Running "Make this template feel more exciting" on a password reset template
produced 20+ suggestions including config blocks (`BINANCE`, `BUSINESS_WALLET`),
raw HTML structure (`EMAIL_OPENING_BODY`), and URL-only values — none of which
appear as rendered prose in the template output.

---

## Root Cause Analysis

The resolution graph (`build_graph()`) is intentionally complete — it contains
all keys needed to resolve any token that might appear in any content block linked
to the template. This is correct behaviour for the resolution engine: it must be
able to resolve any key it encounters during traversal.

However, for tone rewriting, only the keys that are actually *visited* during
resolution of the specific template HTML and text bodies are candidates. The gap
was that no step in `suggest_tone_rewrite` cross-referenced the graph against the
template's actual token usage.

The resolution engine already tracks visited keys for cycle detection during
`resolve_template()`. This visited set is the exact reachability information
needed — it was simply not being exposed.

---

## Solution

Two changes, both minimal and additive:

### Change 1 — `shared/resolution/resolver.py`

Add `resolved_keys: list[str]` to `ResolutionResult` with a default factory so
that existing callers that construct `ResolutionResult` directly are unaffected.
This satisfies FR-017 — no existing construction site needs to be updated.

```python
from dataclasses import dataclass, field

@dataclass
class ResolutionResult:
    resolved_text: str
    unresolvable_keys: list[UnresolvableKey]
    resolved_keys: list[str] = field(default_factory=list)
```

`resolved_keys` is the **union** of all canonical keys visited during resolution
of both the HTML body and the text body in a single `resolve_template()` call.
The visited set is accumulated across both body resolutions — it must **not** be
reset between the HTML pass and the text pass. A key visited in either body
appears in `resolved_keys` exactly once.

`resolved_keys` includes keys resolved transitively (i.e. keys referenced by
other keys, not just keys directly present in the template HTML). For example,
if `EN.PARAGRAPH_1` contains `##EN.FIRST_NAME##`, then `EN.FIRST_NAME` is
included in `resolved_keys` even though it does not appear directly in the
template HTML.

### Reachability semantics

**Transitive keys are included.**  
When the resolver visits a key whose value contains `##OTHER_KEY##` tokens, it
recurses into each referenced key. All keys visited during that recursive
traversal are added to the visited set. For example, given:

```
EN.GREETING = "Hi, my name is ##EN.FIRST_NAME##"
EN.FIRST_NAME = "##PARAM_FIRST_NAME##"
```

Resolving `EN.GREETING` visits both `EN.GREETING` and `EN.FIRST_NAME`. Both
appear in `resolved_keys`. `EN.FIRST_NAME` would then be filtered out by
`is_eligible_for_rewrite` (its value is a bare token matching the
`^(##[^#]+##\s*)+$` exclusion rule), but `EN.GREETING` is eligible — the LLM
rewrites its prose while preserving the `##EN.FIRST_NAME##` token in place.

**Namespace tokens are expanded before visiting.**  
The resolver runs namespace expansion via `expand_namespace()` before any key
lookup. Tokens of the form `##LANG_LOCAL.KEY1##` and `##PARAM_CUST_BRAND.KEY2##`
are expanded to their canonical forms before the key is added to the visited set:

- `##LANG_LOCAL.KEY1##` → expanded to `##EN.KEY1##` (for `lang_local=EN`)
  → canonical key `EN.KEY1` is added to `resolved_keys`
- `##PARAM_CUST_BRAND.KEY2##` → expanded to `##SKRILL.KEY2##` (for `param_cust_brand=SKRILL`)
  → canonical key `SKRILL.KEY2` is added to `resolved_keys`

The raw namespace placeholder forms (`LANG_LOCAL.KEY1`, `PARAM_CUST_BRAND.KEY2`)
never appear in `resolved_keys`. Only canonical keys appear.

**`resolved_keys` is session-scoped.**  
Because namespace expansion uses the active `lang_local` and `param_cust_brand`
from session context, the same template produces a different `resolved_keys` set
for different sessions. A template referencing `##LANG_LOCAL.PARAGRAPH_1##` will
produce `EN.PARAGRAPH_1` in `resolved_keys` for an EN session and
`DE.PARAGRAPH_1` for a DE session. The reachability set correctly reflects only
the keys reachable for the active locale and brand — which is exactly the right
scope for tone rewriting.

### Change 2 — `template_assistant/subagents/tone_suggestion_subagent.py`

In `suggest_tone_rewrite`, add a reachability pre-filter between `build_graph()`
and `is_eligible_for_rewrite()`. The value passed to `is_eligible_for_rewrite`
must be the working copy value if one exists for that key, otherwise the raw
graph value — consistent with FR-007 from patch-01.

```python
# 1. Build the full graph (all keys in all linked content blocks)
graph = await build_graph(pool, template_name)

# 2. Resolve the template to discover which keys are actually used.
#    resolved_keys is the union of all keys visited across both HTML
#    and text body resolutions.
result = await resolve_template(
    template_name=template_name,
    lang_local=lang_local,
    param_cust_brand=param_cust_brand,
    session_id=session_id,
    graph=graph,
    pool=pool,
    redis=redis,
)
reachable = set(result.resolved_keys)

# 3. Read the current working copy so eligibility uses the live value,
#    not the stale graph raw value.
wc = await get_working_copy(redis, template_name, session_id)

# 4. Apply reachability pre-filter, then content eligibility filter.
#    Working copy value takes priority over graph value for eligibility
#    checking — consistent with patch-01 FR-007.
eligible = {
    k: wc.get(k, v) for k, v in graph.items()
    if k in reachable
    and is_eligible_for_rewrite(k, wc.get(k, v), lang_local, param_cust_brand)
}
```

---

## Filter Pipeline (after this change)

```
build_graph()
    → ~3000 keys (all content block keys for this template)

reachability filter (k in result.resolved_keys)
    → ~20–50 keys (only keys visited during template resolution)

is_eligible_for_rewrite()
    → ~5–15 keys (prose text keys only, no HTML / URLs / tokens / config)

LLM prompt
    → genuine rewritable prose keys only
```

---

## Design Decisions

**Why `field(default_factory=list)` instead of a required field?**

Making `resolved_keys` a required field with no default would be a breaking
change for every existing caller that constructs `ResolutionResult` positionally
or by keyword. Using `field(default_factory=list)` makes the change genuinely
non-breaking — all existing `ResolutionResult(resolved_text=...,
unresolvable_keys=...)` constructions continue to work without modification.
This directly satisfies FR-017.

**Why expose `resolved_keys` from `ResolutionResult` rather than re-traversing?**

The resolver already computes the visited set for cycle detection. Exposing it
adds no runtime cost. Re-traversing the template bodies separately (e.g. with a
regex scan for `##KEY##` tokens) would be cheaper to implement but would miss
transitively resolved keys — keys that are not directly in the HTML but are
referenced by other keys. Using the resolver's own visited set is authoritative.

**Why is `resolved_keys` the union across both HTML and text bodies?**

Both the HTML and text bodies of a template may reference different keys, or
the same keys. Any key reachable from either body is a valid rewrite candidate.
Restricting to only the HTML body would silently exclude keys used only in the
plain-text version of the template.

**Why is reachability a separate step from `is_eligible_for_rewrite`?**

`is_eligible_for_rewrite` evaluates a single key/value pair in isolation — it has
no access to the template structure. Reachability is a property of the template,
not of the key. Mixing the two concerns would require passing the full resolution
result into the eligibility function, breaking its clean single-key contract and
making it untestable in isolation. They remain separate sequential filters.

**Why does `resolved_keys` include transitively resolved keys?**

A key like `EN.PARAGRAPH_1` may resolve to a value containing `##EN.FIRST_NAME##`.
`EN.FIRST_NAME` is not directly in the template HTML but is reachable from it.
Including transitive keys ensures that if `EN.FIRST_NAME` has prose content, it
is a valid rewrite candidate. In practice, transitive keys are usually short
tokens or parameters and are filtered out by `is_eligible_for_rewrite` anyway —
but the reachability set should be accurate.

**Why does `resolved_keys` contain canonical keys, not namespace placeholder forms?**

The resolver expands `##LANG_LOCAL.X##` and `##PARAM_CUST_BRAND.X##` tokens via
`expand_namespace()` before any lookup. The visited set is populated after
expansion, so only canonical keys ever enter it. This means `resolved_keys` is
directly comparable to the keys in `build_graph()` — no further transformation
is needed when checking `k in reachable`.

**Why is `resolved_keys` session-scoped rather than template-scoped?**

Namespace expansion is driven by `lang_local` and `param_cust_brand` from session
context. A template containing `##LANG_LOCAL.PARAGRAPH_1##` resolves to
`EN.PARAGRAPH_1` in an EN session and `DE.PARAGRAPH_1` in a DE session — these
are genuinely different keys with different values. The reachability set must
reflect the active session's locale and brand to ensure tone rewrites target
only the keys that will actually render in the user's session.

**Why use working-copy values for eligibility checking?**

The user may have already overridden a key in the working copy — for example,
changing `EN.PARAGRAPH_1` from prose to a URL. The graph raw value would still
be prose and would incorrectly pass the eligibility filter. Using the working
copy value ensures eligibility reflects the actual current state of the template
in this session. This is consistent with patch-01 FR-007.

---

## Impact on Existing Callers

`ResolutionResult` uses `field(default_factory=list)` for `resolved_keys`, so
existing callers that construct `ResolutionResult` directly are **not broken**.
No construction sites need to be updated.

Callers that only read fields from a `ResolutionResult` instance are unaffected
in all cases.

To verify no construction sites pass a positional third argument that would
silently receive the wrong value:

```bash
grep -r "ResolutionResult(" .
```

Any call of the form `ResolutionResult(text, keys, some_third_arg)` would need
review — but this pattern should not exist in the current codebase.

---

## Functional Requirements

**FR-014**: `suggest_tone_rewrite` MUST pre-filter the resolution graph to only
keys reachable in the template HTML and text bodies before applying
`is_eligible_for_rewrite`. Keys present in the graph but not visited during
template resolution MUST be excluded and MUST NOT be passed to the LLM.

**FR-015**: `ResolutionResult` MUST expose `resolved_keys: list[str]` — the
complete union of canonical keys visited during resolution of both HTML and text
bodies in a single `resolve_template()` call, including transitively resolved
keys. The visited set MUST be accumulated across both body resolutions and MUST
NOT be reset between them. This field is the authoritative reachability set for
`suggest_tone_rewrite`.

**FR-016**: The reachability pre-filter MUST run before `is_eligible_for_rewrite`.
The ordering is: graph → reachability → eligibility → LLM.

**FR-017**: Adding `resolved_keys` to `ResolutionResult` MUST NOT change the
behaviour of `resolve_template()` or any other caller of the shared resolution
library. The `field(default_factory=list)` default ensures all existing
construction sites remain valid without modification.

**FR-018**: The value used for eligibility checking in the reachability-filtered
candidate set MUST be the working copy value for that key if one exists in Redis,
otherwise the raw graph value. The graph raw value MUST NOT be used when a
working copy override is present.

**FR-019**: `resolved_keys` MUST contain only canonical keys — never namespace
placeholder forms such as `LANG_LOCAL.KEY1` or `PARAM_CUST_BRAND.KEY2`. Namespace
expansion via `expand_namespace()` runs before any key is added to the visited
set, so the expanded canonical form (e.g. `EN.KEY1`, `SKRILL.KEY2`) is what
appears in `resolved_keys`. The reachability filter `k in reachable` operates
on canonical keys from `build_graph()` and requires no further transformation.

**FR-020**: `resolved_keys` is session-scoped. The same template MUST produce
different `resolved_keys` sets for different `lang_local` or `param_cust_brand`
values, because namespace expansion is driven by session context. A key reachable
in an EN session (e.g. `EN.PARAGRAPH_1`) is not necessarily reachable in a DE
session (where `DE.PARAGRAPH_1` would appear instead).

---

## Test Requirements

The following tests must be present in addition to all existing passing tests.

**T-001 — `resolved_keys` is populated correctly** (in `shared/` integration tests)  
Call `resolve_template()` on a known template. Assert that `result.resolved_keys`
is non-empty and contains all keys known to be directly referenced in the template
HTML or text body. Assert that it also contains at least one transitively resolved
key if the template has any. Assert that keys present in the graph but not
referenced in the template are absent from `resolved_keys`.

**T-002 — `resolved_keys` is the union across both bodies**  
Use a template where HTML and text bodies reference different keys. Assert that
`resolved_keys` contains keys from both bodies, not just one.

**T-003 — Reachability pre-filter excludes unreachable keys from suggestions**  
Identify a key that exists in the resolution graph for a template but is not
referenced in that template's HTML or text body. Call `suggest_tone_rewrite`.
Assert that key does not appear in `suggestions` or `ineligible_keys` in the
response — it must be silently excluded before the eligibility filter runs.

**T-004 — Working copy value used for eligibility, not graph value**  
Override a key in the working copy to a URL value. Call `suggest_tone_rewrite`.
Assert that key does not appear in `suggestions` even if its graph raw value
would have passed the eligibility filter.

**T-005 — Existing resolution tests still pass**  
All tests under `shared/` and `template_assistant/tests/` that were passing
before this change must continue to pass. The `field(default_factory=list)`
default means no existing test should require modification.

**T-006 — Namespace placeholder tokens produce canonical keys in `resolved_keys`**  
Use a template that references `##LANG_LOCAL.PARAGRAPH_1##` in its HTML body.
Call `resolve_template()` with `lang_local=EN`. Assert that `EN.PARAGRAPH_1`
appears in `result.resolved_keys`. Assert that `LANG_LOCAL.PARAGRAPH_1` does
not appear in `result.resolved_keys`. Repeat with `lang_local=DE` and assert
`DE.PARAGRAPH_1` appears instead of `EN.PARAGRAPH_1`, confirming session scoping.

**T-007 — Transitive prose keys are eligible, bare token keys are filtered out**  
Use a template where `EN.GREETING` resolves to `"Hi, my name is ##EN.FIRST_NAME##"`
and `EN.FIRST_NAME` resolves to `"##PARAM_FIRST_NAME##"`. Call
`suggest_tone_rewrite`. Assert that `EN.GREETING` appears in `suggestions`
(it is prose with an embedded token). Assert that `EN.FIRST_NAME` does not
appear in `suggestions` (its value is a bare token and is filtered by
`is_eligible_for_rewrite`). Assert that the `new_value` for `EN.GREETING`
preserves the `##EN.FIRST_NAME##` token exactly.

---

## Success Criteria

**SC-001**: After this change, the candidate key set passed to `is_eligible_for_rewrite`
in `suggest_tone_rewrite` is bounded by the number of keys actually used in the
template — typically 20–50 for a standard Skrill template, not 250+.

**SC-002**: The final eligible set passed to the LLM contains only keys whose
resolved values appear as rendered prose in the template output.

**SC-003**: Existing behaviour of `resolve_template()`, `resolve_key()`, and all
resolution subagent tools is unchanged. All existing tests in `shared/` and
`template_assistant/tests/` continue to pass without modification.

**SC-004**: Running "Make this template feel more exciting" on the password reset
template produces suggestions only for genuine prose keys (subject lines,
paragraph bodies, greeting lines). Config blocks, raw HTML structure, URL-only
values, and unreachable keys do not appear in the suggestion diff.

**SC-005**: A key overridden in the working copy to an ineligible value (e.g. a
URL) does not appear in suggestions, even if its original graph value would have
passed the eligibility filter.

**SC-006**: A template referencing `##LANG_LOCAL.PARAGRAPH_1##` produces
`EN.PARAGRAPH_1` in `resolved_keys` for an EN session and `DE.PARAGRAPH_1`
for a DE session. The namespace placeholder form `LANG_LOCAL.PARAGRAPH_1`
never appears in `resolved_keys` for any session.

**SC-007**: A transitive prose key (reachable via `##KEY##` reference in
another key's value, not directly in the template HTML) appears in
`suggestions` if it passes `is_eligible_for_rewrite`. A bare token key
reachable by the same path (value is only `##PARAM_X##`) does not appear
in `suggestions`.