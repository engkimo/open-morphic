"""Tests for Celery worker — Sprint 2-B.

All tests mock the actual execution; no real Redis/Celery needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCeleryApp:
    def test_celery_app_created(self) -> None:
        from infrastructure.queue.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "morphic_agent"

    def test_celery_app_config(self) -> None:
        from infrastructure.queue.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.enable_utc is True
        assert celery_app.conf.task_track_started is True


class TestExecuteTaskWorker:
    def test_task_registered(self) -> None:
        # Force import to register
        import infrastructure.queue.tasks  # noqa: F401
        from infrastructure.queue.celery_app import celery_app

        assert "morphic.execute_task" in celery_app.tasks

    @patch("infrastructure.queue.tasks._execute_async")
    def test_worker_calls_execute_async(self, mock_exec: MagicMock) -> None:

        from infrastructure.queue.tasks import execute_task_worker

        mock_exec.return_value = {"task_id": "abc", "status": "success"}
        result = execute_task_worker("abc")
        assert result["status"] == "success"
        mock_exec.assert_called_once_with("abc")

    @patch("infrastructure.queue.tasks._execute_async")
    def test_worker_retries_on_error(self, mock_exec: MagicMock) -> None:
        from celery.exceptions import Retry

        from infrastructure.queue.tasks import execute_task_worker

        mock_exec.side_effect = RuntimeError("boom")
        with pytest.raises(Retry):
            execute_task_worker.apply(args=["bad-id"], throw=True).get()


class TestCeleryDispatch:
    def test_celery_enabled_dispatches_to_worker(self) -> None:
        """When celery_enabled=True, task route uses .delay() instead of BackgroundTasks."""
        from unittest.mock import patch as mock_patch

        from fastapi.testclient import TestClient

        from interface.api.container import AppContainer
        from interface.api.main import create_app
        from shared.config import Settings

        settings = Settings(celery_enabled=True, use_postgres=False, planning_mode="disabled")
        container = AppContainer(settings=settings)
        container.create_task = AsyncMock()
        from domain.entities.task import TaskEntity

        container.create_task.execute = AsyncMock(return_value=TaskEntity(goal="test"))

        app = create_app(container=container)
        client = TestClient(app)

        with mock_patch("infrastructure.queue.tasks.execute_task_worker") as mock_worker:
            mock_worker.delay = MagicMock()
            resp = client.post("/api/tasks", json={"goal": "test"})
            assert resp.status_code == 201
            mock_worker.delay.assert_called_once()

    def test_celery_disabled_uses_background_tasks(self) -> None:
        """When celery_enabled=False, task route uses BackgroundTasks."""
        from fastapi.testclient import TestClient

        from interface.api.container import AppContainer
        from interface.api.main import create_app
        from shared.config import Settings

        settings = Settings(celery_enabled=False, use_postgres=False)
        container = AppContainer(settings=settings)
        container.create_task = AsyncMock()
        from domain.entities.task import TaskEntity

        container.create_task.execute = AsyncMock(return_value=TaskEntity(goal="test"))
        container.execute_task = AsyncMock()

        app = create_app(container=container)
        client = TestClient(app)
        resp = client.post("/api/tasks", json={"goal": "test"})
        assert resp.status_code == 201
