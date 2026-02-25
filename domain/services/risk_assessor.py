"""RiskAssessor — Pure domain service. Evaluates action risk level.

No infrastructure dependencies. Uses only domain entities and value objects.
"""

from __future__ import annotations

import re

from domain.entities.execution import Action
from domain.value_objects import RiskLevel

# Patterns that indicate credential/sensitive file access
_CREDENTIAL_PATTERNS = [
    r"\.ssh/",
    r"\.aws/",
    r"\.gnupg/",
    r"\.kube/config",
    r"/\.env$",
    r"/\.env\.",
    r"credentials",
    r"\.pem$",
    r"id_rsa",
    r"id_ed25519",
]

_DANGEROUS_SHELL_PATTERNS = [
    r"\bsudo\b",
    r"\brm\s+-rf\b",
    r"\brm\s+-r\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\b:\(\)\{.*\}",  # fork bomb
    r"\bchmod\s+777\b",
    r"\bchown\s+-R\b",
]

# Static risk mapping: tool_name → base risk level
_TOOL_RISK_MAP: dict[str, RiskLevel] = {
    # SAFE
    "fs_read": RiskLevel.SAFE,
    "fs_glob": RiskLevel.SAFE,
    "fs_tree": RiskLevel.SAFE,
    "system_process_list": RiskLevel.SAFE,
    "system_resource_info": RiskLevel.SAFE,
    "system_clipboard_get": RiskLevel.SAFE,
    "system_screenshot": RiskLevel.SAFE,
    "browser_screenshot": RiskLevel.SAFE,
    "browser_extract": RiskLevel.SAFE,
    "dev_pkg_search": RiskLevel.SAFE,
    "cron_list": RiskLevel.SAFE,
    "gui_screenshot_ocr": RiskLevel.SAFE,
    # LOW
    "shell_background": RiskLevel.LOW,
    "system_notify": RiskLevel.LOW,
    "system_clipboard_set": RiskLevel.LOW,
    "browser_navigate": RiskLevel.LOW,
    "browser_pdf": RiskLevel.LOW,
    "gui_open_app": RiskLevel.LOW,
    "cron_once": RiskLevel.LOW,
    "cron_cancel": RiskLevel.LOW,
    "fs_watch": RiskLevel.LOW,
    # MEDIUM
    "shell_exec": RiskLevel.MEDIUM,
    "shell_stream": RiskLevel.MEDIUM,
    "shell_pipe": RiskLevel.MEDIUM,
    "fs_write": RiskLevel.MEDIUM,
    "fs_edit": RiskLevel.MEDIUM,
    "fs_move": RiskLevel.MEDIUM,
    "browser_click": RiskLevel.MEDIUM,
    "browser_type": RiskLevel.MEDIUM,
    "dev_git": RiskLevel.MEDIUM,
    "dev_docker": RiskLevel.MEDIUM,
    "dev_pkg_install": RiskLevel.MEDIUM,
    "dev_env_setup": RiskLevel.MEDIUM,
    "gui_applescript": RiskLevel.MEDIUM,
    "gui_accessibility": RiskLevel.MEDIUM,
    "cron_schedule": RiskLevel.MEDIUM,
    # HIGH
    "fs_delete": RiskLevel.HIGH,
    "system_process_kill": RiskLevel.HIGH,
}


class RiskAssessor:
    """Assess the risk level of an action based on tool name and arguments.

    Pure domain logic — no I/O, no external dependencies.
    """

    def assess(self, action: Action) -> RiskLevel:
        """Return the risk level for a given action."""
        base_risk = _TOOL_RISK_MAP.get(action.tool, RiskLevel.MEDIUM)

        # Escalate based on argument inspection
        escalated = self._check_escalation(action, base_risk)
        return escalated

    def _check_escalation(self, action: Action, base_risk: RiskLevel) -> RiskLevel:
        """Check if arguments escalate the base risk to a higher level."""
        path = action.args.get("path", "")
        cmd = action.args.get("cmd", "")
        recursive = action.args.get("recursive", False)

        # fs_delete + recursive → CRITICAL
        if action.tool == "fs_delete" and recursive:
            return RiskLevel.CRITICAL

        # Credential/sensitive file access → CRITICAL
        if path and self._is_sensitive_path(path):
            return RiskLevel.CRITICAL

        # Dangerous shell commands → CRITICAL
        if cmd and self._is_dangerous_command(cmd):
            return RiskLevel.CRITICAL

        return base_risk

    def _is_sensitive_path(self, path: str) -> bool:
        return any(re.search(p, path) for p in _CREDENTIAL_PATTERNS)

    def _is_dangerous_command(self, cmd: str) -> bool:
        return any(re.search(p, cmd) for p in _DANGEROUS_SHELL_PATTERNS)
