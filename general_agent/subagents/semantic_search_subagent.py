from __future__ import annotations

from google.adk.agents import LlmAgent

from general_agent.ml.embeddings import encode_query
from general_agent.models import TemplateSearchResult, clamp_limit
from shared.db import get_pool
from shared.embeddings import semantic_search_by_embedding
from template_assistant.llm import get_llm_model


async def semantic_search_templates(
    query: str,
    limit: int = 10,
) -> list[TemplateSearchResult]:
    """Find templates by natural-language intent using pgvector cosine similarity."""
    effective_limit = clamp_limit(limit)
    embedding = encode_query(query)
    pool = get_pool()
    return await semantic_search_by_embedding(pool, embedding, effective_limit)


async def _semantic_search_templates_tool(
    query: str,
    limit: int = 10,
) -> list[dict]:
    results = await semantic_search_templates(query, limit=limit)
    return [result.to_dict() for result in results]


def create_semantic_search_subagent() -> LlmAgent:
    return LlmAgent(
        name="SemanticSearchSubagent",
        model=get_llm_model("SEMANTIC_SEARCH"),
        description="""
        Finds templates by natural language intent using semantic similarity search
        over pre-computed summary embeddings. Read-only; never writes to any store.
        """,
        instruction="""
        You are the Semantic Search Subagent. You find templates whose purpose
        matches a user's natural language description.

        ## Your tool
        - semantic_search_templates: encodes the query with all-mpnet-base-v2 and
          searches template_details.summary_embeded via pgvector cosine distance.
          Results are ordered by similarity (closest first).

        ## Behaviour rules
        - Always call semantic_search_templates for intent-based discovery requests.
        - Respect the limit parameter (default 10, maximum 50).
        - When no results are returned, tell the user no matching templates were found.
        - Never write to PostgreSQL or Redis.
        """,
        tools=[_semantic_search_templates_tool],
    )


SemanticSearchSubagent = create_semantic_search_subagent()
