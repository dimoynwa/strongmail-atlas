import pytest

from general_agent.agent import GeneralAgent
from general_agent.subagents.semantic_search_subagent import SemanticSearchSubagent
from general_agent.subagents.semantic_search_subagent import semantic_search_templates
from general_agent.subagents.tone_discovery_subagent import (
    ToneDiscoverySubagent,
    find_templates_by_tone,
)
from tests.general_agent.conftest import seed_template


@pytest.mark.asyncio
async def test_fan_out_password_and_reassuring_tone(db_pool):
    """Multi-strategy query: semantic search + tone discovery."""
    await seed_template(
        db_pool,
        template_id="tpl-password",
        template_name="PasswordReset",
        summary="Secure password reset instructions for account recovery.",
        embed_summary="password reset template for changing account credentials",
        tones={"caring": 0.8, "approval": 0.6},
    )
    await seed_template(
        db_pool,
        template_id="tpl-harsh",
        template_name="PasswordLockout",
        summary="Account locked due to failed password attempts.",
        embed_summary="password lockout security warning email",
        tones={"anger": 0.7, "caring": 0.1},
    )

    semantic_results = await semantic_search_templates("password reset", limit=10)
    tone_results = await find_templates_by_tone("caring", min_score=0.5, limit=10)

    semantic_names = {result.template_name for result in semantic_results}
    tone_names = {result.template_name for result in tone_results}

    assert "PasswordReset" in semantic_names
    assert "PasswordReset" in tone_names
    assert "PasswordLockout" in semantic_names
    assert "PasswordLockout" not in tone_names

    overlap = semantic_names & tone_names
    assert overlap == {"PasswordReset"}


def test_general_agent_registers_all_subagents():
    subagent_names = {agent.name for agent in GeneralAgent.sub_agents}
    assert subagent_names == {
        SemanticSearchSubagent.name,
        ToneDiscoverySubagent.name,
        "KeywordSearchSubagent",
        "StructuralQuerySubagent",
    }


def test_general_agent_instruction_mentions_fan_out():
    instruction = GeneralAgent.instruction or ""
    assert "SemanticSearchSubagent" in instruction
    assert "ToneDiscoverySubagent" in instruction
    assert "password-related templates that feel reassuring" in instruction
