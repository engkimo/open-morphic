"""Tests for cron tools — Sprint 2-E. Mocked APScheduler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.local_execution.tools import cron_tools


@pytest.fixture(autouse=True)
def _reset_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset cron singleton state between tests."""
    monkeypatch.setattr(cron_tools, "_scheduler", None)
    monkeypatch.setattr(cron_tools, "_registered_jobs", {})


def _mock_scheduler() -> MagicMock:
    """Create a mock APScheduler."""
    scheduler = MagicMock()
    scheduler.add_job = MagicMock()
    scheduler.remove_job = MagicMock()
    scheduler.start = MagicMock()
    return scheduler


class TestCronSchedule:
    @pytest.mark.asyncio
    async def test_schedule_recurring_job(self) -> None:
        scheduler = _mock_scheduler()
        with patch.object(cron_tools, "_get_scheduler", return_value=scheduler):
            result = await cron_tools.cron_schedule({"cmd": "echo hello", "cron": "0 9 * * *"})
        assert "Scheduled recurring" in result
        scheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_missing_cmd_raises(self) -> None:
        with pytest.raises(ValueError, match="cmd is required"):
            await cron_tools.cron_schedule({"cron": "0 9 * * *"})

    @pytest.mark.asyncio
    async def test_schedule_missing_cron_raises(self) -> None:
        with pytest.raises(ValueError, match="cron expression is required"):
            await cron_tools.cron_schedule({"cmd": "echo"})

    @pytest.mark.asyncio
    async def test_schedule_invalid_cron_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid cron"):
            await cron_tools.cron_schedule({"cmd": "echo", "cron": "bad"})

    @pytest.mark.asyncio
    async def test_schedule_custom_job_id(self) -> None:
        scheduler = _mock_scheduler()
        with patch.object(cron_tools, "_get_scheduler", return_value=scheduler):
            result = await cron_tools.cron_schedule(
                {"cmd": "echo", "cron": "0 9 * * *", "job_id": "my-job"}
            )
        assert "my-job" in result


class TestCronOnce:
    @pytest.mark.asyncio
    async def test_schedule_one_shot(self) -> None:
        scheduler = _mock_scheduler()
        with patch.object(cron_tools, "_get_scheduler", return_value=scheduler):
            result = await cron_tools.cron_once({"cmd": "echo done", "delay_seconds": 60})
        assert "one-shot" in result
        scheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_one_shot_missing_cmd_raises(self) -> None:
        with pytest.raises(ValueError, match="cmd is required"):
            await cron_tools.cron_once({"delay_seconds": 60})

    @pytest.mark.asyncio
    async def test_one_shot_zero_delay_raises(self) -> None:
        with pytest.raises(ValueError, match="delay_seconds must be positive"):
            await cron_tools.cron_once({"cmd": "echo", "delay_seconds": 0})


class TestCronList:
    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        result = await cron_tools.cron_list({})
        assert "No scheduled" in result

    @pytest.mark.asyncio
    async def test_list_with_jobs(self) -> None:
        cron_tools._registered_jobs["j1"] = {"cmd": "echo", "cron": "0 9 * * *", "type": "cron"}
        result = await cron_tools.cron_list({})
        assert "j1" in result
        assert "echo" in result


class TestCronCancel:
    @pytest.mark.asyncio
    async def test_cancel_existing_job(self) -> None:
        scheduler = _mock_scheduler()
        cron_tools._registered_jobs["j1"] = {"cmd": "echo", "type": "cron"}
        with patch.object(cron_tools, "_get_scheduler", return_value=scheduler):
            result = await cron_tools.cron_cancel({"job_id": "j1"})
        assert "Cancelled" in result
        assert "j1" not in cron_tools._registered_jobs

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self) -> None:
        result = await cron_tools.cron_cancel({"job_id": "missing"})
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_cancel_missing_id_raises(self) -> None:
        with pytest.raises(ValueError, match="job_id is required"):
            await cron_tools.cron_cancel({})


class TestToolRegistration:
    def test_cron_tools_in_registry(self) -> None:
        from infrastructure.local_execution.tools import TOOL_REGISTRY

        cron_names = ["cron_schedule", "cron_once", "cron_list", "cron_cancel"]
        for name in cron_names:
            assert name in TOOL_REGISTRY, f"{name} not in TOOL_REGISTRY"

    def test_total_tool_count(self) -> None:
        from infrastructure.local_execution.tools import TOOL_REGISTRY

        # 2 web + 4 shell + 7 fs + 7 system + 4 dev + 6 browser + 4 gui + 4 cron = 38
        assert len(TOOL_REGISTRY) == 38
