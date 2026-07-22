"""Append-only checkpoint registry and authenticated peer exchange tests."""

from __future__ import annotations

import asyncio
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
    CheckpointAcknowledgementSigningRequest,
    CheckpointExchangeSigningRequest,
    CheckpointPeerCursorStore,
    CheckpointPeerKeyDeclaration,
    CheckpointPeerTrustDeclaration,
    CheckpointRangeSigningRequest,
    CheckpointRegistryStore,
    SignedCheckpointExchangePacket,
    SignedCheckpointRangeBundle,
    build_checkpoint_acknowledgement_request,
    build_checkpoint_exchange_request,
    build_checkpoint_peer_trust,
    build_checkpoint_range_request,
    build_signed_checkpoint_acknowledgement,
    build_signed_checkpoint_exchange_packet,
    build_signed_checkpoint_range_bundle,
    verify_checkpoint_acknowledgement,
    verify_checkpoint_exchange_packet,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_gossip import (
    CheckpointGossipService,
    fetch_checkpoint_gossip_status,
    fetch_signed_checkpoint_range,
    submit_signed_checkpoint_acknowledgement,
)
from benchmarks.agent_cli_gossip_transport import (
    CheckpointGossipServer,
    send_checkpoint_gossip_request,
)
from benchmarks.agent_cli_peer_trust_ledger import (
    CheckpointPeerRotationSignature,
    CheckpointPeerTrustGeneration,
    build_checkpoint_peer_trust_ledger,
    build_checkpoint_peer_trust_rotation_certificate,
    build_checkpoint_peer_trust_rotation_template,
)
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


def _three_record_registry(tmp_path: Path, context):
    _, ledger, _, witness_trust, _ = context
    store = CheckpointRegistryStore(
        tmp_path / "source-range.jsonl",
        registry_id="production-registry",
    )
    records = tuple(
        store.append(*_checkpoint(context, previous, current), witness_trust, ledger)
        for previous, current in ((1, 2), (2, 4), (4, 6))
    )
    return store, records


def _signed_range(records, peer_keys, peer_trust):
    request = build_checkpoint_range_request(
        records,
        peer_trust,
        source_peer_id="peer-1",
    )
    return build_signed_checkpoint_range_bundle(
        request,
        records,
        key_id="peer-1-key-1",
        signature_base64=base64.b64encode(
            peer_keys["peer-1"].sign(request.statement.signing_bytes())
        ).decode(),
        peer_trust=peer_trust,
    )


