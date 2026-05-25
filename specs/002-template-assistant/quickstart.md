# Quickstart: Template Assistant Agent

## Prerequisites
- Python 3.11+
- PostgreSQL running (with `template_details` and `template_tone_evaluations` tables)
- Redis running
- `google-adk`, `transformers`, `trafilatura`, `asyncpg`, `redis-py` installed

## Running the Agent

The agent is designed to be run within the ADK runtime. To test it interactively:

```python
import asyncio
from google_adk import AgentRuntime
from template_assistant.agent import TemplateAssistantAgent

async def main():
    agent = TemplateAssistantAgent()
    runtime = AgentRuntime(agent)
    
    # Inject required session context
    session_state = {
        "session_id": "test-session-123",
        "template_name": "WelcomeEmail",
        "lang_local": "en-US",
        "param_cust_brand": "BrandX"
    }
    
    print("Agent: Hi! I'm ready to help you with the WelcomeEmail template (en-US, BrandX).")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        response = await runtime.invoke(user_input, session_state=session_state)
        print(f"Agent: {response}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Running Tests

Tests are written using `pytest` and `pytest-asyncio`.

```bash
# Run all tests for the template assistant
pytest template_assistant/tests/

# Run unit tests for a specific subagent (does not boot full ADK runtime)
pytest template_assistant/tests/test_tone_suggestion_subagent.py

# Run the end-to-end multi-turn conversation test
pytest template_assistant/tests/test_e2e_agent.py
```