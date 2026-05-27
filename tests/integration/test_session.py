from __future__ import annotations

import pytest

from app.models import DiffEntry, PendingDiff
from app.session import (
    _extract_overrides,
    _parse_json_object,
    merge_working_copy,
    parse_pending_diff,
)
from template_assistant.eligibility import get_eligible_keys


def test_parse_json_object_from_codeblock():
    payload = _parse_json_object('```json\n{"KEY": "value"}\n```')
    assert payload == {"KEY": "value"}


def test_extract_overrides_from_array():
    payload = {
        "overrides": [
            {"key": "EN.PARAGRAPH_1", "value": "Hello world from override"},
        ]
    }
    assert _extract_overrides(payload) == {
        "EN.PARAGRAPH_1": "Hello world from override"
    }


def test_merge_working_copy_applies_overrides():
    eligible = {"EN.PARAGRAPH_1": "Original text long enough for eligibility"}
    overrides = {"EN.PARAGRAPH_1": "Updated text long enough for eligibility"}
    merged = merge_working_copy(eligible, overrides)
    assert merged["EN.PARAGRAPH_1"] == "Updated text long enough for eligibility"


def test_parse_pending_diff():
    response = """
    {
      "snapshot_overwritten": true,
      "suggestions": [
        {
          "key": "EN.PARAGRAPH_1",
          "current_value": "Old value here long enough",
          "suggested_value": "New value here long enough"
        }
      ]
    }
    """
    diff = parse_pending_diff(response)
    assert diff is not None
    assert diff.snapshot_overwritten is True
    assert len(diff.entries) == 1
    assert diff.entries[0].key == "EN.PARAGRAPH_1"


@pytest.fixture
def session_state():
    return {
        "session_id": "test-session-001",
        "template_name": "TestTemplate",
        "lang_local": "en-us",
        "param_cust_brand": "brandx",
    }


@pytest.mark.asyncio
async def test_get_eligible_keys(db_pool, redis_client, session_state):
    del redis_client
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO template (id, name) VALUES ('t1', 'TestTemplate')
            ON CONFLICT (id) DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO template_details (template_id, lang_local, param_cust_brand, html, text)
            VALUES (
                't1', 'EN', 'BRANDX',
                '<p>##EN.PARAGRAPH_1##</p><p>##EN.SHORT##</p><p>##EN.CTA_URL##</p>',
                ''
            )
            ON CONFLICT DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO content_block (id) VALUES ('cb1') ON CONFLICT DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO content_block_details (id, content_block_id)
            VALUES (1, 'cb1') ON CONFLICT DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO template_content_block (template_id, content_block_id)
            VALUES ('t1', 'cb1') ON CONFLICT DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO content_block_kv (content_block_details_id, field_key, field_value)
            VALUES
                (1, 'EN.PARAGRAPH_1', 'This is a long enough paragraph for tone editing.'),
                (1, 'EN.SHORT', 'short'),
                (1, 'EN.CTA_URL', 'https://example.com/login')
            ON CONFLICT DO NOTHING
            """
        )

    eligible = await get_eligible_keys(session_state, force_reload=True)
    assert "EN.PARAGRAPH_1" in eligible
    assert "EN.SHORT" not in eligible
    assert "EN.CTA_URL" not in eligible


def test_pending_diff_dataclass():
    diff = PendingDiff(
        entries=[DiffEntry(key="K", old_value="old", new_value="new")],
        snapshot_overwritten=False,
    )
    assert diff.entries[0].new_value == "new"
