"""TLS 1.3 mutual-auth transport for signed checkpoint gossip."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import os
import secrets
import ssl
import stat
from contextlib import suppress
from pathlib import Path
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_gossip_tls_identity import (
    CheckpointPeerTlsTrust,
    certificate_fingerprints,
    resolve_active_tls_peer,
    verify_active_tls_certificate,
)

GOSSIP_MTLS_PROTOCOL_VERSION = 2
MAX_GOSSIP_REQUEST_BYTES = 64 * 1024
MAX_GOSSIP_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_GOSSIP_RETAINED_NONCES = 1024
MAX_GOSSIP_CONCURRENT_CLIENTS = 8
DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS = 2.0

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _validate_identifier(value: str, *, label: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


def _validated_addresses(addresses: frozenset[str], *, label: str) -> frozenset[str]:
    if not addresses:
        raise ValueError(f"checkpoint gossip {label} allowlist must not be empty")
    normalized: set[str] = set()
    for address in addresses:
        try:
            normalized.add(str(ipaddress.ip_address(address)))
        except ValueError as exc:
            raise ValueError(f"checkpoint gossip {label} allowlist is invalid") from exc
    if normalized != set(addresses):
        raise ValueError(f"checkpoint gossip {label} allowlist must be canonical")
    return frozenset(normalized)


def _read_certificate(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError("TLS certificate cannot be read") from exc


def _require_private_key_permissions(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("TLS private key cannot be read") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("TLS private key must be a regular non-symlink file")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o077:
        raise ValueError("TLS private key permissions must not allow group or other access")


class CheckpointMutualTlsGossipDescriptor(_FrozenModel):
    protocol_version: int
    transport: str
    host: str
    port: int = Field(ge=1, le=65535)
    registry_id: str = Field(min_length=1, max_length=200)
    server_peer_id: str = Field(min_length=1, max_length=200)
    server_certificate_sha256: str = Field(pattern=_SHA256_PATTERN)
    server_spki_sha256: str = Field(pattern=_SHA256_PATTERN)
    tls_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    instance_id: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_descriptor(self) -> CheckpointMutualTlsGossipDescriptor:
        if self.protocol_version != GOSSIP_MTLS_PROTOCOL_VERSION:
            raise ValueError("unsupported checkpoint mTLS gossip protocol")
        if self.transport != "mtls":
            raise ValueError("checkpoint gossip transport must be mTLS")
        try:
            if str(ipaddress.ip_address(self.host)) != self.host:
                raise ValueError
        except ValueError as exc:
            raise ValueError("checkpoint gossip descriptor host must be a canonical IP") from exc
        _validate_identifier(self.registry_id, label="registry_id")
        _validate_identifier(self.server_peer_id, label="server_peer_id")
        return self


class _MutualTlsRequest(_FrozenModel):
    protocol_version: int
    registry_id: str
    server_peer_id: str
    client_peer_id: str
    instance_id: str
    client_nonce: str
    operation: str = Field(min_length=1, max_length=100)
    payload: dict[str, object]

    @model_validator(mode="after")
    def validate_request(self) -> _MutualTlsRequest:
        if self.protocol_version != GOSSIP_MTLS_PROTOCOL_VERSION:
            raise ValueError("unsupported checkpoint mTLS gossip protocol")
        for value, label in (
            (self.registry_id, "registry_id"),
            (self.server_peer_id, "server_peer_id"),
            (self.client_peer_id, "client_peer_id"),
            (self.operation, "operation"),
        ):
            _validate_identifier(value, label=label)
        try:
            nonce = base64.b64decode(self.client_nonce, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("checkpoint gossip client nonce is invalid") from exc
        if len(nonce) != 32 or base64.b64encode(nonce).decode() != self.client_nonce:
            raise ValueError("checkpoint gossip client nonce must encode 32 bytes")
        return self


class CheckpointMutualTlsGossipRequestHandler(Protocol):
    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...


class CheckpointMutualTlsGossipServer:
    """Serve bounded requests after CA, hostname, peer pin, and IP authentication."""

    def __init__(
        self,
        *,
        descriptor_path: Path,
        bind_host: str,
        advertised_host: str,
        registry_id: str,
        server_peer_id: str,
        handler: CheckpointMutualTlsGossipRequestHandler,
        tls_trust: CheckpointPeerTlsTrust,
        certificate_path: Path,
        private_key_path: Path,
        certificate_authority_path: Path,
        allowed_client_addresses: frozenset[str],
        request_timeout_seconds: float = DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS,
        max_requests: int = 64,
        max_concurrent_clients: int = MAX_GOSSIP_CONCURRENT_CLIENTS,
    ) -> None:
        _validate_identifier(registry_id, label="registry_id")
        _validate_identifier(server_peer_id, label="server_peer_id")
        if tls_trust.registry_id != registry_id:
            raise ValueError("TLS trust uses another registry")
        try:
            bind_host = str(ipaddress.ip_address(bind_host))
            advertised_host = str(ipaddress.ip_address(advertised_host))
        except ValueError as exc:
            raise ValueError("checkpoint gossip bind and advertised hosts must be IPs") from exc
        if not 0 < request_timeout_seconds <= 30:
            raise ValueError("checkpoint gossip timeout must be in (0, 30] seconds")
        if not 1 <= max_requests <= MAX_GOSSIP_RETAINED_NONCES:
            raise ValueError("checkpoint gossip max_requests is out of bounds")
        if not 1 <= max_concurrent_clients <= 64:
            raise ValueError("checkpoint gossip max concurrent clients is out of bounds")
        _require_private_key_permissions(private_key_path)
        certificate = _read_certificate(certificate_path)
        verify_active_tls_certificate(certificate, tls_trust, server_peer_id)
        certificate_sha256, spki_sha256 = certificate_fingerprints(certificate)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        try:
            context.load_cert_chain(certificate_path, private_key_path)
            context.load_verify_locations(cafile=certificate_authority_path)
        except (OSError, ssl.SSLError) as exc:
            raise ValueError("TLS server credentials are invalid") from exc

        self.descriptor_path = descriptor_path
        self.bind_host = bind_host
        self.advertised_host = advertised_host
        self.registry_id = registry_id
        self.server_peer_id = server_peer_id
        self._handler = handler
        self._tls_trust = tls_trust
        self._certificate_sha256 = certificate_sha256
        self._spki_sha256 = spki_sha256
        self._allowed_client_addresses = _validated_addresses(
            allowed_client_addresses,
            label="client address",
        )
        self._request_timeout_seconds = request_timeout_seconds
        self._max_requests = max_requests
        self._max_concurrent_clients = max_concurrent_clients
        self._ssl_context = context
        self._instance_id = secrets.token_hex(32)
        self._owned_descriptor_text: str | None = None
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
            raise RuntimeError("checkpoint mTLS gossip server is already running")
        if self._stopped.is_set():
            raise RuntimeError("checkpoint mTLS gossip server cannot be restarted")
        server = await asyncio.start_server(
            self._handle_client,
            host=self.bind_host,
            port=0,
            ssl=self._ssl_context,
            ssl_handshake_timeout=0.25,
            limit=MAX_GOSSIP_REQUEST_BYTES,
        )
        sockets = server.sockets
        if not sockets:
            server.close()
            await server.wait_closed()
            raise RuntimeError("checkpoint mTLS gossip server did not bind a socket")
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
            raise RuntimeError("checkpoint mTLS gossip server is not running")
        try:
            if lifetime_timeout_seconds is None:
                await self.wait_stopped()
            else:
                if not 0 < lifetime_timeout_seconds <= 3600:
                    raise ValueError("checkpoint gossip lifetime must be in (0, 3600] seconds")
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self.wait_stopped(), timeout=lifetime_timeout_seconds
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
        client_nonce: str | None = None
        try:
            peername = writer.get_extra_info("peername")
            peer_address = str(ipaddress.ip_address(peername[0])) if peername else ""
            if peer_address not in self._allowed_client_addresses:
                await self._write_response(writer, {"error": "address_not_allowed", "ok": False})
                return
            if len(self._client_writers) > self._max_concurrent_clients:
                await self._write_response(writer, {"error": "server_busy", "ok": False})
                return
            ssl_object = writer.get_extra_info("ssl_object")
            if ssl_object is None or ssl_object.version() != "TLSv1.3":
                raise ValueError("TLS 1.3 session is required")
            peer_certificate = ssl_object.getpeercert(binary_form=True)
            if not peer_certificate:
                raise ValueError("client TLS certificate is missing")
            authenticated_peer_id = resolve_active_tls_peer(
                peer_certificate, self._tls_trust
            )
            raw = await self._read_request_line(reader)
            request = _MutualTlsRequest.model_validate_json(raw)
            client_nonce = request.client_nonce
            if (
                request.registry_id != self.registry_id
                or request.server_peer_id != self.server_peer_id
                or request.instance_id != self._instance_id
                or request.client_peer_id != authenticated_peer_id
            ):
                await self._write_response(
                    writer,
                    self._response(client_nonce, error="endpoint_or_peer_mismatch"),
                )
                return
            async with self._counter_lock:
                if client_nonce in self._used_client_nonces:
                    await self._write_response(
                        writer, self._response(client_nonce, error="replayed_nonce")
                    )
                    return
                if len(self._used_client_nonces) >= MAX_GOSSIP_RETAINED_NONCES:
                    await self._write_response(
                        writer,
                        self._response(client_nonce, error="nonce_capacity_exhausted"),
                    )
                    return
                if self._completed_requests >= self._max_requests:
                    await self._write_response(
                        writer,
                        self._response(client_nonce, error="request_capacity_exhausted"),
                    )
                    return
                self._used_client_nonces.add(client_nonce)
                self._completed_requests += 1
                should_stop = self._completed_requests >= self._max_requests
            try:
                result = await asyncio.wait_for(
                    self._handler.dispatch(request.operation, request.payload),
                    timeout=self._request_timeout_seconds,
                )
                response = self._response(client_nonce, result=result)
                if len(_canonical_json(response).encode()) > MAX_GOSSIP_RESPONSE_BYTES - 1:
                    response = self._response(client_nonce, error="response_too_large")
                await self._write_response(writer, response)
            except TimeoutError:
                await self._write_response(
                    writer, self._response(client_nonce, error="request_timeout")
                )
            except Exception:
                await self._write_response(
                    writer, self._response(client_nonce, error="internal_error")
                )
        except TimeoutError:
            with suppress(ConnectionError):
                await self._write_response(writer, {"error": "request_timeout", "ok": False})
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            with suppress(ConnectionError):
                await self._write_response(writer, {"error": "invalid_request", "ok": False})
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
            reader.readline(), timeout=self._request_timeout_seconds
        )
        if not raw or len(raw) > MAX_GOSSIP_REQUEST_BYTES or not raw.endswith(b"\n"):
            raise ValueError("checkpoint gossip request size is invalid")
        return raw

    def _response(
        self,
        client_nonce: str,
        *,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> dict[str, object]:
        response: dict[str, object] = {
            "client_nonce": client_nonce,
            "instance_id": self._instance_id,
            "ok": error is None,
            "protocol_version": GOSSIP_MTLS_PROTOCOL_VERSION,
            "registry_id": self.registry_id,
            "server_peer_id": self.server_peer_id,
        }
        if error is None:
            response["result"] = result
        else:
            response["error"] = error
        return response

    @staticmethod
    async def _write_response(
        writer: asyncio.StreamWriter,
        response: dict[str, object],
    ) -> None:
        encoded = _canonical_json(response).encode() + b"\n"
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
        descriptor = CheckpointMutualTlsGossipDescriptor(
            protocol_version=GOSSIP_MTLS_PROTOCOL_VERSION,
            transport="mtls",
            host=self.advertised_host,
            port=port,
            registry_id=self.registry_id,
            server_peer_id=self.server_peer_id,
            server_certificate_sha256=self._certificate_sha256,
            server_spki_sha256=self._spki_sha256,
            tls_trust_sha256=self._tls_trust.tls_trust_sha256,
            instance_id=self._instance_id,
        )
        descriptor_text = _canonical_json(descriptor.model_dump(mode="json")) + "\n"
        temporary = path.with_suffix(f".{self._instance_id[:12]}.tmp")
        try:
            temporary.write_text(descriptor_text, encoding="utf-8")
            temporary.chmod(0o600)
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise ValueError("checkpoint gossip descriptor already exists") from exc
        finally:
            temporary.unlink(missing_ok=True)
        path.chmod(0o600)
        self._owned_descriptor_text = descriptor_text

    def _remove_owned_descriptor(self) -> None:
        if self._owned_descriptor_text is None:
            return
        try:
            descriptor_text = self.descriptor_path.read_text(encoding="utf-8")
        except OSError:
            return
        if descriptor_text == self._owned_descriptor_text:
            self.descriptor_path.unlink(missing_ok=True)


class CheckpointMutualTlsGossipClient:
    """Reusable request sender with one pinned mutual-TLS configuration."""

    def __init__(
        self,
        *,
        descriptor_path: Path,
        client_peer_id: str,
        tls_trust: CheckpointPeerTlsTrust,
        certificate_path: Path,
        private_key_path: Path,
        certificate_authority_path: Path,
        server_hostname: str,
        allowed_server_addresses: frozenset[str],
        request_timeout_seconds: float = DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        _validate_identifier(client_peer_id, label="client_peer_id")
        _validate_identifier(server_hostname, label="server_hostname")
        if not 0 < request_timeout_seconds <= 30:
            raise ValueError("checkpoint gossip timeout must be in (0, 30] seconds")
        self.descriptor_path = descriptor_path
        self.client_peer_id = client_peer_id
        self.tls_trust = CheckpointPeerTlsTrust.model_validate(
            tls_trust.model_dump(mode="json")
        )
        self.certificate_path = certificate_path
        self.private_key_path = private_key_path
        self.certificate_authority_path = certificate_authority_path
        self.server_hostname = server_hostname
        self.allowed_server_addresses = _validated_addresses(
            allowed_server_addresses,
            label="server address",
        )
        self.request_timeout_seconds = request_timeout_seconds

    async def __call__(
        self,
        *,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return await send_checkpoint_mtls_gossip_request(
            descriptor_path=self.descriptor_path,
            client_peer_id=self.client_peer_id,
            tls_trust=self.tls_trust,
            certificate_path=self.certificate_path,
            private_key_path=self.private_key_path,
            certificate_authority_path=self.certificate_authority_path,
            server_hostname=self.server_hostname,
            allowed_server_addresses=self.allowed_server_addresses,
            operation=operation,
            payload=payload,
            request_timeout_seconds=self.request_timeout_seconds,
        )


async def send_checkpoint_mtls_gossip_request(
    *,
    descriptor_path: Path,
    client_peer_id: str,
    tls_trust: CheckpointPeerTlsTrust,
    certificate_path: Path,
    private_key_path: Path,
    certificate_authority_path: Path,
    server_hostname: str,
    allowed_server_addresses: frozenset[str],
    operation: str,
    payload: dict[str, object],
    client_nonce: bytes | None = None,
    request_timeout_seconds: float = DEFAULT_GOSSIP_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Send one request only after mutual CA, hostname, address, and peer-pin checks."""
    if not 0 < request_timeout_seconds <= 30:
        raise ValueError("checkpoint gossip timeout must be in (0, 30] seconds")
    _validate_identifier(client_peer_id, label="client_peer_id")
    _validate_identifier(operation, label="operation")
    _validate_identifier(server_hostname, label="server_hostname")
    addresses = _validated_addresses(allowed_server_addresses, label="server address")
    if stat.S_IMODE(descriptor_path.stat().st_mode) != 0o600:
        raise ValueError("checkpoint gossip descriptor permissions must be 0600")
    descriptor = CheckpointMutualTlsGossipDescriptor.model_validate_json(
        descriptor_path.read_text(encoding="utf-8")
    )
    if descriptor.host not in addresses:
        raise ValueError("checkpoint gossip endpoint is outside the server address allowlist")
    if (
        descriptor.registry_id != tls_trust.registry_id
        or descriptor.tls_trust_sha256 != tls_trust.tls_trust_sha256
    ):
        raise ValueError("checkpoint gossip descriptor does not match TLS trust")
    active_server = tls_trust.active_enrollment(descriptor.server_peer_id).statement
    if (
        descriptor.server_certificate_sha256 != active_server.certificate_sha256
        or descriptor.server_spki_sha256 != active_server.spki_sha256
    ):
        raise ValueError("checkpoint gossip descriptor active certificate pin is invalid")
    _require_private_key_permissions(private_key_path)
    verify_active_tls_certificate(
        _read_certificate(certificate_path), tls_trust, client_peer_id
    )
    nonce = client_nonce if client_nonce is not None else secrets.token_bytes(32)
    if len(nonce) != 32:
        raise ValueError("checkpoint gossip client nonce must contain 32 bytes")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    try:
        context.load_verify_locations(cafile=certificate_authority_path)
        context.load_cert_chain(certificate_path, private_key_path)
    except (OSError, ssl.SSLError) as exc:
        raise ValueError("TLS client credentials are invalid") from exc

    writer: asyncio.StreamWriter | None = None
    try:
        reader, connected_writer = await asyncio.wait_for(
            asyncio.open_connection(
                descriptor.host,
                descriptor.port,
                ssl=context,
                server_hostname=server_hostname,
                ssl_handshake_timeout=request_timeout_seconds,
                limit=MAX_GOSSIP_RESPONSE_BYTES,
            ),
            timeout=request_timeout_seconds,
        )
        writer = connected_writer
        peername = connected_writer.get_extra_info("peername")
        peer_address = str(ipaddress.ip_address(peername[0])) if peername else ""
        if peer_address not in addresses:
            raise ValueError("checkpoint gossip connected endpoint is outside allowlist")
        ssl_object = connected_writer.get_extra_info("ssl_object")
        if ssl_object is None or ssl_object.version() != "TLSv1.3":
            raise RuntimeError("checkpoint gossip TLS 1.3 negotiation failed")
        server_certificate = ssl_object.getpeercert(binary_form=True)
        if not server_certificate:
            raise RuntimeError("checkpoint gossip server certificate is missing")
        verify_active_tls_certificate(
            server_certificate, tls_trust, descriptor.server_peer_id
        )
        request = _MutualTlsRequest(
            protocol_version=GOSSIP_MTLS_PROTOCOL_VERSION,
            registry_id=descriptor.registry_id,
            server_peer_id=descriptor.server_peer_id,
            client_peer_id=client_peer_id,
            instance_id=descriptor.instance_id,
            client_nonce=base64.b64encode(nonce).decode(),
            operation=operation,
            payload=payload,
        )
        encoded = _canonical_json(request.model_dump(mode="json")).encode() + b"\n"
        if len(encoded) > MAX_GOSSIP_REQUEST_BYTES:
            raise ValueError("checkpoint gossip request exceeds protocol limit")
        connected_writer.write(encoded)
        await asyncio.wait_for(
            connected_writer.drain(), timeout=request_timeout_seconds
        )
        raw = await asyncio.wait_for(reader.readline(), timeout=request_timeout_seconds)
        if not raw or len(raw) > MAX_GOSSIP_RESPONSE_BYTES or not raw.endswith(b"\n"):
            raise RuntimeError("checkpoint gossip endpoint returned an invalid response")
        response = json.loads(raw)
        if not isinstance(response, dict):
            raise RuntimeError("checkpoint gossip endpoint returned an invalid response")
        expected = {
            "protocol_version": GOSSIP_MTLS_PROTOCOL_VERSION,
            "registry_id": descriptor.registry_id,
            "server_peer_id": descriptor.server_peer_id,
            "instance_id": descriptor.instance_id,
            "client_nonce": request.client_nonce,
        }
        if any(response.get(key) != value for key, value in expected.items()):
            raise RuntimeError("checkpoint gossip endpoint response does not match request")
        if response.get("ok") is not True:
            raise RuntimeError(
                f"checkpoint gossip request rejected: {response.get('error', 'unknown_error')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("checkpoint gossip endpoint returned an invalid result")
        return result
    except ssl.SSLError as exc:
        raise RuntimeError("checkpoint gossip TLS certificate or endpoint failed") from exc
    except ValueError:
        raise
    except (OSError, TimeoutError) as exc:
        raise RuntimeError("checkpoint gossip TLS certificate or endpoint failed") from exc
    finally:
        if writer is not None:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
