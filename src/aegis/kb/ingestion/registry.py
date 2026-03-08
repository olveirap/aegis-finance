# SPDX-License-Identifier: MIT
"""YAML-driven source registry for the ingestion framework."""

from __future__ import annotations

import os
from typing import Any
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from aegis.kb.ontology import SourceType, SubTopic


class AuthConfig(BaseModel):
    type: str  # e.g. "api_key", "oauth", "none"
    env: str | None = None  # Environment variable name


class StageConfig(BaseModel):
    connector: str
    extractor: str | list[str] | None = None
    emit: str | None = None


class SourceConfig(BaseModel):
    name: str
    schedule: str | None = None
    ontology_tags: list[SubTopic]
    jurisdiction: list[str]
    
    # Single-stage options
    connector: str | None = None
    extractor: str | list[str] | None = None
    base_url: str | None = None
    auth: AuthConfig | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    
    # Multi-stage options
    stages: list[StageConfig] | None = None
    
    @model_validator(mode="after")
    def validate_stages(self) -> SourceConfig:
        if not self.stages and not self.connector:
            raise ValueError("Must provide either 'connector' or 'stages'")
        return self


class SourceRegistry:
    """Loads and registers AI knowledge sources from YAML configurations."""

    def __init__(self, sources: dict[str, SourceConfig] = None) -> None:
        self.sources = sources or {}

    @classmethod
    def load(cls, yaml_dir: str | Path) -> SourceRegistry:
        """Loads all YAML files in the given directory."""
        yaml_dir = Path(yaml_dir)
        sources: dict[str, SourceConfig] = {}
        
        if not yaml_dir.exists():
            return cls(sources)
            
        for filepath in yaml_dir.glob("*.yaml"):
            with open(filepath, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if not data or "sources" not in data:
                    continue
                
                for source_data in data["sources"]:
                    try:
                        config = SourceConfig(**source_data)
                        sources[config.name] = config
                    except Exception as e:
                        print(f"Failed to load source config in {filepath}: {e}")
        
        return cls(sources)
