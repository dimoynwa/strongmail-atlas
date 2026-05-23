# Feature Specification: Placeholder Resolution Engine

**Feature Branch**: `001-placeholder-resolution-engine`

**Created**: 2026-05-23

**Status**: Draft

**Input**: User description: Build a shared Python library called the Placeholder Resolution
Engine that resolves ##PLACEHOLDER## tokens in StrongMail email template bodies given a
template name, locale, brand, and session ID.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Build Resolution Graph (Priority: P1)

An AI agent needs to load the complete set of placeholder key→value pairs for a given
template before it can answer any question about that template's content. The agent
calls the library with a template name and runtime context; the library queries the
database and returns an in-memory structure the agent can pass to subsequent resolution
calls.

**Why this priority**: Every other user story depends on having a populated resolution
graph. Without it, no placeholder can be resolved. This is the mandatory foundation.

**Independent Test**: Call the graph-building function with a known template name and
verify the returned map contains the expected keys and raw values. No HTML resolution
is required to validate this story.

**Acceptance Scenarios**:

1. **Given** a template that has two content blocks both defining the same key, **When**
   the graph is built, **Then** the value from the first block (by link order) is used
   and the second is silently discarded.
2. **Given** a template with no content blocks, **When** the graph is built, **Then** an
   empty map is returned without error.
3. **Given** a template name that does not exist in the database, **When** the graph is
   built, **Then** a descriptive error is raised identifying the missing template.

---

### User Story 2 — Resolve Full Template Body (Priority: P2)

An AI agent wants to evaluate the tone, completeness, or quality of an email template.
It passes the raw HTML (or text) body string from the database to the library, and
receives the fully resolved string with every ##PLACEHOLDER## replaced by its final
value, plus a list of any keys that could not be resolved.

**Why this priority**: This is the primary consumer use case. Agents cannot evaluate or
rewrite template content without seeing the resolved text. Delivering a fully resolved
body is the core value proposition of this library.

**Independent Test**: Use a template body string containing three placeholders — one that
resolves cleanly, one that chains through a second placeholder, and one that is missing
from the graph. Verify the output string and the unresolvable list match expectations.

**Acceptance Scenarios**:

1. **Given** a body string with placeholder tokens and a fully populated resolution
   graph, **When** full resolution is called, **Then** every resolvable token is replaced
   with its final string value and none remain in the output.
2. **Given** a body string where a placeholder value itself contains another placeholder,
   **When** full resolution is called, **Then** the nested placeholder is also resolved
   recursively until no ##TOKEN## patterns remain.
3. **Given** a body string containing a placeholder with no matching key in the graph and
   no Redis override, **When** full resolution is called, **Then** the output includes
   the unresolved placeholder verbatim and the key appears in the returned unresolvable
   list.
4. **Given** a placeholder chain that references itself (direct or indirect cycle),
   **When** full resolution is called, **Then** the cycle is detected, the involved key
   is added to the unresolvable list with reason "cycle", and no infinite loop occurs.

---

### User Story 3 — Resolve Single Placeholder Key (Priority: P3)

An AI agent wants to answer a targeted question such as "what does the brand footer say
for Skrill in English?" without resolving the entire template body. It passes a single
key string to the library and receives the resolved final string value for that key
alone.

**Why this priority**: Useful for scoped queries where the agent only needs one piece
of content. Less critical than full-body resolution because agents could achieve the same
result by resolving the full body; this story makes targeted lookups efficient.

**Independent Test**: Call single-key resolution with a key that chains through two
intermediate placeholders. Verify the final resolved string matches the expected end
value.

**Acceptance Scenarios**:

1. **Given** a resolution graph is built and a known key is requested, **When** single-key
   resolution is called, **Then** the fully resolved value (with all nested tokens
   expanded) is returned.
2. **Given** a key whose raw value contains a prefix matching any runtime context key
   (e.g., LANG_LOCAL with locale EN, or any other context key), **When** single-key
   resolution is called, **Then** the matching prefix is expanded to its uppercased
   context value before the nested lookup proceeds.
3. **Given** a key that starts with SM_RULE_, **When** single-key resolution is called,
   **Then** the rule is evaluated against the runtime context and the correct branch
   value is returned.
4. **Given** a key that is absent from the graph and has no Redis override, **When**
   single-key resolution is called, **Then** a structured error value is returned
   identifying the missing key; no exception propagates unless the caller requests
   strict mode.

