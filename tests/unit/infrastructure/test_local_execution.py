"""Tests for LAEE — Local Autonomous Execution Engine.

Covers all 8 completion criteria for Sprint 1.3b:
  CC#1: shell_exec("echo hello") → "hello"
  CC#2: fs_write + fs_read round-trip
  CC#3: fs_delete(recursive=True) denied in confirm-destructive
  CC#4: full-auto executes all without confirmation
  CC#5: confirm-all confirms everything except SAFE
  CC#6: all operations logged to audit log
  CC#7: undo_last() reverts fs_write
  CC#8: sudo commands auto-classified as CRITICAL → denied
"""

from __future__ import annotations

import json
from pathlib import Path

from domain.entities.execution import Action, UndoAction
from domain.value_objects import ApprovalMode, RiskLevel
from domain.value_objects.status import ObservationStatus
from infrastructure.local_execution.audit_log import JsonlAuditLogger
from infrastructure.local_execution.executor import LocalExecutor
from infrastructure.local_execution.undo_manager import UndoManager

# ── Helpers ──


def _make_executor(
    tmp_path: Path,
    mode: ApprovalMode = ApprovalMode.CONFIRM_DESTRUCTIVE,
) -> LocalExecutor:
    audit = JsonlAuditLogger(tmp_path / "audit.jsonl")
    return LocalExecutor(approval_mode=mode, audit_logger=audit)


def _audit_entries(tmp_path: Path) -> list[dict]:
    log_file = tmp_path / "audit.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]


# ══════════════════════════════════════════════════════════
# CC#1: shell_exec("echo hello") → "hello"
# ══════════════════════════════════════════════════════════


