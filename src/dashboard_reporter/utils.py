from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path, chunk_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def to_plain_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    text = str(value).strip()
    return text or None


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_token(value: Any, *, lowercase: bool = True, remove_accents: bool = True) -> str:
    if value is None:
        return ""
    token = str(value).strip()
    if remove_accents:
        token = strip_accents(token)
    token = re.sub(r"\s+", " ", token)
    return token.lower() if lowercase else token


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return normalize_whitespace(value) == ""
    return False


def stable_hash_from_mapping(values: dict[str, Any]) -> str:
    return sha256_text(json_dumps(values))
