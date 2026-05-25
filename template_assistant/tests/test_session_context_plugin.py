import pytest

from template_assistant.plugins.session_context_plugin import (
    SessionContextPlugin,
    default_session_state_from_env,
)


@pytest.mark.asyncio
async def test_session_context_plugin_seeds_state(monkeypatch):
    monkeypatch.setenv("TEMPLATE_NAME", "WelcomeEmail")
    monkeypatch.setenv("LANG_LOCAL", "EN-US")
    monkeypatch.setenv("PARAM_CUST_BRAND", "BrandX")

    session = type("Session", (), {"id": "sess-42", "state": {}})()
    invocation_context = type(
        "InvocationContext",
        (),
        {"session": session},
    )()

    plugin = SessionContextPlugin()
    await plugin.before_run_callback(invocation_context=invocation_context)

    assert session.state == {
        "session_id": "sess-42",
        "template_name": "WelcomeEmail",
        "lang_local": "EN-US",
        "param_cust_brand": "BrandX",
    }


def test_default_session_state_from_env(monkeypatch):
    monkeypatch.setenv("TEMPLATE_NAME", "T1")
    monkeypatch.setenv("LANG_LOCAL", "EN")
    monkeypatch.setenv("PARAM_CUST_BRAND", "SKRILL")
    assert default_session_state_from_env() == {
        "template_name": "T1",
        "lang_local": "EN",
        "param_cust_brand": "SKRILL",
    }