---

### User Story 4 — Working Copy Priority in Resolution (Priority: P4)

During an interactive session, an AI agent has already applied tone rewrites to several
placeholders and stored those edits in the session working copy. When the agent resolves
the template body again (e.g., to evaluate the effect of its changes), the resolution
must use the edited values, not the original database values.

**Why this priority**: Without this, an agent's rewrite suggestions would not be
reflected in subsequent resolution calls, making iterative template editing impossible.
This is an important session-level correctness guarantee.

**Independent Test**: Write an override value for a known key into the working copy store
under the correct session key, then call full-body resolution. Verify the output uses
the override value, not the database value.

**Acceptance Scenarios**:

1. **Given** a placeholder key has both a value in the resolution graph and an override
   in the working copy store for the active session, **When** resolution is performed,
   **Then** the working copy value is used and the graph value is ignored.
2. **Given** a placeholder key has only a working copy override (no entry in the
   resolution graph), **When** resolution is performed, **Then** the override is used
   and the key does not appear in the unresolvable list.
3. **Given** a working copy override is itself a raw string containing another
   ##PLACEHOLDER## token, **When** resolution is performed, **Then** the nested
   placeholder is resolved recursively using the graph (or further overrides).
4. **Given** a session ID that has no working copy entries, **When** resolution is
   performed, **Then** resolution falls back to the graph without error.

---

### User Story 5 — Unresolvable Placeholder Scan (Priority: P5)

An AI agent wants to report data quality issues in a template to its user — specifically,
which placeholders cannot be resolved and why. It calls a single scan operation that
inspects every placeholder in the template body and returns a structured report of
unresolvable keys with a reason for each.

**Why this priority**: Useful for diagnostics and proactive data quality reporting, but
agents can still answer most questions without this story. Lower priority than active
resolution capabilities.

**Independent Test**: Use a template body containing one missing key, one cycle, and one
broken SM_RULE_ chain. Verify the scan returns exactly three entries with the correct
reason codes.

**Acceptance Scenarios**:

1. **Given** a template body where all placeholders resolve successfully, **When** the
   unresolvable scan is called, **Then** an empty list is returned.
2. **Given** a placeholder key that is absent from the graph and has no working copy
   override, **When** the scan is called, **Then** the key appears in the result with
   reason "missing key".
3. **Given** a placeholder chain forming a cycle (A→B→A), **When** the scan is called,
   **Then** the cycle is reported with reason "cycle" and the full cycle path
   (e.g., "A → B → A") is included.
4. **Given** an SM_RULE_ key whose `rule_ast` has `valid: false`, or whose evaluated
   branch target key is absent from the graph, **When** the scan is called, **Then**
   the key appears with reason "invalid rule" or "broken rule chain" respectively, and
   the missing target key is identified in the detail field.

---

### Edge Cases

- A key wrappers containing mixed styles (e.g., `##/KEY##` or `##\\KEY##`) must
  normalize to the same canonical form as `##KEY##`.
- Any runtime context key whose value is an empty string must be treated as a missing key
  when it appears as a namespace prefix — no silent empty-string substitution.
- A placeholder key whose first segment matches no runtime context key is looked up as-is
  (no expansion applied); it is not an error if no prefix match is found.
- An SM_RULE_ chain that is longer than 10 hops must be treated as a cycle and reported
  as such, preventing unbounded rule traversal.
- An SM_RULE_ whose `rule_ast` column is NULL or has `valid: false` must be reported as
  unresolvable with reason "invalid rule"; evaluation must not proceed.
- A rule branch result of `####KEY####` must first reduce `####` → `##`, yielding
  `##KEY##`, which is then treated as a content key lookup.
- A template body that contains no ##PLACEHOLDER## tokens at all must return the
  original body unchanged with an empty unresolvable list.
- Keys are case-insensitive at input but are always normalized to uppercase before any
  lookup; mixed-case variations of the same key must resolve to the same value.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The library MUST load all placeholder key→value pairs for a named template
  from the database in a single graph-building operation, honouring link order for
  duplicate keys.
- **FR-002**: The library MUST expand any runtime context key that appears as a
  dot-separated prefix in a placeholder key before performing any graph lookup. The
  prefix token is matched case-insensitively against all context key names; the matched
  context value replaces the prefix and is uppercased. `LANG_LOCAL` and
  `PARAM_CUST_BRAND` are the canonical examples, but every key in the runtime context
  participates in prefix expansion.
