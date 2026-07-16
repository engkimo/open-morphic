"""Authenticated loopback transport for controlling one active chat turn."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from contextlib import suppress
from pathlib import Path
from typing import Any, Self

from interface.cli.turn_control import ActiveTurnController

_HOST = "127.0.0.1"
_MAX_LINE_BYTES = 4096
_PROTOCOL_VERSION = 1
_REQUEST_TIMEOUT_SECONDS = 2.0
_SUPPORTED_COMMANDS = frozenset({"cancel", "status"})


class ChatControlServer:
    """Expose one controller through a short-lived authenticated loopback server."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        session_id: str,
        turn_controller: ActiveTurnController,
    ) -> None:
        self._workspace_root = workspace_root
        self._session_id = session_id
        self._turn_controller = turn_controller
        self._token = secrets.token_urlsafe(32)
        self._server: asyncio.Server | None = None
        self._port: int | None = None

    @property
    def descriptor_path(self) -> Path:
        return _descriptor_path(self._workspace_root, self._session_id)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("chat control server is already running")

        server = await asyncio.start_server(
            self._handle_client,
            host=_HOST,
            port=0,
            limit=_MAX_LINE_BYTES,
        )
        sockets = server.sockets
        if not sockets:
            server.close()
            await server.wait_closed()
            raise RuntimeError("chat control server did not bind a socket")

        self._server = server
        self._port = int(sockets[0].getsockname()[1])
        try:
            self._write_descriptor()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        server = self._server
        self._server = None
        self._port = None
        if server is not None:
            server.close()
            await server.wait_closed()
        self._remove_owned_descriptor()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw_request = await asyncio.wait_for(
                reader.readline(),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            response = self._decode_and_dispatch(raw_request)
        except TimeoutError:
            response = {"error": "request_timeout", "ok": False}
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            response = {"error": "invalid_request", "ok": False}

        writer.write(
            json.dumps(response, ensure_ascii=False, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        with suppress(ConnectionError):
            await writer.drain()
        writer.close()
        with suppress(ConnectionError):
            await writer.wait_closed()

    def _decode_and_dispatch(self, raw_request: bytes) -> dict[str, object]:
        if not raw_request or len(raw_request) > _MAX_LINE_BYTES:
            raise ValueError("invalid control request size")
        request = json.loads(raw_request.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("control request must be an object")

        token = request.get("token")
        if not isinstance(token, str) or not secrets.compare_digest(token, self._token):
            return {"error": "unauthorized", "ok": False}
        if request.get("session_id") != self._session_id:
            return {"error": "session_mismatch", "ok": False}

        command = request.get("command")
        if command not in _SUPPORTED_COMMANDS:
            return {"error": "unsupported_command", "ok": False}

        active_turn = self._turn_controller.has_active_turn
        response: dict[str, object] = {
            "active_turn": active_turn,
            "ok": True,
            "session_id": self._session_id,
        }
        if command == "cancel":
            response["cancelled"] = self._turn_controller.cancel_active_turn()
        return response

    def _write_descriptor(self) -> None:
        if self._port is None:
            raise RuntimeError("chat control server is not bound")
        path = self.descriptor_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        payload = {
            "host": _HOST,
            "port": self._port,
            "protocol_version": _PROTOCOL_VERSION,
            "session_id": self._session_id,
            "token": self._token,
        }
        temporary = path.with_suffix(f".{self._token[:12]}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        path.chmod(0o600)

    def _remove_owned_descriptor(self) -> None:
        path = self.descriptor_path
        try:
            descriptor = _read_descriptor(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if descriptor.get("token") == self._token:
            path.unlink(missing_ok=True)


async def send_chat_control_command(
    *,
    workspace_root: Path,
    session_id: str,
    command: str,
) -> dict[str, object]:
    """Send one authenticated command or report an inactive missing descriptor."""
    if command not in _SUPPORTED_COMMANDS:
        raise ValueError(f"unsupported chat control command: {command}")

    descriptor_path = _descriptor_path(workspace_root, session_id)
    if not descriptor_path.exists():
        response: dict[str, object] = {
            "active_turn": False,
            "ok": True,
            "session_id": session_id,
        }
        if command == "cancel":
            response["cancelled"] = False
        return response

    descriptor = _validated_descriptor(descriptor_path, session_id=session_id)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host=str(descriptor["host"]),
                port=int(descriptor["port"]),
                limit=_MAX_LINE_BYTES,
            ),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except (OSError, TimeoutError) as exc:
        raise RuntimeError("chat control endpoint is unavailable") from exc

    request = {
        "command": command,
        "session_id": session_id,
        "token": descriptor["token"],
    }
    try:
        writer.write(
            json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        await writer.drain()
        raw_response = await asyncio.wait_for(
            reader.readline(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    finally:
        writer.close()
        with suppress(ConnectionError):
            await writer.wait_closed()

    response = json.loads(raw_response.decode("utf-8"))
    if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
        raise RuntimeError("chat control endpoint returned an invalid response")
    if response["ok"] is not True:
        error = response.get("error", "unknown_error")
        raise RuntimeError(f"chat control request rejected: {error}")
    return response


def discover_active_chat_sessions(*, workspace_root: Path) -> list[str]:
    """List session ids with syntactically valid local control descriptors."""
    control_dir = workspace_root / ".morphic" / "control"
    if not control_dir.exists():
        return []
    sessions: list[str] = []
    for path in sorted(control_dir.glob("*.json")):
        try:
            descriptor = _validated_descriptor(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        sessions.append(str(descriptor["session_id"]))
    return sessions


def _descriptor_path(workspace_root: Path, session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return workspace_root / ".morphic" / "control" / f"{digest}.json"


def _read_descriptor(path: Path) -> dict[str, Any]:
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(descriptor, dict):
        raise ValueError("chat control descriptor must be an object")
    return descriptor


def _validated_descriptor(
    path: Path,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    descriptor = _read_descriptor(path)
    if descriptor.get("protocol_version") != _PROTOCOL_VERSION:
        raise ValueError("unsupported chat control protocol")
    if descriptor.get("host") != _HOST:
        raise ValueError("chat control host must be loopback")
    port = descriptor.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("invalid chat control port")
    token = descriptor.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("invalid chat control token")
    descriptor_session = descriptor.get("session_id")
    if not isinstance(descriptor_session, str) or not descriptor_session:
        raise ValueError("invalid chat control session")
    if session_id is not None and descriptor_session != session_id:
        raise ValueError("chat control session mismatch")
    return descriptor
