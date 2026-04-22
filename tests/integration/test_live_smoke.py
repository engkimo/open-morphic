"""Live smoke tests — real Ollama + real filesystem.

Run with: uv run pytest tests/integration/test_live_smoke.py -v -s
Requires: Ollama running with a qwen3 model (qwen3-coder:30b or qwen3:8b)
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from domain.entities.execution import Action
from domain.entities.task import SubTask
from domain.value_objects import ApprovalMode
from domain.value_objects.status import ObservationStatus
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.local_execution.audit_log import JsonlAuditLogger
from infrastructure.local_execution.executor import LocalExecutor
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer

_HAS_OLLAMA = shutil.which("ollama") is not None

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(not _HAS_OLLAMA, reason="Ollama CLI not installed"),
]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def ollama():
    mgr = OllamaManager()
    if not await mgr.is_running():
        pytest.skip("Ollama not running")
    models = await mgr.list_models()
    if not any("qwen3" in m for m in models):
        pytest.skip("qwen3 model not available")
    return mgr


@pytest.fixture(scope="module")
async def qwen3_model(ollama: OllamaManager) -> str:
    """Return the best available qwen3 model name (prefer coder:30b)."""
    models = await ollama.list_models()
    if any("qwen3-coder" in m for m in models):
        return "qwen3-coder:30b"
    return "qwen3:8b"


# ══════════════════════════════════════════════════════════
# Sprint 1.2: OllamaManager live test
# ══════════════════════════════════════════════════════════


class TestOllamaLive:
    async def test_is_running(self, ollama: OllamaManager) -> None:
        assert await ollama.is_running()

    async def test_list_models(self, ollama: OllamaManager) -> None:
        models = await ollama.list_models()
        assert len(models) > 0
        print(f"\n  Installed models: {models}")

    async def test_direct_inference(self, ollama: OllamaManager, qwen3_model: str) -> None:
        """Direct Ollama API call to verify inference works."""
        import httpx

        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=120.0) as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "model": qwen3_model,
                    "messages": [
                        {"role": "user", "content": "What is 2+2? Answer with just the number."},
                    ],
                    "stream": False,
                    "think": False,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            answer = data["message"]["content"]
            print(f"\n  Ollama ({qwen3_model}) response: {answer[:100]}")
            assert "4" in answer


# ══════════════════════════════════════════════════════════
# Sprint 1.3: IntentAnalyzer live test (LLM decomposition)
# ══════════════════════════════════════════════════════════


class _InMemoryCostRepo:
    """Minimal in-memory CostRepository for integration tests."""

    def __init__(self) -> None:
        self._records: list = []

    async def save(self, record) -> None:
        self._records.append(record)

    async def get_daily_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_monthly_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_local_usage_rate(self) -> float:
        if not self._records:
            return 0.0
        local = sum(1 for r in self._records if r.is_local)
        return local / len(self._records)


class TestIntentAnalyzerLive:
    async def test_decompose_goal(self, ollama: OllamaManager) -> None:
        """Real LLM decomposes a goal into subtasks."""
        from infrastructure.llm.cost_tracker import CostTracker
        from infrastructure.llm.litellm_gateway import LiteLLMGateway
        from shared.config import Settings

        settings = Settings()
        cost_tracker = CostTracker(_InMemoryCostRepo())
        gateway = LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)
        analyzer = IntentAnalyzer(llm=gateway)

        subtasks = await analyzer.decompose(
            "Write a Python function that checks if a number is prime"
        )
        print(f"\n  Decomposed into {len(subtasks)} subtasks:")
        for st in subtasks:
            print(f"    - {st.description} (deps: {st.dependencies})")

        assert len(subtasks) >= 1
        assert all(isinstance(st, SubTask) for st in subtasks)
        assert all(st.description for st in subtasks)


# ══════════════════════════════════════════════════════════
# Sprint 1.3b: LAEE live test (real filesystem)
# ══════════════════════════════════════════════════════════


class TestLAEELive:
    async def test_shell_exec_real(self) -> None:
        """CC#1: Real shell execution."""
        with TemporaryDirectory() as tmp:
            audit = JsonlAuditLogger(Path(tmp) / "audit.jsonl")
            executor = LocalExecutor(
                approval_mode=ApprovalMode.CONFIRM_DESTRUCTIVE,
                audit_logger=audit,
            )
            obs = await executor.execute(
                Action(tool="shell_exec", args={"cmd": "echo 'LAEE live test'"})
            )
            assert obs.status == ObservationStatus.SUCCESS
            assert "LAEE live test" in obs.result
            print(f"\n  shell_exec result: {obs.result}")

    async def test_fs_workflow(self) -> None:
        """CC#2+CC#7: Write → Read → Edit → Undo → verify."""
        with TemporaryDirectory() as tmp:
            audit = JsonlAuditLogger(Path(tmp) / "audit.jsonl")
            executor = LocalExecutor(
                approval_mode=ApprovalMode.FULL_AUTO,
                audit_logger=audit,
            )
            filepath = str(Path(tmp) / "test.py")

            # Write
            obs = await executor.execute(
                Action(
                    tool="fs_write",
                    args={"path": filepath, "content": "def hello():\n    return 'world'\n"},
                )
            )
            assert obs.status == ObservationStatus.SUCCESS
            print(f"\n  fs_write: {obs.result}")

            # Read
            obs = await executor.execute(Action(tool="fs_read", args={"path": filepath}))
            assert obs.status == ObservationStatus.SUCCESS
            assert "def hello" in obs.result
            print(f"  fs_read: {obs.result[:50]}...")

            # Edit
            obs = await executor.execute(
                Action(
                    tool="fs_edit",
                    args={"path": filepath, "old": "world", "new": "morphic"},
                )
            )
            assert obs.status == ObservationStatus.SUCCESS

            # Verify edit
            obs = await executor.execute(Action(tool="fs_read", args={"path": filepath}))
            assert "morphic" in obs.result
            print(f"  After edit: {obs.result[:50]}...")

            # Undo edit
            obs = await executor.undo_last()
            assert obs.status == ObservationStatus.SUCCESS

            # Verify undo
            obs = await executor.execute(Action(tool="fs_read", args={"path": filepath}))
            assert "world" in obs.result
            print(f"  After undo: {obs.result[:50]}...")

            # Check audit log
            log_path = Path(tmp) / "audit.jsonl"
            entries = [
                json.loads(line) for line in log_path.read_text().splitlines() if line.strip()
            ]
            print(f"  Audit log: {len(entries)} entries")
            assert len(entries) >= 4

    async def test_approval_modes(self) -> None:
        """CC#3-5: Verify all 3 approval modes work correctly."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            danger_dir = tmp_path / "danger"
            danger_dir.mkdir()
            (danger_dir / "file.txt").write_text("delete me")

            audit = JsonlAuditLogger(tmp_path / "audit.jsonl")

            # confirm-destructive: recursive delete should be DENIED
            executor_cd = LocalExecutor(
                approval_mode=ApprovalMode.CONFIRM_DESTRUCTIVE,
                audit_logger=audit,
            )
            obs = await executor_cd.execute(
                Action(tool="fs_delete", args={"path": str(danger_dir), "recursive": True})
            )
            assert obs.status == ObservationStatus.DENIED
            assert danger_dir.exists()
            print("\n  confirm-destructive + recursive delete: DENIED (correct)")

            # confirm-all: even fs_write should be DENIED
            executor_ca = LocalExecutor(
                approval_mode=ApprovalMode.CONFIRM_ALL,
                audit_logger=audit,
            )
            obs = await executor_ca.execute(
                Action(
                    tool="fs_write",
                    args={"path": str(tmp_path / "x.txt"), "content": "x"},
                )
            )
            assert obs.status == ObservationStatus.DENIED
            print("  confirm-all + fs_write: DENIED (correct)")

            # full-auto: recursive delete should succeed
            executor_fa = LocalExecutor(
                approval_mode=ApprovalMode.FULL_AUTO,
                audit_logger=audit,
            )
            obs = await executor_fa.execute(
                Action(tool="fs_delete", args={"path": str(danger_dir), "recursive": True})
            )
            assert obs.status == ObservationStatus.SUCCESS
            assert not danger_dir.exists()
            print("  full-auto + recursive delete: SUCCESS (correct)")

    async def test_sudo_detection(self) -> None:
        """CC#8: sudo command auto-classified as CRITICAL."""
        with TemporaryDirectory() as tmp:
            audit = JsonlAuditLogger(Path(tmp) / "audit.jsonl")
            executor = LocalExecutor(
                approval_mode=ApprovalMode.CONFIRM_DESTRUCTIVE,
                audit_logger=audit,
            )
            obs = await executor.execute(Action(tool="shell_exec", args={"cmd": "sudo echo hi"}))
            assert obs.status == ObservationStatus.DENIED
            print("\n  sudo command: DENIED (correct, CRITICAL risk)")

    async def test_dev_git_status(self) -> None:
        """Dev tools: git status in current repo."""
        with TemporaryDirectory() as tmp:
            audit = JsonlAuditLogger(Path(tmp) / "audit.jsonl")
            executor = LocalExecutor(
                approval_mode=ApprovalMode.FULL_AUTO,
                audit_logger=audit,
            )
            obs = await executor.execute(
                Action(
                    tool="dev_git",
                    args={"cmd": "status --short", "cwd": str(Path.cwd())},
                )
            )
            assert obs.status == ObservationStatus.SUCCESS
            print(f"\n  git status:\n{obs.result}")

    async def test_system_resource_info(self) -> None:
        """System tools: resource info."""
        with TemporaryDirectory() as tmp:
            audit = JsonlAuditLogger(Path(tmp) / "audit.jsonl")
            executor = LocalExecutor(
                approval_mode=ApprovalMode.FULL_AUTO,
                audit_logger=audit,
            )
            obs = await executor.execute(Action(tool="system_resource_info", args={}))
            assert obs.status == ObservationStatus.SUCCESS
            assert "CPU" in obs.result
            print(f"\n  {obs.result}")
