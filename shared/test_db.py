from __future__ import annotations

from urllib.parse import urlparse

import asyncpg


async def ensure_test_database(url: str) -> None:
    """Create the test database if it does not already exist."""
    parsed = urlparse(url)
    db_name = parsed.path.strip("/")
    admin_url = _admin_url(url)

    conn = await asyncpg.connect(admin_url)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name,
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


def _admin_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(path="/postgres").geturl()


def assert_test_database(url: str) -> None:
    """Refuse destructive pytest setup against a non-test database."""
    db_name = urlparse(url).path.strip("/")
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"Refusing destructive test setup on database {db_name!r}. "
            "Set TEST_DATABASE_URL to a dedicated *_test database."
        )
