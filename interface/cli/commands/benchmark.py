"""CLI commands for benchmarks — Sprint 7.6."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import typer

from interface.cli.formatters import console

benchmark_app = typer.Typer(no_args_is_help=True)
_AGENT_CLI_MANIFEST_OPTION = typer.Option(
    ...,
    "--manifest",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Same-task benchmark manifest JSON.",
)
_AGENT_CLI_RESULTS_OPTION = typer.Option(
    ...,
    "--results",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Recorded trial observations JSON.",
)
_AGENT_CLI_JSON_OPTION = typer.Option(False, "--json", help="Emit deterministic JSON.")
_RECORDER_CONFIG_OPTION = typer.Option(
    ...,
    "--config",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Recorder command configuration JSON.",
)
_RECORDER_WORKTREE_OPTION = typer.Option(None, "--worktree-root", help="Isolated worktree root.")
_RECORDER_SOURCE_OPTION = typer.Option(None, "--source-root", help="Source Git workspace.")
_RECORDER_EVIDENCE_OPTION = typer.Option(None, "--evidence", help="Evidence JSON output path.")
_RECORDER_EXECUTE_OPTION = typer.Option(False, "--execute", help="Execute the recorded plan.")
_RECORDER_ACK_OPTION = typer.Option(
    False,
    "--acknowledge-paid",
    help="Acknowledge that configured commands may incur charges.",
)
_RECORDER_COST_CAP_OPTION = typer.Option(
    None,
    "--cost-cap-usd",
    help="Explicit cap that must cover the configured maximum estimate.",
)
_FINALIZE_EVIDENCE_OPTION = typer.Option(
    ...,
    "--evidence",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Normalized recorder evidence JSON.",
)
_FINALIZE_REVIEWS_OPTION = typer.Option(
    ...,
    "--reviews",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Independent adjudication reviews JSON.",
)
_FINALIZE_OUTPUT_OPTION = typer.Option(None, "--output", help="Final Phase 40 results path.")
_REHEARSAL_OUTPUT_OPTION = typer.Option(..., "--output-dir", help="New rehearsal bundle directory.")
_REHEARSAL_REVISION_OPTION = typer.Option("HEAD", "--revision", help="Git revision to pin.")
_PREFLIGHT_VERSIONS_OPTION = typer.Option(
    ...,
    "--runtime-versions",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Declared agent CLI versions JSON; no version command is executed.",
)
_PREFLIGHT_OUTPUT_OPTION = typer.Option(..., "--output", help="New preflight JSON path.")
_PREFLIGHT_INPUT_OPTION = typer.Option(
    ...,
    "--preflight",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Campaign preflight JSON.",
)
_OPTIONAL_PREFLIGHT_INPUT = typer.Option(
    None,
    "--preflight",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional campaign preflight binding.",
)
_OPTIONAL_REVIEW_POLICY_INPUT = typer.Option(
    None,
    "--review-policy",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional operator/reviewer separation policy declaration.",
)
_OPTIONAL_REVIEWER_TRUST_INPUT = typer.Option(
    None,
    "--reviewer-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional reviewer Ed25519 public-key trust declaration.",
)
_OPTIONAL_ATTESTATIONS_INPUT = typer.Option(
    None,
    "--attestations",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional signed reviewer attestation bundle.",
)
_STATUS_EVIDENCE_OPTION = typer.Option(
    None,
    "--evidence",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional normalized evidence JSON.",
)
_STATUS_REVIEWS_OPTION = typer.Option(
    None,
    "--reviews",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional pending template or completed reviews JSON.",
)
_STATUS_RESULTS_OPTION = typer.Option(
    None,
    "--results",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional finalized results JSON.",
)


def _write_new_evidence(path: Path, payload: str) -> None:
    """Publish evidence atomically without replacing an existing path."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.link(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _get_container() -> Any:
    from interface.cli._utils import _get_container as _gc

    return _gc()


