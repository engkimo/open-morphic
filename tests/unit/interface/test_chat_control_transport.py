"""Authenticated loopback chat control transport tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import stat

import pytest

from interface.cli.chat_control_transport import (
    ChatControlServer,
    send_chat_control_command,
)
from interface.cli.turn_control import ActiveTurnController, TurnCancelledError


@pytest.mark.asyncio
async def test_control_server_reports_and_cancels_active_turn(tmp_path) -> None:
    controller = ActiveTurnController()
    operation_started = asyncio.Event()

    async def operation() -> None:
        operation_started.set()
        await asyncio.Event().wait()

    controlled = asyncio.create_task(controller.run(operation))
    await operation_started.wait()

    async with ChatControlServer(
        workspace_root=tmp_path,
        session_id="chat-control-1",
        turn_controller=controller,
    ) as server:
        descriptor = json.loads(server.descriptor_path.read_text(encoding="utf-8"))
        assert descriptor["host"] == "127.0.0.1"
        assert descriptor["session_id"] == "chat-control-1"
        assert descriptor["token"]
        assert stat.S_IMODE(server.descriptor_path.stat().st_mode) == 0o600

        status = await send_chat_control_command(
            workspace_root=tmp_path,
            session_id="chat-control-1",
            command="status",
        )
        assert status == {
            "active_turn": True,
            "ok": True,
            "session_id": "chat-control-1",
        }

        cancelled = await send_chat_control_command(
            workspace_root=tmp_path,
            session_id="chat-control-1",
            command="cancel",
        )
        assert cancelled == {
            "active_turn": True,
            "cancelled": True,
            "ok": True,
            "session_id": "chat-control-1",
        }

    with pytest.raises(TurnCancelledError):
        await controlled
    assert server.descriptor_path.exists() is False


@pytest.mark.asyncio
async def test_control_server_rejects_invalid_token_without_cancelling(tmp_path) -> None:
    controller = ActiveTurnController()
    operation_started = asyncio.Event()

    async def operation() -> None:
        operation_started.set()
        await asyncio.Event().wait()

    controlled = asyncio.create_task(controller.run(operation))
    await operation_started.wait()

    async with ChatControlServer(
        workspace_root=tmp_path,
        session_id="chat-control-auth",
        turn_controller=controller,
    ) as server:
        descriptor = json.loads(server.descriptor_path.read_text(encoding="utf-8"))

        async def request(payload: dict[str, object]) -> dict[str, object]:
            reader, writer = await asyncio.open_connection(
                host=descriptor["host"],
                port=descriptor["port"],
            )
            writer.write(json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n")
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            return response

        unauthorized = await request(
            {
                "command": "cancel",
                "session_id": "chat-control-auth",
                "token": "wrong-token",
            }
        )
        mismatched = await request(
            {
                "command": "cancel",
                "session_id": "another-session",
                "token": descriptor["token"],
            }
        )
        unsupported = await request(
            {
                "command": "restart",
                "session_id": "chat-control-auth",
                "token": descriptor["token"],
            }
        )
        invalid_steer = await request(
            {
                "command": "steer",
                "session_id": "chat-control-auth",
                "token": descriptor["token"],
            }
        )

        assert unauthorized == {"error": "unauthorized", "ok": False}
        assert mismatched == {"error": "session_mismatch", "ok": False}
        assert unsupported == {"error": "unsupported_command", "ok": False}
        assert invalid_steer == {"error": "invalid_steer_prompt", "ok": False}
        assert controller.has_active_turn is True

    controlled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await controlled


@pytest.mark.asyncio
async def test_control_client_reports_inactive_when_descriptor_is_absent(tmp_path) -> None:
    response = await send_chat_control_command(
        workspace_root=tmp_path,
        session_id="chat-control-idle",
        command="status",
    )

    assert response == {
        "active_turn": False,
        "ok": True,
        "session_id": "chat-control-idle",
    }


@pytest.mark.asyncio
async def test_control_client_rejects_non_loopback_descriptor(tmp_path) -> None:
    session_id = "chat-control-host"
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    descriptor_path = tmp_path / ".morphic" / "control" / f"{digest}.json"
    descriptor_path.parent.mkdir(parents=True)
    descriptor_path.write_text(
        json.dumps(
            {
                "host": "0.0.0.0",
                "port": 8000,
                "protocol_version": 1,
                "session_id": session_id,
                "token": "token",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="loopback"):
        await send_chat_control_command(
            workspace_root=tmp_path,
            session_id=session_id,
            command="status",
        )


@pytest.mark.asyncio
async def test_control_client_rejects_unsupported_command(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        await send_chat_control_command(
            workspace_root=tmp_path,
            session_id="chat-control-command",
            command="restart",
        )


@pytest.mark.asyncio
async def test_control_server_queues_bounded_steer_and_cancels_turn(tmp_path) -> None:
    controller = ActiveTurnController()
    operation_started = asyncio.Event()

    async def operation() -> None:
        operation_started.set()
        await asyncio.Event().wait()

    controlled = asyncio.create_task(controller.run(operation))
    await operation_started.wait()

    async with ChatControlServer(
        workspace_root=tmp_path,
        session_id="chat-control-steer",
        turn_controller=controller,
    ):
        response = await send_chat_control_command(
            workspace_root=tmp_path,
            session_id="chat-control-steer",
            command="steer",
            prompt="  continue with focused tests  ",
        )

    assert response == {
        "active_turn": True,
        "ok": True,
        "session_id": "chat-control-steer",
        "steered": True,
    }
    with pytest.raises(TurnCancelledError):
        await controlled
    assert controller.take_steer_prompt() == "continue with focused tests"


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["   ", "x" * 2049])
async def test_control_client_rejects_invalid_steer_prompt_before_cancel(
    tmp_path,
    prompt: str,
) -> None:
    with pytest.raises(ValueError, match="steer prompt"):
        await send_chat_control_command(
            workspace_root=tmp_path,
            session_id="chat-control-invalid-steer",
            command="steer",
            prompt=prompt,
        )
