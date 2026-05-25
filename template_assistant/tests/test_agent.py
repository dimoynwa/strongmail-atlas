from unittest.mock import MagicMock

import pytest
from google.adk.sessions.state import State

from template_assistant.agent import (
    TemplateAssistantAgent,
    announce_context,
    build_context_greeting,
)
from template_assistant.subagents.resolution_subagent import ResolutionSubagent
from template_assistant.subagents.tone_evaluation_subagent import ToneEvaluationSubagent
from template_assistant.subagents.tone_suggestion_subagent import ToneSuggestionSubagent
from template_assistant.subagents.working_copy_subagent import WorkingCopySubagent


def test_greeting_for_valid_context():
    state = {
        "template_name": "WelcomeEmail",
        "lang_local": "en-us",
        "param_cust_brand": "brandx",
        "session_id": "sess-1",
    }
    greeting = build_context_greeting(state)
    assert greeting == (
        "Hi! I'm ready to help you with the WelcomeEmail template (EN-US, BRANDX)."
    )


def test_greeting_refused_when_context_missing():
    greeting = build_context_greeting({"session_id": "sess-1"})
    assert greeting is not None
    assert "cannot help" in greeting.lower()


def test_greeting_not_repeated_once_announced():
    state = {
        "template_name": "WelcomeEmail",
        "lang_local": "EN-US",
        "param_cust_brand": "BRANDX",
        "session_id": "sess-1",
        "_context_announced": True,
    }
    assert build_context_greeting(state) is None


@pytest.mark.asyncio
async def test_announce_context_with_adk_state():
    state = State(
        {
            "template_name": "WelcomeEmail",
            "lang_local": "en-us",
            "param_cust_brand": "brandx",
            "session_id": "sess-1",
        },
        {},
    )
    callback_context = MagicMock()
    callback_context.state = state

    result = await announce_context(callback_context)

    assert result is not None
    assert "WelcomeEmail" in result.parts[0].text
    assert state["_context_announced"] is True


def test_sub_agents_registered():
    agent = TemplateAssistantAgent
    names = {sub.name for sub in agent.sub_agents}
    assert names == {
        "ResolutionSubagent",
        "WorkingCopySubagent",
        "ToneEvaluationSubagent",
        "ToneSuggestionSubagent",
    }


def test_template_assistant_agent_singleton():
    from template_assistant.agent import app

    assert TemplateAssistantAgent.name == "TemplateAssistant"
    assert ResolutionSubagent in TemplateAssistantAgent.sub_agents
    assert WorkingCopySubagent in TemplateAssistantAgent.sub_agents
    assert ToneEvaluationSubagent in TemplateAssistantAgent.sub_agents
    assert ToneSuggestionSubagent in TemplateAssistantAgent.sub_agents
    assert app.name == "template_assistant"
    assert len(app.plugins) == 2
