# Feature Specification: Parse SM_RULE Text at Runtime

**Feature Branch**: `013-parse-rule-text-runtime`

**Created**: 2026-05-28

**Status**: Draft

**Input**: Change the Placeholder Resolution Engine so SM_RULE evaluation no longer reads
pre-parsed JSON from `dynamic_content_details.rule_ast`. Instead, load the raw StrongMail
rule DSL from `dynamic_content_details.rule_text` (the rule “text” column), parse it at
evaluation time with logic aligned to
`strongmail-email-resolution-system/src/email_resolution/services/dynamic_content_rule_engine.py`,
then evaluate the resulting AST using the existing condition and branch-normalisation behaviour.

**Related specs**: `001-placeholder-resolution-engine` (supersedes its SM_RULE data-source
assumption and FR-007 / clarification on `rule_ast` as authoritative).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Resolve SM_RULE from live rule text (Priority: P1)

An AI agent resolves a template that contains `SM_RULE_*` placeholders. For each rule, the
library loads the human-readable rule string from the database, parses it into the same AST
shape used today, evaluates conditions against the runtime context, and returns the correct
`then` or `else` branch value after normalisation.

**Why this priority**: This is the only behavioural change consumers care about. Rule text
becomes the single source of truth; stale or missing `rule_ast` rows no longer block
resolution when `rule_text` is valid.

**Independent Test**: Seed `dynamic_content_details` with `rule_text` for a known rule and
NULL or intentionally wrong `rule_ast`. Call `evaluate_sm_rule` with a context that satisfies
the condition. Assert the branch result matches the `then` value in `rule_text`, not `rule_ast`.

**Acceptance Scenarios**:

1. **Given** a row where `rule_text` is `If (PARAM_CUST_BRAND is equal to Neteller) Then ##BRAND_LOGO_NETELLER## Else ##BRAND_LOGO_SKRILL##` and `rule_ast` is NULL, **When** the rule is evaluated with `PARAM_CUST_BRAND=NETELLER`, **Then** the normalised `then` branch value is returned.
2. **Given** a row where `rule_text` is valid but `rule_ast` contains a different `then` value, **When** the rule is evaluated, **Then** the outcome follows `rule_text` exclusively.
3. **Given** a row where `rule_text` is empty or whitespace only, **When** the rule is evaluated, **Then** `ReasonCode.INVALID_RULE` is returned.
4. **Given** a row where `rule_text` does not start with `If` or yields no parseable conditions, **When** the rule is evaluated, **Then** `ReasonCode.INVALID_RULE` is returned.

---

### User Story 2 — Parser parity with email resolution engine (Priority: P2)

Operators and rule structure in production data use StrongMail natural-language phrases (e.g.
`is equal to`), not Python expressions. The parser must recognise the same operator set and
`If (…) Then … [Else …]` grammar as the reference dynamic content rule engine so parsed ASTs
match what StrongMail authors intended.

**Why this priority**: Incorrect parsing silently changes which branch fires, breaking brand
and locale-specific content.

**Independent Test**: Unit-test `parse_rule_to_ast` against a fixed corpus of rule strings
(including multi-clause conditions, parentheses, and `is null` / `is not null`) and assert
clause count, operators, variable keys, and `valid` flag without touching the database.

**Acceptance Scenarios**:

1. **Given** rule text `If (A is equal to 1 Or B is equal to 2) Then X`, **When** parsed, **Then** `valid` is true, `condition.combiner` is `or`, and two clauses are present with `variable_key` `A` and `B`.
2. **Given** rule text with `is greater than or equal to` before `is greater than` in the same clause, **When** parsed, **Then** the longer operator phrase is matched (longest-match-first).
3. **Given** rule text `If (FOO is not null) Then BAR`, **When** parsed, **Then** the clause has operator `is not null` and empty `value`.
4. **Given** rule text with nested parentheses in the condition, **When** parsed, **Then** `Or` / `And` inside parentheses do not split the condition prematurely.

---

### User Story 3 — Unchanged downstream evaluation semantics (Priority: P3)

After parsing, condition evaluation, branch selection, return-value normalisation, SM_RULE
chaining, and unresolvable reporting in the resolution pipeline must behave as they do today
for ASTs that were previously loaded from `rule_ast`.

