"""Offline authority-root rotation and append-only benchmark transparency."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_authority import BenchmarkAuthority
from benchmarks.agent_cli_comparison import SCHEMA_VERSION

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
TransparencyArtifactKind = Literal[
    "authority_root_ledger",
    "reviewer_enrollments",
    "campaign_envelope",
]


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


def _decode_base64(value: str, *, label: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{label} must encode exactly {length} bytes")
    return decoded


def _public_key(authority: BenchmarkAuthority) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(
        _decode_base64(
            authority.public_key_base64,
            label="authority public_key_base64",
            length=32,
        )
    )


class AuthorityRotationStatement(_FrozenModel):
    schema_version: int
    generation: int = Field(ge=2)
    predecessor_authority_sha256: str = Field(pattern=_SHA256_PATTERN)
    successor_authority_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> AuthorityRotationStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.predecessor_authority_sha256 == self.successor_authority_sha256:
            raise ValueError("authority rotation must change the root authority")
        return self

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class AuthorityRotationSigningRequest(_FrozenModel):
    statement: AuthorityRotationStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> AuthorityRotationSigningRequest:
        expected = self.statement.signing_bytes()
        decoded = _decode_base64(
            self.signing_payload_base64,
            label="authority rotation signing payload",
            length=len(expected),
        )
        if decoded != expected:
            raise ValueError("authority rotation payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class AuthorityRotationCertificate(_FrozenModel):
    statement: AuthorityRotationStatement
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_encoding(self) -> AuthorityRotationCertificate:
        _decode_base64(
            self.signature_base64,
            label="authority rotation signature",
            length=64,
        )
        return self


class AuthorityRootGeneration(_FrozenModel):
    schema_version: int
    generation: int = Field(ge=1)
    authority: BenchmarkAuthority
    rotation: AuthorityRotationCertificate | None = None

    @model_validator(mode="after")
    def validate_generation(self) -> AuthorityRootGeneration:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if (self.generation == 1) != (self.rotation is None):
            raise ValueError("only the genesis authority may omit a rotation certificate")
        return self


class AuthorityRootLedgerStatement(_FrozenModel):
    schema_version: int
    generations: tuple[AuthorityRootGeneration, ...] = Field(min_length=1)
    revoked_authority_sha256: tuple[str, ...] = ()
    active_generation: int = Field(ge=1)
    ledger_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> AuthorityRootLedgerStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.active_generation != self.generations[-1].generation:
            raise ValueError("active_generation must identify the latest root generation")
        revoked = self.revoked_authority_sha256
        if tuple(sorted(set(revoked))) != revoked:
            raise ValueError("revoked authority fingerprints must be sorted and unique")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in revoked
        ):
            raise ValueError("revoked authority fingerprints must be SHA-256 hex")
        if self.ledger_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("authority root ledger fingerprint does not match statement")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"ledger_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class AuthorityRootLedgerSigningRequest(_FrozenModel):
    statement: AuthorityRootLedgerStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> AuthorityRootLedgerSigningRequest:
        expected = self.statement.signing_bytes()
        try:
            decoded = base64.b64decode(self.signing_payload_base64, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("authority root ledger payload must be canonical base64") from exc
        if decoded != expected or base64.b64encode(decoded).decode() != self.signing_payload_base64:
            raise ValueError("authority root ledger payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedAuthorityRootLedger(_FrozenModel):
    statement: AuthorityRootLedgerStatement
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_encoding(self) -> SignedAuthorityRootLedger:
        _decode_base64(
            self.signature_base64,
            label="authority root ledger signature",
            length=64,
        )
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_authority_rotation_request(
    *,
    generation: int,
    predecessor: BenchmarkAuthority,
    successor: BenchmarkAuthority,
) -> AuthorityRotationSigningRequest:
    """Create a predecessor-key signing payload for one root rotation."""
    statement = AuthorityRotationStatement(
        schema_version=SCHEMA_VERSION,
        generation=generation,
        predecessor_authority_sha256=predecessor.authority_sha256,
        successor_authority_sha256=successor.authority_sha256,
    )
    return AuthorityRotationSigningRequest(
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def _validate_generation_chain(
    generations: tuple[AuthorityRootGeneration, ...],
) -> None:
    if not generations:
        raise ValueError("authority root ledger requires at least one generation")
    if generations[0].generation != 1 or generations[0].rotation is not None:
        raise ValueError("authority root ledger must begin with an unsigned genesis")
    fingerprints: set[str] = set()
    for index, generation in enumerate(generations):
        if generation.generation != index + 1:
            raise ValueError("authority root generations must be contiguous and ordered")
        fingerprint = generation.authority.authority_sha256
        if fingerprint in fingerprints:
            raise ValueError("authority root generations must not reuse an authority")
        fingerprints.add(fingerprint)
        if index == 0:
            continue
        predecessor = generations[index - 1].authority
        rotation = generation.rotation
        if rotation is None:
            raise ValueError("rotated authority generation is missing its certificate")
        expected = AuthorityRotationStatement(
            schema_version=SCHEMA_VERSION,
            generation=generation.generation,
            predecessor_authority_sha256=predecessor.authority_sha256,
            successor_authority_sha256=fingerprint,
        )
        if rotation.statement != expected:
            raise ValueError("authority rotation statement does not match generation chain")
        try:
            _public_key(predecessor).verify(
                _decode_base64(
                    rotation.signature_base64,
                    label="authority rotation signature",
                    length=64,
                ),
                rotation.statement.signing_bytes(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("authority rotation signature is invalid") from exc


def build_authority_root_ledger_request(
    generations: tuple[AuthorityRootGeneration, ...],
    *,
    revoked_authority_sha256: tuple[str, ...] = (),
) -> AuthorityRootLedgerSigningRequest:
    """Create an active-root signing payload after verifying the full rotation chain."""
    _validate_generation_chain(generations)
    known = {generation.authority.authority_sha256 for generation in generations}
    revoked = tuple(sorted(set(revoked_authority_sha256)))
    unknown = set(revoked) - known
    if unknown:
        raise ValueError("revoked authority is not present in the root ledger")
    active = generations[-1].authority.authority_sha256
    if active in revoked:
        raise ValueError("active authority is revoked")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generations": [item.model_dump(mode="json") for item in generations],
        "revoked_authority_sha256": list(revoked),
        "active_generation": generations[-1].generation,
    }
    statement = AuthorityRootLedgerStatement(
        **payload,
        ledger_sha256=_canonical_sha256(payload),
    )
    return AuthorityRootLedgerSigningRequest(
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def verify_authority_root_ledger(
    ledger: SignedAuthorityRootLedger,
) -> BenchmarkAuthority:
    """Verify rotations, revocations, and the latest authority's ledger signature."""
    statement = AuthorityRootLedgerStatement.model_validate(
        ledger.statement.model_dump(mode="json")
    )
    if statement.ledger_sha256 != _canonical_sha256(statement._binding_payload()):
        raise ValueError("authority root ledger fingerprint does not match statement")
    _validate_generation_chain(statement.generations)
    known = {
        generation.authority.authority_sha256 for generation in statement.generations
    }
    if set(statement.revoked_authority_sha256) - known:
        raise ValueError("revoked authority is not present in the root ledger")
    active = statement.generations[-1].authority
    if active.authority_sha256 in statement.revoked_authority_sha256:
        raise ValueError("active authority is revoked")
    try:
        _public_key(active).verify(
            _decode_base64(
                ledger.signature_base64,
                label="authority root ledger signature",
                length=64,
            ),
            statement.signing_bytes(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("authority root ledger signature is invalid") from exc
    return active


class TransparencyLogEntry(_FrozenModel):
    sequence: int = Field(ge=0)
    kind: TransparencyArtifactKind
    artifact_sha256: str = Field(pattern=_SHA256_PATTERN)

    def leaf_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


def _leaf_hash(entry: TransparencyLogEntry) -> bytes:
    return hashlib.sha256(b"\x00" + entry.leaf_bytes()).digest()


def _largest_power_of_two_less_than(value: int) -> int:
    return 1 << ((value - 1).bit_length() - 1)


def _merkle_root(entries: tuple[TransparencyLogEntry, ...]) -> bytes:
    if not entries:
        return hashlib.sha256(b"").digest()
    if len(entries) == 1:
        return _leaf_hash(entries[0])
    split = _largest_power_of_two_less_than(len(entries))
    return hashlib.sha256(
        b"\x01" + _merkle_root(entries[:split]) + _merkle_root(entries[split:])
    ).digest()


class TransparencyLog(_FrozenModel):
    schema_version: int
    log_id: str = Field(min_length=1, max_length=200)
    entries: tuple[TransparencyLogEntry, ...]
    tree_size: int = Field(ge=0)
    root_sha256: str = Field(pattern=_SHA256_PATTERN)
    log_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_log(self) -> TransparencyLog:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if not self.log_id or self.log_id != self.log_id.strip():
            raise ValueError("log_id must be non-blank without surrounding whitespace")
        if tuple(entry.sequence for entry in self.entries) != tuple(range(len(self.entries))):
            raise ValueError("transparency log entries must have contiguous sequence numbers")
        if self.tree_size != len(self.entries):
            raise ValueError("transparency tree_size does not match entries")
        if self.root_sha256 != _merkle_root(self.entries).hex():
            raise ValueError("transparency root does not match entries")
        if self.log_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("transparency log fingerprint does not match entries")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"log_sha256"})

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_transparency_log(
    log_id: str,
    entries: tuple[TransparencyLogEntry, ...],
) -> TransparencyLog:
    """Build a complete deterministic RFC 6962-style Merkle log artifact."""
    normalized = tuple(
        entry.model_copy(update={"sequence": index})
        for index, entry in enumerate(entries)
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "log_id": log_id,
        "entries": [entry.model_dump(mode="json") for entry in normalized],
        "tree_size": len(normalized),
        "root_sha256": _merkle_root(normalized).hex(),
    }
    return TransparencyLog(**payload, log_sha256=_canonical_sha256(payload))