def _run(coro: Any) -> Any:
    from interface.cli._utils import _run as _r

    return _r(coro)


@benchmark_app.command("run")
def run_all() -> None:
    """Run all benchmarks (context continuity + dedup accuracy)."""
    from benchmarks.runner import run_all as _run_all

    container = _get_container()
    adapters = container._context_adapters
    result = _run(_run_all(adapters))

    # Context continuity
    if result.context_continuity:
        console.print("\n[bold]Context Continuity Benchmark[/bold]")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Engine", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Decisions", justify="right")
        table.add_column("Artifacts", justify="right")
        table.add_column("Blockers", justify="right")
        table.add_column("Length", justify="right")

        for s in result.context_continuity.adapter_scores:
            score_style = "green" if s.score >= 0.85 else "yellow" if s.score >= 0.5 else "red"
            table.add_row(
                s.engine,
                f"[{score_style}]{s.score:.0%}[/{score_style}]",
                f"{s.decisions_found}/{s.decisions_injected}",
                f"{s.artifacts_found}/{s.artifacts_injected}",
                f"{s.blockers_found}/{s.blockers_injected}",
                str(s.context_length),
            )
        console.print(table)
        overall = result.context_continuity.overall_score
        style = "green" if overall >= 0.85 else "yellow"
        console.print(f"  Overall: [{style}]{overall:.0%}[/{style}]")

    # Dedup accuracy
    if result.dedup_accuracy:
        console.print("\n[bold]Memory Dedup Benchmark[/bold]")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Scenario", style="cyan")
        table.add_column("Dedup Rate", justify="right")
        table.add_column("Raw", justify="right")
        table.add_column("Unique", justify="right")

        for s in result.dedup_accuracy.scores:
            rate_style = "green" if s.dedup_rate >= 0.5 else "yellow"
            table.add_row(
                s.scenario,
                f"[{rate_style}]{s.dedup_rate:.0%}[/{rate_style}]",
                str(s.total_raw),
                str(s.deduped_count),
            )
        console.print(table)
        accuracy = result.dedup_accuracy.overall_accuracy
        style = "green" if accuracy >= 0.5 else "yellow"
        console.print(f"  Overall: [{style}]{accuracy:.0%}[/{style}]")

    # Errors
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  [red]• {err}[/red]")

    # Summary
    console.print(f"\n[bold]Overall Score: {result.overall_score:.0%}[/bold]")
    if result.overall_score >= 0.85:
        console.print("[green]✓ Benchmark threshold (85%) passed[/green]")
    else:
        console.print("[yellow]⚠ Below 85% threshold[/yellow]")


@benchmark_app.command("continuity")
def run_continuity() -> None:
    """Run context continuity benchmark only."""
    from benchmarks.context_continuity import run_benchmark

    container = _get_container()
    adapters = container._context_adapters
    result = run_benchmark(adapters)

    console.print(f"\n[bold]Context Continuity: {result.overall_score:.0%}[/bold]")
    for s in result.adapter_scores:
        style = "green" if s.score >= 0.85 else "yellow" if s.score >= 0.5 else "red"
        console.print(f"  {s.engine:<15} [{style}]{s.score:.0%}[/{style}]")


@benchmark_app.command("dedup")
def run_dedup() -> None:
    """Run memory dedup accuracy benchmark only."""
    from benchmarks.dedup_accuracy import run_benchmark

    container = _get_container()
    adapters = container._context_adapters
    result = _run(run_benchmark(adapters))

    console.print(f"\n[bold]Dedup Accuracy: {result.overall_accuracy:.0%}[/bold]")
    for s in result.scores:
        style = "green" if s.dedup_rate >= 0.5 else "yellow"
        console.print(f"  {s.scenario:<25} [{style}]{s.dedup_rate:.0%}[/{style}]")


