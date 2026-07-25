"""Tests for the recorded same-task agent CLI comparison benchmark."""

from __future__ import annotations

import json

import pytest

from benchmarks.agent_cli_comparison import (
    AgentCliManifest,
    RecordedResults,
    evaluate_recorded_results,
)


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "benchmark_id": "same-task-001",
        "task": {
            "id": "task-001",
            "goal": "Implement the same tested change",
            "workspace_revision": "abc123",
            "checks": ["unit", "ruff"],
            "handoff_assertions": ["decision", "failure"],
        },
        "arms": ["codex_cli", "claude_code", "morphic_control"],
        "repetitions": 2,
    }


def _observations() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    values = {
        "codex_cli": [
            (True, True, ["unit", "ruff"], 120.0, 0.20, 1),
            (False, False, [], 180.0, 0.10, 2),
        ],
        "claude_code": [
            (True, True, ["unit"], 90.0, 0.30, 1),
            (True, False, ["unit", "ruff"], 110.0, 0.40, 1),
        ],
        "morphic_control": [
            (True, True, ["unit", "ruff"], 105.0, 0.25, 0),
            (True, True, ["unit", "ruff"], 105.0, 0.25, 0),
        ],
    }
    for arm, trials in values.items():
        for trial, (completed, accepted, checks, elapsed, cost, interventions) in enumerate(
            trials, start=1
        ):
            rows.append(
                {
                    "arm": arm,
                    "trial": trial,
                    "completed": completed,
                    "accepted_patch": accepted,
                    "passed_checks": checks,
                    "elapsed_seconds": elapsed,
                    "cost_usd": cost,
                    "human_interventions": interventions,
                    "recovery_attempted": trial == 2,
                    "recovery_succeeded": arm != "codex_cli" and trial == 2,
                    "passed_handoff_assertions": (
                        ["decision", "failure"] if arm == "morphic_control" else ["decision"]
                    ),
                }
            )
    return {
        "schema_version": 1,
        "benchmark_id": "same-task-001",
        "task_id": "task-001",
        "observations": rows,
    }


def test_evaluate_same_task_results_without_a_composite_score() -> None:
    report = evaluate_recorded_results(
        AgentCliManifest.model_validate(_manifest()),
        RecordedResults.model_validate(_observations()),
    ).to_dict()

    assert report["benchmark_id"] == "same-task-001"
    assert report["observation_count"] == 6
    assert "overall_score" not in report
    assert report["arms"]["codex_cli"] == {
        "accepted_patch_rate": 0.5,
        "completion_rate": 0.5,
        "context_handoff_score": 0.5,
        "mean_cost_usd": 0.15,
        "mean_human_interventions": 1.5,
        "median_elapsed_seconds": 150.0,
        "recovery_rate": 0.0,
        "verification_rate": 0.5,
    }
    assert report["leaders"]["accepted_patch_rate"] == ["morphic_control"]
    assert report["leaders"]["median_elapsed_seconds"] == ["claude_code"]
    assert report["leaders"]["mean_human_interventions"] == ["morphic_control"]
    assert report["leaders"]["context_handoff_score"] == ["morphic_control"]


def test_report_json_is_deterministic_and_has_no_timestamp() -> None:
    manifest = AgentCliManifest.model_validate(_manifest())
    results = RecordedResults.model_validate(_observations())

    first = evaluate_recorded_results(manifest, results).to_json()
    second = evaluate_recorded_results(manifest, results).to_json()

    assert first == second
    assert "timestamp" not in json.loads(first)
    assert first == json.dumps(json.loads(first), ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda data: data["observations"].pop(), "missing observations"),
        (
            lambda data: data["observations"].append(dict(data["observations"][0])),
            "duplicate observation",
        ),
        (lambda data: data.update(task_id="other-task"), "task_id"),
    ],
)
def test_rejects_incomplete_duplicate_or_mismatched_results(mutate: object, match: str) -> None:
    raw = _observations()
    mutate(raw)  # type: ignore[operator]

    with pytest.raises(ValueError, match=match):
        evaluate_recorded_results(
            AgentCliManifest.model_validate(_manifest()),
            RecordedResults.model_validate(raw),
        )


def test_manifest_requires_the_three_comparison_arms() -> None:
    raw = _manifest()
    raw["arms"] = ["codex_cli", "morphic_control"]

    with pytest.raises(ValueError, match="exactly"):
        AgentCliManifest.model_validate(raw)


def test_rejects_invalid_recovery_claim() -> None:
    raw = _observations()
    raw["observations"][0]["recovery_succeeded"] = True  # type: ignore[index]

    with pytest.raises(ValueError, match="recovery_succeeded"):
        RecordedResults.model_validate(raw)


def test_rejects_non_finite_measurements() -> None:
    raw = _observations()
    raw["observations"][0]["elapsed_seconds"] = float("inf")  # type: ignore[index]

    with pytest.raises(ValueError, match="finite number"):
        RecordedResults.model_validate(raw)


def test_rejects_undeclared_checks_and_handoff_assertions() -> None:
    raw = _observations()
    raw["observations"][0]["passed_checks"] = ["not-declared"]  # type: ignore[index]

    with pytest.raises(ValueError, match="undeclared checks"):
        evaluate_recorded_results(
            AgentCliManifest.model_validate(_manifest()),
            RecordedResults.model_validate(raw),
        )

    raw = _observations()
    raw["observations"][0]["passed_handoff_assertions"] = [  # type: ignore[index]
        "not-declared"
    ]
    with pytest.raises(ValueError, match="undeclared handoff assertions"):
        evaluate_recorded_results(
            AgentCliManifest.model_validate(_manifest()),
            RecordedResults.model_validate(raw),
        )
