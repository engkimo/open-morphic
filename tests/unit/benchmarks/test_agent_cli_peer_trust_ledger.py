"""Peer-trust generation ledger and rollover continuity tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from benchmarks.agent_cli_checkpoint_registry import (
    CheckpointPeerKeyDeclaration,
    CheckpointPeerTrust,
    CheckpointPeerTrustDeclaration,
    build_checkpoint_peer_trust,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_peer_trust_ledger import (
    CheckpointPeerRotationSignature,
    CheckpointPeerTrustGeneration,
    CheckpointPeerTrustLedger,
    build_checkpoint_peer_trust_ledger,
    build_checkpoint_peer_trust_rotation_certificate,
    build_checkpoint_peer_trust_rotation_template,
)
from interface.cli.main import app

runner = CliRunner()


def _private(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _trust_context():
    predecessor_keys = {
        f"peer-{index}": _private(70 + index) for index in range(1, 4)
    }
    successor_keys = dict(predecessor_keys)
    successor_keys["peer-2-next"] = _private(79)
    predecessor = build_checkpoint_peer_trust(
        CheckpointPeerTrustDeclaration(
            schema_version=SCHEMA_VERSION,
            registry_id="rotation-registry",
            keys=tuple(
                CheckpointPeerKeyDeclaration(
                    peer_id=peer_id,
                    key_id=f"{peer_id}-key-1",
                    public_key_base64=base64.b64encode(
                        private_key.public_key().public_bytes_raw()
                    ).decode(),
                )
                for peer_id, private_key in predecessor_keys.items()
            ),
        )
    )
    successor_declarations = []
    for peer_id, private_key in predecessor_keys.items():
        successor_declarations.append(
            CheckpointPeerKeyDeclaration(
                peer_id=peer_id,
                key_id=f"{peer_id}-key-1",
                public_key_base64=base64.b64encode(
                    private_key.public_key().public_bytes_raw()
                ).decode(),
                status="revoked" if peer_id == "peer-2" else "active",
            )
        )
    successor_declarations.append(
        CheckpointPeerKeyDeclaration(
            peer_id="peer-2",
            key_id="peer-2-key-2",
            public_key_base64=base64.b64encode(
                successor_keys["peer-2-next"].public_key().public_bytes_raw()
            ).decode(),
        )
    )
    successor = build_checkpoint_peer_trust(
        CheckpointPeerTrustDeclaration(
            schema_version=SCHEMA_VERSION,
            registry_id="rotation-registry",
            keys=tuple(successor_declarations),
        )
    )
    return predecessor_keys, successor_keys, predecessor, successor


def _rotation_certificate(
    predecessor: CheckpointPeerTrust,
    successor: CheckpointPeerTrust,
    predecessor_keys: dict[str, Ed25519PrivateKey],
    *,
    signers: tuple[str, ...] = ("peer-1", "peer-2"),
):
    template = build_checkpoint_peer_trust_rotation_template(
        predecessor,
        successor,
        generation=2,
    )
    requests = {request.peer_id: request for request in template.requests}
    signatures = tuple(
        CheckpointPeerRotationSignature(
            peer_id=peer_id,
            key_id=f"{peer_id}-key-1",
            signature_base64=base64.b64encode(
                predecessor_keys[peer_id].sign(
                    requests[peer_id].statement.signing_bytes()
                )
            ).decode(),
        )
        for peer_id in signers
    )
    return template, build_checkpoint_peer_trust_rotation_certificate(
        template,
        predecessor,
        successor,
        signatures,
    )


def test_peer_trust_ledger_resolves_historical_and_active_generations() -> None:
    predecessor_keys, _, predecessor, successor = _trust_context()
    template, rotation = _rotation_certificate(
        predecessor,
        successor,
        predecessor_keys,
    )

    ledger = build_checkpoint_peer_trust_ledger(
        (
            CheckpointPeerTrustGeneration(
                schema_version=SCHEMA_VERSION,
                generation=1,
                trust=predecessor,
            ),
            CheckpointPeerTrustGeneration(
                schema_version=SCHEMA_VERSION,
                generation=2,
                trust=successor,
                rotation=rotation,
            ),
        )
    )

    assert template.minimum_distinct_peer_signatures == 2
    assert ledger.active_generation == 2
    assert ledger.active_trust == successor
    assert ledger.resolve_peer_trust(predecessor.peer_trust_sha256) == predecessor
    assert ledger.resolve_peer_trust(successor.peer_trust_sha256) == successor
    with pytest.raises(ValueError, match="not present in peer trust ledger"):
        ledger.resolve_peer_trust("f" * 64)


def test_peer_trust_rotation_rejects_minority_and_untrusted_keys() -> None:
    predecessor_keys, successor_keys, predecessor, successor = _trust_context()
    template = build_checkpoint_peer_trust_rotation_template(
        predecessor,
        successor,
        generation=2,
    )
    peer_1_request = next(
        request for request in template.requests if request.peer_id == "peer-1"
    )
    minority = (
        CheckpointPeerRotationSignature(
            peer_id="peer-1",
            key_id="peer-1-key-1",
            signature_base64=base64.b64encode(
                predecessor_keys["peer-1"].sign(
                    peer_1_request.statement.signing_bytes()
                )
            ).decode(),
        ),
    )

    with pytest.raises(ValueError, match="strict-majority quorum is incomplete"):
        build_checkpoint_peer_trust_rotation_certificate(
            template,
            predecessor,
            successor,
            minority,
        )

    peer_2_request = next(
        request for request in template.requests if request.peer_id == "peer-2"
    )
    unknown_rotation_key = minority + (
        CheckpointPeerRotationSignature(
            peer_id="peer-2",
            key_id="peer-2-key-2",
            signature_base64=base64.b64encode(
                successor_keys["peer-2-next"].sign(
                    peer_2_request.statement.signing_bytes()
                )
            ).decode(),
        ),
    )
    with pytest.raises(ValueError, match="active predecessor key"):
        build_checkpoint_peer_trust_rotation_certificate(
            template,
            predecessor,
            successor,
            unknown_rotation_key,
        )

    invalid_signature = minority + (
        CheckpointPeerRotationSignature(
            peer_id="peer-2",
            key_id="peer-2-key-1",
            signature_base64=base64.b64encode(bytes(64)).decode(),
        ),
    )
    with pytest.raises(ValueError, match="signature is invalid: peer-2"):
        build_checkpoint_peer_trust_rotation_certificate(
            template,
            predecessor,
            successor,
            invalid_signature,
        )


def test_peer_trust_ledger_rejects_gaps_reuse_and_tampering() -> None:
    predecessor_keys, _, predecessor, successor = _trust_context()
    _, rotation = _rotation_certificate(
        predecessor,
        successor,
        predecessor_keys,
    )
    genesis = CheckpointPeerTrustGeneration(
        schema_version=SCHEMA_VERSION,
        generation=1,
        trust=predecessor,
    )
    successor_generation = CheckpointPeerTrustGeneration(
        schema_version=SCHEMA_VERSION,
        generation=2,
        trust=successor,
        rotation=rotation,
    )
    ledger = build_checkpoint_peer_trust_ledger((genesis, successor_generation))

    with pytest.raises(ValueError, match="contiguous"):
        build_checkpoint_peer_trust_ledger(
            (
                genesis,
                successor_generation.model_copy(update={"generation": 3}),
            )
        )
    with pytest.raises(ValueError, match="must change peer trust"):
        build_checkpoint_peer_trust_rotation_template(
            predecessor,
            predecessor,
            generation=2,
        )
    payload = ledger.model_dump(mode="json")
    payload["ledger_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        CheckpointPeerTrustLedger.model_validate(payload)


def test_peer_trust_rotation_and_ledger_cli_are_private_key_free(
    tmp_path: Path,
) -> None:
    predecessor_keys, _, predecessor, successor = _trust_context()
    predecessor_path = tmp_path / "predecessor.json"
    successor_path = tmp_path / "successor.json"
    predecessor_path.write_text(predecessor.to_json(), encoding="utf-8")
    successor_path.write_text(successor.to_json(), encoding="utf-8")
    template_path = tmp_path / "rotation-template.json"

    template_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-peer-trust-rotation-template",
            "--predecessor-peer-trust",
            str(predecessor_path),
            "--successor-peer-trust",
            str(successor_path),
            "--generation",
            "2",
            "--output",
            str(template_path),
            "--json",
        ],
    )
    assert template_result.exit_code == 0, template_result.output
    assert "private" not in template_path.read_text(encoding="utf-8").lower()
    _, rotation = _rotation_certificate(
        predecessor,
        successor,
        predecessor_keys,
    )
    generations_path = tmp_path / "trust-generations.json"
    generations_path.write_text(
        json.dumps(
            {
                "generations": [
                    CheckpointPeerTrustGeneration(
                        schema_version=SCHEMA_VERSION,
                        generation=1,
                        trust=predecessor,
                    ).model_dump(mode="json"),
                    CheckpointPeerTrustGeneration(
                        schema_version=SCHEMA_VERSION,
                        generation=2,
                        trust=successor,
                        rotation=rotation,
                    ).model_dump(mode="json"),
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "peer-trust-ledger.json"
    ledger_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-peer-trust-ledger",
            "--generations",
            str(generations_path),
            "--output",
            str(ledger_path),
            "--json",
        ],
    )

    assert ledger_result.exit_code == 0, ledger_result.output
    ledger = CheckpointPeerTrustLedger.model_validate_json(
        ledger_path.read_text(encoding="utf-8")
    )
    assert ledger.active_trust == successor
