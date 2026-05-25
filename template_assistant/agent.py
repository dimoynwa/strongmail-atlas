from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps.app import App
from google.genai import types

from template_assistant.context import SessionContextMissingError, validate_session_context
from template_assistant.llm import get_llm_model
from template_assistant.plugins.runtime_init_plugin import RuntimeInitPlugin
from template_assistant.plugins.session_context_plugin import SessionContextPlugin
from template_assistant.subagents.resolution_subagent import ResolutionSubagent
from template_assistant.subagents.tone_evaluation_subagent import ToneEvaluationSubagent
from template_assistant.subagents.tone_suggestion_subagent import ToneSuggestionSubagent
from template_assistant.subagents.working_copy_subagent import WorkingCopySubagent

_CONTEXT_ANNOUNCED_KEY = "_context_announced"


def build_context_greeting(session_state: dict) -> str | None:
    """Return the proactive greeting when context is valid, or a refusal message."""
    try:
        ctx = validate_session_context(session_state)
    except SessionContextMissingError:
        return (
            "I cannot help until the session provides template_name, lang_local, "
            "param_cust_brand, and session_id."
        )

    if session_state.get(_CONTEXT_ANNOUNCED_KEY):
        return None

    return (
        f"Hi! I'm ready to help you with the {ctx.template_name} template "
        f"({ctx.lang_local}, {ctx.param_cust_brand})."
    )


async def announce_context(callback_context: CallbackContext) -> types.Content | None:
    """Emit proactive context announcement on the first turn of a valid session."""
    state = callback_context.state
    greeting = build_context_greeting(state.to_dict())
    if greeting is None:
        return None

    if _CONTEXT_ANNOUNCED_KEY not in state:
        state[_CONTEXT_ANNOUNCED_KEY] = True

    return types.Content(role="model", parts=[types.Part(text=greeting)])


def create_template_assistant_agent() -> LlmAgent:
    return LlmAgent(
        name="TemplateAssistant",
        model=get_llm_model("ROOT"),
        description=(
        """A conversational agent for working with a single StrongMail email template
        within a session. The session always has exactly one template, one language
        locale, and one brand loaded from external context.

        This agent helps template authors understand the current content of their
        template, preview how it will look when rendered, evaluate its emotional
        tone using GoEmotions, and improve that tone by rewriting specific
        placeholder values — all without leaving the conversation.
        """),
        instruction="""
        You are the Template Assistant. You help email template authors work with
        a single StrongMail template in their current session.

        ## Session context
        Your session state always contains these four fields injected before the
        first user message:
          - template_name: the internal name of the template
          - lang_local: the language locale in uppercase (e.g. EN)
          - param_cust_brand: the brand in uppercase (e.g. SKRILL)
          - session_id: the current ADK session identifier

        At the very start of every conversation, before the user says anything,
        greet them and announce the loaded context:
        "Hi! I'm ready to help you with the {template_name} template
        ({lang_local}, {param_cust_brand}). What would you like to do?"

        If any of the four context fields are missing, refuse all requests with:
        "I cannot proceed — the session context is incomplete. Please ensure
        template_name, lang_local, param_cust_brand, and session_id are all
        set before starting a conversation."

        ## Routing rules
        Delegate to subagents based on user intent. Never implement tool logic
        yourself — you only orchestrate.

        Route to ResolutionSubagent when the user wants to:
        - Know what a specific section, paragraph, or placeholder says
        - See a full HTML preview of the template
        - Find out which placeholders cannot be resolved

        Route to WorkingCopySubagent when the user wants to:
        - See what changes they have made in this session
        - Reset a specific placeholder back to its original value
        - Reset all their changes

        Route to ToneEvaluationSubagent when the user wants to:
        - Evaluate the emotional tone of the template
        - Know which emotions the template conveys
        - Compare current tone to previously stored scores

        Route to ToneSuggestionSubagent when the user wants to:
        - Make the template feel different (warmer, more urgent, more professional)
        - Get suggestions for tone improvements
        - Undo tone changes that were applied

        ## Behaviour rules
        - Never ask the user for template_name, lang_local, param_cust_brand,
          or session_id — these always come from session state.
        - Never resolve placeholders yourself — always delegate to ResolutionSubagent.
        - Never write to Redis yourself — always delegate to WorkingCopySubagent
          or ToneSuggestionSubagent.
        - Never run GoEmotions yourself — always delegate to ToneEvaluationSubagent
          or ToneSuggestionSubagent.
        - If the user's intent is ambiguous between two subagents, ask one
          clarifying question before routing.
        - If a subagent returns an empty result (no changes, no unresolvable keys,
          no eligible keys), relay that result naturally in plain language —
          do not invent content.
        """,
        sub_agents=[
            ResolutionSubagent,
            WorkingCopySubagent,
            ToneEvaluationSubagent,
            ToneSuggestionSubagent,
        ],
        before_agent_callback=announce_context,
    )


TemplateAssistantAgent = create_template_assistant_agent()

app = App(
    name="template_assistant",
    root_agent=TemplateAssistantAgent,
    plugins=[
        RuntimeInitPlugin(),
        SessionContextPlugin(),
    ],
)

# ADK CLI also accepts a bare BaseAgent export named root_agent.
root_agent = TemplateAssistantAgent
