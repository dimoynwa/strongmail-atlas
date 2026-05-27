import pytest

from general_agent.subagents.keyword_search_subagent import keyword_search_templates
from tests.general_agent.conftest import seed_template


@pytest.mark.asyncio
async def test_keyword_search_matches_subject(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-reset",
        template_name="AccountReset",
        subject="Password reset instructions",
        summary="Help users reset their password.",
    )
    await seed_template(
        db_pool,
        template_id="tpl-welcome",
        template_name="WelcomeEmail",
        subject="Welcome to our service",
        summary="Greet new users.",
    )

    results = await keyword_search_templates("reset", fields=["subject"], limit=10)

    assert len(results) == 1
    assert results[0].template_name == "AccountReset"
    assert results[0].source == "keyword_search"


@pytest.mark.asyncio
async def test_keyword_search_matches_name(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-1",
        template_name="notification_alert",
        subject="Alert",
        summary="System alert message.",
    )

    results = await keyword_search_templates("notification", fields=["name"], limit=10)

    assert len(results) == 1
    assert results[0].template_name == "notification_alert"
