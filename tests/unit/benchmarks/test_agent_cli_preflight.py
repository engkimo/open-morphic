"""Tests for agent CLI campaign preflight and review template binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    finalize_recorded_results,
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


def _completed_reviews(*, reviewer_ids: tuple[str, str, str] | None = None):
    evidence = _evidence()
    policy = _policy()
    payload = build_review_template(
        _preflight(),
        evidence,
        review_policy_sha256=policy.policy_sha256,
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
    policy = _policy()
    template = build_review_template(
        preflight,
        evidence,
        review_policy_sha256=policy.policy_sha256,
    )
    reviews = _completed_reviews()
    results = finalize_recorded_results(manifest, evidence, reviews)

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
        ),
        build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            reviews=reviews,
            review_policy=policy,
        ),
        build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            reviews=reviews,
            results=results,
            review_policy=policy,
        ),
    ]

    assert [status.stage for status in statuses] == list(CampaignStage)
    assert all(status.paid_execution_authorized is False for status in statuses)
    assert statuses[-1].next_action == "campaign_complete"
    assert statuses[-1].to_json() == build_campaign_status(
        manifest,
        preflight=preflight,
        evidence=evidence,
        reviews=reviews,
        results=results,
        review_policy=policy,
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
