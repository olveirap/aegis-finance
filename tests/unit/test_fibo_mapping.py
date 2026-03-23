# SPDX-License-Identifier: MIT
"""Tests for FIBO mapping."""

from __future__ import annotations

from aegis.kb.ontology import GraphNodeType, GraphEdgeType
from aegis.kb.fibo_mapping import FIBO_NODE_MAPPING, FIBO_EDGE_MAPPING, get_fibo_iri


def test_all_node_types_mapped() -> None:
    for node_type in GraphNodeType:
        assert node_type in FIBO_NODE_MAPPING, f"{node_type} lacks FIBO mapping"
        iri = get_fibo_iri(node_type)
        assert iri is not None
        assert iri.startswith("https://spec.edmcouncil.org/fibo/ontology/")


def test_all_edge_types_mapped() -> None:
    for edge_type in GraphEdgeType:
        assert edge_type in FIBO_EDGE_MAPPING, f"{edge_type} lacks FIBO mapping"
        iri = get_fibo_iri(edge_type)
        assert iri is not None
        assert iri.startswith("https://spec.edmcouncil.org/fibo/ontology/")
