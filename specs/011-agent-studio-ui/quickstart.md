# Quickstart: StrongMail Agent Studio

**Feature**: 011-agent-studio-ui
**Date**: 2026-05-27

## Dependencies

Ensure the following dependencies are installed in your environment:

```txt
streamlit>=1.32.0
pandas
nest_asyncio
```

## Running the Application

To start the Streamlit application, run the following command from the project root:

```bash
streamlit run app/main.py
```

## Testing

The testing strategy focuses on the session helpers and integration with the ADK agents:

- Use `pytest` and `pytest-asyncio` for testing `session.py` helpers.
- **No mocking of ADK agents**: Use real agents with a real PostgreSQL database and Redis instance.
- **Smoke test**: Open a template, verify the working copy is populated correctly, and send one chat message.
- **Integration test**: Edit the working copy via the `data_editor` callback and verify that Redis is updated.
- **No browser/Selenium tests**: Streamlit component behavior is tested manually.
