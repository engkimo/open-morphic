"""Tests for PlannerModel VO (T010 RED)."""

from __future__ import annotations

from domain.value_objects.planner_model import PlannerModel


class TestPlannerModel:
    def test_members(self) -> None:
        assert PlannerModel.SONNET == "sonnet"
        assert PlannerModel.HAIKU == "haiku"

    def test_two_members(self) -> None:
        assert len(PlannerModel) == 2

    def test_string_enum(self) -> None:
        assert isinstance(PlannerModel.SONNET, str)
        assert PlannerModel.HAIKU.value == "haiku"

    def test_to_gateway_id_sonnet(self) -> None:
        assert PlannerModel.SONNET.to_gateway_id() == "claude-sonnet-4-6"

    def test_to_gateway_id_haiku(self) -> None:
        assert PlannerModel.HAIKU.to_gateway_id() == "claude-haiku-4-5-20251001"

    def test_equality(self) -> None:
        assert PlannerModel("sonnet") == PlannerModel.SONNET
        assert PlannerModel("haiku") == PlannerModel.HAIKU
