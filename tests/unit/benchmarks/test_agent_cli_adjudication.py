"""Tests for provider receipts and deterministic benchmark adjudication."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from benchmarks.agent_cli_adjudication import (
    AdjudicationReviews,
    RecordedEvidence,
    finalize_recorded_results,
    finalized_results_json,
)
from benchmarks.agent_cli_comparison import AgentCliManifest
from benchmarks.agent_cli_receipts import ProviderReceipt, ProviderReceiptParser
from interface.cli.main import app

runner = CliRunner()


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "benchmark_id": "adjudicate-001",
        "task": {
            "id": "task-001",
            "goal": "Implement the same change",
            "workspace_revision": "abc123",
            "checks": ["unit"],
            "handoff_assertions": ["decision"],
        },
        "arms": ["codex_cli", "claude_code", "morphic_control"],
        "repetitions": 1,
    }


def _command(*, exit_code: int = 0) -> dict[str, object]:
    return {
        "argv_sha256": "a" * 64,
        "exit_code": exit_code,
        "timed_out": False,
        "elapsed_seconds": 10.0,
        "stdout_sha256": "b" * 64,
        "stdout_bytes": 100,
        "stderr_sha256": "c" * 64,
        "stderr_bytes": 0,
    }


def _receipt(arm: str, cost: float) -> dict[str, object]:
    sources = {
        "codex_cli": "calculated_from_usage",
        "claude_code": "provider_reported",
        "morphic_control": "morphic_reported",
    }
    return {
        "provider": arm,
        "success": True,
        "model": "o4-mini" if arm == "codex_cli" else f"{arm}-model",
        "usage": {"input_tokens": 100, "output_tokens": 20},
        "cost_usd": cost,
        "cost_source": sources[arm],
        "parse_errors": 0,
    }


def _evidence() -> dict[str, object]:
    trials = []
    for arm, cost in (
        ("codex_cli", 0.000198),
        ("claude_code", 0.2),
        ("morphic_control", 0.3),
    ):
        trials.append(
            {
                "arm": arm,
                "trial": 1,
                "reserved_cost_usd": cost,
                "agent": _command(),
                "checks": {"unit": _command()},
                "handoff_assertions": {"decision": _command()},
                "receipt": _receipt(arm, cost),
                "completed": True,
                "passed_checks": ["unit"],
                "passed_handoff_assertions": ["decision"],
            }
        )
    return {
        "schema_version": 1,
        "benchmark_id": "adjudicate-001",
        "task_id": "task-001",
        "workspace_revision": "abc123",
        "estimated_max_cost_usd": 0.6,
        "authorized_cost_cap_usd": 1.0,
        "cost_collection": "normalized_receipts",
        "trials": trials,
    }


def _reviews() -> dict[str, object]:
    return {
        "schema_version": 1,
        "benchmark_id": "adjudicate-001",
        "task_id": "task-001",
        "workspace_revision": "abc123",
        "decisions": [
            {
                "arm": arm,
                "trial": 1,
                "agent_argv_sha256": "a" * 64,
                "accepted_patch": True,
                "human_interventions": index,
                "recovery_attempted": index > 0,
                "recovery_succeeded": index > 0,
                "reviewer_id": "reviewer-1",
                "review_artifact_sha256": "d" * 64,
            }
            for index, arm in enumerate(
                ("codex_cli", "claude_code", "morphic_control")
            )
        ],
    }


def test_parse_codex_receipt_calculates_cost_from_usage() -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 1000, "output_tokens": 100},
                }
            ),
        ]
    )

    receipt = ProviderReceiptParser().parse(
        arm="codex_cli",
        stdout=stdout,
        model_hint="o4-mini",
    )

    assert receipt is not None
    assert receipt.cost_usd == 0.00154
    assert receipt.cost_source == "calculated_from_usage"
    assert "thread-1" not in receipt.to_json()


def test_parse_claude_receipt_uses_provider_reported_cost() -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "done",
                    "total_cost_usd": 0.012,
                    "usage": {"input_tokens": 100, "output_tokens": 20},
                }
            ),
        ]
    )

    receipt = ProviderReceiptParser().parse(arm="claude_code", stdout=stdout)

    assert receipt is not None
    assert receipt.model == "claude-sonnet-4-6"
    assert receipt.cost_usd == 0.012
    assert receipt.cost_source == "provider_reported"
    assert "done" not in receipt.to_json()


def test_parse_morphic_receipt_requires_canonical_envelope() -> None:
    stdout = json.dumps(
        {
            "type": "morphic_benchmark_receipt",
            "success": True,
            "model": "o4-mini",
            "cost_usd": 0.02,
            "usage": {"input_tokens": 120, "output_tokens": 30},
        }
    )

    receipt = ProviderReceiptParser().parse(arm="morphic_control", stdout=stdout)

    assert receipt is not None
    assert receipt.cost_usd == 0.02
    assert receipt.provider == "morphic_control"
    assert ProviderReceiptParser().parse(arm="morphic_control", stdout="not-json") is None


def test_receipt_rejects_wrong_source_negative_usage_and_tampered_codex_cost() -> None:
    base = {
        "provider": "codex_cli",
        "success": True,
        "model": "o4-mini",
        "usage": {"input_tokens": 100, "output_tokens": 20},
        "cost_usd": 0.000198,
        "cost_source": "calculated_from_usage",
    }
    with pytest.raises(ValueError, match="cost_source"):
        ProviderReceipt.model_validate({**base, "cost_source": "provider_reported"})
    with pytest.raises(ValueError, match="non-negative"):
        ProviderReceipt.model_validate({**base, "usage": {"input_tokens": -1}})
    with pytest.raises(ValueError, match="does not match usage"):
        ProviderReceipt.model_validate({**base, "cost_usd": 1.0})


def test_finalize_joins_machine_evidence_and_reviews() -> None:
    results = finalize_recorded_results(
        AgentCliManifest.model_validate(_manifest()),
        RecordedEvidence.model_validate(_evidence()),
        AdjudicationReviews.model_validate(_reviews()),
    )
    payload = results.model_dump(mode="json")

    assert len(payload["observations"]) == 3
    assert payload["observations"][0] == {
        "arm": "codex_cli",
        "trial": 1,
        "completed": True,
        "accepted_patch": True,
        "passed_checks": ["unit"],
        "elapsed_seconds": 10.0,
        "cost_usd": 0.000198,
        "human_interventions": 0,
        "recovery_attempted": False,
        "recovery_succeeded": False,
        "passed_handoff_assertions": ["decision"],
    }


def test_finalized_json_is_deterministic() -> None:
    args = (
        AgentCliManifest.model_validate(_manifest()),
        RecordedEvidence.model_validate(_evidence()),
        AdjudicationReviews.model_validate(_reviews()),
    )

    first = finalized_results_json(finalize_recorded_results(*args))
    second = finalized_results_json(finalize_recorded_results(*args))

    assert first == second
    assert "timestamp" not in json.loads(first)
    assert first == json.dumps(json.loads(first), ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda evidence, reviews: evidence["trials"][0].update(receipt=None), "receipt"),
        (
            lambda evidence, reviews: reviews["decisions"][0].update(
                agent_argv_sha256="e" * 64
            ),
            "fingerprint",
        ),
        (lambda evidence, reviews: reviews["decisions"].pop(), "missing review"),
        (
            lambda evidence, reviews: evidence.update(authorized_cost_cap_usd=0.5),
            "authorized cost cap",
        ),
        (
            lambda evidence, reviews: evidence["trials"][0]["receipt"].update(
                parse_errors=1
            ),
            "parse errors",
        ),
        (
            lambda evidence, reviews: evidence.update(
                cost_collection="pending_adjudication"
            ),
            "not normalized_receipts",
        ),
    ],
)
def test_finalize_rejects_incomplete_or_inconsistent_campaign(
    mutate: object,
    match: str,
) -> None:
    evidence = _evidence()
    reviews = _reviews()
    mutate(evidence, reviews)  # type: ignore[operator]

    with pytest.raises(ValueError, match=match):
        finalize_recorded_results(
            AgentCliManifest.model_validate(_manifest()),
            RecordedEvidence.model_validate(evidence),
            AdjudicationReviews.model_validate(reviews),
        )


def test_finalize_rejects_acceptance_when_provider_failed() -> None:
    evidence = _evidence()
    evidence["trials"][0]["receipt"]["success"] = False  # type: ignore[index]

    with pytest.raises(ValueError, match="accepted_patch requires completed"):
        finalize_recorded_results(
            AgentCliManifest.model_validate(_manifest()),
            RecordedEvidence.model_validate(evidence),
            AdjudicationReviews.model_validate(_reviews()),
        )


def test_finalize_rejects_successful_recovery_when_trial_still_failed() -> None:
    evidence = _evidence()
    reviews = _reviews()
    evidence["trials"][0]["receipt"]["success"] = False  # type: ignore[index]
    reviews["decisions"][0].update(  # type: ignore[index]
        accepted_patch=False,
        recovery_attempted=True,
        recovery_succeeded=True,
    )

    with pytest.raises(ValueError, match="recovery_succeeded requires completed"):
        finalize_recorded_results(
            AgentCliManifest.model_validate(_manifest()),
            RecordedEvidence.model_validate(evidence),
            AdjudicationReviews.model_validate(reviews),
        )


def test_cli_finalizes_without_starting_an_agent(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    evidence = tmp_path / "evidence.json"
    reviews = tmp_path / "reviews.json"
    output = tmp_path / "results.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    evidence.write_text(json.dumps(_evidence()), encoding="utf-8")
    reviews.write_text(json.dumps(_reviews()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-finalize",
            "--manifest",
            str(manifest),
            "--evidence",
            str(evidence),
            "--reviews",
            str(reviews),
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["observations"][0]["arm"] == "codex_cli"
    assert len(json.loads(output.read_text(encoding="utf-8"))["observations"]) == 3

    second = runner.invoke(
        app,
        [
            "benchmark",
            "agent-cli-finalize",
            "--manifest",
            str(manifest),
            "--evidence",
            str(evidence),
            "--reviews",
            str(reviews),
            "--output",
            str(output),
        ],
    )
    assert second.exit_code == 1
    assert "already exists" in second.output
