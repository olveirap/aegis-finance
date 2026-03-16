# SPDX-License-Identifier: MIT
"""Tests for temporal modeling and logic."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError

from aegis.kb.temporal import TemporalInterval, CausalActionNode, point_in_time_filter


class TestTemporalInterval:
    def test_valid_interval(self) -> None:
        now = datetime.now(timezone.utc)
        later = now + timedelta(days=1)
        interval = TemporalInterval(t_start=now, t_end=later)
        assert interval.t_start == now
        assert interval.t_end == later

    def test_open_ended_interval(self) -> None:
        now = datetime.now(timezone.utc)
        interval = TemporalInterval(t_start=now)
        assert interval.t_start == now
        assert interval.t_end is None

    def test_invalid_interval(self) -> None:
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(days=1)
        with pytest.raises(ValidationError):
            TemporalInterval(t_start=now, t_end=earlier)


class TestCausalActionNode:
    def test_action_node_creation(self) -> None:
        now = datetime.now(timezone.utc)
        node = CausalActionNode(
            action_type="AMENDS",
            effective_date=now,
            description="Law 123 amended"
        )
        assert node.action_type == "AMENDS"
        assert node.effective_date == now
        assert node.description == "Law 123 amended"


class TestPointInTimeFilter:
    def test_filter_generation(self) -> None:
        now = datetime.now(timezone.utc)
        filter_dict = point_in_time_filter(now)
        
        # Verify structure
        assert "$and" in filter_dict
        conditions = filter_dict["$and"]
        assert len(conditions) == 2
        
        # Checking string output of isoformat()
        now_str = now.isoformat()
        assert conditions[0]["$or"][0]["temporal_validity.t_start"]["$lte"] == now_str
        assert conditions[1]["$or"][0]["temporal_validity.t_end"]["$gt"] == now_str
