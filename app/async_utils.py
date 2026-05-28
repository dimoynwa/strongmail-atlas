from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")

_background_loop: asyncio.AbstractEventLoop | None = None
_background_loop_lock = threading.Lock()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    """Return a dedicated background event loop for all app async work."""
    global _background_loop
    with _background_loop_lock:
        if _background_loop is None or _background_loop.is_closed():
            loop = asyncio.new_event_loop()

            def _run_loop() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(
                target=_run_loop,
                name="agent-studio-async",
                daemon=True,
            )
            thread.start()
            _background_loop = loop
    return _background_loop


def run_async(coro: Coroutine[object, object, T]) -> T:
    """Run async code on the shared background loop from sync Streamlit code."""
    loop = _get_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def run_async_at_startup(coro: Coroutine[object, object, T]) -> T:
    """Backward-compatible alias — all startup async uses the shared loop."""
    return run_async(coro)