def test_signed_range_imports_missing_suffix_and_retries_idempotently(
    tmp_path: Path,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    _, records = _three_record_registry(tmp_path, context)
    peer_keys, peer_trust = _peer_trust()
    bundle = _signed_range(records[1:], peer_keys, peer_trust)
    target = CheckpointRegistryStore(
        tmp_path / "target-range.jsonl",
        registry_id="production-registry",
    )
    target.append(
        records[0].consistency_proof,
        records[0].checkpoint,
        witness_trust,
        ledger,
    )

    imported = target.import_range_bundle(
        bundle,
        peer_trust,
        witness_trust,
        ledger,
    )
    retried = target.import_range_bundle(
        bundle,
        peer_trust,
        witness_trust,
        ledger,
    )

    assert imported.record_count == 3
    assert retried == imported
    assert imported.records == records


def test_range_import_rejects_gap_without_partial_write(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    _, records = _three_record_registry(tmp_path, context)
    peer_keys, peer_trust = _peer_trust()
    gap_bundle = _signed_range(records[2:], peer_keys, peer_trust)
    target = CheckpointRegistryStore(
        tmp_path / "target-gap.jsonl",
        registry_id="production-registry",
    )
    target.append(
        records[0].consistency_proof,
        records[0].checkpoint,
        witness_trust,
        ledger,
    )

    with pytest.raises(ValueError, match="gap"):
        target.import_range_bundle(
            gap_bundle,
            peer_trust,
            witness_trust,
            ledger,
        )

    assert target.replay(witness_trust, ledger).records == (records[0],)


def test_range_import_rejects_conflicting_overlap_without_partial_write(
    tmp_path: Path,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, entries = context
    _, records = _three_record_registry(tmp_path, context)
    target = CheckpointRegistryStore(
        tmp_path / "target-fork.jsonl",
        registry_id="production-registry",
    )
    target.append(
        records[0].consistency_proof,
        records[0].checkpoint,
        witness_trust,
        ledger,
    )
    alternate_entries = (
        entries[0],
        entries[1].model_copy(update={"artifact_sha256": "f" * 64}),
    ) + entries[2:]
    alternate_proof, alternate_checkpoint = _checkpoint(
        context,
        1,
        2,
        entries=alternate_entries,
    )
    alternate_store = CheckpointRegistryStore(
        tmp_path / "alternate-range.jsonl",
        registry_id="production-registry",
    )
    alternate = alternate_store.append(
        alternate_proof,
        alternate_checkpoint,
        witness_trust,
        ledger,
    )
    peer_keys, peer_trust = _peer_trust()
    fork_bundle = _signed_range((alternate,), peer_keys, peer_trust)

    with pytest.raises(ValueError, match="conflicting range overlap"):
        target.import_range_bundle(
            fork_bundle,
            peer_trust,
            witness_trust,
            ledger,
        )

    assert target.replay(witness_trust, ledger).records == (records[0],)


def test_range_bundle_rejects_invalid_signature(tmp_path: Path) -> None:
    context = _context()
    _, records = _three_record_registry(tmp_path, context)
    _, peer_trust = _peer_trust()
    request = build_checkpoint_range_request(
        records,
        peer_trust,
        source_peer_id="peer-1",
    )

    with pytest.raises(ValueError, match="range signature is invalid"):
        build_signed_checkpoint_range_bundle(
            request,
            records,
            key_id="peer-1-key-1",
            signature_base64=base64.b64encode(bytes(64)).decode(),
            peer_trust=peer_trust,
        )


def test_signed_acknowledgement_advances_durable_peer_cursor(
    tmp_path: Path,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    _, records = _three_record_registry(tmp_path, context)
    peer_keys, peer_trust = _peer_trust()
    first_bundle = _signed_range(records[:2], peer_keys, peer_trust)
    target = CheckpointRegistryStore(
        tmp_path / "ack-target.jsonl",
        registry_id="production-registry",
    )
    first_snapshot = target.import_range_bundle(
        first_bundle,
        peer_trust,
        witness_trust,
        ledger,
    )
    invalid_snapshot = first_snapshot.model_copy(update={"record_count": 99})
    with pytest.raises(ValueError, match="record_count"):
        build_checkpoint_acknowledgement_request(
            first_bundle,
            invalid_snapshot,
            peer_trust,
            acknowledging_peer_id="peer-2",
        )
    request = build_checkpoint_acknowledgement_request(
        first_bundle,
        first_snapshot,
        peer_trust,
        acknowledging_peer_id="peer-2",
    )
    with pytest.raises(ValueError, match="acknowledgement signature is invalid"):
        build_signed_checkpoint_acknowledgement(
            request,
            key_id="peer-2-key-1",
            signature_base64=base64.b64encode(bytes(64)).decode(),
            peer_trust=peer_trust,
        )
    acknowledgement = build_signed_checkpoint_acknowledgement(
        request,
        key_id="peer-2-key-1",
        signature_base64=base64.b64encode(
            peer_keys["peer-2"].sign(request.statement.signing_bytes())
        ).decode(),
        peer_trust=peer_trust,
    )
    cursors = CheckpointPeerCursorStore(
        tmp_path / "peer-cursors.jsonl",
        registry_id="production-registry",
    )

    first_cursor = cursors.append(acknowledgement, peer_trust)
    retried = cursors.append(acknowledgement, peer_trust)
    snapshot = cursors.replay(peer_trust)

    assert verify_checkpoint_acknowledgement(
        acknowledgement,
        peer_trust,
    ) == acknowledgement.statement
    assert retried == first_cursor
    assert snapshot.cursor_count == 1
    assert snapshot.positions[0].source_peer_id == "peer-1"
    assert snapshot.positions[0].acknowledging_peer_id == "peer-2"
    assert snapshot.positions[0].acknowledged_record_sequence == 1
    assert stat.S_IMODE(cursors.path.stat().st_mode) == 0o600

    payload = json.loads(cursors.path.read_text(encoding="utf-8"))
    payload["cursor_record_sha256"] = "f" * 64
    cursors.path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cursor record.*fingerprint"):
        cursors.replay(peer_trust)


def test_peer_cursor_rejects_acknowledgement_regression(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, entries = context
    _, records = _three_record_registry(tmp_path, context)
    peer_keys, peer_trust = _peer_trust()
    target = CheckpointRegistryStore(
        tmp_path / "regression-target.jsonl",
        registry_id="production-registry",
    )
    full_bundle = _signed_range(records, peer_keys, peer_trust)
    snapshot = target.import_range_bundle(
        full_bundle,
        peer_trust,
        witness_trust,
        ledger,
    )

    def acknowledgement_for(bundle, applied_snapshot):
        request = build_checkpoint_acknowledgement_request(
            bundle,
            applied_snapshot,
            peer_trust,
            acknowledging_peer_id="peer-2",
        )
        return build_signed_checkpoint_acknowledgement(
            request,
            key_id="peer-2-key-1",
            signature_base64=base64.b64encode(
                peer_keys["peer-2"].sign(request.statement.signing_bytes())
            ).decode(),
            peer_trust=peer_trust,
        )

    cursor_store = CheckpointPeerCursorStore(
        tmp_path / "regression-cursors.jsonl",
        registry_id="production-registry",
    )
    cursor_store.append(acknowledgement_for(full_bundle, snapshot), peer_trust)
    older_bundle = _signed_range(records[:2], peer_keys, peer_trust)
    older_target = CheckpointRegistryStore(
        tmp_path / "older-regression-target.jsonl",
        registry_id="production-registry",
    )
    older_snapshot = older_target.import_range_bundle(
        older_bundle,
        peer_trust,
        witness_trust,
        ledger,
    )

    with pytest.raises(ValueError, match="cursor regression"):
        cursor_store.append(
            acknowledgement_for(older_bundle, older_snapshot),
            peer_trust,
        )

    alternate_entries = (
        entries[0],
        entries[1].model_copy(update={"artifact_sha256": "e" * 64}),
    ) + entries[2:]
    alternate_store = CheckpointRegistryStore(
        tmp_path / "conflicting-cursor-source.jsonl",
        registry_id="production-registry",
    )
    alternate_records = tuple(
        alternate_store.append(
            *_checkpoint(
                context,
                previous,
                current,
                entries=alternate_entries,
            ),
            witness_trust,
            ledger,
        )
        for previous, current in ((1, 2), (2, 4), (4, 6))
    )
    alternate_bundle = _signed_range(alternate_records, peer_keys, peer_trust)
    alternate_target = CheckpointRegistryStore(
        tmp_path / "conflicting-cursor-target.jsonl",
        registry_id="production-registry",
    )
    alternate_snapshot = alternate_target.import_range_bundle(
        alternate_bundle,
        peer_trust,
        witness_trust,
        ledger,
    )

    with pytest.raises(ValueError, match="conflicting peer cursor"):
        cursor_store.append(
            acknowledgement_for(alternate_bundle, alternate_snapshot),
            peer_trust,
        )


def test_checkpoint_range_and_cursor_cli_workflow(tmp_path: Path) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    source, records = _three_record_registry(tmp_path, context)
    peer_keys, peer_trust = _peer_trust()
    witness_trust_path = tmp_path / "range-witness-trust.json"
    ledger_path = tmp_path / "range-ledger.json"
    peer_trust_path = tmp_path / "range-peer-trust.json"
    witness_trust_path.write_text(witness_trust.to_json(), encoding="utf-8")
    ledger_path.write_text(ledger.to_json(), encoding="utf-8")
    peer_trust_path.write_text(peer_trust.to_json(), encoding="utf-8")
    range_request_path = tmp_path / "range-request.json"

    exported = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-range-export-template",
            "--registry",
            str(source.path),
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
            "--start-sequence",
            "0",
            "--max-records",
            "3",
            "--output",
            str(range_request_path),
            "--json",
        ],
    )
    assert exported.exit_code == 0, exported.output
    range_request = CheckpointRangeSigningRequest.model_validate_json(
        range_request_path.read_text(encoding="utf-8")
    )
    bundle = build_signed_checkpoint_range_bundle(
        range_request,
        records,
        key_id="peer-1-key-1",
        signature_base64=base64.b64encode(
            peer_keys["peer-1"].sign(range_request.statement.signing_bytes())
        ).decode(),
        peer_trust=peer_trust,
    )
    bundle_path = tmp_path / "signed-range.json"
    bundle_path.write_text(bundle.to_json(), encoding="utf-8")
    target_path = tmp_path / "cli-range-target.jsonl"

    imported = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-range-import",
            "--registry",
            str(target_path),
            "--registry-id",
            "production-registry",
            "--range-bundle",
            str(bundle_path),
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
    assert json.loads(imported.output)["record_count"] == 3

    acknowledgement_request_path = tmp_path / "ack-request.json"
    acknowledgement_template = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-acknowledgement-template",
            "--registry",
            str(target_path),
            "--registry-id",
            "production-registry",
            "--range-bundle",
            str(bundle_path),
            "--peer-trust",
            str(peer_trust_path),
            "--witness-trust",
            str(witness_trust_path),
            "--authority-root-ledger",
            str(ledger_path),
            "--acknowledging-peer-id",
            "peer-2",
            "--output",
            str(acknowledgement_request_path),
            "--json",
        ],
    )
    assert acknowledgement_template.exit_code == 0, acknowledgement_template.output
    acknowledgement_request = (
        CheckpointAcknowledgementSigningRequest.model_validate_json(
            acknowledgement_request_path.read_text(encoding="utf-8")
        )
    )
    acknowledgement = build_signed_checkpoint_acknowledgement(
        acknowledgement_request,
        key_id="peer-2-key-1",
        signature_base64=base64.b64encode(
            peer_keys["peer-2"].sign(
                acknowledgement_request.statement.signing_bytes()
            )
        ).decode(),
        peer_trust=peer_trust,
    )
    acknowledgement_path = tmp_path / "signed-acknowledgement.json"
    acknowledgement_path.write_text(acknowledgement.to_json(), encoding="utf-8")
    cursor_path = tmp_path / "cli-peer-cursors.jsonl"

    stored = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-cursor-store",
            "--cursor-ledger",
            str(cursor_path),
            "--registry-id",
            "production-registry",
            "--acknowledgement",
            str(acknowledgement_path),
            "--peer-trust",
            str(peer_trust_path),
            "--json",
        ],
    )
    assert stored.exit_code == 0, stored.output
    cursor_status = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-cursor-status",
            "--cursor-ledger",
            str(cursor_path),
            "--registry-id",
            "production-registry",
            "--peer-trust",
            str(peer_trust_path),
            "--json",
        ],
    )
    assert cursor_status.exit_code == 0, cursor_status.output
    status_payload = json.loads(cursor_status.output)
    assert status_payload["cursor_count"] == 1
    assert status_payload["positions"][0]["acknowledged_record_sequence"] == 2


