# SPDX-License-Identifier: MIT
"""Unit tests for the YAML config loader (Task 1.6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aegis.config import (
    DatabaseConfig,
    Settings,
    get_config,
    reset_config,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _always_reset_config():
    """Ensure the singleton is cleared before and after every test."""
    reset_config()
    yield
    reset_config()


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    """Write *data* as YAML to a temp file and return the path."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ── Tests ────────────────────────────────────────────────────────────────────


class TestLoadDefaultConfig:
    """Loading the real project config.yaml."""

    def test_loads_default_config(self) -> None:
        """Load config.yaml from the project root; all top-level sections present."""
        cfg = get_config()
        assert cfg.llm is not None
        assert cfg.embedding is not None
        assert cfg.privacy is not None
        assert cfg.database is not None
        assert cfg.market is not None
        assert cfg.rag is not None
        assert cfg.staleness is not None

    def test_default_values(self) -> None:
        """Defaults must match the spec in config.yaml."""
        cfg = get_config()
        assert cfg.rag.chunk_size == 512
        assert cfg.rag.chunk_overlap == 64
        assert cfg.rag.top_k == 5
        assert cfg.privacy.risk_threshold == pytest.approx(0.05)
        assert cfg.staleness.warn_after_days == 30
        assert cfg.embedding.dimension == 768
        assert cfg.market.cache_ttl.prices == 900
        assert cfg.market.cache_ttl.rates == 3600
        assert cfg.market.mep_source == "ambito"
        assert cfg.llm.local.model == "qwen3.5"


class TestEnvVarInterpolation:
    """${VAR} replacement inside config values."""

    def test_env_var_interpolation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set an env var and verify it appears in the loaded config."""
        monkeypatch.setenv("TEST_API_KEY", "sk-secret-123")
        p = _write_yaml(tmp_path, {
            "llm": {"cloud": {"api_key": "${TEST_API_KEY}"}},
        })
        cfg = get_config(path=p)
        assert cfg.llm.cloud.api_key == "sk-secret-123"

    def test_missing_env_var_becomes_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unset env var should resolve to an empty string."""
        monkeypatch.delenv("TOTALLY_NONEXISTENT_VAR", raising=False)
        p = _write_yaml(tmp_path, {
            "llm": {"cloud": {"api_key": "${TOTALLY_NONEXISTENT_VAR}"}},
        })
        cfg = get_config(path=p)
        assert cfg.llm.cloud.api_key == ""


class TestDatabaseConfig:
    """DatabaseConfig model and its connection_string property."""

    def test_database_connection_string(self) -> None:
        """connection_string must return a properly formatted DSN."""
        db = DatabaseConfig(
            host="db.example.com",
            port=5433,
            name="mydb",
            user="admin",
            password="s3cret",
        )
        assert db.connection_string == "postgresql://admin:s3cret@db.example.com:5433/mydb"

    def test_database_connection_string_default(self) -> None:
        """Default values produce the expected development DSN."""
        db = DatabaseConfig()
        assert db.connection_string == "postgresql://aegis:@localhost:5432/aegis_finance"


class TestConfigEdgeCases:
    """Error handling and singleton lifecycle."""

    def test_missing_config_file_raises(self, tmp_path: Path) -> None:
        """Loading from a nonexistent path must raise FileNotFoundError."""
        bogus = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError):
            get_config(path=bogus)

    def test_reset_config_clears_singleton(self, tmp_path: Path) -> None:
        """After reset_config(), get_config() re-loads from disk."""
        data_v1 = {"rag": {"chunk_size": 111}}
        data_v2 = {"rag": {"chunk_size": 222}}

        p = _write_yaml(tmp_path, data_v1)
        cfg1 = get_config(path=p)
        assert cfg1.rag.chunk_size == 111

        reset_config()

        # Overwrite the file and reload
        p.write_text(yaml.dump(data_v2), encoding="utf-8")
        cfg2 = get_config(path=p)
        assert cfg2.rag.chunk_size == 222

    def test_singleton_returns_same_object(self) -> None:
        """Consecutive calls without reset return the identical object."""
        a = get_config()
        b = get_config()
        assert a is b

    def test_empty_yaml_uses_defaults(self, tmp_path: Path) -> None:
        """An empty YAML file should produce Settings with all defaults."""
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        cfg = get_config(path=p)
        assert isinstance(cfg, Settings)
        assert cfg.rag.chunk_size == 512