**Why this priority**: Consumers depend on stable `ReasonCode` values and normalisation rules
(`####`→`##`, `SM_RULE_` chaining, etc.).

**Independent Test**: Re-run existing `_evaluate_condition` and `_normalize_return_value` tests
and integration tests that resolve templates with SM_RULE placeholders; only the DB column
and parse step change.

**Acceptance Scenarios**:

1. **Given** a parsed AST with `valid: true` and OR-combined clauses, **When** `_evaluate_condition` runs, **Then** supported operators behave identically to pre-change integration tests.
2. **Given** a parsed AST whose selected branch is an uppercase-only token, **When** normalised, **Then** `SM_RULE_{TOKEN}` is produced for chained resolution.
3. **Given** a rule name that does not exist in `dynamic_content`, **When** evaluated, **Then** `ReasonCode.MISSING_KEY` is returned (unchanged).

---

### Edge Cases

- `rule_text` is NULL while `rule_ast` is populated → treat as invalid rule (`INVALID_RULE`); do not fall back to `rule_ast`.
- Variable expressions use dot notation (e.g. `Context.PARAM_CUST_BRAND`) → `variable_key` is the uppercased last segment only.
- Condition combiner in the parser output is always `or` for split `Or`/`And` segments at depth zero; nested groups rely on parenthesis stripping per reference implementation.
- `And` between clauses at the top level is split into separate parts but still OR-combined in the AST (`combiner: "or"`) — preserve reference parser behaviour even if business rules rarely use `And`.
- Rule text with only `If`/`Then` and no `Else` → `else` is null; evaluator returns empty string for the false branch (current behaviour).
- Unicode or extra whitespace in rule text → trimming applies to the full rule and captured groups; matching is case-insensitive for operators and `If`/`Then`/`Else`.
- Numerical operators (`is greater than`, etc.) may appear in parsed clauses; evaluation must support them consistently with `dynamic_content_rule_engine` (numeric compare when possible, else lexicographic).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `evaluate_sm_rule` MUST load rule content from `dynamic_content_details.rule_text`
  via the existing `dynamic_content` / `dynamic_content_details` join keyed by rule name. It MUST
  NOT read or use `rule_ast` for evaluation.
- **FR-002**: The library MUST include a dedicated parser module that exposes
  `parse_rule_to_ast(content: str) -> dict` producing ASTs with:
  - `schema_version`: `1`
  - `kind`: `"strongmail_dynamic_content_rule"`
  - `valid`: true only when content is non-empty, starts with `If` (case-insensitive), and at
    least one condition clause was parsed
  - `condition`: `{ "combiner": "or", "clauses": [...] }` where each clause has
    `variable_expr`, `variable_key` (last dot-segment, uppercased), `operator`, and `value`
  - `then` and `else` branch strings (else may be null)
- **FR-003**: The parser MUST support these operators (longest match first, case-insensitive):
  `is equal to`, `is not equal to`, `contains`, `does not contain`, `is greater than or equal to`,
  `is less than or equal to`, `is greater than`, `is less than`, `is not one of`, `is one of`,
  `is not null`, `is null`.
- **FR-004**: The parser MUST parse the grammar
  `If (<condition>) Then <then> [Else <else>]` including parenthesised conditions and
  `Or` / `And` delimiters at depth zero outside nested parentheses.
- **FR-005**: Parser logic MUST stay aligned with
  `strongmail-email-resolution-system/.../dynamic_content_rule_engine.py` and the reference
  implementation in `samples/rule_engine.py` (`parse_rule_to_ast` / `_parse_rule`). StrongMail
  rules are not Python expressions; Python-only evaluators (e.g. asteval) MUST NOT be used.
- **FR-006**: After parsing, if `valid` is false, evaluation MUST return `ReasonCode.INVALID_RULE`
  without evaluating conditions.
- **FR-007**: Condition evaluation and branch normalisation in `sm_rule_evaluator` MUST remain
  unchanged except where needed to support all operators the parser can emit (including numeric
  comparisons if present in reference engine).
- **FR-008**: Integration tests and test fixtures MUST seed `rule_text` as the authoritative
  column; tests MUST NOT depend on pre-populated `rule_ast` for SM_RULE behaviour.
