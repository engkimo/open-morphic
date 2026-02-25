"""JSONL Audit Logger — append-only action log for LAEE."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from domain.entities.execution import Action
from domain.ports.audit_logger import AuditLogger
from domain.value_objects import RiskLevel


class JsonlAuditLogger(AuditLogger):
    """Append-only JSONL audit log.

    Every LAEE action is recorded with timestamp, tool, args, risk, and result.
    Compliant with Manus principle 3: file as infinite context.
    """

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self, action: Action, result: str, risk: RiskLevel, success: bool = True
    ) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": action.tool,
            "args": action.args,
            "risk": risk.name,
            "success": success,
            "result_summary": result[:500],
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def query(
        self,
        tool: str | None = None,
        risk: RiskLevel | None = None,
        since: datetime | None = None,
    ) -> list[dict]:
        if not self._path.exists():
            return []
        entries: list[dict] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if tool and entry["tool"] != tool:
                    continue
                if risk is not None and entry["risk"] != risk.name:
                    continue
                if since:
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if ts < since:
                        continue
                entries.append(entry)
        return entries
