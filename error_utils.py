from __future__ import annotations

import re
from typing import Any

_TOKEN_EXHAUSTION_PATTERNS = (
    re.compile(r"insufficient_quota", re.IGNORECASE),
    re.compile(r"quota", re.IGNORECASE),
    re.compile(r"token\s*limit", re.IGNORECASE),
    re.compile(r"maximum context length", re.IGNORECASE),
    re.compile(r"context length", re.IGNORECASE),
    re.compile(r"rate limit", re.IGNORECASE),
)


def _stringify_error(exc: Any) -> str:
    if exc is None:
        return ""
    if isinstance(exc, BaseException):
        return str(exc)
    return str(exc)


def is_token_exhaustion_error(exc: Any) -> bool:
    """Return True when an exception looks like quota or token exhaustion."""

    message = _stringify_error(exc).lower()
    if not message:
        return False
    return any(pattern.search(message) for pattern in _TOKEN_EXHAUSTION_PATTERNS)


def friendly_token_exhaustion_message(context: str = "The research run") -> str:
    """Return a user-facing explanation for exhausted API quota or token budget."""

    return (
        f"{context} stopped because the API quota or token limit was reached. "
        "Please check your OpenAI usage, billing, or request size, then try again."
    )


def friendly_api_error_message(exc: Any, context: str = "The research run") -> str:
    """Return a safe user-facing error message for API failures."""

    if is_token_exhaustion_error(exc):
        return friendly_token_exhaustion_message(context)

    return f"{context} failed unexpectedly. Please try again."