- **FR-003**: The library MUST strip all recognised placeholder wrapper patterns
  (`##KEY##`, `##/KEY##`, `##//KEY##`, `##\KEY##`) to produce a canonical uppercase key
  before lookup.
- **FR-004**: The library MUST resolve placeholder values recursively, following chains
  of placeholder references until a terminal string value is reached or an error
  condition is detected.
- **FR-005**: The library MUST check the session working copy store before consulting the
  resolution graph for every key lookup; a working copy hit MUST take absolute priority.
  If the working copy store is unreachable, the library MUST raise a typed
  `WorkingCopyUnavailableError`; silent fallback to graph-only resolution is prohibited.
- **FR-006**: The library MUST detect and reject circular placeholder references, raising
  a typed exception that identifies the full cycle path.
- **FR-007**: The library MUST evaluate SM_RULE_ keys by reading the pre-parsed rule AST
  from the `rule_ast` column of the `dynamic_content_details` table. The AST schema is:
  `{schema_version, kind, valid, condition: {combiner, clauses[]}, then, else}`.
  Each clause contains a `variable_key` (uppercased last dot-segment of the variable
  expression), an `operator` (natural-language phrase: "is equal to", "is not equal to",
  "contains", "does not contain", "is greater than", "is greater than or equal to",
  "is less than", "is less than or equal to", "is null", "is not null", "is one of",
  "is not one of"), and a `value`. Clauses are OR-combined by default. The branch
  result (`then` or `else`) is normalised before use: `####` → `##`, leading `\`
  stripped, plain uppercase-only value → `SM_RULE_{VALUE}` (triggers chained rule
  lookup), `##KEY##` → inner KEY for graph lookup. If `valid: false` in the AST, the
  rule MUST be treated as unresolvable with reason "invalid rule".
- **FR-008**: The library MUST provide a full-body resolution operation that replaces
  every ##PLACEHOLDER## token in a given string and returns a named result object
  containing exactly two fields: `resolved_body: str` (the fully substituted string)
  and `unresolvable: list[UnresolvableEntry]` (entries for every key that could not be
  resolved). No additional metadata fields are included.
- **FR-009**: The library MUST provide a single-key resolution operation that resolves
  one placeholder key to its final string value given a pre-built resolution graph and
  runtime context.
- **FR-010**: The library MUST provide an unresolvable scan operation that inspects all
  placeholder tokens in a template body and returns a list of `UnresolvableEntry` objects,
  one per unresolvable key, each with `key: str`, `reason: ReasonCode` (enum:
  `MISSING_KEY`, `CYCLE`, `BROKEN_RULE_CHAIN`, `INVALID_RULE`), and `detail: str`.
- **FR-011**: The library MUST NOT silently swallow errors or substitute empty strings
  for unresolvable keys; every failure MUST be surfaced in the return value or as a
  typed exception.
- **FR-012**: The resolution graph MUST be treated as immutable after it is constructed;
  no resolution operation may modify the graph.

### Key Entities

- **Template**: A named email communication artefact with an HTML body and a plain-text
  body, both of which may contain ##PLACEHOLDER## tokens.
- **Resolution Graph**: An immutable mapping of canonical placeholder keys to their raw
  values, constructed from the database for a specific template at the start of a
  resolution session.
- **Content Block**: A database record that associates a placeholder key and its raw
  value with a template, ordered by link sequence.
- **Runtime Context**: The set of parameters supplied at resolution time — template
  name, locale (e.g., EN), brand (e.g., SKRILL), and session ID.
- **Namespace Prefix**: Any runtime context key whose name appears as the dot-separated
  first segment of a placeholder key (e.g., `LANG_LOCAL` in `LANG_LOCAL.PARAGRAPH_1`).
  All context keys participate in prefix expansion, not just `LANG_LOCAL` and
  `PARAM_CUST_BRAND`. The matched prefix is replaced with its context value, uppercased.
- **SM_RULE**: A conditional content rule stored in `dynamic_content_details.rule_ast`
  as a pre-parsed JSON AST (`schema_version: 1`, `kind: "strongmail_dynamic_content_rule"`).
  The AST contains a condition block (combiner + clauses with natural-language operators)
  and `then`/`else` branch values. Evaluating the condition selects a branch; the branch
  value is normalised and points to either a content key, another SM_RULE_ (chaining),
  or an inline string fragment.
