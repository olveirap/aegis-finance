# SPDX-License-Identifier: MIT
"""Tests for the KB ontology and metadata schema (Task 0.1)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from aegis.kb.metadata import ChunkMetadata
from aegis.kb.ontology import (
    GraphEdgeType,
    GraphNodeType,
    SourceType,
    SubTopic,
    SUBTOPIC_PARENTS,
    TopicCategory,
    children_of,
)

# ── Paths ────────────────────────────────────────────────────────────────────

TAXONOMY_YAML = (
    Path(__file__).resolve().parents[2] / "data" / "knowledge" / "taxonomy.yaml"
)


# ── Ontology enum tests ─────────────────────────────────────────────────────


class TestTopicHierarchy:
    """Topic ↔ SubTopic hierarchy is consistent."""

    def test_every_subtopic_has_a_parent(self) -> None:
        assert set(SUBTOPIC_PARENTS.keys()) == set(SubTopic)

    def test_children_of_roundtrips(self) -> None:
        for cat in TopicCategory:
            kids = children_of(cat)
            assert len(kids) >= 1, f"{cat} has no children"
            for kid in kids:
                assert SUBTOPIC_PARENTS[kid] == cat

    def test_no_orphaned_categories(self) -> None:
        """Every TopicCategory is the parent of at least one SubTopic."""
        parents_used = set(SUBTOPIC_PARENTS.values())
        assert parents_used == set(TopicCategory)


class TestSourceType:
    """SourceType enum covers expected sources."""

    EXPECTED = {
        "blog",
        "reddit",
        "youtube",
        "regulation",
        "book_summary",
        "user_note",
        "api_timeseries",
        "rss_feed",
        "video_webinar",
    }

    def test_all_expected_present(self) -> None:
        actual = {s.value for s in SourceType}
        assert actual == self.EXPECTED


class TestGraphTypes:
    """Graph prep enums are not empty and have no duplicates."""

    def test_node_types_non_empty(self) -> None:
        assert len(GraphNodeType) >= 4

    def test_edge_types_non_empty(self) -> None:
        assert len(GraphEdgeType) >= 4


# ── taxonomy.yaml ↔ ontology.py alignment ────────────────────────────────────


class TestTaxonomyYAML:
    """taxonomy.yaml loads correctly and matches ontology.py."""

    @pytest.fixture()
    def taxonomy(self) -> dict:
        assert TAXONOMY_YAML.exists(), f"Missing {TAXONOMY_YAML}"
        with open(TAXONOMY_YAML) as f:
            return yaml.safe_load(f)

    def test_yaml_loads(self, taxonomy: dict) -> None:
        assert "topics" in taxonomy

    def test_yaml_categories_match_enum(self, taxonomy: dict) -> None:
        yaml_cats = set(taxonomy["topics"].keys())
        enum_cats = {cat.value for cat in TopicCategory}
        assert yaml_cats == enum_cats, (
            f"Mismatch — YAML: {yaml_cats}, Enum: {enum_cats}"
        )

    def test_yaml_subtopics_match_enum(self, taxonomy: dict) -> None:
        yaml_subtopics: set[str] = set()
        for cat_data in taxonomy["topics"].values():
            for st in cat_data["subtopics"]:
                yaml_subtopics.add(st["name"])
        enum_subtopics = {st.value for st in SubTopic}
        assert yaml_subtopics == enum_subtopics, (
            f"Mismatch — YAML: {sorted(yaml_subtopics)}, Enum: {sorted(enum_subtopics)}"
        )

    def test_yaml_graph_edge_types_match_enum(self, taxonomy: dict) -> None:
        yaml_edges = set(taxonomy.get("graph_edge_types", []))
        enum_edges = {e.value for e in GraphEdgeType}
        assert yaml_edges == enum_edges

    def test_yaml_graph_node_types_match_enum(self, taxonomy: dict) -> None:
        yaml_nodes = set(taxonomy.get("graph_node_types", []))
        enum_nodes = {n.value for n in GraphNodeType}
        assert yaml_nodes == enum_nodes


# ── ChunkMetadata validation ────────────────────────────────────────────────


class TestChunkMetadata:
    """ChunkMetadata validates correctly."""

    def _valid_payload(self, **overrides) -> dict:
        base = {
            "source_url": "https://example.com/article",
            "source_type": "blog",
            "topic_tags": ["budgeting"],
            "jurisdiction": ["AR"],
            "language": "es-AR",
            "relevance_score": 0.85,
        }
        base.update(overrides)
        return base

    def test_valid_payload_accepted(self) -> None:
        meta = ChunkMetadata(**self._valid_payload())
        assert meta.jurisdiction == ["AR"]
        assert meta.topic_tags == [SubTopic.BUDGETING]

    def test_global_jurisdiction_default(self) -> None:
        meta = ChunkMetadata(**self._valid_payload(jurisdiction=["GLOBAL"]))
        assert meta.jurisdiction == ["GLOBAL"]

    def test_multiple_jurisdictions(self) -> None:
        meta = ChunkMetadata(**self._valid_payload(jurisdiction=["AR", "UY"]))
        assert set(meta.jurisdiction) == {"AR", "UY"}

    def test_invalid_jurisdiction_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown jurisdiction"):
            ChunkMetadata(**self._valid_payload(jurisdiction=["XX"]))

    def test_empty_topic_tags_rejected(self) -> None:
        with pytest.raises(ValueError):
            ChunkMetadata(**self._valid_payload(topic_tags=[]))

    def test_invalid_source_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            ChunkMetadata(**self._valid_payload(source_type="newspaper"))

    def test_relevance_score_bounds(self) -> None:
        with pytest.raises(ValueError):
            ChunkMetadata(**self._valid_payload(relevance_score=1.5))
        with pytest.raises(ValueError):
            ChunkMetadata(**self._valid_payload(relevance_score=-0.1))

    def test_entity_ids_default_empty(self) -> None:
        meta = ChunkMetadata(**self._valid_payload())
        assert meta.entity_ids == []

    def test_entity_ids_accepts_uuids(self) -> None:
        ids = [uuid4(), uuid4()]
        meta = ChunkMetadata(**self._valid_payload(entity_ids=ids))
        assert meta.entity_ids == ids

    def test_jurisdiction_is_independent_of_topic(self) -> None:
        """Any topic can have any jurisdiction — they are orthogonal facets."""
        # Budgeting (Personal Finance) can be AR, US, or GLOBAL
        for jur in [["AR"], ["US"], ["GLOBAL"]]:
            meta = ChunkMetadata(**self._valid_payload(jurisdiction=jur))
            assert meta.topic_tags == [SubTopic.BUDGETING]
            assert meta.jurisdiction == jur