def extend_transparency_log(
    previous: TransparencyLog,
    entries: tuple[TransparencyLogEntry, ...],
) -> TransparencyLog:
    """Append entries to a complete log without mutating its existing prefix."""
    return build_transparency_log(previous.log_id, previous.entries + entries)


def verify_complete_log_extension(
    previous: TransparencyLog,
    current: TransparencyLog,
) -> None:
    """Verify append-only growth when both complete log artifacts are available."""
    previous = TransparencyLog.model_validate(previous.model_dump(mode="json"))
    current = TransparencyLog.model_validate(current.model_dump(mode="json"))
    if previous.log_id != current.log_id:
        raise ValueError("transparency log_id changed")
    if current.tree_size < previous.tree_size:
        raise ValueError("transparency log is not an append-only extension")
    if current.entries[: previous.tree_size] != previous.entries:
        raise ValueError("transparency log is not an append-only extension")


class TransparencyTreeHeadStatement(_FrozenModel):
    schema_version: int
    log_id: str = Field(min_length=1, max_length=200)
    tree_size: int = Field(ge=0)
    root_sha256: str = Field(pattern=_SHA256_PATTERN)
    authority_root_ledger_sha256: str = Field(pattern=_SHA256_PATTERN)
    tree_head_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_statement(self) -> TransparencyTreeHeadStatement:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.tree_head_sha256 != _canonical_sha256(self._binding_payload()):
            raise ValueError("transparency tree head fingerprint does not match statement")
        return self

    def _binding_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"tree_head_sha256"})

    def signing_bytes(self) -> bytes:
        return _canonical_json(self.model_dump(mode="json")).encode()


