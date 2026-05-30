from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_evaluate_includes_plain_text(api_client):
    session_resp = await api_client.post(
        "/session",
        json={
            "template_name": "AnyTemplate",
            "lang_local": "EN",
            "param_cust_brand": "SKRILL",
        },
    )
    if session_resp.status_code == 404:
        pytest.skip("Template not seeded in test DB")

    session_id = session_resp.json()["session_id"]
    import api.state as state

    state.classifier = lambda text: [{"label": "joy", "score": 0.8}]

    with patch("api.routers.tone.build_preview") as preview_mock:
        preview_mock.return_value = {
            "resolved_text": "Sample plain text for evaluation.",
            "resolved_html": "<p>Sample plain text for evaluation.</p>",
            "evaluated_from": "graph",
        }
        response = await api_client.post(
            f"/tone/evaluate/{session_id}",
            json={"top_n": 3},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["plain_text"] == "Sample plain text for evaluation."
    assert body["plain_text_length"] == len(body["plain_text"])
