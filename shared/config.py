import os
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5434/strongmail_tov",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_test_database_url() -> str:
    """Return the dedicated PostgreSQL URL used by pytest fixtures."""
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    parsed = urlparse(DATABASE_URL)
    base_name = parsed.path.strip("/") or "postgres"
    return urlunparse(parsed._replace(path=f"/{base_name}_test"))
