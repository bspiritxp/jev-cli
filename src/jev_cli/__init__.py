"""jev-cli — 调用 Jev (System One) 做结构化判断。TypeSafe 与 OpenRouter 按 key 自动选择。"""

from jev_cli.cli import app, main
from jev_cli.client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    TypeSafeError,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    OverloadedError,
    APIError,
    evaluate,
    noul_question,
    choice_question,
    score_question,
)

__version__ = "0.1.0"

__all__ = [
    "app",
    "main",
    "evaluate",
    "noul_question",
    "choice_question",
    "score_question",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "TypeSafeError",
    "AuthenticationError",
    "ValidationError",
    "RateLimitError",
    "OverloadedError",
    "APIError",
    "__version__",
]
