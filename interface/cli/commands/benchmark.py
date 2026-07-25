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
_CHECKPOINT_TLS_REVOCATIONS_OPTION = typer.Option(
    None, "--revocations", exists=True, file_okay=True, dir_okay=False, readable=True
)
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
_OPTIONAL_REVIEWER_AUTHORITY_INPUT = typer.Option(
    None,
    "--reviewer-authority",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional organization benchmark authority declaration.",
)
_OPTIONAL_REVIEWER_ENROLLMENTS_INPUT = typer.Option(
    None,
    "--reviewer-enrollments",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional authority-signed reviewer enrollment bundle.",
)
_OPTIONAL_CAMPAIGN_ENVELOPE_INPUT = typer.Option(
    None,
    "--campaign-envelope",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional authority-signed finalized campaign envelope.",
)
_OPTIONAL_AUTHORITY_ROOT_LEDGER_INPUT = typer.Option(
    None,
    "--authority-root-ledger",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional signed authority-root ledger.",
)
_OPTIONAL_TRANSPARENCY_PROOF_INPUT = typer.Option(
    None,
    "--transparency-proof",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional campaign-envelope transparency inclusion proof.",
)
_OPTIONAL_TRANSPARENCY_CONSISTENCY_INPUT = typer.Option(
    None,
    "--transparency-consistency-proof",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional compact Merkle consistency proof.",
)
_OPTIONAL_TRANSPARENCY_WITNESS_TRUST_INPUT = typer.Option(
    None,
    "--transparency-witness-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional transparency witness trust declaration.",
)
_OPTIONAL_WITNESS_CHECKPOINT_INPUT = typer.Option(
    None,
    "--witness-checkpoint",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional signed witness checkpoint bundle.",
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
_AUTHORITY_ROTATION_GENERATION_OPTION = typer.Option(..., "--generation", min=2)
_AUTHORITY_PREDECESSOR_OPTION = typer.Option(
    ...,
    "--predecessor",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_AUTHORITY_SUCCESSOR_OPTION = typer.Option(
    ...,
    "--successor",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_AUTHORITY_GENERATIONS_OPTION = typer.Option(
    ...,
    "--generations",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="JSON object containing generations and optional revocations.",
)
_TRANSPARENCY_LOG_ID_OPTION = typer.Option(..., "--log-id")
_TRANSPARENCY_ENTRIES_OPTION = typer.Option(
    ...,
    "--entries",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="JSON array of transparency log entries.",
)
_TRANSPARENCY_LOG_INPUT = typer.Option(
    ...,
    "--log",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_AUTHORITY_ROOT_LEDGER_INPUT = typer.Option(
    ...,
    "--authority-root-ledger",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_TRANSPARENCY_TREE_HEAD_INPUT = typer.Option(
    ...,
    "--tree-head",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_TRANSPARENCY_LEAF_INDEX_OPTION = typer.Option(..., "--leaf-index", min=0)
_TRANSPARENCY_CURRENT_LOG_INPUT = typer.Option(
    ...,
    "--current-log",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_TRANSPARENCY_PREVIOUS_TREE_HEAD_INPUT = typer.Option(
    ...,
    "--previous-tree-head",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_TRANSPARENCY_CURRENT_TREE_HEAD_INPUT = typer.Option(
    ...,
    "--current-tree-head",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_WITNESS_TRUST_DECLARATION_INPUT = typer.Option(
    ...,
    "--declaration",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_WITNESS_TRUST_INPUT = typer.Option(
    ...,
    "--witness-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_TRANSPARENCY_CONSISTENCY_INPUT = typer.Option(
    ...,
    "--consistency-proof",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_REGISTRY_OPTION = typer.Option(
    ...,
    "--registry",
    help="Checkpoint registry JSONL path.",
)
_CHECKPOINT_REGISTRY_ID_OPTION = typer.Option(..., "--registry-id")
_CHECKPOINT_PEER_TRUST_INPUT = typer.Option(
    ...,
    "--peer-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_SOURCE_PEER_OPTION = typer.Option(..., "--source-peer-id")
_CHECKPOINT_SEQUENCE_OPTION = typer.Option(
    None,
    "--sequence",
    min=0,
    help="Registry sequence to export; defaults to the latest record.",
)
_WITNESS_CHECKPOINT_INPUT = typer.Option(
    ...,
    "--witness-checkpoint",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_PACKET_INPUT = typer.Option(
    ...,
    "--packet",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_RANGE_BUNDLE_INPUT = typer.Option(
    ...,
    "--range-bundle",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_START_SEQUENCE_OPTION = typer.Option(
    0,
    "--start-sequence",
    min=0,
)
_CHECKPOINT_MAX_RECORDS_OPTION = typer.Option(
    100,
    "--max-records",
    min=1,
    max=1000,
)
_CHECKPOINT_ACKNOWLEDGING_PEER_OPTION = typer.Option(
    ...,
    "--acknowledging-peer-id",
)
_CHECKPOINT_ACKNOWLEDGEMENT_INPUT = typer.Option(
    ...,
    "--acknowledgement",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_CURSOR_LEDGER_OPTION = typer.Option(
    ...,
    "--cursor-ledger",
    help="Peer acknowledgement cursor JSONL path.",
)
_CHECKPOINT_PREDECESSOR_PEER_TRUST_INPUT = typer.Option(
    ...,
    "--predecessor-peer-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_SUCCESSOR_PEER_TRUST_INPUT = typer.Option(
    ...,
    "--successor-peer-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_PEER_TRUST_GENERATIONS_INPUT = typer.Option(
    ...,
    "--generations",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT = typer.Option(
    None,
    "--peer-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT = typer.Option(
    None,
    "--peer-trust-ledger",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_PEER_TRUST_LEDGER_INPUT = typer.Option(
    ...,
    "--peer-trust-ledger",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)
_CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT = typer.Option(
    ...,
    "--descriptor",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Mode 0600 loopback gossip descriptor.",
)
_CHECKPOINT_GOSSIP_DESCRIPTOR_OUTPUT = typer.Option(
    ...,
    "--descriptor",
    help="New mode 0600 loopback gossip descriptor path.",
)
_CHECKPOINT_GOSSIP_BUNDLES_INPUT = typer.Option(
    ...,
    "--range-bundles",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="JSON object containing pre-signed range bundles.",
)
_CHECKPOINT_GOSSIP_MAX_REQUESTS_OPTION = typer.Option(
    64,
    "--max-requests",
    min=1,
    max=1024,
    help="Authenticated requests accepted before deterministic shutdown.",
)
_CHECKPOINT_GOSSIP_LIFETIME_OPTION = typer.Option(
    300.0,
    "--lifetime-seconds",
    min=1.0,
    max=3600.0,
    help="Maximum listener lifetime without deterministic shutdown.",
)
_CHECKPOINT_TLS_CERTIFICATE_INPUT = typer.Option(
    ...,
    "--certificate",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Active TLS leaf certificate PEM.",
)
_CHECKPOINT_TLS_PRIVATE_KEY_INPUT = typer.Option(
    ...,
    "--private-key",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="TLS private key with owner-only permissions.",
)
_CHECKPOINT_TLS_CA_INPUT = typer.Option(
    ...,
    "--certificate-authority",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="CA bundle used for mutual certificate verification.",
)
_CHECKPOINT_TLS_TRUST_INPUT = typer.Option(
    ...,
    "--tls-trust",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Peer-signed TLS trust JSON.",
)
_CHECKPOINT_TLS_ENROLLMENTS_INPUT = typer.Option(
    ...,
    "--enrollments",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="JSON object containing signed TLS enrollments.",
)
_CHECKPOINT_TLS_TEMPLATE_INPUT = typer.Option(
    ...,
    "--template",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Private-key-free TLS enrollment template JSON.",
)
_CHECKPOINT_TLS_REVOCATION_TEMPLATE_INPUT = typer.Option(
    ..., "--revocation-template", exists=True, file_okay=True, dir_okay=False, readable=True
)
_CHECKPOINT_TLS_PEER_TRUST_INPUT = typer.Option(
    ..., "--peer-trust", exists=True, file_okay=True, dir_okay=False, readable=True
)
_CHECKPOINT_TLS_KEY_ID_OPTION = typer.Option(
    ...,
    "--key-id",
    help="Eligible peer identity key ID used for the detached signature.",
)
_CHECKPOINT_TLS_SIGNATURE_OPTION = typer.Option(
    ...,
    "--signature-base64",
    help="Detached Ed25519 signature over the template signing payload.",
)
_CHECKPOINT_TLS_PREDECESSOR_INPUT = typer.Option(
    None,
    "--predecessor",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Required predecessor enrollment for generation greater than one.",
)
_CHECKPOINT_TLS_BIND_HOST_OPTION = typer.Option(
    ...,
    "--bind-host",
    help="Explicit bind IP.",
)
_CHECKPOINT_TLS_ADVERTISED_HOST_OPTION = typer.Option(
    ...,
    "--advertised-host",
    help="Explicit client-visible IP.",
)
_CHECKPOINT_TLS_ALLOWED_CLIENTS_OPTION = typer.Option(
    ...,
    "--allow-client-address",
    help="Allowed client IP; repeat for each address.",
)
_CHECKPOINT_TLS_CLIENT_PEER_OPTION = typer.Option(
    ...,
    "--client-peer-id",
    help="Enrolled client peer identity.",
)
_CHECKPOINT_TLS_SERVER_HOSTNAME_OPTION = typer.Option(
    ...,
    "--server-hostname",
    help="DNS name that must match the server certificate SAN.",
)
_CHECKPOINT_TLS_ALLOWED_SERVERS_OPTION = typer.Option(
    ...,
    "--allow-server-address",
    help="Allowed server IP; repeat for each address.",
)
_CHECKPOINT_GOSSIP_SYNC_AUDIT_OPTION = typer.Option(
    ...,
    "--sync-audit",
    help="Durable checkpoint gossip sync audit JSONL path.",
)
_CHECKPOINT_GOSSIP_SYNC_ROUNDS_OPTION = typer.Option(
    16,
    "--max-rounds",
    min=1,
    max=100,
)
_CHECKPOINT_GOSSIP_SYNC_ATTEMPTS_OPTION = typer.Option(
    3,
    "--max-attempts",
    min=1,
    max=10,
    help="Attempts per status or range request.",
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
    reviewer_authority_path: Path | None = _OPTIONAL_REVIEWER_AUTHORITY_INPUT,
    reviewer_enrollments_path: Path | None = _OPTIONAL_REVIEWER_ENROLLMENTS_INPUT,
    authority_root_ledger_path: Path | None = _OPTIONAL_AUTHORITY_ROOT_LEDGER_INPUT,
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
        reviewer_authority = None
        reviewer_enrollments = None
        authority_root_ledger = None
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
        if (
            reviewer_trust is not None
            and reviewer_trust.reviewer_authority_sha256 is not None
            and reviewer_authority_path is None
        ):
            raise ValueError("--reviewer-authority is required for authority-bound trust")
        if (
            reviewer_trust is not None
            and reviewer_trust.reviewer_authority_sha256 is not None
            and reviewer_enrollments_path is None
        ):
            raise ValueError("--reviewer-enrollments is required for authority-bound trust")
        if attestations_path is not None:
            from benchmarks.agent_cli_attestation import ReviewAttestationBundle

            attestations = ReviewAttestationBundle.model_validate_json(
                attestations_path.read_text(encoding="utf-8")
            )
        if reviewer_authority_path is not None:
            from benchmarks.agent_cli_authority import (
                BenchmarkAuthorityDeclaration,
                build_benchmark_authority,
            )

            reviewer_authority = build_benchmark_authority(
                BenchmarkAuthorityDeclaration.model_validate_json(
                    reviewer_authority_path.read_text(encoding="utf-8")
                )
            )
        if reviewer_enrollments_path is not None:
            from benchmarks.agent_cli_authority import ReviewerEnrollmentBundle

            reviewer_enrollments = ReviewerEnrollmentBundle.model_validate_json(
                reviewer_enrollments_path.read_text(encoding="utf-8")
            )
        if authority_root_ledger_path is not None:
            from benchmarks.agent_cli_transparency import SignedAuthorityRootLedger

            authority_root_ledger = SignedAuthorityRootLedger.model_validate_json(
                authority_root_ledger_path.read_text(encoding="utf-8")
            )
        results = finalize_recorded_results(
            manifest,
            evidence,
            reviews,
            review_policy=review_policy,
            reviewer_trust=reviewer_trust,
            attestations=attestations,
            reviewer_authority=reviewer_authority,
            reviewer_enrollments=reviewer_enrollments,
            authority_root_ledger=authority_root_ledger,
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
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        config = AgentCliRecorderConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
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
        evidence = RecordedEvidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
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
        reviews = AdjudicationReviews.model_validate_json(reviews_path.read_text(encoding="utf-8"))
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


@benchmark_app.command("agent-cli-reviewer-enrollment-template")
def create_agent_cli_reviewer_enrollment_template(
    review_policy_path: Path = _OPTIONAL_REVIEW_POLICY_INPUT,
    reviewer_trust_path: Path = _OPTIONAL_REVIEWER_TRUST_INPUT,
    reviewer_authority_path: Path = _OPTIONAL_REVIEWER_AUTHORITY_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create authority signing payloads for reviewer keys without private keys."""
    from benchmarks.agent_cli_attestation import (
        ReviewerTrustDeclaration,
        build_reviewer_trust,
    )
    from benchmarks.agent_cli_authority import (
        BenchmarkAuthorityDeclaration,
        build_benchmark_authority,
        build_reviewer_enrollment_template,
    )
    from benchmarks.agent_cli_review_policy import (
        ReviewerPolicyDeclaration,
        build_reviewer_policy,
    )

    try:
        if (
            review_policy_path is None
            or reviewer_trust_path is None
            or reviewer_authority_path is None
        ):
            raise ValueError(
                "--review-policy, --reviewer-trust, and --reviewer-authority are required"
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
        authority = build_benchmark_authority(
            BenchmarkAuthorityDeclaration.model_validate_json(
                reviewer_authority_path.read_text(encoding="utf-8")
            )
        )
        template = build_reviewer_enrollment_template(authority, policy, trust)
        if not output_path.parent.exists():
            raise ValueError("reviewer enrollment output parent must already exist")
        if output_path.exists():
            raise ValueError("reviewer enrollment output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI reviewer enrollment template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print(f"Created {len(template.requests)} authority enrollment requests")


@benchmark_app.command("agent-cli-authority-rotation-template")
def create_agent_cli_authority_rotation_template(
    generation: int = _AUTHORITY_ROTATION_GENERATION_OPTION,
    predecessor_path: Path = _AUTHORITY_PREDECESSOR_OPTION,
    successor_path: Path = _AUTHORITY_SUCCESSOR_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create a predecessor-root signing payload without reading private keys."""
    from benchmarks.agent_cli_authority import (
        BenchmarkAuthorityDeclaration,
        build_benchmark_authority,
    )
    from benchmarks.agent_cli_transparency import build_authority_rotation_request

    try:
        predecessor = build_benchmark_authority(
            BenchmarkAuthorityDeclaration.model_validate_json(
                predecessor_path.read_text(encoding="utf-8")
            )
        )
        successor = build_benchmark_authority(
            BenchmarkAuthorityDeclaration.model_validate_json(
                successor_path.read_text(encoding="utf-8")
            )
        )
        request = build_authority_rotation_request(
            generation=generation,
            predecessor=predecessor,
            successor=successor,
        )
        if not output_path.parent.exists():
            raise ValueError("authority rotation output parent must already exist")
        if output_path.exists():
            raise ValueError("authority rotation output already exists")
        _write_new_evidence(output_path, request.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI authority rotation template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(request.to_json())
    else:
        console.print(f"Created authority rotation request for generation {generation}")


@benchmark_app.command("agent-cli-authority-root-ledger-template")
def create_agent_cli_authority_root_ledger_template(
    generations_path: Path = _AUTHORITY_GENERATIONS_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify a rotation chain and create the active-root ledger signing payload."""
    from benchmarks.agent_cli_transparency import (
        AuthorityRootGeneration,
        build_authority_root_ledger_request,
    )

    try:
        payload = json.loads(generations_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("authority root generations JSON must be an object")
        generations_payload = payload.get("generations")
        if not isinstance(generations_payload, list):
            raise ValueError("authority root generations must be a JSON array")
        revocations = payload.get("revoked_authority_sha256", [])
        if not isinstance(revocations, list) or not all(
            isinstance(value, str) for value in revocations
        ):
            raise ValueError("authority root revocations must be a string array")
        request = build_authority_root_ledger_request(
            tuple(AuthorityRootGeneration.model_validate(item) for item in generations_payload),
            revoked_authority_sha256=tuple(revocations),
        )
        if not output_path.parent.exists():
            raise ValueError("authority root ledger output parent must already exist")
        if output_path.exists():
            raise ValueError("authority root ledger output already exists")
        _write_new_evidence(output_path, request.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI authority root ledger failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(request.to_json())
    else:
        console.print("Created active-root ledger signing request")


@benchmark_app.command("agent-cli-transparency-log")
def create_agent_cli_transparency_log(
    log_id: str = _TRANSPARENCY_LOG_ID_OPTION,
    entries_path: Path = _TRANSPARENCY_ENTRIES_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Build a complete deterministic Merkle transparency log offline."""
    from benchmarks.agent_cli_transparency import (
        TransparencyLogEntry,
        build_transparency_log,
    )

    try:
        payload = json.loads(entries_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("transparency entries JSON must be an array")
        log = build_transparency_log(
            log_id,
            tuple(TransparencyLogEntry.model_validate(item) for item in payload),
        )
        if not output_path.parent.exists():
            raise ValueError("transparency log output parent must already exist")
        if output_path.exists():
            raise ValueError("transparency log output already exists")
        _write_new_evidence(output_path, log.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI transparency log failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(log.to_json())
    else:
        console.print(f"Created transparency log tree_size={log.tree_size}")


@benchmark_app.command("agent-cli-transparency-tree-head-template")
def create_agent_cli_transparency_tree_head_template(
    log_path: Path = _TRANSPARENCY_LOG_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create an active-root signing payload for one Merkle tree head."""
    from benchmarks.agent_cli_transparency import (
        SignedAuthorityRootLedger,
        TransparencyLog,
        build_transparency_tree_head_request,
    )

    try:
        log = TransparencyLog.model_validate_json(log_path.read_text(encoding="utf-8"))
        ledger = SignedAuthorityRootLedger.model_validate_json(
            authority_root_ledger_path.read_text(encoding="utf-8")
        )
        request = build_transparency_tree_head_request(log, ledger)
        if not output_path.parent.exists():
            raise ValueError("transparency tree head output parent must already exist")
        if output_path.exists():
            raise ValueError("transparency tree head output already exists")
        _write_new_evidence(output_path, request.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI transparency tree head failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(request.to_json())
    else:
        console.print("Created transparency tree-head signing request")


@benchmark_app.command("agent-cli-transparency-proof")
def create_agent_cli_transparency_proof(
    log_path: Path = _TRANSPARENCY_LOG_INPUT,
    tree_head_path: Path = _TRANSPARENCY_TREE_HEAD_INPUT,
    leaf_index: int = _TRANSPARENCY_LEAF_INDEX_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Build an inclusion proof for one entry under a signed tree head."""
    from benchmarks.agent_cli_transparency import (
        SignedTransparencyTreeHead,
        TransparencyLog,
        build_transparency_inclusion_proof,
    )

    try:
        log = TransparencyLog.model_validate_json(log_path.read_text(encoding="utf-8"))
        tree_head = SignedTransparencyTreeHead.model_validate_json(
            tree_head_path.read_text(encoding="utf-8")
        )
        proof = build_transparency_inclusion_proof(
            log,
            leaf_index=leaf_index,
            tree_head=tree_head,
        )
        if not output_path.parent.exists():
            raise ValueError("transparency proof output parent must already exist")
        if output_path.exists():
            raise ValueError("transparency proof output already exists")
        _write_new_evidence(output_path, proof.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI transparency proof failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(proof.to_json())
    else:
        console.print(f"Created transparency proof for leaf {leaf_index}")


@benchmark_app.command("agent-cli-transparency-consistency-proof")
def create_agent_cli_transparency_consistency_proof(
    current_log_path: Path = _TRANSPARENCY_CURRENT_LOG_INPUT,
    previous_tree_head_path: Path = _TRANSPARENCY_PREVIOUS_TREE_HEAD_INPUT,
    current_tree_head_path: Path = _TRANSPARENCY_CURRENT_TREE_HEAD_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Build a compact append-only proof between two signed tree heads."""
    from benchmarks.agent_cli_transparency import (
        SignedAuthorityRootLedger,
        SignedTransparencyTreeHead,
        TransparencyLog,
        build_transparency_consistency_proof,
    )

    try:
        current_log = TransparencyLog.model_validate_json(
            current_log_path.read_text(encoding="utf-8")
        )
        previous_tree_head = SignedTransparencyTreeHead.model_validate_json(
            previous_tree_head_path.read_text(encoding="utf-8")
        )
        current_tree_head = SignedTransparencyTreeHead.model_validate_json(
            current_tree_head_path.read_text(encoding="utf-8")
        )
        ledger = SignedAuthorityRootLedger.model_validate_json(
            authority_root_ledger_path.read_text(encoding="utf-8")
        )
        proof = build_transparency_consistency_proof(
            current_log,
            previous_tree_head=previous_tree_head,
            current_tree_head=current_tree_head,
            authority_root_ledger=ledger,
        )
        if not output_path.parent.exists():
            raise ValueError("consistency proof output parent must already exist")
        if output_path.exists():
            raise ValueError("consistency proof output already exists")
        _write_new_evidence(output_path, proof.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI consistency proof failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(proof.to_json())
    else:
        console.print(
            "Created compact consistency proof "
            f"{proof.previous_tree_head.statement.tree_size}->"
            f"{proof.current_tree_head.statement.tree_size}"
        )


@benchmark_app.command("agent-cli-witness-trust")
def create_agent_cli_witness_trust(
    declaration_path: Path = _WITNESS_TRUST_DECLARATION_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Normalize an intersecting transparency-witness quorum declaration."""
    from benchmarks.agent_cli_witness import (
        TransparencyWitnessTrustDeclaration,
        build_transparency_witness_trust,
    )

    try:
        trust = build_transparency_witness_trust(
            TransparencyWitnessTrustDeclaration.model_validate_json(
                declaration_path.read_text(encoding="utf-8")
            )
        )
        if not output_path.parent.exists():
            raise ValueError("witness trust output parent must already exist")
        if output_path.exists():
            raise ValueError("witness trust output already exists")
        _write_new_evidence(output_path, trust.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI witness trust failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(trust.to_json())
    else:
        console.print(
            f"Created witness trust minimum_distinct_witnesses={trust.minimum_distinct_witnesses}"
        )


@benchmark_app.command("agent-cli-witness-checkpoint-template")
def create_agent_cli_witness_checkpoint_template(
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    consistency_proof_path: Path = _TRANSPARENCY_CONSISTENCY_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create private-key-free signing requests for a witness checkpoint."""
    from benchmarks.agent_cli_transparency import (
        SignedAuthorityRootLedger,
        TransparencyConsistencyProof,
    )
    from benchmarks.agent_cli_witness import (
        TransparencyWitnessTrust,
        build_witness_checkpoint_template,
    )

    try:
        trust = TransparencyWitnessTrust.model_validate_json(
            witness_trust_path.read_text(encoding="utf-8")
        )
        proof = TransparencyConsistencyProof.model_validate_json(
            consistency_proof_path.read_text(encoding="utf-8")
        )
        ledger = SignedAuthorityRootLedger.model_validate_json(
            authority_root_ledger_path.read_text(encoding="utf-8")
        )
        template = build_witness_checkpoint_template(trust, proof, ledger)
        if not output_path.parent.exists():
            raise ValueError("witness checkpoint output parent must already exist")
        if output_path.exists():
            raise ValueError("witness checkpoint output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI witness checkpoint failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print(f"Created {len(template.requests)} witness signing requests")


@benchmark_app.command("agent-cli-checkpoint-peer-trust")
def create_agent_cli_checkpoint_peer_trust(
    declaration_path: Path = _WITNESS_TRUST_DECLARATION_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Normalize public keys trusted to exchange checkpoint records."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerTrustDeclaration,
        build_checkpoint_peer_trust,
    )

    try:
        trust = build_checkpoint_peer_trust(
            CheckpointPeerTrustDeclaration.model_validate_json(
                declaration_path.read_text(encoding="utf-8")
            )
        )
        if not output_path.parent.exists():
            raise ValueError("checkpoint peer trust output parent must already exist")
        if output_path.exists():
            raise ValueError("checkpoint peer trust output already exists")
        _write_new_evidence(output_path, trust.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint peer trust failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(trust.to_json())
    else:
        console.print(f"Created checkpoint peer trust with {len(trust.keys)} keys")


@benchmark_app.command("agent-cli-checkpoint-peer-tls-enrollment-template")
def create_agent_cli_checkpoint_peer_tls_enrollment_template(
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    peer_id: str = typer.Option(..., "--peer-id", help="Peer identity to enroll."),
    generation: int = typer.Option(
        ...,
        "--generation",
        min=1,
        help="Monotonic TLS enrollment generation.",
    ),
    predecessor_path: Path | None = _CHECKPOINT_TLS_PREDECESSOR_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create a private-key-free peer-signed TLS enrollment request."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsEnrollment,
        build_checkpoint_peer_tls_enrollment_template,
    )

    try:
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        predecessor = (
            CheckpointPeerTlsEnrollment.model_validate_json(
                predecessor_path.read_text(encoding="utf-8")
            )
            if predecessor_path is not None
            else None
        )
        template = build_checkpoint_peer_tls_enrollment_template(
            certificate_path.read_bytes(),
            peer_trust,
            peer_id=peer_id,
            generation=generation,
            predecessor=predecessor,
        )
        if not output_path.parent.exists():
            raise ValueError("TLS enrollment output parent must already exist")
        if output_path.exists():
            raise ValueError("TLS enrollment output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI TLS enrollment template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print(
            f"Created TLS enrollment signing request peer={peer_id} generation={generation}"
        )


@benchmark_app.command("agent-cli-checkpoint-peer-tls-enrollment")
def create_agent_cli_checkpoint_peer_tls_enrollment(
    template_path: Path = _CHECKPOINT_TLS_TEMPLATE_INPUT,
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    key_id: str = _CHECKPOINT_TLS_KEY_ID_OPTION,
    signature_base64: str = _CHECKPOINT_TLS_SIGNATURE_OPTION,
    predecessor_path: Path | None = _CHECKPOINT_TLS_PREDECESSOR_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify an external identity signature and finalize one TLS enrollment."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsEnrollment,
        CheckpointPeerTlsEnrollmentTemplate,
        build_signed_checkpoint_peer_tls_enrollment,
    )

    try:
        template = CheckpointPeerTlsEnrollmentTemplate.model_validate_json(
            template_path.read_text(encoding="utf-8")
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        predecessor = (
            CheckpointPeerTlsEnrollment.model_validate_json(
                predecessor_path.read_text(encoding="utf-8")
            )
            if predecessor_path is not None
            else None
        )
        enrollment = build_signed_checkpoint_peer_tls_enrollment(
            template,
            certificate_path.read_bytes(),
            peer_trust,
            key_id=key_id,
            signature_base64=signature_base64,
            predecessor=predecessor,
        )
        if not output_path.parent.exists():
            raise ValueError("TLS enrollment output parent must already exist")
        if output_path.exists():
            raise ValueError("TLS enrollment output already exists")
        _write_new_evidence(output_path, enrollment.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI TLS enrollment failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(enrollment.to_json())
    else:
        console.print(
            "Verified TLS enrollment "
            f"peer={enrollment.statement.peer_id} "
            f"generation={enrollment.statement.generation}"
        )


@benchmark_app.command("agent-cli-checkpoint-peer-tls-revocation-template")
def create_agent_cli_checkpoint_peer_tls_revocation_template(
    tls_trust_path: Path = _CHECKPOINT_TLS_TRUST_INPUT,
    peer_trust_path: Path = _CHECKPOINT_TLS_PEER_TRUST_INPUT,
    peer_id: str = typer.Option(..., "--peer-id"),
    generation: int = typer.Option(..., "--generation", min=1),
    reason: str = typer.Option(..., "--reason"),
    revoked_at: str = typer.Option(..., "--revoked-at"),
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create a private-key-free signed TLS revocation request."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsTrust,
        build_checkpoint_peer_tls_revocation_template,
    )

    try:
        tls_trust = CheckpointPeerTlsTrust.model_validate_json(
            tls_trust_path.read_text(encoding="utf-8")
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        template = build_checkpoint_peer_tls_revocation_template(
            tls_trust,
            peer_trust,
            peer_id=peer_id,
            generation=generation,
            reason=reason,
            revoked_at=revoked_at,
        )
        if output_path.exists():
            raise ValueError("TLS revocation template output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI TLS revocation template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    typer.echo(template.to_json()) if as_json else console.print("Created TLS revocation template")


@benchmark_app.command("agent-cli-checkpoint-peer-tls-revocation")
def create_agent_cli_checkpoint_peer_tls_revocation(
    template_path: Path = _CHECKPOINT_TLS_REVOCATION_TEMPLATE_INPUT,
    peer_trust_path: Path = _CHECKPOINT_TLS_PEER_TRUST_INPUT,
    key_id: str = _CHECKPOINT_TLS_KEY_ID_OPTION,
    signature_base64: str = _CHECKPOINT_TLS_SIGNATURE_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify a peer signature and finalize a TLS revocation artifact."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsRevocationTemplate,
        build_signed_checkpoint_peer_tls_revocation,
    )

    try:
        template = CheckpointPeerTlsRevocationTemplate.model_validate_json(
            template_path.read_text(encoding="utf-8")
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        revocation = build_signed_checkpoint_peer_tls_revocation(
            template, peer_trust, key_id=key_id, signature_base64=signature_base64
        )
        if output_path.exists():
            raise ValueError("TLS revocation output already exists")
        _write_new_evidence(output_path, revocation.model_dump_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI TLS revocation failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    typer.echo(revocation.model_dump_json()) if as_json else console.print(
        "Verified TLS revocation"
    )


@benchmark_app.command("agent-cli-checkpoint-peer-tls-trust")
def create_agent_cli_checkpoint_peer_tls_trust(
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    enrollments_path: Path = _CHECKPOINT_TLS_ENROLLMENTS_INPUT,
    revocations_path: Path | None = _CHECKPOINT_TLS_REVOCATIONS_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify enrollment chains and publish active per-peer TLS pins."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsEnrollment,
        CheckpointPeerTlsRevocation,
        build_checkpoint_peer_tls_trust,
    )

    try:
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        payload = json.loads(enrollments_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("enrollments"), list):
            raise ValueError("TLS enrollments JSON must contain an enrollments array")
        revocations: tuple[CheckpointPeerTlsRevocation, ...] = ()
        if revocations_path is not None:
            revocation_payload = json.loads(revocations_path.read_text(encoding="utf-8"))
            if not isinstance(revocation_payload, dict) or not isinstance(
                revocation_payload.get("revocations"), list
            ):
                raise ValueError("TLS revocations JSON must contain a revocations array")
            revocations = tuple(
                CheckpointPeerTlsRevocation.model_validate(item)
                for item in revocation_payload["revocations"]
            )
        trust = build_checkpoint_peer_tls_trust(
            peer_trust,
            tuple(
                CheckpointPeerTlsEnrollment.model_validate(item) for item in payload["enrollments"]
            ),
            revocations,
        )
        if not output_path.parent.exists():
            raise ValueError("TLS trust output parent must already exist")
        if output_path.exists():
            raise ValueError("TLS trust output already exists")
        _write_new_evidence(output_path, trust.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI TLS trust failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(trust.to_json())
    else:
        console.print(
            "Created checkpoint TLS trust "
            f"peers={len(trust.peer_ids())} enrollments={len(trust.enrollments)}"
        )


@benchmark_app.command("agent-cli-checkpoint-peer-trust-rotation-template")
def create_agent_cli_checkpoint_peer_trust_rotation_template(
    predecessor_path: Path = _CHECKPOINT_PREDECESSOR_PEER_TRUST_INPUT,
    successor_path: Path = _CHECKPOINT_SUCCESSOR_PEER_TRUST_INPUT,
    generation: int = _AUTHORITY_ROTATION_GENERATION_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create strict-majority predecessor-peer rollover signing requests."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_peer_trust_ledger import (
        build_checkpoint_peer_trust_rotation_template,
    )

    try:
        predecessor = CheckpointPeerTrust.model_validate_json(
            predecessor_path.read_text(encoding="utf-8")
        )
        successor = CheckpointPeerTrust.model_validate_json(
            successor_path.read_text(encoding="utf-8")
        )
        template = build_checkpoint_peer_trust_rotation_template(
            predecessor,
            successor,
            generation=generation,
        )
        if not output_path.parent.exists():
            raise ValueError("peer trust rotation output parent must already exist")
        if output_path.exists():
            raise ValueError("peer trust rotation output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI peer trust rotation failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print(
            "Created peer trust rotation requests "
            f"generation={generation} quorum="
            f"{template.minimum_distinct_peer_signatures}"
        )


@benchmark_app.command("agent-cli-checkpoint-peer-trust-ledger")
def create_agent_cli_checkpoint_peer_trust_ledger(
    generations_path: Path = _CHECKPOINT_PEER_TRUST_GENERATIONS_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify and publish a complete peer-trust generation ledger."""
    from benchmarks.agent_cli_peer_trust_ledger import (
        CheckpointPeerTrustGeneration,
        build_checkpoint_peer_trust_ledger,
    )

    try:
        payload = json.loads(generations_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("peer trust generations JSON must be an object")
        generations_payload = payload.get("generations")
        if not isinstance(generations_payload, list):
            raise ValueError("peer trust generations must be a JSON array")
        ledger = build_checkpoint_peer_trust_ledger(
            tuple(
                CheckpointPeerTrustGeneration.model_validate(item) for item in generations_payload
            )
        )
        if not output_path.parent.exists():
            raise ValueError("peer trust ledger output parent must already exist")
        if output_path.exists():
            raise ValueError("peer trust ledger output already exists")
        _write_new_evidence(output_path, ledger.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI peer trust ledger failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(ledger.to_json())
    else:
        console.print(f"Created peer trust ledger active_generation={ledger.active_generation}")


def _load_checkpoint_registry_dependencies(
    witness_trust_path: Path,
    authority_root_ledger_path: Path,
) -> tuple[Any, Any]:
    from benchmarks.agent_cli_transparency import SignedAuthorityRootLedger
    from benchmarks.agent_cli_witness import TransparencyWitnessTrust

    witness_trust = TransparencyWitnessTrust.model_validate_json(
        witness_trust_path.read_text(encoding="utf-8")
    )
    ledger = SignedAuthorityRootLedger.model_validate_json(
        authority_root_ledger_path.read_text(encoding="utf-8")
    )
    return witness_trust, ledger


@benchmark_app.command("agent-cli-checkpoint-registry-status")
def show_agent_cli_checkpoint_registry_status(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Replay and verify a local registry without changing it."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointRegistryStore

    try:
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        snapshot = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).replay(witness_trust, ledger)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint registry status failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(snapshot.to_json())
    else:
        console.print(
            "Verified checkpoint registry "
            f"records={snapshot.record_count} tree_size={snapshot.current_tree_size}"
        )


@benchmark_app.command("agent-cli-checkpoint-registry-store")
def store_agent_cli_checkpoint_registry_record(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    consistency_proof_path: Path = _TRANSPARENCY_CONSISTENCY_INPUT,
    witness_checkpoint_path: Path = _WITNESS_CHECKPOINT_INPUT,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify and durably append one witnessed checkpoint."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointRegistryStore
    from benchmarks.agent_cli_transparency import TransparencyConsistencyProof
    from benchmarks.agent_cli_witness import SignedWitnessCheckpoint

    try:
        if not registry_path.parent.exists():
            raise ValueError("checkpoint registry parent must already exist")
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        proof = TransparencyConsistencyProof.model_validate_json(
            consistency_proof_path.read_text(encoding="utf-8")
        )
        checkpoint = SignedWitnessCheckpoint.model_validate_json(
            witness_checkpoint_path.read_text(encoding="utf-8")
        )
        record = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).append(proof, checkpoint, witness_trust, ledger)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint registry store failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(record.to_json())
    else:
        console.print(
            f"Stored checkpoint registry sequence={record.sequence} "
            f"tree_size={record.checkpoint.statement.current_tree_size}"
        )


@benchmark_app.command("agent-cli-checkpoint-registry-export-template")
def export_agent_cli_checkpoint_registry_template(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    source_peer_id: str = _CHECKPOINT_SOURCE_PEER_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    sequence: int | None = _CHECKPOINT_SEQUENCE_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create a detached peer-signing request for one exact registry record."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerTrust,
        CheckpointRegistryStore,
        build_checkpoint_exchange_request,
    )

    try:
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        snapshot = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).replay(witness_trust, ledger)
        if not snapshot.records:
            raise ValueError("checkpoint registry has no records to export")
        selected_sequence = len(snapshot.records) - 1 if sequence is None else sequence
        if selected_sequence >= len(snapshot.records):
            raise ValueError("checkpoint registry sequence does not exist")
        request = build_checkpoint_exchange_request(
            snapshot.records[selected_sequence],
            peer_trust,
            source_peer_id=source_peer_id,
        )
        if not output_path.parent.exists():
            raise ValueError("checkpoint export output parent must already exist")
        if output_path.exists():
            raise ValueError("checkpoint export output already exists")
        _write_new_evidence(output_path, request.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint registry export failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(request.to_json())
    else:
        console.print(
            "Created checkpoint exchange signing request "
            f"sequence={request.statement.record_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-registry-import")
def import_agent_cli_checkpoint_registry_packet(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    packet_path: Path = _CHECKPOINT_PACKET_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Authenticate and atomically import one peer checkpoint packet."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerTrust,
        CheckpointRegistryStore,
        SignedCheckpointExchangePacket,
    )

    try:
        if not registry_path.parent.exists():
            raise ValueError("checkpoint registry parent must already exist")
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        packet = SignedCheckpointExchangePacket.model_validate_json(
            packet_path.read_text(encoding="utf-8")
        )
        record = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).import_packet(packet, peer_trust, witness_trust, ledger)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint registry import failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(record.to_json())
    else:
        console.print(
            f"Imported checkpoint registry sequence={record.sequence} "
            f"tree_size={record.checkpoint.statement.current_tree_size}"
        )


@benchmark_app.command("agent-cli-checkpoint-range-export-template")
def export_agent_cli_checkpoint_range_template(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    source_peer_id: str = _CHECKPOINT_SOURCE_PEER_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    start_sequence: int = _CHECKPOINT_START_SEQUENCE_OPTION,
    max_records: int = _CHECKPOINT_MAX_RECORDS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create one signing request for a bounded contiguous registry range."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerTrust,
        CheckpointRegistryStore,
        build_checkpoint_range_request,
    )

    try:
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        snapshot = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).replay(witness_trust, ledger)
        if start_sequence >= snapshot.record_count:
            raise ValueError("checkpoint range start sequence does not exist")
        records = snapshot.records[start_sequence : start_sequence + max_records]
        request = build_checkpoint_range_request(
            records,
            peer_trust,
            source_peer_id=source_peer_id,
        )
        if not output_path.parent.exists():
            raise ValueError("checkpoint range output parent must already exist")
        if output_path.exists():
            raise ValueError("checkpoint range output already exists")
        _write_new_evidence(output_path, request.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint range export failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(request.to_json())
    else:
        console.print(
            "Created checkpoint range signing request "
            f"{request.statement.first_sequence}->"
            f"{request.statement.last_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-range-import")
def import_agent_cli_checkpoint_range(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    range_bundle_path: Path = _CHECKPOINT_RANGE_BUNDLE_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Authenticate a range and atomically append its missing suffix."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerTrust,
        CheckpointRegistryStore,
        SignedCheckpointRangeBundle,
    )

    try:
        if not registry_path.parent.exists():
            raise ValueError("checkpoint registry parent must already exist")
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        bundle = SignedCheckpointRangeBundle.model_validate_json(
            range_bundle_path.read_text(encoding="utf-8")
        )
        snapshot = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).import_range_bundle(bundle, peer_trust, witness_trust, ledger)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint range import failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(snapshot.to_json())
    else:
        console.print(
            "Imported checkpoint range "
            f"records={snapshot.record_count} tree_size={snapshot.current_tree_size}"
        )


@benchmark_app.command("agent-cli-checkpoint-acknowledgement-template")
def create_agent_cli_checkpoint_acknowledgement_template(
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    range_bundle_path: Path = _CHECKPOINT_RANGE_BUNDLE_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    acknowledging_peer_id: str = _CHECKPOINT_ACKNOWLEDGING_PEER_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create a receiver signing request for an exactly applied range head."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerTrust,
        CheckpointRegistryStore,
        SignedCheckpointRangeBundle,
        build_checkpoint_acknowledgement_request,
    )

    try:
        witness_trust, ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        bundle = SignedCheckpointRangeBundle.model_validate_json(
            range_bundle_path.read_text(encoding="utf-8")
        )
        snapshot = CheckpointRegistryStore(
            registry_path,
            registry_id=registry_id,
        ).replay(witness_trust, ledger)
        request = build_checkpoint_acknowledgement_request(
            bundle,
            snapshot,
            peer_trust,
            acknowledging_peer_id=acknowledging_peer_id,
        )
        if not output_path.parent.exists():
            raise ValueError("checkpoint acknowledgement output parent must already exist")
        if output_path.exists():
            raise ValueError("checkpoint acknowledgement output already exists")
        _write_new_evidence(output_path, request.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint acknowledgement failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(request.to_json())
    else:
        console.print(
            "Created checkpoint acknowledgement signing request "
            f"sequence={request.statement.acknowledged_record_sequence}"
        )


def _load_checkpoint_peer_trust_source(
    peer_trust_path: Path | None,
    peer_trust_ledger_path: Path | None,
) -> Any:
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_peer_trust_ledger import CheckpointPeerTrustLedger

    if (peer_trust_path is None) == (peer_trust_ledger_path is None):
        raise ValueError("exactly one of --peer-trust or --peer-trust-ledger is required")
    if peer_trust_path is not None:
        return CheckpointPeerTrust.model_validate_json(peer_trust_path.read_text(encoding="utf-8"))
    assert peer_trust_ledger_path is not None
    return CheckpointPeerTrustLedger.model_validate_json(
        peer_trust_ledger_path.read_text(encoding="utf-8")
    )


def _active_checkpoint_peer_trust(peer_trust_source: Any) -> Any:
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_peer_trust_ledger import CheckpointPeerTrustLedger

    if isinstance(peer_trust_source, CheckpointPeerTrust):
        return peer_trust_source
    if isinstance(peer_trust_source, CheckpointPeerTrustLedger):
        return peer_trust_source.active_trust
    raise ValueError("unsupported checkpoint peer trust source")


def _build_checkpoint_mtls_client(
    *,
    descriptor_path: Path,
    peer_trust_source: Any,
    tls_trust_path: Path,
    client_peer_id: str,
    certificate_path: Path,
    private_key_path: Path,
    certificate_authority_path: Path,
    server_hostname: str,
    allowed_server_addresses: list[str],
) -> Any:
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsTrust,
        verify_checkpoint_peer_tls_trust,
    )
    from benchmarks.agent_cli_gossip_tls_transport import (
        CheckpointMutualTlsGossipClient,
    )

    active_peer_trust = _active_checkpoint_peer_trust(peer_trust_source)
    tls_trust = CheckpointPeerTlsTrust.model_validate_json(
        tls_trust_path.read_text(encoding="utf-8")
    )
    verify_checkpoint_peer_tls_trust(tls_trust, active_peer_trust)
    return CheckpointMutualTlsGossipClient(
        descriptor_path=descriptor_path,
        client_peer_id=client_peer_id,
        tls_trust=tls_trust,
        certificate_path=certificate_path,
        private_key_path=private_key_path,
        certificate_authority_path=certificate_authority_path,
        server_hostname=server_hostname,
        allowed_server_addresses=frozenset(allowed_server_addresses),
    )


@benchmark_app.command("agent-cli-checkpoint-cursor-store")
def store_agent_cli_checkpoint_cursor(
    cursor_ledger_path: Path = _CHECKPOINT_CURSOR_LEDGER_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    acknowledgement_path: Path = _CHECKPOINT_ACKNOWLEDGEMENT_INPUT,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Verify and durably store one monotonic peer acknowledgement."""
    from benchmarks.agent_cli_checkpoint_registry import (
        CheckpointPeerCursorStore,
        SignedCheckpointAcknowledgement,
    )

    try:
        if not cursor_ledger_path.parent.exists():
            raise ValueError("checkpoint cursor ledger parent must already exist")
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        acknowledgement = SignedCheckpointAcknowledgement.model_validate_json(
            acknowledgement_path.read_text(encoding="utf-8")
        )
        record = CheckpointPeerCursorStore(
            cursor_ledger_path,
            registry_id=registry_id,
        ).append(acknowledgement, peer_trust)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint cursor store failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(record.to_json())
    else:
        console.print(
            "Stored checkpoint peer cursor "
            f"sequence={record.acknowledgement.statement.acknowledged_record_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-cursor-status")
def show_agent_cli_checkpoint_cursor_status(
    cursor_ledger_path: Path = _CHECKPOINT_CURSOR_LEDGER_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Replay peer acknowledgements without changing the cursor ledger."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerCursorStore

    try:
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        snapshot = CheckpointPeerCursorStore(
            cursor_ledger_path,
            registry_id=registry_id,
        ).replay(peer_trust)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint cursor status failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(snapshot.to_json())
    else:
        console.print(
            "Verified checkpoint peer cursors "
            f"records={snapshot.cursor_count} peers={len(snapshot.positions)}"
        )


def _load_checkpoint_gossip_bundles(path: Path) -> tuple[Any, ...]:
    from benchmarks.agent_cli_checkpoint_registry import SignedCheckpointRangeBundle

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("bundles"), list):
        raise ValueError("checkpoint gossip bundles must contain a JSON bundles array")
    return tuple(SignedCheckpointRangeBundle.model_validate(item) for item in payload["bundles"])


@benchmark_app.command("agent-cli-checkpoint-gossip-serve")
def serve_agent_cli_checkpoint_gossip(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_OUTPUT,
    range_bundles_path: Path = _CHECKPOINT_GOSSIP_BUNDLES_INPUT,
    cursor_ledger_path: Path = _CHECKPOINT_CURSOR_LEDGER_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    source_peer_id: str = _CHECKPOINT_SOURCE_PEER_OPTION,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    max_requests: int = _CHECKPOINT_GOSSIP_MAX_REQUESTS_OPTION,
    lifetime_seconds: float = _CHECKPOINT_GOSSIP_LIFETIME_OPTION,
) -> None:
    """Explicitly serve pre-signed checkpoint artifacts on loopback only."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerCursorStore
    from benchmarks.agent_cli_gossip import CheckpointGossipService
    from benchmarks.agent_cli_gossip_transport import CheckpointGossipServer

    try:
        if not descriptor_path.parent.exists():
            raise ValueError("checkpoint gossip descriptor parent must already exist")
        if not cursor_ledger_path.parent.exists():
            raise ValueError("checkpoint gossip cursor parent must already exist")
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        service = CheckpointGossipService(
            registry_id=registry_id,
            source_peer_id=source_peer_id,
            range_bundles=_load_checkpoint_gossip_bundles(range_bundles_path),
            cursor_store=CheckpointPeerCursorStore(
                cursor_ledger_path,
                registry_id=registry_id,
            ),
            peer_trust=peer_trust,
        )

        async def run_server() -> None:
            server = CheckpointGossipServer(
                descriptor_path=descriptor_path,
                registry_id=registry_id,
                source_peer_id=source_peer_id,
                handler=service,
                max_requests=max_requests,
            )
            async with server:
                console.print(
                    "Checkpoint gossip listening on loopback "
                    f"descriptor={descriptor_path} max_requests={max_requests}"
                )
                await server.serve_until_stopped(
                    lifetime_timeout_seconds=lifetime_seconds,
                )

        _run(run_server())
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint gossip server failed: {exc}[/red]")
        raise typer.Exit(code=1) from None


@benchmark_app.command("agent-cli-checkpoint-gossip-status")
def show_agent_cli_checkpoint_gossip_status(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Query authenticated range availability without changing either peer."""
    from benchmarks.agent_cli_gossip import fetch_checkpoint_gossip_status

    try:
        status = _run(fetch_checkpoint_gossip_status(descriptor_path=descriptor_path))
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint gossip status failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(json.dumps(status, ensure_ascii=False, sort_keys=True))
    else:
        console.print(
            "Authenticated checkpoint gossip "
            f"source={status['source_peer_id']} "
            f"ranges={len(status['available_ranges'])}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-mtls-serve")
def serve_agent_cli_checkpoint_gossip_mtls(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_OUTPUT,
    range_bundles_path: Path = _CHECKPOINT_GOSSIP_BUNDLES_INPUT,
    cursor_ledger_path: Path = _CHECKPOINT_CURSOR_LEDGER_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    source_peer_id: str = _CHECKPOINT_SOURCE_PEER_OPTION,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    tls_trust_path: Path = _CHECKPOINT_TLS_TRUST_INPUT,
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    private_key_path: Path = _CHECKPOINT_TLS_PRIVATE_KEY_INPUT,
    certificate_authority_path: Path = _CHECKPOINT_TLS_CA_INPUT,
    bind_host: str = _CHECKPOINT_TLS_BIND_HOST_OPTION,
    advertised_host: str = _CHECKPOINT_TLS_ADVERTISED_HOST_OPTION,
    allowed_client_addresses: list[str] = _CHECKPOINT_TLS_ALLOWED_CLIENTS_OPTION,
    max_requests: int = _CHECKPOINT_GOSSIP_MAX_REQUESTS_OPTION,
    lifetime_seconds: float = _CHECKPOINT_GOSSIP_LIFETIME_OPTION,
) -> None:
    """Serve checkpoint gossip over TLS 1.3 mutual authentication."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerCursorStore
    from benchmarks.agent_cli_gossip import CheckpointGossipService
    from benchmarks.agent_cli_gossip_tls_identity import (
        CheckpointPeerTlsTrust,
        verify_checkpoint_peer_tls_trust,
    )
    from benchmarks.agent_cli_gossip_tls_transport import (
        CheckpointMutualTlsGossipServer,
    )

    try:
        if not descriptor_path.parent.exists():
            raise ValueError("checkpoint gossip descriptor parent must already exist")
        if not cursor_ledger_path.parent.exists():
            raise ValueError("checkpoint gossip cursor parent must already exist")
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        tls_trust = CheckpointPeerTlsTrust.model_validate_json(
            tls_trust_path.read_text(encoding="utf-8")
        )
        verify_checkpoint_peer_tls_trust(
            tls_trust,
            _active_checkpoint_peer_trust(peer_trust),
        )
        service = CheckpointGossipService(
            registry_id=registry_id,
            source_peer_id=source_peer_id,
            range_bundles=_load_checkpoint_gossip_bundles(range_bundles_path),
            cursor_store=CheckpointPeerCursorStore(
                cursor_ledger_path,
                registry_id=registry_id,
            ),
            peer_trust=peer_trust,
        )

        async def run_server() -> None:
            server = CheckpointMutualTlsGossipServer(
                descriptor_path=descriptor_path,
                bind_host=bind_host,
                advertised_host=advertised_host,
                registry_id=registry_id,
                server_peer_id=source_peer_id,
                handler=service,
                tls_trust=tls_trust,
                certificate_path=certificate_path,
                private_key_path=private_key_path,
                certificate_authority_path=certificate_authority_path,
                allowed_client_addresses=frozenset(allowed_client_addresses),
                max_requests=max_requests,
            )
            async with server:
                console.print(
                    "Checkpoint gossip listening with TLS 1.3 mutual auth "
                    f"descriptor={descriptor_path} max_requests={max_requests}"
                )
                await server.serve_until_stopped(lifetime_timeout_seconds=lifetime_seconds)

        _run(run_server())
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint mTLS server failed: {exc}[/red]")
        raise typer.Exit(code=1) from None


@benchmark_app.command("agent-cli-checkpoint-gossip-mtls-status")
def show_agent_cli_checkpoint_gossip_mtls_status(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    peer_trust_path: Path = _CHECKPOINT_PEER_TRUST_INPUT,
    tls_trust_path: Path = _CHECKPOINT_TLS_TRUST_INPUT,
    client_peer_id: str = _CHECKPOINT_TLS_CLIENT_PEER_OPTION,
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    private_key_path: Path = _CHECKPOINT_TLS_PRIVATE_KEY_INPUT,
    certificate_authority_path: Path = _CHECKPOINT_TLS_CA_INPUT,
    server_hostname: str = _CHECKPOINT_TLS_SERVER_HOSTNAME_OPTION,
    allowed_server_addresses: list[str] = _CHECKPOINT_TLS_ALLOWED_SERVERS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Query checkpoint status over pinned TLS 1.3 mutual authentication."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointPeerTrust
    from benchmarks.agent_cli_gossip import fetch_checkpoint_gossip_status

    try:
        peer_trust = CheckpointPeerTrust.model_validate_json(
            peer_trust_path.read_text(encoding="utf-8")
        )
        client = _build_checkpoint_mtls_client(
            descriptor_path=descriptor_path,
            peer_trust_source=peer_trust,
            tls_trust_path=tls_trust_path,
            client_peer_id=client_peer_id,
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            certificate_authority_path=certificate_authority_path,
            server_hostname=server_hostname,
            allowed_server_addresses=allowed_server_addresses,
        )
        status = _run(
            fetch_checkpoint_gossip_status(
                descriptor_path=descriptor_path,
                request_sender=client,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint mTLS status failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(json.dumps(status, ensure_ascii=False, sort_keys=True))
    else:
        console.print(
            "Mutually authenticated checkpoint gossip "
            f"source={status.get('source_peer_id', 'unknown')} "
            f"ranges={len(status.get('available_ranges', []))}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-mtls-fetch")
def fetch_agent_cli_checkpoint_gossip_mtls_range(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    start_sequence: int = _CHECKPOINT_START_SEQUENCE_OPTION,
    max_records: int = _CHECKPOINT_MAX_RECORDS_OPTION,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    tls_trust_path: Path = _CHECKPOINT_TLS_TRUST_INPUT,
    client_peer_id: str = _CHECKPOINT_TLS_CLIENT_PEER_OPTION,
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    private_key_path: Path = _CHECKPOINT_TLS_PRIVATE_KEY_INPUT,
    certificate_authority_path: Path = _CHECKPOINT_TLS_CA_INPUT,
    server_hostname: str = _CHECKPOINT_TLS_SERVER_HOSTNAME_OPTION,
    allowed_server_addresses: list[str] = _CHECKPOINT_TLS_ALLOWED_SERVERS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Fetch and verify one signed range over pinned mutual TLS."""
    from benchmarks.agent_cli_gossip import fetch_signed_checkpoint_range

    try:
        if not output_path.parent.exists():
            raise ValueError("checkpoint gossip output parent must already exist")
        if output_path.exists():
            raise ValueError("checkpoint gossip output already exists")
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        client = _build_checkpoint_mtls_client(
            descriptor_path=descriptor_path,
            peer_trust_source=peer_trust,
            tls_trust_path=tls_trust_path,
            client_peer_id=client_peer_id,
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            certificate_authority_path=certificate_authority_path,
            server_hostname=server_hostname,
            allowed_server_addresses=allowed_server_addresses,
        )
        bundle = _run(
            fetch_signed_checkpoint_range(
                descriptor_path=descriptor_path,
                start_sequence=start_sequence,
                max_records=max_records,
                peer_trust=peer_trust,
                request_sender=client,
            )
        )
        _write_new_evidence(output_path, bundle.to_json())
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint mTLS fetch failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(bundle.to_json())
    else:
        console.print(
            "Fetched mutually authenticated checkpoint range "
            f"{bundle.statement.first_sequence}->{bundle.statement.last_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-mtls-ack")
def submit_agent_cli_checkpoint_gossip_mtls_acknowledgement(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    acknowledgement_path: Path = _CHECKPOINT_ACKNOWLEDGEMENT_INPUT,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    tls_trust_path: Path = _CHECKPOINT_TLS_TRUST_INPUT,
    client_peer_id: str = _CHECKPOINT_TLS_CLIENT_PEER_OPTION,
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    private_key_path: Path = _CHECKPOINT_TLS_PRIVATE_KEY_INPUT,
    certificate_authority_path: Path = _CHECKPOINT_TLS_CA_INPUT,
    server_hostname: str = _CHECKPOINT_TLS_SERVER_HOSTNAME_OPTION,
    allowed_server_addresses: list[str] = _CHECKPOINT_TLS_ALLOWED_SERVERS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Submit a signed acknowledgement over pinned mutual TLS."""
    from benchmarks.agent_cli_checkpoint_registry import SignedCheckpointAcknowledgement
    from benchmarks.agent_cli_gossip import submit_signed_checkpoint_acknowledgement

    try:
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        client = _build_checkpoint_mtls_client(
            descriptor_path=descriptor_path,
            peer_trust_source=peer_trust,
            tls_trust_path=tls_trust_path,
            client_peer_id=client_peer_id,
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            certificate_authority_path=certificate_authority_path,
            server_hostname=server_hostname,
            allowed_server_addresses=allowed_server_addresses,
        )
        acknowledgement = SignedCheckpointAcknowledgement.model_validate_json(
            acknowledgement_path.read_text(encoding="utf-8")
        )
        record = _run(
            submit_signed_checkpoint_acknowledgement(
                descriptor_path=descriptor_path,
                acknowledgement=acknowledgement,
                request_sender=client,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint mTLS ack failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(record.to_json())
    else:
        console.print(
            "Submitted mutually authenticated checkpoint acknowledgement "
            f"sequence={record.acknowledgement.statement.acknowledged_record_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-fetch")
def fetch_agent_cli_checkpoint_gossip_range(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    start_sequence: int = _CHECKPOINT_START_SEQUENCE_OPTION,
    max_records: int = _CHECKPOINT_MAX_RECORDS_OPTION,
    peer_trust_path: Path | None = _OPTIONAL_CHECKPOINT_PEER_TRUST_INPUT,
    peer_trust_ledger_path: Path | None = (_OPTIONAL_CHECKPOINT_PEER_TRUST_LEDGER_INPUT),
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Fetch and independently verify one already signed checkpoint range."""
    from benchmarks.agent_cli_gossip import fetch_signed_checkpoint_range

    try:
        if not output_path.parent.exists():
            raise ValueError("checkpoint gossip output parent must already exist")
        if output_path.exists():
            raise ValueError("checkpoint gossip output already exists")
        peer_trust = _load_checkpoint_peer_trust_source(
            peer_trust_path,
            peer_trust_ledger_path,
        )
        bundle = _run(
            fetch_signed_checkpoint_range(
                descriptor_path=descriptor_path,
                start_sequence=start_sequence,
                max_records=max_records,
                peer_trust=peer_trust,
            )
        )
        _write_new_evidence(output_path, bundle.to_json())
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint gossip fetch failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(bundle.to_json())
    else:
        console.print(
            "Fetched authenticated checkpoint range "
            f"{bundle.statement.first_sequence}->{bundle.statement.last_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-ack")
def submit_agent_cli_checkpoint_gossip_acknowledgement(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    acknowledgement_path: Path = _CHECKPOINT_ACKNOWLEDGEMENT_INPUT,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Submit a signed range acknowledgement to its source peer."""
    from benchmarks.agent_cli_checkpoint_registry import SignedCheckpointAcknowledgement
    from benchmarks.agent_cli_gossip import submit_signed_checkpoint_acknowledgement

    try:
        acknowledgement = SignedCheckpointAcknowledgement.model_validate_json(
            acknowledgement_path.read_text(encoding="utf-8")
        )
        record = _run(
            submit_signed_checkpoint_acknowledgement(
                descriptor_path=descriptor_path,
                acknowledgement=acknowledgement,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint gossip ack failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(record.to_json())
    else:
        console.print(
            "Submitted authenticated checkpoint acknowledgement "
            f"sequence={record.acknowledgement.statement.acknowledged_record_sequence}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-sync")
def sync_agent_cli_checkpoint_gossip(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    sync_audit_path: Path = _CHECKPOINT_GOSSIP_SYNC_AUDIT_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    source_peer_id: str = _CHECKPOINT_SOURCE_PEER_OPTION,
    peer_trust_ledger_path: Path = _CHECKPOINT_PEER_TRUST_LEDGER_INPUT,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    max_rounds: int = _CHECKPOINT_GOSSIP_SYNC_ROUNDS_OPTION,
    max_records: int = _CHECKPOINT_MAX_RECORDS_OPTION,
    max_attempts: int = _CHECKPOINT_GOSSIP_SYNC_ATTEMPTS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Run one bounded resumable pull loop without reading private keys."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointRegistryStore
    from benchmarks.agent_cli_gossip_sync import (
        CheckpointGossipSyncAuditStore,
        CheckpointGossipSyncPolicy,
        run_checkpoint_gossip_sync,
    )
    from benchmarks.agent_cli_peer_trust_ledger import CheckpointPeerTrustLedger

    try:
        if not registry_path.parent.exists():
            raise ValueError("checkpoint gossip registry parent must already exist")
        if not sync_audit_path.parent.exists():
            raise ValueError("checkpoint gossip sync audit parent must already exist")
        witness_trust, authority_ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust_ledger = CheckpointPeerTrustLedger.model_validate_json(
            peer_trust_ledger_path.read_text(encoding="utf-8")
        )
        retry_delays = tuple(min(0.05 * (2**index), 1.0) for index in range(max_attempts - 1))
        result = _run(
            run_checkpoint_gossip_sync(
                descriptor_path=descriptor_path,
                registry_store=CheckpointRegistryStore(
                    registry_path,
                    registry_id=registry_id,
                ),
                audit_store=CheckpointGossipSyncAuditStore(
                    sync_audit_path,
                    registry_id=registry_id,
                    source_peer_id=source_peer_id,
                ),
                peer_trust_ledger=peer_trust_ledger,
                witness_trust=witness_trust,
                authority_root_ledger=authority_ledger,
                policy=CheckpointGossipSyncPolicy(
                    max_rounds=max_rounds,
                    max_records=max_records,
                    max_attempts_per_request=max_attempts,
                    retry_delays_seconds=retry_delays,
                ),
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint gossip sync failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(result.to_json())
    else:
        console.print(
            "Checkpoint gossip sync stopped "
            f"reason={result.stop_reason} records={result.local_record_count} "
            f"imported={result.records_imported} retries={result.retries}"
        )


@benchmark_app.command("agent-cli-checkpoint-gossip-mtls-sync")
def sync_agent_cli_checkpoint_gossip_mtls(
    descriptor_path: Path = _CHECKPOINT_GOSSIP_DESCRIPTOR_INPUT,
    registry_path: Path = _CHECKPOINT_REGISTRY_OPTION,
    sync_audit_path: Path = _CHECKPOINT_GOSSIP_SYNC_AUDIT_OPTION,
    registry_id: str = _CHECKPOINT_REGISTRY_ID_OPTION,
    source_peer_id: str = _CHECKPOINT_SOURCE_PEER_OPTION,
    peer_trust_ledger_path: Path = _CHECKPOINT_PEER_TRUST_LEDGER_INPUT,
    witness_trust_path: Path = _WITNESS_TRUST_INPUT,
    authority_root_ledger_path: Path = _AUTHORITY_ROOT_LEDGER_INPUT,
    tls_trust_path: Path = _CHECKPOINT_TLS_TRUST_INPUT,
    client_peer_id: str = _CHECKPOINT_TLS_CLIENT_PEER_OPTION,
    certificate_path: Path = _CHECKPOINT_TLS_CERTIFICATE_INPUT,
    private_key_path: Path = _CHECKPOINT_TLS_PRIVATE_KEY_INPUT,
    certificate_authority_path: Path = _CHECKPOINT_TLS_CA_INPUT,
    server_hostname: str = _CHECKPOINT_TLS_SERVER_HOSTNAME_OPTION,
    allowed_server_addresses: list[str] = _CHECKPOINT_TLS_ALLOWED_SERVERS_OPTION,
    max_rounds: int = _CHECKPOINT_GOSSIP_SYNC_ROUNDS_OPTION,
    max_records: int = _CHECKPOINT_MAX_RECORDS_OPTION,
    max_attempts: int = _CHECKPOINT_GOSSIP_SYNC_ATTEMPTS_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Run the bounded resumable pull loop over pinned mutual TLS."""
    from benchmarks.agent_cli_checkpoint_registry import CheckpointRegistryStore
    from benchmarks.agent_cli_gossip_sync import (
        CheckpointGossipSyncAuditStore,
        CheckpointGossipSyncPolicy,
        run_checkpoint_gossip_sync,
    )
    from benchmarks.agent_cli_peer_trust_ledger import CheckpointPeerTrustLedger

    try:
        if not registry_path.parent.exists():
            raise ValueError("checkpoint gossip registry parent must already exist")
        if not sync_audit_path.parent.exists():
            raise ValueError("checkpoint gossip sync audit parent must already exist")
        witness_trust, authority_ledger = _load_checkpoint_registry_dependencies(
            witness_trust_path,
            authority_root_ledger_path,
        )
        peer_trust_ledger = CheckpointPeerTrustLedger.model_validate_json(
            peer_trust_ledger_path.read_text(encoding="utf-8")
        )
        client = _build_checkpoint_mtls_client(
            descriptor_path=descriptor_path,
            peer_trust_source=peer_trust_ledger,
            tls_trust_path=tls_trust_path,
            client_peer_id=client_peer_id,
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            certificate_authority_path=certificate_authority_path,
            server_hostname=server_hostname,
            allowed_server_addresses=allowed_server_addresses,
        )
        retry_delays = tuple(min(0.05 * (2**index), 1.0) for index in range(max_attempts - 1))
        result = _run(
            run_checkpoint_gossip_sync(
                descriptor_path=descriptor_path,
                registry_store=CheckpointRegistryStore(
                    registry_path,
                    registry_id=registry_id,
                ),
                audit_store=CheckpointGossipSyncAuditStore(
                    sync_audit_path,
                    registry_id=registry_id,
                    source_peer_id=source_peer_id,
                ),
                peer_trust_ledger=peer_trust_ledger,
                witness_trust=witness_trust,
                authority_root_ledger=authority_ledger,
                policy=CheckpointGossipSyncPolicy(
                    max_rounds=max_rounds,
                    max_records=max_records,
                    max_attempts_per_request=max_attempts,
                    retry_delays_seconds=retry_delays,
                ),
                request_sender=client,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Agent CLI checkpoint mTLS sync failed: {exc}[/red]")
        raise typer.Exit(code=1) from None
    if as_json:
        typer.echo(result.to_json())
    else:
        console.print(
            "Mutually authenticated checkpoint sync stopped "
            f"reason={result.stop_reason} records={result.local_record_count} "
            f"imported={result.records_imported} retries={result.retries}"
        )


@benchmark_app.command("agent-cli-campaign-envelope-template")
def create_agent_cli_campaign_envelope_template(
    manifest_path: Path = _AGENT_CLI_MANIFEST_OPTION,
    preflight_path: Path = _PREFLIGHT_INPUT_OPTION,
    evidence_path: Path = _FINALIZE_EVIDENCE_OPTION,
    reviews_path: Path = _FINALIZE_REVIEWS_OPTION,
    review_policy_path: Path = _OPTIONAL_REVIEW_POLICY_INPUT,
    reviewer_trust_path: Path = _OPTIONAL_REVIEWER_TRUST_INPUT,
    reviewer_authority_path: Path = _OPTIONAL_REVIEWER_AUTHORITY_INPUT,
    reviewer_enrollments_path: Path = _OPTIONAL_REVIEWER_ENROLLMENTS_INPUT,
    authority_root_ledger_path: Path | None = _OPTIONAL_AUTHORITY_ROOT_LEDGER_INPUT,
    attestations_path: Path = _OPTIONAL_ATTESTATIONS_INPUT,
    results_path: Path = _AGENT_CLI_RESULTS_OPTION,
    output_path: Path = _PREFLIGHT_OUTPUT_OPTION,
    as_json: bool = _AGENT_CLI_JSON_OPTION,
) -> None:
    """Create one authority signing payload for the complete finalized campaign."""
    from benchmarks.agent_cli_adjudication import AdjudicationReviews, RecordedEvidence
    from benchmarks.agent_cli_attestation import (
        ReviewAttestationBundle,
        ReviewerTrustDeclaration,
        build_reviewer_trust,
    )
    from benchmarks.agent_cli_authority import (
        BenchmarkAuthorityDeclaration,
        ReviewerEnrollmentBundle,
        build_benchmark_authority,
        build_campaign_envelope_request,
    )
    from benchmarks.agent_cli_comparison import AgentCliManifest, RecordedResults
    from benchmarks.agent_cli_preflight import CampaignPreflight
    from benchmarks.agent_cli_review_policy import (
        ReviewerPolicyDeclaration,
        build_reviewer_policy,
    )

    try:
        required = {
            "--review-policy": review_policy_path,
            "--reviewer-trust": reviewer_trust_path,
            "--reviewer-authority": reviewer_authority_path,
            "--reviewer-enrollments": reviewer_enrollments_path,
            "--attestations": attestations_path,
        }
        missing = [name for name, path in required.items() if path is None]
        if missing:
            raise ValueError(f"required authority artifact missing: {', '.join(missing)}")
        assert review_policy_path is not None
        assert reviewer_trust_path is not None
        assert reviewer_authority_path is not None
        assert reviewer_enrollments_path is not None
        assert attestations_path is not None
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        preflight = CampaignPreflight.model_validate_json(
            preflight_path.read_text(encoding="utf-8")
        )
        evidence = RecordedEvidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
        reviews = AdjudicationReviews.model_validate_json(reviews_path.read_text(encoding="utf-8"))
        policy = build_reviewer_policy(
            ReviewerPolicyDeclaration.model_validate_json(
                review_policy_path.read_text(encoding="utf-8")
            )
        )
        authority = build_benchmark_authority(
            BenchmarkAuthorityDeclaration.model_validate_json(
                reviewer_authority_path.read_text(encoding="utf-8")
            )
        )
        trust = build_reviewer_trust(
            ReviewerTrustDeclaration.model_validate_json(
                reviewer_trust_path.read_text(encoding="utf-8")
            ),
            policy,
        )
        enrollments = ReviewerEnrollmentBundle.model_validate_json(
            reviewer_enrollments_path.read_text(encoding="utf-8")
        )
        attestations = ReviewAttestationBundle.model_validate_json(
            attestations_path.read_text(encoding="utf-8")
        )
        results = RecordedResults.model_validate_json(results_path.read_text(encoding="utf-8"))
        authority_root_ledger = None
        if authority_root_ledger_path is not None:
            from benchmarks.agent_cli_transparency import SignedAuthorityRootLedger

            authority_root_ledger = SignedAuthorityRootLedger.model_validate_json(
                authority_root_ledger_path.read_text(encoding="utf-8")
            )
        template = build_campaign_envelope_request(
            authority=authority,
            manifest=manifest,
            preflight=preflight,
            evidence=evidence,
            reviews=reviews,
            review_policy=policy,
            reviewer_trust=trust,
            reviewer_enrollments=enrollments,
            attestations=attestations,
            results=results,
            authority_root_ledger=authority_root_ledger,
        )
        if not output_path.parent.exists():
            raise ValueError("campaign envelope output parent must already exist")
        if output_path.exists():
            raise ValueError("campaign envelope output already exists")
        _write_new_evidence(output_path, template.to_json())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Agent CLI campaign envelope template failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    if as_json:
        typer.echo(template.to_json())
    else:
        console.print("Created authority campaign envelope signing request")


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
    reviewer_authority_path: Path | None = _OPTIONAL_REVIEWER_AUTHORITY_INPUT,
    reviewer_enrollments_path: Path | None = _OPTIONAL_REVIEWER_ENROLLMENTS_INPUT,
    campaign_envelope_path: Path | None = _OPTIONAL_CAMPAIGN_ENVELOPE_INPUT,
    authority_root_ledger_path: Path | None = _OPTIONAL_AUTHORITY_ROOT_LEDGER_INPUT,
    transparency_proof_path: Path | None = _OPTIONAL_TRANSPARENCY_PROOF_INPUT,
    transparency_consistency_path: Path | None = (_OPTIONAL_TRANSPARENCY_CONSISTENCY_INPUT),
    transparency_witness_trust_path: Path | None = (_OPTIONAL_TRANSPARENCY_WITNESS_TRUST_INPUT),
    witness_checkpoint_path: Path | None = _OPTIONAL_WITNESS_CHECKPOINT_INPUT,
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
        manifest = AgentCliManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        preflight = (
            CampaignPreflight.model_validate_json(preflight_path.read_text(encoding="utf-8"))
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
        reviewer_authority = None
        reviewer_enrollments = None
        campaign_envelope = None
        authority_root_ledger = None
        transparency_proof = None
        transparency_consistency_proof = None
        transparency_witness_trust = None
        witness_checkpoint = None
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
        if reviewer_authority_path is not None:
            from benchmarks.agent_cli_authority import (
                BenchmarkAuthorityDeclaration,
                build_benchmark_authority,
            )

            reviewer_authority = build_benchmark_authority(
                BenchmarkAuthorityDeclaration.model_validate_json(
                    reviewer_authority_path.read_text(encoding="utf-8")
                )
            )
        if reviewer_enrollments_path is not None:
            from benchmarks.agent_cli_authority import ReviewerEnrollmentBundle

            reviewer_enrollments = ReviewerEnrollmentBundle.model_validate_json(
                reviewer_enrollments_path.read_text(encoding="utf-8")
            )
        if campaign_envelope_path is not None:
            from benchmarks.agent_cli_authority import SignedCampaignEnvelope

            campaign_envelope = SignedCampaignEnvelope.model_validate_json(
                campaign_envelope_path.read_text(encoding="utf-8")
            )
        if authority_root_ledger_path is not None:
            from benchmarks.agent_cli_transparency import SignedAuthorityRootLedger

            authority_root_ledger = SignedAuthorityRootLedger.model_validate_json(
                authority_root_ledger_path.read_text(encoding="utf-8")
            )
        if transparency_proof_path is not None:
            from benchmarks.agent_cli_transparency import TransparencyInclusionProof

            transparency_proof = TransparencyInclusionProof.model_validate_json(
                transparency_proof_path.read_text(encoding="utf-8")
            )
        if transparency_consistency_path is not None:
            from benchmarks.agent_cli_transparency import (
                TransparencyConsistencyProof,
            )

            transparency_consistency_proof = TransparencyConsistencyProof.model_validate_json(
                transparency_consistency_path.read_text(encoding="utf-8")
            )
        if transparency_witness_trust_path is not None:
            from benchmarks.agent_cli_witness import (
                TransparencyWitnessTrustDeclaration,
                build_transparency_witness_trust,
            )

            transparency_witness_trust = build_transparency_witness_trust(
                TransparencyWitnessTrustDeclaration.model_validate_json(
                    transparency_witness_trust_path.read_text(encoding="utf-8")
                )
            )
        if witness_checkpoint_path is not None:
            from benchmarks.agent_cli_witness import SignedWitnessCheckpoint

            witness_checkpoint = SignedWitnessCheckpoint.model_validate_json(
                witness_checkpoint_path.read_text(encoding="utf-8")
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
            reviewer_authority=reviewer_authority,
            reviewer_enrollments=reviewer_enrollments,
            campaign_envelope=campaign_envelope,
            authority_root_ledger=authority_root_ledger,
            transparency_proof=transparency_proof,
            transparency_consistency_proof=transparency_consistency_proof,
            transparency_witness_trust=transparency_witness_trust,
            witness_checkpoint=witness_checkpoint,
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
