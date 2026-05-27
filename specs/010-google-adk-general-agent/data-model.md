# Data Model: Google ADK General Agent

## Dataclasses

### TemplateSearchResult
Used by `SemanticSearchSubagent`, `KeywordSearchSubagent`, and `StructuralQuerySubagent` (for template lists).

- `template_id`: str
- `template_name`: str
- `summary`: str
- `score`: float (similarity score, relevance score, etc.)
- `source`: str (e.g., "semantic_search", "keyword_search", "content_block")

### ToneDiscoveryResult
Used by `ToneDiscoverySubagent`.

- `template_id`: str
- `template_name`: str
- `emotions`: dict[str, float] (mapping of emotion names to scores)
- `evaluated_at`: datetime

### StructuralSummary
Used by `StructuralQuerySubagent` for aggregate structure queries.

- `template_id`: str
- `template_name`: str
- `content_block_count`: int
- `placeholder_count`: int
- `unresolvable_count`: int

### ResolutionHealthResult
Used by `StructuralQuerySubagent` for health queries.

- `template_id`: str
- `template_name`: str
- `total_keys`: int
- `unresolvable_keys`: int
- `health_score`: float (0.0–1.0)