class TransparencyTreeHeadSigningRequest(_FrozenModel):
    statement: TransparencyTreeHeadStatement
    signing_payload_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_payload(self) -> TransparencyTreeHeadSigningRequest:
        expected = self.statement.signing_bytes()
        try:
            decoded = base64.b64decode(self.signing_payload_base64, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("transparency tree head payload must be canonical base64") from exc
        if decoded != expected or base64.b64encode(decoded).decode() != self.signing_payload_base64:
            raise ValueError("transparency tree head payload does not match statement")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class SignedTransparencyTreeHead(_FrozenModel):
    statement: TransparencyTreeHeadStatement
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_encoding(self) -> SignedTransparencyTreeHead:
        _decode_base64(
            self.signature_base64,
            label="transparency tree head signature",
            length=64,
        )
        return self


class TransparencyInclusionProof(_FrozenModel):
    schema_version: int
    entry: TransparencyLogEntry
    leaf_index: int = Field(ge=0)
    tree_size: int = Field(ge=1)
    audit_path_sha256: tuple[str, ...]
    tree_head: SignedTransparencyTreeHead

    @model_validator(mode="after")
    def validate_proof(self) -> TransparencyInclusionProof:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.leaf_index >= self.tree_size:
            raise ValueError("transparency leaf_index is outside tree_size")
        if self.entry.sequence != self.leaf_index:
            raise ValueError("transparency entry sequence does not match leaf_index")
        if self.tree_head.statement.tree_size != self.tree_size:
            raise ValueError("transparency proof tree_size does not match tree head")
        for digest in self.audit_path_sha256:
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("transparency audit path must contain SHA-256 hex")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def build_transparency_tree_head_request(
    log: TransparencyLog,
    ledger: SignedAuthorityRootLedger,
) -> TransparencyTreeHeadSigningRequest:
    """Create an active-root signing payload for one Merkle tree head."""
    verify_authority_root_ledger(ledger)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "log_id": log.log_id,
        "tree_size": log.tree_size,
        "root_sha256": log.root_sha256,
        "authority_root_ledger_sha256": ledger.statement.ledger_sha256,
    }
    statement = TransparencyTreeHeadStatement(
        **payload,
        tree_head_sha256=_canonical_sha256(payload),
    )
    return TransparencyTreeHeadSigningRequest(
        statement=statement,
        signing_payload_base64=base64.b64encode(statement.signing_bytes()).decode(),
    )


