"""Tests for Artifact Pipeline — Plan D.

Verifies that:
- AuditLog.get_produced_files extracts fs_write paths
- TaskEntity.artifact_paths field works
- TaskResponse includes artifact_paths
- register_tool works for dynamic LAEE tool registration
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from domain.entities.task import TaskEntity
from infrastructure.local_execution.audit_log import JsonlAuditLogger
from infrastructure.local_execution.tools import TOOL_REGISTRY, register_tool
from interface.api.schemas import TaskResponse


# ── AuditLog.get_produced_files ────────────────────────────


class TestAuditLogProducedFiles:
    @pytest.fixture
    def tmp_log(self, tmp_path: Path) -> Path:
        return tmp_path / "audit.jsonl"

    @pytest.fixture
    def logger(self, tmp_log: Path) -> JsonlAuditLogger:
        return JsonlAuditLogger(log_path=tmp_log)

    def _write_entry(self, path: Path, tool: str, success: bool, args: dict):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool,
            "args": args,
            "risk": "MEDIUM",
            "success": success,
            "result_summary": "ok",
        }
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def test_extracts_fs_write_paths(self, tmp_log, logger):
        self._write_entry(tmp_log, "fs_write", True, {"path": "/tmp/slides.pptx"})
        self._write_entry(tmp_log, "fs_write", True, {"path": "/tmp/report.pdf"})
        paths = logger.get_produced_files()
        assert paths == ["/tmp/slides.pptx", "/tmp/report.pdf"]

    def test_ignores_failed_writes(self, tmp_log, logger):
        self._write_entry(tmp_log, "fs_write", False, {"path": "/tmp/failed.txt"})
        self._write_entry(tmp_log, "fs_write", True, {"path": "/tmp/ok.txt"})
        paths = logger.get_produced_files()
        assert paths == ["/tmp/ok.txt"]

    def test_ignores_non_write_tools(self, tmp_log, logger):
        self._write_entry(tmp_log, "fs_read", True, {"path": "/tmp/data.json"})
        self._write_entry(tmp_log, "web_search", True, {"query": "test"})
        paths = logger.get_produced_files()
        assert paths == []

    def test_deduplicates_paths(self, tmp_log, logger):
        self._write_entry(tmp_log, "fs_write", True, {"path": "/tmp/dup.txt"})
        self._write_entry(tmp_log, "fs_write", True, {"path": "/tmp/dup.txt"})
        paths = logger.get_produced_files()
        assert len(paths) == 1

    def test_since_filter(self, tmp_log, logger):
        old_entry = {
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "tool": "fs_write",
            "args": {"path": "/tmp/old.txt"},
            "risk": "MEDIUM",
            "success": True,
            "result_summary": "ok",
        }
        new_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": "fs_write",
            "args": {"path": "/tmp/new.txt"},
            "risk": "MEDIUM",
            "success": True,
            "result_summary": "ok",
        }
        with open(tmp_log, "a") as f:
            f.write(json.dumps(old_entry) + "\n")
            f.write(json.dumps(new_entry) + "\n")

        since = datetime.now() - timedelta(hours=1)
        paths = logger.get_produced_files(since=since)
        assert paths == ["/tmp/new.txt"]

    def test_empty_log(self, logger):
        paths = logger.get_produced_files()
        assert paths == []

    def test_file_path_key_variant(self, tmp_log, logger):
        """Some tools use 'file_path' instead of 'path'."""
        self._write_entry(tmp_log, "fs_write", True, {"file_path": "/tmp/alt.txt"})
        paths = logger.get_produced_files()
        assert paths == ["/tmp/alt.txt"]


# ── TaskEntity.artifact_paths ──────────────────────────────


class TestTaskEntityArtifacts:
    def test_default_empty(self):
        task = TaskEntity(goal="Test")
        assert task.artifact_paths == []

    def test_set_artifact_paths(self):
        task = TaskEntity(
            goal="Create slides",
            artifact_paths=["/tmp/slides.pptx", "/tmp/report.pdf"],
        )
        assert len(task.artifact_paths) == 2
        assert "/tmp/slides.pptx" in task.artifact_paths


# ── TaskResponse.artifact_paths ────────────────────────────


class TestTaskResponseArtifacts:
    def test_from_task_includes_artifacts(self):
        task = TaskEntity(
            goal="Create slides",
            artifact_paths=["/tmp/slides.pptx"],
        )
        resp = TaskResponse.from_task(task)
        assert resp.artifact_paths == ["/tmp/slides.pptx"]

    def test_from_task_empty_artifacts(self):
        task = TaskEntity(goal="Simple query")
        resp = TaskResponse.from_task(task)
        assert resp.artifact_paths == []


# ── register_tool (dynamic LAEE extension) ─────────────────


class TestRegisterTool:
    def test_register_adds_to_registry(self):
        async def dummy_handler(args: dict) -> str:
            return "ok"

        original_count = len(TOOL_REGISTRY)
        register_tool("_test_dynamic_tool", dummy_handler)
        assert "_test_dynamic_tool" in TOOL_REGISTRY
        assert TOOL_REGISTRY["_test_dynamic_tool"] is dummy_handler

        # Cleanup
        del TOOL_REGISTRY["_test_dynamic_tool"]
        assert len(TOOL_REGISTRY) == original_count

    def test_register_overwrites_existing(self):
        async def handler_a(args: dict) -> str:
            return "a"

        async def handler_b(args: dict) -> str:
            return "b"

        register_tool("_test_overwrite", handler_a)
        assert TOOL_REGISTRY["_test_overwrite"] is handler_a

        register_tool("_test_overwrite", handler_b)
        assert TOOL_REGISTRY["_test_overwrite"] is handler_b

        # Cleanup
        del TOOL_REGISTRY["_test_overwrite"]
