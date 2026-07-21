"""Tests for agent CLI campaign preflight and review template binding."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from typer.testing import CliRunner

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    finalize_recorded_results,
)
from benchmarks.agent_cli_attestation import (
    ReviewAttestationBundle,
    ReviewerPublicKeyDeclaration,
    ReviewerTrustDeclaration,
    SignedReviewAttestation,
    build_review_attestation_template,
    build_reviewer_trust,
    verify_review_attestations,
)
from benchmarks.agent_cli_authority import (
    BenchmarkAuthorityDeclaration,
    ReviewerEnrollmentCertificate,
    SignedCampaignEnvelope,
    build_benchmark_authority,
    build_campaign_envelope_request,
    build_reviewer_enrollment_bundle,
    build_reviewer_enrollment_statement,
    build_reviewer_enrollment_template,
    verify_reviewer_enrollments,
    verify_signed_campaign_envelope,
)
from benchmarks.agent_cli_campaign import CampaignStage, build_campaign_status
from benchmarks.agent_cli_comparison import AgentCliArm, AgentCliManifest
from benchmarks.agent_cli_preflight import (
    CampaignPreflight,
    RuntimeVersionBundle,
    build_campaign_preflight,
    build_review_template,
    recorded_evidence_sha256,
    validate_review_bindings,
)
from benchmarks.agent_cli_recorder import AgentCliRecorderConfig
from benchmarks.agent_cli_review_policy import (
    ReviewerPolicyDeclaration,
    build_reviewer_policy,
    validate_reviewer_policy_capacity,
    validate_reviewer_separation,
)
from interface.cli.main import app

runner = CliRunner()
REVISION = "a" * 40


def _manifest() -> AgentCliManifest:
    return AgentCliManifest.model_validate(
        {
            "schema_version": 1,
            "benchmark_id": "campaign-001",
            "task": {
                "id": "task-001",
                "goal": "Implement the selected task.",
                "workspace_revision": REVISION,
                "checks": ["unit"],
                "handoff_assertions": ["decision"],
            },
            "arms": ["codex_cli", "claude_code", "morphic_control"],
            "repetitions": 1,
        }
    )


def _config() -> AgentCliRecorderConfig:
    return AgentCliRecorderConfig.model_validate(
        {
            "schema_version": 1,
            "benchmark_id": "campaign-001",
            "arm_commands": {
                "codex_cli": ["codex", "exec", "{goal}"],
                "claude_code": ["claude", "-p", "{goal}"],
                "morphic_control": [
                    "morphic",
                    "code",
                    "--benchmark-receipt",
                    "{goal}",
                ],
            },
            "check_commands": {"unit": ["python", "-m", "pytest", "-q"]},
            "handoff_commands": {"decision": ["python", "-c", "raise SystemExit(0)"]},
            "estimated_cost_usd_per_trial": {
                "codex_cli": 0.5,
                "claude_code": 0.5,
                "morphic_control": 1.0,
            },
            "model_hints": {"codex_cli": "o4-mini"},
            "timeout_seconds": 300.0,
        }
    )


def _versions() -> RuntimeVersionBundle:
    return RuntimeVersionBundle.model_validate(
        {
            "schema_version": 1,
            "benchmark_id": "campaign-001",
            "runtimes": {
                "codex_cli": {"executable": "codex", "version": "codex-cli 1.2.3"},
                "claude_code": {"executable": "claude", "version": "claude 2.3.4"},
                "morphic_control": {
                    "executable": "morphic",
                    "version": "morphic-agent 0.6.3",
                },
            },
        }
    )


def _command(seed: str) -> dict[str, object]:
    return {
        "argv_sha256": seed * 64,
        "exit_code": 0,
        "timed_out": False,
        "elapsed_seconds": 1.0,
        "stdout_sha256": "b" * 64,
        "stdout_bytes": 10,
        "stderr_sha256": "c" * 64,
        "stderr_bytes": 0,
    }


def _evidence() -> RecordedEvidence:
    receipts = {
        "codex_cli": {
            "provider": "codex_cli",
            "success": True,
            "model": "o4-mini",
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            "cost_usd": 0.000198,
            "cost_source": "calculated_from_usage",
            "parse_errors": 0,
        },
        "claude_code": {
            "provider": "claude_code",
            "success": True,
            "model": "claude-sonnet",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "cost_usd": 0.01,
            "cost_source": "provider_reported",
            "parse_errors": 0,
        },
        "morphic_control": {
            "provider": "morphic_control",
            "success": True,
            "model": "morphic-control[codex_cli]",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "cost_usd": 0.02,
            "cost_source": "morphic_reported",
            "parse_errors": 0,
        },
    }
    trials = []
    for index, arm in enumerate(AgentCliArm, start=1):
        trials.append(
            {
                "arm": arm.value,
                "trial": 1,
                "reserved_cost_usd": 1.0,
                "agent": _command(str(index)),
                "checks": {"unit": _command("d")},
                "handoff_assertions": {"decision": _command("e")},
                "receipt": receipts[arm.value],
                "completed": True,
                "passed_checks": ["unit"],
                "passed_handoff_assertions": ["decision"],
            }
        )
    return RecordedEvidence.model_validate(
        {
            "schema_version": 1,
            "benchmark_id": "campaign-001",
            "task_id": "task-001",
            "workspace_revision": REVISION,
            "estimated_max_cost_usd": 2.0,
            "authorized_cost_cap_usd": 2.0,
            "cost_collection": "normalized_receipts",
            "trials": trials,
        }
    )


def _preflight():
    return build_campaign_preflight(
        _manifest(),
        _config(),
        _versions(),
        resolved_revision=REVISION,
    )


def _policy():
    return build_reviewer_policy(
        ReviewerPolicyDeclaration.model_validate(
            {
                "schema_version": 1,
                "benchmark_id": "campaign-001",
                "operator_id": "operator-1",
                "reviewer_ids": ["reviewer-2", "reviewer-1"],
                "minimum_distinct_reviewers": 2,
            }
        )
    )


def _completed_reviews(
    *,
    reviewer_ids: tuple[str, str, str] | None = None,
    reviewer_trust_sha256: str | None = None,
):
    evidence = _evidence()
    policy = _policy()
    payload = build_review_template(
        _preflight(),
        evidence,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=reviewer_trust_sha256,
    ).model_dump(mode="json")
    payload["review_completed"] = True
    assigned = reviewer_ids or ("reviewer-1", "reviewer-2", "reviewer-1")
    for decision, reviewer_id in zip(payload["decisions"], assigned, strict=True):
        decision.update(
            accepted_patch=False,
            human_interventions=0,
            recovery_attempted=False,
            recovery_succeeded=False,
            reviewer_id=reviewer_id,
            review_artifact_sha256="f" * 64,
        )
    return AdjudicationReviews.model_validate(payload)


def _private_keys() -> dict[str, Ed25519PrivateKey]:
    return {
        "reviewer-1": Ed25519PrivateKey.from_private_bytes(b"\x01" * 32),
        "reviewer-2": Ed25519PrivateKey.from_private_bytes(b"\x02" * 32),
    }


def _trust_declaration(
    *,
    revoke_reviewer_2: bool = False,
    reviewer_authority_sha256: str | None = None,
) -> ReviewerTrustDeclaration:
    keys = _private_keys()
    declarations = []
    for reviewer_id, private_key in keys.items():
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        declarations.append(
            ReviewerPublicKeyDeclaration(
                reviewer_id=reviewer_id,
                key_id=f"{reviewer_id}-key-1",
                public_key_base64=base64.b64encode(public_bytes).decode(),
                status=(
                    "revoked"
                    if revoke_reviewer_2 and reviewer_id == "reviewer-2"
                    else "active"
                ),
            )
        )
    return ReviewerTrustDeclaration(
        schema_version=1,
        benchmark_id="campaign-001",
        review_policy_sha256=_policy().policy_sha256,
        reviewer_authority_sha256=reviewer_authority_sha256,
        keys=tuple(reversed(declarations)),
    )


def _review_attestation_bundle(policy, trust, reviews):
    template = build_review_attestation_template(policy, trust, reviews)
    private_keys = _private_keys()
    signed = tuple(
        SignedReviewAttestation(
            statement=request.statement,
            key_id=f"{request.statement.reviewer_id}-key-1",
            signature_base64=base64.b64encode(
                private_keys[request.statement.reviewer_id].sign(
                    request.statement.signing_bytes()
                )
            ).decode(),
        )
        for request in template.requests
    )
    return ReviewAttestationBundle(
        schema_version=1,
        benchmark_id=reviews.benchmark_id,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=trust.reviewer_trust_sha256,
        reviews_sha256=template.reviews_sha256,
        attestations=signed,
    )


def _signed_attestations():
    policy = _policy()
    trust = build_reviewer_trust(_trust_declaration(), policy)
    reviews = _completed_reviews(reviewer_trust_sha256=trust.reviewer_trust_sha256)
    return policy, trust, reviews, _review_attestation_bundle(policy, trust, reviews)


def _authority_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b"\x03" * 32)


def _authority_declaration() -> BenchmarkAuthorityDeclaration:
    public_bytes = _authority_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return BenchmarkAuthorityDeclaration(
        schema_version=1,
        authority_id="example-org-benchmark-ca",
        public_key_base64=base64.b64encode(public_bytes).decode(),
    )


def _anchored_artifacts():
    policy = _policy()
    authority = build_benchmark_authority(_authority_declaration())
    trust = build_reviewer_trust(
        _trust_declaration(reviewer_authority_sha256=authority.authority_sha256),
        policy,
    )
    reviews = _completed_reviews(reviewer_trust_sha256=trust.reviewer_trust_sha256)
    attestations = _review_attestation_bundle(policy, trust, reviews)
    certificates = []
    for key in trust.keys:
        statement = build_reviewer_enrollment_statement(
            authority,
            policy,
            trust,
            key,
        )
        certificates.append(
            ReviewerEnrollmentCertificate(
                statement=statement,
                signature_base64=base64.b64encode(
                    _authority_private_key().sign(statement.signing_bytes())
                ).decode(),
            )
        )
    enrollments = build_reviewer_enrollment_bundle(
        authority,
        policy,
        trust,
        tuple(reversed(certificates)),
    )
    results = finalize_recorded_results(
        _manifest(),
        _evidence(),
        reviews,
        review_policy=policy,
        reviewer_trust=trust,
        attestations=attestations,
        reviewer_authority=authority,
        reviewer_enrollments=enrollments,
    )
    request = build_campaign_envelope_request(
        authority=authority,
        manifest=_manifest(),
        preflight=_preflight(),
        evidence=_evidence(),
        reviews=reviews,
        review_policy=policy,
        reviewer_trust=trust,
        reviewer_enrollments=enrollments,
        attestations=attestations,
        results=results,
    )
    envelope = SignedCampaignEnvelope(
        statement=request.statement,
        signature_base64=base64.b64encode(
            _authority_private_key().sign(request.statement.signing_bytes())
        ).decode(),
    )
    return (
        authority,
        policy,
        trust,
        enrollments,
        reviews,
        attestations,
        results,
        request,
        envelope,
    )


def test_preflight_is_deterministic_non_authorizing_and_prompt_free() -> None:
    first = _preflight()
    second = _preflight()

    assert first.to_json() == second.to_json()
    assert first.execution_authorized is False
    assert first.estimated_max_cost_usd == 2.0
    assert first.trial_count == 3
    assert len(first.preflight_sha256) == 64
    assert len(first.manifest_sha256) == 64
    assert len(first.config_sha256) == 64
    assert "Implement the selected task" not in first.to_json()
    assert set(first.runtime_fingerprints) == set(AgentCliArm)


def test_preflight_binds_manifest_goal_without_exposing_it() -> None:
    changed_payload = _manifest().model_dump(mode="json")
    changed_payload["task"]["goal"] = "A different selected task."
    changed = build_campaign_preflight(
        AgentCliManifest.model_validate(changed_payload),
        _config(),
        _versions(),
        resolved_revision=REVISION,
    )

    assert changed.manifest_sha256 != _preflight().manifest_sha256
    assert "A different selected task" not in changed.to_json()


def test_preflight_normalizes_and_fingerprints_runtime_versions() -> None:
    payload = _versions().model_dump(mode="json")
    payload["runtimes"]["codex_cli"]["version"] = "  codex-cli\n1.2.3  "

    report = build_campaign_preflight(
        _manifest(),
        _config(),
        RuntimeVersionBundle.model_validate(payload),
        resolved_revision=REVISION,
    )

    runtime = report.runtime_fingerprints[AgentCliArm.CODEX_CLI]
    assert runtime.version == "codex-cli 1.2.3"
    assert len(runtime.version_sha256) == 64


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda payload: payload["runtimes"].pop("claude_code"), "exactly"),
        (
            lambda payload: payload["runtimes"]["codex_cli"].update(
                executable="different"
            ),
            "executable",
        ),
    ],
)
def test_preflight_rejects_incomplete_or_mismatched_runtime_declarations(
    mutation: object,
    match: str,
) -> None:
    payload = _versions().model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]

    with pytest.raises((ValidationError, ValueError), match=match):
        build_campaign_preflight(
            _manifest(),
            _config(),
            RuntimeVersionBundle.model_validate(payload),
            resolved_revision=REVISION,
        )


def test_preflight_requires_manifest_to_pin_full_resolved_commit() -> None:
    with pytest.raises(ValueError, match="immutable resolved revision"):
        build_campaign_preflight(
            _manifest(),
            _config(),
            _versions(),
            resolved_revision="b" * 40,
        )


def test_preflight_report_rejects_artifact_tampering() -> None:
    payload = _preflight().model_dump(mode="json")
    payload["estimated_max_cost_usd"] = 1.0

    with pytest.raises(ValidationError, match="preflight fingerprint"):
        CampaignPreflight.model_validate(payload)


def test_review_template_binds_every_trial_to_preflight_and_evidence() -> None:
    evidence = _evidence()
    template = build_review_template(_preflight(), evidence)
    payload = template.model_dump(mode="json")

    assert template.preflight_sha256 == _preflight().preflight_sha256
    assert template.evidence_sha256 == recorded_evidence_sha256(evidence)
    assert len(template.decisions) == 3
    assert payload["decisions"][0]["accepted_patch"] is None
    assert payload["decisions"][0]["reviewer_id"] is None
    assert payload["review_completed"] is False


def test_completed_review_bindings_validate_and_finalize() -> None:
    evidence = _evidence()
    preflight = _preflight()
    template = build_review_template(preflight, evidence).model_dump(mode="json")
    template["review_completed"] = True
    for decision in template["decisions"]:
        decision.update(
            accepted_patch=True,
            human_interventions=0,
            recovery_attempted=False,
            recovery_succeeded=False,
            reviewer_id="reviewer-1",
            review_artifact_sha256="f" * 64,
        )
    reviews = AdjudicationReviews.model_validate(template)

    validate_review_bindings(preflight, evidence, reviews)
    results = finalize_recorded_results(_manifest(), evidence, reviews)

    assert len(results.observations) == 3
    assert all(observation.accepted_patch for observation in results.observations)


def test_finalizer_rejects_review_bound_to_different_evidence() -> None:
    evidence = _evidence()
    payload = build_review_template(_preflight(), evidence).model_dump(mode="json")
    payload["review_completed"] = True
    for decision in payload["decisions"]:
        decision.update(
            accepted_patch=False,
            human_interventions=0,
            recovery_attempted=False,
            recovery_succeeded=False,
            reviewer_id="reviewer-1",
            review_artifact_sha256="f" * 64,
        )
    reviews = AdjudicationReviews.model_validate(payload)
    tampered = evidence.model_copy(update={"authorized_cost_cap_usd": 1.5})

    with pytest.raises(ValueError, match="evidence fingerprint"):
        finalize_recorded_results(_manifest(), tampered, reviews)


def test_committed_runtime_version_template_validates() -> None:
    root = Path(__file__).parents[3]
    payload = json.loads(
        (root / "benchmarks/templates/agent_cli_runtime_versions.example.json").read_text()
    )

    bundle = RuntimeVersionBundle.model_validate(payload)

    assert bundle.benchmark_id == "agent-cli-local-rehearsal"
    assert set(bundle.runtimes) == set(AgentCliArm)


def test_preflight_cli_publishes_exclusively(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmarks import agent_cli_preflight

    async def resolved(*_args: object, **_kwargs: object) -> str:
        return REVISION

    monkeypatch.setattr(agent_cli_preflight, "resolve_git_revision", resolved)
    manifest = tmp_path / "manifest.json"
    config = tmp_path / "config.json"
    versions = tmp_path / "versions.json"
    output = tmp_path / "preflight.json"
    manifest.write_text(_manifest().model_dump_json(), encoding="utf-8")
    config.write_text(_config().model_dump_json(), encoding="utf-8")
    versions.write_text(_versions().model_dump_json(), encoding="utf-8")

    args = [
        "benchmark",
        "agent-cli-preflight",
        "--manifest",
        str(manifest),
        "--config",
        str(config),
        "--runtime-versions",
        str(versions),
        "--source-root",
        str(tmp_path),
        "--output",
        str(output),
        "--json",
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0
    assert json.loads(first.output)["execution_authorized"] is False
    assert second.exit_code == 1
    assert "already exists" in second.output


def test_review_template_cli_writes_null_decisions(tmp_path: Path) -> None:
    preflight = tmp_path / "preflight.json"
    evidence = tmp_path / "evidence.json"
    output = tmp_path / "reviews.json"
    preflight.write_text(_preflight().to_json(), encoding="utf-8")
    evidence.write_text(
        json.dumps(_evidence().model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-review-template",
            "--preflight",
            str(preflight),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["review_completed"] is False
    assert all(row["accepted_patch"] is None for row in payload["decisions"])


def test_finalize_cli_requires_preflight_for_bound_reviews(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preflight_path = tmp_path / "preflight.json"
    evidence_path = tmp_path / "evidence.json"
    reviews_path = tmp_path / "reviews.json"
    output_path = tmp_path / "results.json"
    evidence = _evidence()
    preflight = _preflight()
    payload = build_review_template(preflight, evidence).model_dump(mode="json")
    payload["review_completed"] = True
    for decision in payload["decisions"]:
        decision.update(
            accepted_patch=False,
            human_interventions=0,
            recovery_attempted=False,
            recovery_succeeded=False,
            reviewer_id="reviewer-1",
            review_artifact_sha256="f" * 64,
        )
    manifest_path.write_text(_manifest().model_dump_json(), encoding="utf-8")
    preflight_path.write_text(preflight.to_json(), encoding="utf-8")
    evidence_path.write_text(
        json.dumps(evidence.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    reviews_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    base_args = [
        "benchmark",
        "agent-cli-finalize",
        "--manifest",
        str(manifest_path),
        "--evidence",
        str(evidence_path),
        "--reviews",
        str(reviews_path),
        "--output",
        str(output_path),
    ]

    refused = runner.invoke(app, base_args)
    accepted = runner.invoke(
        app,
        [*base_args, "--preflight", str(preflight_path)],
    )

    assert refused.exit_code == 1
    assert "--preflight is required" in refused.output
    assert accepted.exit_code == 0
    assert output_path.exists()


def test_reviewer_policy_is_deterministic_and_normalizes_reviewer_order() -> None:
    first = _policy()
    second = _policy()

    assert first.to_json() == second.to_json()
    assert first.reviewer_ids == ("reviewer-1", "reviewer-2")
    assert len(first.policy_sha256) == 64


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (
            {
                "operator_id": "same",
                "reviewer_ids": ["same"],
                "minimum_distinct_reviewers": 1,
            },
            "operator",
        ),
        (
            {
                "operator_id": "operator",
                "reviewer_ids": ["reviewer", "reviewer"],
                "minimum_distinct_reviewers": 1,
            },
            "unique",
        ),
        (
            {
                "operator_id": "operator",
                "reviewer_ids": ["reviewer"],
                "minimum_distinct_reviewers": 2,
            },
            "minimum",
        ),
    ],
)
def test_reviewer_policy_rejects_invalid_separation(payload: dict, match: str) -> None:
    with pytest.raises((ValidationError, ValueError), match=match):
        build_reviewer_policy(
            ReviewerPolicyDeclaration.model_validate(
                {"schema_version": 1, "benchmark_id": "campaign-001", **payload}
            )
        )


def test_review_template_binds_reviewer_policy() -> None:
    template = build_review_template(
        _preflight(),
        _evidence(),
        review_policy_sha256=_policy().policy_sha256,
    )

    assert template.review_policy_sha256 == _policy().policy_sha256


def test_reviewer_policy_rejects_impossible_campaign_capacity() -> None:
    declaration = ReviewerPolicyDeclaration.model_validate(
        {
            "schema_version": 1,
            "benchmark_id": "campaign-001",
            "operator_id": "operator",
            "reviewer_ids": ["r1", "r2", "r3", "r4"],
            "minimum_distinct_reviewers": 4,
        }
    )

    with pytest.raises(ValueError, match="campaign decision count"):
        validate_reviewer_policy_capacity(
            build_reviewer_policy(declaration),
            decision_count=3,
        )


def test_reviewer_separation_accepts_allowed_distinct_reviewers() -> None:
    validate_reviewer_separation(_policy(), _completed_reviews())


@pytest.mark.parametrize(
    ("reviewer_ids", "match"),
    [
        (("operator-1", "reviewer-2", "reviewer-1"), "operator"),
        (("outsider", "reviewer-2", "reviewer-1"), "not allowed"),
        (("reviewer-1", "reviewer-1", "reviewer-1"), "distinct"),
    ],
)
def test_reviewer_separation_rejects_policy_violations(
    reviewer_ids: tuple[str, str, str],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_reviewer_separation(
            _policy(),
            _completed_reviews(reviewer_ids=reviewer_ids),
        )


def test_campaign_status_advances_deterministically_without_authorization() -> None:
    manifest = _manifest()
    preflight = _preflight()
    evidence = _evidence()
    policy, trust, reviews, attestations = _signed_attestations()
    template = build_review_template(
        preflight,
        evidence,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=trust.reviewer_trust_sha256,
    )
    results = finalize_recorded_results(
        manifest,
        evidence,
        reviews,
        review_policy=policy,
        reviewer_trust=trust,
        attestations=attestations,
    )

    statuses = [
        build_campaign_status(manifest),
        build_campaign_status(manifest, preflight=preflight),
        build_campaign_status(manifest, preflight=preflight, evidence=evidence),
        build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            review_template=template,
            review_policy=policy,
            reviewer_trust=trust,
        ),
        build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            reviews=reviews,
            review_policy=policy,
            reviewer_trust=trust,
        ),
        build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            reviews=reviews,
            review_policy=policy,
            reviewer_trust=trust,
            attestations=attestations,
        ),
        build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            reviews=reviews,
            results=results,
            review_policy=policy,
            reviewer_trust=trust,
            attestations=attestations,
        ),
    ]

    assert [status.stage for status in statuses] == [
        CampaignStage.MANIFEST_READY,
        CampaignStage.PREFLIGHT_READY,
        CampaignStage.RECORDED,
        CampaignStage.REVIEW_PENDING,
        CampaignStage.REVIEW_ATTESTATION_PENDING,
        CampaignStage.REVIEW_COMPLETE,
        CampaignStage.FINALIZED,
    ]
    assert all(status.paid_execution_authorized is False for status in statuses)
    assert statuses[-2].attestations_verified is True
    assert statuses[-1].next_action == "campaign_complete"
    assert statuses[-1].to_json() == build_campaign_status(
        manifest,
        preflight=preflight,
        evidence=evidence,
        reviews=reviews,
        results=results,
        review_policy=policy,
        reviewer_trust=trust,
        attestations=attestations,
    ).to_json()


def test_campaign_status_rejects_artifact_order_gaps() -> None:
    with pytest.raises(ValueError, match="preflight"):
        build_campaign_status(_manifest(), evidence=_evidence())


def test_campaign_status_rejects_manifest_contract_mismatch() -> None:
    changed_payload = _manifest().model_dump(mode="json")
    changed_payload["task"]["goal"] = "Different goal under the same identity."
    changed_preflight = build_campaign_preflight(
        AgentCliManifest.model_validate(changed_payload),
        _config(),
        _versions(),
        resolved_revision=REVISION,
    )

    with pytest.raises(ValueError, match="manifest fingerprint"):
        build_campaign_status(_manifest(), preflight=changed_preflight)


def test_campaign_status_rejects_evidence_estimate_mismatch() -> None:
    evidence = _evidence().model_copy(update={"estimated_max_cost_usd": 1.5})

    with pytest.raises(ValueError, match="evidence estimate"):
        build_campaign_status(_manifest(), preflight=_preflight(), evidence=evidence)


def test_campaign_status_cli_is_read_only(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    preflight = tmp_path / "preflight.json"
    evidence = tmp_path / "evidence.json"
    reviews = tmp_path / "reviews.json"
    policy = tmp_path / "policy.json"
    manifest.write_text(_manifest().model_dump_json(), encoding="utf-8")
    preflight.write_text(_preflight().to_json(), encoding="utf-8")
    evidence.write_text(
        json.dumps(_evidence().model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    reviews.write_text(_completed_reviews().model_dump_json(), encoding="utf-8")
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": "campaign-001",
                "operator_id": "operator-1",
                "reviewer_ids": ["reviewer-1", "reviewer-2"],
                "minimum_distinct_reviewers": 2,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-status",
            "--manifest",
            str(manifest),
            "--preflight",
            str(preflight),
            "--evidence",
            str(evidence),
            "--reviews",
            str(reviews),
            "--review-policy",
            str(policy),
            "--json",
        ],
    )

    after = {path: path.read_bytes() for path in tmp_path.iterdir()}
    assert result.exit_code == 0
    assert json.loads(result.output)["stage"] == "review_complete"
    assert before == after


def test_committed_review_policy_template_validates() -> None:
    root = Path(__file__).parents[3]
    payload = json.loads(
        (root / "benchmarks/templates/agent_cli_review_policy.example.json").read_text()
    )

    declaration = ReviewerPolicyDeclaration.model_validate(payload)

    assert build_reviewer_policy(declaration).benchmark_id == "agent-cli-local-rehearsal"


def test_reviewer_trust_is_deterministic_and_normalizes_key_order() -> None:
    first = build_reviewer_trust(_trust_declaration(), _policy())
    second = build_reviewer_trust(_trust_declaration(), _policy())

    assert first.to_json() == second.to_json()
    assert [key.reviewer_id for key in first.keys] == ["reviewer-1", "reviewer-2"]
    assert len(first.reviewer_trust_sha256) == 64
    assert all(len(key.public_key_sha256) == 64 for key in first.keys)


def test_reviewer_trust_rejects_unauthorized_or_missing_active_keys() -> None:
    payload = _trust_declaration().model_dump(mode="json")
    payload["keys"][0]["reviewer_id"] = "outsider"
    with pytest.raises(ValueError, match="allowed reviewer"):
        build_reviewer_trust(ReviewerTrustDeclaration.model_validate(payload), _policy())

    with pytest.raises(ValueError, match="active key"):
        build_reviewer_trust(_trust_declaration(revoke_reviewer_2=True), _policy())


def test_attestation_template_binds_exact_review_provenance_without_private_keys() -> None:
    policy, trust, reviews, _bundle = _signed_attestations()

    template = build_review_attestation_template(policy, trust, reviews)

    assert template.reviewer_trust_sha256 == trust.reviewer_trust_sha256
    assert len(template.requests) == 2
    assert {request.statement.reviewer_id for request in template.requests} == {
        "reviewer-1",
        "reviewer-2",
    }
    assert all(
        request.statement.reviews_sha256 == template.reviews_sha256
        for request in template.requests
    )
    assert "private" not in template.to_json().lower()


def test_attestation_verifier_accepts_one_active_signature_per_reviewer() -> None:
    policy, trust, reviews, bundle = _signed_attestations()

    verify_review_attestations(policy, trust, reviews, bundle)


@pytest.mark.parametrize("mutation", ["signature", "missing", "mixed_reviews"])
def test_attestation_verifier_rejects_tampering_and_incomplete_bundles(
    mutation: str,
) -> None:
    policy, trust, reviews, bundle = _signed_attestations()
    payload = bundle.model_dump(mode="json")
    if mutation == "signature":
        payload["attestations"][0]["signature_base64"] = base64.b64encode(b"x" * 64).decode()
    elif mutation == "missing":
        payload["attestations"].pop()
    else:
        payload["reviews_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="signature|attestation|reviews fingerprint"):
        verify_review_attestations(
            policy,
            trust,
            reviews,
            ReviewAttestationBundle.model_validate(payload),
        )


def test_attestation_verifier_rejects_revoked_signing_key() -> None:
    policy, _trust, _reviews, _bundle = _signed_attestations()
    revoked_trust = build_reviewer_trust(
        ReviewerTrustDeclaration.model_validate(
            {
                **_trust_declaration().model_dump(mode="json"),
                "keys": [
                    {
                        **key,
                        "status": (
                            "revoked"
                            if key["reviewer_id"] == "reviewer-2"
                            else key["status"]
                        ),
                    }
                    for key in _trust_declaration().model_dump(mode="json")["keys"]
                ],
            }
        ),
        policy,
        require_active_key_per_reviewer=False,
    )
    reviews = _completed_reviews(
        reviewer_trust_sha256=revoked_trust.reviewer_trust_sha256
    )
    template = build_review_attestation_template(policy, revoked_trust, reviews)
    private_keys = _private_keys()
    signed = tuple(
        SignedReviewAttestation(
            statement=request.statement,
            key_id=f"{request.statement.reviewer_id}-key-1",
            signature_base64=base64.b64encode(
                private_keys[request.statement.reviewer_id].sign(
                    request.statement.signing_bytes()
                )
            ).decode(),
        )
        for request in template.requests
    )
    bundle = ReviewAttestationBundle(
        schema_version=1,
        benchmark_id=reviews.benchmark_id,
        review_policy_sha256=policy.policy_sha256,
        reviewer_trust_sha256=revoked_trust.reviewer_trust_sha256,
        reviews_sha256=template.reviews_sha256,
        attestations=signed,
    )

    with pytest.raises(ValueError, match="revoked"):
        verify_review_attestations(policy, revoked_trust, reviews, bundle)


def test_trust_bound_finalization_requires_verified_attestations() -> None:
    policy, trust, reviews, attestations = _signed_attestations()

    with pytest.raises(ValueError, match="require policy, trust, and attestations"):
        finalize_recorded_results(
            _manifest(),
            _evidence(),
            reviews,
            review_policy=policy,
            reviewer_trust=trust,
        )

    results = finalize_recorded_results(
        _manifest(),
        _evidence(),
        reviews,
        review_policy=policy,
        reviewer_trust=trust,
        attestations=attestations,
    )

    assert len(results.observations) == 3


def test_trust_bound_finalize_and_status_cli_require_and_verify_bundle(
    tmp_path: Path,
) -> None:
    policy, trust, reviews, attestations = _signed_attestations()
    paths = {
        "manifest": tmp_path / "manifest.json",
        "preflight": tmp_path / "preflight.json",
        "evidence": tmp_path / "evidence.json",
        "reviews": tmp_path / "reviews.json",
        "policy": tmp_path / "policy.json",
        "trust": tmp_path / "trust.json",
        "attestations": tmp_path / "attestations.json",
        "results": tmp_path / "results.json",
    }
    paths["manifest"].write_text(_manifest().model_dump_json(), encoding="utf-8")
    paths["preflight"].write_text(_preflight().to_json(), encoding="utf-8")
    paths["evidence"].write_text(_evidence().model_dump_json(), encoding="utf-8")
    paths["reviews"].write_text(reviews.model_dump_json(), encoding="utf-8")
    paths["policy"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": policy.benchmark_id,
                "operator_id": policy.operator_id,
                "reviewer_ids": list(policy.reviewer_ids),
                "minimum_distinct_reviewers": policy.minimum_distinct_reviewers,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    paths["trust"].write_text(_trust_declaration().model_dump_json(), encoding="utf-8")
    paths["attestations"].write_text(attestations.to_json(), encoding="utf-8")
    base = [
        "benchmark",
        "agent-cli-finalize",
        "--manifest",
        str(paths["manifest"]),
        "--preflight",
        str(paths["preflight"]),
        "--evidence",
        str(paths["evidence"]),
        "--reviews",
        str(paths["reviews"]),
        "--review-policy",
        str(paths["policy"]),
        "--output",
        str(paths["results"]),
    ]

    refused = runner.invoke(app, base)
    accepted = runner.invoke(
        app,
        [
            *base,
            "--reviewer-trust",
            str(paths["trust"]),
            "--attestations",
            str(paths["attestations"]),
        ],
    )

    assert refused.exit_code == 1
    assert "--reviewer-trust is required" in refused.output
    assert accepted.exit_code == 0
    before = {path: path.read_bytes() for path in paths.values()}
    status = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-status",
            "--manifest",
            str(paths["manifest"]),
            "--preflight",
            str(paths["preflight"]),
            "--evidence",
            str(paths["evidence"]),
            "--reviews",
            str(paths["reviews"]),
            "--results",
            str(paths["results"]),
            "--review-policy",
            str(paths["policy"]),
            "--reviewer-trust",
            str(paths["trust"]),
            "--attestations",
            str(paths["attestations"]),
            "--json",
        ],
    )

    assert status.exit_code == 0
    assert json.loads(status.output)["stage"] == "finalized"
    assert json.loads(status.output)["attestations_verified"] is True
    assert before == {path: path.read_bytes() for path in paths.values()}


def test_attestation_template_cli_is_read_only(tmp_path: Path) -> None:
    policy, trust, reviews, _bundle = _signed_attestations()
    reviews_path = tmp_path / "reviews.json"
    policy_path = tmp_path / "policy.json"
    trust_path = tmp_path / "trust.json"
    output_path = tmp_path / "attestation-template.json"
    reviews_path.write_text(reviews.model_dump_json(), encoding="utf-8")
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": policy.benchmark_id,
                "operator_id": policy.operator_id,
                "reviewer_ids": list(policy.reviewer_ids),
                "minimum_distinct_reviewers": policy.minimum_distinct_reviewers,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    trust_path.write_text(_trust_declaration().model_dump_json(), encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-attestation-template",
            "--reviews",
            str(reviews_path),
            "--review-policy",
            str(policy_path),
            "--reviewer-trust",
            str(trust_path),
            "--output",
            str(output_path),
            "--json",
        ],
    )

    after_inputs = {path: path.read_bytes() for path in before}
    assert result.exit_code == 0
    assert json.loads(result.output)["attestations_completed"] is False
    assert before == after_inputs
    assert output_path.exists()


def test_committed_reviewer_trust_template_validates() -> None:
    root = Path(__file__).parents[3]
    payload = json.loads(
        (root / "benchmarks/templates/agent_cli_reviewer_trust.example.json").read_text()
    )
    policy_payload = json.loads(
        (root / "benchmarks/templates/agent_cli_review_policy.example.json").read_text()
    )
    policy = build_reviewer_policy(ReviewerPolicyDeclaration.model_validate(policy_payload))

    trust = build_reviewer_trust(ReviewerTrustDeclaration.model_validate(payload), policy)

    assert trust.benchmark_id == "agent-cli-local-rehearsal"


def test_benchmark_authority_is_deterministic_and_self_fingerprinted() -> None:
    first = build_benchmark_authority(_authority_declaration())
    second = build_benchmark_authority(_authority_declaration())

    assert first.to_json() == second.to_json()
    assert len(first.public_key_sha256) == 64
    assert len(first.authority_sha256) == 64


def test_reviewer_enrollments_verify_every_trust_key() -> None:
    authority, policy, trust, enrollments, *_rest = _anchored_artifacts()

    verify_reviewer_enrollments(authority, policy, trust, enrollments)

    assert [
        certificate.statement.key_id for certificate in enrollments.certificates
    ] == ["reviewer-1-key-1", "reviewer-2-key-1"]
    assert len(enrollments.reviewer_enrollments_sha256) == 64


def test_reviewer_enrollment_template_cli_is_private_key_free_and_read_only(
    tmp_path: Path,
) -> None:
    authority, policy, trust, *_rest = _anchored_artifacts()
    template = build_reviewer_enrollment_template(authority, policy, trust)
    policy_path = tmp_path / "policy.json"
    trust_path = tmp_path / "trust.json"
    authority_path = tmp_path / "authority.json"
    output_path = tmp_path / "enrollment-template.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": policy.benchmark_id,
                "operator_id": policy.operator_id,
                "reviewer_ids": list(policy.reviewer_ids),
                "minimum_distinct_reviewers": policy.minimum_distinct_reviewers,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    trust_path.write_text(
        _trust_declaration(
            reviewer_authority_sha256=authority.authority_sha256
        ).model_dump_json(),
        encoding="utf-8",
    )
    authority_path.write_text(_authority_declaration().model_dump_json(), encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-reviewer-enrollment-template",
            "--review-policy",
            str(policy_path),
            "--reviewer-trust",
            str(trust_path),
            "--reviewer-authority",
            str(authority_path),
            "--output",
            str(output_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == json.loads(template.to_json())
    assert len(template.requests) == 2
    assert "private" not in template.to_json().lower()
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize("mutation", ["signature", "missing", "mixed_trust"])
def test_reviewer_enrollments_reject_tampering_and_incomplete_coverage(
    mutation: str,
) -> None:
    authority, policy, trust, enrollments, *_rest = _anchored_artifacts()
    payload = enrollments.model_dump(mode="json")
    if mutation == "signature":
        payload["certificates"][0]["signature_base64"] = base64.b64encode(
            b"x" * 64
        ).decode()
    elif mutation == "missing":
        payload["certificates"].pop()
    else:
        payload["reviewer_trust_sha256"] = "f" * 64

    with pytest.raises(
        ValueError,
        match="signature|coverage|trust fingerprint|enrollment fingerprint",
    ):
        verify_reviewer_enrollments(
            authority,
            policy,
            trust,
            type(enrollments).model_validate(payload),
        )


def test_reviewer_enrollment_rejects_invalid_authority_signature() -> None:
    authority, policy, trust, enrollments, *_rest = _anchored_artifacts()
    certificates = list(enrollments.certificates)
    certificates[0] = certificates[0].model_copy(
        update={"signature_base64": base64.b64encode(b"x" * 64).decode()}
    )

    with pytest.raises(ValueError, match="enrollment signature"):
        build_reviewer_enrollment_bundle(
            authority,
            policy,
            trust,
            tuple(certificates),
        )


def test_authority_bound_finalization_requires_enrollment_certificates() -> None:
    (
        authority,
        policy,
        trust,
        enrollments,
        reviews,
        attestations,
        _results,
        _request,
        _envelope,
    ) = _anchored_artifacts()

    with pytest.raises(ValueError, match="authority and reviewer enrollments"):
        finalize_recorded_results(
            _manifest(),
            _evidence(),
            reviews,
            review_policy=policy,
            reviewer_trust=trust,
            attestations=attestations,
        )

    results = finalize_recorded_results(
        _manifest(),
        _evidence(),
        reviews,
        review_policy=policy,
        reviewer_trust=trust,
        attestations=attestations,
        reviewer_authority=authority,
        reviewer_enrollments=enrollments,
    )

    assert len(results.observations) == 3


def test_campaign_envelope_binds_every_artifact_without_authorizing_execution() -> None:
    *_, request, _envelope = _anchored_artifacts()
    second = _anchored_artifacts()[-2]

    assert request.to_json() == second.to_json()
    assert request.statement.paid_execution_authorized is False
    assert len(request.statement.results_sha256) == 64
    assert len(request.statement.reviewer_enrollments_sha256) == 64
    assert len(request.statement.attestations_sha256) == 64


def test_signed_campaign_envelope_verifies_and_rejects_tampering() -> None:
    (
        authority,
        policy,
        trust,
        enrollments,
        reviews,
        attestations,
        results,
        _request,
        envelope,
    ) = _anchored_artifacts()
    kwargs = {
        "authority": authority,
        "manifest": _manifest(),
        "preflight": _preflight(),
        "evidence": _evidence(),
        "reviews": reviews,
        "review_policy": policy,
        "reviewer_trust": trust,
        "reviewer_enrollments": enrollments,
        "attestations": attestations,
        "results": results,
    }

    verify_signed_campaign_envelope(**kwargs, envelope=envelope)
    tampered = envelope.model_copy(
        update={"signature_base64": base64.b64encode(b"x" * 64).decode()}
    )
    with pytest.raises(ValueError, match="campaign envelope signature"):
        verify_signed_campaign_envelope(**kwargs, envelope=tampered)


def test_authority_bound_campaign_waits_for_signed_envelope_before_finalized() -> None:
    (
        authority,
        policy,
        trust,
        enrollments,
        reviews,
        attestations,
        results,
        _request,
        envelope,
    ) = _anchored_artifacts()
    common = {
        "preflight": _preflight(),
        "evidence": _evidence(),
        "reviews": reviews,
        "results": results,
        "review_policy": policy,
        "reviewer_trust": trust,
        "attestations": attestations,
        "reviewer_authority": authority,
        "reviewer_enrollments": enrollments,
    }

    pending = build_campaign_status(_manifest(), **common)
    finalized = build_campaign_status(
        _manifest(),
        **common,
        campaign_envelope=envelope,
    )

    assert pending.stage is CampaignStage.CAMPAIGN_ENVELOPE_PENDING
    assert pending.next_action == "sign_campaign_envelope"
    assert finalized.stage is CampaignStage.FINALIZED
    assert finalized.campaign_envelope_verified is True
    assert finalized.paid_execution_authorized is False


def test_campaign_envelope_template_cli_preserves_all_inputs(tmp_path: Path) -> None:
    (
        authority,
        policy,
        trust,
        enrollments,
        reviews,
        attestations,
        results,
        request,
        envelope,
    ) = _anchored_artifacts()
    payloads = {
        "manifest": _manifest().model_dump_json(),
        "preflight": _preflight().to_json(),
        "evidence": _evidence().model_dump_json(),
        "reviews": reviews.model_dump_json(),
        "policy": json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": policy.benchmark_id,
                "operator_id": policy.operator_id,
                "reviewer_ids": list(policy.reviewer_ids),
                "minimum_distinct_reviewers": policy.minimum_distinct_reviewers,
            },
            sort_keys=True,
        ),
        "trust": _trust_declaration(
            reviewer_authority_sha256=authority.authority_sha256
        ).model_dump_json(),
        "authority": _authority_declaration().model_dump_json(),
        "enrollments": enrollments.to_json(),
        "attestations": attestations.to_json(),
        "results": results.model_dump_json(),
    }
    paths = {}
    for name, payload in payloads.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(payload, encoding="utf-8")
    finalized = tmp_path / "finalized.json"
    before_finalize = {path: path.read_bytes() for path in paths.values()}
    finalize_result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-finalize",
            "--manifest",
            str(paths["manifest"]),
            "--preflight",
            str(paths["preflight"]),
            "--evidence",
            str(paths["evidence"]),
            "--reviews",
            str(paths["reviews"]),
            "--review-policy",
            str(paths["policy"]),
            "--reviewer-trust",
            str(paths["trust"]),
            "--reviewer-authority",
            str(paths["authority"]),
            "--reviewer-enrollments",
            str(paths["enrollments"]),
            "--attestations",
            str(paths["attestations"]),
            "--output",
            str(finalized),
        ],
    )

    assert finalize_result.exit_code == 0
    assert json.loads(finalized.read_text()) == results.model_dump(mode="json")
    assert before_finalize == {path: path.read_bytes() for path in paths.values()}
    output = tmp_path / "campaign-envelope-template.json"
    before = {path: path.read_bytes() for path in paths.values()}
    args = ["benchmark", "agent-cli-campaign-envelope-template"]
    for name in payloads:
        option = "--review-policy" if name == "policy" else f"--{name}"
        option = "--reviewer-trust" if name == "trust" else option
        option = "--reviewer-authority" if name == "authority" else option
        option = "--reviewer-enrollments" if name == "enrollments" else option
        args.extend([option, str(paths[name])])
    args.extend(["--output", str(output), "--json"])

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert json.loads(result.output) == json.loads(request.to_json())
    assert before == {path: path.read_bytes() for path in paths.values()}
    assert output.exists()
    envelope_path = tmp_path / "campaign-envelope.json"
    envelope_path.write_text(envelope.to_json(), encoding="utf-8")
    status_before = {
        path: path.read_bytes() for path in [*paths.values(), envelope_path]
    }
    status_args = ["benchmark", "agent-cli-status"]
    for name in payloads:
        option = "--review-policy" if name == "policy" else f"--{name}"
        option = "--reviewer-trust" if name == "trust" else option
        option = "--reviewer-authority" if name == "authority" else option
        option = "--reviewer-enrollments" if name == "enrollments" else option
        status_args.extend([option, str(paths[name])])
    status_args.extend(
        ["--campaign-envelope", str(envelope_path), "--json"]
    )

    status = runner.invoke(app, status_args)

    assert status.exit_code == 0
    assert json.loads(status.output)["stage"] == "finalized"
    assert json.loads(status.output)["campaign_envelope_verified"] is True
    assert status_before == {
        path: path.read_bytes() for path in [*paths.values(), envelope_path]
    }


def test_committed_authority_and_anchored_trust_templates_validate() -> None:
    root = Path(__file__).parents[3]
    authority_declaration = BenchmarkAuthorityDeclaration.model_validate_json(
        (root / "benchmarks/templates/agent_cli_reviewer_authority.example.json").read_text()
    )
    trust_declaration = ReviewerTrustDeclaration.model_validate_json(
        (
            root
            / "benchmarks/templates/agent_cli_anchored_reviewer_trust.example.json"
        ).read_text()
    )
    policy = build_reviewer_policy(
        ReviewerPolicyDeclaration.model_validate_json(
            (root / "benchmarks/templates/agent_cli_review_policy.example.json").read_text()
        )
    )
    authority = build_benchmark_authority(authority_declaration)

    trust = build_reviewer_trust(trust_declaration, policy)

    assert trust.reviewer_authority_sha256 == authority.authority_sha256
