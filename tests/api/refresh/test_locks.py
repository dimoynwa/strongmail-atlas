from __future__ import annotations

import time

from api.refresh import locks


def test_acquire_and_release_template_lock(redis_client):
    del redis_client
    assert locks.acquire_lock("template", "job-a", target="tpl-1") is True
    assert locks.get_lock_holder("template", target="tpl-1") == "job-a"
    assert locks.acquire_lock("template", "job-b", target="tpl-1") is False
    locks.release_lock("template", target="tpl-1")
    assert locks.get_lock_holder("template", target="tpl-1") is None
    assert locks.acquire_lock("template", "job-b", target="tpl-1") is True


def test_full_lock_blocks_until_released(redis_client):
    del redis_client
    assert locks.acquire_lock("full", "full-job") is True
    assert locks.is_locked("full") is True
    assert locks.acquire_lock("full", "other") is False
    locks.release_lock("full")
    assert locks.is_locked("full") is False


def test_lock_expires(redis_client):
    del redis_client
    assert locks.acquire_lock("template", "job-exp", target="tpl-x", ttl_seconds=1) is True
    time.sleep(1.1)
    assert locks.get_lock_holder("template", target="tpl-x") is None