def test_peer_trust_ledger_replays_and_advances_historical_cursors(
    tmp_path: Path,
) -> None:
    context = _context()
    _, authority_ledger, _, witness_trust, _ = context
    _, records = _three_record_registry(tmp_path, context)
    predecessor_keys, predecessor_trust = _peer_trust()
    _, successor_trust = _peer_trust(revoke_peer_2=True)
    template = build_checkpoint_peer_trust_rotation_template(
        predecessor_trust,
        successor_trust,
        generation=2,
    )
    requests = {request.peer_id: request for request in template.requests}
    rotation = build_checkpoint_peer_trust_rotation_certificate(
        template,
        predecessor_trust,
        successor_trust,
        tuple(
            CheckpointPeerRotationSignature(
                peer_id=peer_id,
                key_id=f"{peer_id}-key-1",
                signature_base64=base64.b64encode(
                    predecessor_keys[peer_id].sign(
                        requests[peer_id].statement.signing_bytes()
                    )
                ).decode(),
            )
            for peer_id in ("peer-1", "peer-2")
        ),
    )
    trust_ledger = build_checkpoint_peer_trust_ledger(
        (
            CheckpointPeerTrustGeneration(
                schema_version=SCHEMA_VERSION,
                generation=1,
                trust=predecessor_trust,
            ),
            CheckpointPeerTrustGeneration(
                schema_version=SCHEMA_VERSION,
                generation=2,
                trust=successor_trust,
                rotation=rotation,
            ),
        )
    )
    target = CheckpointRegistryStore(
        tmp_path / "rotation-target.jsonl",
        registry_id="production-registry",
    )

    def signed_acknowledgement(bundle, snapshot, trust, key_id, private_key):
        request = build_checkpoint_acknowledgement_request(
            bundle,
            snapshot,
            trust,
            acknowledging_peer_id="peer-2",
        )
        return build_signed_checkpoint_acknowledgement(
            request,
            key_id=key_id,
            signature_base64=base64.b64encode(
                private_key.sign(request.statement.signing_bytes())
            ).decode(),
            peer_trust=trust,
        )

    first_bundle = _signed_range(
        records[:2],
        predecessor_keys,
        predecessor_trust,
    )
    first_snapshot = target.import_range_bundle(
        first_bundle,
        predecessor_trust,
        witness_trust,
        authority_ledger,
    )
    first_acknowledgement = signed_acknowledgement(
        first_bundle,
        first_snapshot,
        predecessor_trust,
        "peer-2-key-1",
        predecessor_keys["peer-2"],
    )
    cursors = CheckpointPeerCursorStore(
        tmp_path / "rotation-cursors.jsonl",
        registry_id="production-registry",
    )
    cursors.append(first_acknowledgement, predecessor_trust)
    successor_keys = dict(predecessor_keys)
    successor_keys["peer-2"] = _private(59)
    second_bundle = _signed_range(
        records[2:],
        successor_keys,
        successor_trust,
    )
    second_snapshot = target.import_range_bundle(
        second_bundle,
        successor_trust,
        witness_trust,
        authority_ledger,
    )
    second_acknowledgement = signed_acknowledgement(
        second_bundle,
        second_snapshot,
        successor_trust,
        "peer-2-key-2",
        successor_keys["peer-2"],
    )

    with pytest.raises(ValueError, match="does not match peer trust"):
        cursors.replay(successor_trust)
    cursors.append(second_acknowledgement, trust_ledger)
    cursor_snapshot = cursors.replay(trust_ledger)

    assert cursor_snapshot.cursor_count == 2
    assert cursor_snapshot.positions[0].acknowledged_record_sequence == 2
    trust_ledger_path = tmp_path / "rotation-trust-ledger.json"
    trust_ledger_path.write_text(trust_ledger.to_json(), encoding="utf-8")
    cursor_status = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-checkpoint-cursor-status",
            "--cursor-ledger",
            str(cursors.path),
            "--registry-id",
            "production-registry",
            "--peer-trust-ledger",
            str(trust_ledger_path),
            "--json",
        ],
    )
    assert cursor_status.exit_code == 0, cursor_status.output
    assert json.loads(cursor_status.output)["cursor_count"] == 2


