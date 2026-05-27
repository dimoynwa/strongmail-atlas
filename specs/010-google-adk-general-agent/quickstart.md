# Quickstart: Google ADK General Agent

## Overview
The General Agent is a stateless conversational interface for discovering and auditing StrongMail templates. It uses four specialized subagents to handle semantic search, keyword search, structural queries, and tone discovery.

## Prerequisites
- Python 3.11+
- PostgreSQL with `pgvector` extension installed and populated with template data.
- `sentence-transformers` package installed.

## Setup
1. **Database**: Ensure PostgreSQL is running with the `pgvector` extension enabled. Set the `DATABASE_URL` environment variable with your connection string.
2. **Dependencies**: Ensure `sentence-transformers` is installed (`pip install sentence-transformers`).
3. **Pre-download Model**: Download the `all-mpnet-base-v2` model before running the agent to avoid startup delays:
   ```bash
   python -c "from general_agent.ml.embeddings import get_encoder; get_encoder()"
   ```
4. **Redis**: Note that **no Redis instance is required** for the General Agent. It is completely stateless.

## Usage
The agent is exported for the Google ADK framework. It requires no session context and no Redis.

```python
from general_agent.agent import GeneralAgent, app, root_agent

# ADK CLI: adk web general_agent
# Programmatic tool access (no LLM):
from general_agent.subagents.semantic_search_subagent import semantic_search_templates
# results = await semantic_search_templates("password reset")
```

## Smoke Test
Verify the encoder and database connectivity:
```bash
uv run python -c "from general_agent.ml.embeddings import encode_query; print(len(encode_query('password reset')))"
uv run pytest tests/general_agent/integration/test_semantic_search.py -q
```

## Testing
Run the test suite using `pytest`:
```bash
pytest tests/general_agent/
```
Or with uv:
```bash
uv run pytest tests/general_agent/
```
Tests require a real PostgreSQL database (no mocks) but do not require Redis.