- **FR-009**: Documentation in `specs/001-placeholder-resolution-engine` data model and
  assumptions that mark `rule_ast` as authoritative MUST be treated as superseded by this
  feature once implemented (follow-up doc update in plan/tasks phase).

### Key Entities

- **Rule text (`rule_text`)**: Raw StrongMail dynamic content rule DSL stored in
  `dynamic_content_details`. Becomes the sole input for SM_RULE evaluation.
- **Rule AST**: In-memory JSON structure produced by `parse_rule_to_ast`; same schema as
  previously stored in `rule_ast`. Ephemeral at runtime — not required to be persisted by
  this library.
- **Dynamic content rule**: Named entity in `dynamic_content` (with or without `SM_RULE_`
  prefix) joined to its details row.
- **Clause**: One variable expression, natural-language operator, and comparison value (empty
  for null checks).

---

## Parser contract (implementation reference)

The following behaviour is normative for `parse_rule_to_ast` (equivalent to the user-supplied
reference implementation):

| Aspect | Rule |
|--------|------|
| Validity | `valid=false` if empty, missing leading `If`, or zero clauses after parse |
| Variable key | Last segment of dot-separated `variable_expr`, uppercased |
| Combiner | Always `"or"` in output `condition` |
| Null operators | `value` is empty string |
| Then/Else split | Last case-insensitive ` else ` separates branches |
| Operator matching | Longest operator name wins; regex case-insensitive |

Reference code to embed (or line-match) in `shared/resolution/rule_parser.py`:

```python
# parse_rule_to_ast, _parse_rule, _parse_condition, _split_by_or_and,
# _extract_variable, _extract_paren_content
# Constants: RULE_AST_SCHEMA_VERSION = 1, RULE_AST_KIND = "strongmail_dynamic_content_rule"
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of existing SM_RULE integration tests pass when fixtures provide only
  `rule_text` (with `rule_ast` null or ignored).
- **SC-002**: Parser unit tests cover at least 10 distinct rule strings including every
  operator family and an invalid/empty rule case.
- **SC-003**: For a sample of production-like rules, parsed `variable_key`, `operator`, `then`,
  and `else` match the reference `parse_rule_to_ast` output from `samples/rule_engine.py`.
- **SC-004**: No resolution code path reads `rule_ast` after this change (verified by code
  search / review).
- **SC-005**: SM_RULE resolution latency increases by less than 5 ms per rule on average
  compared to the `rule_ast` path (parse-once per `evaluate_sm_rule` call).

---

## Scope

**In scope**

- New `shared/resolution/rule_parser.py` (or equivalent) with `parse_rule_to_ast`
- `shared/resolution/sm_rule_evaluator.py` query and flow change
- Unit tests for parser; updates to `tests/integration/test_sm_rule_evaluator.py` and DB fixtures
- Spec/data-model corrections referencing `rule_text` as authoritative (during plan/implement)

**Out of scope**

- Writing or migrating `rule_ast` in the database
- Changing placeholder graph building or working-copy behaviour
- UI or template-assistant changes (unless they duplicate SM_RULE evaluation — separate follow-up)
- Replacing `_evaluate_condition` with a call into the external email-resolution service

---

## Assumptions

- Production PostgreSQL uses column name `rule_text` for the raw DSL (user input called this
  the “text column”; it is not a separate `text` column on `dynamic_content_details`).
- `rule_ast` may remain in the schema for other consumers but is irrelevant to this library
  after the change.
- Rule strings in `rule_text` follow the same authoring conventions as in the email resolution
  system export.
- Parse errors do not throw; they surface as `valid: false` and `INVALID_RULE` at evaluation.
- The library remains read-only with respect to database content.

---

## Clarifications

### Session 2026-05-28

- Q: Which database column holds the raw rule? → A: `dynamic_content_details.rule_text`
  (not `rule_ast`). User “text column” refers to this field.
- Q: Should we fall back to `rule_ast` when `rule_text` is missing? → A: No. Missing or
  unparseable `rule_text` → `INVALID_RULE`.
- Q: Where does parser logic live? → A: New module under `shared/resolution/`, copied from the
  provided reference implementation and kept in sync with `dynamic_content_rule_engine.py`.
