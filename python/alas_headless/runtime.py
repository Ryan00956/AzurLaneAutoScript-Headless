"""Context-local binding used by the pinned ALAS OCR integration hook."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Optional


_SEMANTIC_SESSION: ContextVar[Optional[Any]] = ContextVar(
    "alas_headless_semantic_session",
    default=None,
)


def bind_semantic_session(session: Any) -> Token:
    if session is None:
        raise ValueError("semantic session binding cannot be None")
    return _SEMANTIC_SESSION.set(session)


def current_semantic_session() -> Optional[Any]:
    return _SEMANTIC_SESSION.get()


def reset_semantic_session(token: Token) -> None:
    _SEMANTIC_SESSION.reset(token)
