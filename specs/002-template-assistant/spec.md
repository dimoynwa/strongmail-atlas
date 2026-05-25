# Feature Specification: Template Assistant

**Feature Branch**: `002-template-assistant`

**Created**: 2026-05-24

**Status**: Draft

**Input**: User description: "Build a Google ADK conversational agent called the Template Assistant. This agent allows users to query, preview, edit and improve the emotional tone of a StrongMail email template within a single session. WHAT it does: The agent is given a template name, language locale, and brand via session context at startup. Using that context it can answer questions about the template's resolved content, show a full HTML preview, evaluate the emotional tone using GoEmotions, suggest and apply tone rewrites to specific placeholder values, and allow the user to undo those changes — all within a single conversational session. WHY it exists: Email template authors need to understand and control the emotional tone of their communications. The template content is split across many database tables and must be resolved through a placeholder system before it can be read or evaluated. This agent abstracts that complexity and provides a natural language interface for working with a single template. WHAT it does NOT do: It does not search across templates. It does not write to PostgreSQL. It does not persist changes beyond the current session. It does not evaluate tone automatically — only when the user asks. SESSION CONTEXT: Three values are always injected into the agent session before the first user message: template_name, lang_local, param_cust_brand. The agent refuses to answer any question if these are missing. The user never needs to state them. CORE USER STORIES: As a template author, I want to ask what a specific section of the template says so that I can understand the current content without opening the editor. As a template author, I want to see a full resolved HTML preview of the template so that I can review it as it would appear to recipients. As a template author, I want to know which placeholders in the template cannot be resolved under the current context so that I can identify and fix data quality issues. As a template author, I want to ask what changes I have made to the template in this session so that I can review my working copy before committing. As a template author, I want to reset a specific placeholder or all my changes back to the original database values so that I can start over without ending the session. As a template author, I want to ask the agent to evaluate the emotional tone of the template so that I can understand how recipients are likely to feel reading it. As a template author, I want to tell the agent to make the template feel more reassuring, and have it suggest rewrites for the specific placeholder values that drive that change, so that I can achieve my desired tone efficiently. As a template author, I want the suggested rewrites to be applied immediately and be able to undo them individually or all at once so that I can experiment safely. As a template author, I want tone suggestions to be based on the current working copy state so that suggestions are coherent with changes I have already made."

## Clarifications

- Q: How should the meaningful text be extracted from the HTML string before sending it to the GoEmotions model? → A: Use the `trafilatura` Python library (to cleanly strip HTML, headers, footers, and navigation).

- Q: How should the agent determine which placeholder keys are eligible for tone rewriting? → A: Rule-based heuristics (e.g., exclude keys ending in `_URL`, `_COLOR`, `_ID`, or values starting with `http`).
- Q: Should the undo snapshot restore keys to their pre-suggestion working copy value, or to the original graph value? → A: Pre-suggestion working copy value (preserves any manual edits the user made earlier in the session).
- Q: What should the agent do when GoEmotions returns low confidence scores across all labels? → A: Always report the top scores (regardless of how low the absolute confidence values are).
- Q: Should the agent proactively tell the user what template it is working on at the start of the conversation? → A: Proactively announce (e.g., "Hi! I'm ready to help you with the `WelcomeEmail` template (en-US, BrandX).").
- Q: What should the ToneSuggestionSubagent do when it cannot find any rewriteable keys? → A: Inform the user (explain that no eligible text placeholders were found to rewrite).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Template Content (Priority: P1)

As a template author, I want to ask what a specific section of the template says so that I can understand the current content without opening the editor.

**Why this priority**: Understanding the current content is the foundation for any further interaction or modification.

**Independent Test**: Can be fully tested by asking the agent about a specific paragraph or section and verifying the response matches the resolved template content.

**Acceptance Scenarios**:

1. **Given** a valid session context with a template name, **When** the user asks "What does paragraph 1 say?", **Then** the agent responds with the resolved text of paragraph 1.
2. **Given** a valid session context, **When** the user asks "What is the current value of EN.CTA_BUTTON_TEXT?", **Then** the agent responds with the resolved value of that specific placeholder.

---

### User Story 2 - Full HTML Preview (Priority: P1)

As a template author, I want to see a full resolved HTML preview of the template so that I can review it as it would appear to recipients.

**Why this priority**: Authors need to see the complete picture to understand the overall structure and flow before making tone adjustments.

**Independent Test**: Can be fully tested by asking for a preview and verifying the returned HTML represents the fully resolved template.

**Acceptance Scenarios**:

1. **Given** a valid session context, **When** the user asks "Show me the full preview of this template", **Then** the agent returns the complete, resolved HTML body.

---

