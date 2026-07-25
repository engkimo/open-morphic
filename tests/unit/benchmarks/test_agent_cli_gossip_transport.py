"""Bounded authenticated loopback gossip transport tests."""

from __future__ import annotations

import asyncio
import base64
import json
import stat
from pathlib import Path

import pytest

from benchmarks.agent_cli_gossip_transport import (
    MAX_GOSSIP_REQUEST_BYTES,
    MAX_GOSSIP_RESPONSE_BYTES,
    CheckpointGossipServer,
    send_checkpoint_gossip_request,
)


class _RecordingHandler:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        self.requests.append((operation, payload))
        return {"operation": operation, "payload": payload}


class _OversizedResponseHandler:
    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {"blob": "x" * MAX_GOSSIP_RESPONSE_BYTES}


@pytest.mark.asyncio
async def test_gossip_transport_authenticates_one_use_nonce_and_removes_descriptor(
    tmp_path: Path,
) -> None:
    handler = _RecordingHandler()
    descriptor_path = tmp_path / "gossip" / "source-peer.json"
    nonce = bytes(range(32))

    async with CheckpointGossipServer(
        descriptor_path=descriptor_path,
        registry_id="gossip-registry",
        source_peer_id="peer-1",
        handler=handler,
        max_requests=4,
    ) as server:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        assert descriptor["host"] == "127.0.0.1"
        assert descriptor["protocol_version"] == 1
        assert descriptor["registry_id"] == "gossip-registry"
        assert descriptor["source_peer_id"] == "peer-1"
        assert descriptor["token"]
        assert stat.S_IMODE(descriptor_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(descriptor_path.stat().st_mode) == 0o600

        response = await send_checkpoint_gossip_request(
            descriptor_path=descriptor_path,
            operation="status",
            payload={"cursor": 3},
            client_nonce=nonce,
        )

        assert response == {
            "operation": "status",
            "payload": {"cursor": 3},
        }
        assert handler.requests == [("status", {"cursor": 3})]
        assert server.completed_requests == 1
        with pytest.raises(RuntimeError, match="replayed_nonce"):
            await send_checkpoint_gossip_request(
                descriptor_path=descriptor_path,
                operation="status",
                payload={},
                client_nonce=nonce,
            )
        assert handler.requests == [("status", {"cursor": 3})]

    assert descriptor_path.exists() is False
    assert server.active_client_count == 0


@pytest.mark.asyncio
async def test_gossip_transport_rejects_wrong_token_version_and_oversized_request(
    tmp_path: Path,
) -> None:
    handler = _RecordingHandler()
    descriptor_path = tmp_path / "gossip.json"

    async with CheckpointGossipServer(
        descriptor_path=descriptor_path,
        registry_id="gossip-registry",
        source_peer_id="peer-1",
        handler=handler,
        max_requests=4,
    ):
        original = json.loads(descriptor_path.read_text(encoding="utf-8"))
        wrong_token = dict(original)
        wrong_token["token"] = base64.b64encode(bytes([9]) * 32).decode()
        descriptor_path.write_text(json.dumps(wrong_token), encoding="utf-8")
        descriptor_path.chmod(0o600)
        with pytest.raises(RuntimeError, match="authentication"):
            await send_checkpoint_gossip_request(
                descriptor_path=descriptor_path,
                operation="status",
                payload={},
            )

        unsupported = dict(original)
        unsupported["protocol_version"] = 2
        descriptor_path.write_text(json.dumps(unsupported), encoding="utf-8")
        descriptor_path.chmod(0o600)
        with pytest.raises(ValueError, match="unsupported.*protocol"):
            await send_checkpoint_gossip_request(
                descriptor_path=descriptor_path,
                operation="status",
                payload={},
            )

        descriptor_path.write_text(json.dumps(original), encoding="utf-8")
        descriptor_path.chmod(0o600)
        with pytest.raises(ValueError, match="request.*limit"):
            await send_checkpoint_gossip_request(
                descriptor_path=descriptor_path,
                operation="status",
                payload={"blob": "x" * MAX_GOSSIP_REQUEST_BYTES},
            )

    assert handler.requests == []


@pytest.mark.asyncio
async def test_gossip_transport_bounds_dispatch_timeout_and_request_count(
    tmp_path: Path,
) -> None:
    handler = _RecordingHandler(delay_seconds=0.1)
    descriptor_path = tmp_path / "gossip.json"
    server = CheckpointGossipServer(
        descriptor_path=descriptor_path,
        registry_id="gossip-registry",
        source_peer_id="peer-1",
        handler=handler,
        request_timeout_seconds=0.02,
        max_requests=1,
    )
    await server.start()

    with pytest.raises(RuntimeError, match="request_timeout"):
        await send_checkpoint_gossip_request(
            descriptor_path=descriptor_path,
            operation="status",
            payload={},
            request_timeout_seconds=0.5,
        )
    await asyncio.wait_for(server.wait_stopped(), timeout=0.5)
    await server.close()

    assert server.completed_requests == 1
    assert descriptor_path.exists() is False
    assert handler.requests == []


@pytest.mark.asyncio
async def test_gossip_server_closes_stalled_clients_deterministically(
    tmp_path: Path,
) -> None:
    handler = _RecordingHandler()
    descriptor_path = tmp_path / "gossip.json"
    server = CheckpointGossipServer(
        descriptor_path=descriptor_path,
        registry_id="gossip-registry",
        source_peer_id="peer-1",
        handler=handler,
        request_timeout_seconds=10.0,
        max_requests=4,
    )
    await server.start()
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    reader, writer = await asyncio.open_connection(
        descriptor["host"],
        descriptor["port"],
    )
    for _ in range(20):
        if server.active_client_count:
            break
        await asyncio.sleep(0.001)
    assert server.active_client_count == 1

    await asyncio.wait_for(server.close(), timeout=0.5)

    assert await asyncio.wait_for(reader.read(), timeout=0.5) == b""
    assert server.active_client_count == 0
    assert descriptor_path.exists() is False
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_gossip_server_bounds_read_timeout_concurrency_and_response(
    tmp_path: Path,
) -> None:
    timeout_descriptor = tmp_path / "timeout.json"
    timeout_server = CheckpointGossipServer(
        descriptor_path=timeout_descriptor,
        registry_id="gossip-registry",
        source_peer_id="peer-1",
        handler=_RecordingHandler(),
        request_timeout_seconds=0.02,
        max_requests=2,
    )
    await timeout_server.start()
    descriptor = json.loads(timeout_descriptor.read_text(encoding="utf-8"))
    reader, writer = await asyncio.open_connection(
        descriptor["host"],
        descriptor["port"],
    )

    timeout_response = json.loads(
        await asyncio.wait_for(reader.readline(), timeout=0.5)
    )

    assert timeout_response == {"error": "request_timeout", "ok": False}
    writer.close()
    await writer.wait_closed()
    await timeout_server.close()

    bounded_descriptor = tmp_path / "bounded.json"
    bounded_server = CheckpointGossipServer(
        descriptor_path=bounded_descriptor,
        registry_id="gossip-registry",
        source_peer_id="peer-1",
        handler=_OversizedResponseHandler(),
        max_requests=2,
        max_concurrent_clients=1,
    )
    await bounded_server.start()
    descriptor = json.loads(bounded_descriptor.read_text(encoding="utf-8"))
    _, stalled_writer = await asyncio.open_connection(
        descriptor["host"],
        descriptor["port"],
    )
    for _ in range(20):
        if bounded_server.active_client_count:
            break
        await asyncio.sleep(0.001)
    with pytest.raises(RuntimeError, match="server_busy"):
        await send_checkpoint_gossip_request(
            descriptor_path=bounded_descriptor,
            operation="status",
            payload={},
        )
    stalled_writer.close()
    await stalled_writer.wait_closed()
    for _ in range(20):
        if bounded_server.active_client_count == 0:
            break
        await asyncio.sleep(0.001)
    with pytest.raises(RuntimeError, match="response_too_large"):
        await send_checkpoint_gossip_request(
            descriptor_path=bounded_descriptor,
            operation="status",
            payload={},
        )
    await bounded_server.close()
