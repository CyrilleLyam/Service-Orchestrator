from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://orchestrator:orchestrator@localhost:5433/service_orchestrator"
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "text"
    log_sql: bool = False

    max_request_bytes: int = 1024 * 1024
    max_definition_bytes: int = 256 * 1024
    max_definition_depth: int = 64
    max_payload_bytes: int = 64 * 1024
    max_payload_depth: int = 16

    max_schema_depth: int = 32
    max_schema_nodes: int = 2_000
    max_pattern_length: int = 256

    max_rule_depth: int = 16
    max_rule_nodes: int = 200
    max_rule_steps: int = 10_000
