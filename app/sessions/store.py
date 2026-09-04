from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import uuid4

from app.sessions.models import RecommendationSession


class SessionStore(Protocol):
    async def create(self) -> RecommendationSession: ...
    async def get(self, session_id: str) -> RecommendationSession | None: ...
    async def save(self, session: RecommendationSession) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, RecommendationSession] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> RecommendationSession:
        session = RecommendationSession(session_id=str(uuid4()))
        async with self._lock:
            self._sessions[session.session_id] = session.model_copy(deep=True)
        return session

    async def get(self, session_id: str) -> RecommendationSession | None:
        async with self._lock:
            value = self._sessions.get(session_id)
            return value.model_copy(deep=True) if value else None

    async def save(self, session: RecommendationSession) -> None:
        validated = RecommendationSession.model_validate(session.model_dump())
        async with self._lock:
            self._sessions[validated.session_id] = validated.model_copy(deep=True)