### User Story 3 - Identify Unresolvable Placeholders (Priority: P2)

As a template author, I want to know which placeholders in the template cannot be resolved under the current context so that I can identify and fix data quality issues.

**Why this priority**: Data quality is crucial, but secondary to basic content retrieval.

**Independent Test**: Can be fully tested by asking for unresolvable placeholders and verifying the agent lists the correct ones based on the current context.

**Acceptance Scenarios**:

1. **Given** a template with missing data for the current context, **When** the user asks "Which placeholders cannot be resolved?", **Then** the agent provides a list of the unresolvable placeholders.

---

### User Story 4 - Evaluate Emotional Tone (Priority: P1)

As a template author, I want to ask the agent to evaluate the emotional tone of the template so that I can understand how recipients are likely to feel reading it.

**Why this priority**: This is a core value proposition of the agent, enabling authors to understand the emotional impact of their templates.

**Independent Test**: Can be fully tested by asking for a tone evaluation and verifying the agent returns a breakdown of emotional scores.

**Acceptance Scenarios**:

1. **Given** a valid session context, **When** the user asks "Evaluate the tone of this template", **Then** the agent returns a list of emotions and their corresponding scores based on the current resolved content.

---

### User Story 5 - Suggest and Apply Tone Rewrites (Priority: P1)

As a template author, I want to tell the agent to make the template feel more reassuring, and have it suggest rewrites for the specific placeholder values that drive that change, so that I can achieve my desired tone efficiently. I want the suggested rewrites to be applied immediately.

**Why this priority**: This is the primary action the agent facilitates, allowing authors to actively improve their templates.

**Independent Test**: Can be fully tested by requesting a tone change, verifying the agent suggests appropriate rewrites, and confirming those rewrites are immediately reflected in the working copy.

**Acceptance Scenarios**:

1. **Given** a valid session context, **When** the user asks "Make this template feel more reassuring", **Then** the agent suggests rewrites for specific placeholders, shows the current vs. suggested values, and applies the changes to the working copy.

---

### User Story 6 - Review Working Copy Changes (Priority: P2)

As a template author, I want to ask what changes I have made to the template in this session so that I can review my working copy before committing.

**Why this priority**: Essential for tracking progress and understanding the current state of modifications within the session.

**Independent Test**: Can be fully tested by making changes, asking for a summary of changes, and verifying the agent lists the modified placeholders and their new values.

**Acceptance Scenarios**:

1. **Given** a session with modified placeholders, **When** the user asks "What have I changed so far?", **Then** the agent lists all placeholders that have been overridden in the current session.

---

### User Story 7 - Undo Tone Suggestions (Priority: P2)

As a template author, I want to be able to undo suggested rewrites individually or all at once so that I can experiment safely.

**Why this priority**: Provides a safety net for experimentation, crucial for a good user experience when modifying content.

**Independent Test**: Can be fully tested by applying a tone suggestion, asking to undo it, and verifying the placeholder reverts to its previous state in the working copy.

**Acceptance Scenarios**:

1. **Given** recently applied tone suggestions, **When** the user asks "Undo the tone changes you just made", **Then** the agent reverts the affected placeholders to their pre-suggestion values.
2. **Given** recently applied tone suggestions affecting multiple placeholders, **When** the user asks "Undo only the changes to paragraph 1", **Then** the agent reverts only the placeholder corresponding to paragraph 1.

---

### User Story 8 - Reset Working Copy (Priority: P3)

As a template author, I want to reset a specific placeholder or all my changes back to the original database values so that I can start over without ending the session.

**Why this priority**: Useful for starting fresh, but less frequently used than targeted undo operations.

**Independent Test**: Can be fully tested by making changes, asking to reset all changes, and verifying the working copy is cleared.

**Acceptance Scenarios**:

1. **Given** a session with modified placeholders, **When** the user asks "Reset all my changes", **Then** the agent clears the entire working copy for the session.
2. **Given** a session with modified placeholders, **When** the user asks "Reset paragraph 1 back to its original value", **Then** the agent removes the override for that specific placeholder from the working copy.

---

### Edge Cases

- What happens when the user asks a question but the session context (template_name, lang_local, param_cust_brand) is missing?
- What happens when the user asks to evaluate the tone of a template that consists mostly of unresolvable placeholders or non-text content (e.g., just images and links)?
- What happens when the user asks to undo a change, but no changes have been made yet in the current session?
- What happens when the user asks for tone suggestions, but the template contains no placeholders suitable for rewriting (e.g., only URLs, colors, or IDs)?
  - *Resolution*: The agent will inform the user that no eligible text placeholders were found to rewrite.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST validate the presence of `session_id`, `template_name`, `lang_local`, and `param_cust_brand` in the session context before processing any user request.
