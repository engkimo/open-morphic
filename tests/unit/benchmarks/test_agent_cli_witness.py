"""Compact Merkle consistency and witnessed checkpoint tests."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from benchmarks.agent_cli_authority import (
    BenchmarkAuthorityDeclaration,
    build_benchmark_authority,
)
from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_transparency import (
    AuthorityRootGeneration,
    SignedAuthorityRootLedger,
    SignedTransparencyTreeHead,
    TransparencyConsistencyProof,
    TransparencyLogEntry,
    build_authority_root_ledger_request,
    build_transparency_consistency_proof,
    build_transparency_log,
    build_transparency_tree_head_request,
    verify_transparency_consistency_proof,
)
from benchmarks.agent_cli_witness import (
    SignedWitnessCheckpoint,
    TransparencyWitnessKeyDeclaration,
    TransparencyWitnessSignature,
    TransparencyWitnessTrustDeclaration,
    WitnessCheckpointTemplate,
    build_transparency_witness_trust,
    build_witness_checkpoint_bundle,
    build_witness_checkpoint_template,
    detect_witness_checkpoint_conflict,
    verify_witness_checkpoint_bundle,
)
from interface.cli.main import app

runner = CliRunner()


def _private(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _authority_ledger():
    private_key = _private(20)
    authority = build_benchmark_authority(
        BenchmarkAuthorityDeclaration(
            schema_version=SCHEMA_VERSION,
            authority_id="witness-test-root",
            public_key_base64=base64.b64encode(
                private_key.public_key().public_bytes_raw()
            ).decode(),
        )
    )
    request = build_authority_root_ledger_request(
        (
            AuthorityRootGeneration(
                schema_version=SCHEMA_VERSION,
                generation=1,
                authority=authority,
            ),
        )
    )
    ledger = SignedAuthorityRootLedger(
        statement=request.statement,
        signature_base64=base64.b64encode(
            private_key.sign(request.statement.signing_bytes())
        ).decode(),
    )
    return private_key, ledger


def _entries(count: int, *, offset: int = 0) -> tuple[TransparencyLogEntry, ...]:
    return tuple(
        TransparencyLogEntry(
            sequence=index,
            kind="campaign_envelope",
            artifact_sha256=f"{index + offset + 1:064x}",
        )
        for index in range(count)
    )


def _signed_head(log, private_key, ledger):
    request = build_transparency_tree_head_request(log, ledger)
    return SignedTransparencyTreeHead(
        statement=request.statement,
        signature_base64=base64.b64encode(
            private_key.sign(request.statement.signing_bytes())
        ).decode(),
    )


def _proof(previous_size: int, current_size: int):
    authority_private, ledger = _authority_ledger()
    current_log = build_transparency_log("witness-log", _entries(current_size))
    previous_log = build_transparency_log(
        "witness-log",
        current_log.entries[:previous_size],
    )
    previous_head = _signed_head(previous_log, authority_private, ledger)
    current_head = _signed_head(current_log, authority_private, ledger)
    proof = build_transparency_consistency_proof(
        current_log,
        previous_tree_head=previous_head,
        current_tree_head=current_head,
        authority_root_ledger=ledger,
    )
    return authority_private, ledger, current_log, proof


def _witness_trust():
    keys = {f"witness-{index}": _private(30 + index) for index in range(1, 4)}
    declaration = TransparencyWitnessTrustDeclaration(
        schema_version=SCHEMA_VERSION,
        log_id="witness-log",
        minimum_distinct_witnesses=2,
        keys=tuple(
            TransparencyWitnessKeyDeclaration(
                witness_id=witness_id,
                key_id=f"{witness_id}-key-1",
                public_key_base64=base64.b64encode(
                    private_key.public_key().public_bytes_raw()
                ).decode(),
            )
            for witness_id, private_key in reversed(keys.items())
        ),
    )
    return keys, build_transparency_witness_trust(declaration)


def _signed_checkpoint(proof, ledger):
    keys, trust = _witness_trust()
    template = build_witness_checkpoint_template(trust, proof, ledger)
    signatures = tuple(
        TransparencyWitnessSignature(
            witness_id=request.witness_id,
            key_id=f"{request.witness_id}-key-1",
            signature_base64=base64.b64encode(
                keys[request.witness_id].sign(request.statement.signing_bytes())
            ).decode(),
        )
        for request in template.requests[:2]
    )
    bundle = build_witness_checkpoint_bundle(
        trust,
        proof,
        ledger,
        signatures,
    )
    return keys, trust, template, bundle


def test_rfc6962_compact_consistency_proofs_verify_for_non_power_of_two_trees() -> None:
    authority_private, ledger = _authority_ledger()
    for current_size in range(2, 13):
        current_log = build_transparency_log("witness-log", _entries(current_size))
        current_head = _signed_head(current_log, authority_private, ledger)
        for previous_size in range(1, current_size):
            previous_log = build_transparency_log(
                "witness-log",
                current_log.entries[:previous_size],
            )
            previous_head = _signed_head(previous_log, authority_private, ledger)
            proof = build_transparency_consistency_proof(
                current_log,
                previous_tree_head=previous_head,
                current_tree_head=current_head,
                authority_root_ledger=ledger,
            )

            verify_transparency_consistency_proof(proof, ledger)
            assert len(proof.audit_path_sha256) <= math.ceil(
                math.log2(current_size)
            ) + 1


def test_consistency_path_matches_rfc6962_seven_leaf_example_shape() -> None:
    _, _, current_log, proof = _proof(3, 7)

    def leaf(index: int) -> bytes:
        return hashlib.sha256(
            b"\x00" + current_log.entries[index].leaf_bytes()
        ).digest()

    def node(left: bytes, right: bytes) -> bytes:
        return hashlib.sha256(b"\x01" + left + right).digest()

    expected = (
        leaf(2),
        leaf(3),
        node(leaf(0), leaf(1)),
        node(node(leaf(4), leaf(5)), leaf(6)),
    )

    assert proof.audit_path_sha256 == tuple(item.hex() for item in expected)


def test_consistency_proof_rejects_tampered_path_and_split_root() -> None:
    _, ledger, _, proof = _proof(3, 7)
    tampered = proof.model_copy(
        update={"audit_path_sha256": ("00" * 32,) + proof.audit_path_sha256[1:]}
    )
    tampered = tampered.model_copy(
        update={
            "consistency_proof_sha256": _sha256(
                tampered.model_dump(
                    mode="json",
                    exclude={"consistency_proof_sha256"},
                )
            )
        }
    )

    with pytest.raises(ValueError, match="consistency proof roots do not match"):
        verify_transparency_consistency_proof(tampered, ledger)

    split_head = proof.current_tree_head.model_copy(
        update={
            "statement": proof.current_tree_head.statement.model_copy(
                update={"root_sha256": "ff" * 32}
            )
        }
    )
    split = proof.model_copy(update={"current_tree_head": split_head})
    with pytest.raises(ValueError, match="tree head fingerprint|signature"):
        verify_transparency_consistency_proof(split, ledger)


def test_witness_trust_requires_intersecting_quorum() -> None:
    keys, trust = _witness_trust()

    assert trust.minimum_distinct_witnesses == 2
    assert len(keys) == 3
    payload = trust.model_dump(mode="json", exclude={"witness_trust_sha256"})
    payload["minimum_distinct_witnesses"] = 1
    payload["keys"] = [
        {
            "witness_id": key.witness_id,
            "key_id": key.key_id,
            "public_key_base64": key.public_key_base64,
            "status": key.status,
        }
        for key in trust.keys
    ]
    with pytest.raises(ValueError, match="strict majority"):
        build_transparency_witness_trust(
            TransparencyWitnessTrustDeclaration.model_validate(payload)
        )


def test_witness_checkpoint_requires_distinct_valid_quorum_signatures() -> None:
    _, ledger, _, proof = _proof(3, 7)
    _, trust, template, bundle = _signed_checkpoint(proof, ledger)

    verify_witness_checkpoint_bundle(trust, proof, ledger, bundle)

    assert len(template.requests) == 3
    assert len(bundle.signatures) == 2
    with pytest.raises(ValueError, match="witness quorum"):
        build_witness_checkpoint_bundle(
            trust,
            proof,
            ledger,
            bundle.signatures[:1],
        )
    tampered_signature = bundle.signatures[0].model_copy(
        update={"signature_base64": base64.b64encode(bytes(64)).decode()}
    )
    tampered = bundle.model_copy(
        update={"signatures": (tampered_signature,) + bundle.signatures[1:]}
    )
    tampered = tampered.model_copy(
        update={
            "witness_checkpoint_sha256": _sha256(
                tampered.model_dump(
                    mode="json",
                    exclude={"witness_checkpoint_sha256"},
                )
            )
        }
    )
    with pytest.raises(ValueError, match="witness signature is invalid"):
        verify_witness_checkpoint_bundle(trust, proof, ledger, tampered)


def test_witness_checkpoints_detect_same_size_split_view() -> None:
    authority_private, ledger = _authority_ledger()
    common = _entries(3)
    first_log = build_transparency_log("witness-log", common + _entries(4, offset=10))
    second_log = build_transparency_log("witness-log", common + _entries(4, offset=20))
    previous_log = build_transparency_log("witness-log", common)
    previous_head = _signed_head(previous_log, authority_private, ledger)

    bundles: list[SignedWitnessCheckpoint] = []
    for current_log in (first_log, second_log):
        proof = build_transparency_consistency_proof(
            current_log,
            previous_tree_head=previous_head,
            current_tree_head=_signed_head(current_log, authority_private, ledger),
            authority_root_ledger=ledger,
        )
        bundles.append(_signed_checkpoint(proof, ledger)[3])

    with pytest.raises(ValueError, match="split-view checkpoint"):
        detect_witness_checkpoint_conflict(bundles[0], bundles[1])


def test_consistency_and_witness_cli_paths_are_offline_and_private_key_free(
    tmp_path: Path,
) -> None:
    _, ledger, current_log, expected_proof = _proof(3, 7)
    inputs = {
        "current-log": current_log.to_json(),
        "previous-tree-head": expected_proof.previous_tree_head.model_dump_json(),
        "current-tree-head": expected_proof.current_tree_head.model_dump_json(),
        "authority-root-ledger": ledger.to_json(),
    }
    paths: dict[str, Path] = {}
    for name, payload in inputs.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(payload, encoding="utf-8")
    before = {path: path.read_bytes() for path in paths.values()}
    proof_path = tmp_path / "consistency-proof.json"
    args = ["benchmark", "agent-cli-transparency-consistency-proof"]
    for name, path in paths.items():
        args.extend([f"--{name}", str(path)])
    args.extend(["--output", str(proof_path), "--json"])

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    proof = TransparencyConsistencyProof.model_validate_json(
        proof_path.read_text(encoding="utf-8")
    )
    assert proof == expected_proof
    assert before == {path: path.read_bytes() for path in paths.values()}

    _, trust = _witness_trust()
    declaration_payload = {
        "schema_version": trust.schema_version,
        "log_id": trust.log_id,
        "minimum_distinct_witnesses": trust.minimum_distinct_witnesses,
        "keys": [
            {
                "witness_id": key.witness_id,
                "key_id": key.key_id,
                "algorithm": key.algorithm,
                "public_key_base64": key.public_key_base64,
                "status": key.status,
            }
            for key in trust.keys
        ],
    }
    declaration_path = tmp_path / "witness-declaration.json"
    declaration_path.write_text(
        json.dumps(declaration_payload, sort_keys=True),
        encoding="utf-8",
    )
    trust_path = tmp_path / "witness-trust.json"
    trust_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-witness-trust",
            "--declaration",
            str(declaration_path),
            "--output",
            str(trust_path),
            "--json",
        ],
    )
    assert trust_result.exit_code == 0
    assert json.loads(trust_result.output) == json.loads(trust.to_json())

    template_path = tmp_path / "witness-template.json"
    template_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-witness-checkpoint-template",
            "--witness-trust",
            str(trust_path),
            "--consistency-proof",
            str(proof_path),
            "--authority-root-ledger",
            str(paths["authority-root-ledger"]),
            "--output",
            str(template_path),
            "--json",
        ],
    )

    assert template_result.exit_code == 0
    template = WitnessCheckpointTemplate.model_validate_json(
        template_path.read_text(encoding="utf-8")
    )
    assert len(template.requests) == 3
    assert "private" not in template.to_json().lower()


def test_committed_witness_trust_template_has_intersecting_quorum() -> None:
    root = Path(__file__).parents[3]
    declaration = TransparencyWitnessTrustDeclaration.model_validate_json(
        (
            root / "benchmarks/templates/agent_cli_witness_trust.example.json"
        ).read_text(encoding="utf-8")
    )

    trust = build_transparency_witness_trust(declaration)

    assert trust.log_id == "example-org-agent-cli"
    assert trust.minimum_distinct_witnesses == 2
    assert len({key.witness_id for key in trust.keys}) == 3
