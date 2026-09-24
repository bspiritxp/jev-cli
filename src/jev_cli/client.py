"""HTTP client for the Jev System One evaluation endpoint.

Jev (``jev-latest``) does not generate text; it evaluates a ``state`` against a
set of typed ``questions`` and returns structured answers (a probability, a
choice, or a score) your code can consume directly.

Two hosts speak this contract:

- TypeSafe:    ``POST https://api.typesafe.ai/v1/systemone``
- OpenRouter:  ``POST https://openrouter.ai/api/v1/systemone``

``evaluate`` uses a custom endpoint from ``~/.config/jev-cli/setting.yaml`` when
``base_url`` and ``api_key`` are both set. Otherwise ``TYPESAFE_API_KEY`` selects
TypeSafe, and ``OPENROUTER_API_KEY`` selects OpenRouter. Key text is never
inspected. An explicit base URL argument always wins, so local mocks keep working.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Sequence

from jev_cli import settings

DEFAULT_BASE_URL = "https://api.typesafe.ai"
OPENROUTER_API_BASE = "https://openrouter.ai/api"
DEFAULT_MODEL = "jev-latest"

API_KEY_ENV = "TYPESAFE_API_KEY"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
BASE_URL_ENV = "TYPESAFE_BASE_URL"
MODEL_ENV = "TYPESAFE_MODEL"

_OPENROUTER_HOSTS = frozenset({"openrouter.ai", "www.openrouter.ai"})
_TYPESAFE_HOSTS = frozenset({"api.typesafe.ai"})
_TYPESAFE_MODEL_PREFIXES = ("~typesafe/", "typesafe/")

# HTTP status codes the docs say to retry with exponential backoff.
_RETRYABLE_STATUSES = (429, 529)


class TypeSafeError(Exception):
    """Base error raised for System One API failures."""


class AuthenticationError(TypeSafeError):
    """401 — missing or invalid API key."""


class ValidationError(TypeSafeError):
    """400/422 — the request body failed validation."""


class RateLimitError(TypeSafeError):
    """429 — rate limit exceeded."""


class OverloadedError(TypeSafeError):
    """529 — upstream temporarily overloaded."""


class APIError(TypeSafeError):
    """Any other non-2xx response."""


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_message(body: str) -> str:
    if not body:
        return ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()
    if isinstance(data, dict):
        for key in ("message", "error", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict) and value.get("message"):
                return str(value["message"])
    return body.strip()


def _env_value(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _is_openrouter_url(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in _OPENROUTER_HOSTS


def _is_typesafe_url(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in _TYPESAFE_HOSTS


def _is_full_endpoint(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    return path.endswith("/v1/systemone") or path.endswith("/alpha/decisions")


def normalize_base_url(base_url: str) -> str:
    """Collapse OpenRouter site roots onto the API root. Other URLs pass through."""
    base_url = base_url.strip().rstrip("/")
    if not base_url or not _is_openrouter_url(base_url) or _is_full_endpoint(base_url):
        return base_url
    path = urllib.parse.urlparse(base_url).path.rstrip("/")
    if path in ("", "/api"):
        return OPENROUTER_API_BASE
    return base_url


def _endpoint_from_base(base_url: str) -> str:
    normalized = normalize_base_url(base_url)
    if _is_full_endpoint(normalized):
        return normalized
    return f"{normalized}/v1/systemone"


def _custom_endpoint() -> dict[str, str] | None:
    try:
        return settings.configured_endpoint()
    except settings.SettingsError as exc:
        raise TypeSafeError(str(exc)) from exc


def resolve_api_key(api_key: str | None = None) -> str:
    """``--api-key`` / argument, then custom settings, then TypeSafe env, then OpenRouter env."""
    explicit = (api_key or "").strip()
    if explicit:
        return explicit
    custom = _custom_endpoint()
    if custom:
        return custom["api_key"]
    key = _env_value(API_KEY_ENV) or _env_value(OPENROUTER_API_KEY_ENV)
    if not key:
        raise AuthenticationError(
            "缺少 API Key：请运行 jev-cli setup 配置自定义端点，"
            f"或设置 {API_KEY_ENV}（TypeSafe）/ {OPENROUTER_API_KEY_ENV}（OpenRouter），"
            "或传入 --api-key。"
        )
    return key


def resolve_endpoint(base_url: str | None = None) -> str:
    """Return the System One URL.

    An explicit base URL argument always wins, including a local mock. Otherwise
    a complete custom endpoint in ``~/.config/jev-cli/setting.yaml`` wins, then
    ``TYPESAFE_BASE_URL``. If none of those are set, ``TYPESAFE_API_KEY`` selects
    TypeSafe and ``OPENROUTER_API_KEY`` selects OpenRouter. The key string itself
    is not inspected.
    """
    explicit = (base_url or "").strip()
    if explicit:
        return _endpoint_from_base(explicit)
    custom = _custom_endpoint()
    if custom:
        return _endpoint_from_base(custom["base_url"])
    env_url = _env_value(BASE_URL_ENV)
    if env_url:
        return _endpoint_from_base(env_url)
    if _env_value(API_KEY_ENV):
        return f"{DEFAULT_BASE_URL}/v1/systemone"
    if _env_value(OPENROUTER_API_KEY_ENV):
        return f"{OPENROUTER_API_BASE}/v1/systemone"
    return f"{DEFAULT_BASE_URL}/v1/systemone"


def resolve_model(model: str | None = None) -> str:
    """``--model`` / argument, then custom settings, then ``TYPESAFE_MODEL``, then default."""
    explicit = (model or "").strip()
    if explicit:
        return explicit
    custom = _custom_endpoint()
    if custom and custom.get("model_name"):
        return custom["model_name"]
    return _env_value(MODEL_ENV) or DEFAULT_MODEL


def default_key_source() -> str:
    """Name the key source used when no ``--api-key`` is passed."""
    try:
        custom = settings.configured_endpoint()
    except settings.SettingsError as exc:
        return f"自定义配置无效：{exc}"
    if custom:
        return "自定义配置"
    if _env_value(API_KEY_ENV):
        return API_KEY_ENV
    if _env_value(OPENROUTER_API_KEY_ENV):
        return OPENROUTER_API_KEY_ENV
    return "无"


def canonical_model(model: str, url: str) -> str:
    """Strip OpenRouter's ``typesafe/`` prefix only on the official TypeSafe host.

    Custom endpoints keep ``model_name`` unchanged. OpenRouter also keeps it.
    """
    if not _is_typesafe_url(url):
        return model
    for prefix in _TYPESAFE_MODEL_PREFIXES:
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


def evaluate(
    *,
    state: Any,
    questions: Mapping[str, Mapping[str, Any]],
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 60.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Evaluate ``state`` against ``questions`` and return the JSON response.

    ``state`` may be a string, dict, or list. ``questions`` is a mapping of
    question id -> question object (see ``noul_question``, ``choice_question``,
    ``score_question``).

    Host selection ignores the key string. Pass ``base_url`` to force a host,
    including a local mock. Otherwise a complete custom endpoint wins, then
    ``TYPESAFE_BASE_URL``. With no explicit URL, ``TYPESAFE_API_KEY`` selects
    TypeSafe, and ``OPENROUTER_API_KEY`` selects OpenRouter only when the
    official env var is unset. Both accept ``jev-latest``.
    """
    api_key = resolve_api_key(api_key)
    model = resolve_model(model)
    url = resolve_endpoint(base_url)
    model = canonical_model(model, url)

    payload: dict[str, Any] = {
        "state": state,
        "model": model,
        "questions": dict(questions),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    delay = 0.5
    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise APIError("响应不是 JSON。若指向了 OpenRouter 网页根路径，请省略 --base-url，让客户端自动选择。") from exc
        except urllib.error.HTTPError as exc:
            status = exc.code
            detail = _extract_message(_read_error_body(exc))

            if status in _RETRYABLE_STATUSES and attempt < max_retries:
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue

            if status == 401:
                raise AuthenticationError(detail or "API Key 无效或缺失。") from exc
            if status in (400, 422):
                raise ValidationError(detail or "请求体校验失败。") from exc
            if status == 402:
                if _is_openrouter_url(url):
                    raise APIError(detail or "OpenRouter 额度不足：https://openrouter.ai/credits") from exc
                raise APIError(detail or "账户额度不足。") from exc
            if status == 429:
                raise RateLimitError(detail or "请求过于频繁，已被限流。") from exc
            if status == 529:
                raise OverloadedError(detail or "服务暂时过载，请稍后重试。") from exc
            raise APIError(f"HTTP {status}: {detail or '未知错误'}") from exc
        except urllib.error.URLError as exc:
            raise APIError(f"网络错误：{exc.reason}") from exc

    raise OverloadedError("重试次数用尽，服务仍未恢复。")


def noul_question(instructions: Any, yes: str | None = None, no: str | None = None) -> dict[str, Any]:
    """Build a Noul (yes/no) question.

    ``instructions`` is the yes/no question to evaluate. ``yes`` / ``no``
    optionally describe what a value near 1 / near 0 means.
    """
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    criteria: dict[str, str] = {}
    if yes:
        criteria["true"] = yes
    if no:
        criteria["false"] = no
    if criteria:
        question["criteria"] = criteria
    return question


def choice_question(instructions: Any, criteria: Mapping[str, str | None]) -> dict[str, Any]:
    """Build a Choice (pick one option) question.

    ``criteria`` maps option name -> description (``None`` when an option needs
    no extra detail).
    """
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score_question(instructions: Any, levels: Sequence[Any]) -> dict[str, Any]:
    """Build a Score (rate along ordered levels) question.

    ``levels`` is an ordered list of level descriptions, low end first. The
    returned score ranges from 0 to ``len(levels) - 1``.
    """
    if len(levels) < 2:
        raise ValidationError("Score 至少需要 2 个等级描述。")
    if len(levels) > 10:
        raise ValidationError("Score 最多支持 10 个等级描述。")
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}
