"""Custom endpoint settings stored at ``$HOME/.config/jev-cli/setting.yaml``.

The file is a flat mapping of three strings. It is not a general YAML document:
only ``base_url``, ``api_key``, and ``model_name`` are read, and values are
single-line scalars.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Mapping

_FIELDS = ("base_url", "api_key", "model_name")
_HEADER = (
    "# jev-cli 自定义端点。配齐 base_url 与 api_key 后优先于环境变量。\n"
    "# 优先级：自定义配置 > TYPESAFE_API_KEY > OPENROUTER_API_KEY\n"
)


class SettingsError(Exception):
    """The settings file is unreadable, incomplete, or not a usable endpoint."""


def settings_path() -> Path:
    """Return ``$HOME/.config/jev-cli/setting.yaml``."""
    return Path.home() / ".config" / "jev-cli" / "setting.yaml"


def load_settings() -> dict[str, str]:
    """Return saved fields. Missing file is an empty dict."""
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SettingsError(f"无法读取 {path}：{exc}") from exc
    return _parse(text)


def configured_endpoint() -> dict[str, str] | None:
    """Return the custom endpoint when it is complete, else None.

    A file that sets only some of the endpoint fields is an error: silently
    ignoring it would send the wrong key to the wrong host.
    """
    data = load_settings()
    if not data:
        return None
    if data.get("api_key") and data.get("base_url"):
        _validate_base_url(data["base_url"])
        return data
    raise SettingsError(
        f"自定义配置不完整（{settings_path()}）：需要同时设置 base_url 与 api_key。"
        "请运行 jev-cli setup，或 jev-cli setup --clear。"
    )


def save_settings(values: Mapping[str, str]) -> Path:
    """Write all three fields. Creates the parent directory at mode 0700."""
    data = _require_complete(values)
    path = settings_path()
    tmp = path.with_suffix(".yaml.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        tmp.write_text(_dump(data), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise SettingsError(f"无法写入 {path}：{exc}") from exc
    return path


def clear_settings() -> bool:
    """Delete the settings file. Return whether it existed."""
    path = settings_path()
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError as exc:
        raise SettingsError(f"无法删除 {path}：{exc}") from exc
    return True


def _require_complete(values: Mapping[str, str]) -> dict[str, str]:
    data = {key: (values.get(key) or "").strip() for key in _FIELDS}
    missing = [key for key, value in data.items() if not value]
    if missing:
        raise SettingsError(
            "自定义端点需要 base_url、api_key、model_name。缺少：" + "、".join(missing)
        )
    _validate_base_url(data["base_url"])
    if any("\n" in value or "\r" in value for value in data.values()):
        raise SettingsError("配置项不能包含换行。")
    return data


def _validate_base_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SettingsError(f"base_url 必须是 http(s) URL：{url}")


def _parse(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped in {"---", "..."}:
            continue
        key, sep, raw = stripped.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key not in _FIELDS:
            continue
        found[key] = _unquote(_strip_comment(raw.strip()))
    return {key: value for key, value in found.items() if value}


def _strip_comment(value: str) -> str:
    if value and value[0] not in "\"'" and " #" in value:
        return value.split(" #", 1)[0].rstrip()
    return value


def _unquote(value: str) -> str:
    if len(value) < 2 or value[0] != value[-1] or value[0] not in "\"'":
        return value
    inner = value[1:-1]
    if value[0] == '"':
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return inner.replace("''", "'")


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dump(data: Mapping[str, str]) -> str:
    lines = [_HEADER.rstrip("\n")]
    lines.extend(f"{key}: {_quote(data[key])}" for key in _FIELDS)
    lines.append("")
    return "\n".join(lines)
