import pytest

from template_assistant.context import (
    SessionContext,
    SessionContextMissingError,
    validate_session_context,
)


def test_valid_context_passes_validation():
    ctx = validate_session_context(
        {
            "template_name": "WelcomeEmail",
            "lang_local": "en-us",
            "param_cust_brand": "brandx",
            "session_id": "sess-1",
        }
    )
    assert ctx == SessionContext(
        template_name="WelcomeEmail",
        lang_local="EN-US",
        param_cust_brand="BRANDX",
        session_id="sess-1",
    )


@pytest.mark.parametrize(
    "missing_field",
    ["template_name", "lang_local", "param_cust_brand", "session_id"],
)
def test_missing_field_raises(missing_field):
    payload = {
        "template_name": "WelcomeEmail",
        "lang_local": "EN-US",
        "param_cust_brand": "BRANDX",
        "session_id": "sess-1",
    }
    payload[missing_field] = ""
    with pytest.raises(SessionContextMissingError):
        validate_session_context(payload)
