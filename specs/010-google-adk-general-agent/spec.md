# Feature Specification: Google ADK General Agent

**Feature Branch**: `010-google-adk-general-agent`

**Created**: May 27, 2026

**Status**: Draft

**Input**: User description: "Build a Google ADK conversational agent called the General Agent. This agent answers discovery and audit questions that span the entire StrongMail template catalogue. It is stateless — it requires no session context and holds no per-user state. It never writes to any store. WHAT it does: The General Agent lets users find templates by intent, keyword, structure, or emotional tone. It uses four subagents to handle different retrieval strategies: semantic similarity search, keyword/full-text search, SQL-based structural queries, and tone-based discovery. WHY it exists: The StrongMail database contains many templates that are difficult to discover without knowing their exact names. Template authors and operations teams need a conversational interface to find the right template, audit structural relationships, and identify templates by emotional character — without writing SQL directly. THE FOUR SUBAGENTS and what they do: 1. SemanticSearchSubagent — finds templates by natural language intent using pgvector cosine similarity search over template_details.summary_embeded. 2. KeywordSearchSubagent — finds templates by exact term matching using PostgreSQL full-text search over template name, subject, and summary. 3. StructuralQuerySubagent — answers questions about template composition and resolution health using direct SQL queries. 4. ToneDiscoverySubagent — finds and ranks templates by emotional tone scores stored in template_tone_evaluations. KEY BEHAVIORS: STATELESS — The General Agent requires no session context. It has no session state, no working copy, no per-user Redis state. Every request is independent. READ-ONLY — The agent never writes to PostgreSQL or Redis. All four subagents are purely read-only. SEMANTIC SEARCH MODEL — SemanticSearchSubagent encodes the user's query at runtime using sentence-transformers/all-mpnet-base-v2 (768 dimensions), loaded as a module-level singleton via get_encoder() in general_agent/ml/embeddings.py. The query vector is matched against template_details.summary_embeded using pgvector cosine distance (<=>) operator. The column name is summary_embeded (one 'd'). RESULT LIMITS — All search and discovery tools must accept a limit parameter (default: 10, max: 50) to prevent unbounded result sets. MULTI-STRATEGY QUERIES — The root agent may delegate to more than one subagent for a single user query when multiple strategies are relevant. For example, "find password-related templates that feel reassuring" should combine SemanticSearchSubagent and ToneDiscoverySubagent results. NO RESOLUTION AT QUERY TIME — The agent never resolves placeholder tokens as part of answering a query. Resolution health data comes from pre-computed structural queries against the database, not from running the resolution engine. SUBAGENT PATTERN — Use true Google ADK subagents via sub_agents=[] on the root agent. Never use AgentTool for subagent delegation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find Templates by Natural Language Intent (Priority: P1)

Template authors and operations teams need to find templates using natural language descriptions of their intent, so they can locate templates without knowing exact names.

**Why this priority**: Discoverability is the primary goal of the General Agent. Semantic search provides the most flexible way to find templates based on what they do.

**Independent Test**: Can be fully tested by asking the agent to find templates for a specific purpose (e.g., "Find a template for changing the password") and verifying that relevant templates are returned based on semantic similarity.

**Acceptance Scenarios**:

1. **Given** a catalogue of templates with embedded summaries (`summary_embeded`), **When** the user asks "Which template is used to welcome new users?", **Then** the agent returns a list of relevant welcome templates using semantic search.
2. **Given** a catalogue of templates, **When** the user asks "Find templates related to account suspension", **Then** the agent returns relevant templates, limited to the default of 10 results.

---

### User Story 2 - Find Templates by Keyword Match (Priority: P1)

Template authors and operations teams need to find templates by searching for exact terms in the template name, subject, or summary, so they can quickly locate templates when they know specific keywords.

**Why this priority**: Keyword search is a fundamental and highly reliable method for finding specific templates.

**Independent Test**: Can be fully tested by asking the agent to find templates containing a specific word (e.g., "Find templates with 'reset' in the subject") and verifying that only templates matching the keyword are returned.

**Acceptance Scenarios**:

1. **Given** a catalogue of templates, **When** the user asks "Which templates mention 'Skrill Wallet' in the body?", **Then** the agent returns templates containing that exact phrase.
2. **Given** a catalogue of templates, **When** the user asks "Find all templates whose name contains 'notification'", **Then** the agent returns matching templates.

---

### User Story 3 - Audit Template Structure and Health (Priority: P2)

Operations teams need to query the structural composition and resolution health of templates, so they can identify dependencies and potential issues without writing queries manually.

**Why this priority**: Auditing is crucial for maintaining a healthy template ecosystem, but secondary to basic discoverability.

**Independent Test**: Can be fully tested by asking the agent about template dependencies (e.g., "Which templates include content block 123?") and verifying that the correct templates are identified based on pre-computed structural data.

**Acceptance Scenarios**:

