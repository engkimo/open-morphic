"""Offline quorum witnesses for benchmark transparency checkpoints."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_comparison import SCHEMA_VERSION
from benchmarks.agent_cli_transparency import (
    SignedAuthorityRootLedger,
    TransparencyConsistencyProof,
    verify_transparency_consistency_proof,
)

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


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _validate_identifier(identifier: str, *, label: str) -> None:
    if not identifier or identifier != identifier.strip():
        raise ValueError(f"{label} must be non-blank without surrounding whitespace")


def _decode_base64(value: str, *, label: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


class TransparencyWitnessKeyDeclaration(_FrozenModel):
    witness_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    status: Literal["active", "revoked"] = "active"

    @model_validator(mode="after")
    def validate_key(self) -> TransparencyWitnessKeyDeclaration:
        _validate_identifier(self.witness_id, label="witness_id")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(
            self.public_key_base64,
            label="witness public_key_base64",
            length=32,
        )
        return self


class TransparencyWitnessTrustDeclaration(_FrozenModel):
    schema_version: int
    log_id: str = Field(min_length=1, max_length=200)
    minimum_distinct_witnesses: int = Field(ge=1)
    keys: tuple[TransparencyWitnessKeyDeclaration, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_declaration(self) -> TransparencyWitnessTrustDeclaration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        _validate_identifier(self.log_id, label="log_id")
        identities = [(key.witness_id, key.key_id) for key in self.keys]
        if len(identities) != len(set(identities)):
            raise ValueError("witness key identities must be unique")
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("witness key_id values must be globally unique")
        return self


class TransparencyWitnessKey(_FrozenModel):
    witness_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    status: Literal["active", "revoked"]

    @model_validator(mode="after")
    def validate_fingerprint(self) -> TransparencyWitnessKey:
        declaration = TransparencyWitnessKeyDeclaration(
            witness_id=self.witness_id,
            key_id=self.key_id,
            algorithm=self.algorithm,
            public_key_base64=self.public_key_base64,
            status=self.status,
        )
        public_key = _decode_base64(
            declaration.public_key_base64,
            label="witness public_key_base64",
            length=32,
        )
        if self.public_key_sha256 != hashlib.sha256(public_key).hexdigest():
            raise ValueError("witness public key fingerprint does not match key")
        return self


class TransparencyWitnessTrust(_FrozenModel):
    schema_version: int
    log_id: str = Field(min_length=1, max_length=200)
    minimum_distinct_witnesses: int = Field(ge=1)
    keys: tuple[TransparencyWitnessKey, ...] = Field(min_length=1)
    witness_trust_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_trust(self) -> TransparencyWitnessTrust:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if tuple(sorted(self.keys, key=_key_identity)) != self.keys:
            raise ValueError("witness keys must be sorted")
        if self.witness_trust_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("witness trust fingerprint does not match declaration")
        _validate_witness_capacity(
            self.keys,
            minimum_distinct_witnesses=self.minimum_distinct_witnesses,
        )
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"witness_trust_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _key_identity(
    key: TransparencyWitnessKey | TransparencyWitnessKeyDeclaration,
) -> tuple[str, str]:
    return key.witness_id, key.key_id


def _validate_witness_capacity(
    keys: tuple[TransparencyWitnessKey, ...],
    *,
    minimum_distinct_witnesses: int,
) -> None:
    active_witnesses = {key.witness_id for key in keys if key.status == "active"}
    declared_witnesses = {key.witness_id for key in keys}
    missing = sorted(declared_witnesses - active_witnesses)
    if missing:
        raise ValueError(f"witness has no active key: {', '.join(missing)}")
    if minimum_distinct_witnesses > len(active_witnesses):
        raise ValueError("witness quorum exceeds active witness capacity")
    if minimum_distinct_witnesses <= len(active_witnesses) // 2:
        raise ValueError("witness quorum must be a strict majority")


def build_transparency_witness_trust(
    declaration: TransparencyWitnessTrustDeclaration,
) -> TransparencyWitnessTrust:
    """Normalize witness public keys and require an intersecting active quorum."""
    keys = tuple(
        sorted(
            (
                TransparencyWitnessKey(
                    witness_id=key.witness_id,
                    key_id=key.key_id,
                    algorithm=key.algorithm,
                    public_key_base64=key.public_key_base64,
                    public_key_sha256=hashlib.sha256(
                        _decode_base64(
                            key.public_key_base64,
                            label="witness public_key_base64",
                            length=32,
                        )
                    ).hexdigest(),
                    status=key.status,
                )
                for key in declaration.keys
            ),
            key=_key_identity,
        )
    )
    _validate_witness_capacity(
        keys,
        minimum_distinct_witnesses=declaration.minimum_distinct_witnesses,
    )
    payload = {
        "schema_version": declaration.schema_version,
        "log_id": declaration.log_id,
        "minimum_distinct_witnesses": declaration.minimum_distinct_witnesses,
        "keys": [key.model_dump(mode="json") for key in keys],
    }
    return TransparencyWitnessTrust(
        **payload,
        witness_trust_sha256=_canonical_sha256(payload),
    )


class WitnessCheckpointStatement(_FrozenModel):
    schema_version: int
    log_id: str = Field(min_length=1, max_length=200)
    previous_tree_size: int = Field(ge=1)
    previous_root_sha256: str = Field(pattern=_SHA256_PATTERN)
    previous_tree_head_sha256: str = Field(pattern=_SHA256_PATTERN)
    current_tree_size: int = Field(ge=2)
    current_root_sha256: str = Field(pattern=_SHA256_PATTERN)
    current_tree_head_sha256: str = Field(pattern=_SHA256_PATTERN)
    authority_root_ledger_sha256: str = Field(pattern=_SHA256_PATTERN)
    consistency_proof_sha256: str = Field(pattern=_SHA256_PATTERN)
    witness_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    checkpoint_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> WitnessCheckpointStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.previous_tree_size >= self.current_tree_size:
            raise ValueError("witness checkpoint requires increasing tree sizes")
        if self.checkpoint_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("witness checkpoint fingerprint does not match statement")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"checkpoint_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class WitnessCheckpointSigningRequest(_FrozenModel):
    witness_id: str = Field(min_length=1, max_length=200)
    eligible_key_ids: tuple[str, ...] = Field(min_length=1)
    statement: WitnessCheckpointStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> WitnessCheckpointSigningRequest:
        _validate_identifier(self.witness_id, label="witness_id")
        if tuple(sorted(set(self.eligible_key_ids))) != self.eligible_key_ids:
            raise ValueError("eligible witness key IDs must be sorted and unique")
        expected = self.statement.signing_bytes()
        try:
            decoded = base64.b64decode(self.signing_payload_base64, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("witness checkpoint payload must be canonical base64") from exc
        if decoded != expected or base64.b64encode(decoded).decode() != (
            self.signing_payload_base64
        ):
            raise ValueError("witness checkpoint payload does not match statement")
        return self


class WitnessCheckpointTemplate(_FrozenModel):
    schema_version: int
    witness_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    consistency_proof_sha256: str = Field(pattern=_SHA256_PATTERN)
    statement: WitnessCheckpointStatement
    requests: tuple[WitnessCheckpointSigningRequest, ...] = Field(min_length=1)
    signatures_completed: Literal[False] = False

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class TransparencyWitnessSignature(_FrozenModel):
    witness_id: str = Field(min_length=1, max_length=200)
    key_id: str = Field(min_length=1, max_length=200)
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature(self) -> TransparencyWitnessSignature:
        _validate_identifier(self.witness_id, label="witness_id")
        _validate_identifier(self.key_id, label="key_id")
        _decode_base64(
            self.signature_base64,
            label="witness checkpoint signature",
            length=64,
        )
        return self


class SignedWitnessCheckpoint(_FrozenModel):
    schema_version: int
    statement: WitnessCheckpointStatement
    signatures: tuple[TransparencyWitnessSignature, ...] = Field(min_length=1)
    witness_checkpoint_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_bundle(self) -> SignedWitnessCheckpoint:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if tuple(sorted(self.signatures, key=_signature_identity)) != self.signatures:
            raise ValueError("witness signatures must be sorted")
        witness_ids = [signature.witness_id for signature in self.signatures]
        if len(witness_ids) != len(set(witness_ids)):
            raise ValueError("witness checkpoint signatures must use distinct witnesses")
        if self.witness_checkpoint_sha256 != _canonical_sha256(
            self._binding_payload()
        ):
            raise ValueError("witness checkpoint bundle fingerprint does not match")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"witness_checkpoint_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _signature_identity(
    signature: TransparencyWitnessSignature,
) -> tuple[str, str]:
    return signature.witness_id, signature.key_id


def _checkpoint_statement(
    trust: TransparencyWitnessTrust,
    proof: TransparencyConsistencyProof,
    ledger: SignedAuthorityRootLedger,
) -> WitnessCheckpointStatement:
    verify_transparency_consistency_proof(proof, ledger)
    previous = proof.previous_tree_head.statement
    current = proof.current_tree_head.statement
    if trust.log_id != current.log_id:
        raise ValueError("witness trust log_id does not match consistency proof")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "log_id": current.log_id,
        "previous_tree_size": previous.tree_size,
        "previous_root_sha256": previous.root_sha256,
        "previous_tree_head_sha256": previous.tree_head_sha256,
        "current_tree_size": current.tree_size,
        "current_root_sha256": current.root_sha256,
        "current_tree_head_sha256": current.tree_head_sha256,
        "authority_root_ledger_sha256": ledger.statement.ledger_sha256,
        "consistency_proof_sha256": proof.consistency_proof_sha256,
        "witness_trust_sha256": trust.witness_trust_sha256,
    }
    return WitnessCheckpointStatement(
        **payload,
        checkpoint_sha256=_canonical_sha256(payload),
    )


def build_witness_checkpoint_template(
    trust: TransparencyWitnessTrust,
    proof: TransparencyConsistencyProof,
    ledger: SignedAuthorityRootLedger,
) -> WitnessCheckpointTemplate:
    """Create one private-key-free checkpoint request per active witness."""
    statement = _checkpoint_statement(trust, proof, ledger)
    active_keys: dict[str, list[str]] = {}
    for key in trust.keys:
        if key.status == "active":
            active_keys.setdefault(key.witness_id, []).append(key.key_id)
    requests = tuple(
        WitnessCheckpointSigningRequest(
            witness_id=witness_id,
            eligible_key_ids=tuple(sorted(key_ids)),
            statement=statement,
            signing_payload_base64=base64.b64encode(
                statement.signing_bytes()
            ).decode(),
        )
        for witness_id, key_ids in sorted(active_keys.items())
    )
    return WitnessCheckpointTemplate(
        schema_version=SCHEMA_VERSION,
        witness_trust_sha256=trust.witness_trust_sha256,
        consistency_proof_sha256=proof.consistency_proof_sha256,
        statement=statement,
        requests=requests,
    )


def build_witness_checkpoint_bundle(
    trust: TransparencyWitnessTrust,
    proof: TransparencyConsistencyProof,
    ledger: SignedAuthorityRootLedger,
    signatures: tuple[TransparencyWitnessSignature, ...],
) -> SignedWitnessCheckpoint:
    """Normalize and verify a quorum of detached witness signatures."""
    statement = _checkpoint_statement(trust, proof, ledger)
    ordered = tuple(sorted(signatures, key=_signature_identity))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "statement": statement.model_dump(mode="json"),
        "signatures": [signature.model_dump(mode="json") for signature in ordered],
    }
    bundle = SignedWitnessCheckpoint(
        **payload,
        witness_checkpoint_sha256=_canonical_sha256(payload),
    )
    verify_witness_checkpoint_bundle(trust, proof, ledger, bundle)
    return bundle


def verify_witness_checkpoint_bundle(
    trust: TransparencyWitnessTrust,
    proof: TransparencyConsistencyProof,
    ledger: SignedAuthorityRootLedger,
    bundle: SignedWitnessCheckpoint,
) -> None:
    """Verify exact checkpoint binding and an intersecting witness quorum."""
    trust = TransparencyWitnessTrust.model_validate(trust.model_dump(mode="json"))
    bundle = SignedWitnessCheckpoint.model_validate(bundle.model_dump(mode="json"))
    expected_statement = _checkpoint_statement(trust, proof, ledger)
    if bundle.statement != expected_statement:
        raise ValueError("witness checkpoint does not match consistency proof")
    if len(bundle.signatures) < trust.minimum_distinct_witnesses:
        raise ValueError("witness quorum is incomplete")
    active_keys = {
        (key.witness_id, key.key_id): key for key in trust.keys if key.status == "active"
    }
    for signature in bundle.signatures:
        key = active_keys.get(_signature_identity(signature))
        if key is None:
            raise ValueError("witness signature does not use an active trusted key")
        try:
            Ed25519PublicKey.from_public_bytes(
                _decode_base64(
                    key.public_key_base64,
                    label="witness public_key_base64",
                    length=32,
                )
            ).verify(
                _decode_base64(
                    signature.signature_base64,
                    label="witness checkpoint signature",
                    length=64,
                ),
                bundle.statement.signing_bytes(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError(
                f"witness signature is invalid: {signature.witness_id}"
            ) from exc


def detect_witness_checkpoint_conflict(
    first: SignedWitnessCheckpoint,
    second: SignedWitnessCheckpoint,
) -> None:
    """Reject two witnessed roots for the same log and tree size."""
    first_statement = SignedWitnessCheckpoint.model_validate(
        first.model_dump(mode="json")
    ).statement
    second_statement = SignedWitnessCheckpoint.model_validate(
        second.model_dump(mode="json")
    ).statement
    if first_statement.log_id != second_statement.log_id:
        return
    if (
        first_statement.current_tree_size == second_statement.current_tree_size
        and first_statement.current_root_sha256
        != second_statement.current_root_sha256
    ):
        raise ValueError("split-view checkpoint detected for the same tree size")