- **Working Copy**: A key→value store keyed by session that holds user-edited overrides
  for placeholder values; always consulted before the resolution graph.
- **Unresolvable Report**: A list of `UnresolvableEntry` objects returned alongside
  resolved content. Each entry has three fields: `key: str` (the canonical placeholder
  key that failed), `reason: ReasonCode` (a typed enum — `MISSING_KEY`, `CYCLE`,
  `BROKEN_RULE_CHAIN`, `INVALID_RULE`), and `detail: str` (human-readable context,
  e.g., the full cycle path `"A → B → A"` or the missing branch target key).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every placeholder in a 200-placeholder template body is resolved in a
  single call without the agent needing to loop or call the library more than once.
- **SC-002**: Resolution of a full template body containing up to 200 placeholders
  completes in under 500 milliseconds under normal load.
- **SC-003**: 100% of circular placeholder references are detected and reported; no
  infinite loop or stack overflow can occur regardless of cycle length.
- **SC-004**: Working copy overrides are reflected in resolved output in 100% of cases
  for the active session; stale values from prior sessions are never returned.
- **SC-005**: Every unresolvable placeholder is reported with a specific reason; zero
  silent failures occur.
- **SC-006**: A standalone integration test suite validates all five user stories against
  real database and cache instances without any mocking.

## Clarifications

### Session 2026-05-23

- Q: What should the return type of full-body resolution be — plain string, named dataclass, or tuple? → A: Named result dataclass with exactly two fields: `resolved_body: str` and `unresolvable: list[UnresolvableEntry]`. No metadata.
- Q: When the working copy store (Redis) is unreachable at resolution time, fail hard or fall back? → A: Raise a typed `WorkingCopyUnavailableError`; silent fallback to graph-only resolution is prohibited.
- Q: Are only LANG_LOCAL and PARAM_CUST_BRAND expanded as namespace prefixes, or all runtime context keys? → A: All runtime context keys participate in prefix expansion — any key whose name matches the dot-separated first segment of a placeholder key is expanded to its uppercased value.
- Q: What is the SM_RULE DSL format and where is it read from? → A: Rules are stored as pre-parsed JSON AST in `dynamic_content_details.rule_ast`. The AST schema is `{schema_version, kind, valid, condition: {combiner, clauses[]}, then, else}`. Clauses use natural-language operators and are OR-combined. Branch results are normalised (####→##, leading \ stripped, uppercase-only → SM_RULE_ chain, ##KEY## → key lookup). `valid: false` → unresolvable with reason "invalid rule".
- Q: What is the exact schema of each entry in the unresolvable list? → A: `UnresolvableEntry` with three fields: `key: str`, `reason: ReasonCode` (typed enum: MISSING_KEY, CYCLE, BROKEN_RULE_CHAIN, INVALID_RULE), `detail: str` (human-readable context, e.g. cycle path or missing target key).

## Assumptions

- The StrongMail PostgreSQL database schema is read-only from the library's perspective;
  the library never modifies database content.
- The session working copy store is expected to be reachable for all resolution calls
  that include a session ID. An unreachable store raises `WorkingCopyUnavailableError`;
  the library never silently falls back to graph-only resolution.
- SM_RULE conditions are stored as pre-parsed JSON ASTs in `dynamic_content_details.rule_ast`;
  the library reads and evaluates the AST — it does not parse raw rule text. The evaluation
  logic follows the behaviour documented in `samples/rule_engine.py` but is implemented
  from scratch in the new library.
- SM_RULE chains longer than 10 hops are treated as cycles; this limit is a safety
  bound and does not represent a known business constraint.
- The canonical form of a placeholder key is uppercase ASCII; locale and brand values
  supplied in the runtime context are also uppercased before namespace expansion.
- The library is consumed only by internal AI agents operating on trusted inputs;
  no user-facing input sanitisation beyond key normalisation is required.
- Each agent constructs a fresh resolution graph per invocation; the library does not
  manage a long-lived cache of graphs across sessions.
- The working copy store key format is `working-copy:{template_name}:{session_id}`; the
  library treats this as fixed and does not support alternative key schemes.
