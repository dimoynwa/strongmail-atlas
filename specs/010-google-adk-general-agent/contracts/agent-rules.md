# Contracts: Google ADK General Agent

## 1. Root Agent Fan-Out Rules
- The root `GeneralAgent` may delegate to multiple subagents simultaneously when a query spans more than one retrieval strategy.
- The results from these multiple subagents MUST be merged into a single coherent response.
- **Example**: "Find password-related templates that feel reassuring" requires delegating to `SemanticSearchSubagent` (for "password-related") and `ToneDiscoverySubagent` (for "reassuring"), then merging the results.

## 2. Shared Module Access
- **`general_agent/ml/embeddings.py`**: `SemanticSearchSubagent` is the ONLY subagent that may call this module (via the `encode_query(text: str)` helper).
- **Shared Modules**: All subagents may call `shared/embeddings.py` and `shared/db.py`.
- **Subagent Isolation**: No subagent may import from another subagent.

## 3. Read-Only Constraint
- **STRICT RULE**: No subagent may write to PostgreSQL or Redis under any circumstances. All database interactions MUST be `SELECT` queries.

## 4. Tool Signatures

**Note on Limits**: All search and discovery tools accept a `limit` parameter with a default of 10. The maximum allowed limit is 50.

### SemanticSearchSubagent
```python
def semantic_search_templates(query: str, limit: int = 10) -> list[TemplateSearchResult]:
    ...
```

### KeywordSearchSubagent
```python
def keyword_search_templates(query: str, fields: list[str] = ["name", "subject", "summary"], limit: int = 10) -> list[TemplateSearchResult]:
    ...
```

### StructuralQuerySubagent
```python
def find_templates_by_content_block(content_block_id: str, limit: int = 10) -> list[TemplateSearchResult]:
    ...

def find_templates_by_dynamic_content_rule(rule_id: str, limit: int = 10) -> list[TemplateSearchResult]:
    ...

def get_template_resolution_health(template_name: str) -> ResolutionHealthResult:
    ...

def get_template_structure_summary(template_name: str) -> StructuralSummary:
    ...
```

### ToneDiscoverySubagent
- **Data Source**: The `ToneDiscoverySubagent` MUST read from `template_tone_evaluations` only. It MUST NEVER call the GoEmotions classifier at query time; scores are pre-computed by the offline pipeline.

```python
def find_templates_by_tone(emotion: str, min_score: float = 0.5, lang_local: str = "EN", param_cust_brand: str = "SKRILL", limit: int = 10) -> list[ToneDiscoveryResult]:
    ...

def rank_templates_by_emotion(emotion: str, lang_local: str = "EN", param_cust_brand: str = "SKRILL", limit: int = 10) -> list[ToneDiscoveryResult]:
    ...
```
