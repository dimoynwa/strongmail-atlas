import pytest

from general_agent.subagents.semantic_search_subagent import semantic_search_templates
from tests.general_agent.conftest import seed_template


@pytest.mark.asyncio
async def test_semantic_search_returns_similar_templates(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-password",
        template_name="PasswordReset",
        summary="Template for resetting user passwords securely.",
        embed_summary="password reset template for changing account credentials",
    )
    await seed_template(
        db_pool,
        template_id="tpl-welcome",
        template_name="WelcomeEmail",
        summary="Welcome message for new users joining the platform.",
        embed_summary="welcome email for onboarding new customers",
    )

    results = await semantic_search_templates("find password reset templates", limit=5)

    assert results
    assert results[0].template_name == "PasswordReset"
    assert results[0].source == "semantic_search"
    assert results[0].score > 0


@pytest.mark.asyncio
async def test_semantic_search_respects_limit(db_pool):
    for index in range(3):
        await seed_template(
            db_pool,
            template_id=f"tpl-{index}",
            template_name=f"Template{index}",
            summary=f"Notification template number {index}",
            embed_summary="account notification email template",
        )

    results = await semantic_search_templates("notification email", limit=2)
    assert len(results) == 2
