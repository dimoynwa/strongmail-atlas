from __future__ import annotations

import json

import pytest


async def _seed_export_data(db_pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO template (id, name) VALUES ('ex1', 'ExportTemplate') ON CONFLICT DO NOTHING"
        )
        await conn.execute(
            """
            INSERT INTO template_details
                (template_id, lang_local, param_cust_brand, subject, summary, html, text)
            VALUES ('ex1', 'EN', 'SKRILL', 'Plain subject', 'A summary', '', '')
            """
        )
        await conn.execute(
            """
            INSERT INTO template_tone_evaluations
                (template_id, model_id, lang_local, param_cust_brand, tones)
            VALUES (
                'ex1',
                'goemotions',
                'EN',
                'SKRILL',
                $1::jsonb
            )
            """,
            json.dumps(
                {
                    "joy": 0.9,
                    "admiration": 0.7,
                    "approval": 0.5,
                    "_warning": "no_meaningful_text",
                }
            ),
        )


@pytest.mark.asyncio
async def test_export_csv_format(api_client, db_pool):
    await _seed_export_data(db_pool)
    response = await api_client.get("/tone/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8")
    lines = text.strip().splitlines()
    assert lines[0].startswith("NAME,SUBJECT")
    assert "ExportTemplate" in lines[1]
    assert "joy" in lines[1]
    assert "no_meaningful_text" in lines[1]
    assert "_warning" not in lines[1]


@pytest.mark.asyncio
async def test_export_xlsx_format(api_client, db_pool):
    await _seed_export_data(db_pool)
    response = await api_client.get("/tone/export?format=xlsx")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert len(response.content) > 100