1. **Given** pre-computed structural data, **When** the user asks "Which templates use dynamic content rule 456?", **Then** the agent returns the list of templates using that rule.
2. **Given** pre-computed resolution health data, **When** the user asks "Which templates have the most unresolvable placeholders?", **Then** the agent returns a ranked list of templates with resolution issues.

---

### User Story 4 - Discover Templates by Emotional Tone (Priority: P2)

Template authors need to find and rank templates based on their emotional character, so they can ensure communications align with brand guidelines and desired user experience.

**Why this priority**: Tone discovery is a unique and valuable feature for content creators, though less frequently used than basic search.

**Independent Test**: Can be fully tested by asking the agent to find templates with a specific tone (e.g., "Find templates where urgency is above 0.7") and verifying that the returned templates match the criteria based on pre-computed tone evaluations.

**Acceptance Scenarios**:

1. **Given** pre-computed tone evaluations, **When** the user asks "Find templates with the highest admiration score", **Then** the agent returns a ranked list of templates based on that emotion.
2. **Given** pre-computed tone evaluations, **When** the user asks "Rank all templates by joy score for EN brand", **Then** the agent returns the appropriately ranked list.

---

### User Story 5 - Combine Multiple Search Strategies (Priority: P3)

Users need to find templates using a combination of intent, keywords, structure, and tone, so they can perform highly specific and nuanced searches.

**Why this priority**: Advanced querying provides significant power but is less common than single-strategy searches.

**Independent Test**: Can be fully tested by asking a complex query (e.g., "find password-related templates that feel reassuring") and verifying that the agent delegates to multiple specialized search capabilities to produce a combined result.

**Acceptance Scenarios**:

1. **Given** a complex user query, **When** the user asks "find password-related templates that feel reassuring", **Then** the agent delegates to both the semantic search and tone discovery capabilities to formulate a comprehensive answer.

### Edge Cases

- What happens when a search query returns no results? The agent should gracefully inform the user that no matching templates were found.
- What happens when a user asks the agent to modify a template? The agent must refuse the request, stating that it is strictly read-only.
- What happens when a user requests more than 50 results? The agent must cap the results at 50 and inform the user of the limit.
- What happens if the user asks a question unrelated to the template catalogue? The agent should clarify its purpose and decline to answer unrelated questions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a conversational interface for querying the template catalogue.
- **FR-002**: The system MUST be stateless, requiring no session context, no working copy, and no per-user state. It MUST NOT read or write any Redis state. Every request MUST be independent.
- **FR-003**: The system MUST be strictly read-only. It MUST NEVER modify any underlying data stores.
- **FR-004**: The system MUST support semantic similarity search using natural language intent via pgvector cosine distance (`<=>`) operator over `template_details.summary_embeded`. Results MUST be ordered ascending by distance (closer = more similar).
- **FR-004a**: The system MUST encode the user's query at runtime using `sentence-transformers/all-mpnet-base-v2` (768 dimensions), loaded as a module-level singleton via `get_encoder()` in `general_agent/ml/embeddings.py`. It MUST NEVER be instantiated inside a tool function.
- **FR-004b**: The project MUST list `sentence-transformers` as an explicit dependency.
- **FR-005**: The system MUST support keyword and full-text search over template name, subject, and summary.
- **FR-006**: The system MUST support structural queries to audit template composition and resolution health.
- **FR-007**: The system MUST support tone-based discovery to find and rank templates by emotional tone scores. The `ToneDiscoverySubagent` MUST read from `template_tone_evaluations` only. It MUST NEVER call the GoEmotions classifier at query time; scores are pre-computed by the offline pipeline.
- **FR-008**: The system MUST allow combining multiple search strategies for a single user query. The root agent MAY delegate to multiple subagents for a single query and merge their results into a coherent response.
- **FR-009**: The system MUST NOT resolve placeholder tokens as part of answering a query. The structural query for unresolvable placeholders MUST be a SQL-based count against `body_placeholder_keys` and `content_block_kv` — not a live resolution run.
- **FR-010**: The system MUST enforce result limits on all search and discovery interactions (default: 10, max: 50).

### Key Entities

- **Template**: Represents a template with attributes like name, subject, summary, and embedded summary vector (`summary_embeded`).
- **Content Block**: A reusable block of content included in templates.
- **Dynamic Content Rule**: A rule used to dynamically alter template content.
- **Tone Evaluation**: Pre-computed emotional tone scores for a template.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can successfully retrieve relevant templates using natural language queries without knowing exact template names.
- **SC-002**: Users can successfully retrieve relevant templates using exact keyword matches.
- **SC-003**: Users can successfully identify templates using specific content blocks or dynamic content rules.
- **SC-004**: Users can successfully find templates matching specific emotional tone criteria.
- **SC-005**: The system responds to queries without modifying any underlying data stores.
- **SC-006**: The system correctly limits result sets to a maximum of 50 items per query.

## Assumptions

- The underlying data store is populated with template details and tone evaluations data.
- The summary data is populated with vectors generated by a semantic search model.
- Pre-computed resolution health data is available in the data store.
- The user is authorized to view the template catalogue metadata.
