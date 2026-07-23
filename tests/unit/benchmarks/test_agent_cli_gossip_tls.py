"""Peer-signed TLS identity and mutual-auth gossip transport tests."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from typer.testing import CliRunner

from benchmarks.agent_cli_checkpoint_registry import (
    CheckpointPeerKeyDeclaration,
    CheckpointPeerTrustDeclaration,
    build_checkpoint_peer_trust,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_gossip_tls_identity import (
    CheckpointPeerTlsEnrollment,
    CheckpointPeerTlsTrust,
    build_checkpoint_peer_tls_enrollment_template,
    build_checkpoint_peer_tls_trust,
    build_signed_checkpoint_peer_tls_enrollment,
)
from benchmarks.agent_cli_gossip_tls_transport import (
    CheckpointMutualTlsGossipServer,
    send_checkpoint_mtls_gossip_request,
)
from interface.cli.main import app

runner = CliRunner()


def _private(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _write_private_key(path: Path, private_key: Ed25519PrivateKey) -> None:
    path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _certificate_authority() -> tuple[Ed25519PrivateKey, x509.Certificate]:
    private_key = _private(80)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Morphic Test CA")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(1)
        .not_valid_before(datetime(2025, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2035, 1, 1, tzinfo=UTC))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key, algorithm=None)
    )
    return private_key, certificate


def _leaf_certificate(
    *,
    common_name: str,
    serial_number: int,
    ca_private_key: Ed25519PrivateKey,
    ca_certificate: x509.Certificate,
) -> tuple[Ed25519PrivateKey, x509.Certificate]:
    private_key = _private(80 + serial_number)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        )
        .issuer_name(ca_certificate.subject)
        .public_key(private_key.public_key())
        .serial_number(serial_number)
        .not_valid_before(datetime(2025, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=UTC))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
            ),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_private_key, algorithm=None)
    )
    return private_key, certificate


def _write_certificate(path: Path, certificate: x509.Certificate) -> None:
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def _identity_context():
    identity_keys = {
        "server-peer": _private(91),
        "client-peer": _private(92),
    }
    trust = build_checkpoint_peer_trust(
        CheckpointPeerTrustDeclaration(
            schema_version=SCHEMA_VERSION,
            registry_id="tls-registry",
            keys=tuple(
                CheckpointPeerKeyDeclaration(
                    peer_id=peer_id,
                    key_id=f"{peer_id}-identity-1",
                    public_key_base64=base64.b64encode(
                        private_key.public_key().public_bytes_raw()
                    ).decode(),
                )
                for peer_id, private_key in identity_keys.items()
            ),
        )
    )
    return identity_keys, trust


def _enrollment(
    certificate: x509.Certificate,
    *,
    peer_id: str,
    identity_key: Ed25519PrivateKey,
    peer_trust,
    generation: int = 1,
    predecessor: CheckpointPeerTlsEnrollment | None = None,
) -> CheckpointPeerTlsEnrollment:
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)
    template = build_checkpoint_peer_tls_enrollment_template(
        certificate_pem,
        peer_trust,
        peer_id=peer_id,
        generation=generation,
        predecessor=predecessor,
    )
    return build_signed_checkpoint_peer_tls_enrollment(
        template,
        certificate_pem,
        peer_trust,
        key_id=f"{peer_id}-identity-1",
        signature_base64=base64.b64encode(
            identity_key.sign(template.statement.signing_bytes())
        ).decode(),
        predecessor=predecessor,
    )


class _RecordingHandler:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        self.requests.append((operation, payload))
        return {"operation": operation, "payload": payload}


@pytest.mark.asyncio
async def test_peer_signed_tls_rotation_and_mutual_tls_transport(
    tmp_path: Path,
) -> None:
    identity_keys, peer_trust = _identity_context()
    ca_key, ca_certificate = _certificate_authority()
    server_key_v1, server_certificate_v1 = _leaf_certificate(
        common_name="server-peer-v1",
        serial_number=1,
        ca_private_key=ca_key,
        ca_certificate=ca_certificate,
    )
    server_key_v2, server_certificate_v2 = _leaf_certificate(
        common_name="server-peer-v2",
        serial_number=2,
        ca_private_key=ca_key,
        ca_certificate=ca_certificate,
    )
    client_key, client_certificate = _leaf_certificate(
        common_name="client-peer",
        serial_number=3,
        ca_private_key=ca_key,
        ca_certificate=ca_certificate,
    )
    server_enrollment_v1 = _enrollment(
        server_certificate_v1,
        peer_id="server-peer",
        identity_key=identity_keys["server-peer"],
        peer_trust=peer_trust,
    )
    server_enrollment_v2 = _enrollment(
        server_certificate_v2,
        peer_id="server-peer",
        identity_key=identity_keys["server-peer"],
        peer_trust=peer_trust,
        generation=2,
        predecessor=server_enrollment_v1,
    )
    client_enrollment = _enrollment(
        client_certificate,
        peer_id="client-peer",
        identity_key=identity_keys["client-peer"],
        peer_trust=peer_trust,
    )
    server_template = build_checkpoint_peer_tls_enrollment_template(
        server_certificate_v1.public_bytes(serialization.Encoding.PEM),
        peer_trust,
        peer_id="server-peer",
        generation=1,
    )
    with pytest.raises(ValueError, match="signature is invalid"):
        build_signed_checkpoint_peer_tls_enrollment(
            server_template,
            server_certificate_v1.public_bytes(serialization.Encoding.PEM),
            peer_trust,
            key_id="server-peer-identity-1",
            signature_base64=base64.b64encode(
                identity_keys["client-peer"].sign(
                    server_template.statement.signing_bytes()
                )
            ).decode(),
        )
    tls_trust = build_checkpoint_peer_tls_trust(
        peer_trust,
        (server_enrollment_v1, server_enrollment_v2, client_enrollment),
    )

    assert tls_trust.active_enrollment("server-peer") == server_enrollment_v2
    assert tls_trust.active_enrollment("client-peer") == client_enrollment
    with pytest.raises(ValueError, match="predecessor"):
        build_checkpoint_peer_tls_trust(
            peer_trust,
            (server_enrollment_v2, client_enrollment),
        )

    ca_path = tmp_path / "ca.pem"
    server_certificate_path = tmp_path / "server-v2.pem"
    server_key_path = tmp_path / "server-v2-key.pem"
    old_server_certificate_path = tmp_path / "server-v1.pem"
    old_server_key_path = tmp_path / "server-v1-key.pem"
    client_certificate_path = tmp_path / "client.pem"
    client_key_path = tmp_path / "client-key.pem"
    _write_certificate(ca_path, ca_certificate)
    _write_certificate(server_certificate_path, server_certificate_v2)
    _write_private_key(server_key_path, server_key_v2)
    _write_certificate(old_server_certificate_path, server_certificate_v1)
    _write_private_key(old_server_key_path, server_key_v1)
    _write_certificate(client_certificate_path, client_certificate)
    _write_private_key(client_key_path, client_key)

    with pytest.raises(ValueError, match="active.*certificate pin"):
        CheckpointMutualTlsGossipServer(
            descriptor_path=tmp_path / "old-server.json",
            bind_host="127.0.0.1",
            advertised_host="127.0.0.1",
            registry_id="tls-registry",
            server_peer_id="server-peer",
            handler=_RecordingHandler(),
            tls_trust=tls_trust,
            certificate_path=old_server_certificate_path,
            private_key_path=old_server_key_path,
            certificate_authority_path=ca_path,
            allowed_client_addresses=frozenset({"127.0.0.1"}),
        )

    handler = _RecordingHandler()
    descriptor_path = tmp_path / "remote-gossip.json"
    async with CheckpointMutualTlsGossipServer(
        descriptor_path=descriptor_path,
        bind_host="127.0.0.1",
        advertised_host="127.0.0.1",
        registry_id="tls-registry",
        server_peer_id="server-peer",
        handler=handler,
        tls_trust=tls_trust,
        certificate_path=server_certificate_path,
        private_key_path=server_key_path,
        certificate_authority_path=ca_path,
        allowed_client_addresses=frozenset({"127.0.0.1"}),
        max_requests=4,
    ) as server:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        assert descriptor["transport"] == "mtls"
        assert descriptor["protocol_version"] == 2
        assert descriptor["server_peer_id"] == "server-peer"
        assert "token" not in descriptor
        assert stat.S_IMODE(descriptor_path.stat().st_mode) == 0o600

        response = await send_checkpoint_mtls_gossip_request(
            descriptor_path=descriptor_path,
            client_peer_id="client-peer",
            tls_trust=tls_trust,
            certificate_path=client_certificate_path,
            private_key_path=client_key_path,
            certificate_authority_path=ca_path,
            server_hostname="localhost",
            allowed_server_addresses=frozenset({"127.0.0.1"}),
            operation="status",
            payload={"cursor": 3},
            client_nonce=bytes(range(32)),
        )

        assert response == {"operation": "status", "payload": {"cursor": 3}}
        assert handler.requests == [("status", {"cursor": 3})]
        assert server.completed_requests == 1
        with pytest.raises(RuntimeError, match="replayed_nonce"):
            await send_checkpoint_mtls_gossip_request(
                descriptor_path=descriptor_path,
                client_peer_id="client-peer",
                tls_trust=tls_trust,
                certificate_path=client_certificate_path,
                private_key_path=client_key_path,
                certificate_authority_path=ca_path,
                server_hostname="localhost",
                allowed_server_addresses=frozenset({"127.0.0.1"}),
                operation="status",
                payload={},
                client_nonce=bytes(range(32)),
            )
        with pytest.raises(RuntimeError, match="TLS|certificate|endpoint"):
            await send_checkpoint_mtls_gossip_request(
                descriptor_path=descriptor_path,
                client_peer_id="client-peer",
                tls_trust=tls_trust,
                certificate_path=client_certificate_path,
                private_key_path=client_key_path,
                certificate_authority_path=ca_path,
                server_hostname="wrong.example",
                allowed_server_addresses=frozenset({"127.0.0.1"}),
                operation="status",
                payload={},
            )
        with pytest.raises(ValueError, match="allowlist"):
            await send_checkpoint_mtls_gossip_request(
                descriptor_path=descriptor_path,
                client_peer_id="client-peer",
                tls_trust=tls_trust,
                certificate_path=client_certificate_path,
                private_key_path=client_key_path,
                certificate_authority_path=ca_path,
                server_hostname="localhost",
                allowed_server_addresses=frozenset({"192.0.2.1"}),
                operation="status",
                payload={},
            )

        tls_trust_path = tmp_path / "tls-trust.json"
        tls_trust_path.write_text(tls_trust.to_json(), encoding="utf-8")
        (tmp_path / "peer-trust.json").write_text(
            peer_trust.to_json(), encoding="utf-8"
        )
        cli_status = await asyncio.to_thread(
            runner.invoke,
            app,
            [
                "benchmark",
                "agent-cli-checkpoint-gossip-mtls-status",
                "--descriptor",
                str(descriptor_path),
                "--tls-trust",
                str(tls_trust_path),
                "--peer-trust",
                str(tmp_path / "peer-trust.json"),
                "--client-peer-id",
                "client-peer",
                "--certificate",
                str(client_certificate_path),
                "--private-key",
                str(client_key_path),
                "--certificate-authority",
                str(ca_path),
                "--server-hostname",
                "localhost",
                "--allow-server-address",
                "127.0.0.1",
                "--json",
            ],
        )
        assert cli_status.exit_code == 0, cli_status.output
        assert json.loads(cli_status.output) == {"operation": "status", "payload": {}}

        reader, writer = await asyncio.open_connection(
            descriptor["host"],
            descriptor["port"],
        )
        writer.write(b'{"operation":"status"}\n')
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), timeout=1.0) == b""
        writer.close()
        await writer.wait_closed()

    assert descriptor_path.exists() is False
    assert server.active_client_count == 0


def test_tls_identity_cli_is_private_key_free(tmp_path: Path) -> None:
    identity_keys, peer_trust = _identity_context()
    ca_key, ca_certificate = _certificate_authority()
    _, server_certificate = _leaf_certificate(
        common_name="server-peer",
        serial_number=4,
        ca_private_key=ca_key,
        ca_certificate=ca_certificate,
    )
    peer_trust_path = tmp_path / "peer-trust.json"
    certificate_path = tmp_path / "server.pem"
    template_path = tmp_path / "tls-enrollment-template.json"
    peer_trust_path.write_text(peer_trust.to_json(), encoding="utf-8")
    _write_certificate(certificate_path, server_certificate)

    template_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-peer-tls-enrollment-template",
            "--certificate",
            str(certificate_path),
            "--peer-trust",
            str(peer_trust_path),
            "--peer-id",
            "server-peer",
            "--generation",
            "1",
            "--output",
            str(template_path),
            "--json",
        ],
    )

    assert template_result.exit_code == 0, template_result.output
    assert "private" not in template_path.read_text(encoding="utf-8").lower()
    template = build_checkpoint_peer_tls_enrollment_template(
        certificate_path.read_bytes(),
        peer_trust,
        peer_id="server-peer",
        generation=1,
    )
    enrollment = build_signed_checkpoint_peer_tls_enrollment(
        template,
        certificate_path.read_bytes(),
        peer_trust,
        key_id="server-peer-identity-1",
        signature_base64=base64.b64encode(
            identity_keys["server-peer"].sign(template.statement.signing_bytes())
        ).decode(),
    )
    enrollment_path = tmp_path / "tls-enrollment.json"
    enrollment_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-peer-tls-enrollment",
            "--template",
            str(template_path),
            "--certificate",
            str(certificate_path),
            "--peer-trust",
            str(peer_trust_path),
            "--key-id",
            "server-peer-identity-1",
            "--signature-base64",
            enrollment.signature_base64,
            "--output",
            str(enrollment_path),
            "--json",
        ],
    )
    assert enrollment_result.exit_code == 0, enrollment_result.output
    assert CheckpointPeerTlsEnrollment.model_validate_json(
        enrollment_path.read_text(encoding="utf-8")
    ) == enrollment
    enrollments_path = tmp_path / "tls-enrollments.json"
    enrollments_path.write_text(
        json.dumps(
            {"enrollments": [enrollment.model_dump(mode="json")]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    tls_trust_path = tmp_path / "tls-trust.json"
    trust_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-peer-tls-trust",
            "--peer-trust",
            str(peer_trust_path),
            "--enrollments",
            str(enrollments_path),
            "--output",
            str(tls_trust_path),
            "--json",
        ],
    )

    assert trust_result.exit_code == 0, trust_result.output
    assert CheckpointPeerTlsTrust.model_validate_json(
        tls_trust_path.read_text(encoding="utf-8")
    ).active_enrollment("server-peer") == enrollment
    serve_help = runner.invoke(
        app,
        ["benchmark", "agent-cli-checkpoint-gossip-mtls-serve", "--help"],
    )
    assert serve_help.exit_code == 0, serve_help.output
    assert "Allowed client IP" in serve_help.output
