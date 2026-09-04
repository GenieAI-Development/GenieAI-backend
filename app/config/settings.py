from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    kapruka_mcp_url: str | None = "https://mcp.kapruka.com/mcp"
    kapruka_mcp_command: str | None = None
    kapruka_mcp_args: list[str] = Field(default_factory=list)
    kapruka_delivery_tool: str = "kapruka_check_delivery"
    kapruka_timeout_seconds: float = 15.0
    kapruka_max_attempts: int = 2
    kapruka_rate_limit_per_minute: int = 50

    catalogue_dir: Path = Path("data/catalogue")
    bm25_dir: Path = Path("data/bm25")
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    qdrant_collection_prefix: str = "kapruka_"
    qdrant_timeout_seconds: float = 10.0
    openai_timeout_seconds: float = 30.0

    dense_top_k: int = 40
    bm25_top_k: int = 40
    fused_top_k: int = 20
    rrf_k: int = 60
    max_smart_shopping_products: int = 12

    llm_primary_model: str = "gpt-4.1-mini"
    llm_fallback_models: list[str] = Field(default_factory=lambda: ["gpt-5-mini"])
    llm_max_attempts_per_model: int = 2
    mcp_verification_concurrency: int = 8
    mcp_broad_failure_ratio: float = 0.5
    request_message_max_length: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
