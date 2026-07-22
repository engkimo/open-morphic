"""Append-only checkpoint registry and authenticated peer exchange tests."""

from __future__ import annotations

import base64
import hashlib
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from benchmarks.agent_cli_authority import (
    BenchmarkAuthorityDeclaration,
    build_benchmark_authority,
)
from benchmarks.agent_cli_checkpoint_registry import (
    CheckpointExchangeSigningRequest,
    CheckpointPeerKeyDeclaration,
    CheckpointPeerTrustDeclaration,
    CheckpointRegistryStore,
    SignedCheckpointExchangePacket,
    build_checkpoint_exchange_request,
    build_checkpoint_peer_trust,
    build_signed_checkpoint_exchange_packet,
    verify_checkpoint_exchange_packet,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_transparency import (
    AuthorityRootGeneration,
    SignedAuthorityRootLedger,
    SignedTransparencyTreeHead,
    TransparencyLogEntry,
    build_authority_root_ledger_request,
    build_transparency_consistency_proof,
    build_transparency_log,
    build_transparency_tree_head_request,
)
from benchmarks.agent_cli_witness import (
    TransparencyWitnessKeyDeclaration,
    TransparencyWitnessSignature,
    TransparencyWitnessTrustDeclaration,
    build_transparency_witness_trust,
    build_witness_checkpoint_bundle,
    build_witness_checkpoint_template,
)
from interface.cli.main import app

runner = CliRunner()


def _private(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _context():
    authority_private = _private(40)
    authority = build_benchmark_authority(
        BenchmarkAuthorityDeclaration(
            schema_version=SCHEMA_VERSION,
            authority_id="registry-test-root",
            public_key_base64=base64.b64encode(
                authority_private.public_key().public_bytes_raw()
            ).decode(),
        )
    )
    ledger_request = build_authority_root_ledger_request(
        (
            AuthorityRootGeneration(
                schema_version=SCHEMA_VERSION,
                generation=1,
                authority=authority,
            ),
        )
    )
    ledger = SignedAuthorityRootLedger(
        statement=ledger_request.statement,
        signature_base64=base64.b64encode(
            authority_private.sign(ledger_request.statement.signing_bytes())
        ).decode(),
    )
    witness_keys = {f"witness-{index}": _private(40 + index) for index in range(1, 4)}
    witness_trust = build_transparency_witness_trust(
        TransparencyWitnessTrustDeclaration(
            schema_version=SCHEMA_VERSION,
            log_id="registry-log",
            minimum_distinct_witnesses=2,
            keys=tuple(
                TransparencyWitnessKeyDeclaration(
                    witness_id=witness_id,
                    key_id=f"{witness_id}-key-1",
                    public_key_base64=base64.b64encode(
                        private_key.public_key().public_bytes_raw()
                    ).decode(),
                )
                for witness_id, private_key in witness_keys.items()
            ),
        )
    )
    entries = tuple(
        TransparencyLogEntry(
            sequence=index,
            kind="campaign_envelope",
            artifact_sha256=f"{index + 1:064x}",
        )
        for index in range(6)
    )
    return authority_private, ledger, witness_keys, witness_trust, entries


def _signed_head(log, private_key, ledger):
    request = build_transparency_tree_head_request(log, ledger)
    return SignedTransparencyTreeHead(
        statement=request.statement,
        signature_base64=base64.b64encode(
            private_key.sign(request.statement.signing_bytes())
        ).decode(),
    )


def _checkpoint(context, previous_size: int, current_size: int, *, entries=None):
    authority_private, ledger, witness_keys, witness_trust, default_entries = context
    selected_entries = entries or default_entries
    current_log = build_transparency_log(
        witness_trust.log_id,
        selected_entries[:current_size],
    )
    previous_log = build_transparency_log(
        witness_trust.log_id,
        selected_entries[:previous_size],
    )
    proof = build_transparency_consistency_proof(
        current_log,
        previous_tree_head=_signed_head(previous_log, authority_private, ledger),
        current_tree_head=_signed_head(current_log, authority_private, ledger),
        authority_root_ledger=ledger,
    )
    template = build_witness_checkpoint_template(witness_trust, proof, ledger)
    signatures = tuple(
        TransparencyWitnessSignature(
            witness_id=request.witness_id,
            key_id=f"{request.witness_id}-key-1",
            signature_base64=base64.b64encode(
                witness_keys[request.witness_id].sign(
                    request.statement.signing_bytes()
                )
            ).decode(),
        )
        for request in template.requests[:2]
    )
    checkpoint = build_witness_checkpoint_bundle(
        witness_trust,
        proof,
        ledger,
        signatures,
    )
    return proof, checkpoint


def _peer_trust(*, revoke_peer_2: bool = False):
    peer_keys = {f"peer-{index}": _private(50 + index) for index in range(1, 3)}
    declaration = CheckpointPeerTrustDeclaration(
        schema_version=SCHEMA_VERSION,
        registry_id="production-registry",
        keys=tuple(
            CheckpointPeerKeyDeclaration(
                peer_id=peer_id,
                key_id=f"{peer_id}-key-1",
                public_key_base64=base64.b64encode(
                    private_key.public_key().public_bytes_raw()
                ).decode(),
                status=(
                    "revoked" if revoke_peer_2 and peer_id == "peer-2" else "active"
                ),
            )
            for peer_id, private_key in peer_keys.items()
        )
        + (
            (
                CheckpointPeerKeyDeclaration(
                    peer_id="peer-2",
                    key_id="peer-2-key-2",
                    public_key_base64=base64.b64encode(
                        _private(59).public_key().public_bytes_raw()
                    ).decode(),
                ),
            )
            if revoke_peer_2
            else ()
        ),
    )
    return peer_keys, build_checkpoint_peer_trust(declaration)


def test_registry_appends_replays_and_fsyncs_hash_chain(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    first_proof, first_checkpoint = _checkpoint(context, 1, 3)
    second_proof, second_checkpoint = _checkpoint(context, 3, 5)

    first = store.append(first_proof, first_checkpoint, witness_trust, ledger)
    second = store.append(second_proof, second_checkpoint, witness_trust, ledger)
    snapshot = store.replay(witness_trust, ledger)

    assert snapshot.records == (first, second)
    assert first.sequence == 0
    assert first.previous_record_sha256 is None
    assert second.sequence == 1
    assert second.previous_record_sha256 == first.record_sha256
    assert snapshot.current_tree_size == 5
    assert snapshot.head_record_sha256 == second.record_sha256
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_registry_duplicate_append_is_idempotent(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    proof, checkpoint = _checkpoint(context, 1, 3)

    first = store.append(proof, checkpoint, witness_trust, ledger)
    second = store.append(proof, checkpoint, witness_trust, ledger)

    assert second == first
    assert store.replay(witness_trust, ledger).record_count == 1


def test_registry_serializes_concurrent_duplicate_appends(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    proof, checkpoint = _checkpoint(context, 1, 3)

    with ThreadPoolExecutor(max_workers=8) as executor:
        records = tuple(
            executor.map(
                lambda _: store.append(
                    proof,
                    checkpoint,
                    witness_trust,
                    ledger,
                ),
                range(16),
            )
        )

    assert len({record.record_sha256 for record in records}) == 1
    assert store.replay(witness_trust, ledger).record_count == 1


@pytest.mark.parametrize("mutation", ["sequence", "previous_hash", "record_hash"])
def test_registry_replay_rejects_hash_chain_tampering(
    tmp_path: Path,
    mutation: str,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    first = _checkpoint(context, 1, 3)
    second = _checkpoint(context, 3, 5)
    store.append(*first, witness_trust, ledger)
    store.append(*second, witness_trust, ledger)
    lines = store.path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[1])
    if mutation == "sequence":
        payload["sequence"] = 4
    elif mutation == "previous_hash":
        payload["previous_record_sha256"] = "f" * 64
    else:
        payload["record_sha256"] = "f" * 64
    lines[1] = json.dumps(payload, sort_keys=True)
    store.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sequence|hash chain|fingerprint"):
        store.replay(witness_trust, ledger)


def test_registry_replay_rejects_truncated_tail(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    store.append(*_checkpoint(context, 1, 3), witness_trust, ledger)
    store.path.write_text(
        store.path.read_text(encoding="utf-8").rstrip("\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="truncated final record"):
        store.replay(witness_trust, ledger)


def test_registry_rejects_witnessed_split_view(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, entries = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    proof, checkpoint = _checkpoint(context, 1, 3)
    store.append(proof, checkpoint, witness_trust, ledger)
    alternate_entries = entries[:2] + (
        entries[2].model_copy(update={"artifact_sha256": "f" * 64}),
    ) + entries[3:]
    split_proof, split_checkpoint = _checkpoint(
        context,
        1,
        3,
        entries=alternate_entries,
    )

    with pytest.raises(ValueError, match="split-view checkpoint"):
        store.append(split_proof, split_checkpoint, witness_trust, ledger)


def test_authenticated_peer_packet_imports_and_retries_idempotently(
    tmp_path: Path,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    source = CheckpointRegistryStore(
        tmp_path / "source.jsonl",
        registry_id="production-registry",
    )
    proof, checkpoint = _checkpoint(context, 1, 3)
    record = source.append(proof, checkpoint, witness_trust, ledger)
    peer_keys, peer_trust = _peer_trust()
    request = build_checkpoint_exchange_request(
        record,
        peer_trust,
        source_peer_id="peer-1",
    )
    packet = build_signed_checkpoint_exchange_packet(
        request,
        record,
        key_id="peer-1-key-1",
        signature_base64=base64.b64encode(
            peer_keys["peer-1"].sign(request.statement.signing_bytes())
        ).decode(),
        peer_trust=peer_trust,
    )
    target = CheckpointRegistryStore(
        tmp_path / "target.jsonl",
        registry_id="production-registry",
    )

    imported = target.import_packet(
        packet,
        peer_trust,
        witness_trust,
        ledger,
    )
    retried = target.import_packet(
        packet,
        peer_trust,
        witness_trust,
        ledger,
    )

    assert imported == retried
    assert target.replay(witness_trust, ledger).record_count == 1
    assert imported.checkpoint == record.checkpoint


def test_peer_packet_rejects_invalid_or_revoked_sender(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    source = CheckpointRegistryStore(
        tmp_path / "source.jsonl",
        registry_id="production-registry",
    )
    proof, checkpoint = _checkpoint(context, 1, 3)
    record = source.append(proof, checkpoint, witness_trust, ledger)
    peer_keys, peer_trust = _peer_trust()
    request = build_checkpoint_exchange_request(
        record,
        peer_trust,
        source_peer_id="peer-2",
    )
    packet = SignedCheckpointExchangePacket.model_validate(
        build_signed_checkpoint_exchange_packet(
            request,
            record,
            key_id="peer-2-key-1",
            signature_base64=base64.b64encode(
                peer_keys["peer-2"].sign(request.statement.signing_bytes())
            ).decode(),
            peer_trust=peer_trust,
        ).model_dump(mode="json")
    )
    invalid_payload = packet.model_dump(mode="json", exclude={"packet_sha256"})
    invalid_payload["signature_base64"] = base64.b64encode(bytes(64)).decode()
    invalid = SignedCheckpointExchangePacket(
        **invalid_payload,
        packet_sha256=hashlib.sha256(
            json.dumps(
                invalid_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    )

    with pytest.raises(ValueError, match="signature is invalid"):
        verify_checkpoint_exchange_packet(invalid, peer_trust)
    _, revoked_trust = _peer_trust(revoke_peer_2=True)
    with pytest.raises(ValueError, match="active trusted key"):
        verify_checkpoint_exchange_packet(packet, revoked_trust)


def test_registry_status_is_read_only_for_a_missing_path(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    path = tmp_path / "missing.jsonl"

    snapshot = CheckpointRegistryStore(
        path,
        registry_id="production-registry",
    ).replay(witness_trust, ledger)

    assert snapshot.record_count == 0
    assert not path.exists()


def test_registry_rejects_stale_checkpoint(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "checkpoints.jsonl",
        registry_id="production-registry",
    )
    store.append(*_checkpoint(context, 1, 4), witness_trust, ledger)

    with pytest.raises(ValueError, match="stale checkpoint"):
        store.append(*_checkpoint(context, 2, 3), witness_trust, ledger)


def test_peer_trust_requires_an_active_key_for_every_peer() -> None:
    private_key = _private(61)

    with pytest.raises(ValueError, match="peer has no active key"):
        build_checkpoint_peer_trust(
            CheckpointPeerTrustDeclaration(
                schema_version=SCHEMA_VERSION,
                registry_id="production-registry",
                keys=(
                    CheckpointPeerKeyDeclaration(
                        peer_id="retired-peer",
                        key_id="retired-peer-key-1",
                        public_key_base64=base64.b64encode(
                            private_key.public_key().public_bytes_raw()
                        ).decode(),
                        status="revoked",
                    ),
                ),
            )
        )


def test_checkpoint_registry_cli_store_status_export_and_import(
    tmp_path: Path,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    proof, checkpoint = _checkpoint(context, 1, 3)
    proof_path = tmp_path / "proof.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    witness_trust_path = tmp_path / "witness-trust.json"
    ledger_path = tmp_path / "ledger.json"
    registry_path = tmp_path / "source.jsonl"
    for path, payload in (
        (proof_path, proof.to_json()),
        (checkpoint_path, checkpoint.to_json()),
        (witness_trust_path, witness_trust.to_json()),
        (ledger_path, ledger.to_json()),
    ):
        path.write_text(payload, encoding="utf-8")

    stored = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-registry-store",
            "--registry",
            str(registry_path),
            "--registry-id",
            "production-registry",
            "--consistency-proof",
            str(proof_path),
            "--witness-checkpoint",
            str(checkpoint_path),
            "--witness-trust",
            str(witness_trust_path),
            "--authority-root-ledger",
            str(ledger_path),
            "--json",
        ],
    )
    assert stored.exit_code == 0, stored.output
    record = CheckpointRegistryStore(
        registry_path,
        registry_id="production-registry",
    ).replay(witness_trust, ledger).records[0]

    status = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-registry-status",
            "--registry",
            str(registry_path),
            "--registry-id",
            "production-registry",
            "--witness-trust",
            str(witness_trust_path),
            "--authority-root-ledger",
            str(ledger_path),
            "--json",
        ],
    )
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["record_count"] == 1

    peer_keys, peer_trust = _peer_trust()
    peer_trust_path = tmp_path / "peer-trust.json"
    peer_trust_path.write_text(peer_trust.to_json(), encoding="utf-8")
    request_path = tmp_path / "exchange-request.json"
    exported = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-registry-export-template",
            "--registry",
            str(registry_path),
            "--registry-id",
            "production-registry",
            "--witness-trust",
            str(witness_trust_path),
            "--authority-root-ledger",
            str(ledger_path),
            "--peer-trust",
            str(peer_trust_path),
            "--source-peer-id",
            "peer-1",
            "--output",
            str(request_path),
            "--json",
        ],
    )
    assert exported.exit_code == 0, exported.output
    request = CheckpointExchangeSigningRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    packet = build_signed_checkpoint_exchange_packet(
        request,
        record,
        key_id="peer-1-key-1",
        signature_base64=base64.b64encode(
            peer_keys["peer-1"].sign(request.statement.signing_bytes())
        ).decode(),
        peer_trust=peer_trust,
    )
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(packet.to_json(), encoding="utf-8")
    target_path = tmp_path / "target.jsonl"

    imported = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-registry-import",
            "--registry",
            str(target_path),
            "--registry-id",
            "production-registry",
            "--packet",
            str(packet_path),
            "--peer-trust",
            str(peer_trust_path),
            "--witness-trust",
            str(witness_trust_path),
            "--authority-root-ledger",
            str(ledger_path),
            "--json",
        ],
    )
    assert imported.exit_code == 0, imported.output
    assert json.loads(imported.output)["record_sha256"] == record.record_sha256


def test_committed_peer_trust_template_and_cli(tmp_path: Path) -> None:
    root = Path(__file__).parents[3]
    declaration_path = (
        root
        / "benchmarks/templates/agent_cli_checkpoint_peer_trust.example.json"
    )
    declaration = CheckpointPeerTrustDeclaration.model_validate_json(
        declaration_path.read_text(encoding="utf-8")
    )
    trust = build_checkpoint_peer_trust(declaration)
    output_path = tmp_path / "peer-trust.json"

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-peer-trust",
            "--declaration",
            str(declaration_path),
            "--output",
            str(output_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_path.read_text(encoding="utf-8") == trust.to_json()
    assert {key.peer_id for key in trust.keys} == {
        "registry-peer-a",
        "registry-peer-b",
    }
