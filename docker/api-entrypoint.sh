#!/bin/sh
set -eu

# Default env file baked from .env.example; override with ENV_FILE or mount your own .env.
ENV_FILE="${ENV_FILE:-/app/.env}"

if [ -f "$ENV_FILE" ]; then
  PYTHON_BIN=/app/.venv/bin/python
  if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN=python3
  fi
  # Export vars from the env file only when not already set (runtime -e / compose env win).
  eval "$(ENV_FILE="$ENV_FILE" "$PYTHON_BIN" - <<'PY'
import os
import shlex

from dotenv import dotenv_values

path = os.environ.get("ENV_FILE", "/app/.env")
for key, value in dotenv_values(path).items():
    if value is None or key in os.environ:
        continue
    print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

exec "$@"
