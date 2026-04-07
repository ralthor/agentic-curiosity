from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path


def load_env_file(path: Path, *, override: bool = False) -> None:
    """Load simple KEY=VALUE pairs from a dotenv-style file into os.environ."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        if line.startswith('export '):
            line = line[7:].lstrip()

        if '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        if override or key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default

    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name: str, *, default: Sequence[str] | None = None, separator: str = ',') -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return list(default or [])

    return [item.strip() for item in value.split(separator) if item.strip()]


def env_int(name: str, *, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default

    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default
