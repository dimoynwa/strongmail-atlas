from __future__ import annotations

import time

from api.refresh import locks as refresh_locks
from api.tone_batch import locks as tone_locks


def test_tone_lock_isolated_from_refresh_locks(redis_client):
    del redis_client
    assert tone_locks.acquire_tone_lock("tone-job-a") is True
    assert refresh_locks.acquire_lock("full", "refresh-job-a") is True
    assert refresh_locks.acquire_lock("template", "refresh-job-b", target="tpl-1") is True

    assert tone_locks.get_tone_lock_holder() == "tone-job-a"
    assert refresh_locks.get_lock_holder("full") == "refresh-job-a"
    assert refresh_locks.get_lock_holder("template", target="tpl-1") == "refresh-job-b"

    tone_locks.release_tone_lock()
    refresh_locks.release_lock("full")
    refresh_locks.release_lock("template", target="tpl-1")

    assert tone_locks.get_tone_lock_holder() is None
    assert refresh_locks.get_lock_holder("full") is None


def test_tone_lock_expires(redis_client):
    del redis_client
    assert tone_locks.acquire_tone_lock("tone-exp", ttl_seconds=1) is True
    time.sleep(1.1)
    assert tone_locks.get_tone_lock_holder() is None