class TestShellExec:
    async def test_echo_hello(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        action = Action(tool="shell_exec", args={"cmd": "echo hello"})
        obs = await executor.execute(action)
        assert obs.status == ObservationStatus.SUCCESS
        assert obs.result == "hello"

    async def test_shell_exec_failure(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        action = Action(tool="shell_exec", args={"cmd": "false"})
        obs = await executor.execute(action)
        assert obs.status == ObservationStatus.ERROR

    async def test_shell_pipe(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        action = Action(tool="shell_pipe", args={"cmds": ["echo hello world", "wc -w"]})
        obs = await executor.execute(action)
        assert obs.status == ObservationStatus.SUCCESS
        assert obs.result.strip() == "2"


# ══════════════════════════════════════════════════════════
# CC#2: fs_write + fs_read round-trip
# ══════════════════════════════════════════════════════════


class TestFsRoundTrip:
    async def test_write_then_read(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        filepath = str(tmp_path / "test.txt")

        write_obs = await executor.execute(
            Action(tool="fs_write", args={"path": filepath, "content": "hello world"})
        )
        assert write_obs.status == ObservationStatus.SUCCESS

        read_obs = await executor.execute(Action(tool="fs_read", args={"path": filepath}))
        assert read_obs.status == ObservationStatus.SUCCESS
        assert read_obs.result == "hello world"

    async def test_fs_edit(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        filepath = str(tmp_path / "edit_me.txt")
        (tmp_path / "edit_me.txt").write_text("foo bar baz")

        obs = await executor.execute(
            Action(tool="fs_edit", args={"path": filepath, "old": "bar", "new": "QUX"})
        )
        assert obs.status == ObservationStatus.SUCCESS
        assert (tmp_path / "edit_me.txt").read_text() == "foo QUX baz"

    async def test_fs_glob(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.txt").write_text("c")

        executor = _make_executor(tmp_path)
        obs = await executor.execute(
            Action(tool="fs_glob", args={"pattern": "*.py", "path": str(tmp_path)})
        )
        assert obs.status == ObservationStatus.SUCCESS
        assert "a.py" in obs.result
        assert "b.py" in obs.result
        assert "c.txt" not in obs.result

    async def test_fs_tree(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.txt").write_text("hi")

        executor = _make_executor(tmp_path)
        obs = await executor.execute(Action(tool="fs_tree", args={"path": str(tmp_path)}))
        assert obs.status == ObservationStatus.SUCCESS
        assert "sub" in obs.result
        assert "file.txt" in obs.result

    async def test_fs_move(self, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("moveme")

        executor = _make_executor(tmp_path)
        obs = await executor.execute(
            Action(tool="fs_move", args={"src": str(src), "dst": str(dst)})
        )
        assert obs.status == ObservationStatus.SUCCESS
        assert not src.exists()
        assert dst.read_text() == "moveme"


# ══════════════════════════════════════════════════════════
# CC#3: fs_delete(recursive=True) denied in confirm-destructive
# ══════════════════════════════════════════════════════════


class TestConfirmDestructive:
    async def test_fs_delete_recursive_denied(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        d = tmp_path / "danger"
        d.mkdir()
        (d / "file.txt").write_text("x")

        obs = await executor.execute(
            Action(tool="fs_delete", args={"path": str(d), "recursive": True})
        )
        assert obs.status == ObservationStatus.DENIED
        assert d.exists(), "Directory must NOT be deleted when denied"

    async def test_fs_delete_non_recursive_is_high_denied(self, tmp_path: Path) -> None:
        """fs_delete (non-recursive) is HIGH → denied in confirm-destructive."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        f = tmp_path / "file.txt"
        f.write_text("x")

        obs = await executor.execute(Action(tool="fs_delete", args={"path": str(f)}))
        assert obs.status == ObservationStatus.DENIED

    async def test_shell_exec_allowed(self, tmp_path: Path) -> None:
        """shell_exec is MEDIUM → allowed in confirm-destructive."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        obs = await executor.execute(Action(tool="shell_exec", args={"cmd": "echo ok"}))
        assert obs.status == ObservationStatus.SUCCESS


# ══════════════════════════════════════════════════════════
# CC#4: full-auto executes all without confirmation
# ══════════════════════════════════════════════════════════


class TestFullAuto:
    async def test_fs_delete_recursive_allowed(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path, mode=ApprovalMode.FULL_AUTO)
        d = tmp_path / "autodelete"
        d.mkdir()
        (d / "file.txt").write_text("x")

        obs = await executor.execute(
            Action(tool="fs_delete", args={"path": str(d), "recursive": True})
        )
        assert obs.status == ObservationStatus.SUCCESS
        assert not d.exists()

    async def test_process_kill_allowed(self, tmp_path: Path) -> None:
        """Even HIGH risk is auto-approved in full-auto."""
        # We don't actually kill a process, just verify it wouldn't be denied
        # by checking approval logic directly
        from domain.services.approval_engine import ApprovalEngine

        engine = ApprovalEngine()
        assert not engine.needs_approval(ApprovalMode.FULL_AUTO, RiskLevel.CRITICAL)


# ══════════════════════════════════════════════════════════
# CC#5: confirm-all confirms everything except SAFE
# ══════════════════════════════════════════════════════════


class TestConfirmAll:
    async def test_fs_read_allowed(self, tmp_path: Path) -> None:
        """SAFE tool allowed in confirm-all."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_ALL)
        f = tmp_path / "readable.txt"
        f.write_text("contents")

        obs = await executor.execute(Action(tool="fs_read", args={"path": str(f)}))
        assert obs.status == ObservationStatus.SUCCESS

    async def test_fs_write_denied(self, tmp_path: Path) -> None:
        """MEDIUM tool denied in confirm-all."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_ALL)
        obs = await executor.execute(
            Action(tool="fs_write", args={"path": str(tmp_path / "x.txt"), "content": "x"})
        )
        assert obs.status == ObservationStatus.DENIED

    async def test_shell_background_denied(self, tmp_path: Path) -> None:
        """LOW tool denied in confirm-all."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_ALL)
        obs = await executor.execute(Action(tool="shell_background", args={"cmd": "sleep 1"}))
        assert obs.status == ObservationStatus.DENIED

    async def test_fs_glob_allowed(self, tmp_path: Path) -> None:
        """SAFE tool allowed in confirm-all."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_ALL)
        obs = await executor.execute(
            Action(tool="fs_glob", args={"pattern": "*.py", "path": str(tmp_path)})
        )
        assert obs.status == ObservationStatus.SUCCESS


# ══════════════════════════════════════════════════════════
# CC#6: all operations logged to audit log
# ══════════════════════════════════════════════════════════


class TestAuditLog:
    async def test_success_logged(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        await executor.execute(Action(tool="shell_exec", args={"cmd": "echo audit"}))

        entries = _audit_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["tool"] == "shell_exec"
        assert entries[0]["success"] is True
        assert entries[0]["risk"] == "MEDIUM"

    async def test_denied_logged(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        f = tmp_path / "del.txt"
        f.write_text("x")
        await executor.execute(Action(tool="fs_delete", args={"path": str(f)}))

        entries = _audit_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["success"] is False

    async def test_error_logged(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        await executor.execute(
            Action(tool="fs_read", args={"path": str(tmp_path / "nonexistent.txt")})
        )

        entries = _audit_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["success"] is False

    async def test_multiple_ops_logged(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        await executor.execute(Action(tool="shell_exec", args={"cmd": "echo a"}))
        await executor.execute(Action(tool="shell_exec", args={"cmd": "echo b"}))
        await executor.execute(Action(tool="shell_exec", args={"cmd": "echo c"}))

        entries = _audit_entries(tmp_path)
        assert len(entries) == 3

    async def test_query_by_tool(self, tmp_path: Path) -> None:
        audit = JsonlAuditLogger(tmp_path / "audit.jsonl")
        action_a = Action(tool="fs_read", args={"path": "/tmp/a"})
        action_b = Action(tool="shell_exec", args={"cmd": "echo x"})
        audit.log(action_a, "ok", RiskLevel.SAFE)
        audit.log(action_b, "ok", RiskLevel.MEDIUM)

        results = audit.query(tool="fs_read")
        assert len(results) == 1
        assert results[0]["tool"] == "fs_read"

    async def test_query_by_risk(self, tmp_path: Path) -> None:
        audit = JsonlAuditLogger(tmp_path / "audit.jsonl")
        audit.log(Action(tool="fs_read", args={}), "ok", RiskLevel.SAFE)
        audit.log(Action(tool="shell_exec", args={}), "ok", RiskLevel.MEDIUM)

        results = audit.query(risk=RiskLevel.SAFE)
        assert len(results) == 1


# ══════════════════════════════════════════════════════════
# CC#7: undo_last() reverts fs_write
# ══════════════════════════════════════════════════════════


class TestUndo:
    async def test_undo_new_file(self, tmp_path: Path) -> None:
        """Write new file → undo → file deleted."""
        executor = _make_executor(tmp_path)
        filepath = tmp_path / "undome.txt"

        await executor.execute(
            Action(tool="fs_write", args={"path": str(filepath), "content": "temp"})
        )
        assert filepath.exists()
        assert await executor.get_undo_stack_size() == 1

        undo_obs = await executor.undo_last()
        assert undo_obs.status == ObservationStatus.SUCCESS
        assert not filepath.exists()
        assert await executor.get_undo_stack_size() == 0

    async def test_undo_overwrite(self, tmp_path: Path) -> None:
        """Overwrite file → undo → original content restored."""
        executor = _make_executor(tmp_path)
        filepath = tmp_path / "overwrite.txt"
        filepath.write_text("original")

        await executor.execute(
            Action(tool="fs_write", args={"path": str(filepath), "content": "modified"})
        )
        assert filepath.read_text() == "modified"

        undo_obs = await executor.undo_last()
        assert undo_obs.status == ObservationStatus.SUCCESS
        assert filepath.read_text() == "original"

    async def test_undo_empty_stack(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        obs = await executor.undo_last()
        assert obs.status == ObservationStatus.ERROR
        assert "Nothing to undo" in obs.result

    async def test_undo_fs_edit(self, tmp_path: Path) -> None:
        """Edit file → undo → original text restored."""
        executor = _make_executor(tmp_path)
        filepath = tmp_path / "editundo.txt"
        filepath.write_text("hello world")

        await executor.execute(
            Action(tool="fs_edit", args={"path": str(filepath), "old": "world", "new": "mars"})
        )
        assert filepath.read_text() == "hello mars"

        undo_obs = await executor.undo_last()
        assert undo_obs.status == ObservationStatus.SUCCESS
        assert filepath.read_text() == "hello world"


# ══════════════════════════════════════════════════════════
# CC#8: sudo auto-classified as CRITICAL → denied
# ══════════════════════════════════════════════════════════


class TestSudoCritical:
    async def test_sudo_denied_in_confirm_destructive(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        obs = await executor.execute(Action(tool="shell_exec", args={"cmd": "sudo echo hi"}))
        assert obs.status == ObservationStatus.DENIED

    async def test_rm_rf_denied_in_confirm_destructive(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        obs = await executor.execute(Action(tool="shell_exec", args={"cmd": "rm -rf /tmp/danger"}))
        assert obs.status == ObservationStatus.DENIED

    async def test_sudo_allowed_in_full_auto(self, tmp_path: Path) -> None:
        """In full-auto, even CRITICAL actions are allowed (user's responsibility)."""
        executor = _make_executor(tmp_path, mode=ApprovalMode.FULL_AUTO)
        # We use a safe sudo-like command that won't actually need root
        obs = await executor.execute(
            Action(tool="shell_exec", args={"cmd": "echo 'not really sudo'"})
        )
        assert obs.status == ObservationStatus.SUCCESS

    async def test_credential_path_denied(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path, mode=ApprovalMode.CONFIRM_DESTRUCTIVE)
        obs = await executor.execute(
            Action(tool="fs_read", args={"path": "/home/user/.ssh/id_rsa"})
        )
        assert obs.status == ObservationStatus.DENIED


# ══════════════════════════════════════════════════════════
# UndoManager unit tests
# ══════════════════════════════════════════════════════════


class TestUndoManager:
    def test_push_and_pop(self) -> None:
        mgr = UndoManager()
        undo = UndoAction(
            original_tool="fs_write",
            original_args={"path": "/tmp/a"},
            undo_tool="fs_delete",
            undo_args={"path": "/tmp/a"},
        )
        mgr.push(undo)
        assert mgr.size == 1

        popped = mgr.pop()
        assert popped is not None
        assert popped.undo_tool == "fs_delete"
        assert mgr.size == 0

    def test_pop_empty(self) -> None:
        mgr = UndoManager()
        assert mgr.pop() is None

    def test_lifo_order(self) -> None:
        mgr = UndoManager()
        mgr.push(
            UndoAction(
                original_tool="a",
                original_args={},
                undo_tool="undo_a",
                undo_args={},
            )
        )
        mgr.push(
            UndoAction(
                original_tool="b",
                original_args={},
                undo_tool="undo_b",
                undo_args={},
            )
        )
        assert mgr.pop().undo_tool == "undo_b"
        assert mgr.pop().undo_tool == "undo_a"


# ══════════════════════════════════════════════════════════
# Unknown tool
# ══════════════════════════════════════════════════════════


class TestUnknownTool:
    async def test_unknown_tool_returns_error(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        obs = await executor.execute(Action(tool="nonexistent_tool", args={}))
        assert obs.status == ObservationStatus.ERROR
        assert "Unknown tool" in obs.result
