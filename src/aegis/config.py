# SPDX-License-Identifier: MIT
"""YAML-based configuration loader with environment variable interpolation.

Loads ``config.yaml`` from the project root (or an arbitrary path), replaces
``${VAR_NAME}`` placeholders with their environment values, and validates the
result through Pydantic v2 models.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator

# ---------------------------------------------------------------------------
# Regex for ${ENV_VAR} placeholders
# ---------------------------------------------------------------------------
_ENV_VAR_RE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")


def _interpolate_env(value: Any) -> Any:
    """Recursively walk a parsed YAML tree and replace ``${VAR}`` tokens."""
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(
            lambda m: os.environ.get(m.group("name"), ""), value
        )
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Pydantic sub-models
# ---------------------------------------------------------------------------


class LocalLLMConfig(BaseModel):
    """Configuration for the local llama.cpp inference server."""

    model: str = "qwen3.5"
    llama_cpp_server: str = "http://localhost:8080"


class CloudLLMConfig(BaseModel):
    """Configuration for a cloud LLM provider."""

    provider: str = "openai"
    api_key: str = ""
    enabled: bool = True


class LLMConfig(BaseModel):
    """Top-level LLM configuration (local + cloud)."""

    local: LocalLLMConfig = LocalLLMConfig()
    cloud: CloudLLMConfig = CloudLLMConfig()


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""

    api_base: str = "http://localhost:8081/v1"
    model: str = "qwen3-embedding"
    ocr_fallback: str = "qwen3-vl-embedding"
    dimension: int = 1024


class RedactionBuckets(BaseModel):
    """Numeric buckets used to anonymise financial amounts."""

    ars: list[int] = [0, 50_000, 500_000, 5_000_000, 50_000_000]
    usd: list[int] = [0, 100, 1_000, 10_000, 100_000]


class PrivacyConfig(BaseModel):
    """Privacy and redaction settings."""

    risk_threshold: float = 0.05
    anonymize_tools: bool = True
    redaction_buckets: RedactionBuckets = RedactionBuckets()


class DatabaseConfig(BaseModel):
    """PostgreSQL database connection settings."""

    host: str = "localhost"
    port: int = 5432
    name: str = "aegis_finance"
    user: str = "aegis"
    password: str = ""

    @property
    def connection_string(self) -> str:
        """Return a ``postgresql://`` DSN built from the individual fields."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class CacheTTL(BaseModel):
    """Time-to-live values (seconds) for market data caches."""

    prices: int = 900
    rates: int = 3600


class MarketConfig(BaseModel):
    """Market data retrieval settings."""

    cache_ttl: CacheTTL = CacheTTL()
    mep_source: str = "ambito"


class RAGConfig(BaseModel):
    """Retrieval-augmented generation chunking parameters."""

    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 5


class StalenessConfig(BaseModel):
    """Staleness detection thresholds."""

    warn_after_days: int = 30


# ---------------------------------------------------------------------------
# Root settings model
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    """Aggregated application configuration."""

    llm: LLMConfig = LLMConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    database: DatabaseConfig = DatabaseConfig()
    market: MarketConfig = MarketConfig()
    rag: RAGConfig = RAGConfig()
    staleness: StalenessConfig = StalenessConfig()

    @model_validator(mode="before")
    @classmethod
    def _interpolate(cls, values: Any) -> Any:  # noqa: ANN401
        """Replace ``${ENV_VAR}`` placeholders before validation."""
        return _interpolate_env(values)


# ---------------------------------------------------------------------------
# Singleton loader
# ---------------------------------------------------------------------------

_SETTINGS: Settings | None = None

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def get_config(path: Path | None = None) -> Settings:
    """Load and return the application :class:`Settings` singleton.

    Parameters
    ----------
    path:
        Explicit path to a YAML configuration file.  When *None* the loader
        looks for ``config.yaml`` two directories above this module (i.e. the
        project root when installed in ``src/aegis/``).

    Raises
    ------
    FileNotFoundError
        If the resolved configuration file does not exist.
    """
    global _SETTINGS  # noqa: PLW0603

    if _SETTINGS is not None:
        return _SETTINGS

    config_path = path or _DEFAULT_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            "Hint: copy config.yaml.example to config.yaml and fill in your "
            "environment-specific values, or set the path explicitly via "
            "get_config(path=...)."
        )

    with open(config_path, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    _SETTINGS = Settings.model_validate(raw)
    return _SETTINGS


def reset_config() -> None:
    """Clear the cached singleton — useful for tests."""
    global _SETTINGS  # noqa: PLW0603
    _SETTINGS = None
