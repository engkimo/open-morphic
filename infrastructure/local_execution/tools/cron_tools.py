"""Cron tools — APScheduler-based scheduling for LAEE."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

# Lazy singleton scheduler
_scheduler = None
_scheduler_lock = asyncio.Lock()
# Track registered jobs for listing
_registered_jobs: dict[str, dict[str, Any]] = {}


async def _get_scheduler():  # noqa: ANN202
    """Lazy-init the APScheduler AsyncIOScheduler."""
    global _scheduler  # noqa: PLW0603
    async with _scheduler_lock:
        if _scheduler is None:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            _scheduler = AsyncIOScheduler()
            _scheduler.start()
        return _scheduler


def _make_job_func(cmd: str):  # noqa: ANN202
    """Create a callable that runs a shell command."""

    async def _run_cmd() -> None:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    return _run_cmd


async def cron_schedule(args: dict[str, Any]) -> str:
    """Schedule a recurring job with cron expression."""
    cmd = args.get("cmd", "")
    if not cmd:
        raise ValueError("cmd is required")

    cron_expr = args.get("cron", "")
    if not cron_expr:
        raise ValueError("cron expression is required (e.g. '0 9 * * *')")

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr} (expected 5 fields)")

    scheduler = await _get_scheduler()
    job_id = args.get("job_id", str(uuid.uuid4())[:8])

    scheduler.add_job(
        _make_job_func(cmd),
        "cron",
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        id=job_id,
        replace_existing=True,
    )
    _registered_jobs[job_id] = {"cmd": cmd, "cron": cron_expr, "type": "cron"}
    return f"Scheduled recurring job {job_id}: '{cmd}' with cron '{cron_expr}'"


async def cron_once(args: dict[str, Any]) -> str:
    """Schedule a one-shot timer job."""
    cmd = args.get("cmd", "")
    if not cmd:
        raise ValueError("cmd is required")

    delay_seconds = args.get("delay_seconds", 0)
    if delay_seconds <= 0:
        raise ValueError("delay_seconds must be positive")

    scheduler = await _get_scheduler()
    job_id = args.get("job_id", str(uuid.uuid4())[:8])

    from datetime import datetime, timedelta

    run_at = datetime.now() + timedelta(seconds=delay_seconds)
    scheduler.add_job(
        _make_job_func(cmd),
        "date",
        run_date=run_at,
        id=job_id,
        replace_existing=True,
    )
    _registered_jobs[job_id] = {
        "cmd": cmd,
        "delay_seconds": delay_seconds,
        "type": "once",
        "run_at": run_at.isoformat(),
    }
    return f"Scheduled one-shot job {job_id}: '{cmd}' in {delay_seconds}s"


async def cron_list(args: dict[str, Any]) -> str:
    """List all registered scheduled jobs."""
    if not _registered_jobs:
        return "No scheduled jobs."
    lines = []
    for job_id, info in _registered_jobs.items():
        if info["type"] == "cron":
            lines.append(f"  {job_id}: '{info['cmd']}' cron='{info['cron']}'")
        else:
            lines.append(f"  {job_id}: '{info['cmd']}' at {info.get('run_at', 'N/A')}")
    return "Scheduled jobs:\n" + "\n".join(lines)


async def cron_cancel(args: dict[str, Any]) -> str:
    """Cancel a scheduled job by ID."""
    job_id = args.get("job_id", "")
    if not job_id:
        raise ValueError("job_id is required")

    if job_id not in _registered_jobs:
        return f"Job {job_id} not found"

    scheduler = await _get_scheduler()
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass  # Job may have already executed
    _registered_jobs.pop(job_id, None)
    return f"Cancelled job {job_id}"
