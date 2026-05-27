# Technical Research & Decisions

**Feature**: Google ADK General Agent

## 1. Semantic Search Model
- **Decision**: Use `sentence-transformers/all-mpnet-base-v2` (768 dimensions).
- **Rationale**: Provides high-quality sentence embeddings suitable for natural language intent matching. Loaded as a module-level singleton via `get_encoder()` in `general_agent/ml/embeddings.py` to avoid instantiation overhead during tool calls.
- **Alternatives considered**: OpenAI embeddings (rejected due to cost/latency and requirement for local pgvector matching), smaller models like `all-MiniLM-L6-v2` (rejected in favor of higher quality `mpnet`).

## 2. Vector Search Implementation
- **Decision**: Use `pgvector` with the `<=>` (cosine distance) operator.
- **Rationale**: The embeddings are stored in `template_details.summary_embeded`. Cosine distance is the standard metric for `sentence-transformers`. Results are ordered ascending by distance (closer = more similar) with a strict `LIMIT`.
- **Alternatives considered**: Euclidean distance (`<->`) or inner product (`<#>`). Cosine distance is recommended for `all-mpnet-base-v2`.

## 3. Subagent Architecture
- **Decision**: Use true Google ADK subagents via `sub_agents=[]` on the root `GeneralAgent`.
- **Rationale**: Allows the root agent to delegate to specialized subagents (Semantic, Keyword, Structural, Tone) based on the user's query.
- **Alternatives considered**: `AgentTool` (explicitly rejected by requirements).

## 4. State Management
- **Decision**: The agent is completely stateless.
- **Rationale**: Requires no session context, no working copy, and no per-user Redis state. All subagents are strictly read-only and never write to PostgreSQL or Redis.
- **Alternatives considered**: Stateful conversational memory (rejected as the agent is designed for stateless discovery and audit).