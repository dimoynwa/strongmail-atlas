from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


from shared.config import get_test_database_url


async def _seed_template(db_pool, *, template_id: str, name: str, html: str) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO template (id, name) VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """,
            template_id,
            name,
        )
        await conn.execute(
            """
            INSERT INTO template_details
                (template_id, lang_local, param_cust_brand, html, text)
            VALUES ($1, 'EN', 'SKRILL', $2, '')
            ON CONFLICT DO NOTHING
            """,
            template_id,
            html,
        )


@pytest.fixture
def mock_classifier():
    classifier = MagicMock(
        return_value=[
            {"label": "joy", "score": 0.9},
            {"label": "admiration", "score": 0.7},
            {"label": "approval", "score": 0.5},
        ]
    )
    return classifier


@pytest.mark.asyncio
async def test_reevaluate_returns_top_emotions(api_client, db_pool, mock_classifier, monkeypatch):
    import api.state as state

    await _seed_template(
        db_pool,
        template_id="t1",
        name="password_reset_en",
        html="<p>Hello world, this is a long enough email body for tone analysis.</p>",
    )
    state.classifier = mock_classifier
    monkeypatch.setenv("DATABASE_URL", get_test_database_url())

    with patch("api.routers.tone.resolve_template") as resolve_mock:
        from shared.resolution.resolver import ResolutionResult

        resolve_mock.return_value = ResolutionResult(
            resolved_body="<p>Hello world, this is a long enough email body for tone analysis.</p>",
            unresolvable=[],
        )
        response = await api_client.post("/tone/reevaluate/password_reset_en")

    assert response.status_code == 200
    body = response.json()
    assert body["template_name"] == "password_reset_en"
    assert "joy" in body["emotions"]
    assert "_warning" not in body["emotions"]
    assert body["warning"] is None


@pytest.mark.asyncio
async def test_reevaluate_not_found(api_client, mock_classifier):
    import api.state as state

    state.classifier = mock_classifier
    response = await api_client.post("/tone/reevaluate/does_not_exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reevaluate_warning_for_short_text(api_client, db_pool, mock_classifier, monkeypatch):
    import api.state as state

    await _seed_template(db_pool, template_id="t2", name="short_tpl", html="<p>Hi</p>")
    state.classifier = mock_classifier
    monkeypatch.setenv("DATABASE_URL", get_test_database_url())

    with patch("api.routers.tone.resolve_template") as resolve_mock:
        from shared.resolution.resolver import ResolutionResult

        resolve_mock.return_value = ResolutionResult(
            resolved_body="<p>Hi</p>",
            unresolvable=[],
        )
        response = await api_client.post("/tone/reevaluate/short_tpl")

    assert response.status_code == 200
    body = response.json()
    assert body["warning"] == "no_meaningful_text"
    assert "_warning" not in body["emotions"]