def _audit_path(
    entries: tuple[TransparencyLogEntry, ...],
    leaf_index: int,
) -> tuple[bytes, ...]:
    if len(entries) == 1:
        return ()
    split = _largest_power_of_two_less_than(len(entries))
    if leaf_index < split:
        return _audit_path(entries[:split], leaf_index) + (
            _merkle_root(entries[split:]),
        )
    return _audit_path(entries[split:], leaf_index - split) + (
        _merkle_root(entries[:split]),
    )


def build_transparency_inclusion_proof(
    log: TransparencyLog,
    *,
    leaf_index: int,
    tree_head: SignedTransparencyTreeHead,
) -> TransparencyInclusionProof:
    """Build an inclusion proof against an already-signed matching tree head."""
    if leaf_index < 0 or leaf_index >= log.tree_size:
        raise ValueError("transparency leaf_index is outside tree_size")
    statement = tree_head.statement
    if (
        statement.log_id,
        statement.tree_size,
        statement.root_sha256,
    ) != (log.log_id, log.tree_size, log.root_sha256):
        raise ValueError("signed transparency tree head does not match log")
    return TransparencyInclusionProof(
        schema_version=SCHEMA_VERSION,
        entry=log.entries[leaf_index],
        leaf_index=leaf_index,
        tree_size=log.tree_size,
        audit_path_sha256=tuple(item.hex() for item in _audit_path(log.entries, leaf_index)),
        tree_head=tree_head,
    )


def _root_from_audit_path(
    leaf_hash: bytes,
    *,
    leaf_index: int,
    tree_size: int,
    audit_path: tuple[bytes, ...],
) -> bytes:
    position = 0

    def rebuild(current: bytes, index: int, size: int) -> bytes:
        nonlocal position
        if size == 1:
            return current
        split = _largest_power_of_two_less_than(size)
        if index < split:
            left = rebuild(current, index, split)
            if position >= len(audit_path):
                raise ValueError("transparency inclusion proof audit path is incomplete")
            right = audit_path[position]
            position += 1
            return hashlib.sha256(b"\x01" + left + right).digest()
        right = rebuild(current, index - split, size - split)
        if position >= len(audit_path):
            raise ValueError("transparency inclusion proof audit path is incomplete")
        left = audit_path[position]
        position += 1
        return hashlib.sha256(b"\x01" + left + right).digest()

    root = rebuild(leaf_hash, leaf_index, tree_size)
    if position != len(audit_path):
        raise ValueError("transparency inclusion proof audit path has extra nodes")
    return root


def verify_transparency_inclusion_proof(
    proof: TransparencyInclusionProof,
    ledger: SignedAuthorityRootLedger,
    *,
    expected_kind: TransparencyArtifactKind,
    expected_artifact_sha256: str,
) -> None:
    """Verify the artifact leaf, signed tree head, and authority-root ledger."""
    proof = TransparencyInclusionProof.model_validate(proof.model_dump(mode="json"))
    active = verify_authority_root_ledger(ledger)
    statement = TransparencyTreeHeadStatement.model_validate(
        proof.tree_head.statement.model_dump(mode="json")
    )
    if statement.authority_root_ledger_sha256 != ledger.statement.ledger_sha256:
        raise ValueError("transparency tree head does not match authority root ledger")
    if statement.tree_head_sha256 != _canonical_sha256(statement._binding_payload()):
        raise ValueError("transparency tree head fingerprint does not match statement")
    try:
        _public_key(active).verify(
            _decode_base64(
                proof.tree_head.signature_base64,
                label="transparency tree head signature",
                length=64,
            ),
            statement.signing_bytes(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("transparency tree head signature is invalid") from exc
    if (proof.entry.kind, proof.entry.artifact_sha256) != (
        expected_kind,
        expected_artifact_sha256,
    ):
        raise ValueError("transparency inclusion proof does not match expected artifact")
    root = _root_from_audit_path(
        _leaf_hash(proof.entry),
        leaf_index=proof.leaf_index,
        tree_size=proof.tree_size,
        audit_path=tuple(bytes.fromhex(item) for item in proof.audit_path_sha256),
    )
    if root.hex() != statement.root_sha256:
        raise ValueError("transparency inclusion proof root does not match tree head")
