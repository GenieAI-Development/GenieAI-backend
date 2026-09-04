from __future__ import annotations

from typing import Callable, TypeVar

from pydantic import BaseModel

from app.integrations.llm.client import StructuredLLMClient
from app.observability.logging import log_event


OutputT = TypeVar("OutputT", bound=BaseModel)


class LLMDecisionError(RuntimeError):
    """Every validated primary and fallback LLM attempt failed."""


class ReliableLLMExecutor:
    def __init__(
        self,
        client: StructuredLLMClient,
        primary_model: str,
        fallback_models: list[str],
        attempts_per_model: int = 2,
    ) -> None:
        if attempts_per_model < 1:
            raise ValueError("attempts_per_model must be at least one")
        self.client = client
        self.primary_model = primary_model
        self.fallback_models = fallback_models
        self.attempts_per_model = attempts_per_model

    async def execute(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[OutputT],
        validator: Callable[[OutputT], OutputT] | None = None,
    ) -> OutputT:
        errors: list[Exception] = []
        models = [self.primary_model, *self.fallback_models]
        for model_index, model in enumerate(models):
            for attempt in range(1, self.attempts_per_model + 1):
                try:
                    value = await self.client.complete(
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=response_model,
                    )
                    validated = response_model.model_validate(value)
                    if validator is not None:
                        validated = validator(validated)
                    log_event(
                        "llm_decision_succeeded",
                        model=model,
                        attempt=attempt,
                        fallback_used=model_index > 0,
                    )
                    return validated
                except Exception as exc:
                    errors.append(exc)
                    log_event(
                        "llm_decision_attempt_failed",
                        model=model,
                        attempt=attempt,
                        fallback_used=model_index > 0,
                        failure_type=type(exc).__name__,
                    )
        raise LLMDecisionError(
            f"structured LLM decision failed after {len(errors)} attempts"
        ) from errors[-1]
