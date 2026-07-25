"""Bounded authenticated loopback transport for signed checkpoint gossip."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import stat
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

GOSSIP_PROTOCOL_VERSION = 1
GOSSIP_LOOPBACK_HOST = "127.0.0.1"
MAX_GOSSIP_REQUEST_BYTES = 64 * 1024
MAX_GOSSIP_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_GOSSIP_RETAINED_NONCES = 1024
MAX_GOSSIP_CONCURRENT_CLIENTS = 8
DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS = 2.0

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_base64(value: str, *, label: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


def _validate_identifier(identifier: str, *, label: str) -> None:
    if not identifier or identifier != identifier.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


def _authentication_sha256(token: bytes, payload: object) -> str:
    return hmac.new(
        token,
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class CheckpointGossipDescriptor(_FrozenModel):
    protocol_version: int
    host: str
    port: int = Field(ge=1, le=65535)
    registry_id: str = Field(min_length=1, max_length=200)
    source_peer_id: str = Field(min_length=1, max_length=200)
    instance_id: str = Field(pattern=_SHA256_PATTERN)
    token: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_descriptor(self) -> CheckpointGossipDescriptor:
        if self.protocol_version != GOSSIP_PROTOCOL_VERSION:
            raise ValueError("unsupported checkpoint gossip protocol")
        if self.host != GOSSIP_LOOPBACK_HOST:
            raise ValueError("checkpoint gossip host must be loopback")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        _decode_base64(self.token, label="checkpoint gossip token", length=32)
        return self


class _ChallengeRequest(_FrozenModel):
    phase: str
    protocol_version: int
    registry_id: str
    source_peer_id: str
    instance_id: str
    client_nonce: str

    @model_validator(mode="after")
    def validate_challenge(self) -> _ChallengeRequest:
        if self.phase != "challenge":
            raise ValueError("checkpoint gossip challenge phase is invalid")
        if self.protocol_version != GOSSIP_PROTOCOL_VERSION:
            raise ValueError("unsupported checkpoint gossip protocol")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        if not self.instance_id:
            raise ValueError("checkpoint gossip instance_id is required")
        _decode_base64(self.client_nonce, label="checkpoint gossip client nonce", length=32)
        return self


class _AuthenticatedRequest(_FrozenModel):
    phase: str
    protocol_version: int
    registry_id: str
    source_peer_id: str
    instance_id: str
    client_nonce: str
    server_nonce: str
    operation: str = Field(min_length=1, max_length=100)
    payload: dict[str, object]
    authentication_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_request(self) -> _AuthenticatedRequest:
        if self.phase != "request":
            raise ValueError("checkpoint gossip request phase is invalid")
        if self.protocol_version != GOSSIP_PROTOCOL_VERSION:
            raise ValueError("unsupported checkpoint gossip protocol")
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.source_peer_id, label="source_peer_id")
        _validate_identifier(self.operation, label="operation")
        _decode_base64(self.client_nonce, label="checkpoint gossip client nonce", length=32)
        _decode_base64(self.server_nonce, label="checkpoint gossip server nonce", length=32)
        return self

    def binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"authentication_sha256"})


class CheckpointGossipRequestHandler(Protocol):
    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...


class CheckpointGossipServer:
    """Serve bounded challenge-authenticated requests on one loopback socket."""

    def __init__(
        self,
        *,
        descriptor_path: Path,
        registry_id: str,
        source_peer_id: str,
        handler: CheckpointGossipRequestHandler,
        request_timeout_seconds: float = DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS,
        max_requests: int = 64,
        max_concurrent_clients: int = MAX_GOSSIP_CONCURRENT_CLIENTS,
    ) -> None:
        _validate_identifier(registry_id, label="registry_id")
        _validate_identifier(source_peer_id, label="source_peer_id")
        if not 0 < request_timeout_seconds <= 30:
            raise ValueError("checkpoint gossip timeout must be in (0, 30] seconds")
        if not 1 <= max_requests <= MAX_GOSSIP_RETAINED_NONCES:
            raise ValueError("checkpoint gossip max_requests is out of bounds")
        if not 1 <= max_concurrent_clients <= 64:
            raise ValueError("checkpoint gossip max concurrent clients is out of bounds")
        self.descriptor_path = descriptor_path
        self.registry_id = registry_id
        self.source_peer_id = source_peer_id
        self._handler = handler
        self._request_timeout_seconds = request_timeout_seconds
        self._max_requests = max_requests
        self._max_concurrent_clients = max_concurrent_clients
        self._token = secrets.token_bytes(32)
        self._instance_id = secrets.token_hex(32)
        self._server: asyncio.Server | None = None
        self._client_tasks: set[asyncio.Task[object]] = set()
        self._client_writers: set[asyncio.StreamWriter] = set()
        self._used_client_nonces: set[str] = set()
        self._counter_lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._completed_requests = 0

    @property
    def completed_requests(self) -> int:
        return self._completed_requests

    @property
    def active_client_count(self) -> int:
        return len(self._client_writers)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("checkpoint gossip server is already running")
        if self._stopped.is_set():
            raise RuntimeError("checkpoint gossip server cannot be restarted")
        server = await asyncio.start_server(
            self._handle_client,
            host=GOSSIP_LOOPBACK_HOST,
            port=0,
            limit=MAX_GOSSIP_REQUEST_BYTES,
        )
        sockets = server.sockets
        if not sockets:
            server.close()
            await server.wait_closed()
            raise RuntimeError("checkpoint gossip server did not bind a socket")
        self._server = server
        try:
            self._write_descriptor(int(sockets[0].getsockname()[1]))
        except Exception:
            await self.close()
            raise

    async def wait_stopped(self) -> None:
        await self._stopped.wait()

    async def serve_until_stopped(
        self,
        *,
        lifetime_timeout_seconds: float | None = None,
    ) -> None:
        if self._server is None:
            raise RuntimeError("checkpoint gossip server is not running")
        try:
            if lifetime_timeout_seconds is None:
                await self.wait_stopped()
            else:
                if not 0 < lifetime_timeout_seconds <= 3600:
                    raise ValueError(
                        "checkpoint gossip lifetime must be in (0, 3600] seconds"
                    )
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self.wait_stopped(),
                        timeout=lifetime_timeout_seconds,
                    )
        finally:
            await self.close()

    async def close(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            server.close()
        self._stopped.set()
        current = asyncio.current_task()
        tasks = tuple(task for task in self._client_tasks if task is not current)
        for writer in tuple(self._client_writers):
            writer.close()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:
            await server.wait_closed()
        for writer in tuple(self._client_writers):
            with suppress(ConnectionError):
                await writer.wait_closed()
        self._remove_owned_descriptor()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._client_tasks.add(task)
        self._client_writers.add(writer)
        should_stop = False
        try:
            if len(self._client_writers) > self._max_concurrent_clients:
                await self._write_response(
                    writer,
                    {"error": "server_busy", "ok": False},
                )
                return
            challenge_raw = await self._read_request_line(reader)
            challenge = _ChallengeRequest.model_validate_json(challenge_raw)
            if (
                challenge.registry_id != self.registry_id
                or challenge.source_peer_id != self.source_peer_id
                or challenge.instance_id != self._instance_id
            ):
                await self._write_response(
                    writer,
                    {"error": "endpoint_mismatch", "ok": False},
                )
                return
            if challenge.client_nonce in self._used_client_nonces:
                await self._write_response(
                    writer,
                    {"error": "replayed_nonce", "ok": False},
                )
                return
            if len(self._used_client_nonces) >= MAX_GOSSIP_RETAINED_NONCES:
                await self._write_response(
                    writer,
                    {"error": "nonce_capacity_exhausted", "ok": False},
                )
                return
            self._used_client_nonces.add(challenge.client_nonce)
            server_nonce = base64.b64encode(secrets.token_bytes(32)).decode()
            challenge_response = {
                "client_nonce": challenge.client_nonce,
                "instance_id": self._instance_id,
                "ok": True,
                "phase": "challenge",
                "protocol_version": GOSSIP_PROTOCOL_VERSION,
                "registry_id": self.registry_id,
                "server_nonce": server_nonce,
                "source_peer_id": self.source_peer_id,
            }
            await self._write_authenticated_response(writer, challenge_response)

            request_raw = await self._read_request_line(reader)
            request = _AuthenticatedRequest.model_validate_json(request_raw)
            if (
                request.registry_id != self.registry_id
                or request.source_peer_id != self.source_peer_id
                or request.instance_id != self._instance_id
                or request.client_nonce != challenge.client_nonce
                or request.server_nonce != server_nonce
            ):
                await self._write_authenticated_error(
                    writer,
                    challenge.client_nonce,
                    server_nonce,
                    "challenge_mismatch",
                )
                return
            expected_authentication = _authentication_sha256(
                self._token,
                request.binding_payload(),
            )
            if not hmac.compare_digest(
                request.authentication_sha256,
                expected_authentication,
            ):
                await self._write_authenticated_error(
                    writer,
                    challenge.client_nonce,
                    server_nonce,
                    "unauthorized",
                )
                return
            async with self._counter_lock:
                if self._completed_requests >= self._max_requests:
                    await self._write_authenticated_error(
                        writer,
                        challenge.client_nonce,
                        server_nonce,
                        "request_capacity_exhausted",
                    )
                    return
                self._completed_requests += 1
                should_stop = self._completed_requests >= self._max_requests
            try:
                result = await asyncio.wait_for(
                    self._handler.dispatch(request.operation, request.payload),
                    timeout=self._request_timeout_seconds,
                )
                response = self._response_payload(
                    client_nonce=challenge.client_nonce,
                    server_nonce=server_nonce,
                    result=result,
                )
                if len(_canonical_json(response).encode("utf-8")) > (
                    MAX_GOSSIP_RESPONSE_BYTES - 128
                ):
                    await self._write_authenticated_error(
                        writer,
                        challenge.client_nonce,
                        server_nonce,
                        "response_too_large",
                    )
                else:
                    await self._write_authenticated_response(writer, response)
            except TimeoutError:
                await self._write_authenticated_error(
                    writer,
                    challenge.client_nonce,
                    server_nonce,
                    "request_timeout",
                )
            except GossipRequestError as exc:
                await self._write_authenticated_error(
                    writer,
                    challenge.client_nonce,
                    server_nonce,
                    exc.code,
                )
            except Exception:
                await self._write_authenticated_error(
                    writer,
                    challenge.client_nonce,
                    server_nonce,
                    "internal_error",
                )
        except TimeoutError:
            with suppress(ConnectionError):
                await self._write_response(
                    writer,
                    {"error": "request_timeout", "ok": False},
                )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            with suppress(ConnectionError):
                await self._write_response(
                    writer,
                    {"error": "invalid_request", "ok": False},
                )
        except ConnectionError:
            pass
        except asyncio.CancelledError:
            raise
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            self._client_writers.discard(writer)
            if task is not None:
                self._client_tasks.discard(task)
            if should_stop:
                server = self._server
                if server is not None:
                    server.close()
                self._stopped.set()

    async def _read_request_line(self, reader: asyncio.StreamReader) -> bytes:
        raw = await asyncio.wait_for(
            reader.readline(),
            timeout=self._request_timeout_seconds,
        )
        if not raw or len(raw) > MAX_GOSSIP_REQUEST_BYTES or not raw.endswith(b"\n"):
            raise ValueError("checkpoint gossip request size is invalid")
        return raw

    async def _write_authenticated_error(
        self,
        writer: asyncio.StreamWriter,
        client_nonce: str,
        server_nonce: str,
        error: str,
    ) -> None:
        await self._write_authenticated_response(
            writer,
            {
                "client_nonce": client_nonce,
                "error": error,
                "instance_id": self._instance_id,
                "ok": False,
                "phase": "response",
                "protocol_version": GOSSIP_PROTOCOL_VERSION,
                "registry_id": self.registry_id,
                "server_nonce": server_nonce,
                "source_peer_id": self.source_peer_id,
            },
        )

    def _response_payload(
        self,
        *,
        client_nonce: str,
        server_nonce: str,
        result: dict[str, object],
    ) -> dict[str, object]:
        return {
            "client_nonce": client_nonce,
            "instance_id": self._instance_id,
            "ok": True,
            "phase": "response",
            "protocol_version": GOSSIP_PROTOCOL_VERSION,
            "registry_id": self.registry_id,
            "result": result,
            "server_nonce": server_nonce,
            "source_peer_id": self.source_peer_id,
        }

    async def _write_authenticated_response(
        self,
        writer: asyncio.StreamWriter,
        response: dict[str, object],
    ) -> None:
        authenticated = {
            **response,
            "authentication_sha256": _authentication_sha256(self._token, response),
        }
        await self._write_response(writer, authenticated)

    @staticmethod
    async def _write_response(
        writer: asyncio.StreamWriter,
        response: dict[str, object],
    ) -> None:
        encoded = _canonical_json(response).encode("utf-8") + b"\n"
        if len(encoded) > MAX_GOSSIP_RESPONSE_BYTES:
            raise ValueError("checkpoint gossip response exceeds protocol limit")
        writer.write(encoded)
        await writer.drain()

    def _write_descriptor(self, port: int) -> None:
        path = self.descriptor_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        if path.exists():
            raise ValueError("checkpoint gossip descriptor already exists")
        descriptor = CheckpointGossipDescriptor(
            protocol_version=GOSSIP_PROTOCOL_VERSION,
            host=GOSSIP_LOOPBACK_HOST,
            port=port,
            registry_id=self.registry_id,
            source_peer_id=self.source_peer_id,
            instance_id=self._instance_id,
            token=base64.b64encode(self._token).decode(),
        )
        temporary = path.with_suffix(f".{self._instance_id[:12]}.tmp")
        try:
            temporary.write_text(
                _canonical_json(descriptor.model_dump(mode="json")) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        path.chmod(0o600)

    def _remove_owned_descriptor(self) -> None:
        try:
            payload = json.loads(self.descriptor_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if (
            payload.get("instance_id") == self._instance_id
            and payload.get("token") == base64.b64encode(self._token).decode()
        ):
            self.descriptor_path.unlink(missing_ok=True)


class GossipRequestError(ValueError):
    """A safe protocol error code returned by a checkpoint gossip handler."""

    def __init__(self, code: str) -> None:
        _validate_identifier(code, label="checkpoint gossip error code")
        self.code = code
        super().__init__(code)


async def send_checkpoint_gossip_request(
    *,
    descriptor_path: Path,
    operation: str,
    payload: dict[str, object],
    client_nonce: bytes | None = None,
    request_timeout_seconds: float = DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Send one bounded request after a one-use authenticated nonce challenge."""
    _validate_identifier(operation, label="operation")
    if not 0 < request_timeout_seconds <= 30:
        raise ValueError("checkpoint gossip timeout must be in (0, 30] seconds")
    descriptor = _read_validated_descriptor(descriptor_path)
    token = _decode_base64(
        descriptor.token,
        label="checkpoint gossip token",
        length=32,
    )
    nonce_bytes = client_nonce if client_nonce is not None else secrets.token_bytes(32)
    if len(nonce_bytes) != 32:
        raise ValueError("checkpoint gossip client nonce must contain 32 bytes")
    client_nonce_base64 = base64.b64encode(nonce_bytes).decode()
    challenge = {
        "client_nonce": client_nonce_base64,
        "instance_id": descriptor.instance_id,
        "phase": "challenge",
        "protocol_version": GOSSIP_PROTOCOL_VERSION,
        "registry_id": descriptor.registry_id,
        "source_peer_id": descriptor.source_peer_id,
    }
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                descriptor.host,
                descriptor.port,
                limit=MAX_GOSSIP_RESPONSE_BYTES,
            ),
            timeout=request_timeout_seconds,
        )
    except (OSError, TimeoutError) as exc:
        raise RuntimeError("checkpoint gossip endpoint is unavailable") from exc
    try:
        await _client_write_request(writer, challenge)
        challenge_response = await _client_read_response(
            reader,
            timeout_seconds=request_timeout_seconds,
        )
        if challenge_response.get("ok") is not True:
            raise RuntimeError(
                "checkpoint gossip request rejected: "
                f"{challenge_response.get('error', 'unknown_error')}"
            )
        _verify_authenticated_response(
            challenge_response,
            token=token,
            descriptor=descriptor,
            client_nonce=client_nonce_base64,
        )
        server_nonce = challenge_response.get("server_nonce")
        if not isinstance(server_nonce, str):
            raise RuntimeError("checkpoint gossip challenge is invalid")
        _decode_base64(
            server_nonce,
            label="checkpoint gossip server nonce",
            length=32,
        )
        request_payload = {
            "client_nonce": client_nonce_base64,
            "instance_id": descriptor.instance_id,
            "operation": operation,
            "payload": payload,
            "phase": "request",
            "protocol_version": GOSSIP_PROTOCOL_VERSION,
            "registry_id": descriptor.registry_id,
            "server_nonce": server_nonce,
            "source_peer_id": descriptor.source_peer_id,
        }
        authenticated_request = {
            **request_payload,
            "authentication_sha256": _authentication_sha256(token, request_payload),
        }
        await _client_write_request(writer, authenticated_request)
        response = await _client_read_response(
            reader,
            timeout_seconds=request_timeout_seconds,
        )
        _verify_authenticated_response(
            response,
            token=token,
            descriptor=descriptor,
            client_nonce=client_nonce_base64,
            server_nonce=server_nonce,
        )
        if response.get("ok") is not True:
            raise RuntimeError(
                "checkpoint gossip request rejected: "
                f"{response.get('error', 'unknown_error')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("checkpoint gossip endpoint returned an invalid result")
        return result
    finally:
        writer.close()
        with suppress(ConnectionError):
            await writer.wait_closed()


def _read_validated_descriptor(path: Path) -> CheckpointGossipDescriptor:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("checkpoint gossip descriptor permissions must be 0600")
    return CheckpointGossipDescriptor.model_validate_json(path.read_text(encoding="utf-8"))


async def _client_write_request(
    writer: asyncio.StreamWriter,
    payload: dict[str, object],
) -> None:
    encoded = _canonical_json(payload).encode("utf-8") + b"\n"
    if len(encoded) > MAX_GOSSIP_REQUEST_BYTES:
        raise ValueError("checkpoint gossip request exceeds protocol request limit")
    writer.write(encoded)
    await writer.drain()


async def _client_read_response(
    reader: asyncio.StreamReader,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    raw = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
    if not raw or len(raw) > MAX_GOSSIP_RESPONSE_BYTES or not raw.endswith(b"\n"):
        raise RuntimeError("checkpoint gossip endpoint returned an invalid response")
    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
        raise RuntimeError("checkpoint gossip endpoint returned an invalid response")
    return response


def _verify_authenticated_response(
    response: dict[str, Any],
    *,
    token: bytes,
    descriptor: CheckpointGossipDescriptor,
    client_nonce: str,
    server_nonce: str | None = None,
) -> None:
    authentication = response.get("authentication_sha256")
    if not isinstance(authentication, str):
        raise RuntimeError("checkpoint gossip response authentication is missing")
    binding = {
        key: value
        for key, value in response.items()
        if key != "authentication_sha256"
    }
    expected = _authentication_sha256(token, binding)
    if not hmac.compare_digest(authentication, expected):
        raise RuntimeError("checkpoint gossip response authentication is invalid")
    if (
        response.get("protocol_version") != GOSSIP_PROTOCOL_VERSION
        or response.get("instance_id") != descriptor.instance_id
        or response.get("client_nonce") != client_nonce
        or response.get("registry_id") != descriptor.registry_id
        or response.get("source_peer_id") != descriptor.source_peer_id
    ):
        raise RuntimeError("checkpoint gossip response challenge does not match")
    if server_nonce is not None and response.get("server_nonce") != server_nonce:
        raise RuntimeError("checkpoint gossip response server nonce does not match")