@pytest.mark.asyncio
async def test_authenticated_gossip_fetches_range_and_submits_acknowledgement(
    tmp_path: Path,
) -> None:
    context = _context()
    _, ledger, _, witness_trust, _ = context
    _, records = _three_record_registry(tmp_path, context)
    peer_keys, peer_trust = _peer_trust()
    bundle = _signed_range(records, peer_keys, peer_trust)
    cursor_store = CheckpointPeerCursorStore(
        tmp_path / "gossip-cursors.jsonl",
        registry_id="production-registry",
    )
    service = CheckpointGossipService(
        registry_id="production-registry",
        source_peer_id="peer-1",
        range_bundles=(bundle,),
        cursor_store=cursor_store,
        peer_trust=peer_trust,
    )
    descriptor_path = tmp_path / "gossip" / "peer-1.json"

    async with CheckpointGossipServer(
        descriptor_path=descriptor_path,
        registry_id="production-registry",
        source_peer_id="peer-1",
        handler=service,
        max_requests=8,
    ):
        fetched = await fetch_signed_checkpoint_range(
            descriptor_path=descriptor_path,
            start_sequence=0,
            max_records=3,
            peer_trust=peer_trust,
        )
        assert fetched == bundle

        with pytest.raises(ValueError, match="does not match peer trust"):
            _, wrong_trust = _peer_trust(revoke_peer_2=True)
            await fetch_signed_checkpoint_range(
                descriptor_path=descriptor_path,
                start_sequence=0,
                max_records=3,
                peer_trust=wrong_trust,
            )

        target = CheckpointRegistryStore(
            tmp_path / "gossip-target.jsonl",
            registry_id="production-registry",
        )
        snapshot = target.import_range_bundle(
            fetched,
            peer_trust,
            witness_trust,
            ledger,
        )
        request = build_checkpoint_acknowledgement_request(
            fetched,
            snapshot,
            peer_trust,
            acknowledging_peer_id="peer-2",
        )
        acknowledgement = build_signed_checkpoint_acknowledgement(
            request,
            key_id="peer-2-key-1",
            signature_base64=base64.b64encode(
                peer_keys["peer-2"].sign(request.statement.signing_bytes())
            ).decode(),
            peer_trust=peer_trust,
        )
        cursor_record = await submit_signed_checkpoint_acknowledgement(
            descriptor_path=descriptor_path,
            acknowledgement=acknowledgement,
        )

        assert cursor_record.acknowledgement == acknowledgement
        assert cursor_store.replay(peer_trust).cursor_count == 1

        fetched_path = tmp_path / "gossip-range.json"
        cli_fetch = await asyncio.to_thread(
            runner.invoke,
            app,
            [
                "benchmark",
                "agent-cli-checkpoint-gossip-fetch",
                "--descriptor",
                str(descriptor_path),
                "--peer-trust",
                str(tmp_path / "peer-trust.json"),
                "--start-sequence",
                "0",
                "--max-records",
                "3",
                "--output",
                str(fetched_path),
                "--json",
            ],
        )
        assert cli_fetch.exit_code == 2

        peer_trust_path = tmp_path / "peer-trust.json"
        peer_trust_path.write_text(peer_trust.to_json(), encoding="utf-8")
        cli_fetch = await asyncio.to_thread(
            runner.invoke,
            app,
            [
                "benchmark",
                "agent-cli-checkpoint-gossip-fetch",
                "--descriptor",
                str(descriptor_path),
                "--peer-trust",
                str(peer_trust_path),
                "--start-sequence",
                "0",
                "--max-records",
                "3",
                "--output",
                str(fetched_path),
                "--json",
            ],
        )
        assert cli_fetch.exit_code == 0, cli_fetch.output
        assert SignedCheckpointRangeBundle.model_validate_json(
            fetched_path.read_text(encoding="utf-8")
        ) == bundle
        cli_status = await asyncio.to_thread(
            runner.invoke,
            app,
            [
                "benchmark",
                "agent-cli-checkpoint-gossip-status",
                "--descriptor",
                str(descriptor_path),
                "--json",
            ],
        )
        assert cli_status.exit_code == 0, cli_status.output
        assert json.loads(cli_status.output)["available_ranges"][0][
            "range_bundle_sha256"
        ] == bundle.range_bundle_sha256
        acknowledgement_path = tmp_path / "gossip-acknowledgement.json"
        acknowledgement_path.write_text(acknowledgement.to_json(), encoding="utf-8")
        cli_ack = await asyncio.to_thread(
            runner.invoke,
            app,
            [
                "benchmark",
                "agent-cli-checkpoint-gossip-ack",
                "--descriptor",
                str(descriptor_path),
                "--acknowledgement",
                str(acknowledgement_path),
                "--json",
            ],
        )
        assert cli_ack.exit_code == 0, cli_ack.output
        assert json.loads(cli_ack.output)["acknowledgement"] == (
            acknowledgement.model_dump(mode="json")
        )
        assert cursor_store.replay(peer_trust).cursor_count == 1
        invalid_acknowledgement = acknowledgement.model_copy(
            update={"signature_base64": base64.b64encode(bytes(64)).decode()}
        )
        with pytest.raises(ValueError, match="fingerprint"):
            await submit_signed_checkpoint_acknowledgement(
                descriptor_path=descriptor_path,
                acknowledgement=invalid_acknowledgement,
            )
        with pytest.raises(RuntimeError, match="invalid_acknowledgement"):
            await send_checkpoint_gossip_request(
                descriptor_path=descriptor_path,
                operation="submit_acknowledgement",
                payload={
                    "acknowledgement": invalid_acknowledgement.model_dump(mode="json")
                },
            )
        assert cursor_store.replay(peer_trust).cursor_count == 1

    bundles_path = tmp_path / "gossip-bundles.json"
    bundles_path.write_text(
        json.dumps({"bundles": [bundle.model_dump(mode="json")]}, sort_keys=True),
        encoding="utf-8",
    )
    serve_descriptor = tmp_path / "served-gossip.json"
    serve_task = asyncio.create_task(
        asyncio.to_thread(
            runner.invoke,
            app,
            [
                "benchmark",
                "agent-cli-checkpoint-gossip-serve",
                "--descriptor",
                str(serve_descriptor),
                "--range-bundles",
                str(bundles_path),
                "--cursor-ledger",
                str(tmp_path / "served-cursors.jsonl"),
                "--registry-id",
                "production-registry",
                "--source-peer-id",
                "peer-1",
                "--peer-trust",
                str(peer_trust_path),
                "--max-requests",
                "1",
                "--lifetime-seconds",
                "5",
            ],
        )
    )
    for _ in range(200):
        if serve_descriptor.exists() or serve_task.done():
            break
        await asyncio.sleep(0.01)
    assert serve_descriptor.exists(), (await serve_task).output
    served_status = await fetch_checkpoint_gossip_status(
        descriptor_path=serve_descriptor
    )
    serve_result = await asyncio.wait_for(serve_task, timeout=2)

    assert served_status["source_peer_id"] == "peer-1"
    assert serve_result.exit_code == 0, serve_result.output
    assert serve_descriptor.exists() is False
