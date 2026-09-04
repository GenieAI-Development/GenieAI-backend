from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import uuid4

from app.observability.logging import bind_request_context, log_event


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


@dataclass
class RequestTrace:
    request_id: str
    session_id: str
    request_type: str
    started_at: float = field(default_factory=time.perf_counter)

    def __post_init__(self) -> None:
        bind_request_context(
            request_id=self.request_id,
            session_id=self.session_id,
            request_type=self.request_type,
        )

    @contextmanager
    def stage(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            log_event(
                "pipeline_stage",
                request_id=self.request_id,
                session_id=self.session_id,
                request_type=self.request_type,
                pipeline_stage=name,
                stage_duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    def finish(self, response_type: str, result_count: int, failure_category: str | None = None):
        log_event(
            "request_complete",
            request_id=self.request_id,
            session_id=self.session_id,
            request_type=self.request_type,
            total_request_ms=round((time.perf_counter() - self.started_at) * 1000, 2),
            final_result_count=result_count,
            response_type=response_type,
            failure_category=failure_category,
        )
