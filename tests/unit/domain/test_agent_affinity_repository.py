"""Tests for AgentAffinityRepository port — ABC contract validation.

Sprint 7.4: Affinity-Aware Routing + Task Handoff
"""

from __future__ import annotations

import pytest

from domain.ports.agent_affinity_repository import AgentAffinityRepository


class TestAgentAffinityRepositoryABC:
    """AgentAffinityRepository is a proper ABC and cannot be instantiated."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            AgentAffinityRepository()  # type: ignore[abstract]

    def test_has_get_method(self) -> None:
        assert hasattr(AgentAffinityRepository, "get")

    def test_has_get_by_topic_method(self) -> None:
        assert hasattr(AgentAffinityRepository, "get_by_topic")

    def test_has_get_by_engine_method(self) -> None:
        assert hasattr(AgentAffinityRepository, "get_by_engine")

    def test_has_upsert_method(self) -> None:
        assert hasattr(AgentAffinityRepository, "upsert")

    def test_has_list_all_method(self) -> None:
        assert hasattr(AgentAffinityRepository, "list_all")
