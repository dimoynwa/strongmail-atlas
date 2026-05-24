import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5434/strongmail_tov",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
