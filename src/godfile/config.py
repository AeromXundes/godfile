"""Repo-level configuration: `[tool.godfile]` in pyproject.toml or .godfilerc.

Search walks up from the working directory; in each directory .godfilerc
(top-level TOML keys) takes precedence over pyproject.toml's [tool.godfile]
table. CLI flags override anything found in a file.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

CONFIG_KEYS = {
    "max-types": int,
    "fail-at": int,
    "enum-weight-lines": int,
    "count-exceptions": bool,
    "count-internal": bool,
    "sources": bool,
    "exclude": list,
    "default-excludes": bool,
    "ctags-bin": str,
}


class ConfigError(Exception):
    pass


def _parse(path: Path) -> dict | None:
    """Return the config table from *path*, or None if pyproject has no
    [tool.godfile] table."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path}: {e}") from e
    if path.name == "pyproject.toml":
        return data.get("tool", {}).get("godfile")
    return data


def _validate(raw: dict, source: Path) -> dict:
    cfg = {}
    for key, value in raw.items():
        if key not in CONFIG_KEYS:
            valid = ", ".join(sorted(CONFIG_KEYS))
            raise ConfigError(f"{source}: unknown option {key!r} (valid: {valid})")
        want = CONFIG_KEYS[key]
        if want is list:
            ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
        else:
            # bool is a subclass of int; don't let `max-types = true` through
            ok = isinstance(value, want) and not (want is int and isinstance(value, bool))
        if not ok:
            raise ConfigError(f"{source}: option {key!r} must be a {want.__name__}")
        cfg[key.replace("-", "_")] = value
    return cfg


def load_config(explicit: str | None = None, start: str | None = None) -> dict:
    """Load file config. An explicit --config path must contain config;
    otherwise the nearest .godfilerc / pyproject.toml with a [tool.godfile]
    table wins, searching upward from *start* (default: cwd)."""
    if explicit:
        path = Path(explicit)
        raw = _parse(path)
        if raw is None:
            raise ConfigError(f"{path}: no [tool.godfile] table found")
        return _validate(raw, path)

    directory = Path(start or ".").resolve()
    for candidate_dir in (directory, *directory.parents):
        for name in (".godfilerc", "pyproject.toml"):
            path = candidate_dir / name
            if path.is_file():
                raw = _parse(path)
                if raw is not None:
                    return _validate(raw, path)
    return {}