@benchmark_app.command("agent-cli")
def compare_agent_clis(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    results_path: Path = _AGENT_CLI_RESULTS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Compare recorded Codex, Claude Code, and Morphic-controlled trials."""
    from benchmarks.agent_cli_comparison import (
        AgentCliManifest,
        RecordedResults,
        evaluate_recorded_results,
    )

    try:
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        results = RecordedResults.model_validate_json(results_path.read_text(encoding="utf-8"))
        report = evaluate_recorded_results(manifest, results)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid agent CLI benchmark input: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        console.print(report.to_json(), markup=False)
        return

    from rich.table import Table

    table = Table(title=f"Agent CLI Same-task Benchmark: {report.benchmark_id}")
    table.add_column("Arm", style="cyan")
    table.add_column("Complete", justify="right")
    table.add_column("Accepted", justify="right")
    table.add_column("Verified", justify="right")
    table.add_column("Median sec", justify="right")
    table.add_column("Mean USD", justify="right")
    table.add_column("Interventions", justify="right")
    table.add_column("Recovery", justify="right")
    table.add_column("Handoff", justify="right")
    for arm, metrics in report.arms.items():
        recovery = "n/a" if metrics.recovery_rate is None else f"{metrics.recovery_rate:.0%}"
        table.add_row(
            arm,
            f"{metrics.completion_rate:.0%}",
            f"{metrics.accepted_patch_rate:.0%}",
            f"{metrics.verification_rate:.0%}",
            f"{metrics.median_elapsed_seconds:.1f}",
            f"{metrics.mean_cost_usd:.4f}",
            f"{metrics.mean_human_interventions:.2f}",
            recovery,
            f"{metrics.context_handoff_score:.0%}",
        )
    console.print(table)
    console.print("[bold]Metric leaders[/bold]")
    for metric, leaders in report.leaders.items():
        names = ", ".join(leaders) if leaders else "n/a"
        console.print(f"  {metric}: {names}")
    console.print("[dim]No composite score; metric leaders are reported independently.[/dim]")


@benchmark_app.command("agent-cli-record")
def record_agent_cli_trials(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    config_path: Path = _RECORDER_CONFIG_OPTION,
    worktree_root: Path | None = _RECORDER_WORKTREE_OPTION,
    source_root: Path | None = _RECORDER_SOURCE_OPTION,
    evidence_path: Path | None = _RECORDER_EVIDENCE_OPTION,
    execute: bool = _RECORDER_EXECUTE_OPTION,
    acknowledge_paid: bool = _RECORDER_ACK_OPTION,
    cost_cap_usd: float | None = _RECORDER_COST_CAP_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Plan or explicitly execute isolated same-task CLI trials."""
    from benchmarks.agent_cli_comparison import AgentCliManifest
    from benchmarks.agent_cli_recorder import (
        AgentCliRecorderConfig,
        AgentCliTrialRecorder,
        GitWorktreeManager,
        LocalCommandRunner,
        build_recording_plan,
        validate_execution_consent,
    )

    try:
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        config = AgentCliRecorderConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
        plan = build_recording_plan(manifest, config)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid agent CLI recorder input: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if not execute:
        if as_json:
            typer.echo(plan.to_json())
        else:
            console.print(
                f"Recorder plan trials={plan.trial_count} "
                f"estimated_max=${plan.estimated_max_cost_usd:.6f} execute=false"
            )
        return

    try:
        validate_execution_consent(
            plan,
            acknowledged_paid=acknowledge_paid,
            cost_cap_usd=cost_cap_usd,
        )
        if worktree_root is None:
            raise ValueError("--worktree-root is required with --execute")
        if evidence_path is None:
            raise ValueError("--evidence is required with --execute")
        if not evidence_path.parent.exists():
            raise ValueError("evidence output parent must already exist")
        if evidence_path.exists():
            raise ValueError("evidence output already exists")
    except ValueError as exc:
        console.print(f"[red]Recorder execution refused: {exc}[/red]")
        raise typer.Exit(code=2) from None

    recorder = AgentCliTrialRecorder(
        worktree_manager=GitWorktreeManager(),
        command_runner=LocalCommandRunner(),
    )
    try:
        evidence = _run(
            recorder.record(
                manifest=manifest,
                config=config,
                source_root=(source_root or Path.cwd()).resolve(),
                worktree_root=worktree_root.resolve(),
                acknowledged_paid=acknowledge_paid,
                cost_cap_usd=cost_cap_usd,
            )
        )
        _write_new_evidence(evidence_path, evidence.to_json())
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Recorder execution failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(evidence.to_json())
    else:
        console.print(f"Recorded {len(evidence.trials)} isolated trials to {evidence_path}")


@benchmark_app.command("agent-cli-finalize")
def finalize_agent_cli_trials(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    evidence_path: Path = _FINALIZE_EVIDENCE_OPTION,
    reviews_path: Path = _FINALIZE_REVIEWS_OPTION,
    preflight_path: Path | None = _OPTIONAL_PREFLIGHT_INPUT,
    review_policy_path: Path | None = _OPTIONAL_REVIEW_POLICY_INPUT,
    reviewer_trust_path: Path | None = _OPTIONAL_REVIEWER_TRUST_INPUT,
    attestations_path: Path | None = _OPTIONAL_ATTESTATIONS_INPUT,
    output_path: Path | None = _FINALIZE_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Join normalized receipts and reviews into Phase 40 observations."""
    from benchmarks.agent_cli_adjudication import (
        AdjudicationReviews,
        RecordedEvidence,
        finalize_recorded_results,
        finalized_results_json,
    )
    from benchmarks.agent_cli_comparison import AgentCliManifest

    try:
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        evidence = RecordedEvidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
        reviews = AdjudicationReviews.model_validate_json(reviews_path.read_text(encoding="utf-8"))
        review_policy = None
        reviewer_trust = None
        attestations = None
        if reviews.preflight_sha256 is not None and preflight_path is None:
            raise ValueError("--preflight is required for a preflight-bound review")
        if preflight_path is not None:
            from benchmarks.agent_cli_preflight import (
                CampaignPreflight,
                validate_review_bindings,
            )

            preflight = CampaignPreflight.model_validate_json(
                preflight_path.read_text(encoding="utf-8")
            )
            validate_review_bindings(preflight, evidence, reviews)
        if reviews.review_policy_sha256 is not None and review_policy_path is None:
            raise ValueError("--review-policy is required for a policy-bound review")
        if review_policy_path is not None:
            from benchmarks.agent_cli_review_policy import (
                ReviewerPolicyDeclaration,
                build_reviewer_policy,
                validate_reviewer_separation,
            )

            declaration = ReviewerPolicyDeclaration.model_validate_json(
                review_policy_path.read_text(encoding="utf-8")
            )
            review_policy = build_reviewer_policy(declaration)
            validate_reviewer_separation(review_policy, reviews)
        if reviews.reviewer_trust_sha256 is not None and reviewer_trust_path is None:
            raise ValueError("--reviewer-trust is required for a trust-bound review")
        if reviews.reviewer_trust_sha256 is not None and attestations_path is None:
            raise ValueError("--attestations is required for a trust-bound review")
        if reviewer_trust_path is not None:
            if review_policy is None:
                raise ValueError("--review-policy is required with --reviewer-trust")
            from benchmarks.agent_cli_attestation import (
                ReviewerTrustDeclaration,
                build_reviewer_trust,
            )

            trust_declaration = ReviewerTrustDeclaration.model_validate_json(
                reviewer_trust_path.read_text(encoding="utf-8")
            )
            reviewer_trust = build_reviewer_trust(trust_declaration, review_policy)
        if attestations_path is not None:
            from benchmarks.agent_cli_attestation import ReviewAttestationBundle

            attestations = ReviewAttestationBundle.model_validate_json(
                attestations_path.read_text(encoding="utf-8")
            )
        results = finalize_recorded_results(
            manifest,
            evidence,
            reviews,
            review_policy=review_policy,
            reviewer_trust=reviewer_trust,
            attestations=attestations,
        )
        payload = finalized_results_json(results)
        if output_path is not None:
            if not output_path.parent.exists():
                raise ValueError("output parent must already exist")
            if output_path.exists():
                raise ValueError("output already exists")
            _write_new_evidence(output_path, payload)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI adjudication failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(payload)
    else:
        console.print(f"Finalized {len(results.observations)} benchmark observations")


@benchmark_app.command("agent-cli-preflight")
def preflight_agent_cli_campaign(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    config_path: Path = _RECORDER_CONFIG_OPTION,
    runtime_versions_path: Path = _PREFLIGHT_VERSIONS_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    source_root: Path | None = _RECORDER_SOURCE_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Validate one pinned campaign without launching an agent or authorizing execution."""
    from benchmarks.agent_cli_comparison import AgentCliManifest
    from benchmarks.agent_cli_preflight import (
        RuntimeVersionBundle,
        build_campaign_preflight,
        resolve_git_revision,
    )
    from benchmarks.agent_cli_recorder import AgentCliRecorderConfig

    try:
        manifest = AgentCliManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        config = AgentCliRecorderConfig.model_validate_json(
            config_path.read_text(encoding="utf-8")
        )
        versions = RuntimeVersionBundle.model_validate_json(
            runtime_versions_path.read_text(encoding="utf-8")
        )
        if not output_path.parent.exists():
            raise ValueError("preflight output parent must already exist")
        if output_path.exists():
            raise ValueError("preflight output already exists")
        source = (source_root or Path.cwd()).resolve()
        resolved = _run(resolve_git_revision(source, manifest.task.workspace_revision))
        report = build_campaign_preflight(
            manifest,
            config,
            versions,
            resolved_revision=resolved,
        )
        _write_new_evidence(output_path, report.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI preflight failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(report.to_json())
    else:
        console.print(
            f"Preflight ready trials={report.trial_count} "
            f"estimated_max=${report.estimated_max_cost_usd:.6f} "
            "execution_authorized=false"
        )


@benchmark_app.command("agent-cli-review-template")
def create_agent_cli_review_template(
    preflight_path: Path = _PREFLIGHT_INPUT_OPTION,
    evidence_path: Path = _FINALIZE_EVIDENCE_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    review_policy_path: Path | None = _OPTIONAL_REVIEW_POLICY_INPUT,
    reviewer_trust_path: Path | None = _OPTIONAL_REVIEWER_TRUST_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Generate null independent review decisions bound to exact campaign evidence."""
    from benchmarks.agent_cli_adjudication import RecordedEvidence
    from benchmarks.agent_cli_preflight import CampaignPreflight, build_review_template

    try:
        preflight = CampaignPreflight.model_validate_json(
            preflight_path.read_text(encoding="utf-8")
        )
        evidence = RecordedEvidence.model_validate_json(
            evidence_path.read_text(encoding="utf-8")
        )
        review_policy_sha256 = None
        reviewer_trust_sha256 = None
        review_policy = None
        if review_policy_path is not None:
            from benchmarks.agent_cli_review_policy import (
                ReviewerPolicyDeclaration,
                build_reviewer_policy,
                validate_reviewer_policy_capacity,
            )

            declaration = ReviewerPolicyDeclaration.model_validate_json(
                review_policy_path.read_text(encoding="utf-8")
            )
            review_policy = build_reviewer_policy(declaration)
            if review_policy.benchmark_id != preflight.benchmark_id:
                raise ValueError("review policy benchmark_id does not match preflight")
            validate_reviewer_policy_capacity(
                review_policy,
                decision_count=len(evidence.trials),
            )
            review_policy_sha256 = review_policy.policy_sha256
        if reviewer_trust_path is not None:
            if review_policy is None:
                raise ValueError("--review-policy is required with --reviewer-trust")
            from benchmarks.agent_cli_attestation import (
                ReviewerTrustDeclaration,
                build_reviewer_trust,
            )

            trust_declaration = ReviewerTrustDeclaration.model_validate_json(
                reviewer_trust_path.read_text(encoding="utf-8")
            )
            reviewer_trust = build_reviewer_trust(trust_declaration, review_policy)
            reviewer_trust_sha256 = reviewer_trust.reviewer_trust_sha256
        if not output_path.parent.exists():
            raise ValueError("review template output parent must already exist")
        if output_path.exists():
            raise ValueError("review template output already exists")
        template = build_review_template(
            preflight,
            evidence,
            review_policy_sha256=review_policy_sha256,
            reviewer_trust_sha256=reviewer_trust_sha256,
        )
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI review template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print(f"Created {len(template.decisions)} bound review decisions")


@benchmark_app.command("agent-cli-attestation-template")
def create_agent_cli_attestation_template(
    reviews_path: Path = _FINALIZE_REVIEWS_OPTION,
    review_policy_path: Path = _OPTIONAL_REVIEW_POLICY_INPUT,
    reviewer_trust_path: Path = _OPTIONAL_REVIEWER_TRUST_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create canonical reviewer signing payloads without reading private keys."""
    from benchmarks.agent_cli_adjudication import AdjudicationReviews
    from benchmarks.agent_cli_attestation import (
        ReviewerTrustDeclaration,
        build_review_attestation_template,
        build_reviewer_trust,
    )
    from benchmarks.agent_cli_review_policy import (
        ReviewerPolicyDeclaration,
        build_reviewer_policy,
    )

    try:
        if review_policy_path is None or reviewer_trust_path is None:
            raise ValueError("--review-policy and --reviewer-trust are required")
        reviews = AdjudicationReviews.model_validate_json(
            reviews_path.read_text(encoding="utf-8")
        )
        policy = build_reviewer_policy(
            ReviewerPolicyDeclaration.model_validate_json(
                review_policy_path.read_text(encoding="utf-8")
            )
        )
        trust = build_reviewer_trust(
            ReviewerTrustDeclaration.model_validate_json(
                reviewer_trust_path.read_text(encoding="utf-8")
            ),
            policy,
        )
        template = build_review_attestation_template(policy, trust, reviews)
        if not output_path.parent.exists():
            raise ValueError("attestation template output parent must already exist")
        if output_path.exists():
            raise ValueError("attestation template output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI attestation template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print(f"Created {len(template.requests)} reviewer signing requests")


@benchmark_app.command("agent-cli-status")
def show_agent_cli_campaign_status(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    preflight_path: Path | None = _OPTIONAL_PREFLIGHT_INPUT,
    evidence_path: Path | None = _STATUS_EVIDENCE_OPTION,
    reviews_path: Path | None = _STATUS_REVIEWS_OPTION,
    results_path: Path | None = _STATUS_RESULTS_OPTION,
    review_policy_path: Path | None = _OPTIONAL_REVIEW_POLICY_INPUT,
    reviewer_trust_path: Path | None = _OPTIONAL_REVIEWER_TRUST_INPUT,
    attestations_path: Path | None = _OPTIONAL_ATTESTATIONS_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Validate and report campaign lifecycle artifacts without executing commands."""
    from benchmarks.agent_cli_adjudication import AdjudicationReviews, RecordedEvidence
    from benchmarks.agent_cli_campaign import build_campaign_status
    from benchmarks.agent_cli_comparison import AgentCliManifest, RecordedResults
    from benchmarks.agent_cli_preflight import CampaignPreflight, ReviewTemplate
    from benchmarks.agent_cli_review_policy import (
        ReviewerPolicyDeclaration,
        build_reviewer_policy,
    )

    try:
        manifest = AgentCliManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        preflight = (
            CampaignPreflight.model_validate_json(
                preflight_path.read_text(encoding="utf-8")
            )
            if preflight_path is not None
            else None
        )
        evidence = (
            RecordedEvidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
            if evidence_path is not None
            else None
        )
        review_template = None
        reviews = None
        if reviews_path is not None:
            review_payload = json.loads(reviews_path.read_text(encoding="utf-8"))
            if not isinstance(review_payload, dict):
                raise ValueError("reviews JSON must be an object")
            if review_payload.get("review_completed") is False:
                review_template = ReviewTemplate.model_validate(review_payload)
            else:
                reviews = AdjudicationReviews.model_validate(review_payload)
        results = (
            RecordedResults.model_validate_json(results_path.read_text(encoding="utf-8"))
            if results_path is not None
            else None
        )
        review_policy = None
        reviewer_trust = None
        attestations = None
        if review_policy_path is not None:
            declaration = ReviewerPolicyDeclaration.model_validate_json(
                review_policy_path.read_text(encoding="utf-8")
            )
            review_policy = build_reviewer_policy(declaration)
        if reviewer_trust_path is not None:
            if review_policy is None:
                raise ValueError("--review-policy is required with --reviewer-trust")
            from benchmarks.agent_cli_attestation import (
                ReviewerTrustDeclaration,
                build_reviewer_trust,
            )

            reviewer_trust = build_reviewer_trust(
                ReviewerTrustDeclaration.model_validate_json(
                    reviewer_trust_path.read_text(encoding="utf-8")
                ),
                review_policy,
            )
        if attestations_path is not None:
            from benchmarks.agent_cli_attestation import ReviewAttestationBundle

            attestations = ReviewAttestationBundle.model_validate_json(
                attestations_path.read_text(encoding="utf-8")
            )
        status = build_campaign_status(
            manifest,
            preflight=preflight,
            evidence=evidence,
            review_template=review_template,
            reviews=reviews,
            results=results,
            review_policy=review_policy,
            reviewer_trust=reviewer_trust,
            attestations=attestations,
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI campaign status failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(status.to_json())
    else:
        console.print(
            f"Campaign stage={status.stage.value} next={status.next_action} "
            "paid_execution_authorized=false"
        )


@benchmark_app.command("agent-cli-rehearse")
def rehearse_agent_cli_trials(
    output_dir: Path = _REHEARSAL_OUTPUT_OPTION,
    source_root: Path | None = _RECORDER_SOURCE_OPTION,
    worktree_root: Path | None = _RECORDER_WORKTREE_OPTION,
    revision: str = _REHEARSAL_REVISION_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Run the complete three-arm evidence pipeline with internal zero-cost fixtures."""
    from benchmarks.agent_cli_rehearsal import (
        publish_local_rehearsal,
        resolve_git_revision,
        run_local_rehearsal,
    )

    source = (source_root or Path.cwd()).resolve()
    output = output_dir.resolve()
    if output.exists():
        console.print(f"[red]Rehearsal output already exists: {output}[/red]")
        raise typer.Exit(code=1)
    if not output.parent.exists():
        console.print("[red]Rehearsal output parent must already exist[/red]")
        raise typer.Exit(code=1)

    temporary_root: tempfile.TemporaryDirectory[str] | None = None
    if worktree_root is None:
        temporary_root = tempfile.TemporaryDirectory(prefix="morphic-agent-cli-rehearsal-")
        isolated_root = Path(temporary_root.name)
    else:
        isolated_root = worktree_root.resolve()
    try:
        pinned_revision = _run(resolve_git_revision(source, revision))
        artifacts = _run(
            run_local_rehearsal(
                source_root=source,
                worktree_root=isolated_root,
                workspace_revision=pinned_revision,
                python_executable=sys.executable,
            )
        )
        publish_local_rehearsal(output, artifacts)
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI rehearsal failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    finally:
        if temporary_root is not None:
            temporary_root.cleanup()

    if as_json:
        typer.echo(
            json.dumps(
                artifacts.results.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        console.print(
            f"Rehearsed {len(artifacts.results.observations)} local trials "
            f"at $0.000000 into {output}"
        )
