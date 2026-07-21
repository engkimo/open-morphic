"""Authority-root rotation and append-only campaign transparency tests."""

from __future__ import annotations

import base64
import hashlib
import json
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
    AuthorityRotationCertificate,
    SignedAuthorityRootLedger,
    SignedTransparencyTreeHead,
    TransparencyInclusionProof,
    TransparencyLog,
    TransparencyLogEntry,
    TransparencyTreeHeadSigningRequest,
    build_authority_root_ledger_request,
    build_authority_rotation_request,
    build_transparency_inclusion_proof,
    build_transparency_log,
    build_transparency_tree_head_request,
    extend_transparency_log,
    verify_authority_root_ledger,
    verify_complete_log_extension,
    verify_transparency_inclusion_proof,
)
from interface.cli.main import app

runner = CliRunner()


def _private(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _authority(seed: int, authority_id: str):
    private_key = _private(seed)
    public_key = private_key.public_key().public_bytes_raw()
    authority = build_benchmark_authority(
        BenchmarkAuthorityDeclaration(
            schema_version=SCHEMA_VERSION,
            authority_id=authority_id,
            public_key_base64=base64.b64encode(public_key).decode(),
        )
    )
    return private_key, authority


def _signed_ledger(*, revoke_genesis: bool = False):
    genesis_private, genesis = _authority(11, "benchmark-root-2026")
    active_private, active = _authority(12, "benchmark-root-2027")
    rotation_request = build_authority_rotation_request(
        generation=2,
        predecessor=genesis,
        successor=active,
    )
    rotation = AuthorityRotationCertificate(
        statement=rotation_request.statement,
        signature_base64=base64.b64encode(
            genesis_private.sign(rotation_request.statement.signing_bytes())
        ).decode(),
    )
    generations = (
        AuthorityRootGeneration(
            schema_version=SCHEMA_VERSION,
            generation=1,
            authority=genesis,
        ),
        AuthorityRootGeneration(
            schema_version=SCHEMA_VERSION,
            generation=2,
            authority=active,
            rotation=rotation,
        ),
    )
    request = build_authority_root_ledger_request(
        generations,
        revoked_authority_sha256=(genesis.authority_sha256,) if revoke_genesis else (),
    )
    ledger = SignedAuthorityRootLedger(
        statement=request.statement,
        signature_base64=base64.b64encode(
            active_private.sign(request.statement.signing_bytes())
        ).decode(),
    )
    return active_private, genesis, active, ledger


def _signed_head(log, private_key, ledger):
    request = build_transparency_tree_head_request(log, ledger)
    return SignedTransparencyTreeHead(
        statement=request.statement,
        signature_base64=base64.b64encode(
            private_key.sign(request.statement.signing_bytes())
        ).decode(),
    )


def test_authority_root_ledger_verifies_rotation_revocation_and_active_signature() -> None:
    _, genesis, active, ledger = _signed_ledger(revoke_genesis=True)

    verified = verify_authority_root_ledger(ledger)

    assert verified == active
    assert ledger.statement.active_generation == 2
    assert ledger.statement.revoked_authority_sha256 == (genesis.authority_sha256,)


def test_authority_root_ledger_rejects_invalid_rotation_signature() -> None:
    _, _, _, ledger = _signed_ledger()
    generation = ledger.statement.generations[1]
    tampered_rotation = generation.rotation.model_copy(
        update={"signature_base64": base64.b64encode(bytes(64)).decode()}
    )
    tampered_generation = generation.model_copy(update={"rotation": tampered_rotation})
    with pytest.raises(ValueError, match="rotation signature is invalid"):
        build_authority_root_ledger_request(
            (ledger.statement.generations[0], tampered_generation)
        )


def test_authority_root_ledger_rejects_revoked_active_root() -> None:
    _, _, active, ledger = _signed_ledger()

    with pytest.raises(ValueError, match="active authority is revoked"):
        build_authority_root_ledger_request(
            ledger.statement.generations,
            revoked_authority_sha256=(active.authority_sha256,),
        )


def test_transparency_log_uses_rfc6962_domain_separated_hashes() -> None:
    first = TransparencyLogEntry(
        sequence=0,
        kind="authority_root_ledger",
        artifact_sha256="11" * 32,
    )
    second = TransparencyLogEntry(
        sequence=1,
        kind="campaign_envelope",
        artifact_sha256="22" * 32,
    )
    log = build_transparency_log("benchmark-production", (first, second))
    left = hashlib.sha256(b"\x00" + first.leaf_bytes()).digest()
    right = hashlib.sha256(b"\x00" + second.leaf_bytes()).digest()

    assert log.root_sha256 == hashlib.sha256(b"\x01" + left + right).hexdigest()
    assert log.tree_size == 2


def test_transparency_inclusion_proof_verifies_and_rejects_tampering() -> None:
    active_private, _, _, ledger = _signed_ledger(revoke_genesis=True)
    entries = tuple(
        TransparencyLogEntry(
            sequence=index,
            kind=kind,
            artifact_sha256=f"{index + 1:02x}" * 32,
        )
        for index, kind in enumerate(
            ("authority_root_ledger", "reviewer_enrollments", "campaign_envelope")
        )
    )
    log = build_transparency_log("benchmark-production", entries)
    head = _signed_head(log, active_private, ledger)
    proof = build_transparency_inclusion_proof(log, leaf_index=2, tree_head=head)

    verify_transparency_inclusion_proof(
        proof,
        ledger,
        expected_kind="campaign_envelope",
        expected_artifact_sha256=entries[2].artifact_sha256,
    )
    tampered = proof.model_copy(
        update={"audit_path_sha256": ("00" * 32,) + proof.audit_path_sha256[1:]}
    )
    with pytest.raises(ValueError, match="inclusion proof root does not match"):
        verify_transparency_inclusion_proof(
            tampered,
            ledger,
            expected_kind="campaign_envelope",
            expected_artifact_sha256=entries[2].artifact_sha256,
        )


def test_complete_log_extension_requires_exact_prefix() -> None:
    first = TransparencyLogEntry(
        sequence=0,
        kind="authority_root_ledger",
        artifact_sha256="11" * 32,
    )
    second = TransparencyLogEntry(
        sequence=1,
        kind="campaign_envelope",
        artifact_sha256="22" * 32,
    )
    original = build_transparency_log("benchmark-production", (first,))
    extended = extend_transparency_log(original, (second,))

    verify_complete_log_extension(original, extended)
    replaced = build_transparency_log(
        "benchmark-production",
        (
            first.model_copy(update={"artifact_sha256": "33" * 32}),
            second,
        ),
    )
    with pytest.raises(ValueError, match="not an append-only extension"):
        verify_complete_log_extension(original, replaced)


def test_transparency_cli_builds_private_key_free_artifacts_read_only(
    tmp_path: Path,
) -> None:
    active_private, genesis, _, ledger = _signed_ledger(revoke_genesis=True)
    generations_path = tmp_path / "generations.json"
    generations_path.write_text(
        json.dumps(
            {
                "generations": [
                    item.model_dump(mode="json")
                    for item in ledger.statement.generations
                ],
                "revoked_authority_sha256": [genesis.authority_sha256],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    ledger_request_path = tmp_path / "ledger-request.json"
    ledger_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-authority-root-ledger-template",
            "--generations",
            str(generations_path),
            "--output",
            str(ledger_request_path),
            "--json",
        ],
    )
    assert ledger_result.exit_code == 0
    assert "private" not in ledger_result.output.lower()

    entries_path = tmp_path / "entries.json"
    entries_path.write_text(
        json.dumps(
            [
                {
                    "sequence": 0,
                    "kind": "campaign_envelope",
                    "artifact_sha256": "44" * 32,
                }
            ],
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "log.json"
    log_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-transparency-log",
            "--log-id",
            "benchmark-production",
            "--entries",
            str(entries_path),
            "--output",
            str(log_path),
            "--json",
        ],
    )
    assert log_result.exit_code == 0
    log = TransparencyLog.model_validate_json(log_path.read_text(encoding="utf-8"))
    assert log.tree_size == 1

    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(ledger.to_json(), encoding="utf-8")
    head_request_path = tmp_path / "head-request.json"
    head_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-transparency-tree-head-template",
            "--log",
            str(log_path),
            "--authority-root-ledger",
            str(ledger_path),
            "--output",
            str(head_request_path),
            "--json",
        ],
    )
    assert head_result.exit_code == 0
    request = TransparencyTreeHeadSigningRequest.model_validate_json(
        head_request_path.read_text(encoding="utf-8")
    )
    head = SignedTransparencyTreeHead(
        statement=request.statement,
        signature_base64=base64.b64encode(
            active_private.sign(request.statement.signing_bytes())
        ).decode(),
    )
    head_path = tmp_path / "head.json"
    head_path.write_text(head.model_dump_json(), encoding="utf-8")
    proof_path = tmp_path / "proof.json"
    proof_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-transparency-proof",
            "--log",
            str(log_path),
            "--tree-head",
            str(head_path),
            "--leaf-index",
            "0",
            "--output",
            str(proof_path),
            "--json",
        ],
    )

    assert proof_result.exit_code == 0
    proof = TransparencyInclusionProof.model_validate_json(
        proof_path.read_text(encoding="utf-8")
    )
    verify_transparency_inclusion_proof(
        proof,
        ledger,
        expected_kind="campaign_envelope",
        expected_artifact_sha256="44" * 32,
    )
    assert generations_path.read_text(encoding="utf-8").startswith("{")
    assert entries_path.read_text(encoding="utf-8").startswith("[")
