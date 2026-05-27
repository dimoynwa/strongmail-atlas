# Research: Refactor Tone Suggestion Orchestrator

## Overview

This document consolidates research and technical decisions for the `ToneSuggestionSubagent` refactor. Since the user provided a highly prescriptive implementation plan in the prompt, there are no `NEEDS CLARIFICATION` items to resolve. The decisions below reflect the explicit constraints and requirements provided.

## Decisions

### 1. Two-Stage Key Classification
- **Decision**: Implement a two-stage classification process in `classify_keys`. Stage 1 uses deterministic name heuristics (suffixes and substrings). Stage 2 uses a single LLM call for ambiguous keys.
- **Rationale**: Deterministic heuristics are fast, 100% reliable, and cost nothing. They catch the vast majority of structural chrome (URLs, footer links, etc.). The LLM is only invoked for keys that cannot be definitively classified by name alone, reducing token usage and latency while maintaining high accuracy.
- **Alternatives considered**: Using only an LLM (too slow/expensive, prone to hallucination on obvious structural keys). Using only heuristics (too rigid, cannot handle poorly named keys that contain actual prose).

### 2. Orchestrator and Subagent Pattern
- **Decision**: Refactor `ToneSuggestionSubagent` into an orchestrator `LlmAgent` with no direct tools, delegating to four specialist subagents (`KeyClassifierAgent`, `SuggestAgent`, `ApplyAgent`, `UndoAgent`), each with a single tool.
- **Rationale**: This is the recommended pattern for complex workflows in the Google GenAI ADK. It splits the monolithic instruction prompt into focused, single-responsibility prompts, which significantly improves instruction adherence for models like Gemini Flash.
- **Alternatives considered**: Keeping the monolithic agent but improving the prompt (already attempted, led to degradation). Using `AgentTool` instead of true subagents (explicitly forbidden by the user's prompt).

### 3. Session State Data Flow Contract
- **Decision**: Strictly manage data flow between subagents using `session.state`. The orchestrator writes `eligible_keys`. `KeyClassifierAgent` reads `eligible_keys` and writes `tone_bearing_keys` and `structural_keys`. `SuggestAgent` reads `tone_bearing_keys` and writes `suggestions` and `suggestion_id`. `ApplyAgent` reads `suggestions` and `suggestion_id`.
- **Rationale**: This creates a clear, decoupled pipeline where each agent only has access to the data it needs. It prevents `SuggestAgent` from accidentally processing structural keys and enforces the human-in-the-loop confirmation gate (by requiring `suggestion_id` for `ApplyAgent`).
- **Alternatives considered**: Passing data directly between tools (violates ADK agent isolation principles).

### 4. Snapshot and Undo Mechanism
- **Decision**: `ApplyAgent` captures a pre-apply snapshot to Redis before any working copy writes. `UndoAgent` restores from this snapshot, using `hdel` for keys marked with `SNAPSHOT_NONE_SENTINEL`.
- **Rationale**: Ensures safe experimentation. The all-or-nothing snapshot guarantees that if the application fails mid-way, the state is not corrupted. The sentinel handling correctly removes keys that were added by the suggestion rather than just modified.
- **Alternatives considered**: No undo mechanism (unacceptable UX). Partial snapshots (too complex to reason about during rollback).