- **FR-002**: The system MUST refuse to answer questions and prompt the user if the required session context is missing.
- **FR-002b**: The system MUST proactively announce the loaded template context (name, locale, brand) at the start of a valid session.
- **FR-003**: The system MUST resolve template placeholders using the shared resolution engine.
- **FR-004**: The system MUST maintain a session-specific working copy to store temporary overrides for placeholder values.
- **FR-005**: The system MUST use the working copy values (if present) instead of the original database values when resolving the template.
- **FR-006**: The system MUST be able to evaluate the emotional tone of the resolved template text on demand, always reporting the top scores regardless of absolute confidence values. The text MUST be extracted from the HTML using a robust library (like `trafilatura`) to strip boilerplate (headers, footers, navigation) before evaluation. The evaluation MUST use the `SamLowe/roberta-base-go_emotions` model via the `transformers` pipeline with `top_k=None` (to return all 28 emotion labels). The model MUST be loaded once at the module level at agent startup, not per request.
- **FR-006b**: If the plain text extracted from the resolved HTML is fewer than 50 characters, the agent MUST warn the user that evaluation may be unreliable due to a high number of unresolvable placeholders, and still return whatever scores GoEmotions produces.
- **FR-007**: The system MUST map natural language tone requests (e.g., "more reassuring") to specific target emotion profiles (a `dict[emotion_label, float]` representing target weights). The agent may extend these via LLM reasoning but MUST use these as anchors:
  - "more reassuring" → high relief, high caring, low fear, low nervousness
  - "more urgent" → high desire, high nervousness
  - "warmer" → high joy, high love, high gratitude
  - "more professional" → high approval, low amusement, low excitement
- **FR-008**: The system MUST identify placeholders suitable for natural language rewriting using rule-based heuristics (e.g., excluding keys ending in `_URL`, `_COLOR`, `_ID`, or values starting with `http`).
- **FR-009**: The system MUST generate rewrite suggestions for suitable placeholders to align the template with the requested target tone. The ToneSuggestionSubagent MUST use the ADK agent's underlying LLM (Gemini) to generate rewrites. The LLM receives: the target emotion profile, the current resolved value of each eligible key, and the surrounding resolved template context. It MUST NOT hallucinate placeholder keys — only rewrite values of keys explicitly identified as eligible.
- **FR-010**: The system MUST automatically apply generated rewrite suggestions to the session's working copy.
- **FR-011**: The system MUST create a snapshot of the affected placeholders' values immediately before applying tone suggestions.
- **FR-012**: The system MUST provide the ability to undo applied tone suggestions by restoring values from the pre-suggestion snapshot (which preserves any prior manual edits made during the session).
- **FR-013**: The system MUST provide the ability to reset specific placeholders or the entire working copy back to their original state.
- **FR-014**: The system MUST NOT persist working copy changes to the permanent database.
- **FR-015**: The system MUST NOT search for information across multiple templates.

### Key Entities

- **Session Context**: Contains the `template_name`, `lang_local`, and `param_cust_brand` required to resolve a specific template instance.
- **Working Copy**: A temporary, session-scoped store of overridden placeholder values. The Redis key format MUST be `working-copy:{template_name}:{session_id}`.
- **Tone Evaluation**: A set of scores representing the emotional profile of the resolved template text.
- **Tone Suggestion**: A proposed rewrite for a specific placeholder value aimed at achieving a target emotional tone.
- **Working Copy Snapshot**: A temporary record of placeholder values captured immediately before applying a set of tone suggestions, used for undo operations. The Redis key format MUST be `working-copy-snapshot:{template_name}:{session_id}`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The agent correctly refuses 100% of requests when the required session context is missing.
- **SC-002**: Users can successfully retrieve the resolved content of specific template sections or the full HTML preview.
- **SC-003**: The agent accurately identifies and lists unresolvable placeholders based on the current context.
- **SC-004**: Tone evaluations are generated successfully upon request and reflect the current state of the working copy.
- **SC-005**: Users can request a tone change, receive suggestions, and have them automatically applied to the working copy in a single interaction.
- **SC-006**: Users can successfully undo applied tone suggestions, restoring the exact previous state of the affected placeholders.
- **SC-007**: Users can successfully review all changes made in the current session.

## Assumptions

- The underlying shared resolution engine is fully functional and accessible to the agent.
- The GoEmotions model (or equivalent) is available locally for tone evaluation.
- A mechanism exists (e.g., Redis) to store and retrieve the session-specific working copy and snapshots.
- The agent framework (Google ADK) supports the required conversational flow and tool execution.
- The user interacts with the agent through a text-based conversational interface.