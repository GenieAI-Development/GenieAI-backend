from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any


_request_context: ContextVar[dict[str, str]] = ContextVar(
    "genieai_request_context", default={}
)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def bind_request_context(*, request_id: str, session_id: str, request_type: str) -> None:
    _request_context.set(
        {
            "request_id": request_id,
            "session_id": session_id,
            "request_type": request_type,
        }
    )


def log_event(event: str, **fields: Any) -> None:
    logging.getLogger("genieai").info(
        json.dumps(
            {"event": event, **_request_context.get(), **fields},
            default=str,
            sort_keys=True,
        )
    )
