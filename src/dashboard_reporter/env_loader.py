from __future__ import annotations

import os
from pathlib import Path


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False

    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return value[:index].rstrip()

    return value.strip()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _find_dotenv(start_path: Path | None = None) -> Path | None:
    cursor = (start_path or Path.cwd()).resolve()
    for directory in [cursor, *cursor.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_env_from_dotenv(start_path: Path | None = None) -> Path | None:
    dotenv_path = _find_dotenv(start_path=start_path)
    if dotenv_path is None:
        return None

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        env_key = key.strip()
        if not env_key:
            continue
        if env_key in os.environ:
            continue

        parsed_value = _unquote(_strip_inline_comment(value.strip()))
        os.environ[env_key] = parsed_value

    return dotenv_path
